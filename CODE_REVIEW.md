# Code Review — Dermatology AI (Derma_AI)

**Reviewed revision:** `13a299a` (`pre-triage-removal`), working branch `arena/45118ec8-derma-ai`
**Review date:** 2026-10-29
**Reviewer:** Arena agent (static analysis + live behavioural probes against a throw-away copy)
**Scope:** every tracked source file — 12.3 kLOC of Python/HTML plus scripts, notebooks, config and docs
**Changes made by this review:** none. The repository was not modified (probes ran against a copy in `/tmp`).

---

## 1. Verdict

**This codebase is a good *demo shell* around an untrained model, and it is not fit for a pilot, a
live deployment, or a published result.** Four independent things are true at once:

1. The web layer looks production-shaped (bcrypt, rate limits, file-type checks, sessions, audit log)
   but has a **critical authorization hole** — any logged-in doctor can create accounts, reset other
   people's passwords, and revoke the admin's session. I reproduced all of this.
2. **The AI system has never actually been connected to a trained model.** `server.py` constructs
   `DermatologyCBM(...)` with `pretrained_backbone=True` and never loads a checkpoint, so the
   concept head and classifier are randomly initialised. Every "diagnosis" the dashboard produces is
   noise — unless torch is missing, in which case it returns a **hardcoded melanoma** instead.
3. **The numbers on the poster and slides are constants from a mock fallback function.** "84.3%
   HAM10000 accuracy", "<3% Fitz gap" and "12% override rate" are literally `_mock_analytics()` in
   `server.py:1028` and the `0.12` override rate hard-coded in `main.py`.
4. The public **poster still claims "HIPAA Compliant • 256-bit Encrypted • role-based access • full
   audit logging"**, none of which is true of this codebase (P1-13).

The research scaffolding (concept bottleneck, Grad-CAM/IG, fairness tracker, HITL buffer) is
reasonably well structured and clearly documented. The problem is that the *claims* have outrun the
*evidence*, and a few security controls were added in a way that broke the app they were protecting.

| Area | Status | Blocking? |
|---|---|---|
| Security / authorization | 🔴 Critical privilege escalation, stored XSS, CSRF gate breaks UI | Yes |
| Clinical safety of outputs | 🔴 Untrained model + fail-open mock diagnoses | Yes |
| Research integrity | 🔴 Circular metrics, published mock numbers, no held-out data | Yes (publication) |
| Data protection (PHI) | 🟠 Plaintext JSON, 0644, ephemeral disk, fake patients mixed in; poster claims HIPAA/encryption | Yes (real users) |
| ML pipeline correctness | 🟠 Train/serve skew, broken eval scripts, PPO claims don't hold | Yes (any result) |
| Reliability / concurrency | 🟠 Lost-update race loses 30% of concurrent writes | Yes (multi-user) |
| Tests / CI / packaging | 🔴 None at all (no tests, no CI, no lockfile) | Yes (maintainability) |
| Docs accuracy | 🟠 Placeholders, wrong dataset sizes, dead file references | No |

---

## 2. How this review was done

* **Static pass** over every `.py`, `.html`, `.yaml`, `.tex`, `.md` file, plus `ruff --select F,E9,B`
  (77 findings, incl. an undefined name and 30 unused imports).
* **Live probes.** I installed a minimal dependency set (FastAPI, Starlette TestClient, bcrypt,
  slowapi, filetype, numpy, pandas, Pillow) in a scratch venv, copied `dermatology-ai/` to `/tmp/probe`,
  booted the app through `create_app()` and exercised the API. Torch-dependent paths (model forward,
  PPO) were reviewed statically — torch is a ~1 GB install and its absence is itself informative
  (see finding P0-2).
* **Cross-checking** of every stated result against the code path that would produce it.

Everything labelled **Verified** below was reproduced during this review; the exact probe output is
in [Appendix B](#appendix-b--reproduction-log).

---

## 3. Findings

Severity: **P0** = must fix before any deployment, even internal demo to clinicians · **P1** = must
fix before any real data or any reported metric · **P2** = should fix before a pilot · **P3** = hygiene.

### P0 — Blockers

#### P0-1 · Inference runs on a randomly initialised model — no checkpoint is ever loaded
`server.py:574-586`, `main.py:run_ui`, `ui.py`

```python
model = DermatologyCBM(num_classes=3, num_concepts=7,
                       hrnet_name="hrnet_w18", pretrained_backbone=True, ...)
model = model.float(); model.eval()      # ← and that is all
```
`grep -n "load_state_dict\|ckpt\|checkpoint" server.py main.py ui.py` returns **nothing** for the CBM.
Only the ImageNet backbone is pretrained; `concept_bottleneck` and `classifier` are freshly
initialised (Kaiming/orthogonal, `model.py:180`). The PPO agent, by contrast, *is* loaded/saved.

**Impact.** Concept scores, predicted class, triage recommendation and Grad-CAM are all driven by
random weights. The demo *looks* like it is working (concepts vary with the image, heatmaps are
plausible) which makes this much more dangerous than an obvious crash. Any screenshot, demo or
poster produced from this build shows noise presented as clinical output.

**Fix.** Load `model_checkpoints/cbm_3class.pt` (path from env, fail closed if missing), verify
`classifier.weight.shape[0]` against `num_classes`, and refuse to serve `/api/diagnose` if no
weights are present. Add a `model_version` / `weights_sha256` field to the diagnosis response.

---

#### P0-2 · Fail-open mock returns a *fake melanoma diagnosis* when the model cannot load
`server.py:894-896`, `server.py:968-985`

```python
backend = get_backend()
if backend is None:
    return _mock_diagnosis()      # → predicted_class "melanoma", triage "follow_up",
                                  #   confidence_caveat None, fitzpatrick 4 (ignored)
```
**Verified.** With torch absent, `POST /api/diagnose` returned `200` with
`{"predicted_class": "melanoma", "triage": "follow_up", "fitzpatrick": 4, "confidence_caveat": null}`
for two different inputs, including `fitzpatrick=99` (out of range, because the range check sits
*after* the mock branch at `server.py:898`).

The same pattern is used for analytics (`_mock_analytics`, `server.py:1028`) and history
(`_mock_history`, `server.py:1054`).

**Impact.** The single most dangerous failure mode in medical software: a degraded system returning
a clinically actionable answer that cannot be distinguished from a real one. A clinician seeing
"melanoma / follow-up" has no way to know the model did not run. Note the mock `override_rate` of
`0.12` — the same 12% that appears on the poster.

**Fix.** Return `503` with `{"error": "model_unavailable"}`. If a demo mode is genuinely wanted, put
it behind an explicit `DEMO_MODE=1` env flag and stamp every response with
`"simulated": true` plus a visible banner in the UI.

---

#### P0-3 · Missing role checks → any doctor can take over the admin console
`server.py:1158, 1213, 1229, 1239, 1254, 1308, 1339`

Nine admin-only mutations depend on `require_csrf`, which only proves *"you are logged in"*
(`server.py:163-178`) — it never checks `role == "admin"`. Compare the read-only admin routes, which
correctly use `require_admin`.

**Verified** with a doctor token (`role: "doctor"`):

| Action | Result |
|---|---|
| `POST /api/admin/doctors` (create account, all permissions by default) | **200 created** |
| `PUT /api/admin/doctors/{id}/permissions` | **200** |
| `POST /api/admin/doctors/{id}/reset-password` → then log in as that user | **200 / 200** |
| `DELETE /api/admin/doctors/{id}` (deactivate a colleague) | **200** |
| `POST /api/admin/doctors/bulk` (deactivate many) | **200** |
| `POST /api/admin/sessions/{admin_token}/revoke` → admin is logged out | **200, admin then 401** |
| `GET /api/admin/doctors` (correctly protected) | 403 |
| `POST /api/admin/change-password` (correctly checks admin id) | 403 |

**Impact.** Complete administrative compromise from any doctor account, including creating a
persistent backdoor account and locking the real administrator out. Combined with P0-4 this is a
straight line to full application takeover.

**Fix.** Replace `Depends(require_csrf)` with a composed dependency
`Depends(require_admin_csrf)` on every `/api/admin/*` route. Better: define an
`AdminUser = Annotated[dict, Depends(require_admin)]` alias and apply it uniformly, then add a test
that asserts **every** route under `/api/admin` returns 403 for a doctor token (see P1-1).

---

#### P0-4 · Stored XSS → admin session theft (chained with P0-3 and the missing input validation)
`dashboard.html:2588-2603`, `dashboard.html:3519, 3564-3575`, `server.py` Pydantic models

Doctor and patient text is interpolated into `innerHTML` and into a JS string inside an inline
handler:

```js
// dashboard.html:2603
<button class="reset-btn" onclick="resetDoctorPassword('${d.id}', prompt('New password for ${d.username}:',''))">
```
```js
// dashboard.html:3519 / 3564
list.innerHTML = patients.map(p => `... ${p.name} ... ${meta} ...`)
timelineInner.innerHTML = p.visits.map(v => `... ${snippet} ...`)
```

The server performs no character or length validation on `username`, `name`, `email`, `contact`,
`history`, `desc`, `notes`, … (`server.py:255-285`, and the 5 MB note accepted in P2-6).

**Verified.** `POST /api/admin/doctors` accepted `username = "x');alert(1);//"` and
`name = "<svg onload=alert(2)>"`; `POST /api/patients` stored `<img src=x onerror=alert(1)>`
verbatim and `/api/patients` served it back unescaped. The activity log (`${a.event}`,
`dashboard.html:2832`) is a third sink, fed by user names.

**Impact.** A malicious doctor creates an account with a crafted username (allowed by P0-3); the
admin opens the doctor table and attacker JavaScript runs with the admin token in scope — session
theft without ever touching the password.

**Fix.** Escape at render time (`textContent`, or a small `esc()` helper for attribute/template
contexts) for *every* interpolation; stop using inline `onclick` with interpolated data (use
`addEventListener` + `dataset`); validate `username` to `^[a-z0-9._-]{3,32}$` server-side; add
`max_length` to all Pydantic fields; and add a CSP (P2-2).

---

#### P0-5 · The CSRF gate silently breaks every mutating action in the UI
`server.py:163-178` vs `dashboard.html:1975-1980`

The API now requires `X-CSRF-Token` on every POST/PUT/DELETE, but `dashboard.html`'s `api()` helper
only ever sets `Authorization`:

```js
if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
```

**Verified.** `POST /api/patients` with a valid Bearer token → `403 {"detail": "X-CSRF-Token header required."}`;
`grep -c "X-CSRF-Token" dashboard.html` → **0**.

So from the browser, patient create/update/delete, visits, notes, triage overrides, offline update,
tracker reset, and every admin action fail. The UI surfaces this as generic `alert('Failed …')`/toasts,
so it reads as "flaky app" rather than "security regression".

**Impact.** The primary workflow is unusable, and the failure is silent. This is a regression
introduced by the 2026-10-22 remediation (P2.5) — see §4.

**Fix (choose one, then be consistent):**
* **(a) Recommended:** auth is Bearer-in-header with no cookies, so cross-site requests cannot attach
  credentials. Drop the CSRF layer entirely and document why (`SameSite`/cookies are not used).
* **(b)** If cookies are introduced later, store `csrf_token` from the login response in memory and
  send it in `api()`; add a test asserting a mutation succeeds end-to-end through the real UI path.

---

#### P0-6 · JSON persistence loses data under concurrency and can corrupt files
`server.py:212-232, 300-309, 750-787`, `metrics_tracker.py:save/export_csv`

Read-modify-write with no lock and a non-atomic `write_text`:

```python
patients = _load_patients()      # read
patients.append(patient)         # mutate
_save_patients(patients)         # truncate + write
```

**Verified.** 20 concurrent `POST /api/patients` (all `201`) → **14** records on disk. Six were lost.
A crash mid-write leaves truncated JSON; `_load_patients` then swallows the decode error and returns
`[]`, i.e. a corrupt file silently becomes "no patients" and the next save overwrites it forever.

Related path bugs found in the same area:
* `tracker.export_csv()` writes `case_history.csv` relative to **CWD**, but `/api/export` then looks
  for it in `Path(__file__).parent` (`server.py:1099-1108`) → under `python main.py --dashboard`
  (CWD = repo root) the export silently returns JSON instead of the file the button promises.
* `FairnessTracker(persist_path="case_history.json")` and `agent_path = "agent_params.pt"` are also
  CWD-relative, while `patients.json`/`doctors.json` are module-relative. Two conventions in one app.
* Files are written `0644` (verified) and hold PHI.

**Fix.** Move persistence to SQLite (WAL) behind a thin repository layer with a single writer
task/`asyncio.Lock`; write via temp file + `os.replace`; make every path absolute and configurable
(`DATA_DIR`); `chmod 0600`; then re-point `export_csv` at the same directory.

---

#### P0-7 · First-run admin password is printed as a **hash**, so the admin can never log in
`server.py:312-325`

```python
pw_hash = _hash_password(secrets.token_urlsafe(16))
logger.warning("ADMIN BOOTSTRAP PASSWORD GENERATED - SAVE THIS PASSWORD:")
logger.warning(pw_hash)          # ← the bcrypt hash, not the password
```

**Verified.** Fresh `create_app()` with no env var produced a `$2b$12$…` string in the log; login with
`admin123` and with an arbitrary password both `401`. The intended credential is destroyed at birth
(the plaintext is never retained), so a first-time deploy has **no usable admin account**.

**Fix.**
```python
pw = os.environ["ADMIN_BOOTSTRAP_PASSWORD"]        # fail fast if unset in prod
pw = pw or secrets.token_urlsafe(16)
logger.warning("Initial admin password (shown once): %s", pw)   # log the plaintext, once
```
…or better, a one-shot CLI (`python -m server create-admin`) that prompts without echoing.

---

#### P0-8 · Default credentials are still in the repo — `seed_demo.py`
`seed_demo.py:556, 564-660, 767`

The P0.2 remediation removed `"admin123"` from `server.py`, but the documented data seeder
reintroduces it:

```python
"password": _hash_password("admin123")     # ×1
"password": _hash_password("Doctor123!")   # ×7
print("  Admin:   username = admin     / password = admin123")
```

Anyone who has read this public repository knows the credentials of a seeded instance — and
`Doctor123!` also fails the app's own 12-character policy (`_validate_password`), i.e. the seeder
creates accounts the API would reject.

**Fix.** Delete the literals; have `seed_demo.py` take passwords from env/CLI or call the same
bootstrap generator as P0-7. Add a `git grep` check for the strings in CI.

---

#### P0-9 · The published metrics are fabricated, and the live metrics are circular
`server.py:942-958`, `metrics_tracker.py:88-90, 196-206`, `poster.html:475`, `slides.html:550`

**(a) Circular ground truth at inference.** `/api/diagnose` registers
`true_label=pred_class` — the model's own prediction — into the fairness tracker:

```python
backend.tracker.register_case(CaseRecord(case_id=case_id, fitz_type=fitzpatrick,
                                         true_label=pred_class, model_triage=model_action, ...))
```
`compute_metrics()` then computes `expected = TRUE_LABEL_TO_TRIAGE[true_label]` and compares it to
`actual = model_triage` (`metrics_tracker.py:88-90`). "Accuracy" measures *self-consistency between
two heads of the same network*, not correctness. Overrides make it worse: on override, `actual`
becomes the clinician's action, so agreement with the clinician is scored as accuracy — the
clinician is treated as ground truth, and a clinician who over-triages actually *raises* the score.

**(b) Published numbers are mock constants.** `poster.html:475` says "84.3% HAM10000 Accuracy";
`slides.html:550` says "84.3% Overall Accuracy" plus "<3% Accuracy Gap" and "12% Override Rate".
Those are exactly `_mock_analytics()`:

```python
{"total_cases": 487, "overall_accuracy": 0.843, "override_rate": 0.12,
 "accuracy_gap": 0.027, "legacy_accuracy": 0.872, "target_accuracy": 0.845}
```
`override_rate 0.12` is also hard-coded in `main.py:seed_tracker` (12% of cases get a random fake
override). No experiment in this repository produces these figures.

**(c) No held-out data anywhere.** `main.py:compute_fairness_metrics` and
`notebooks/01_train_cbm.py:_fairness_report` evaluate the PPO agent on the **same** synthetic cases it
was trained on; those cases are generated by `generate_mock_cases`, which draws concept vectors
*conditioned on the true label* (`main.py:46-56`) — i.e. the label leaks into the features. There is
no test split, no validation protocol, and `fair_audit` reloads the agent and re-scores train cases.

**Impact.** If any of this reaches a thesis, paper, poster or stakeholder deck, it is a research
integrity problem, not a bug. The mitigation is entirely mechanical: stop printing mock values, and
only report numbers a script can reproduce from a frozen split.

**Fix.** (1) Delete the mock constants from `_mock_analytics`; make the endpoint return `503`.
(2) Add `ground_truth_confirmed: bool` + `ground_truth_label` to `CaseRecord`; compute
`clinical_accuracy` only over biopsy-confirmed cases and report `model_vs_clinician_agreement`
separately. (3) Create a locked 70/15/15 split with a checksum, and have every report script refuse
to run against the test split except a designated final-evaluation entry point. (4) Regenerate poster
and slides from a committed JSON artifact produced by that script.

---

### P1 — High

#### P1-1 · No tests, no CI, no lockfile
There is no `tests/` directory, no `.github/workflows`, no `pyproject.toml`/`ruff.toml`, no
`requirements.lock`, no Dockerfile. Consequences are visible: an undefined name ships in
`run_evaluation_ham.py:79` (`Subset`), a CSRF requirement that no client satisfies ships (P0-5), and
an untrained model ships (P0-1) — all three would be caught by ~20 lines of test.

Minimum viable suite:
* `test_authz_matrix` — parametrised over all routes: anonymous → 401, doctor → 403 on `/api/admin/*`,
  admin → 200. This single test would have caught P0-3.
* `test_csrf_contract` — the dashboard's `api()` helper and the server agree on headers.
* `test_persistence_concurrency` — 20 parallel creates → 20 records.
* `test_diagnose_determinism` — same image twice → identical probabilities (the P0.5 acceptance
  criterion, still unverified in-repo).
* `test_fairness_reward` / `test_compute_metrics` on hand-computed fixtures.
* `test_melanin_normalization_shapes`; `test_model_forward_shapes` (torch, CPU, tiny input).
* CI: `ruff`, `pytest`, `bandit`, `pip-audit`, and a Docker build.

#### P1-2 · Deactivated doctors can still log in
`server.py:691-712` never reads `doctor["active"]`; `DELETE /api/admin/doctors/{id}` only flips the
flag. **Verified:** deactivate → login → `200`. (Sessions of deactivated users also stay valid for 8 h.)
**Fix.** Reject in `login` (`if not doctor.get("active", True): 401`), and invalidate that user's
sessions on deactivate. Also add a per-account failed-login counter (see P1-10).

#### P1-3 · Train/serve preprocessing skew (and a docstring that describes neither)
`notebooks/01_train_cbm.py:build_transform`, `samplesEquity.py:24-53`, `ui.py:80-85`

| Phase | Pipeline |
|---|---|
| Train (`build_transform(train=True)`) | `MelaninNormalization(p=1)` + brightness/hue/JPEG/GaussNoise + **Rotate(90)** + HFlip + Resize + Normalize |
| Inference (`inference_transform`) | Resize + Normalize |

The 2026-10-22 fix correctly removed randomness from inference, but it also removed
**MelaninNormalization**, which is applied to *every* training image deterministically (LAB-L
histogram equalisation). The model is therefore trained on equalised luminance and served
non-equalised images — a systematic intensity-domain shift for precisely the Fitzpatrick IV–VI images
the project exists to serve. Separately, `samplesEquity.dark_skin_aug` itself contains **no**
`A.Normalize`, so any consumer that uses it directly (the obvious thing to do, given its name) trains
on 0–1 tensors and serves ImageNet-normalised ones. Its docstring also claims the pipeline excludes
`MelaninNormalization`, which is false for the training path.

**Fix.** Decide explicitly: either (a) apply melanin normalisation in *both* train and serve (keep it
differentiable or accept the XAI caveat and compute attributions on the pre-normalisation tensor),
or (b) make it an augmentation that is *off* at serve time **and retrain** — and then measure the
shift. In all cases: one transform factory with `train|eval` modes, used by notebook, eval scripts
and server; `dark_skin_aug` should either include `Normalize` or be renamed `dark_skin_augmentations`.

#### P1-4 · Both evaluation scripts are broken / non-reproducible
* `run_evaluation_ham.py:79` — `Subset` is not imported (ruff F821). `deterministic_val_split()` is
  dead code; docstring still describes an 80/20 split while `main()` loads `val_meta.csv`.
* `run_evaluation_ham.py:155` — `--data-dir` is parsed and then ignored (`data_root` hard-coded).
* `run_evaluation_ham.py:157` — default checkpoint is `smoke_cbm.pt`, a smoke-test artifact.
* `run_evaluation_passion.py:40-42` — `from dermatology_ai.datasetEquity import …`; the package
  directory is `dermatology-ai` (hyphen, not importable). The script raises `ModuleNotFoundError`
  on line 40 before doing anything.
* Neither script has a `--split` guard, a seed for the sampler, or writes results anywhere; both
  print to stdout only, so no result is reproducible or auditable.
* `run_evaluation_ham.py` reports a "kaposi_sarcoma" row from a HAM10000-only 2-class checkpoint
  (`num_classes` auto-detection) — the row is meaningless.

**Fix.** Rewrite as one `evaluate.py --split test --ckpt … --out results/*.json`, package the app
properly (rename to `dermatology_ai/` + `__init__.py`, or add `sys.path` like the HAM script does),
assert label/mapping consistency against the checkpoint, and emit machine-readable results the
poster/slides can consume.

#### P1-5 · The PPO/fairness claims do not hold as described
`rl_module.py:37, 57-80, 128-150, 341-356`, `docs/proposal/project_proposal.md:34-45`

1. **Environments are single-step.** `done = True` always (`rl_module.py:132`), so GAE degenerates to
   `advantage_t = r_t − V(s_t)`; γ=0.99 and λ=0.95 never influence anything. The "PPO with GAE,
   clipped surrogate, entropy bonus" claim is only the clipped surrogate + entropy part.
2. **One action is unreachable as correct.** `TRUE_LABEL_TO_TRIAGE = {0:0, 1:2, 2:2}` — both
   melanoma and Kaposi sarcoma map to *urgent*, so `follow_up` (action 1) is never the expected
   action, and the `expected_triage == 1` branch of `fairness_weighted_reward` is dead code. A
   3-action space with 2 reachable correct actions means the agent is trained to never use the middle
   recommendation, which is exactly the recommendation the UI's follow-up workflow assumes.
3. **The fairness multiplier is a labelling convention, not a learned equity mechanism.** It scales
   *penalties only* (`×2/3/4` for types IV/V/VI) on synthetic cases. The resulting "gap elimination"
   is measured on cases drawn from the same generator, which oversamples dark skin
   (`fitz_weights=[1,1,1,3,4,4]`) and conditions features on labels. There is no real image, no real
   clinician and no held-out case in the loop.
4. **Offline RL is not validated.** `OfflinePolicyOptimizer` builds one-step rollouts whose *actions
   are the clinician's* and rewards come from the same hand-written reward; then applies an on-policy
   PPO update. That is not a sound offline update (no importance correction, no behaviour policy), and
   it also permanently changes the shared optimizer's LR (`hitl_pipeline.py:151-153`).

**Fix.** Either (a) re-scope the claim to "triage policy over synthetic concept vectors" and drop the
GAE/fairness-gap language from the docs and poster, or (b) do the real thing: multi-step episodes or
an explicit contextual-bandit framing, a held-out synthetic *and* real evaluation, and an offline
method with the correct estimator (e.g. doubly-robust). Keep `follow_up` reachable by giving it
clinical meaning (e.g. melanoma-in-situ / dysplastic-naevus → follow-up) and re-derive the label map
with a dermatologist.

#### P1-6 · The permission model exists only in the UI
`DOCTOR_PERMISSIONS` (`server.py:290-294`) and the per-doctor `permissions` dict are stored, returned
at login and rendered in the admin console — but **no endpoint checks them**. A doctor with
`export_data: false` can still `GET /api/admin/patients/export` (admin-only) and
`GET /api/export` (any authenticated user); `view_history`, `view_analytics`, `run_diagnosis`,
`override_triage` are likewise unenforced. Combined with no record-level ownership rules, any
authenticated account can read the entire patient database.

#### P1-7 · PHI is plaintext, world-readable, ephemeral and mixed with fake data
* `patients.json`, `notes.json`, `doctors.json` are plain JSON, mode `0644` (verified), containing
  names, ages/DOB, phone numbers, national ID (`nin`), clinical history and free-text notes.
* `_seed_demo_patients()` (`server.py:335`, called from `create_app` at `server.py:531`) injects 4
  fabricated patients whenever the store is empty, and `seed_tracker` (`server.py:610`) injects ~500
  fabricated fairness cases **on every cold start** — into the *same* stores as real records. A
  clinician cannot tell demo from real data in the UI.
* `render.yaml` declares no disk, so on Render the service filesystem is ephemeral: every deploy,
  restart or idle spin-down silently deletes all patient data. There is no backup, no retention
  policy, and reads are not audited (only logins are logged).
* Sessions and the tracker live in process memory; a second worker/instance would silently fork the
  data.

**Fix.** For a research prototype: put `DATA_DIR` on a mounted volume, chmod 0600, add
`seed_demo.py --reset` as an explicit opt-in with a `demo: true` flag surfaced in the UI banner, and
document "no real patient data" in the deployment README. For anything beyond that: database with
encryption at rest, access log, retention job, and a DPIA/IRB record before any real image is
uploaded.

#### P1-8 · Unbounded and unvalidated input
No `max_length`/`max_items`/pattern constraints on any Pydantic model (`server.py:255-285`);
**verified** a 5 MB note stored (`notes.json` grew to 5,000,014 bytes) and served back. No pagination
on `/api/patients` (full PII dump in one response). Free-text `contact`/`nin`/`age` are stored without
format checks. `OverrideRequest.clinician_action` accepts any int, so `clinician_action=99` will later
`IndexError` in `TRIAGE_NAMES[actual]` (`ui.py:search_history`, `metrics_tracker.confusion_matrix_chart:206`).

#### P1-9 · Health check triggers full model load *and* a 2000-episode PPO training run, on the request path
`server.py:565-620`, `server.py:676-683`

`get_backend()` is lazy, unlocked, and expensive: it builds HRNet, generates 500 mock cases, and — on
a cold `agent_params.pt` miss — trains PPO for 2000 episodes inside the first request. `/api/health`
calls it. So the Render health probe can time out (container marked unhealthy) and the first user
after a deploy waits minutes. Two concurrent requests can both enter the initialiser (no lock), each
training its own agent. All handlers are `async def` but do blocking CPU/disk work, so they block the
event loop for every other request.

**Fix.** Initialise once at startup (`lifespan`), guarded by `asyncio.Lock`; make `/api/health`
`return {"status": "ok"}` without touching the backend, and add `/api/ready` that reports model
availability; move CPU-bound inference and file I/O to `run_in_threadpool` (or declare the handlers
`def`). Never train at request time — ship the artifact.

#### P1-10 · Rate limiting keys on client IP behind a proxy → one attacker can lock out everyone
`server.py:545-549`

`Limiter(key_func=get_remote_address)` (`server.py:550`) with no `X-Forwarded-For` handling. On Render, every request
arrives from the proxy, so the "5/minute" bucket is **global**. **Verified** the limiter works
(`[401×5, 429×3]`), which is exactly the problem: after five failed logins, *all* clinicians — and the
admin — get 429 for the rest of the minute. There is no per-account throttling, so a distributed
brute force is unlimited.

**Fix.** `get_remote_address` → trusted-proxy-aware key (`X-Forwarded-For` first hop, only when
`TRUST_PROXY=1`), plus a per-username counter with exponential backoff, and separate buckets for
login vs. read endpoints. Never rate-limit in a way that lets an unauthenticated caller deny service
to authenticated users.

#### P1-11 · NumPy 2 incompatibility (XAI crashes on a standard install)
`model.py:284` — `saliency.ptp()`; `ndarray.ptp` was removed in NumPy 2.0 (**verified** on
numpy 2.4.6: `AttributeError: 'numpy.ndarray' object has no attribute 'ptp'`). `requirements.txt`
does not pin numpy, so a fresh install gets 2.x and Integrated Gradients raises.
**Fix.** `np.ptp(saliency)`; pin versions (P1-12); add the XAI path to tests.

#### P1-12 · Requirements are incomplete and unpinned
Missing modules that tracked code imports: `python-docx` (`create_report.py`), `requests`+`tqdm`
(`scripts/download_passion.py`), `reportlab` (`scripts/gen_pdf.py`). `gradio>=6.0` is used only by
the legacy UI yet pulls a very large dependency tree into the production image; `torch>=2.1` alone is
~1 GB on CPU, which is the dominant Render build cost. No lockfile.

---

#### P1-13 · The poster still advertises HIPAA compliance, encryption and audit logging that do not exist
`poster.html:436-437, 555-557`

```html
<h3>HIPAA Compliant</h3>
<p>256-bit encryption, role-based access, physician auth, and full audit logging.</p>
…
HIPAA Compliant &bull; 256-bit Encrypted
```

None of those four properties is true: data is plaintext JSON on disk (P1-7), there is no
encryption in transit enforced by the app (no HSTS/TLS config in-app), role-based access is not
enforced (P0-3, P1-6), and only logins are audited — diagnosis reads/writes are not (P2-7).
The 2026-10-22 remediation removed this wording from `server.py` but the public-facing poster was
missed. This is a legal/regulatory misrepresentation, worse than a bug: it is a claim about
safeguards that a reviewer, ethics committee or partner could reasonably rely on.
(`dashboard.html` also still uses a CSS class named `hipaa-badge` for the disclaimer banner —
cosmetic, but rename it to avoid the implication.)

**Fix.** Delete the claims; replace with the honest posture: *"Research prototype. Not a medical
device. No clinical validation, no HIPAA/ISO 27001 certification, no BAA. Do not enter identifiable
patient data."* Add a CI grep for `HIPAA|compliant|256-bit` so it cannot come back.

### P2 — Medium

| # | Finding | Where | Notes / fix |
|---|---|---|---|
| P2-1 | Session hygiene: UUID4 tokens, in-process dict, 8 h fixed TTL, no logout endpoint; **the sessions UI cannot revoke anything** because the list omits tokens while `/revoke` requires the token in the URL (verified: doctor could revoke the admin's token, but the admin UI shows no button that works) | `server.py:131-178, 1324-1346` | Add `POST /api/logout`; store `jti` + hash; expose a short id, not the token; move to Redis for >1 worker |
| P2-2 | No security headers anywhere: no CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, HSTS. CDN script (`chart.js`) without SRI; 180 KB of inline JS | `server.py:create_app`, `dashboard.html:1938` | `SecurityHeadersMiddleware`; CSP with `script-src 'self' 'sha256-…'`; SRI on CDN |
| P2-3 | Upload hardening ordering: `await file.read()` loads the whole body into RAM *before* the 10 MB check; `Image.open` without `verify()`/`draft()`; no per-user quota on `/api/diagnose` | `server.py:900-925` | Stream with `UploadFile.read(MAX+1)`, check `Content-Length` first; `img.verify()` then reopen |
| P2-4 | Dead/duplicated code: duplicated password-validation block (`server.py:1170-1180`), `print("[DEBUG] create_patient called")` (`server.py:751`), 30 unused imports (ruff F401), unused `fn_rates` (`metrics_tracker.py:133`), `_mock_*` proliferation, dead `deterministic_val_split` | repo-wide | `ruff --fix` + delete; add to CI |
| P2-5 | Swallowed exceptions convert failures into fabricated data: `except Exception: metrics = _mock_analytics()` (`server.py:1022`), `.catch(() => {})` throughout the dashboard (`dashboard.html:2812, 2839, 2865, 2899`) | `server.py`, `dashboard.html:2848` | Log and surface; never fall back to fake values (see P0-2) |
| P2-6 | UI↔API contract drift: `run_diagnosis` early-returns a 12-tuple into 6 Gradio outputs (`ui.py:91` vs `ui.py:341`); `session_data` never contains `"concepts"`, so every override is recorded with a **zero concept vector** (`ui.py:149,169`); `/api/history` returns `[]` whenever the "Info" column exists and uses different field names than the dashboard's table | `ui.py`, `server.py:1043-1052` | One schema module (pydantic) shared by UI/API; contract tests |
| P2-7 | Tracker maths: `accuracy_gap` averages *absent* Fitzpatrick groups as 0.0 accuracy (inflates/unbalances the gap); `confusion_matrix_chart` indexes `cm[expected, actual]` with unchecked values; `enabled=False` override for an unknown `case_id` returns 200 (verified); `/api/reset` wipes the tracker for any user (verified) | `metrics_tracker.py:100-150, 196-206`, `server.py:990, 1112` | Mask absent groups, validate actions, 404 unknown case, restrict reset to admin + confirm |
| P2-8 | Notebook/script drift and Windows-only paths: `01_train_cbm.ipynb` uses `DermDataset(csv, img_dir, …)` while `01_train_cbm.py` uses `MultiSourceDermDataset(csv, DATA_DIR, …)` — same pipeline, two behaviours; `PROJECT_DATA_DIR = Path(r"D:\Dermatology_AI\datasets")` + `mkdir` at import (`scripts/download_datasets.py:38-39`) creates a bogus `D:\…` directory on Linux; `create_report.py:345` writes to `D:\…` | — | Make the `.py` the source of truth and regenerate the notebook, or delete the notebook; use `pathlib.Path(__file__).parents[1] / "datasets"` |
| P2-9 | `render.yaml` is not deployable as written: no `disk`, no `ALLOWED_ORIGINS`, no `ADMIN_BOOTSTRAP_PASSWORD`, `PORT` hard-coded to 10000 (Render injects its own), no `healthCheckPath`, single instance, no `--workers` | `render.yaml` | Add `disk`, `healthCheckPath: /api/health`, env vars via `sync: false`; document secrets |
| P2-10 | Documentation integrity: `README.md:20` instructs agents to read `AGENTS.md`, which **does not exist**; docs reference a non-existent `run_evaluation.py` and `deliverables/`; `docs/Project_Explained.md` has unfilled "output goes here" blocks and wrong dataset figures — it lists DDI as "12k images, 30+ classes" (the published DDI set is **656 images / 570 patients** [Stanford AIMI](https://aimi.stanford.edu/datasets/ddi-diverse-dermatology-images)); it claims HRNet-W18 "AUC ~0.95–0.97 (this work)" with no experiment behind it | `docs/**`, `README.md` | Fix the citations, delete or fill placeholders, mark "this work" rows as "not yet measured" |
| P2-11 | Missing project artefacts: no `LICENSE`, `MODEL_CARD.md`, `DATASET_CARD_*.md`, `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md` — the remediation plan's P3.5/P3.6 are unimplemented | root | Add; link from README |
| P2-12 | ~~Triage removal~~ -- **WITHDRAWN 2026-10-30.** The product owner confirmed the triage module is part of the product (API `triage*` fields, `TRUE_LABEL_TO_TRIAGE`, dashboard panel, `metrics_tracker` triage maths, poster, docs) and must not be removed anywhere. The branch name `pre-triage-removal` is historical only. | repo-wide | Closed: no change made, and none is to be made |

---

### P3 — Low / hygiene

* `_log_activity` re-reads and rewrites the whole file per event; concurrent writers lose entries.
* `@app.on_event("startup")` is deprecated in FastAPI; the cleanup task is never cancelled on shutdown.
* `ALLOWED_ORIGINS.split(",")` without `.strip()`; `allow_credentials=True` is meaningless with
  Bearer auth (and pointless with explicit origins).
* `require_auth` strips `"Bearer "` with `str.replace`, so `XBearer <tok>` or a doubled prefix is
  accepted; compare in constant time for the CSRF token (`!=` is not constant-time).
* Login does a bcrypt verify only when the identifier matches, and updates `last_login` on every
  attempt → a small username-enumeration oracle.
* `torch.load(..., weights_only=True)` everywhere ✅, but `agent.save()` is non-atomic and a partial
  file will crash `agent.load()` on next boot.
* Tokens are kept only in JS memory (good) but there is no expiry handling: after 8 h every click
  fails with a generic alert instead of redirecting to login.
* `dashboard.html`/`poster.html` load Chart.js from a CDN with no integrity hash.
* `.gitignore` lists every debug-script prefix imaginable (`_check_*`, `_smoke_test*`, …) — a sign that
  scratch files were previously committed; replace with a `scripts/dev/` convention.

---

## 4. Regression analysis — what the 2026-10-22 remediation actually did

`dermatology-ai/REMEDIATION_PROMPT.md` (dated 2026-10-22) is largely sound, and the code has clearly
been edited to follow it. Checking the acceptance criteria against the current tree:

| Item | Claimed fix present? | Actually works? |
|---|---|---|
| P0.1 CORS allow-list | Yes (`server.py:540-548`) | Yes, with the caveat that the UI is same-origin so this is belt-and-braces |
| P0.2 No hardcoded admin password | Yes in `server.py` | ❌ **No** — logs the hash (P0-7); `seed_demo.py` still ships `admin123` (P0-8) |
| P0.3 Auth on `/api/diagnose` | Yes | ✅ (verified 401 anonymous) — but the mock path bypasses validation (P0-2) |
| P0.4 Upload hardening | Yes | Mostly ✅ (magic bytes, size cap, 422 on decode); ordering issue in P2-2 |
| P0.5 Deterministic inference | Yes | ⚠️ Determinism yes, but **created train/serve skew** (P1-3) and dropped melanin normalisation the model was trained with |
| P1.1 Eval leakage | Attempted | ❌ Script cannot run (`Subset` undefined; PASSION script import error) (P1-4) |
| P1.2 KS caveat | Yes | ⚠️ Returned by the API but **never rendered** by the dashboard — invisible to clinicians |
| P1.3 PASSION BCC/SCC | Yes (excluded, logged) | ✅ in the download script; PASSION is not in the training path yet |
| P2.1 Password policy | Yes | ✅ at create/reset; not enforced for bootstrap or `seed_demo` |
| P2.3 Session cleanup | Yes | ✅ (deprecated hook) |
| P2.5 CSRF | Yes | ❌ **Broke the entire UI** — no client sends the header (P0-5) |
| P2.6 Unified auth | Not done | — |
| P2.7 Audit logging for diagnoses | Not done | — (logins only) |
| P2.8 PII at rest | Not done | — (P1-7) |
| P2.9 Held-out test set | Not done | — (P0-9c) |
| P2.10 Conditional dark-skin aug | Not done | `MelaninNormalization()` is still applied to all training rows |
| P2.11 Circular fairness eval | Not done — **made worse**: inference now writes the model's own prediction as `true_label` | (P0-9a) |
| P2.12 Demographic parity / equalized odds | Not done | — |
| P3.1–3.8 Tests, CI, cards, lockfile, containers | Not done | — |
| P4.1 Remove HIPAA claim | Partial | ⚠️ removed from `server.py`; **still advertised on `poster.html`** (P1-13) |
| P4.2 Expose `/docs` | Yes | ✅ (verified 200) |

**Lesson for the next pass:** three of the applied fixes are *partial in a way that hides failure*
(password printed as hash, CSRF enforced on a client that never sends it, eval script that cannot
import) and one introduced a modelling defect (P1-3). The remediation should have been driven by
tests, and the acceptance criteria in the prompt are behavioural — they just were not executed.

---

## 5. What is genuinely good (keep this)

* **Concept-bottleneck design** (`model.py`) is clean and readable: HRNet `features_only` →
  `AdaptiveAvgPool` → concept MLP → **linear** classifier. A linear head on concepts is what makes the
  "intervention" story defensible; don't let anyone replace it with an MLP without a reason.
* **Grad-CAM hook strategy** is correct and well explained — hooking the backbone *output* rather than
  a Conv2d (HRNet's parallel branches make the usual choice unreliable), with handle cleanup to avoid
  a leak. This is better than most research code.
* **Docstrings** in `model.py`, `rl_module.py` and `hitl_pipeline.py` are genuinely useful: shapes,
  units, and rationale.
* **Upload hardening**: magic-byte validation, 10 MB cap, `Image.MAX_IMAGE_PIXELS`, 422 on decode
  failure — exactly right in principle.
* **`weights_only=True`** on every `torch.load` in the tree.
* **Disclaimers** are present and consistent in README, `main.tex`, `dashboard.html` (both as HTML
  comment and as a visible banner at line 1007) and `poster.html`; the misleading HIPAA wording is gone
  from the API (but the poster still claims it — see P1-13).
* **No secrets committed** in `server.py` or config (the demo passwords in `seed_demo.py` are the one
  exception).
* **Auth is Bearer-in-header with no cookies** — the right call for an SPA, and the reason the CSRF
  layer should simply be removed.
* **Repo hygiene** is mostly good: `.gitignore` covers generated data and PHI files, no large binaries
  committed, dataset download scripts are documented with licences and access requirements.

---

## 6. Recommended order of work

**Sprint 0 — stop the bleeding (≈1 day).**
1. Load real weights, fail closed (P0-1, P0-2). If there is no checkpoint yet, make `/api/diagnose`
   return 503 and label the UI "model not trained" — do not ship a random-head demo to clinicians.
2. Add `require_admin` to all `/api/admin/*` mutations (P0-3) + the authz matrix test (P1-1).
3. Fix the admin bootstrap log (P0-7) and strip `seed_demo.py` credentials (P0-8).
4. Make the CSRF decision and reconcile client/server (P0-5).
5. Escape all render sinks + validate `username` (P0-4).
6. Delete `_mock_analytics` / `_mock_history` constants and fix the poster/slides numbers or mark them
   as placeholders (P0-9b).

**Sprint 1 — make it hold together (≈3–4 days).**
7. SQLite + single-writer + atomic writes + `DATA_DIR` + chmod 0600 (P0-6, P1-7).
8. Startup `lifespan` init with a lock, fast `/api/health`, `run_in_threadpool` for inference (P1-9).
9. Input limits, action validation, pagination, permission enforcement (P1-6, P1-8).
10. Fix eval scripts + a locked split + `results/*.json` (P1-4, P0-9c).
11. Rate-limit rework + per-account throttle (P1-10); login `active` check (P1-2).

**Sprint 2 — make it trustworthy (≈1–2 weeks).**
12. One transform factory, retrain, measure the melanin-normalisation effect (P1-3).
13. Re-scope or redo the PPO/fairness study; separate `clinical_accuracy` from
    `model_vs_clinician_agreement`; demographic parity + equalized odds (P1-5, P2-7).
14. Security headers, CSP, session rework with logout, `audit` log for diagnoses and reads (P2-1, P2-2).
15. Docker + CI + ruff/mypy/pytest/bandit/pip-audit; pin dependencies (P1-1, P1-12, P2-9).
16. Model card, dataset cards, licence, docs cleanup (P2-10, P2-11).

**Gating question before any clinical data:** is this going to hold real patients? If yes, P1-7
(encryption, audit, retention, backup) and an IRB/ethics record are prerequisites, not backlog items.

---

## Appendix A — Endpoint authorization matrix (as implemented)

| Endpoint | Anonymous | Doctor | Admin | Correct? |
|---|---|---|---|---|
| `GET /`, `/docs`, `/robots.txt`, `/sitemap.xml`, images | 200 | 200 | 200 | ✅ public assets |
| `GET /api/health` | 200 | 200 | 200 | ⚠️ triggers backend init |
| `POST /api/login`, `/api/admin/login` | 200/401 (5/min) | — | — | ✅ |
| `GET /api/patients`, `/api/patients/{id}`, `/visits`, `/notes/{id}` | 401 | 200 | 200 | ⚠️ no permission check |
| `POST/PUT/DELETE /api/patients*`, `/visits`, `/notes`, `/override` | 401 | 403 (CSRF) | 200 | ❌ UI never sends CSRF |
| `POST /api/diagnose` | 401 | 200 | 200 | ⚠️ mock path returns a fake diagnosis |
| `GET /api/analytics`, `/api/history`, `/api/export` | 401 | 200 | 200 | ⚠️ all-PHI export for any user |
| `POST /api/reset`, `/api/offline-update` | 401 | 403 (CSRF) | 200 | ⚠️ no admin gate; any user wipe once CSRF fixed |
| `GET /api/admin/{doctors,sessions,activity,permissions,patients/export,analytics-data}` | 401 | 403 | 200 | ✅ |
| `POST/PUT/DELETE /api/admin/doctors*`, `/permissions`, `/sessions/{tok}/revoke`, `/bulk` | 401 | **200** ❌ | 200 | ❌ **P0-3** |
| `POST /api/admin/change-password` | 401 | 403 | 200 | ✅ (checks admin record) |
| `PUT /api/doctors/me` | 401 | 200 | 200 | ⚠️ mutation without CSRF |

## Appendix B — Reproduction log

Environment: Python 3.11.2; `fastapi`, `starlette`, `bcrypt`, `slowapi`, `filetype`, `pandas`,
`numpy 2.4.6`, `Pillow`; no torch (so the server ran in "API-only mode", which is itself finding P0-2).
Working copy: `/tmp/probe` (a copy of `dermatology-ai/`); the repository was not modified.

```
PROBE 1  bootstrap password handling
  admin record stored: {'id': 'admin-001', 'username': 'admin', 'password': '$2b$12$jbt4xsJ4…'}
  login with admin123 -> 401      login with unknown pw -> 401

PROBE 2  unauthenticated access
  GET /api/patients /api/analytics /api/history /api/export /api/admin/doctors /api/notes/X -> 401 (all)
  POST /api/diagnose (no file) -> 401        GET /docs -> 200

PROBE 3  privilege escalation (doctor-role token, role="doctor")
  doctor creates a new doctor account            -> 200 created
  doctor edits permissions                       -> 200
  doctor resets another account's password       -> 200
     … and logs in as that account               -> 200
  doctor deactivates another doctor              -> 200
  doctor bulk-deactivates doctors                -> 200
  doctor reads admin list (require_admin)        -> 403
  doctor attempts admin password change          -> 403
  login after deactivation                       -> 200        (P1-2)
  non-admin revokes the ADMIN session            -> 200 → admin now 401  (P0-3)

PROBE 4  CSRF contract
  POST /api/patients with Bearer only            -> 403 {'detail': 'X-CSRF-Token header required.'}
  POST /api/patients with CSRF header            -> 201
  dashboard.html sends X-CSRF-Token?               False

PROBE 5  mock diagnosis
  fitzpatrick=6   -> 200 {'predicted_class': 'melanoma', 'fitzpatrick': 4, 'confidence_caveat': None}
  fitzpatrick=99  -> 200 {'predicted_class': 'melanoma', 'fitzpatrick': 4}   (no validation)

PROBE 6  persistence
  20 concurrent POST /api/patients -> statuses {201}; records on disk: +14 of +20   (P0-6)
  patients.json mode 644

PROBE 7  input limits / XSS
  POST /api/override for unknown case            -> 200 {'status': 'recorded'}
  POST /api/reset as non-admin                   -> 200
  POST /api/notes with 5,000,000 chars           -> 200, notes.json = 5,000,014 bytes
  patient name '<img src=x onerror=alert(1)>'    -> 201, served back verbatim
  doctor username "x');alert(1);//"              -> 200 accepted
  admin creates doctor name "<svg onload=alert(2)>" -> 200 accepted

PROBE 8  rate limiting
  8 rapid admin logins -> [401, 401, 401, 401, 401, 429, 429, 429]   (limit works; global bucket)

STATIC
  ruff --select F,E9,B  -> 77 findings (incl. F821 undefined `Subset` in run_evaluation_ham.py:79)
  numpy 2.4.6: np.array([1,2]).ptp() -> AttributeError   (model.py:284)
  grep -n "load_state_dict|ckpt|checkpoint" server.py main.py ui.py -> no CBM checkpoint load
  grep -c "X-CSRF-Token" dashboard.html -> 0
```

## Appendix C — Not reviewed

Binary assets (`.jpg`/`.webp`/`.pdf`/`.docx`), the visual design of `poster.html`/`slides.html`
(only their text and inline JS were read), the contents of `docs/reports/project_update_report.docx`,
and the licensing terms of HAM10000 / PASSION / ISIC (the code's own notes are consistent with public
non-commercial research licences, but no licence file is present in the repo). Torch-dependent runtime
behaviour (model forward, PPO training, Grad-CAM) was reviewed statically, not executed.
