# run: debug-fcc-server-errors   status: active
request: Debug 500 Internal Server Errors observed in the admin UI at http://127.0.0.1:8082/admin — acceptance: be able to log into admin dashboard using known credentials without 500 errors; admin login succeed; admin UI loads doctor list and analytics.
base: pre-triage-removal @ 5732b5903daa685d069a962241d6a2bac9efe20f
| id | kind | status | complexity | model | session | worktree/branch | validated_commit | rounds | depends_on |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| R1 | research | pending | normal |  |  |  |  | 0 |  |\n| I1 | implementation | pending | normal |  |  |  |  | 0 | R1 |\n| V1 | verification | pending | normal |  |  |  |  | 0 | I1 |
