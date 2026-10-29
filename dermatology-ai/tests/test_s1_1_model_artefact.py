"""S1-1 -- the model artefact is verifiable and documented.

Acceptance criteria
-------------------
1. `model_manifest.json` exists, validates against the expected schema, and is
   explicit that no checkpoint ships with the repository.
2. `backend.manifest_error` rejects a checkpoint whose SHA-256 differs from the
   frozen manifest, and a head whose class count differs from the manifest.
3. `Backend.initialise` refuses such a checkpoint (no ``model_ready``) instead of
   serving unattributable weights.
4. `scripts/freeze_model.py` writes a real hash, never invents provenance, and
   only takes numbers from an evaluation report file.
5. `MODEL_CARD.md` exists, carries the not-a-medical-device disclaimer, and
   quotes no accuracy figure of its own.
6. No code path constructs a DermatologyCBM for serving without a checkpoint.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REQUIRED_TOP_LEVEL = {
    "schema_version", "status", "checkpoint", "architecture",
    "preprocessing", "training", "evaluation",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture()
def manifest(app_dir):
    return json.loads((app_dir / "model_manifest.json").read_text(encoding="utf-8"))


def test_manifest_schema_and_honest_placeholder(manifest):
    assert REQUIRED_TOP_LEVEL <= set(manifest)
    assert manifest["schema_version"] == 1
    assert manifest["status"] in {"placeholder", "frozen"}

    checkpoint = manifest["checkpoint"]
    assert checkpoint["path_env"] == "MODEL_CHECKPOINT_PATH"
    if manifest["status"] == "placeholder":
        # Nothing may claim a frozen artefact that does not exist.
        assert checkpoint["sha256"] is None
    else:
        assert HEX64.match(checkpoint["sha256"]), "a frozen manifest needs a real sha256"

    arch = manifest["architecture"]
    assert arch["num_classes"] == 3
    assert arch["num_concepts"] == 7 == len(arch["concept_names"])
    assert manifest["preprocessing"]["module"] == "transforms.build_transform"


def test_manifest_rejects_a_different_checkpoint(tmp_path, manifest):
    from backend import manifest_error

    frozen = json.loads(json.dumps(manifest))
    frozen["checkpoint"]["sha256"] = "a" * 64
    frozen["status"] = "frozen"

    problem = manifest_error(frozen, "b" * 64)
    assert "hash mismatch" in problem

    assert manifest_error(frozen, "a" * 64) == ""
    assert manifest_error(None, "b" * 64) == ""  # no manifest -> nothing to check


def test_manifest_checks_class_count(manifest):
    from backend import manifest_error

    problem = manifest_error(manifest, "c" * 64, num_classes=2)
    assert "classes" in problem


def test_frozen_manifest_without_hash_is_rejected(manifest):
    from backend import manifest_error

    broken = json.loads(json.dumps(manifest))
    broken["status"] = "frozen"
    broken["checkpoint"]["sha256"] = None
    assert "no checkpoint hash" in manifest_error(broken, "d" * 64)


def test_backend_refuses_a_checkpoint_that_fails_the_manifest(tmp_path, monkeypatch, manifest):
    from backend import Backend
    from metrics_tracker import FairnessTracker
    from storage import Store

    checkpoint = tmp_path / "cbm.pt"
    checkpoint.write_bytes(b"not really a checkpoint")
    frozen = json.loads(json.dumps(manifest))
    frozen["checkpoint"]["sha256"] = "0" * 64
    frozen["status"] = "frozen"
    manifest_path = tmp_path / "model_manifest.json"
    manifest_path.write_text(json.dumps(frozen), encoding="utf-8")

    monkeypatch.setenv("MODEL_MANIFEST_PATH", str(manifest_path))
    store = Store(tmp_path / "data")
    backend = Backend(store, FairnessTracker(store), model_path=str(checkpoint))
    status = backend.initialise()

    assert status.model_ready is False
    assert "hash mismatch" in status.reason
    store.close()


def test_freeze_script_writes_a_real_hash(tmp_path, app_dir):
    import subprocess
    import sys

    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"pretend weights")
    out = tmp_path / "manifest.json"
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    written = json.loads(out.read_text())
    import hashlib
    expected = hashlib.sha256(b"pretend weights").hexdigest()
    assert written["checkpoint"]["sha256"] == expected
    assert written["checkpoint"]["bytes"] == len(b"pretend weights")
    # No provenance supplied -> placeholder, and it says so.
    assert written["status"] == "placeholder"
    assert "must not be cited" in written["note"]


def test_freeze_script_marks_complete_provenance_frozen(tmp_path, app_dir):
    import subprocess
    import sys

    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"weights")
    report = tmp_path / "eval.json"
    report.write_text(json.dumps({"valid": True, "clinical_accuracy": 0.5, "n": 10}))
    out = tmp_path / "manifest.json"
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--out", str(out),
         "--dataset", "HAM10000", "--split", "80/20", "--seed", "42",
         "--epochs", "3", "--git-commit", "deadbeef",
         "--metrics-report", str(report)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(out.read_text())
    assert written["status"] == "frozen"
    assert written["evaluation"]["metrics"]["clinical_accuracy"] == 0.5


def test_freeze_script_refuses_a_smoke_report(tmp_path, app_dir):
    import subprocess
    import sys

    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"weights")
    report = tmp_path / "smoke.json"
    report.write_text(json.dumps({"valid": False, "smoke": True, "metrics": {"accuracy": 0.33}}))
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--out", str(tmp_path / "m.json"),
         "--metrics-report", str(report)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not marked valid=true" in result.stderr


def test_freeze_script_rejects_a_missing_report(tmp_path, app_dir):
    import subprocess
    import sys

    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"weights")
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--out", str(tmp_path / "m.json"),
         "--metrics-report", str(tmp_path / "absent.json")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "metrics report not found" in result.stderr


def test_model_card_is_honest(app_dir):
    card = (app_dir / "MODEL_CARD.md").read_text(encoding="utf-8")
    lowered = card.lower()
    assert "not a medical device" in lowered
    assert "no clinical validation" in lowered
    assert "10.71718/kqee-3z39" in card, "DDI must be cited with its DOI"
    assert "656" in card, "DDI image count must be the corrected 656"
    # The card must not quote a result of its own.
    for fake in ("84.3", "0.843", "0.027"):
        assert fake not in card


def test_serving_never_builds_an_unloaded_model(app_dir):
    backend = (app_dir / "backend.py").read_text(encoding="utf-8")
    assert "pretrained_backbone=False" in backend, \
        "the serving model must take its weights from the checkpoint, not the backbone zoo"
    assert "manifest_error" in backend

    ui = (app_dir / "ui.py").read_text(encoding="utf-8")
    assert "MODEL_CHECKPOINT_PATH" in ui or "checkpoint" in ui.lower()
    assert "torch.nn.init" not in ui


def test_ready_endpoint_reports_the_frozen_version(client):
    body = client.get("/api/ready").json()
    assert body["model_ready"] is False
    assert body["model_version"] == ""
    assert "MODEL_CHECKPOINT_PATH" in body["reason"] or body["reason"]
