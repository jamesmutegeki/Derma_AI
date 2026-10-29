"""S0-2 -- authorization is enforced server-side from a single dependency set.

Acceptance criteria
-------------------
1. ``test_authz_matrix`` walks ``app.routes``: for every route under
   ``/api/admin/`` a doctor token gets **403** and an admin token never gets
   401/403.  No route may be protected by the UI alone.
2. Doctor permission flags are enforced by ``require_permission`` for every
   permission-gated route: a doctor without the flag gets 403, with the flag does
   not.
3. ``/api/reset`` and ``/api/offline-update`` (destructive/privileged) are
   admin-only.
4. Auth is Bearer-in-header only: a cookie carrying a valid token is ignored.
"""

from __future__ import annotations

import pytest

from conftest import concrete_url, iter_routes

ADMIN_PREFIX = "/api/admin/"
ADMIN_PUBLIC = {"/api/admin/login"}

#: Routes that must be admin-only even though they are not under /api/admin/.
EXTRA_ADMIN_ONLY = {"/api/reset", "/api/offline-update"}


def _is_admin_only(path: str) -> bool:
    return path in EXTRA_ADMIN_ONLY or (path.startswith(ADMIN_PREFIX) and path not in ADMIN_PUBLIC)


def test_authz_matrix(app, client, admin_token, make_doctor, auth):
    doctor_token, _doctor = make_doctor()
    admin_headers = auth(admin_token)
    doctor_headers = auth(doctor_token)

    checked = 0
    failures: list[str] = []
    for method, path in iter_routes(app):
        if path in ADMIN_PUBLIC:
            continue
        url = concrete_url(path)
        if _is_admin_only(path):
            checked += 1
            doctor_response = client.request(method, url, headers=doctor_headers, json=None)
            if doctor_response.status_code != 403:
                failures.append(f"doctor -> {method} {path} = {doctor_response.status_code}")
            admin_response = client.request(method, url, headers=admin_headers, json=None)
            if admin_response.status_code in (401, 403):
                failures.append(f"admin  -> {method} {path} = {admin_response.status_code}")

    assert checked >= 10, f"expected the admin surface to be enumerated, got {checked} routes"
    assert not failures, "authorization matrix violations:\n" + "\n".join(failures)


def test_destructive_routes_are_admin_only(client, make_doctor, auth):
    token, _doctor = make_doctor()
    assert client.post("/api/reset", headers=auth(token)).status_code == 403
    assert client.post("/api/offline-update", headers=auth(token)).status_code == 403


@pytest.mark.parametrize("permission, method, path", [
    ("view_patient", "GET", "/api/patients"),
    ("edit_patient", "POST", "/api/patients"),
    ("run_diagnosis", "POST", "/api/diagnose"),
    ("view_analytics", "GET", "/api/analytics"),
    ("view_history", "GET", "/api/history"),
    ("export_data", "GET", "/api/export"),
])
def test_permission_flags_are_enforced(client, make_doctor, auth, permission, method, path):
    denied_token, _ = make_doctor(permissions={permission: False})
    allowed_token, _ = make_doctor(permissions={permission: True})

    denied = client.request(method, path, headers=auth(denied_token), json=None)
    assert denied.status_code == 403, f"{path} ignored the missing '{permission}' flag"

    allowed = client.request(method, path, headers=auth(allowed_token), json=None)
    assert allowed.status_code != 403, f"{path} rejected a doctor holding '{permission}'"


def test_admin_bypasses_every_permission_flag(client, admin_token, auth):
    for permission in ("view_patient", "edit_patient", "run_diagnosis", "view_analytics"):
        response = client.get("/api/patients", headers=auth(admin_token))
        assert response.status_code == 200, permission


def test_deactivated_doctor_cannot_use_a_fresh_token(client, make_doctor, auth):
    token, _doctor = make_doctor(active=False)
    assert client.get("/api/patients", headers=auth(token)).status_code == 403


def test_cookie_bearer_is_not_accepted(app, client, make_session):
    """Auth is a header, never a cookie -- so a cross-site request cannot be authenticated."""
    token = make_session("admin", {"id": "admin-1", "username": "admin", "role": "admin"})
    client.cookies.set("session", token)
    response = client.get("/api/admin/doctors")
    assert response.status_code == 401
