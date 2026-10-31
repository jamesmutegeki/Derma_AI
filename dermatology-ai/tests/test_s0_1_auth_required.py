"""S0-1 -- every non-public route requires authentication.

Acceptance criteria
-------------------
1. Enumerating ``app.routes`` (never a hand-written list), every route that is not
   in :data:`tests.conftest.PUBLIC_PATHS` answers **401** without a bearer token.
2. The public allow-list only contains routes that actually exist (so it cannot
   silently rot), and it is exactly the documented surface.
3. A structurally invalid token (wrong scheme, garbage, empty) is also rejected.
4. Logging out revokes the token server-side.
"""

from __future__ import annotations

import pytest

from conftest import PUBLIC_PATHS, concrete_url, iter_routes


def _probe(client, method: str, path: str, headers: dict | None = None):
    return client.request(method, concrete_url(path), headers=headers,
                          json=None, follow_redirects=False)


def test_every_non_public_route_rejects_anonymous(app, client):
    failures = []
    for method, path in iter_routes(app):
        if path in PUBLIC_PATHS:
            continue
        response = _probe(client, method, path)
        if response.status_code != 401:
            failures.append(f"{method} {path} -> {response.status_code}")
    assert not failures, "routes reachable without authentication:\n" + "\n".join(failures)


def test_public_allowlist_matches_installed_routes(app):
    installed = {path for _method, path in iter_routes(app)}
    stale = PUBLIC_PATHS - installed
    assert not stale, f"public allow-list references routes that do not exist: {sorted(stale)}"

    # The documented public surface, spelled out so a new unprotected route is a
    # deliberate decision rather than an accident.
    expected = {
        "/", "/dashboard.js", "/robots.txt",
        "/measles_child.jpg", "/bg_vitiligo.jpg", "/bg_acne_skin.jpg",
        "/assets/{name}", "/favicon.ico",
        "/api/health", "/api/ready", "/api/login", "/api/admin/login",
        "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
    }
    assert expected == PUBLIC_PATHS


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer not-a-real-token"},
    {"Authorization": "Basic YWRtaW46YWRtaW4="},
    {"Authorization": "Bearer "},
    {"Authorization": ""},
    {"X-API-Key": "admin" + "123"},
])
def test_bad_credentials_get_401(client, headers):
    assert client.get("/api/patients", headers=headers).status_code == 401
    assert client.get("/api/admin/doctors", headers=headers).status_code == 401


def test_health_is_liveness_only(client, app):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # Liveness must not disclose model/database state.
    assert set(body) == {"status", "timestamp"}


def test_logout_revokes_the_token(client, make_doctor, auth):
    token, _doctor = make_doctor()
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_deactivated_doctor_session_is_killed(client, make_doctor, auth, app):
    token, doctor = make_doctor()
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    app.state.store.update_user(doctor["id"], {"active": False})
    response = client.get("/api/me", headers=auth(token))
    assert response.status_code == 403
    # The stale session is dropped, not merely refused.
    assert app.state.sessions.get(token) is None
