"""S2-3 -- the retention policy is enforceable, not just written down.

Acceptance criteria
-------------------
1. ``scripts/purge_records.py`` defaults to a dry run and deletes nothing.
2. ``--apply`` deletes only records older than the configured windows, never user
   accounts, and writes an audit entry describing what it removed.
3. The plan is inspectable before it is executed.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from storage import Store


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def seeded(tmp_path):
    data_dir = tmp_path / "data"
    store = Store(data_dir)
    store.create_patient({"name": "Ancient", "created_at": _iso(4000)})
    store.create_patient({"name": "Recent", "created_at": _iso(10)})
    store.create_user({"role": "doctor", "username": "longservice",
                       "email": "l@example.org", "password": "x" * 60,
                       "active": True, "permissions": {}})
    store.append_audit(actor="job", role="system", action="ancient_event", detail="old")
    store.close()
    return data_dir


def _run(app_dir, *args, data_dir):
    return subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "purge_records.py"),
         "--data-dir", str(data_dir), *args],
        capture_output=True, text=True, timeout=300,
    )


def test_dry_run_deletes_nothing(app_dir, seeded):
    before = Store(seeded)
    patients_before = len(before.list_patients())
    audit_before = len(before.list_audit(limit=100))
    before.close()

    result = _run(app_dir, data_dir=seeded)
    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout
    assert "patients older than 1825d : 1" in result.stdout

    after = Store(seeded)
    assert len(after.list_patients()) == patients_before
    assert len(after.list_audit(limit=100)) == audit_before
    after.close()


def test_apply_deletes_only_expired_records_and_audits_it(app_dir, seeded):
    result = _run(app_dir, "--apply", data_dir=seeded)
    assert result.returncode == 0, result.stderr

    store = Store(seeded)
    names = {row["name"] for row in store.list_patients()}
    assert names == {"Recent"}, "the retention window was not enforced"
    # Accounts are never purged: deactivate instead, so audit actors stay resolvable.
    assert store.list_users("doctor")
    events = [row["event"] for row in store.list_audit(limit=50)]
    assert any("purge_records" in event for event in events)
    store.close()


def test_audit_window_is_honoured(app_dir, tmp_path):
    data_dir = tmp_path / "data"
    store = Store(data_dir)
    conn = store._conn  # test-only direct write to backdate an audit row
    with store._tx() as tx:
        tx.execute("INSERT INTO audit (ts, actor, role, action, target, outcome, detail)"
                   " VALUES (?, 'x', 'system', 'old_event', '', 'ok', '')", (_iso(900),))
    store.close()

    result = _run(app_dir, "--apply", "--audit-days", "730", data_dir=data_dir)
    assert result.returncode == 0, result.stderr

    store = Store(data_dir)
    events = [row["event"] for row in store.list_audit(limit=50)]
    assert not any("old_event" in event for event in events)
    assert any("purge_records" in event for event in events), "the purge audit row must survive"
    store.close()
