#!/usr/bin/env python3
"""Convert an external dermatology dataset into this project's training format.

The training and evaluation code reads one layout
(``datasetEquity.DermDataset``)::

    <out>/metadata.csv      image_id,label,fitzpatrick_type[,source]
    <out>/images/<id>.jpg

This script is the only place that knows how a *source* dataset is shaped. It
never guesses:

* labels are translated through an explicit JSON map (``scripts/label_maps/``);
  anything unmapped is reported and skipped, never coerced to `benign`;
* a missing Fitzpatrick value becomes ``0`` ("unknown") and is counted, not
  imputed;
* every input row appears in ``conversion_report.json`` either as converted or
  as skipped with a reason;
* if nothing converts, it fails instead of writing an empty dataset.

Examples
--------
    # SCIN (public GCS bucket), after exporting its CSVs locally
    python scripts/prepare_dataset.py \\
        --source scin \\
        --input <scin>/scin_cases_with_labels.csv \\
        --images-root <scin>/images \\
        --image-column image_path --label-column dermatologist_label_1 \\
        --fitz-column eFST \\
        --label-map scripts/label_maps/scin.json \\
        --output datasets/scin

    # A source whose columns match ours already
    python scripts/prepare_dataset.py --input raw.csv --images-root imgs \\
        --label-map scripts/label_maps/ddi.json --output datasets/ddi
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
LABEL_MAP_DIR = APP_DIR / "scripts" / "label_maps"
CLASSES = ("benign", "melanoma", "kaposi_sarcoma")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def load_label_map(path: str | Path) -> dict[str, str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # Keys starting with "_" are documentation (see the shipped maps), not labels.
    mapping = {k: v for k, v in raw.items() if not str(k).startswith("_")}
    unknown_targets = {v for v in mapping.values() if v not in (*CLASSES, "skip")}
    if unknown_targets:
        raise SystemExit(f"{path}: unsupported target labels {sorted(unknown_targets)}")
    return {str(key).strip().lower(): value for key, value in mapping.items()}


def normalise_fitz(value: str) -> int:
    """Return 1-6, or 0 when the source does not provide a usable value."""
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return 0
    number = int(digits[:2] if len(digits) > 1 else digits)
    return number if 1 <= number <= 6 else 0


def find_image(images_root: Path, relative: str) -> Path | None:
    candidate = images_root / relative
    if candidate.is_file():
        return candidate
    stem = candidate.with_suffix("")
    for suffix in IMAGE_SUFFIXES:
        alternative = Path(str(stem) + suffix)
        if alternative.is_file():
            return alternative
    return None


def convert(args) -> dict:
    source_csv = Path(args.input)
    if not source_csv.is_file():
        raise SystemExit(f"input CSV not found: {source_csv}")

    label_map = load_label_map(args.label_map)
    images_root = Path(args.images_root)
    if not images_root.is_dir():
        raise SystemExit(f"images root not found: {images_root}")

    output = Path(args.output)
    images_out = output / "images"
    images_out.mkdir(parents=True, exist_ok=True)

    rows_out: list[dict] = []
    skipped = Counter()
    unmapped: set[str] = set()
    missing: list[str] = []
    class_counts = Counter()
    fitz_counts = Counter()

    with source_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {args.image_column, args.label_column}
        missing_columns = required - set(reader.fieldnames or [])
        if missing_columns:
            raise SystemExit(
                f"{source_csv} is missing column(s) {sorted(missing_columns)}; "
                f"found {reader.fieldnames}"
            )

        rows_in = 0
        for row_number, row in enumerate(reader, start=2):
            rows_in += 1
            raw_label = (row.get(args.label_column) or "").strip()
            target = label_map.get(raw_label.lower())
            if target is None:
                skipped["unmapped_label"] += 1
                if raw_label:
                    unmapped.add(raw_label)
                continue
            if target == "skip":
                skipped["excluded_by_map"] += 1
                continue

            relative = (row.get(args.image_column) or "").strip()
            if not relative:
                skipped["no_image_path"] += 1
                continue
            image_path = find_image(images_root, relative)
            if image_path is None:
                skipped["missing_image"] += 1
                missing.append(relative)
                continue

            image_id = Path(relative).with_suffix("").name.replace(" ", "_")
            shutil.copyfile(image_path, images_out / f"{image_id}{image_path.suffix.lower()}")

            fitz = normalise_fitz(row.get(args.fitz_column, "") if args.fitz_column else "")
            fitz_counts[fitz] += 1
            class_counts[target] += 1
            rows_out.append({
                "image_id": image_id,
                "label": target,
                "fitzpatrick_type": fitz,
                "source": args.source or source_csv.stem,
                "source_path": relative,
                "_row": row_number,
            })

    if not rows_out:
        raise SystemExit(
            f"no rows converted: {json.dumps(dict(skipped))} "
            f"(unmapped labels: {sorted(unmapped)[:10]}). Check the label map."
        )

    with (output / "metadata.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_id", "label", "fitzpatrick_type", "source"])
        writer.writeheader()
        for row in rows_out:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    report = {
        "source": args.source or source_csv.stem,
        "input": str(source_csv),
        "label_map": str(args.label_map),
        "rows_in": rows_in,
        "rows_out": len(rows_out),
        "skipped": dict(skipped),
        "unmapped_labels": sorted(unmapped),
        "missing_images": missing[:50],
        "class_counts": dict(class_counts),
        "fitzpatrick_counts": {str(k): v for k, v in sorted(fitz_counts.items())},
        "notes": [
            "fitzpatrick_type 0 means 'unknown in the source', not an imputed value.",
            "Every input row appears here as converted or skipped.",
        ],
    }
    (output / "conversion_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                   encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert an external dataset into Derma-AI format")
    parser.add_argument("--input", required=True, help="source metadata CSV")
    parser.add_argument("--images-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--label-map", required=True,
                        help=f"JSON label map; shipped maps in {LABEL_MAP_DIR}")
    parser.add_argument("--source", default=None, help="name recorded in the output CSV")
    parser.add_argument("--image-column", default="image_id")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--fitz-column", default="fitzpatrick_type")
    parser.add_argument("--source-template", default=None,
                        help="optional preset name (scin|ddi|fitzpatrick17k) to print the "
                             "documented column assumptions and exit")
    args = parser.parse_args(argv)

    if args.source_template:
        presets = {
            "scin": {"image-column": "image_path", "label-column": "dermatologist_label_1",
                     "fitz-column": "eFST", "label-map": str(LABEL_MAP_DIR / "scin.json")},
            "ddi": {"image-column": "image_id", "label-column": "label",
                    "fitz-column": "fitzpatrick", "label-map": str(LABEL_MAP_DIR / "ddi.json")},
            "fitzpatrick17k": {"image-column": "md5hash", "label-column": "label",
                               "fitz-column": "fitzpatrick_scale",
                               "label-map": str(LABEL_MAP_DIR / "fitzpatrick17k.json")},
        }
        if args.source_template not in presets:
            raise SystemExit(f"unknown preset; choose from {sorted(presets)}")
        print(json.dumps(presets[args.source_template], indent=2))
        return 0

    report = convert(args)
    print(f"converted {report['rows_out']}/{report['rows_in']} rows -> {args.output}")
    print(f"  classes: {report['class_counts']}")
    print(f"  fitzpatrick: {report['fitzpatrick_counts']}")
    if report["skipped"]:
        print(f"  skipped: {report['skipped']}")
    if report["unmapped_labels"]:
        print(f"  unmapped (add to the label map if intended): {report['unmapped_labels'][:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
