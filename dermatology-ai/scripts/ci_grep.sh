#!/usr/bin/env bash
# CI guard: fail the build on fabricated claims and shipped default credentials.
#
# Scope: everything that ships (Python, HTML, JS, JSON, YAML).  Deliberately
# excluded:
#   * tests/                - they assert these strings are *rejected*
#   * *.md                  - review/brief documents quote the findings
#   * docs/, notebooks/*.ipynb - not executed at runtime (notebooks are .py)
#
# Usage: bash scripts/ci_grep.sh   (exit 0 = clean)

set -euo pipefail

cd "$(dirname "$0")/.."

PATTERN='hipaa|256-bit|84\.3|0\.843|admin123|Doctor123'

matches=$(
  grep -rniE "$PATTERN" \
    --include='*.py' --include='*.html' --include='*.js' \
    --include='*.json' --include='*.yaml' --include='*.yml' \
    --exclude-dir=tests \
    --exclude-dir=__pycache__ \
    --exclude-dir=.git \
    . || true
)

if [[ -n "$matches" ]]; then
  echo "FAIL: fabricated-claim / default-credential guard found matches:" >&2
  printf '%s\n' "$matches" >&2
  exit 1
fi

# Second guard: no mocked clinical payload may be returned by the API.
if grep -rnE '_(mock|fake)_(diagnos|analy|predic|patient)' \
     --include='*.py' --exclude-dir=tests --exclude-dir=__pycache__ . >/dev/null; then
  echo "FAIL: mock/fake clinical payload helper is still present." >&2
  exit 1
fi

echo "OK: no fabricated claims, no default credentials, no mock payloads."
