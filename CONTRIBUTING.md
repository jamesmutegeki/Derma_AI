# Contributing

This is a **research prototype**, not a medical device (see `README.md`). Nothing
in a pull request may imply clinical validation, and no performance number may be
added unless it traces to a frozen evaluation report.

## Ground rules

1. **Test first.** Every change to behaviour lands with a test that fails before
   the change and passes after. Acceptance tests for the remediation work are
   named `tests/test_s<phase>_<n>_*.py`.
2. **No fake data, ever.** No `_mock_*` / `_fake_*` clinical payload, no random
   fallback, no "if the model is missing, return melanoma". A missing model is a
   `503`, a missing record is a `404`.
3. **One source of truth.** Preprocessing lives in `transforms.build_transform`,
   authorization in `auth.py`, constants in `constants.py`, schemas in
   `schemas.py`. Do not add a second copy.
4. **Say what you did not do.** If a number, dataset or result is unmeasured, the
   documentation says so explicitly.
5. **Never commit** patient data, `derma.db`, checkpoints (`.pt`), `.env` or
   credentials.

## Before opening a pull request

```bash
cd dermatology-ai
python -m pytest -q                 # all tests
bash scripts/ci_grep.sh             # fabricated-claim / credential guard
bash scripts/definition_of_done.sh  # the full gate
```

All three must pass. The CI workflow runs the same commands.

## Code style

* Python 3.11, type hints on public functions, `from __future__ import annotations`.
* Tag security-relevant edits with `# SECURITY FIX:` and modelling changes with
  `# ML FIX:`, with one sentence on why.
* Keep dependencies pinned in `requirements.txt`; new dependencies are a
  discussion, not a reflex.
* The dashboard script lives in `dashboard.js` (no inline `<script>`), and any
  new DOM string goes through `esc()` or `textContent`.

## Reporting a problem

Security issues: follow `dermatology-ai/SECURITY.md` ("Reporting a vulnerability"),
not a public issue. Everything else: open an issue with the route or file, what
you expected, and what happened (include the `X-Request-ID` from the response if
you have it).
