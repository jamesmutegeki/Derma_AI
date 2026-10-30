"""S4-2 -- the PASSION helper must not invent a dataset.

The old `scripts/download_passion.py` described twelve classes (nevus,
seborrhoeic keratosis, melanoma, Kaposi sarcoma, BCC, SCC, ...) that PASSION
does not contain -- the published cohort is four paediatric conditions -- and it
silently defaulted a missing Fitzpatrick value to `3`. This test pins the
rewrite: the script carries no label map of its own, refuses to invent a skin
type, and delegates conversion to `scripts/prepare_dataset.py`.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

FABRICATED_CLASSES = (
    "nevus",
    "seborrheic_keratosis",
    "seborrhoeic",
    "lentigo",
    "dermatofibroma",
    "vascular_lesion",
    "basal_cell_carcinoma",
    "squamous_cell_carcinoma",
    "actinic_keratosis",
)


def _script(app_dir: Path) -> Path:
    return app_dir / "scripts" / "download_passion.py"


def _run(app_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_script(app_dir)), *args],
        capture_output=True, text=True, timeout=300,
    )


def test_script_no_longer_carries_a_invented_taxonomy(app_dir):
    text = _script(app_dir).read_text(encoding="utf-8").lower()
    # No mapping table, no exclusion list, and no invented class assigned to a
    # project class. (The docstring may *name* the old classes to explain their
    # removal; what must not exist is the mapping itself.)
    assert "class_mapping" not in text
    assert "excluded_classes" not in text
    for invented in FABRICATED_CLASSES:
        pattern = rf"{invented}[^\n]{{0,40}}(benign|melanoma|kaposi)"
        assert not re.search(pattern, text), f"{invented!r} is still mapped to a class"


def test_script_never_imputes_a_skin_type(app_dir):
    text = _script(app_dir).read_text(encoding="utf-8")
    # The old default ("Using default type 3" / assignment of 3) must be gone.
    assert "default type 3" not in text.lower()
    assert 'fitzpatrick_type"] = 3' not in text
    assert "fillna(3)" not in text
    assert "clip(1, 6)" not in text


def test_script_explains_that_access_is_the_blocker(app_dir):
    result = _run(app_dir)
    output = (result.stdout + result.stderr).lower()
    assert "passionderm" in output
    assert "access" in output
    assert result.returncode != 0


@pytest.fixture()
def archive(tmp_path):
    """A synthetic PASSION-shaped archive: four conditions, one missing FST."""
    from PIL import Image

    root = tmp_path / "archive"
    (root / "images").mkdir(parents=True)
    rows = [
        ("p1", "atopic dermatitis", "5"),
        ("p2", "scabies", "4"),
        ("p3", "impetigo", ""),
        ("p4", "dermatophytosis", "6"),
    ]
    for name, _, _ in rows:
        Image.new("RGB", (24, 24), (140, 100, 80)).save(root / "images" / f"{name}.jpg")
    with (root / "metadata.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["image_id", "label", "fitzpatrick_type"])
        writer.writerows(rows)

    path = tmp_path / "passion.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        for item in root.rglob("*"):
            if item.is_file():
                bundle.write(item, item.relative_to(root))
    return path


def test_conversion_requires_an_explicit_label_map(app_dir, archive, tmp_path):
    result = _run(app_dir, "--archive", str(archive), "--output", str(tmp_path / "out"))
    assert result.returncode != 0
    assert "label-map" in (result.stdout + result.stderr).lower()


def test_conversion_keeps_unknown_skin_types_unknown(app_dir, archive, tmp_path):
    label_map = tmp_path / "map.json"
    # The four PASSION conditions do not map onto the three-class head; a
    # deliberate mapping is required and is the caller's decision.
    label_map.write_text(json.dumps({
        "atopic dermatitis": "benign",
        "scabies": "skip",
        "impetigo": "skip",
        "dermatophytosis": "skip",
    }), encoding="utf-8")
    out = tmp_path / "out"
    result = _run(
        app_dir,
        "--archive", str(archive),
        "--label-map", str(label_map),
        "--output", str(out),
        "--source", "passion",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    rows = list(csv.DictReader((out / "metadata.csv").open()))
    assert [row["image_id"] for row in rows] == ["p1"]
    # p3 has no Fitzpatrick value in the source. It is skipped above, but the
    # rule still holds for every converted row: never invent one.
    assert all(row["fitzpatrick_type"] in {"1", "2", "3", "4", "5", "6", "0"} for row in rows)

    report = json.loads((out / "conversion_report.json").read_text())
    assert report["skipped"]["excluded_by_map"] == 3
    assert report["fitzpatrick_counts"]["5"] == 1


def test_missing_skin_type_is_reported_as_zero(app_dir, archive, tmp_path):
    label_map = tmp_path / "map.json"
    label_map.write_text(json.dumps({"impetigo": "benign"}), encoding="utf-8")
    out = tmp_path / "out2"
    result = _run(
        app_dir, "--archive", str(archive), "--label-map", str(label_map),
        "--output", str(out), "--source", "passion",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    row = next(csv.DictReader((out / "metadata.csv").open()))
    assert row["image_id"] == "p3"
    assert row["fitzpatrick_type"] == "0"  # unknown, not imputed
