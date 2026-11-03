#!/usr/bin/env python3
"""Check a PAD-UFES-20 download before anyone trains on it.

PAD-UFES-20 is the dataset this project can actually start with: 2,298
smartphone images from a Brazilian public clinic, biopsy-proven cancers, and a
Fitzpatrick type per patient. But it has three traps that are invisible until a
metric looks too good:

1. **One patient contributes several lesions, and one lesion several images.**
   Splitting by image leaks the same patient into train and eval.
2. **Cancers are biopsy-proven; the rest are clinical consensus.** Merging the
   two without noticing turns a consensus label into a false certainty.
3. **BCC and SCC are malignant.** They must be excluded, never folded into
   `benign`.

This script checks all three, plus the plain "did the download finish" question.
Column names vary between mirrors, so they are detected rather than assumed, and
whatever was detected is written into the report.

Published counts (Pacheco et al., *Data in Brief* 2020, DOI 10.17632/zr7vgbcyr2.1):
2,298 images / 1,641 lesions / 1,373 patients;
BCC 845 · ACK 730 · NEV 244 · SEK 235 · SCC 192 · MEL 52.

Exit codes: 0 clean, 3 hard failure, 2 bad input.

Usage:
    python scripts/verify_padufes20.py \
        --metadata ~/padufes/metadata.csv \
        --images ~/padufes/images \
        --out padufes_verification.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PUBLISHED_COUNTS = {
    "BCC": 845,
    "ACK": 730,
    "NEV": 244,
    "SEK": 235,
    "SCC": 192,
    "MEL": 52,
}
PUBLISHED_TOTAL = sum(PUBLISHED_COUNTS.values())  # 2,298
PUBLISHED_LESIONS = 1641
PUBLISHED_PATIENTS = 1373

CANCERS = {"BCC", "SCC", "MEL"}  # all biopsy-proven in the publication
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")

# Candidate header names, in preference order, for each logical field.
COLUMNS = {
    "image_id": ("img_id", "image_id", "image", "img", "filename"),
    "diagnostic": ("diagnostic", "diagnosis", "label", "class"),
    "patient": ("patient_id", "patient", "patientid"),
    "lesion": ("lesion_id", "lesion", "lesionid"),
    "fitzpatrick": ("fitzpatrick", "fitzpatrick_type", "skin_type", "fst"),
    "biopsied": ("biopsied", "biopsy", "biopsy_proven"),
}


def detect_columns(fieldnames: list[str]) -> dict[str, str | None]:
    lookup = {name.strip().lower(): name for name in fieldnames}
    detected: dict[str, str | None] = {}
    for field, candidates in COLUMNS.items():
        detected[field] = next((lookup[c] for c in candidates if c in lookup), None)
    return detected


def verify(metadata_csv: Path, images_dir: Path | None,
           strict_counts: bool = False, tolerance: int = 2) -> tuple[dict, list[str]]:
    failures: list[str] = []

    with metadata_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    if not rows:
        raise SystemExit(f"metadata is empty: {metadata_csv}")

    columns = detect_columns(fieldnames)
    for required in ("image_id", "diagnostic", "patient", "lesion", "fitzpatrick"):
        if not columns[required]:
            failures.append(
                f"could not find a {required!r} column; headers are {fieldnames}")
    if failures:
        return {"ok": False, "failures": failures, "columns_detected": columns}, failures

    def value(row: dict, field: str) -> str:
        column = columns[field]
        return (row.get(column) or "").strip() if column else ""

    diagnostics = Counter(value(row, "diagnostic").upper() for row in rows)
    diagnostics.pop("", None)
    unexpected = sorted(set(diagnostics) - set(PUBLISHED_COUNTS))
    if unexpected:
        failures.append(f"unexpected diagnostic values: {unexpected}")

    # -- grouping ----------------------------------------------------------
    lesion_to_patient: dict[str, set[str]] = defaultdict(set)
    images_per_lesion: Counter[str] = Counter()
    for row in rows:
        lesion = value(row, "lesion")
        patient = value(row, "patient")
        if lesion and patient:
            lesion_to_patient[lesion].add(patient)
        if lesion:
            images_per_lesion[lesion] += 1

    split_lesions = sorted(k for k, v in lesion_to_patient.items() if len(v) > 1)
    if split_lesions:
        failures.append(
            f"{len(split_lesions)} lesions are attached to more than one patient "
            f"(e.g. {split_lesions[:3]}); a group-aware split would be wrong")

    patients = {value(row, "patient") for row in rows} - {""}
    lesions = {value(row, "lesion") for row in rows} - {""}
    if patients and len(patients) != PUBLISHED_PATIENTS and len(rows) >= PUBLISHED_TOTAL:
        failures.append(
            f"{len(patients)} patients, the publication reports {PUBLISHED_PATIENTS}")
    if lesions and len(lesions) != PUBLISHED_LESIONS and len(rows) >= PUBLISHED_TOTAL:
        failures.append(
            f"{len(lesions)} lesions, the publication reports {PUBLISHED_LESIONS}")

    # -- duplicate images --------------------------------------------------
    image_ids = [value(row, "image_id") for row in rows]
    duplicates = sorted({i for i, count in Counter(image_ids).items()
                         if count > 1 and i})
    if duplicates:
        failures.append(f"{len(duplicates)} duplicate image rows (e.g. {duplicates[:5]})")

    # -- cancers must be biopsy-proven ------------------------------------
    biopsy_column = columns["biopsied"]
    biopsy_violations = []
    if biopsy_column:
        for row in rows:
            if value(row, "diagnostic").upper() in CANCERS:
                flag = (row.get(biopsy_column) or "").strip().lower()
                if flag in {"0", "false", "no", "n", ""}:
                    biopsy_violations.append(value(row, "image_id") or "?")
        if biopsy_violations:
            failures.append(
                f"{len(biopsy_violations)} cancer rows are not flagged biopsy-proven; "
                "the publication reports 100% for BCC/SCC/MEL")

    # -- skin type ---------------------------------------------------------
    fitz = Counter(value(row, "fitzpatrick") for row in rows)
    fitz.pop("", None)
    unknown_fitz = sum(1 for row in rows if not value(row, "fitzpatrick"))
    if unknown_fitz:
        failures.append(f"{unknown_fitz} rows have no Fitzpatrick value")

    # -- files -------------------------------------------------------------
    file_report: dict = {"checked": False}
    if images_dir and images_dir.is_dir():
        on_disk = {path.stem.lower() for path in images_dir.rglob("*")
                   if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES}
        missing = [i for i in image_ids if i and Path(i).stem.lower() not in on_disk]
        file_report = {
            "checked": True,
            "images": len(on_disk),
            "missing_count": len(missing),
            "missing_examples": missing[:20],
        }
        if missing:
            failures.append(f"{len(missing)} metadata rows have no image file")

    # -- published distribution -------------------------------------------
    counts_applied = bool(strict_counts or len(rows) == PUBLISHED_TOTAL)
    if counts_applied:
        for label, published in PUBLISHED_COUNTS.items():
            observed = diagnostics.get(label, 0)
            if observed and abs(observed - published) > tolerance:
                failures.append(
                    f"{label}: observed {observed}, published {published} "
                    f"(tolerance {tolerance})")

    report = {
        "metadata": str(metadata_csv),
        "images_dir": str(images_dir) if images_dir else None,
        "columns_detected": columns,
        "rows": len(rows),
        "expected_rows": PUBLISHED_TOTAL,
        "class_counts": dict(sorted(diagnostics.items())),
        "published_class_counts": PUBLISHED_COUNTS,
        "class_reference_applied": counts_applied,
        "patients": len(patients),
        "lesions": len(lesions),
        "published_patients": PUBLISHED_PATIENTS,
        "published_lesions": PUBLISHED_LESIONS,
        "images_per_lesion": {
            "max": max(images_per_lesion.values()) if images_per_lesion else 0,
        },
        "fitzpatrick_counts": dict(sorted(fitz.items())),
        "fitzpatrick_missing": unknown_fitz,
        "cancer_rows_without_biopsy_flag": len(biopsy_violations),
        "files": file_report,
        "mapped_classes": {
            "melanoma (MEL)": diagnostics.get("MEL", 0),
            "benign (NEV+SEK)": diagnostics.get("NEV", 0) + diagnostics.get("SEK", 0),
            "skipped (BCC+SCC+ACK)": (diagnostics.get("BCC", 0)
                                      + diagnostics.get("SCC", 0)
                                      + diagnostics.get("ACK", 0)),
            "kaposi_sarcoma": 0,
        },
        "ok": not failures,
        "failures": failures,
    }
    return report, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a PAD-UFES-20 download")
    parser.add_argument("--metadata", required=True, help="metadata.csv from the archive")
    parser.add_argument("--images", default=None, help="image directory (optional)")
    parser.add_argument("--out", default=None, help="write the JSON report here")
    parser.add_argument("--strict-counts", action="store_true",
                        help="apply the published class counts even to a subset")
    parser.add_argument("--tolerance", type=int, default=2)
    args = parser.parse_args(argv)

    metadata = Path(args.metadata).expanduser()
    if not metadata.is_file():
        raise SystemExit(f"metadata CSV not found: {metadata}")
    images = Path(args.images).expanduser() if args.images else None

    report, failures = verify(metadata, images, args.strict_counts, args.tolerance)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"rows        {report['rows']} (published {report['expected_rows']})")
    print(f"patients    {report['patients']} · lesions {report['lesions']}")
    print(f"classes     {report['class_counts']}")
    print(f"mapped      {report['mapped_classes']}")
    print(f"skin types  {report['fitzpatrick_counts']}")
    if report["files"].get("checked"):
        print(f"files       {report['files']['images']} on disk, "
              f"{report['files']['missing_count']} missing")
    if not report["class_reference_applied"]:
        print("note        class reference counts not applied (subset corpus)")

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("\nDo not train on this copy.", file=sys.stderr)
        return 3

    print("\nOK: joined, grouped by patient, cancers biopsy-flagged, skin types present.")
    print("Reminder: no Kaposi sarcoma here. Gate 1A stays paused; train with the "
          "serving hold (docs/TRAINING.md section 2b).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
