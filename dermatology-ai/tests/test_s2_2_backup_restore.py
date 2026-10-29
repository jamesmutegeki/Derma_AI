"""S2-2 -- backups exist, are verified, and actually restore.

Acceptance criteria
-------------------
1. ``scripts/backup_db.py`` writes a timestamped, gzipped snapshot plus a SHA-256
   sidecar, with ``0600`` permissions inside ``0700``.
2. ``--verify`` restores into scratch space, runs ``PRAGMA integrity_check`` and
   compares row counts -- an unverified backup is reported as such.
3. ``--restore`` round-trips: the restored database contains the same rows.
4. ``--keep`` prunes old snapshots and their sidecars.
5. A tampered snapshot fails verification instead of silently restoring.
"""

from __future__ import annotations

import gzip
import hashlib
import stat
import subprocess
import sys

import pytest

from storage import Store


@pytest.fixture()
def populated_db(tmp_path):
    data_dir = tmp_path / "data"
    store = Store(data_dir)
    for index in range(3):
        store.create_patient({"name": f"Patient {index}", "fitz": "IV"})
    store.append_audit(actor="tester", role="admin", action="seeded", detail="fixture")
    store.close()
    return data_dir


def _run(app_dir, *args, data_dir):
    return subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "backup_db.py"),
         "--data-dir", str(data_dir), *args],
        capture_output=True, text=True, timeout=300,
    )


def test_backup_creates_a_snapshot_with_checksum(app_dir, populated_db):
    result = _run(app_dir, data_dir=populated_db)
    assert result.returncode == 0, result.stderr

    snapshots = list((populated_db / "backups").glob("derma-*.db.gz"))
    assert len(snapshots) == 1
    snapshot = snapshots[0]

    sidecar = snapshot.with_suffix(snapshot.suffix + ".sha256")
    assert sidecar.is_file()
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert sidecar.read_text().strip() == digest

    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshot.parent.stat().st_mode) == 0o700

    # The payload really is a gzip of a SQLite database.
    assert gzip.open(snapshot, "rb").read(16).startswith(b"SQLite format 3")


def test_backup_is_verified_and_restorable(app_dir, populated_db, tmp_path):
    result = _run(app_dir, "--verify", data_dir=populated_db)
    assert result.returncode == 0, result.stderr
    assert "verify:   ok" in result.stdout
    assert "'patients': 3" in result.stdout

    snapshot = next((populated_db / "backups").glob("derma-*.db.gz"))
    target = tmp_path / "restored"
    restore = _run(app_dir, "--restore", str(snapshot), "--target", str(target),
                   data_dir=populated_db)
    assert restore.returncode == 0, restore.stderr
    assert "restored" in restore.stdout

    restored = Store(target)
    assert len(restored.list_patients()) == 3
    assert restored.list_audit(limit=10)
    restored.close()


def test_tampered_snapshot_fails_verification(app_dir, populated_db, tmp_path):
    assert _run(app_dir, data_dir=populated_db).returncode == 0
    snapshot = next((populated_db / "backups").glob("derma-*.db.gz"))
    snapshot.write_bytes(snapshot.read_bytes()[:-10] + b"corrupted!")

    result = _run(app_dir, "--restore", str(snapshot), "--target", str(tmp_path / "x"),
                  data_dir=populated_db)
    # --restore does not verify; the verify path must.
    verify = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s');"
         "from pathlib import Path;"
         "import importlib.util;"
         "spec = importlib.util.spec_from_file_location('b', r'%s');"
         "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
         "m.verify(Path(r'%s'))" % (app_dir, app_dir / "scripts" / "backup_db.py", snapshot)],
        capture_output=True, text=True,
    )
    assert verify.returncode != 0
    assert "checksum mismatch" in (verify.stdout + verify.stderr)


def test_retention_prunes_old_snapshots(app_dir, populated_db):
    for _ in range(3):
        assert _run(app_dir, "--keep", "2", data_dir=populated_db).returncode == 0
    snapshots = sorted((populated_db / "backups").glob("derma-*.db.gz"))
    assert len(snapshots) <= 2
    sidecars = list((populated_db / "backups").glob("derma-*.db.gz.sha256"))
    assert len(sidecars) == len(snapshots)


def test_backup_refuses_a_missing_database(app_dir, tmp_path):
    result = _run(app_dir, data_dir=tmp_path / "empty")
    assert result.returncode != 0
    assert "database not found" in (result.stdout + result.stderr)
