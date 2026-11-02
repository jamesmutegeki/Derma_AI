"""S5-4 -- a local corpus is checked before it is trusted.

When the data arrives (a GitHub release, a laptop copy, a Colab download) three
things must happen before a single gradient step:

1. the copy is *complete* -- 10,015 images and 10,015 metadata rows, every row
   joined to a file and every file joined to a row;
2. `lesion_id` is present, because several images of one lesion across the split
   inflate every metric that touches them;
3. the class distribution matches the published release, so a mis-typed label
   map or a half-unzipped archive is caught here rather than in the results.

`scripts/verify_ham10000.py` does that; `prepare_dataset.py --link hardlink`
avoids duplicating 2.7 GB while converting.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _make_corpus(root: Path, rows, images=(), metadata_extra=()):
    from PIL import Image

    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for name in images:
        Image.new("RGB", (16, 16), (120, 90, 70)).save(images_dir / f"{name}.jpg")

    metadata = root / "HAM10000_metadata.csv"
    with metadata.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["lesion_id", "image_id", "dx", *metadata_extra])
        writer.writeheader()
        writer.writerows(rows)
    return images_dir, metadata


def _run(app_dir, *args):
    return subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "verify_ham10000.py"), *args],
        capture_output=True, text=True, timeout=300,
    )


@pytest.fixture()
def small_corpus(tmp_path):
    rows = [
        {"lesion_id": "L1", "image_id": "ISIC_1", "dx": "nv"},
        {"lesion_id": "L1", "image_id": "ISIC_2", "dx": "nv"},
        {"lesion_id": "L2", "image_id": "ISIC_3", "dx": "mel"},
    ]
    images_dir, metadata = _make_corpus(
        tmp_path, rows, images=("ISIC_1", "ISIC_2", "ISIC_3"))
    return images_dir, metadata, tmp_path


def test_a_complete_small_corpus_passes(app_dir, small_corpus):
    images_dir, metadata, tmp = small_corpus
    out = tmp / "verification.json"
    result = _run(app_dir, "--images-dir", str(images_dir), "--metadata", str(metadata),
                  "--expected-total", "3", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert report["ok"] is True
    assert report["image_files"] == 3
    assert report["class_counts"] == {"mel": 1, "nv": 2}
    assert report["lesions"] == 2
    assert report["mapped_classes"]["benign (nv+bkl+df)"] == 2
    assert report["mapped_classes"]["kaposi_sarcoma"] == 0


def test_a_missing_image_is_a_hard_failure(app_dir, small_corpus):
    images_dir, metadata, tmp = small_corpus
    (images_dir / "ISIC_2.jpg").unlink()
    result = _run(app_dir, "--images-dir", str(images_dir), "--metadata", str(metadata),
                  "--expected-total", "3")
    assert result.returncode == 3
    assert "no image file" in (result.stdout + result.stderr).lower()
    assert "do not train" in (result.stdout + result.stderr).lower()


def test_an_orphan_image_is_reported(app_dir, small_corpus):
    images_dir, metadata, tmp = small_corpus
    from PIL import Image

    Image.new("RGB", (8, 8)).save(images_dir / "ISIC_999.jpg")
    out = tmp / "v.json"
    _run(app_dir, "--images-dir", str(images_dir), "--metadata", str(metadata),
         "--expected-total", "4", "--out", str(out))
    report = json.loads(out.read_text())
    assert report["images_without_metadata"] == ["ISIC_999"]


def test_missing_lesion_id_is_refused(app_dir, tmp_path):
    from PIL import Image

    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (8, 8)).save(images / "ISIC_1.jpg")
    metadata = tmp_path / "meta.csv"
    metadata.write_text("image_id,dx\nISIC_1,nv\n", encoding="utf-8")
    result = _run(app_dir, "--images-dir", str(images), "--metadata", str(metadata),
                  "--expected-total", "1")
    assert result.returncode == 3
    assert "lesion_id" in (result.stdout + result.stderr)


def test_class_drift_beyond_tolerance_fails(app_dir, tmp_path):
    from PIL import Image

    images = tmp_path / "images"
    images.mkdir()
    rows = []
    for index in range(5):
        name = f"ISIC_{index}"
        Image.new("RGB", (8, 8)).save(images / f"{name}.jpg")
        rows.append({"lesion_id": f"L{index}", "image_id": name, "dx": "bkl"})
    metadata = tmp_path / "meta.csv"
    with metadata.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["lesion_id", "image_id", "dx"])
        writer.writeheader()
        writer.writerows(rows)

    # bkl is published as 1,099; five rows is a wild drift, not a rounding error.
    result = _run(app_dir, "--images-dir", str(images), "--metadata", str(metadata),
                  "--expected-total", "5", "--tolerance", "2", "--strict-classes")
    assert result.returncode == 3
    assert "bkl" in (result.stdout + result.stderr)


def test_class_reference_is_not_applied_to_a_subset(app_dir, small_corpus):
    """Five images are not a claim about the published distribution."""
    images_dir, metadata, tmp = small_corpus
    out = tmp / "subset.json"
    result = _run(app_dir, "--images-dir", str(images_dir), "--metadata", str(metadata),
                  "--expected-total", "3", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(out.read_text())["class_reference_applied"] is False


def test_hardlink_conversion_does_not_duplicate_the_corpus(app_dir, small_corpus):
    images_dir, metadata, tmp = small_corpus
    label_map = tmp / "map.json"
    label_map.write_text(json.dumps({"nv": "benign", "mel": "melanoma"}), encoding="utf-8")
    out = tmp / "converted"
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "prepare_dataset.py"),
         "--input", str(metadata), "--images-root", str(images_dir),
         "--image-column", "image_id", "--label-column", "dx", "--fitz-column", "",
         "--label-map", str(label_map), "--group-column", "lesion_id",
         "--link", "hardlink", "--output", str(out), "--source", "HAM10000"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    source = images_dir / "ISIC_1.jpg"
    placed = out / "images" / "ISIC_1.jpg"
    assert placed.is_file()
    assert os.stat(placed).st_ino == os.stat(source).st_ino, "hardlink was not used"


def test_fetch_script_is_valid_and_checks_before_downloading(app_dir):
    script = app_dir / "scripts" / "fetch_and_verify_ham10000.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")
    assert "gh release download" in text
    assert "verify_ham10000.py" in text
    assert "--link hardlink" in text
    assert "CC BY-NC 4.0" in text, "the licence has to travel with the mirror"

    result = subprocess.run(["bash", str(script), "--check"],
                            capture_output=True, text=True, timeout=120,
                            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"})
    assert result.returncode == 0
    assert "check only" in (result.stdout + result.stderr).lower()
    assert "download release" not in (result.stdout + result.stderr).lower()
