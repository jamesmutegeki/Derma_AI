# Remediation status

Living record of the review remediation (`CODE_REVIEW.md`, baseline `13a299a`).
An item is only marked **done** when its named acceptance test passes from a
clean checkout.

Run the gate:

```bash
cd dermatology-ai
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # 139 passed
bash scripts/ci_grep.sh      # OK: no fabricated claims, no default credentials, no mock payloads
```

---

## Sprint 0 -- security, honesty, testability

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S0-1** | Every non-public route requires authentication; sessions are revocable | `tests/test_s0_1_auth_required.py::test_every_non_public_route_rejects_anonymous`, `::test_logout_revokes_the_token`, `::test_deactivated_doctor_session_is_killed` | done |
| **S0-2** | One shared authorization dependency set, enforced server-side, route-enumerated | `tests/test_s0_2_authz_matrix.py::test_authz_matrix`, `::test_permission_flags_are_enforced`, `::test_destructive_routes_are_admin_only` | done |
| **S0-3** | Password policy, no shipped defaults, safe bootstrap, login throttling | `tests/test_s0_3_password_policy.py` (7 tests) | done |
| **S0-4** | Dashboard XSS closed; strict CSP with no inline script | `tests/test_s0_4_dashboard_xss.py` (7 tests) | done |
| **S0-5** | Metrics computed from confirmed ground truth only | `tests/test_s0_5_metrics_honesty.py` (6 tests) | done |
| **S0-6** | No fail-open / fake clinical output; demo data labelled | `tests/test_s0_6_no_fake_data.py` (7 tests) | done |
| **S0-7** | Single train/serve preprocessing pipeline | `tests/test_s0_7_transform_parity.py` (8 tests) | done |

Supporting artefacts: `SECURITY.md` (including the Bearer/no-CSRF rationale and a
draft retention/backup policy), `scripts/ci_grep.sh`, pinned
`requirements.txt` / `requirements-dev.txt`.

### What changed, by review finding

| Review item | Resolution |
| --- | --- |
| P0-1 no checkpoint loaded | `backend.Backend` loads `MODEL_CHECKPOINT_PATH`, hashes the weights, and reports the reason when it cannot; `/api/diagnose` is 503 without it |
| P0-2 fail-open mock diagnosis | mock path deleted; `tests/test_s0_6...::test_diagnose_without_checkpoint_returns_503` |
| P0-3 admin routes CSRF-only | `require_admin` on all `/api/admin/*`, `/api/reset`, `/api/offline-update` |
| P0-4 stored XSS | `esc()`/`safeImageUrl()`/`textContent`, delegated event handlers, JS extracted to `dashboard.js` |
| P0-5 CSRF gate broke every write | CSRF removed deliberately; rationale in `server.py` and `SECURITY.md` §2 |
| P0-6 JSON persistence lost writes | SQLite with WAL, `BEGIN IMMEDIATE`, `0700`/`0600` |
| P0-7 bootstrap logged bcrypt hash | generated compliant password written to a `0600` file, only the path logged |
| P0-8 `admin123` / `Doctor123!` | removed everywhere; deny-list assembled at runtime; CI grep |
| P0-9 fabricated metrics | `FairnessTracker` computes from confirmed cases; no literal figures |
| P1-13 poster compliance claims | replaced with prototype/no-BAA wording; class renamed `disclaimer-badge` |
| P1 eval scripts unrunnable | `run_evaluation_ham.py` / `run_evaluation_passion.py` rewritten; `--smoke` proven in CI |
| P1 Windows-only paths | removed from `download_datasets.py`, `create_report.py`, notebook |
| P1 PHI in plaintext / in exports | de-identified CSV export, no identifiers in audit, redaction filter on logs |
| P2-3 upload ordering | streamed `read(MAX+1)`, magic bytes, `Image.verify()` then reopen |
| P2-4 dead code / unused imports | dead paths deleted with the rewrite; 19 unused imports removed (ruff F401 clean) |
| P2-7 tracker maths | empty Fitz groups masked, unknown `case_id` -> 404, `/api/reset` admin-only |
| P2-10 docs integrity | placeholders replaced with procedure, unmeasured HRNet claim removed |
| P2-11 missing artefacts | LICENSE, MODEL_CARD, 3 dataset cards, CITATION.cff, SECURITY.md, CONTRIBUTING.md |
| P3 login enumeration | bcrypt always executed, even for unknown identifiers |
| P3 non-atomic agent save | temp file + `os.replace`, previous checkpoint preserved on failure |
| P3 session expiry in UI | single `handleUnauthorized()` path returns to the login overlay |

---

## Sprint 1 -- model and data integrity

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S1-1** (gate) | Model artefact is verifiable and documented: hash-checked manifest, honest model card, no unattributable weights | `tests/test_s1_1_model_artefact.py` (11 tests) | done |
| **S1-2** | Evaluation scripts run end-to-end and record their own provenance | `tests/test_s1_2_eval_scripts.py` (6 tests) | done |
| **S1-3** | PHI stays put: no identifiers in audit, logs or exports | `tests/test_s1_3_phi_handling.py` (5 tests) | done |
| **S1-4** | Documentation is truthful: DDI corrected, no fabricated figures, README reports status | `tests/test_s1_4_docs_truthfulness.py` (7 tests) | done |
| **S1-5** | Repo is deployable and CI-checked | `tests/test_s1_5_repo_hygiene.py` (4 tests) | done |

Resolution of the review's P1 findings: eval scripts (`Subset`, phantom
`dermatology_ai` package) rewritten around `scripts/eval_common.py`; PHI removed
from audit rows, failed-login records and CSV exports; Windows-only paths
replaced with repo-relative ones; DDI corrected to 656 images / 570 patients with
its DOI; `LICENSE`, `CITATION.cff`, `MODEL_CARD.md`, `.env.example`,
`.github/workflows/ci.yml` and a working `render.yaml` added.

## Sprint 2 -- operations

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S2-1** | Operable: request ids, safe access logs, credential redaction, monitoring summary | `tests/test_s2_1_operability.py` (12 tests) | done |
| **S2-2** | Backups are verified and actually restore | `tests/test_s2_2_backup_restore.py` (6 tests) | done |
| **S2-3** | Retention policy is enforceable | `tests/test_s2_3_retention.py` (3 tests) | done |
| **S2-4** (gate) | Runbook: monitoring, incident response, rollback, go-live checklist | `tests/test_s2_4_operations_runbook.py` (5 tests) | done |

## Sprint 3 -- review leftovers (P2/P3)

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S3-1** | Remaining P2/P3 findings: upload cap while streaming, no login timing oracle, atomic agent saves, dashboard returns to login on 401, documentation placeholders removed, dataset cards + CONTRIBUTING added, `.gitignore` cleaned, unused imports removed | `tests/test_s3_1_cleanup.py` (8 tests) | done |

## Sprint 4 -- dataset substitution and gate options

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S4-1** | Any external dermatology dataset can be converted into the training format without editing training code, with every input row accounted for and no invented labels or Fitzpatrick values | `tests/test_s4_1_dataset_adapter.py` (6 tests) | done |
| **S4-2** | PASSION dependency resolved on paper: card corrected to the published figures and marked unavailable; alternatives assessed and recommended | `docs/DATASET_CARD_PASSION.md`, `docs/DATASET_ALTERNATIVES.md`, `docs/DATASET_CARD_SCIN.md` | done |
| **S4-3** | The four unsatisfied gates are presented as decisions with cost and consequences, not left as a 503 | `docs/GATE_OPTIONS.md` | done |
| **S4-5** | Training actually produces the artefact S1-1 needs: group-aware split (no lesion leakage), per-tone metrics that omit empty groups, and a smoke run that trains but cannot be frozen | `tests/test_s4_4_training_pipeline.py` (10 tests) | done |
| **S4-6** | The PASSION helper no longer describes a dataset that does not exist, and cannot impute a skin type | `tests/test_s4_2_passion_script.py` (6 tests) | done |
| **S4-4** | Approved pathway `1A 2A 3A 4A`: runbook signed with an explicit review basis, retention policy in force, exemption request prepared -- and no fabricated metadata left in the PASSION helper | `tests/test_s4_3_gate_signoff.py`, `tests/test_s4_2_passion_script.py` | done (gates 2, 3) / prepared (gate 4) |

## Sprint 5 -- brand, and the pause on gate 1A

| ID | Requirement | Acceptance test(s) | Status |
| --- | --- | --- | --- |
| **S5-1** | One logo everywhere: the approved navy/coral artwork replaces the three drifting SVG marks on the login card, both headers, the slides and the poster; assets are served from one pinned directory | `tests/test_s5_1_branding.py` (8 tests) | done |
| **S5-2** | The pause on gate 1A is enforced by the code, not by prose: a frozen artefact can be held out of service, and the API reports why | `tests/test_s5_2_serving_hold.py` (5 tests) | done |
| **S5-3** | The T4 procedure is one script that refuses partial downloads and cannot silently produce a servable model | `scripts/train_on_t4.sh --check`, `bash -n` in CI | done |

## Scope decisions

| Date | Decision | Effect |
| --- | --- | --- |
| 2026-10-30 | **The triage module stays.** It is part of the product (API `triage*` fields, `TRUE_LABEL_TO_TRIAGE`, dashboard panel, `metrics_tracker` triage maths, poster and docs). | Review item **P2-12 is withdrawn**; the branch name `pre-triage-removal` is historical and does not describe the code |
| 2026-10-30 | PASSION is treated as **unavailable** after unanswered access requests | Nothing in the pipeline depends on it; SCIN is the recommended substitute for the evaluation role only |
| 2026-10-31 | **Gate 1A is paused** until a Kaposi sarcoma cohort is obtained. No checkpoint may be served in the meantime; a frozen artefact is allowed for measurement only, with `serving.enabled = false` | `/api/diagnose` keeps returning 503 with the hold reason; `train_model.py` holds by default; closing the pause requires a KS cohort that converts to a non-zero class count |
| 2026-10-31 | The approved logo (navy/coral emblem + "DERMATOLOGY SYSTEM") replaces every previous mark | One asset set in `assets/`, served from `/assets/`; the system is branded **Dermatology System** |
| 2026-10-30 | The three-class head is **not** redefined to fit whichever dataset is to hand | Mapped-label cohorts (SCIN, eSkinHealth) are used for tone-stratified evaluation, never as malignancy benchmarks |

## Gate before real patient data

| Gate item | State |
| --- | --- |
| S1-1 frozen manifest + model card | **paused 2026-10-31 at the owner's instruction** until a Kaposi sarcoma cohort exists. **not met -- pipeline ready, artefact not produced.** `scripts/train_model.py` trains and freezes under the rules that make the gate mean something (group-aware split, no invented provenance, smoke reports cannot be frozen). What blocks the actual run: HAM10000 images are served from `dataverse.harvard.edu`, which this development sandbox cannot reach, and **no obtainable public dataset here contains Kaposi sarcoma** (`docs/TRAINING.md` §2b) |
| S2-4 runbook | **met** -- signed 2026-10-30 in `docs/OPERATIONS.md` §6, with the review basis stated plainly: single-engineer self-review, **no independent audit** |
| Written retention/backup policy | **met** -- in force from 2026-10-30 (`SECURITY.md` §4), scoped to synthetic/de-identified data, review due 2027-01-28, enforced by `purge_records.py` and `backup_db.py --verify` |
| IRB / ethics sign-off | **request prepared -- determination pending.** `docs/IRB_EXEMPTION_REQUEST.md` is submission-ready (four bracketed fields to fill). Pending is not approved, and is not recorded as such |

Until all four are met: synthetic or fully de-identified data only.

**These four are decisions, not code.** `docs/GATE_OPTIONS.md` lays out, for each
one, the options available, their cost, what they unblock and which is
recommended; the recommended minimum is `1A + 2A + 3A + 4A` (train and freeze a
real checkpoint; self-sign the runbook with a stated single-reviewer scope;
adopt the retention policy with a review date; obtain a "not human-subjects"
exemption for public-data work).
