#!/usr/bin/env python3
"""Check a local HAM10000 copy before anyone spends GPU time on it.

A partial or mis-joined download is the cheapest possible way to waste a GPU
hour, and the failure is silent: the training loop happily fits whatever 6,000
images it found. This script makes the join explicit.

It answers four questions, in order:

1. Is the corpus complete? (10,015 images, 10,015 metadata rows by default)
2. Does every metadata row have an image, and every image a metadata row?
3. Is `lesion_id` present, so training can split without leaking?
4. Does the class distribution match the published release?

Published HAM10000 counts (Tschandl, Rosendahl & Kittler, *Scientific Data*
5:180161, 2018): nv 6,705 · mel 1,113 · bkl 1,099 · bcc 514 · akiec 327 ·
vasc 142 · df 115.

Exit codes: 0 clean, 3 hard failure (missing files, count mismatch), 2 bad input.

Usage:
    python scripts/verify_ham10000.py \
        --images-dir ~/ham10000/images \
        --metadata ~/ham10000/HAM10000_metadata.csv \
        --out ham10000_verification.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

PUBLISHED_COUNTS = {
    "nv": 6705,
    "mel": 1113,
    "bkl": 1099,
    "bcc": 514,
    "akiec": 327,
    "vasc": 142,
    "df": 115,
}
PUBLISHED_TOTAL = sum(PUBLISHED_COUNTS.values())  # 10,015
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def scan_images(images_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in images_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            found[path.stem] = path
    return found


def verify(images_dir: Path, metadata_csv: Path, expected_total: int,
           tolerance: int, strict_classes: bool = False) -> tuple[dict, list[str]]:
    failures: list[str] = []

    with metadata_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"metadata is empty: {metadata_csv}")

    columns = set(rows[0])
    for required in ("image_id", "dx", "lesion_id"):
        if required not in columns:
            failures.append(f"metadata is missing the {required!r} column; found {sorted(columns)}")

    image_files = scan_images(images_dir)
    metadata_ids = {row.get("image_id", "").strip() for row in rows}
    metadata_ids.discard("")

    missing_files = sorted(metadata_ids - set(image_files))
    orphan_files = sorted(set(image_files) - metadata_ids)

    if len(rows) != expected_total:
        failures.append(
            f"metadata has {len(rows)} rows, the published release has {expected_total}")
    if len(image_files) != expected_total:
        failures.append(
            f"found {len(image_files)} images, the published release has {expected_total}")
    if missing_files:
        failures.append(f"{len(missing_files)} metadata rows have no image file")

    images_by_lesion = Counter()
    for row in rows:
        lesion = (row.get("lesion_id") or "").strip()
        if lesion:
            images_by_lesion[lesion] += 1
    if not images_by_lesion:
        failures.append("no lesion_id values: a group-aware split is impossible")

    class_counts = Counter((row.get("dx") or "").strip() for row in rows)
    class_counts.pop("", None)
    unexpected = sorted(set(class_counts) - set(PUBLISHED_COUNTS))
    if unexpected:
        failures.append(f"unexpected dx labels: {unexpected}")
    # The published counts are a fingerprint of the *whole* release. On a subset
    # they mean nothing, so they are only applied to a full corpus -- or when
    # --strict-classes asks for it explicitly.
    class_reference_applied = bool(strict_classes or len(rows) == PUBLISHED_TOTAL)
    if class_reference_applied:
        for label, published in PUBLISHED_COUNTS.items():
            observed = class_counts.get(label, 0)
            if observed and abs(observed - published) > tolerance:
                failures.append(
                    f"dx={label}: observed {observed}, published {published} "
                    f"(tolerance {tolerance})")

    report = {
        "images_dir": str(images_dir),
        "metadata": str(metadata_csv),
        "metadata_rows": len(rows),
        "image_files": len(image_files),
        "expected_total": expected_total,
        "missing_image_files": missing_files[:50],
        "missing_image_file_count": len(missing_files),
        "images_without_metadata": orphan_files[:50],
        "images_without_metadata_count": len(orphan_files),
        "class_counts": dict(sorted(class_counts.items())),
        "published_class_counts": PUBLISHED_COUNTS,
        "class_reference_applied": class_reference_applied,
        "lesions": len(images_by_lesion),
        "images_per_lesion": {
            "max": max(images_by_lesion.values()) if images_by_lesion else 0,
            "mean": round(sum(images_by_lesion.values()) / len(images_by_lesion), 2)
            if images_by_lesion else 0,
        },
        "mapped_classes": {
            "benign (nv+bkl+df)": sum(class_counts.get(k, 0) for k in ("nv", "bkl", "df")),
            "melanoma (mel)": class_counts.get("mel", 0),
            "kaposi_sarcoma": 0,
            "skipped (bcc+akiec+vasc)": sum(class_counts.get(k, 0) for k in ("bcc", "akiec", "vasc")),
        },
        "ok": not failures,
        "failures": failures,
    }
    return report, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a local HAM10000 copy")
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--out", default=None, help="write the report here (JSON)")
    parser.add_argument("--expected-total", type=int, default=PUBLISHED_TOTAL)
    parser.add_argument("--strict-classes", action="store_true",
                        help="apply the published class counts even to a subset")
    parser.add_argument("--tolerance", type=int, default=2,
                        help="allowed drift per class against the published counts")
    args = parser.parse_args(argv)

    images_dir = Path(args.images_dir).expanduser()
    metadata = Path(args.metadata).expanduser()
    if not images_dir.is_dir():
        raise SystemExit(f"images directory not found: {images_dir}")
    if not metadata.is_file():
        raise SystemExit(f"metadata CSV not found: {metadata}")

    report, failures = verify(images_dir, metadata, args.expected_total, args.tolerance,
                              strict_classes=args.strict_classes)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"images      {report['image_files']} (expected {report['expected_total']})")
    print(f"metadata    {report['metadata_rows']} rows")
    print(f"classes     {report['class_counts']}")
    print(f"mapped      {report['mapped_classes']}")
    print(f"lesions     {report['lesions']} (max {report['images_per_lesion']['max']} images each)")
    if report["missing_image_file_count"]:
        print(f"missing     {report['missing_image_file_count']} files, e.g. "
              f"{report['missing_image_files'][:5]}")
    if report["images_without_metadata_count"]:
        print(f"orphans     {report['images_without_metadata_count']} images with no row, e.g. "
              f"{report['images_without_metadata'][:5]}")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("\nDo not train on this copy.", file=sys.stderr)
        return 3

    print("\nOK: the corpus is complete, joined, and grouped.")
    print("Note: HAM10000 has no kaposi_sarcoma images. Gate 1A stays paused; "
          "train with the serving hold (docs/TRAINING.md section 2b).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
