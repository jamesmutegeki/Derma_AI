"""S4-4 -- training produces a checkpoint that can be frozen, and nothing else.

Gate S1-1 needs a real, hash-verified model. `scripts/train_model.py` is the
producer. These tests pin the properties that make the gate meaningful:

* lesion/patient groups never straddle the split (HAM10000 has several images
  per lesion; leaking them inflates every metric);
* a skin-tone group with no test samples is *absent*, not a zero;
* a `--smoke` run trains a checkpoint but its report is `valid: false` and it
  **refuses to freeze**, leaving the manifest untouched.

The end-to-end tests train a handful of synthetic 64px images for one epoch, so
they exercise the real model and the real report, but they claim nothing.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]


def _train_module():
    spec = importlib.util.spec_from_file_location(
        "train_model_under_test", APP_DIR / "scripts" / "train_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def train_module():
    return _train_module()


# --------------------------------------------------------------------------
# Split integrity
# --------------------------------------------------------------------------

def test_groups_never_straddle_the_split(train_module):
    rows = []
    for group in range(15):
        for image in range(3):
            rows.append({
                "image_id": f"g{group}_{image}",
                "label": ["benign", "melanoma", "kaposi_sarcoma"][group % 3],
                "fitzpatrick_type": str(1 + group % 6),
                "group_id": f"lesion_{group}",
            })
    train_idx, val_idx = train_module.plan_split(rows, seed=7)
    train_groups = {rows[i]["group_id"] for i in train_idx}
    val_groups = {rows[i]["group_id"] for i in val_idx}
    assert train_groups and val_groups
    assert not (train_groups & val_groups), "a lesion leaked across the split"
    assert len(train_idx) + len(val_idx) == len(rows)


def test_partial_group_ids_are_refused(train_module):
    rows = [
        {"image_id": "a", "label": "benign", "fitzpatrick_type": "2", "group_id": "L1"},
        {"image_id": "b", "label": "benign", "fitzpatrick_type": "2", "group_id": ""},
    ]
    with pytest.raises(SystemExit):
        train_module.plan_split(rows, seed=1)


def test_split_is_deterministic(train_module):
    rows = [{"image_id": str(i), "label": ["benign", "melanoma"][i % 2],
             "fitzpatrick_type": "3", "group_id": f"g{i}"} for i in range(20)]
    assert train_module.plan_split(rows, seed=5) == train_module.plan_split(rows, seed=5)


# --------------------------------------------------------------------------
# Metrics honesty
# --------------------------------------------------------------------------

def test_skin_type_groups_without_samples_are_absent(train_module):
    rows = [
        {"fitzpatrick_type": "5"}, {"fitzpatrick_type": "5"}, {"fitzpatrick_type": "6"},
    ]
    metrics = train_module.compute_metrics(rows, [0, 1, 2], [0, 0, 2])
    assert set(metrics["per_skin_type"]) == {"5", "6"}
    assert "1" not in metrics["per_skin_type"]
    assert metrics["per_skin_type"]["5"]["n"] == 2


def test_unknown_skin_type_is_its_own_bucket(train_module):
    rows = [{"fitzpatrick_type": "0"}]
    metrics = train_module.compute_metrics(rows, [0], [0])
    assert metrics["per_skin_type"]["0"]["known_skin_type"] is False
    assert metrics["per_skin_type"]["0"]["accuracy"] == 1.0


def test_absent_class_metrics_are_null_not_zero(train_module):
    rows = [{"fitzpatrick_type": "3"}]
    metrics = train_module.compute_metrics(rows, [0], [0])
    assert metrics["per_class"]["melanoma"]["f1"] is None
    assert metrics["per_class"]["melanoma"]["support"] == 0
    assert metrics["macro_f1"] == 1.0  # only the class that exists counts


# --------------------------------------------------------------------------
# End to end: train, then refuse to freeze a smoke run
# --------------------------------------------------------------------------

@pytest.fixture()
def tiny_dataset(tmp_path):
    from PIL import Image

    data = tmp_path / "data"
    (data / "images").mkdir(parents=True)
    rows = []
    for index in range(12):
        label = "benign" if index % 2 else "melanoma"
        image_id = f"img{index:02d}"
        colour = (150, 110, 90) if label == "benign" else (60, 40, 35)
        Image.new("RGB", (64, 64), colour).save(data / "images" / f"{image_id}.jpg")
        rows.append({"image_id": image_id, "label": label,
                     "fitzpatrick_type": str(4 + index % 2),
                     "group_id": f"lesion{index}"})
    with (data / "metadata.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_id", "label",
                                                    "fitzpatrick_type", "group_id"])
        writer.writeheader()
        writer.writerows(rows)
    return data


def _run(*args):
    return subprocess.run(
        [sys.executable, str(APP_DIR / "scripts" / "train_model.py"), *args],
        capture_output=True, text=True, timeout=900,
    )


def test_smoke_run_trains_but_reports_invalid(tiny_dataset, tmp_path):
    out = tmp_path / "run"
    result = _run(
        "--data-dir", str(tiny_dataset), "--out", str(out), "--smoke",
        "--epochs", "1", "--img-size", "64", "--batch-size", "6",
        "--no-pretrained", "--cpu", "--dataset", "synthetic-fixture",
        "--allow-untrained-classes",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / "report.json").read_text())
    assert report["valid"] is False
    assert report["smoke"] is True
    assert (out / "checkpoints" / "model.pt").is_file()
    assert report["provenance"]["n_train"] > 0
    assert report["provenance"]["n_val"] > 0
    # Provenance is recorded, and unavailable facts stay null rather than invented.
    assert report["provenance"]["img_size"] == 64
    assert report["provenance"]["dataset"] == "synthetic-fixture"


def test_smoke_run_cannot_be_frozen(tiny_dataset, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text((APP_DIR / "model_manifest.json").read_text())
    before = manifest.read_text()

    out = tmp_path / "run2"
    result = _run(
        "--data-dir", str(tiny_dataset), "--out", str(out), "--smoke", "--freeze",
        "--epochs", "1", "--img-size", "64", "--batch-size", "6",
        "--no-pretrained", "--cpu", "--manifest", str(manifest),
        "--allow-untrained-classes",
    )
    assert result.returncode != 0
    assert "refus" in (result.stdout + result.stderr).lower()
    assert manifest.read_text() == before, "a smoke run must not touch the manifest"
    status = json.loads(before)["status"]
    assert status == "placeholder"

def test_training_refuses_a_class_with_no_examples(tiny_dataset, tmp_path):
    """HAM10000 cannot train `kaposi_sarcoma`, so a three-class run must stop and
    say so rather than emit a checkpoint whose third class is an artefact."""
    result = _run(
        "--data-dir", str(tiny_dataset), "--out", str(tmp_path / "run3"), "--smoke",
        "--epochs", "1", "--img-size", "64", "--batch-size", "6",
        "--no-pretrained", "--cpu",
    )
    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    assert "kaposi_sarcoma" in output
    assert "no training examples" in output
    assert not (tmp_path / "run3" / "checkpoints" / "model.pt").exists()


def test_untrained_class_is_recorded_when_explicitly_allowed(tiny_dataset, tmp_path):
    out = tmp_path / "run4"
    result = _run(
        "--data-dir", str(tiny_dataset), "--out", str(out), "--smoke",
        "--epochs", "1", "--img-size", "64", "--batch-size", "6",
        "--no-pretrained", "--cpu", "--allow-untrained-classes",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / "report.json").read_text())
    assert report["untrained_classes"] == ["kaposi_sarcoma"]
    assert report["metrics"]["per_class"]["kaposi_sarcoma"]["support"] == 0
    assert report["metrics"]["per_class"]["kaposi_sarcoma"]["recall"] is None
