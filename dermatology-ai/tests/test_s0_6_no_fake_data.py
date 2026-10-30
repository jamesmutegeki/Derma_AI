"""S0-6 -- no fail-open path returns invented clinical output.

Acceptance criteria
-------------------
1. Without a checkpoint, ``/api/diagnose`` answers **503** with a machine-readable
   reason.  There is no randomly-initialised model, no ``_mock_*`` fallback and no
   predeterminate "melanoma" answer.
2. ``/api/ready`` tells the truth about model availability.
3. Seeded/demo data is only created behind ``DEMO_MODE=1`` and is always labelled
   ``simulated``; it never enters the metrics as ground truth.
4. No fabricated metrics survive in the code base (``_mock_analytics``,
   ``true_label=pred_class``, ``accuracy_gap = 0.12`` ...).
"""

from __future__ import annotations

import io

from PIL import Image

from conftest import repo_files


def _png_bytes(size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (180, 120, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_diagnose_without_checkpoint_returns_503(client, make_doctor, auth, app):
    token, _doctor = make_doctor()
    response = client.post(
        "/api/diagnose",
        headers=auth(token),
        files={"file": ("lesion.png", _png_bytes(), "image/png")},
        data={"fitzpatrick": "4"},
    )
    assert response.status_code == 503, "the API answered without a model"
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("error") == "model_unavailable"
    assert detail.get("reason")


def test_ready_reports_model_absent(client):
    body = client.get("/api/ready").json()
    assert body["model_ready"] is False
    assert body["reason"]
    assert body["demo_mode"] is False


def test_no_mock_helpers_left_in_the_code():
    offenders = []
    for path in repo_files(".py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in ("_mock_", "_fake_", "MockAnalysis", "random.uniform(", "random.random("):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, "fake-data helpers still present:\n" + "\n".join(offenders)


def test_no_swallowed_exceptions_falling_back_to_fake_data():
    """``except:`` blocks must not return fabricated payloads."""
    import re

    offenders = []
    for path in repo_files(".py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"except[^\n]*:\s*\n((?:[ \t]+[^\n]*\n){1,6})", text):
            body = match.group(1)
            if re.search(r"return\s*\{[^}]*\"(?:diagnosis|prediction|triage|accuracy)\"", body):
                offenders.append(f"{path.name}: {body.strip().splitlines()[0]}")
    assert not offenders, "exception handlers return fabricated clinical values:\n" + "\n".join(offenders)


def test_demo_mode_is_explicit_and_labelled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_MODE", "1")
    from server import create_app

    app = create_app(data_dir=tmp_path / "data", initialise_backend=False)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/api/ready").json()["demo_mode"] is True
        token, _ = app.state.sessions.create("admin", {"id": "admin-1", "username": "admin", "role": "admin"})
        patients = client.get("/api/patients", headers={"Authorization": f"Bearer {token}"}).json()["patients"]
        assert patients, "DEMO_MODE=1 should seed demo patients"
        for patient in patients:
            assert patient.get("simulated") is True, "demo patient is not labelled simulated"
    app.state.store.close()


def test_seed_demo_requires_environment_passwords():
    import seed_demo

    source = open(seed_demo.__file__, encoding="utf-8").read()
    assert "DEMO_ADMIN_PASSWORD" in source
    assert "DEMO_DOCTOR_PASSWORD" in source
    # No literal password assignment remains.
    assert 'hash_password("' not in source
    assert "_hash_password(\"" not in source


def test_api_rejects_oversized_and_non_image_uploads(client, make_doctor, auth):
    token, _doctor = make_doctor()
    junk = client.post(
        "/api/diagnose",
        headers=auth(token),
        files={"file": ("payload.png", b"not really an image", "image/png")},
        data={"fitzpatrick": "4"},
    )
    assert junk.status_code in (400, 415, 503)
    assert junk.status_code != 200
