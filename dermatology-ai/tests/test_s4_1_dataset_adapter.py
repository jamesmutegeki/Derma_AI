"""S4-1 -- any external dataset can be converted into the training format.

The project needs to swap external cohorts (SCIN now, DDI/eSkinHealth when
access arrives) without editing the training code. `scripts/prepare_dataset.py`
is that seam:

* it never guesses a label mapping -- unmapped labels are reported and skipped;
* it never silently drops rows -- the report accounts for every input row;
* it refuses to emit an empty or degenerate dataset;
* the output is exactly what `datasetEquity.DermDataset` expects
  (`image_id,label,fitzpatrick_type` plus an `images/` directory), so the
  training and evaluation scripts need no change.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCIN_MAP = {
    "eczema": "benign",
    "allergic contact dermatitis": "benign",
    "melanoma": "melanoma",
    "kaposi sarcoma": "kaposi_sarcoma",
    "psoriasis": "benign",
}


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture()
def raw_dataset(tmp_path):
    images = tmp_path / "raw" / "images"
    images.mkdir(parents=True)
    from PIL import Image

    rows = [
        {"file": "c1.jpg", "dx": "melanoma", "fst": "5"},
        {"file": "c2.jpg", "dx": "eczema", "fst": "4"},
        {"file": "c3.jpg", "dx": "kaposi sarcoma", "fst": "6"},
        {"file": "c4.jpg", "dx": "unknown rare thing", "fst": "3"},  # unmapped
        {"file": "c5.jpg", "dx": "psoriasis", "fst": ""},            # no FST
    ]
    for row in rows:
        Image.new("RGB", (32, 32), (150, 110, 90)).save(images / row["file"])
    csv_path = _write_csv(tmp_path / "raw" / "raw.csv", rows, ["file", "dx", "fst"])
    label_map = tmp_path / "label_map.json"
    label_map.write_text(json.dumps(SCIN_MAP), encoding="utf-8")
    return {"csv": csv_path, "images": images, "map": label_map, "root": tmp_path}


def _run(app_dir, *args):
    return subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "prepare_dataset.py"), *args],
        capture_output=True, text=True, timeout=300,
    )


def test_converts_to_the_training_format(app_dir, raw_dataset, tmp_path):
    out = tmp_path / "out"
    result = _run(
        app_dir,
        "--input", str(raw_dataset["csv"]),
        "--images-root", str(raw_dataset["images"]),
        "--image-column", "file",
        "--label-column", "dx",
        "--fitz-column", "fst",
        "--label-map", str(raw_dataset["map"]),
        "--output", str(out),
        "--source", "scin-test",
    )
    assert result.returncode == 0, result.stderr

    metadata = list(csv.DictReader((out / "metadata.csv").open()))
    assert {row["image_id"] for row in metadata} == {"c1", "c2", "c3", "c5"}
    labels = {row["image_id"]: row["label"] for row in metadata}
    assert labels["c1"] == "melanoma"
    assert labels["c2"] == "benign"
    assert labels["c3"] == "kaposi_sarcoma"

    # The no-FST row is kept but flagged as unknown, never invented.
    fitz = {row["image_id"]: row["fitzpatrick_type"] for row in metadata}
    assert fitz["c5"] == "0"

    # Files are copied into the layout DermDataset expects.
    assert (out / "images" / "c1.jpg").is_file()
    assert list((out / "images").glob("*.jpg"))


def test_every_input_row_is_accounted_for(app_dir, raw_dataset, tmp_path):
    out = tmp_path / "out"
    assert _run(
        app_dir,
        "--input", str(raw_dataset["csv"]),
        "--images-root", str(raw_dataset["images"]),
        "--image-column", "file", "--label-column", "dx", "--fitz-column", "fst",
        "--label-map", str(raw_dataset["map"]), "--output", str(out),
        "--source", "scin-test",
    ).returncode == 0

    report = json.loads((out / "conversion_report.json").read_text())
    assert report["rows_in"] == 5
    assert report["rows_out"] == 4
    assert report["skipped"]["unmapped_label"] == 1
    assert report["unmapped_labels"] == ["unknown rare thing"]
    assert report["source"] == "scin-test"
    assert report["class_counts"]["melanoma"] == 1


def test_missing_images_are_reported_not_ignored(app_dir, raw_dataset, tmp_path):
    (raw_dataset["images"] / "c2.jpg").unlink()
    out = tmp_path / "out"
    result = _run(
        app_dir,
        "--input", str(raw_dataset["csv"]),
        "--images-root", str(raw_dataset["images"]),
        "--image-column", "file", "--label-column", "dx", "--fitz-column", "fst",
        "--label-map", str(raw_dataset["map"]), "--output", str(out),
        "--source", "scin-test",
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((out / "conversion_report.json").read_text())
    assert report["skipped"]["missing_image"] == 1
    assert "c2.jpg" in report["missing_images"]


def test_refuses_an_empty_dataset(app_dir, tmp_path):
    csv_path = _write_csv(tmp_path / "raw.csv", [{"file": "x.jpg", "dx": "zzz", "fst": "3"}],
                          ["file", "dx", "fst"])
    label_map = tmp_path / "map.json"
    label_map.write_text(json.dumps(SCIN_MAP))
    result = _run(
        app_dir,
        "--input", str(csv_path), "--images-root", str(tmp_path),
        "--image-column", "file", "--label-column", "dx", "--fitz-column", "fst",
        "--label-map", str(label_map), "--output", str(tmp_path / "out"),
    )
    assert result.returncode != 0
    assert "no rows" in (result.stdout + result.stderr).lower()


def test_label_maps_are_shipped_and_documented(app_dir):
    maps = app_dir / "scripts" / "label_maps"
    assert maps.is_dir()
    names = {path.stem for path in maps.glob("*.json")}
    assert {"scin", "ddi", "fitzpatrick17k"} <= names
    for path in maps.glob("*.json"):
        # Keys starting with "_" are documentation in the shipped maps.
        mapping = {k: v for k, v in json.loads(path.read_text()).items()
                   if not str(k).startswith("_")}
        assert mapping, f"{path.name} has no labels"
        assert set(mapping.values()) <= {"benign", "melanoma", "kaposi_sarcoma", "skip"}, path.name


def test_dataset_cards_cover_every_supported_source(app_dir):
    cards = {path.name for path in (app_dir / "docs").glob("DATASET_CARD_*.md")}
    assert "DATASET_CARD_SCIN.md" in cards
    for name in cards:
        text = (app_dir / "docs" / name).read_text(encoding="utf-8").lower()
        assert "licence" in text or "license" in text
        assert "fitzpatrick" in text
