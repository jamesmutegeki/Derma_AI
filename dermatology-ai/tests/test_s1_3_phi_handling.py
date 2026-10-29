"""S1-3 -- patient identifiers stay where they belong.

Acceptance criteria
-------------------
1. The audit log records *what happened to which record id*, never a patient's
   name, contact number or free-text history, and never an attempted login email.
2. CSV exports are de-identified: no name, no contact, no history; age is a
   decade band; simulated records are marked.
3. Every export is audited.
4. The web server never writes patient fields to the application log.
"""

from __future__ import annotations

import logging

import pytest

PATIENT = {
    "name": "Zawedde Nakato",
    "age": "34 yrs (DOB: 1991-03-14)",
    "gender": "female",
    "fitz": "IV",
    "contact": "+256 772 555 123",
    "history": "Three month history of a pigmented lesion on the left forearm.",
    "diagnosis": "melanoma",
    "body_site": "left_forearm",
    "status": "active",
    "visits": [],
}

FORBIDDEN_IN_AUDIT = (PATIENT["name"], PATIENT["contact"], PATIENT["history"][:24], "+256")


@pytest.fixture()
def patient(client, make_doctor, auth):
    token, _doctor = make_doctor()
    response = client.post("/api/patients", headers=auth(token), json=PATIENT)
    assert response.status_code == 201, response.text
    return response.json()["patient"]


def _all_audit_text(app) -> str:
    rows = app.state.store.list_audit(limit=500)
    return "\n".join(
        " ".join(str(row.get(key, "")) for key in ("event", "actor", "role", "detail", "outcome"))
        for row in rows
    )


def test_audit_log_holds_no_patient_identifiers(app, client, make_doctor, auth, patient):
    token, _doctor = make_doctor()
    client.get(f"/api/patients/{patient['id']}", headers=auth(token))
    client.put(f"/api/patients/{patient['id']}", headers=auth(token), json=PATIENT)
    client.get("/api/patients", headers=auth(token))

    text = _all_audit_text(app)
    assert patient["id"] in text, "the audit trail must identify the record acted on"
    for forbidden in FORBIDDEN_IN_AUDIT:
        assert forbidden not in text, f"audit log leaked {forbidden!r}"


def test_failed_login_does_not_record_the_email(app, client, make_doctor):
    _token, doctor = make_doctor(username="phi_probe")
    client.post("/api/login", json={"email": doctor["email"], "password": "wrong-password"})
    text = _all_audit_text(app)
    assert doctor["email"] not in text
    assert "login_failed" in text


def test_patient_export_is_de_identified(client, admin_token, auth, app, patient):
    response = client.get("/api/admin/patients/export", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.text

    header = body.splitlines()[0]
    assert "Name" not in header
    assert "Contact" not in header
    assert "History" not in header

    for forbidden in (PATIENT["name"], PATIENT["contact"], "+256"):
        assert forbidden not in body, f"export leaked {forbidden!r}"

    # Age is banded, the record is still identifiable by id, and it is exported.
    assert "30-39" in body
    assert patient["id"] in body

    audit = _all_audit_text(app)
    assert "export_patients" in audit
    assert "deidentified=true" in audit


def test_export_marks_simulated_records(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_MODE", "1")
    from fastapi.testclient import TestClient

    from server import create_app

    app = create_app(data_dir=tmp_path / "data", initialise_backend=False)
    with TestClient(app) as client:
        token, _ = app.state.sessions.create("admin", {"id": "admin-1", "username": "admin",
                                                       "role": "admin", "name": "Admin"})
        headers = {"Authorization": f"Bearer {token}"}
        body = client.get("/api/admin/patients/export", headers=headers).text
        assert "Simulated" in body.splitlines()[0]
        assert ",yes" in body
    app.state.store.close()


def test_server_logs_contain_no_patient_fields(client, make_doctor, auth, caplog, patient):
    caplog.set_level(logging.DEBUG)
    token, _doctor = make_doctor()
    client.get(f"/api/patients/{patient['id']}", headers=auth(token))
    client.get("/api/patients", headers=auth(token))
    for forbidden in (PATIENT["name"], PATIENT["contact"]):
        assert forbidden not in caplog.text
