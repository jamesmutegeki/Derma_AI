"""S2-1 -- the service is operable and its logs are safe to keep.

Acceptance criteria
-------------------
1. Every response carries an ``X-Request-ID`` that is echoed from the client
   when supplied and generated otherwise.
2. Access log lines carry method, path, status, duration and request id.
3. Credentials are redacted from log records (``Bearer ...`` and bcrypt hashes).
4. ``GET /api/admin/ops/summary`` gives administrators counts for monitoring and
   contains no patient identifiers.
"""

from __future__ import annotations

import logging

import pytest

from logging_setup import RedactionFilter, redact


def test_request_id_is_echoed_and_generated(client):
    first = client.get("/api/health")
    second = client.get("/api/health")
    assert first.headers["x-request-id"]
    assert first.headers["x-request-id"] != second.headers["x-request-id"]

    echoed = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert echoed.headers["x-request-id"] == "abc123"


def test_access_log_records_the_request(client, caplog):
    caplog.set_level(logging.INFO)
    client.get("/api/health", headers={"X-Request-ID": "trace-me"})
    assert "trace-me" in caplog.text
    assert "path=/api/health" in caplog.text
    assert "duration_ms=" in caplog.text


@pytest.mark.parametrize("message,secret", [
    ("auth header Bearer abcdef123456 used", "abcdef123456"),
    ("hash $2b$12$abcdefghijklmnopqrstuv", "abcdefghijklmnopqrstuv"),
    ("Authorization: tokenvalue123", "tokenvalue123"),
])
def test_credentials_are_redacted(message, secret):
    assert secret not in redact(message)


def test_redaction_filter_masks_a_log_record(caplog):
    logger = logging.getLogger("derma.test")
    logger.addFilter(RedactionFilter())
    caplog.set_level(logging.INFO)
    logger.info("calling with Bearer supersecrettoken")
    assert "supersecrettoken" not in caplog.text
    assert "[redacted]" in caplog.text


def test_unknown_route_still_gets_a_request_id(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["x-request-id"]


def test_ops_summary_is_counts_only(client, admin_token, auth, make_doctor, patient_record):
    response = client.get("/api/admin/ops/summary", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.json()

    for key in ("patients", "cases", "doctors", "active_sessions", "audit_rows",
                "db_bytes", "model_ready", "agent_ready", "demo_mode", "server_time"):
        assert key in body, f"ops summary is missing {key}"
    assert body["patients"] >= 1
    assert body["doctors"] >= 1
    assert body["db_bytes"] > 0

    blob = str(body)
    assert patient_record["name"] not in blob
    assert patient_record["contact"] not in blob


def test_ops_summary_requires_admin(client, make_doctor, auth):
    token, _ = make_doctor()
    assert client.get("/api/admin/ops/summary", headers=auth(token)).status_code == 403


@pytest.fixture()
def patient_record(client, make_doctor, auth):
    token, _ = make_doctor()
    payload = {"name": "Ops Summary Patient", "contact": "+256 700 111 222",
               "fitz": "V", "age": "41 yrs"}
    response = client.post("/api/patients", headers=auth(token), json=payload)
    assert response.status_code == 201
    return {**payload, "id": response.json()["patient"]["id"]}
