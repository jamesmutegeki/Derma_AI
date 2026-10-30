"""Shared fixtures for the Derma-AI test-suite.

Every test runs against a throw-away ``DATA_DIR`` (SQLite database) and never
touches the repository working tree, the developer's data directory, or the
real model checkpoint.

The API is imported as top-level modules (``import server``), because the
application is deployed as a flat directory of modules, not as a package.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterator

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

#: Routes that are allowed to answer without a bearer token.
#:
#: ``test_s0_1_auth_required`` asserts that *every other* route in
#: ``app.routes`` replies 401, so adding an unprotected route fails the suite.
PUBLIC_PATHS = {
    "/",
    "/dashboard.js",
    "/robots.txt",
    "/measles_child.jpg",
    "/bg_vitiligo.jpg",
    "/bg_acne_skin.jpg",
    "/api/health",
    "/api/ready",
    "/api/login",
    "/api/admin/login",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}

#: Path parameters → concrete values used when probing a route.
PARAM_VALUES = {
    "patient_id": "PAT-2025-0001",
    "visit_id": "1",
    "doctor_id": "doc-000000",
    "case_id": "case-000000",
    "sid": "deadbeef",
}

STRONG_PASSWORD = "Str0ng-Passw0rd!7"


def concrete_url(path: str) -> str:
    """Fill ``{param}`` placeholders with a harmless concrete value."""
    return re.sub(r"\{(\w+)\}", lambda m: PARAM_VALUES.get(m.group(1), "x"), path)


def iter_routes(app) -> Iterator[tuple[str, str]]:
    """Yield ``(method, path)`` for every API route, straight from ``app.routes``.

    Documentation endpoints are included: they are public by design and are
    listed in :data:`PUBLIC_PATHS`.
    """
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            yield method, path


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """A fresh application bound to a temporary database and no model."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEMO_MODE", "0")
    monkeypatch.setenv("TRUST_PROXY", "0")
    # Login rate limiting is exercised on purpose in test_s0_3; everywhere else
    # a generous limit keeps unrelated tests from tripping slowapi.
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "1000/minute")

    from server import create_app

    application = create_app(data_dir=tmp_path / "data", initialise_backend=False)
    application.state.limiter.reset()
    yield application
    application.state.sessions._sessions.clear()
    application.state.store.close()


@pytest.fixture()
def client(app) -> Iterator:
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_session(app):
    """Create a session directly in the session store (no login round-trip)."""

    def _make(role: str, user: dict) -> str:
        token, _session = app.state.sessions.create(role, user)
        return token

    return _make


@pytest.fixture()
def admin_token(make_session) -> str:
    return make_session("admin", {"id": "admin-1", "username": "admin", "role": "admin",
                                  "name": "Site Administrator"})


@pytest.fixture()
def make_doctor(app):
    """Create a doctor account and an authenticated session for it.

    ``permissions=None`` grants every flag; pass a dict to deny specific ones.
    """
    from auth import hash_password
    from constants import DOCTOR_PERMISSIONS

    counter = {"n": 0}

    def _make(permissions: dict | None = None, *, active: bool = True,
              username: str | None = None) -> tuple[str, dict]:
        counter["n"] += 1
        name = username or f"doctor{counter['n']}"
        granted = {flag: True for flag in DOCTOR_PERMISSIONS}
        if permissions:
            granted.update(permissions)
        record = app.state.store.create_user({
            "role": "doctor",
            "username": name,
            "email": f"{name}@example.org",
            "password": hash_password(STRONG_PASSWORD),
            "name": f"Dr {name.title()}",
            "title": "Dermatologist",
            "nin": "",
            "active": active,
            "permissions": granted,
        })
        token, _session = app.state.sessions.create("doctor", record)
        return token, record

    return _make


@pytest.fixture()
def auth():
    """Build ``Authorization`` headers."""

    def _auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    return _auth


def repo_files(*suffixes: str) -> list[Path]:
    """Files in the application directory, skipping caches and virtualenvs."""
    skip = {".git", "__pycache__", "data", "node_modules", ".pytest_cache", "tests"}
    out: list[Path] = []
    for path in APP_DIR.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(APP_DIR).parts):
            continue
        if suffixes and path.suffix not in suffixes:
            continue
        out.append(path)
    return out


@pytest.fixture(scope="session")
def app_dir() -> Path:
    return APP_DIR


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Keep ambient configuration from leaking into tests."""
    for var in ("MODEL_CHECKPOINT_PATH", "AGENT_CHECKPOINT_PATH", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)
    yield
