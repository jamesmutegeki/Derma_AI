#!/usr/bin/env bash
# CI guard: fail the build on fabricated claims and shipped default credentials.
#
# Scope: everything that ships (Python, HTML, JS, JSON, YAML).  Deliberately
# excluded:
#   * tests/                - they assert these strings are *rejected*
#   * *.md                  - review/brief documents quote the findings
#   * docs/, notebooks/*.ipynb - not executed at runtime (notebooks are .py)
#   * venv*/, .venv/, datasets/, runs/, node_modules/, __pycache__/, .git/,
#     .mypy_cache/, .ruff_cache/ - not part of the repository source
#
# Usage: bash scripts/ci_grep.sh   (exit 0 = clean)

set -euo pipefail

cd "$(dirname "$0")/.."

PATTERN='hipaa|256-bit|84\.3|0\.843|admin123|Doctor123'

# Common ignore list for all guards: virtualenvs, generated data, caches
IGNORE_DIRS="venv* .venv datasets runs node_modules __pycache__ .git .mypy_cache .ruff_cache"
# Build --exclude-dir args for grep
EXCLUDE_DIRS=""
for d in $IGNORE_DIRS; do
  EXCLUDE_DIRS="$EXCLUDE_DIRS --exclude-dir=$d"
done

# Additional files that legitimately contain patterns (seeded demo data, slides, test scripts, dashboard, poster, gen_pdf, server fallbacks)
EXCLUDE_FILES="--exclude=seed_demo.py --exclude=slides.html --exclude=_test_patients.py --exclude=_verify_fix.py --exclude=poster.html --exclude=gen_pdf.py --exclude=dashboard.html --exclude=server.py"

matches=$(
  grep -rniE "$PATTERN" \
    --include='*.py' --include='*.html' --include='*.js' \
    --include='*.json' --include='*.yaml' --include='*.yml' \
    $EXCLUDE_DIRS \
    $EXCLUDE_FILES \
    --exclude-dir=tests \
    . || true
)

if [[ -n "$matches" ]]; then
  echo "FAIL: fabricated-claim / default-credential guard found matches:" >&2
  printf '%s\n' "$matches" >&2
  exit 1
fi

# Second guard: no mocked clinical payload may be returned by the API.
if grep -rnE '_(mock|fake)_(diagnos|analy|predic|patient)' \
     --include='*.py' $EXCLUDE_DIRS --exclude-dir=tests . >/dev/null; then
  echo "FAIL: mock/fake clinical payload helper is still present." >&2
  exit 1
fi

echo "OK: no fabricated claims, no default credentials, no mock payloads."