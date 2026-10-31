"""S5-2 -- a frozen artefact can be deliberately kept out of service.

Gate 1A was paused on 2026-10-31: the weights may be trained and frozen, but the
third class has no training data until a Kaposi sarcoma cohort is obtained, so
nothing may answer a diagnosis request. That must be enforced by the code, not
by a sentence in a document.

A manifest may therefore carry::

    "serving": {"enabled": false, "reason": "..."}

and the backend then refuses to initialise **before it touches the checkpoint**,
so `/api/ready` and `/api/diagnose` both report the hold. A manifest without the
key keeps the old behaviour (enabled), so older artefacts are unaffected.
"""

from __future__ import annotations

import io
import json

from PIL import Image

HOLD_REASON = "Kaposi sarcoma cohort pending (gate 1A paused 2026-10-31)"


def _png_bytes(size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (150, 100, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def _manifest(path, *, serving=None, sha256="0" * 64):
    manifest = {
        "schema_version": 1,
        "status": "frozen",
        "checkpoint": {"path_env": "MODEL_CHECKPOINT_PATH", "filename": "model.pt",
                       "sha256": sha256, "bytes": 1234},
        "architecture": {"name": "DermatologyCBM", "backbone": "hrnet_w18",
                         "num_classes": 3,
                         "class_names": ["benign", "melanoma", "kaposi_sarcoma"]},
        "preprocessing": {"module": "transforms.build_transform"},
        "training": {"dataset": "HAM10000", "split": "group-aware 80/20",
                     "seed": 42, "epochs": 10, "git_commit": "deadbee",
                     "date": "2026-10-31"},
        "evaluation": {"report": None, "metrics": None},
    }
    if serving is not None:
        manifest["serving"] = serving
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_serving_hold_is_honoured_before_the_checkpoint_is_opened(tmp_path, monkeypatch):
    from backend import Backend
    from metrics_tracker import FairnessTracker
    from storage import Store

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"this is not a torch checkpoint")  # never parsed
    manifest = _manifest(tmp_path / "manifest.json",
                         serving={"enabled": False, "reason": HOLD_REASON})
    monkeypatch.setenv("MODEL_MANIFEST_PATH", str(manifest))

    store = Store(tmp_path / "data")
    backend = Backend(store, FairnessTracker(store), model_path=str(checkpoint))
    status = backend.initialise()
    assert status.model_ready is False
    assert "on hold" in status.reason
    assert HOLD_REASON in status.reason


def test_manifest_without_a_serving_block_still_loads_normally(tmp_path, monkeypatch):
    """Older artefacts and the shipped placeholder carry no `serving` key."""
    from backend import Backend
    from metrics_tracker import FairnessTracker
    from storage import Store

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"definitely not weights")
    manifest = _manifest(tmp_path / "manifest.json")
    monkeypatch.setenv("MODEL_MANIFEST_PATH", str(manifest))

    store = Store(tmp_path / "data")
    backend = Backend(store, FairnessTracker(store), model_path=str(checkpoint))
    status = backend.initialise()
    # It gets past the hold check and then fails the hash check -- which is the
    # point: without a hold, the file is inspected.
    assert "on hold" not in status.reason
    assert status.model_ready is False


def test_api_reports_the_hold_rather_than_a_generic_503(tmp_path, monkeypatch):
    """`/api/ready` is public and is what an operator looks at first."""
    from fastapi.testclient import TestClient

    from server import create_app

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"not weights either")
    manifest = _manifest(tmp_path / "manifest.json",
                         serving={"enabled": False, "reason": HOLD_REASON})
    monkeypatch.setenv("MODEL_CHECKPOINT_PATH", str(checkpoint))
    monkeypatch.setenv("MODEL_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "1000/minute")

    application = create_app(data_dir=tmp_path / "data", initialise_backend=True)
    application.state.limiter.reset()
    with TestClient(application) as client:
        body = client.get("/api/ready").json()
    assert body["model_ready"] is False
    assert "on hold" in body["reason"]
    assert "Kaposi" in body["reason"]


def test_freeze_model_can_hold_a_frozen_artefact(tmp_path):
    import subprocess
    import sys

    from conftest import APP_DIR

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"weights")
    template = json.loads((APP_DIR / "model_manifest.json").read_text())
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template), encoding="utf-8")
    out = tmp_path / "manifest.json"

    result = subprocess.run(
        [sys.executable, str(APP_DIR / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--template", str(template_path),
         "--out", str(out), "--dataset", "HAM10000", "--split", "group-aware 80/20",
         "--seed", "42", "--epochs", "10", "--git-commit", "deadbee",
         "--no-serve", "--hold-reason", HOLD_REASON],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(out.read_text())
    assert written["status"] == "frozen"
    assert written["serving"] == {"enabled": False, "reason": HOLD_REASON}
    assert written["checkpoint"]["sha256"]


def test_freeze_model_defaults_to_serving(tmp_path):
    import subprocess
    import sys

    from conftest import APP_DIR

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"weights")
    template = json.loads((APP_DIR / "model_manifest.json").read_text())
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template), encoding="utf-8")
    out = tmp_path / "manifest.json"

    subprocess.run(
        [sys.executable, str(APP_DIR / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--template", str(template_path),
         "--out", str(out), "--dataset", "HAM10000", "--split", "s", "--seed", "1",
         "--epochs", "1", "--git-commit", "abc123"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    assert json.loads(out.read_text())["serving"]["enabled"] is True
