#!/usr/bin/env bash
# Train HAM10000 on a GPU box (T4 class) and freeze an artefact.
#
# This is the runner for gate 1A. It is deliberately boring: download, convert,
# train, freeze, print what happened. Every step is a script in this repository,
# so nothing is hidden here that a reviewer cannot re-run by hand.
#
# What it does NOT do:
#   * it does not invent Kaposi sarcoma data. HAM10000 has none, so the run
#     trains with `--allow-untrained-classes` and the artefact is frozen with
#     serving HELD (gate 1A paused 2026-10-31). `/api/diagnose` keeps returning
#     503 until a Kaposi sarcoma cohort exists.
#   * it does not publish numbers. The report it writes is the only source any
#     later figure may quote from.
#
# Usage:
#   bash scripts/train_on_t4.sh --check          # verify prerequisites, no work
#   bash scripts/train_on_t4.sh                  # full run (downloads ~3 GB)
#   EPOCHS=6 IMG_SIZE=224 bash scripts/train_on_t4.sh
#
# Colab (Runtime -> Change runtime type -> T4 GPU):
#   !git clone https://github.com/jamesmutegeki/Derma_AI.git && cd Derma_AI
#   !bash dermatology-ai/scripts/train_on_t4.sh
#   then download dermatology-ai/runs/<date>/report.json and model_manifest.json

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${APP_DIR}/datasets/ham10000}"
DATA_DIR="${DATA_DIR:-${WORK_DIR}/prepared}"
RUN_DIR="${RUN_DIR:-${APP_DIR}/runs/ham10000-$(date +%F)}"
EPOCHS="${EPOCHS:-10}"
BATCH_SIZE="${BATCH_SIZE:-32}"
IMG_SIZE="${IMG_SIZE:-224}"
SEED="${SEED:-42}"
PYTHON="${PYTHON:-python}"
HOLD_REASON="Kaposi sarcoma cohort pending (gate 1A paused 2026-10-31)"
CHECK_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }

say "environment"
"${PYTHON}" - <<'PY'
import platform
import sys

print(f"python   {sys.version.split()[0]}  ({platform.platform()})")
try:
    import torch
    print(f"torch    {torch.__version__}  cuda={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"gpu      {torch.cuda.get_device_name(0)}")
    else:
        print("gpu      none -- a T4 run should show cuda=True. "
              "CPU training is possible but slow; see docs/TRAINING.md section 5")
except ImportError:
    print("torch    MISSING -- run: pip install -r requirements.txt")
PY

say "plan"
cat <<EOF
  work dir   ${WORK_DIR}
  prepared   ${DATA_DIR}
  run dir    ${RUN_DIR}
  epochs     ${EPOCHS}
  batch      ${BATCH_SIZE}
  image size ${IMG_SIZE}
  seed       ${SEED}
  serving    HELD: ${HOLD_REASON}
EOF

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  say "check only -- nothing downloaded, nothing trained"
  exit 0
fi

mkdir -p "${WORK_DIR}/downloads" "${WORK_DIR}/images"

say "download HAM10000 from Harvard Dataverse (public, no account)"
METADATA_URL="https://dataverse.harvard.edu/api/access/datafile/4338392?format=original"
PART1_URL="https://dataverse.harvard.edu/api/access/datafile/3172585"
PART2_URL="https://dataverse.harvard.edu/api/access/datafile/3172584"

fetch() {  # url, destination
  if [[ -s "$2" ]]; then
    echo "  have $(basename "$2") ($(du -h "$2" | cut -f1))"
    return
  fi
  echo "  fetching $(basename "$2")"
  curl -fL --retry 3 --retry-delay 5 -o "$2.part" "$1"
  mv "$2.part" "$2"
}

fetch "${METADATA_URL}" "${WORK_DIR}/downloads/HAM10000_metadata.csv"
fetch "${PART1_URL}" "${WORK_DIR}/downloads/HAM10000_images_part1.zip"
fetch "${PART2_URL}" "${WORK_DIR}/downloads/HAM10000_images_part2.zip"

say "unpack images"
for archive in "${WORK_DIR}"/downloads/HAM10000_images_part*.zip; do
  if ! find "${WORK_DIR}/images" -maxdepth 1 -name 'ISIC_*.jpg' -print -quit | grep -q .; then
    unzip -n -q "${archive}" -d "${WORK_DIR}/images"
  fi
done
IMAGE_COUNT="$(find "${WORK_DIR}/images" -maxdepth 2 -name 'ISIC_*.jpg' | wc -l)"
echo "  images on disk: ${IMAGE_COUNT}"
if [[ "${IMAGE_COUNT}" -lt 9000 ]]; then
  echo "refusing to continue: expected ~10,015 images, found ${IMAGE_COUNT}." >&2
  echo "the download is incomplete -- delete ${WORK_DIR}/downloads and re-run." >&2
  exit 3
fi

# Some archives unpack into a subdirectory; flatten so every image is in one place.
find "${WORK_DIR}/images" -mindepth 2 -name 'ISIC_*.jpg' -exec mv -n {} "${WORK_DIR}/images/" \; 2>/dev/null || true

say "convert to the training layout"
"${PYTHON}" "${APP_DIR}/scripts/prepare_dataset.py" \
  --input "${WORK_DIR}/downloads/HAM10000_metadata.csv" \
  --images-root "${WORK_DIR}/images" \
  --image-column image_id \
  --label-column dx \
  --fitz-column "" \
  --label-map "${APP_DIR}/scripts/label_maps/ham10000.json" \
  --group-column lesion_id \
  --output "${DATA_DIR}" \
  --source HAM10000

"${PYTHON}" - "${DATA_DIR}/conversion_report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
print(f"  rows: {report['rows_in']} -> {report['rows_out']}")
print(f"  classes: {report['class_counts']}")
print(f"  skipped: {report['skipped']}")
if report["rows_out"] < 8000:
    raise SystemExit("refusing to train: fewer than 8000 converted rows")
if "kaposi_sarcoma" in report["class_counts"]:
    raise SystemExit("unexpected: HAM10000 cannot contain kaposi_sarcoma")
print("  as expected: no kaposi_sarcoma rows (gate 1A stays paused)")
PY

say "train"
"${PYTHON}" "${APP_DIR}/scripts/train_model.py" \
  --data-dir "${DATA_DIR}" \
  --out "${RUN_DIR}" \
  --epochs "${EPOCHS}" \
  --batch-size "${BATCH_SIZE}" \
  --img-size "${IMG_SIZE}" \
  --seed "${SEED}" \
  --dataset HAM10000 \
  --split "group-aware 80/20 by lesion_id, seed ${SEED}" \
  --allow-untrained-classes \
  --hold-reason "${HOLD_REASON}" \
  --freeze

say "result"
"${PYTHON}" - "${RUN_DIR}/report.json" "${APP_DIR}/model_manifest.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1]))
manifest = json.load(open(sys.argv[2]))
metrics = report["metrics"]
print(f"  report      {sys.argv[1]}")
print(f"  checkpoint  {report['checkpoint']['path']}")
print(f"  sha256      {report['checkpoint']['sha256']}")
print(f"  valid       {report['valid']}")
print(f"  macro F1    {metrics['macro_f1']}")
for name, values in metrics["per_class"].items():
    print(f"    {name:<14} support={values['support']:<5} f1={values['f1']}")
for group, values in metrics["per_skin_type"].items():
    label = group if values["known_skin_type"] else "unknown (HAM10000 has no skin type)"
    print(f"    skin type {group}: n={values['n']} accuracy={values['accuracy']}  {label}")
print(f"  untrained   {report['untrained_classes']}")
print(f"  manifest    status={manifest['status']} serving={manifest['serving']}")
PY

cat <<EOF

Next:
  1. Copy runs/$(basename "${RUN_DIR}")/report.json and model_manifest.json back into the repo.
  2. Serving stays HELD -- do not pass --serve while gate 1A is paused.
  3. Quote numbers only from that report (docs/TRAINING.md section 6).
EOF
