#!/usr/bin/env python3
"""Back up (and verify) the SQLite database.

An untested backup is not a backup, so this script can restore into a scratch
directory and run ``PRAGMA integrity_check`` with the expected row counts before
declaring success.

    python scripts/backup_db.py                       # snapshot $DATA_DIR/derma.db
    python scripts/backup_db.py --verify              # write, then prove restorable
    python scripts/backup_db.py --keep 30             # keep the 30 newest snapshots
    python scripts/backup_db.py --restore FILE --target /tmp/restored

Snapshots are ``derma-YYYYmmddTHHMMSSZ.db.gz`` plus a ``.sha256`` sidecar. They
are written 0600 into ``$DATA_DIR/backups`` (0700). Encryption at rest is the
operator's responsibility: point ``--output-dir`` at an encrypted volume.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
TABLES = ("patients", "users", "cases", "kv", "audit")


def data_dir(explicit: str | None = None) -> Path:
    return Path(explicit or os.environ.get("DATA_DIR", APP_DIR / "data"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        counts = {}
        for table in TABLES:
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.Error:
                counts[table] = -1
        return counts
    finally:
        conn.close()


def backup(source: Path, output_dir: Path, keep: int | None = None) -> tuple[Path, dict[str, int]]:
    """Take a consistent snapshot using SQLite's online backup API."""
    if not source.is_file():
        raise SystemExit(f"database not found: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(output_dir, 0o700)
    except OSError:  # pragma: no cover - exotic filesystems
        pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"derma-{stamp}.db.gz"

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "snapshot.db"
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        dst = sqlite3.connect(scratch)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with scratch.open("rb") as raw, gzip.open(target, "wb") as compressed:
            shutil.copyfileobj(raw, compressed)

    try:
        os.chmod(target, 0o600)
    except OSError:  # pragma: no cover
        pass
    digest = sha256_file(target)
    target.with_suffix(target.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")

    if keep:
        prune(output_dir, keep)
    return target, row_counts(source)


def prune(output_dir: Path, keep: int) -> list[Path]:
    """Delete all but the ``keep`` newest snapshots. Returns removed paths."""
    snapshots = sorted(output_dir.glob("derma-*.db.gz"))
    removed: list[Path] = []
    for old in snapshots[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
        sidecar = old.with_suffix(old.suffix + ".sha256")
        sidecar.unlink(missing_ok=True)
        removed.append(old)
    return removed


def verify(snapshot: Path, expected: dict[str, int] | None = None) -> dict[str, int]:
    """Restore into a scratch directory and prove the copy is intact."""
    sidecar = snapshot.with_suffix(snapshot.suffix + ".sha256")
    if sidecar.is_file():
        recorded = sidecar.read_text(encoding="utf-8").strip()
        actual = sha256_file(snapshot)
        if recorded != actual:
            raise SystemExit(f"checksum mismatch for {snapshot}: {recorded} != {actual}")

    with tempfile.TemporaryDirectory() as tmp:
        restored = Path(tmp) / "restored.db"
        with gzip.open(snapshot, "rb") as compressed, restored.open("wb") as out:
            shutil.copyfileobj(compressed, out)

        conn = sqlite3.connect(restored)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if integrity != "ok":
            raise SystemExit(f"integrity_check failed for {snapshot}: {integrity}")

        counts = row_counts(restored)
        if expected:
            mismatched = {k: (expected[k], counts.get(k)) for k in expected
                          if expected[k] >= 0 and counts.get(k) != expected[k]}
            if mismatched:
                raise SystemExit(f"row counts differ after restore: {mismatched}")
        return counts


def restore(snapshot: Path, target_dir: Path) -> Path:
    """Restore a snapshot to ``target_dir/derma.db`` (refuses to overwrite)."""
    target = target_dir / "derma.db"
    if target.exists():
        raise SystemExit(f"refusing to overwrite existing database: {target}")
    target_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(snapshot, "rb") as compressed, target.open("wb") as out:
        shutil.copyfileobj(compressed, out)
    try:
        os.chmod(target, 0o600)
    except OSError:  # pragma: no cover
        pass
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot / verify / restore the Derma-AI database")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--output-dir", default=None, help="default: $DATA_DIR/backups")
    parser.add_argument("--keep", type=int, default=30, help="retain this many snapshots (0 = all)")
    parser.add_argument("--verify", action="store_true", help="restore into scratch and check")
    parser.add_argument("--restore", default=None, metavar="SNAPSHOT")
    parser.add_argument("--target", default=None, help="with --restore: destination directory")
    args = parser.parse_args(argv)

    root = data_dir(args.data_dir)
    if args.restore:
        if not args.target:
            raise SystemExit("--restore requires --target DIR")
        restored = restore(Path(args.restore), Path(args.target))
        print(f"restored {args.restore} -> {restored}")
        print(f"row counts: {row_counts(restored)}")
        return 0

    output_dir = Path(args.output_dir) if args.output_dir else root / "backups"
    snapshot, counts = backup(root / "derma.db", output_dir, keep=args.keep or None)
    print(f"snapshot: {snapshot}")
    print(f"sha256:   {sha256_file(snapshot)}")
    print(f"rows:     {counts}")
    if args.verify:
        verify(snapshot, counts)
        print("verify:   ok (integrity_check passed, row counts match)")
    else:
        print("verify:   skipped -- run with --verify before trusting this snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
