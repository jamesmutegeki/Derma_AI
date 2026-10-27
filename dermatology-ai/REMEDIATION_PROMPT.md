# Remediation Prompt — Dermatology AI Codebase

> **Repository:** `Derma_AI` — https://github.com/jamesmutegeki/Derma_AI  
> **Branch / Commit:** `pre-triage-removal` @ `4ce2060e`  
> **Source:** Code review dated 2026-10-22  
> **Purpose:** Systematically remediate security, privacy, and ML-integrity defects found in review.

---

## Table of Contents

- [Context](#context)
- [Instructions for the Agent](#instructions-for-the-agent)
- [Phase P0 — Security Blockers](#phase-p0--security-blockers)
- [Phase P1 — ML Validity & Code-Execution Risks](#phase-p1--ml-validity--code-execution-risks)
- [Phase P2 — Important Hardening](#phase-p2--important-hardening)
- [Phase P3 — Reproducibility, Testing, Documentation](#phase-p3--reproducibility-testing-documentation)
- [Phase P4 — Quick Documentation / Compliance Fixes](#phase-p4--quick-documentation--compliance-fixes)
- [Acceptance Criteria](#acceptance-criteria)
- [Breaking-Change Register](#breaking-change-register)
- [Effort Summary](#effort-summary)

---

## Context

`dermatology-ai` is a research prototype for AI-assisted dermatology triage:

| Component | File | Role |
|---|---|---|
| Concept Bottleneck Model | `model.py` | HRNet-W18 → 7 concepts → 3-class head (benign / melanoma / Kaposi sarcoma) |
| RL triage agent | `rl_module.py` | PPO with Fitzpatrick-weighted fairness rewards |
| Human-in-the-loop loop | `hitl_pipeline.py` | Clinician override → correction buffer → offline PPO update |
| Fairness metrics | `metrics_tracker.py` | Per-skin-type accuracy / FN rate |
| Data loading | `datasetEquity.py`, `samplesEquity.py` | Multi-source loader + augmentations |
| Web API | `server.py` | FastAPI + Gradio + HTML dashboard, JSON file persistence |

The system is **research/educational only — not a medical device, not for clinical use.**

---

## Instructions for the Agent

You are remediating the issues listed below. Work **in priority order (P0 → P4)**.

For every fix:

1. Make the **minimal, targeted change** required — do not refactor unrelated code.
2. Preserve existing function signatures and API contracts unless the fix *requires* a breaking change (if so, log it in the [Breaking-Change Register](#breaking-change-register)).
3. Add or update tests where noted.
4. Add a one-line comment above each changed block: `# SECURITY FIX: <reason>` or `# ML FIX: <reason>`.
5. After each phase, run `dermatology-ai/scripts/tests/_run_tests.py` and report pass/fail.
6. **Never remove** the "research/educational only, not a medical device" disclaimers from README, HTML meta tags, or LaTeX sources.
7. Do not introduce new dependencies without noting them in `requirements.txt` / lockfile.

---

## Phase P0 — Security Blockers

> **Goal:** nothing in this phase may remain unfixed before any deployment, even internal.  
> **Estimated effort:** ~2 hours total.

### P0.1 — Fix CORS misconfiguration

- **File:** `dermatology-ai/server.py:454-460`
- **Problem:** `allow_origins=["*"]` combined with `allow_credentials=True` violates the CORS spec and enables cross-site authenticated requests (CSRF).
- **Fix:**
  - Read an explicit allow-list from env var `ALLOWED_ORIGINS` (comma-separated).
  - Default to `["http://localhost:7860"]` in dev.
  - Keep `allow_credentials=True` **only** with explicit origins — never with `*`.
  - Restrict `allow_methods` to `["GET", "POST", "PUT", "DELETE"]`.
  - Restrict `allow_headers` to `["Authorization", "Content-Type"]`.

### P0.2 — Remove hardcoded admin password

- **File:** `dermatology-ai/server.py:243`
- **Problem:** `"password": _hash_password("admin123")` ships a known default credential in source control.
- **Fix:** Remove the literal. On first run with no admin present, either:
  - **(a)** Generate `secrets.token_urlsafe(16)`, hash and store it, and print it **once** to stdout with a prominent `SAVE THIS PASSWORD` warning; **or**
  - **(b)** Require `ADMIN_BOOTSTRAP_PASSWORD` from the environment and fail startup in production mode if unset.

### P0.3 — Require authentication on `/api/diagnose`

- **File:** `dermatology-ai/server.py:784-843`
- **Problem:** The model inference endpoint is fully public — enables resource exhaustion, model behaviour extraction, and malicious uploads.
- **Fix:** Add `user=Depends(require_auth)` to the endpoint signature.
- **If a public demo is required:** create a separate `/api/demo/diagnose` route with strict per-IP rate limiting (see [P2.1](#p21--rate-limit-auth-endpoints)) and a watermark/disclaimer in the response payload. Do **not** leave the authenticated-grade endpoint open.

### P0.4 — Harden file upload validation

- **File:** `dermatology-ai/server.py:784-806`
- **Problems:** client-controlled `content_type`, no size cap, no magic-byte check, PIL decompression-bomb exposure.
- **Fix:**
  - Set `Image.MAX_IMAGE_PIXELS = 10_000_000` at module load.
  - Reject uploads where `len(contents)` exceeds ~10 MB with HTTP `413`, **before** passing to PIL.
  - Validate real file content with magic bytes (`filetype` or `python-magic`) rather than trusting `file.content_type`.
  - Wrap `Image.open()` in `try/except` and return HTTP `422` on decode failure instead of letting exceptions propagate.

### P0.5 — Fix non-deterministic inference preprocessing

- **Files:** `dermatology-ai/samplesEquity.py`, `dermatology-ai/ui.py`, `dermatology-ai/server.py:805-806`
- **Problem:** Inference reuses the training transform, which applies random augmentations (`A.Rotate(limit=90)`, `A.HorizontalFlip()`, `A.GaussNoise()`), making predictions non-reproducible.
- **Fix:**
  - In `samplesEquity.py`, add a dedicated `inference_transform`:
    - `A.Resize(224, 224)` → `A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)` → `ToTensorV2()`
    - No rotation, flip, noise, or random `MelaninNormalization`.
  - Update `ui.py` `preprocess()` (or add `preprocess_for_inference()`) to use it.
  - Point `server.py:805-806` at the inference path.
  - Verify: two diagnoses of the same image must return identical probabilities.

---

## Phase P1 — ML Validity & Code-Execution Risks

> **Goal:** make reported metrics trustworthy and eliminate deserialisation RCE.  
> **Estimated effort:** ~3 hours total.

### P1.1 — Fix evaluation data leakage

- **File:** `run_evaluation_ham.py:114-115`
- **Problem:** Evaluation builds its own 80/20 split over the **full** HAM10000 metadata, while training used an 85/15 split written to `train_meta.csv` / `val_meta.csv`. The eval "validation" set overlaps the training set.
- **Fix:** Load the committed validation split directly:
  ```python
  val_ds = DermDataset(str(VAL_META), str(HAM_DIR), transform=build_transform(train=False))
  ```
  Ensure `VAL_META` matches the path written by `dermatology-ai/notebooks/01_train_cbm.py`. Re-run evaluation and explicitly flag all previously reported metrics as invalid.

### P1.2 — Fix HAM10000 class-mapping issues

- **File:** `dermatology-ai/notebooks/01_train_cbm.py:62-64, 89-90`
- **Problems:**
  - HAM10000's 7 diagnoses (`mel`, `nv`, `bkl`, `bcc`, `akiec`, `vasc`, `df`) are collapsed to binary, conflating BCC/AK with nevi under "benign".
  - The `kaposi_sarcoma` class has **zero** real samples — only synthetic data.
  - `FITZ_PLACEHOLDER_HAM = 3` assigns a neutral skin type to every HAM10000 row, skewing fairness metrics.
- **Fix — choose one and document it:**
  - **(a)** Keep binary training on HAM10000. Document the collapse in code comments and `DATASET_CARD_HAM10000.md`. Gate Kaposi sarcoma outputs: add a `confidence_caveat` field to the API response when `predicted_class == "kaposi_sarcoma"`, stating the class is synthetic-data-only and unvalidated on real images.
  - **(b)** Switch primary training to ISIC 2019/2020, which provide real multi-class labels and genuine Fitzpatrick metadata.
- Either way, document the Fitzpatrick placeholder and its effect on fairness reporting.

### P1.3 — Fix PASSION dataset mislabeling

- **File:** `dermatology-ai/scripts/download_passion.py:47-64`
- **Problem:** `basal_cell_carcinoma` and `squamous_cell_carcinoma` — both malignant — are mapped to `"benign"`, corrupting ground truth.
- **Fix — choose one:**
  - **Exclude** BCC/SCC samples from the processed dataset, logging the filtered count; **or**
  - **Add** them as a fourth class — requires updating `LABEL_TO_INT`, the model output head size, and all downstream label-dependent code. **This is a breaking change requiring retraining** — log it in the register.
- Record the final decision in `DATASET_CARD_PASSION.md`.

### P1.4 — Make melanin normalization XAI-safe

- **File:** `dermatology-ai/samplesEquity.py:13-18`
- **Problem:** `MelaninNormalization` uses `cv2.equalizeHist`, a non-differentiable LUT operation. Grad-CAM and Integrated Gradients therefore produce incorrect or misleading attributions.
- **Fix:**
  - Move melanin normalization **out** of any graph path requiring `requires_grad=True`.
  - Apply it strictly as a raw-image preprocessing step **before** `ToTensorV2()`.
  - Update the XAI endpoints in `server.py` to state that explanations reflect the **post-normalization** image, not the raw upload.
  - *(Optional, higher effort)* Implement a differentiable histogram-equalisation in PyTorch if in-graph normalization is genuinely required.

### P1.5 — Secure checkpoint loading

- **File:** `dermatology-ai/server.py:120-121`
- **Problem:** `torch.load()` without `weights_only=True` allows arbitrary code execution from a malicious `.pt` file.
- **Fix:**
  ```python
  state = torch.load(args.ckpt, map_location=device, weights_only=True)
  ```
  Audit **every** `torch.load(...)` call in the repository — training scripts, `rl_module.py`, evaluation scripts — and apply the same change.

---

## Phase P2 — Important Hardening

> **Estimated effort:** ~5 hours total.

### P2.1 — Rate-limit auth endpoints
- **Files:** `server.py:590-624` (login), `server.py:1005-1019` (admin login)
- Add `slowapi` (or equivalent): **5 requests/min per IP** on `/api/login` and `/api/admin/login`.

### P2.2 — Enforce a password policy
- **File:** `server.py:44-45`
- Minimum 12 characters; reject common passwords via `zxcvbn` or a blocklist, at registration and password-change time.

### P2.3 — Clean up sessions automatically
- **File:** `server.py:1176-1189`
- Expired sessions are currently purged **only** when an admin hits `/api/admin/sessions`, so `_sessions` grows unbounded.
- Add a startup background task (`asyncio.create_task`) purging expired tokens every N minutes. For multi-process deployment, migrate to Redis with native TTL.

### P2.4 — Sanitize free-text input
- **File:** `server.py:178-200` (`PatientRequest`, `VisitRequest`)
- Add length limits and character validation to the Pydantic models.
- Verify `dashboard.html` escapes all user-supplied text — no unescaped `innerHTML` or template interpolation.

### P2.5 — Add CSRF protection
- For any cookie-based session flow, add CSRF tokens to all state-changing `POST` / `PUT` / `DELETE` endpoints.

### P2.6 — Unify the auth mechanism
- **File:** `server.py:93-96`
- `require_auth` reads only the `Authorization: Bearer` header, but the frontend may send cookies.
- Pick one mechanism — or support both consistently — and document the choice in the README.

### P2.7 — Add audit logging for diagnoses
- **File:** `server.py:784-843`
- Append `case_id`, `fitzpatrick`, `user_id`, and timestamp to an append-only audit log for every diagnosis request. **Never log the raw image.**

### P2.8 — Encrypt PII at rest
- **Files:** `patients.json`, `doctors.json`, `case_history.json`, `notes.json`
- Encrypt with `cryptography.fernet` using a key from an environment variable, or migrate to SQLite + SQLCipher.
- At minimum, set file permissions to `0600`.

### P2.9 — Create a true held-out test set
- No test split currently exists; reported "test" numbers are validation numbers.
- Re-split all datasets **70/15/15** (train/val/test) at project root with a fixed seed.
- Lock the test split and do not touch it until final reporting.
- Update every training and evaluation script to reference the three fixed files.

### P2.10 — Apply dark-skin augmentation conditionally
- **File:** `samplesEquity.py:24-36`
- `dark_skin_aug` is currently applied to **all** training samples, including light-skin HAM10000 images, risking degraded Fitzpatrick I–III performance.
- Apply it only when `fitzpatrick >= 4`; use a standard augmentation pipeline otherwise.

### P2.11 — Fix circular fairness evaluation
- **File:** `metrics_tracker.py:88-90`
- `actual = r.clinician_triage if r.is_override else r.model_triage` treats the clinician as ground truth, inflating accuracy.
- Add `ground_truth_confirmed: bool` and `ground_truth_label` to the case record schema.
- Report two distinct metrics: `clinical_accuracy` (vs. biopsy-confirmed truth) and `model_vs_clinician_agreement`.

### P2.12 — Implement real fairness metrics
- **File:** `metrics_tracker.py:150-151`
- Docs claim demographic parity and equalized odds, but only per-type accuracy and FN rate are computed.
- Implement:
  - **Demographic parity:** `P(triage = urgent | fitzpatrick = f)`
  - **Equalized odds:** `P(triage = urgent | y = melanoma, fitzpatrick = f)`
- Expose both via the metrics API and dashboard.

---

## Phase P3 — Reproducibility, Testing, Documentation

> **Estimated effort:** ~10 hours total.

### P3.1 — Add unit tests
Create `dermatology-ai/tests/unit/` covering:
- `fairness_weighted_reward` (`rl_module.py`)
- `compute_metrics` and the new fairness functions (`metrics_tracker.py`)
- `MelaninNormalization.apply()`
- Model forward/backward output shapes
- PPO GAE and loss computation
- `DermDataset` edge cases: missing images, malformed CSV rows

### P3.2 — Validate dataset schemas
- **File:** `datasetEquity.py:19-31`
- Add schema validation (e.g. `pandera`) with clear, actionable error messages instead of bare `KeyError` / `FileNotFoundError`.

### P3.3 — Add adversarial / OOD robustness tests
Assert clean `4xx` responses (not crashes) for: random noise images, non-medical images, invalid or extreme Fitzpatrick values, truncated and corrupted files.

### P3.4 — Add experiment tracking
Integrate `wandb` or `mlflow` into all training scripts. Log hyperparameters, all seeds (including DataLoader worker seeds), git commit hash, and dataset version/checksum.

### P3.5 — Write dataset cards
Create `DATASET_CARD.md` for HAM10000, the synthetic dataset, PASSION, and ISIC. Each must cover: source, size, class distribution, Fitzpatrick distribution, licence, known biases, and preprocessing applied.

### P3.6 — Write a model card
Create `MODEL_CARD.md`: intended use, limitations (especially the Kaposi sarcoma real-data gap), performance broken down by Fitzpatrick type, and explicit out-of-scope uses.

### P3.7 — Add containerization and CI
- Multi-stage `Dockerfile` with a non-root user and a healthcheck endpoint.
- `.github/workflows/ci.yml` running `ruff` / `black` / `mypy`, `pytest`, Docker build, and `bandit` + `pip-audit` security scans.

### P3.8 — Pin dependencies
Generate `requirements.lock` via `pip-tools`, or migrate to `poetry.lock`.

### P3.9 — Bundle pretrained weights
- **File:** `model.py:45-50`
- `timm.create_model(..., pretrained=True)` fetches from HF Hub at runtime and fails in air-gapped or rate-limited environments.
- Bundle weights locally or provide a documented cache/fallback path.

### P3.10 — Remove the committed binary
- **File:** `Dermatology_AI/wkhtmltox_0.12.6-1.focal_amd64.deb` (~15 MB)
- Remove from git history; install via the Dockerfile's package manager instead.

---

## Phase P4 — Quick Documentation / Compliance Fixes

> **Estimated effort:** ~1 hour total.

### P4.1 — Remove the misleading HIPAA claim
- **File:** `server.py:623`
- Current: `"Authentication successful. HIPAA-compliant session established."`
- Replace with: `"Authentication successful."`
- Add to README: *"HIPAA readiness has not been validated. This system has no BAA, no encryption-at-rest guarantee, and no compliance certification."*

### P4.2 — Expose API documentation
Enable and document FastAPI's auto-generated `/docs` and `/redoc` endpoints in the README.

### P4.3 — Document the PASSION class decision
Record in code comments and `DATASET_CARD_PASSION.md` exactly how and why BCC/SCC were handled (per [P1.3](#p13--fix-passion-dataset-mislabeling)).

---

## Acceptance Criteria

Verify before closing each phase.

### P0
- [ ] Fresh `git clone` + fresh server start contains **no** default credentials.
- [ ] CORS test confirms requests from unlisted origins are rejected.
- [ ] Oversized, malformed, and spoofed-content-type uploads are rejected with correct status codes.
- [ ] `/api/diagnose` returns `401` for unauthenticated requests.
- [ ] Diagnosing the same image twice yields **identical** predicted probabilities.

### P1
- [ ] `run_evaluation_ham.py` evaluates on `val_meta.csv` only, with a printed assertion of **zero** row overlap with `train_meta.csv`.
- [ ] No malignant diagnosis (BCC, SCC) is mapped to `"benign"` anywhere in the active training pipeline.
- [ ] Every `torch.load` call in the repo uses `weights_only=True`.
- [ ] XAI output documentation states the normalization caveat.

### P2
- [ ] Auth endpoints reject the 6th login attempt within one minute from a single IP.
- [ ] `_sessions` shrinks automatically after TTL expiry without admin intervention.
- [ ] Data files are encrypted at rest or chmod `0600`.
- [ ] A locked 70/15/15 split exists and is referenced by all scripts.
- [ ] Demographic parity and equalized odds appear in the metrics output.

### P3
- [ ] `pytest dermatology-ai/tests/` passes, including all new unit tests.
- [ ] `bandit -r dermatology-ai/` and `pip-audit` report no high-severity findings.
- [ ] `MODEL_CARD.md` and all dataset cards exist and are linked from the main README.
- [ ] CI pipeline runs green on push.

### P4
- [ ] README and in-app messaging no longer claim HIPAA compliance.
- [ ] `/docs` is reachable and documented.

---

## Breaking-Change Register

Log every change here that requires model retraining or breaks an API contract. **Do not ship breaking changes silently.**

| # | Change | Trigger | Impact | Retrain Required? | Status |
|---|---|---|---|---|---|
| 1 | Add BCC/SCC as a 4th class | P1.3 option (b) | `LABEL_TO_INT`, model head size, all downstream label logic | ✅ Yes | ☐ |
| 2 | Remove public access to `/api/diagnose` | P0.3 | Any existing unauthenticated client breaks | ❌ No | ☐ |
| 3 | Switch training source to ISIC | P1.2 option (b) | New data pipeline, new metrics baseline | ✅ Yes | ☐ |
| 4 | Re-split datasets 70/15/15 | P2.9 | All previously reported metrics invalidated | ✅ Yes | ☐ |
| 5 | Add `ground_truth_confirmed` to case schema | P2.11 | Existing `case_history.json` records need migration | ❌ No | ☐ |

---

## Effort Summary

| Phase | Theme | Est. Effort | Blocking? |
|---|---|---|---|
| **P0** | Security blockers | ~2 hrs | Blocks **any** deployment |
| **P1** | ML validity & RCE risk | ~3 hrs | Blocks publishing any metrics |
| **P2** | Hardening & fairness rigour | ~5 hrs | Blocks pilot / multi-user use |
| **P3** | Testing, reproducibility, docs | ~10 hrs | Blocks external review |
| **P4** | Documentation & compliance language | ~1 hr | Blocks public release |
| | **Total** | **~21 hrs** | |

---

## Out of Scope / Needs Further Review

These areas were not fully examined in the original review and may contain additional issues:

1. `ui.py` (Gradio frontend) — possible XSS/CSRF surface
2. `dashboard.html` / `poster.html` — CSP headers, inline scripts
3. GPU training paths — all scripts currently hardcode `DEVICE = torch.device("cpu")`
4. PASSION download script — placeholder URL, integration untested
5. `render.yaml` — env var handling and secret management on Render
6. Clinical/regulatory documentation — no IRB or ethics approval found

---

*Reminder: this remains a pre-clinical research prototype. Completing every item above improves engineering quality and research integrity, but does **not** constitute clinical validation, regulatory clearance, or HIPAA compliance.*