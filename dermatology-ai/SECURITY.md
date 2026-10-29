# Security, privacy and data-handling policy

**Status: prototype.** Derma-AI is a research and educational decision-support
system. It is **not a medical device**, has **no clinical validation**, and must
not be used to make treatment decisions. This document describes what the code
actually enforces, what it does not, and what must be true before any real
patient data is loaded.

Last reviewed: 2026-10-30 (branch `arena/45118ec8-derma-ai`).

---

## 1. Threat model

| Asset | Threat | Control |
| --- | --- | --- |
| Patient records (PHI) | Unauthorised read/write by a logged-in clinician | Per-route `require_permission(...)` checks, server-side only |
| Admin functions (account creation, password reset, session revocation) | Privilege escalation by a doctor or an anonymous client | `require_admin` on every `/api/admin/*` route, enumerated by test |
| Session tokens | Theft from process memory or logs | Only SHA-256 digests of tokens are stored; 8-hour TTL; revocable by `sid` or user |
| Credentials | Offline cracking / reuse of shipped defaults | bcrypt (per-password salt), 12+ char policy with class checks and a deny-list, per-account lockout |
| Model output | Being mistaken for a diagnosis | `/api/diagnose` returns 503 when no checkpoint is loaded; disclaimers in the UI/poster/slides |
| Displayed data (patient names, notes, filenames) | Stored XSS against clinicians | Output escaping helpers, no inline scripts, strict CSP |

Out of scope for this prototype: network-level attacks, host compromise,
supply-chain attacks, and physical access to the server.

---

## 2. Authentication: Bearer token, **no CSRF token**

The API authenticates every request with **`Authorization: Bearer <token>`**.

* **Why this is CSRF-safe.** A cross-origin attacker cannot set an
  `Authorization` header on a victim's behalf without CORS preflight approval,
  and browsers never attach a custom header automatically. There is therefore no
  ambient credential to ride on. This is why the per-route CSRF token check from
  the previous build was removed rather than "fixed".
* **Cookies are not accepted for authentication.** `tests/test_s0_2_authz_matrix.py::test_cookie_bearer_is_not_accepted`
  asserts that a valid token presented as a cookie is ignored. If a cookie
  session is ever introduced, CSRF protection (double-submit token or
  `SameSite=Strict`) **must** be added at the same time.
* Tokens live in memory only (`auth.SessionStore`, 8-hour TTL). A process restart
  logs everyone out. They are stored as SHA-256 digests, so a memory dump does
  not yield usable credentials.
* `POST /api/logout` revokes the caller's token; deactivating a doctor revokes
  all of their sessions immediately.

### Authorization model

One dependency set, used by every route (`auth.py`):

* `require_auth` -- any valid session; re-checks that a doctor account is still
  active on each request and kills the session if it is not.
* `require_admin` -- `role == "admin"`; anonymous -> 401, doctor -> 403.
* `require_permission(flag)` -- doctor flag check, admins bypass. Flags are the
  eight values in `constants.DOCTOR_PERMISSIONS`.

`tests/test_s0_2_authz_matrix.py::test_authz_matrix` enumerates `app.routes` at
runtime: every route under `/api/admin/` plus `/api/reset` and
`/api/offline-update` must return 403 for a doctor and must never return 401/403
for an admin. A new unprotected admin route fails the suite; there is no
hand-maintained list to forget to update.

---

## 3. Passwords

* Hashed with **bcrypt**, one salt per password (`auth.hash_password`).
* Policy (`auth.validate_password`): at least 12 characters, upper, lower, digit
  and symbol, plus a deny-list that includes the two historical defaults.
* Applied on doctor creation, password reset and admin password change. The
  deny-list strings are assembled at import time so the CI guard can grep for the
  literals without false positives (`scripts/ci_grep.sh`).
* **No default credentials ship.** The bootstrap admin password is taken from
  `ADMIN_BOOTSTRAP_PASSWORD` or generated; a generated password is written to
  `<DATA_DIR>/INITIAL_ADMIN_PASSWORD.txt` with mode `0600` and only the *path* is
  logged. Delete the file after the first sign-in and change the password.
* Repeated failures are throttled per account with exponential backoff
  (`auth.LoginThrottle`) on top of the per-IP `slowapi` limit. Behind a reverse
  proxy set `TRUST_PROXY=1`, otherwise every client shares the proxy's IP and one
  attacker can lock everyone out.

---

## 4. Data protection

* Persistence is a single SQLite database, `<DATA_DIR>/derma.db`, created with
  the directory at `0700` and the file at `0600`. Writes use `BEGIN IMMEDIATE`
  transactions and WAL, so concurrent writers cannot lose records (the previous
  JSON store lost 6 of 20 concurrent creates).
* Password hashes and internal lookup keys are stripped by
  `storage.public_user()` before any user record leaves the storage layer;
  `tests/test_s0_3` and the admin routes rely on this.
* **Encryption at rest is not implemented.** Whole-disk encryption or SQLite
  encryption (SQLCipher) is an operational prerequisite before real data, not a
  property of this code.
* Uploads: 10 MB cap enforced from `Content-Length` *and* while streaming, magic
  byte sniffing (not the client's content type), and `PIL.MAX_IMAGE_PIXELS` is
  bounded to defuse decompression bombs.
* Logs must not contain patient identifiers, tokens or password material. The
  bootstrap path logs a file path, never a secret.

### Retention and backup policy (draft -- requires IRB/legal sign-off)

Not yet in force. It is written down here so that the gap is explicit rather
than implicit.

| Item | Retention | Disposal |
| --- | --- | --- |
| Patient records (prototype/demo) | Deleted with `DATA_DIR`; no production instance exists | Delete the directory and its backups |
| Patient records (research, post-IRB) | Duration in the approved protocol; default 5 years after last contact | Secure deletion of DB + backups, logged |
| Audit log | 24 months | Secure deletion, logged |
| Session tokens | 8 hours (memory only) | Process exit |
| Backups | Daily snapshot, 30-day rotation, encrypted at rest, stored in Uganda | Verified restore quarterly; deleted on expiry |
| Model checkpoints & exported CSVs | Indefinite for the frozen artefact, but de-identified only | Never include direct identifiers in exports |

Backups must be **restorable and tested**; an untested backup is not a backup.
Both the retention period and the backup target require IRB approval.

---

## 5. Client-side controls

* `dashboard.html` contains no inline `<script>` body; the application script is
  served as `/dashboard.js`, so the CSP can use `script-src 'self'` with no
  `'unsafe-inline'`.
* No third-party scripts, fonts or CDNs are loaded (offline clinics, no supply
  chain).
* All dynamic markup goes through `esc()` or `textContent`; image sources are
  restricted to `data:image/...;base64` by `safeImageUrl()`. Both are unit-tested
  with hostile payloads in `tests/test_s0_4_dashboard_xss.py`.
* CSP: `default-src 'self'; script-src 'self'; object-src` none via default;
  `frame-ancestors 'none'`; `X-Frame-Options: DENY`; `nosniff`;
  `Referrer-Policy: same-origin`.

---

## 6. Honest-output rules

* No `_mock_*` fallback anywhere. Without a checkpoint, `/api/diagnose` returns
  **503** with `{"error": "model_unavailable", "reason": ...}`.
* `/api/health` is liveness only and never touches the model or database;
  `/api/ready` reports `model_ready`, `reason`, weight hash and whether demo mode
  is on.
* Metrics are computed from stored cases. Accuracy is only computed over
  **clinician-confirmed ground truth**; model-vs-clinician agreement is reported
  separately; empty Fitzpatrick groups are `None`, never `0.0`.
* Demo data is opt-in (`DEMO_MODE=1`), every record is flagged `simulated`, and
  it is never used as evaluation data.

---

## 7. CI guards

`scripts/ci_grep.sh` fails the build if the strings `hipaa`, `256-bit`, `84.3`,
`0.843`, `admin123` or `Doctor123!` appear in shipped code (`.py`, `.html`,
`.js`, `.json`, `.yaml`). It also fails on `_mock_*`/`_fake_*` clinical payload
helpers.

Excluded from the scan, deliberately:

* `tests/` -- the tests assert these values are *rejected*;
* `*.md` -- review and brief documents quote the findings they describe;
* `notebooks/*.ipynb` -- removed; only the `.py` sources are kept.

Test suite: `python -m pytest` from the application directory (69 tests at the
time of writing, covering Sprint 0 items S0-1..S0-7).

---

## 8. Known gaps / before real patient data

1. **S1-1** and **S2-4** must be complete.
2. An approved **retention and backup policy** (section 4 above is a draft).
3. **IRB / ethics sign-off** for the Ugandan cohort, including the data-sharing
   question.
4. Encryption at rest and a tested restore.
5. A penetration test and a documented incident-response contact.

Until all five are done, use synthetic or fully de-identified data only.

## Reporting a vulnerability

Do not open a public issue for a security problem. Contact the maintainer of this
repository privately and include the affected route, a reproduction, and the
impact you observed.
