# Remediation status

Living record of the review remediation (`CODE_REVIEW.md`, baseline `13a299a`).
An item is only marked **done** when its named acceptance test passes from a
clean checkout.

Run the gate:

```bash
cd dermatology-ai
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # 69 passed
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

---

## Sprint 1 -- model and data integrity

*(next; see the sprint plan)*

## Sprint 2 -- operations

*(next)*
