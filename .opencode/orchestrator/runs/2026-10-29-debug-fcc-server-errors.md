# run: debug-fcc-server-errors   status: active
request: Debug 500 Internal Server Errors observed in the admin UI at http://127.0.0.1:8082/admin — acceptance: be able to log into admin dashboard using known credentials without 500 errors; admin login succeed; admin UI loads doctor list and analytics.
base: pre-triage-removal @ 5732b5903daa685d069a962241d6a2bac9efe20f
| id | kind | status | complexity | model | session | worktree/branch | validated_commit | rounds | depends_on |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| R1 | research | done | normal |  |  |  |  | 0 |  |\n| I1 | implementation | done | normal |  |  |  | 009e5a5de823c10cb4ad9bef7a25b42f02e91e07 | 0 | R1 |\n## Decisions
- 2026-10-29: Research completed — admin bootstrap password is generated randomly unless ADMIN_BOOTSTRAP_PASSWORD is set; the plain token is only logged as a warning and not persisted. Recommend writing the token to a file (admin_bootstrap_password.txt) and logging its location. (Accepted)

## Findings & risks
- Without explicit password, developers cannot log in as admin, causing 500 errors in admin UI.
- Storing plain token on disk is safe only for local development; must be .gitignored.
- Production deployments should enforce ADMIN_BOOTSTRAP_PASSWORD and avoid file write.

