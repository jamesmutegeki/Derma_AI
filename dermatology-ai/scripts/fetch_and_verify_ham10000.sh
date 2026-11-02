#!/usr/bin/env bash
# Pull a HAM10000 mirror from a GitHub release, verify it, and convert it.
#
# Why a release and not the repository: GitHub rejects any file over 100 MB, and
# HAM10000's two image archives are ~1.37 GB each. Release assets allow up to
# 2 GiB per file, so they are the only sane place for a private mirror.
#
# HAM10000 is CC BY-NC 4.0 (Tschandl et al. 2018, doi:10.7910/DVN/DBW86T):
# non-commercial research use, attribution required. Delete the release once the
# frozen artefact exists; do not leave a permanent public mirror behind.
#
# Usage:
#   bash scripts/fetch_and_verify_ham10000.sh --check
#   bash scripts/fetch_and_verify_ham10000.sh \
#       --repo jamesmutegeki/Derma_AI --tag ham10000-v1 \
#       --work ~/ham10000
#
# Requires an authenticated `gh` for a private repository.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO=""
TAG=""
WORK_DIR="${WORK_DIR:-${HOME}/ham10000}"
PYTHON="${PYTHON:-python}"
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:?--repo needs owner/name}"; shift 2 ;;
    --tag) TAG="${2:?--tag needs a release tag}"; shift 2 ;;
    --work) WORK_DIR="${2:?--work needs a directory}"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }

say "plan"
cat <<EOF
  release    ${REPO:-<not set>} ${TAG:-<no tag>}
  work dir   ${WORK_DIR}
  outputs    ${WORK_DIR}/images, ${WORK_DIR}/converted
EOF

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  command -v gh >/dev/null || echo "  gh: MISSING (needed for a private repository)"
  command -v unzip >/dev/null || echo "  unzip: MISSING"
  echo "  check only -- nothing downloaded, nothing converted"
  exit 0
fi

[[ -n "${REPO}" && -n "${TAG}" ]] || { echo "--repo and --tag are required" >&2; exit 2; }

mkdir -p "${WORK_DIR}/download" "${WORK_DIR}/images"

say "download release assets"
gh release download "${TAG}" --repo "${REPO}" --dir "${WORK_DIR}/download" --clobber

say "checksums (informational)"
( cd "${WORK_DIR}/download" && sha256sum ./* 2>/dev/null || true )

say "unpack"
for archive in "${WORK_DIR}"/download/*.zip; do
  [[ -e "${archive}" ]] || continue
  unzip -n -q "${archive}" -d "${WORK_DIR}/images.raw"
done

# Flatten whatever directory shape the archive used.
find "${WORK_DIR}/images.raw" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \) \
  -exec mv -n {} "${WORK_DIR}/images/" \; 2>/dev/null || true

say "verify"
"${PYTHON}" "${APP_DIR}/scripts/verify_ham10000.py" \
  --images-dir "${WORK_DIR}/images" \
  --metadata "$(find "${WORK_DIR}/download" -maxdepth 1 -name '*metadata*.csv' | head -1)" \
  --out "${WORK_DIR}/verification.json"

say "convert (hardlinks: the corpus is 2.7 GB and does not need a second copy)"
"${PYTHON}" "${APP_DIR}/scripts/prepare_dataset.py" \
  --input "$(find "${WORK_DIR}/download" -maxdepth 1 -name '*metadata*.csv' | head -1)" \
  --images-root "${WORK_DIR}/images" \
  --image-column image_id \
  --label-column dx \
  --fitz-column "" \
  --label-map "${APP_DIR}/scripts/label_maps/ham10000.json" \
  --group-column lesion_id \
  --link hardlink \
  --output "${WORK_DIR}/converted" \
  --source HAM10000

say "summary"
"${PYTHON}" - "${WORK_DIR}/converted/conversion_report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
print(f"  rows {report['rows_in']} -> {report['rows_out']}")
print(f"  classes {report['class_counts']}")
print(f"  skipped {report['skipped']}")
if "kaposi_sarcoma" in report["class_counts"]:
    raise SystemExit("unexpected kaposi_sarcoma rows in HAM10000")
print("  no kaposi_sarcoma rows, as expected: gate 1A stays paused")
PY

cat <<EOF

Next:
  python scripts/train_model.py --data-dir ${WORK_DIR}/converted \\
      --out runs/ham10000-\$(date +%F) --epochs 10 --batch-size 32 --img-size 224 \\
      --dataset HAM10000 --split "group-aware 80/20 by lesion_id, seed 42" \\
      --allow-untrained-classes --freeze
EOF
