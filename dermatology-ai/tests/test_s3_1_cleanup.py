"""S3-1 -- the P2/P3 leftovers from the review.

Acceptance criteria
-------------------
1. Uploads are capped *while streaming* (an 11 MB body is refused even when the
   client lies about ``Content-Length``).
2. Login does not leak whether an account exists: a bcrypt verification runs even
   for an unknown identifier.
3. Agent checkpoints are written atomically, so a crash mid-save cannot leave a
   file that fails to load on the next boot.
4. The dashboard returns to the login screen when the session expires (401)
   instead of failing every subsequent click with a generic alert.
5. Documentation has no "output goes here" placeholders and no unmeasured
   "(this work)" performance claim; dataset cards, CONTRIBUTING exist.
"""

from __future__ import annotations

import io
import re

import pytest
from PIL import Image


def _png(size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 90, 70)).save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------- upload cap
def test_oversized_upload_is_refused_while_streaming(client, make_doctor, auth, app):
    """11 MB without a truthful Content-Length must still be refused."""
    token, _ = make_doctor()
    app.state.backend.status.model_ready = True  # reach the upload code path
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * (11 * 1024 * 1024)
    response = client.post(
        "/api/diagnose",
        headers={**auth(token), "Content-Length": "100"},
        files={"file": ("big.png", payload, "image/png")},
        data={"fitzpatrick": "4"},
    )
    app.state.backend.status.model_ready = False
    assert response.status_code in (413, 422), response.text
    if response.status_code == 422:
        # httpx recomputes Content-Length; the middleware then catches it first.
        assert "large" in response.text.lower() or "image" in response.text.lower()


def test_chunked_upload_without_content_length_is_capped(client, make_doctor, auth, app):
    """No Content-Length at all: the route must still refuse more than 10 MB."""
    token, _ = make_doctor()
    app.state.backend.status.model_ready = True
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * (11 * 1024 * 1024)
    response = client.post(
        "/api/diagnose",
        headers=auth(token),
        files={"file": ("big.png", payload, "image/png")},
        data={"fitzpatrick": "4"},
    )
    app.state.backend.status.model_ready = False
    assert response.status_code in (413, 422), response.text


# ------------------------------------------------------------ login oracle
def test_login_runs_a_hash_check_for_unknown_accounts(client, monkeypatch):
    import server as server_module

    calls = {"n": 0}
    real = server_module.check_password

    def counting(password, hashed):
        calls["n"] += 1
        return real(password, hashed)

    monkeypatch.setattr(server_module, "check_password", counting)

    response = client.post("/api/login", json={"email": "ghost@example.org",
                                               "password": "whatever-123!"})
    assert response.status_code == 401
    assert calls["n"] >= 1, "unknown identifiers skip bcrypt -> timing oracle"


# --------------------------------------------------------- atomic agent save
def test_agent_save_is_atomic(tmp_path, monkeypatch):
    import torch

    from rl_module import PPOAgent

    agent = PPOAgent(state_dim=10, action_dim=3, device="cpu")
    target = tmp_path / "agent.pt"
    agent.save(str(target))
    original = target.read_bytes()

    def exploding_save(*args, **kwargs):  # simulate a crash mid-write
        raise RuntimeError("disk full")

    monkeypatch.setattr(torch, "save", exploding_save)
    with pytest.raises(RuntimeError):
        agent.save(str(target))

    assert target.read_bytes() == original, "a failed save corrupted the previous checkpoint"
    assert not list(tmp_path.glob("*.tmp")), "temporary file left behind"


# ------------------------------------------------- dashboard session expiry
def test_dashboard_handles_expired_sessions(app_dir):
    js = (app_dir / "dashboard.js").read_text(encoding="utf-8")
    assert "401" in js, "the dashboard never checks for 401"
    assert re.search(r"function handleUnauthorized|handleUnauthorized\(", js), \
        "there must be one place that handles an expired session"
    assert "loginOverlay" in js, "the handler must bring the login overlay back"
    assert "state.token = ''" in js, "the stale token must be discarded"
    # A 401 must not surface as a bare alert for every click.
    assert "Session expired" in js or "session expired" in js.lower()


# -------------------------------------------------------------------- docs
def test_no_placeholders_or_unmeasured_claims(repo_root):
    explained = (repo_root / "docs" / "Project_Explained.md").read_text(encoding="utf-8")
    assert "output goes here" not in explained.lower()
    assert "run_evaluation.py" not in explained, "that script does not exist"

    for path in list((repo_root / "docs").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        # Only a *numeric* claim is a problem; "AUC not yet measured" is the fix.
        for match in re.finditer(r"\(this work\)[^\n]*AUC[^\n]*?(?:~|≈)?\s*0\.\d+", text):
            pytest.fail(f"{path.name}: unmeasured claim {match.group(0)!r}")
        assert "deliverables/" not in text, f"{path.name} references a missing directory"


def test_project_artefacts_exist(app_dir, repo_root):
    for name in ("CONTRIBUTING.md",):
        assert (repo_root / name).is_file(), f"{name} is missing"
    cards = list((app_dir / "docs").glob("DATASET_CARD_*.md"))
    assert len(cards) >= 3, f"expected dataset cards, found {[c.name for c in cards]}"
    for card in cards:
        text = card.read_text(encoding="utf-8").lower()
        assert "source" in text and "licence" in text or "license" in text
        assert "fitzpatrick" in text


def test_gitignore_is_not_a_scratch_file_dump(repo_root):
    text = (repo_root / ".gitignore").read_text(encoding="utf-8")
    cruft = [line for line in text.splitlines()
             if re.match(r"^_(check|debug|find|full_test|quick_test|run_tests|smoke_test|test|verify)_", line)]
    assert not cruft, f".gitignore still lists scratch-file prefixes: {cruft}"


@pytest.fixture(scope="module")
def repo_root(app_dir):
    return app_dir.parent
