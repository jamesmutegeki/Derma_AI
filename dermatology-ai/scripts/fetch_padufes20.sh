#!/usr/bin/env bash
# Download PAD-UFES-20, verify it, and convert it -- no form, no waiting.
#
# 2,298 smartphone clinical images from a Brazilian public clinic, with
# biopsy-proven cancers and a Fitzpatrick type per patient. CC BY 4.0, so
# attribution is required and redistribution is allowed.
#
#   Pacheco et al., Data in Brief 2020 · DOI 10.17632/zr7vgbcyr2.1
#
# Usage:
#   bash scripts/fetch_padufes20.sh --check
#   bash scripts/fetch_padufes20.sh --work ~/padufes        # ~3.35 GB download
#   WORK_DIR=~/padufes bash scripts/fetch_padufes20.sh
#
# The script refuses to convert if verification fails, so a partial download
# cannot become a training set.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${APP_DIR}/datasets/padufes20}"
PYTHON="${PYTHON:-python}"
URL="${PADUFES_URL:-https://prod-dcd-datasets-cache-zipfiles.s3.eu-west-1.amazonaws.com/zr7vgbcyr2-1.zip}"
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --work) WORK_DIR="${2:?--work needs a directory}"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }

say "plan"
cat <<EOF
  source     ${URL}
  work dir   ${WORK_DIR}
  licence    CC BY 4.0 (Pacheco et al. 2020, DOI 10.17632/zr7vgbcyr2.1)
  contents   2,298 images · 1,641 lesions · 1,373 patients · 6 diagnoses
  skin tone  Fitzpatrick per patient (this is why it was chosen)
  note       no Kaposi sarcoma: gate 1A stays paused
EOF

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  command -v curl >/dev/null || echo "  curl: MISSING"
  command -v unzip >/dev/null || echo "  unzip: MISSING"
  echo "  check only -- nothing downloaded, nothing converted"
  exit 0
fi

mkdir -p "${WORK_DIR}/download" "${WORK_DIR}/images"

say "download (resumable)"
ARCHIVE="${WORK_DIR}/download/zr7vgbcyr2-1.zip"
if [[ -s "${ARCHIVE}" ]]; then
  echo "  have $(basename "${ARCHIVE}") ($(du -h "${ARCHIVE}" | cut -f1))"
else
  curl -fL --retry 3 --retry-delay 5 -C - -o "${ARCHIVE}.part" "${URL}"
  mv "${ARCHIVE}.part" "${ARCHIVE}"
fi

say "unpack"
unzip -n -q "${ARCHIVE}" -d "${WORK_DIR}/download/extracted"

# The archive nests the images under one or two directories; flatten them.
find "${WORK_DIR}/download/extracted" -type f \
  \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
  -exec cp -n {} "${WORK_DIR}/images/" \; 2>/dev/null || true

METADATA="$(find "${WORK_DIR}/download/extracted" -maxdepth 2 -iname 'metadata.csv' | head -1)"
if [[ -z "${METADATA}" ]]; then
  echo "metadata.csv not found inside the archive; inspect ${WORK_DIR}/download/extracted" >&2
  exit 3
fi

say "verify (grouping, biopsy flags, skin types, class counts)"
"${PYTHON}" "${APP_DIR}/scripts/verify_padufes20.py" \
  --metadata "${METADATA}" \
  --images "${WORK_DIR}/images" \
  --out "${WORK_DIR}/verification.json"

say "convert (hardlinks -- no second copy of 3.35 GB)"
"${PYTHON}" "${APP_DIR}/scripts/prepare_dataset.py" \
  --input "${METADATA}" \
  --images-root "${WORK_DIR}/images" \
  --image-column "$("${PYTHON}" - "${METADATA}" <<'PY'
import csv, sys
# The image column name varies between mirrors; ask the file rather than guess.
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    headers = next(csv.reader(handle))
lookup = {h.strip().lower(): h for h in headers}
print(next(lookup[c] for c in ("img_id", "image_id", "image") if c in lookup))
PY
)" \
  --label-column "$("${PYTHON}" - "${METADATA}" <<'PY'
import csv, sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    headers = next(csv.reader(handle))
lookup = {h.strip().lower(): h for h in headers}
print(next(lookup[c] for c in ("diagnostic", "diagnosis", "label") if c in lookup))
PY
)" \
  --fitz-column "$("${PYTHON}" - "${METADATA}" <<'PY'
import csv, sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    headers = next(csv.reader(handle))
lookup = {h.strip().lower(): h for h in headers}
print(next(lookup[c] for c in ("fitzpatrick", "fitzpatrick_type", "skin_type", "fst") if c in lookup))
PY
)" \
  --group-column "$("${PYTHON}" - "${METADATA}" <<'PY'
import csv, sys
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    headers = next(csv.reader(handle))
lookup = {h.strip().lower(): h for h in headers}
print(next(lookup[c] for c in ("patient_id", "patient") if c in lookup))
PY
)" \
  --label-map "${APP_DIR}/scripts/label_maps/padufes20.json" \
  --link hardlink \
  --output "${WORK_DIR}/converted" \
  --source PAD-UFES-20

say "summary"
"${PYTHON}" - "${WORK_DIR}/converted/conversion_report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
print(f"  rows {report['rows_in']} -> {report['rows_out']}")
print(f"  classes {report['class_counts']}")
print(f"  skipped {report['skipped']}")
if report["class_counts"].get("melanoma", 0) > 60:
    raise SystemExit("melanoma count looks wrong for PAD-UFES-20 (published: 52)")
print("  fine. BCC/SCC/ACK were excluded, not merged into benign.")
PY

cat <<EOF

Next:
  python scripts/train_model.py --data-dir ${WORK_DIR}/converted \\
      --out runs/padufes-\$(date +%F) --epochs 20 --batch-size 32 --img-size 224 \\
      --dataset PAD-UFES-20 --split "patient-grouped 80/20, seed 42" \\
      --allow-untrained-classes --freeze

  (--freeze holds serving by default; gate 1A is paused.)
EOF
