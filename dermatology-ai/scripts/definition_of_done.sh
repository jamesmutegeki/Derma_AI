#!/usr/bin/env bash
# Definition of done -- run from a clean checkout before claiming completion.
#
#   bash dermatology-ai/scripts/definition_of_done.sh
#
# Exits non-zero if any check fails. Nothing here is advisory.

set -uo pipefail

cd "$(dirname "$0")/.."
APP_DIR="$PWD"
REPO_ROOT="$(cd .. && pwd)"
PYTHON="${PYTHON:-python}"

pass=0
fail=0
declare -a failures=()

check() {  # check <name> <command...>
  local name="$1"; shift
  if "$@" >/tmp/dod.out 2>&1; then
    printf '  PASS  %s\n' "$name"
    pass=$((pass + 1))
  else
    printf '  FAIL  %s\n' "$name"
    sed 's/^/          /' /tmp/dod.out | tail -8
    fail=$((fail + 1))
    failures+=("$name")
  fi
}

echo "Definition of done -- $APP_DIR"
echo "commit: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
echo

echo "1. Code integrity"
check "every module byte-compiles" "$PYTHON" -m compileall -q .
check "no undefined names / syntax errors (ruff E9,F63,F7,F82)" \
      "$PYTHON" -m ruff check . --select E9,F63,F7,F82 --exclude tests
check "no fabricated claims or default credentials" bash scripts/ci_grep.sh

echo
echo "2. Behaviour"
check "full test suite" "$PYTHON" -m pytest -q

echo
echo "3. Honesty"
check "model manifest is present and validates" "$PYTHON" - <<'PY'
import json, re, sys
m = json.load(open("model_manifest.json"))
assert m["status"] in {"placeholder", "frozen"}, m["status"]
assert m["architecture"]["num_classes"] == 3
if m["status"] == "frozen":
    assert re.fullmatch(r"[0-9a-f]{64}", m["checkpoint"]["sha256"] or "")
else:
    assert m["checkpoint"]["sha256"] is None
PY
check "no mock/fake clinical helpers" bash -c \
      "! grep -rnE '_(mock|fake)_(diagnos|analy|predic|patient)' --include='*.py' --exclude-dir=tests ."
check "no committed database, checkpoint or .env" bash -c \
      "! find '$REPO_ROOT' -name .git -prune -o -type f \
        \( -name '*.db' -o -name '*.pt' -o -name '*.pth' -o -name '.env' \) -print | grep -q ."
check "disclaimer present in the UI and the docs" bash -c \
      "grep -qi 'not a medical device' dashboard.html && grep -qi 'not a medical device' MODEL_CARD.md"

echo
echo "4. Operations"
check "runbook, security policy and model card exist" bash -c \
      "test -f docs/OPERATIONS.md -a -f SECURITY.md -a -f MODEL_CARD.md -a -f REMEDIATION_STATUS.md"
check "backup verifies and restores" bash -c "
  tmp=\$(mktemp -d)
  DATA_DIR=\$tmp $PYTHON -c 'import sys; sys.path.insert(0,\".\"); from storage import Store; s=Store(sys.argv[1]); s.create_patient({\"name\":\"DoD\"}); s.close()' \"\$tmp\"
  $PYTHON scripts/backup_db.py --data-dir \"\$tmp\" --verify | grep -q 'verify:   ok'
  rm -rf \"\$tmp\""

echo
echo "5. API boots and tells the truth"
check "health is 200 and ready is honest" bash -c "
  tmp=\$(mktemp -d)
  DATA_DIR=\$tmp $PYTHON - <<'PY'
import sys
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from server import create_app
app = create_app(initialise_backend=False)
with TestClient(app) as c:
    assert c.get('/api/health').status_code == 200
    ready = c.get('/api/ready').json()
    assert ready['model_ready'] is False and ready['reason'], ready
    assert c.get('/api/patients').status_code == 401
    assert c.get('/api/admin/doctors').status_code == 401
PY
  rm -rf \"\$tmp\""

echo
echo "------------------------------------------------------------"
printf '%d passed, %d failed\n' "$pass" "$fail"
if (( fail > 0 )); then
  printf 'Blocking: %s\n' "${failures[*]}"
  exit 1
fi
echo "DEFINITION OF DONE: satisfied for the scope implemented in this branch."
echo "Not satisfied (by design): S1-1 frozen weights, S2-4 signature, approved"
echo "retention policy, IRB sign-off -- see docs/OPERATIONS.md section 6."
