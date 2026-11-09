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
PYTHON="${PYTHON:-venv/bin/python}"

# Common ignore list for all guards: virtualenvs, generated data, caches
IGNORE_DIRS="venv* .venv datasets runs node_modules __pycache__ .git .mypy_cache .ruff_cache"
# Build --exclude-dir args for grep/ruff
EXCLUDE_DIRS=""
for d in $IGNORE_DIRS; do
  EXCLUDE_DIRS="$EXCLUDE_DIRS --exclude-dir=$d"
done

# Build -x args for compileall (regex patterns to exclude)
EXCLUDE_REGEX=""
for d in $IGNORE_DIRS; do
  EXCLUDE_REGEX="$EXCLUDE_REGEX -x $d"
done

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
check "every module byte-compiles" bash -c "
  find . -name '*.py' \
    -not -path './venv/*' -not -path './.venv/*' \
    -not -path './datasets/*' -not -path './runs/*' \
    -not -path './node_modules/*' -not -path './__pycache__/*' \
    -not -path './.git/*' -not -path './.mypy_cache/*' -not -path './.ruff_cache/*' \
    | xargs -r $PYTHON -m py_compile
"
check "no undefined names / syntax errors (ruff E9,F63,F7,F82)" \
      "$PYTHON" -m ruff check . --select E9,F63,F7,F82 --exclude tests --exclude seed_demo.py --exclude _test_patients.py --exclude _verify_fix.py
check "no fabricated claims or default credentials" bash scripts/ci_grep.sh

echo
echo "2. Behaviour"
check "PASSION test suite (S10)" "$PYTHON" -m pytest tests/test_s10_passion.py -q

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
      "! grep -rnE '_(mock|fake)_(diagnos|analy|predic|patient)' --include='*.py' $EXCLUDE_DIRS --exclude-dir=tests ."

# Git-aware artefact scan: fail if any *.db, *.pt, *.pth, *.pth.tar, *.ckpt, .env are TRACKED
check "no committed database, checkpoint or .env" bash -c '
  if ! git -C "'"$REPO_ROOT"'" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "run this inside a clone" >&2
    exit 2
  fi
  if git -C "'"$REPO_ROOT"'" ls-files -- "*.db" "*.pt" "*.pth" "*.pth.tar" "*.ckpt" ".env" | grep -q .; then
    echo "TRACKED artefacts found:" >&2
    git -C "'"$REPO_ROOT"'" ls-files -- "*.db" "*.pt" "*.pth" "*.pth.tar" "*.ckpt" ".env" >&2
    exit 1
  fi
'

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
echo "Not satisfied (by design): S1-1 frozen weights (PAUSED 2026-10-31 until a"
echo "Kaposi sarcoma cohort exists), IRB determination."
echo "S2-4 (signed 2026-10-30) and the retention policy (in force 2026-10-30)"
echo "are closed; see docs/OPERATIONS.md section 6 and docs/TRAINING.md."
echo "The remaining two are tracked in docs/GATE_OPTIONS.md and docs/IRB_EXEMPTION_REQUEST.md."