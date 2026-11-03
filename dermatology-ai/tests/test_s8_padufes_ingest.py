"""S8 -- the "start today" dataset is checked, not just recommended.

PAD-UFES-20 is the corpus this project can begin with, so the same discipline
that guards HAM10000 has to guard it:

* one patient -> many lesions -> many images, so the split must group by patient
  and the verifier must prove the lesion/patient join is consistent;
* cancers are biopsy-proven, benign classes are consensus -- a row that claims a
  cancer without the biopsy flag is a provenance failure;
* BCC and SCC are malignant and must be *excluded*, not folded into `benign`;
* a subset is not a distribution, so published counts apply only to a full copy.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

HEADERS = ["patient_id", "lesion_id", "img_id", "diagnostic", "fitzpatrick", "biopsied"]


def _write_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture()
def pad(tmp_path):
    from PIL import Image

    images = tmp_path / "images"
    images.mkdir()
    rows = []
    # Two patients, three lesions, four images: the real topology.
    layout = [
        ("P1", "L1", "img1", "MEL", "3", "1"),
        ("P1", "L1", "img2", "MEL", "3", "1"),
        ("P1", "L2", "img3", "NEV", "3", "0"),
        ("P2", "L3", "img4", "BCC", "5", "1"),
    ]
    for patient, lesion, image, diagnostic, fitz, biopsied in layout:
        rows.append({"patient_id": patient, "lesion_id": lesion, "img_id": image,
                     "diagnostic": diagnostic, "fitzpatrick": fitz, "biopsied": biopsied})
        Image.new("RGB", (24, 24), (150, 110, 90)).save(images / f"{image}.png")
    metadata = _write_csv(tmp_path / "metadata.csv", rows)
    return {"metadata": metadata, "images": images, "rows": rows, "tmp": tmp_path}


def _run(app_dir, *args):
    return subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "verify_padufes20.py"), *args],
        capture_output=True, text=True, timeout=300,
    )


def test_a_clean_copy_passes(app_dir, pad):
    out = pad["tmp"] / "v.json"
    result = _run(app_dir, "--metadata", str(pad["metadata"]),
                  "--images", str(pad["images"]), "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(out.read_text())
    assert report["ok"] is True
    assert report["rows"] == 4
    assert report["patients"] == 2
    assert report["lesions"] == 3
    assert report["class_counts"] == {"BCC": 1, "MEL": 2, "NEV": 1}
    assert report["mapped_classes"]["melanoma (MEL)"] == 2
    assert report["mapped_classes"]["benign (NEV+SEK)"] == 1
    assert report["mapped_classes"]["skipped (BCC+SCC+ACK)"] == 1
    # A subset must not be judged against the published distribution.
    assert report["class_reference_applied"] is False


def test_column_names_are_detected_not_assumed(app_dir, tmp_path):
    from PIL import Image

    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (8, 8)).save(images / "a.png")
    metadata = tmp_path / "meta.csv"
    metadata.write_text(
        "patient,lesion,image_id,diagnosis,skin_type,biopsy\n"
        "P1,L1,a.png,NEV,2,0\n", encoding="utf-8")
    out = tmp_path / "v.json"
    result = _run(app_dir, "--metadata", str(metadata), "--images", str(images),
                  "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    columns = json.loads(out.read_text())["columns_detected"]
    assert columns["image_id"] == "image_id"
    assert columns["diagnostic"] == "diagnosis"
    assert columns["fitzpatrick"] == "skin_type"


def test_a_cancer_without_a_biopsy_flag_is_a_failure(app_dir, pad):
    rows = [dict(row) for row in pad["rows"]]
    rows[0]["biopsied"] = "0"  # MEL claimed without pathological proof
    metadata = _write_csv(pad["tmp"] / "bad.csv", rows)
    result = _run(app_dir, "--metadata", str(metadata), "--images", str(pad["images"]))
    assert result.returncode == 3
    assert "biopsy" in (result.stdout + result.stderr).lower()


def test_a_lesion_attached_to_two_patients_is_a_failure(app_dir, pad):
    rows = [dict(row) for row in pad["rows"]]
    rows[3]["lesion_id"] = "L1"  # P2 now shares P1's lesion
    metadata = _write_csv(pad["tmp"] / "split.csv", rows)
    result = _run(app_dir, "--metadata", str(metadata))
    assert result.returncode == 3
    assert "more than one patient" in (result.stdout + result.stderr)


def test_missing_images_are_a_failure(app_dir, pad):
    (pad["images"] / "img3.png").unlink()
    result = _run(app_dir, "--metadata", str(pad["metadata"]),
                  "--images", str(pad["images"]))
    assert result.returncode == 3
    assert "no image file" in (result.stdout + result.stderr).lower()


def test_missing_skin_type_is_a_failure(app_dir, pad):
    rows = [dict(row) for row in pad["rows"]]
    rows[1]["fitzpatrick"] = ""
    metadata = _write_csv(pad["tmp"] / "nofitz.csv", rows)
    result = _run(app_dir, "--metadata", str(metadata))
    assert result.returncode == 3
    assert "fitzpatrick" in (result.stdout + result.stderr).lower()


def test_published_counts_apply_only_when_asked(app_dir, pad):
    result = _run(app_dir, "--metadata", str(pad["metadata"]), "--strict-counts")
    assert result.returncode == 3
    assert "published" in (result.stdout + result.stderr).lower()


def test_conversion_excludes_the_malignant_classes(app_dir, pad):
    label_map = app_dir / "scripts" / "label_maps" / "padufes20.json"
    out = pad["tmp"] / "converted"
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "prepare_dataset.py"),
         "--input", str(pad["metadata"]), "--images-root", str(pad["images"]),
         "--image-column", "img_id", "--label-column", "diagnostic",
         "--fitz-column", "fitzpatrick", "--label-map", str(label_map),
         "--group-column", "patient_id", "--link", "hardlink",
         "--output", str(out), "--source", "PAD-UFES-20"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = list(csv.DictReader((out / "metadata.csv").open()))
    labels = {row["image_id"]: row["label"] for row in rows}
    assert labels["img1"] == "melanoma"
    assert labels["img3"] == "benign"
    assert "img4" not in labels, "BCC must be excluded, not mapped to benign"
    # P2's only image is a BCC, which is excluded -- so the converted set is P1.
    # The group id still comes from the *patient*, not the lesion.
    assert {row["group_id"] for row in rows} == {"P1"}
    assert all(row["fitzpatrick_type"] in {"3", "5"} for row in rows)


def test_fetch_script_checks_before_downloading(app_dir):
    script = app_dir / "scripts" / "fetch_padufes20.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text(encoding="utf-8")
    assert "CC BY 4.0" in text
    assert "verify_padufes20.py" in text
    assert "--link hardlink" in text
    assert "--hold" not in text or "serving hold" in text

    result = subprocess.run(["bash", str(script), "--check"],
                            capture_output=True, text=True, timeout=120,
                            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp"})
    assert result.returncode == 0
    assert "check only" in (result.stdout + result.stderr).lower()
