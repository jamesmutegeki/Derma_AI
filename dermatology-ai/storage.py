"""SQLite persistence layer for the Dermatology AI dashboard.

Replaces the previous read-modify-write JSON files, which lost records under
concurrent requests (20 parallel creates persisted only 14) and could be left
truncated by a crash mid-write.

Design notes
------------
* One connection guarded by an ``RLock``: SQLite serialises writers anyway, and
  WAL mode lets readers proceed concurrently.  ``BEGIN IMMEDIATE`` makes every
  read-modify-write (id allocation, visit append) atomic.
* Every mutation runs inside a transaction; a crash cannot leave a half-written
  JSON document behind.
* Nothing here fabricates data.  Empty store -> empty results.
* The database file is created ``0600`` inside a ``0700`` directory.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    doc         TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    role         TEXT NOT NULL CHECK (role IN ('admin', 'doctor')),
    username     TEXT NOT NULL,
    username_key TEXT NOT NULL UNIQUE,
    email        TEXT,
    email_key    TEXT,
    password     TEXT NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1,
    doc          TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    doc     TEXT NOT NULL,
    ts      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    actor  TEXT NOT NULL,
    role   TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    outcome TEXT NOT NULL DEFAULT 'ok',
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_cases_ts ON cases(ts);
"""


#: Fields that must never leave the storage layer.
_PRIVATE_USER_FIELDS = ("password", "email_key", "username_key")


def public_user(user: dict) -> dict:
    """Strip secrets from a user record before it is serialised."""
    return {k: v for k, v in user.items() if k not in _PRIVATE_USER_FIELDS}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:  # pragma: no cover - e.g. exotic filesystems
        logger.warning("Could not chmod %s to %o", path, mode)


class Store:
    """Thin, thread-safe repository over a single SQLite database."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        _chmod(self.data_dir, 0o700)
        self.db_path = self.data_dir / "derma.db"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.db_path) + suffix)
            if candidate.exists():
                _chmod(candidate, 0o600)

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _tx(self):
        """Context manager for an immediate (writer-locking) transaction."""

        class _Tx:
            def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
                self.conn = conn
                self.lock = lock

            def __enter__(self):
                self.lock.acquire()
                self.conn.execute("BEGIN IMMEDIATE")
                return self.conn

            def __exit__(self, exc_type, exc, tb):
                try:
                    if exc_type is None:
                        self.conn.commit()
                    else:
                        self.conn.rollback()
                finally:
                    self.lock.release()
                return False

        return _Tx(self._conn, self._lock)

    # -- patients ----------------------------------------------------------
    def list_patients(self, query: str = "", fitz: str = "", limit: int = 200, offset: int = 0) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc FROM patients ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (max(0, int(limit)), max(0, int(offset))),
            ).fetchall()
        patients = [json.loads(r["doc"]) for r in rows]
        if query:
            q = query.lower()
            patients = [
                p for p in patients
                if q in str(p.get("name", "")).lower() or q in str(p.get("id", "")).lower()
            ]
        if fitz:
            patients = [p for p in patients if str(p.get("fitz", "")).lower() == fitz.lower()]
        return patients

    def count_patients(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0])

    def get_patient(self, patient_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT doc FROM patients WHERE id = ?", (patient_id,)).fetchone()
        return json.loads(row["doc"]) if row else None

    def create_patient(self, patient: dict) -> dict:
        """Insert a patient, allocating a collision-free id inside the transaction."""
        now = utcnow()
        with self._tx() as conn:
            pid = str(patient.get("id") or "").strip()
            if not pid:
                pid = self._next_patient_id(conn)
            elif conn.execute("SELECT 1 FROM patients WHERE id = ?", (pid,)).fetchone():
                pid = self._next_patient_id(conn)
            record = {
                "id": pid,
                "name": patient["name"],
                "age": patient.get("age", ""),
                "gender": patient.get("gender", ""),
                "fitz": patient.get("fitz", ""),
                "contact": patient.get("contact", ""),
                "history": patient.get("history", ""),
                "diagnosis": patient.get("diagnosis", ""),
                "body_site": patient.get("body_site", ""),
                "status": patient.get("status", "active"),
                "visits": patient.get("visits", []),
                # Demo/synthetic cohorts are flagged here so the UI can badge them
                # and no downstream consumer can mistake them for real records.
                "simulated": bool(patient.get("simulated", False)),
                "created_at": patient.get("created_at", now),
            }
            conn.execute(
                "INSERT INTO patients (id, doc, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (pid, json.dumps(record), record["created_at"], now),
            )
        return record

    @staticmethod
    def _next_patient_id(conn: sqlite3.Connection) -> str:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"PAT-{today}-"
        rows = conn.execute("SELECT id FROM patients WHERE id LIKE ?", (prefix + "%",)).fetchall()
        max_n = 0
        for row in rows:
            try:
                max_n = max(max_n, int(str(row["id"]).rsplit("-", 1)[-1]))
            except (ValueError, IndexError):
                continue
        candidate = f"{prefix}{max_n + 1:04d}"
        while conn.execute("SELECT 1 FROM patients WHERE id = ?", (candidate,)).fetchone():
            max_n += 1
            candidate = f"{prefix}{max_n + 1:04d}"
        return candidate

    def update_patient(self, patient_id: str, patient: dict) -> Optional[dict]:
        now = utcnow()
        with self._tx() as conn:
            row = conn.execute("SELECT doc FROM patients WHERE id = ?", (patient_id,)).fetchone()
            if not row:
                return None
            existing = json.loads(row["doc"])
            record = {
                "id": patient_id,
                "name": patient["name"],
                "age": patient.get("age", ""),
                "gender": patient.get("gender", ""),
                "fitz": patient.get("fitz", ""),
                "contact": patient.get("contact", ""),
                "history": patient.get("history", ""),
                "diagnosis": patient.get("diagnosis", ""),
                "body_site": patient.get("body_site", ""),
                "status": patient.get("status", "active"),
                "visits": existing.get("visits", []),
                "created_at": existing.get("created_at", now),
            }
            conn.execute("UPDATE patients SET doc = ?, updated_at = ? WHERE id = ?", (json.dumps(record), now, patient_id))
        return record

    def delete_patient(self, patient_id: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            return cur.rowcount > 0

    # -- visits ------------------------------------------------------------
    def list_visits(self, patient_id: str) -> list[dict]:
        patient = self.get_patient(patient_id)
        return list(patient.get("visits", [])) if patient else []

    def add_visit(self, patient_id: str, visit: dict) -> Optional[dict]:
        now = utcnow()
        with self._tx() as conn:
            row = conn.execute("SELECT doc FROM patients WHERE id = ?", (patient_id,)).fetchone()
            if not row:
                return None
            patient = json.loads(row["doc"])
            record = {
                "id": visit.get("id") or f"VIS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
            }
            for key in (
                "date", "desc", "tag", "diagnosis", "ai_findings",
                "treatment_notes", "doctor_name", "lesion_location", "lesion_size",
            ):
                record[key] = visit.get(key, "")
            record["created_at"] = now
            visits = list(patient.get("visits", []))
            visits.append(record)
            patient["visits"] = visits
            conn.execute("UPDATE patients SET doc = ?, updated_at = ? WHERE id = ?", (json.dumps(patient), now, patient_id))
        return record

    def delete_visit(self, patient_id: str, visit_id: str) -> bool:
        now = utcnow()
        with self._tx() as conn:
            row = conn.execute("SELECT doc FROM patients WHERE id = ?", (patient_id,)).fetchone()
            if not row:
                return False
            patient = json.loads(row["doc"])
            visits = list(patient.get("visits", []))
            kept = [v for v in visits if v.get("id") != visit_id]
            if len(kept) == len(visits):
                return False
            patient["visits"] = kept
            conn.execute("UPDATE patients SET doc = ?, updated_at = ? WHERE id = ?", (json.dumps(patient), now, patient_id))
        return True

    # -- users -------------------------------------------------------------
    def list_users(self, role: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc FROM users WHERE role = ? ORDER BY created_at ASC", (role,)
            ).fetchall()
        # SECURITY FIX: never hand password hashes (or their lookup keys) to callers.
        return [public_user(json.loads(r["doc"])) for r in rows]

    def get_user(self, user_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT doc FROM users WHERE id = ?", (user_id,)).fetchone()
        return json.loads(row["doc"]) if row else None

    def find_user(self, *, identifier: str, role: Optional[str] = None) -> Optional[dict]:
        """Look up by username or email (case-insensitive)."""
        key = identifier.strip().lower()
        sql = "SELECT doc FROM users WHERE (username_key = ? OR email_key = ?)"
        params: list[Any] = [key, key]
        if role:
            sql += " AND role = ?"
            params.append(role)
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return json.loads(row["doc"]) if row else None

    def create_user(self, user: dict) -> dict:
        now = utcnow()
        record = dict(user)
        record.setdefault("id", f"doc-{uuid.uuid4().hex[:6]}")
        record.setdefault("active", True)
        record.setdefault("created_at", now)
        record.setdefault("last_login", None)
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO users (id, role, username, username_key, email, email_key,
                                      password, active, doc, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["id"],
                    record["role"],
                    record["username"],
                    record["username"].strip().lower(),
                    record.get("email") or "",
                    (record.get("email") or "").strip().lower() or None,
                    record["password"],
                    1 if record.get("active", True) else 0,
                    json.dumps(record),
                    record["created_at"],
                ),
            )
        return {k: v for k, v in record.items() if k != "password"}

    def update_user(self, user_id: str, changes: dict) -> Optional[dict]:
        with self._tx() as conn:
            row = conn.execute("SELECT doc FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            record = json.loads(row["doc"])
            record.update({k: v for k, v in changes.items() if k != "id"})
            if "email" in changes:
                record["email_key"] = (changes.get("email") or "").strip().lower() or None
            conn.execute(
                "UPDATE users SET doc = ?, password = ?, email = ?, email_key = ?, active = ? WHERE id = ?",
                (
                    json.dumps(record),
                    record.get("password", ""),
                    record.get("email") or "",
                    record.get("email_key"),
                    1 if record.get("active", True) else 0,
                    user_id,
                ),
            )
        return {k: v for k, v in record.items() if k != "password"}

    def username_taken(self, username: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM users WHERE username_key = ?", (username.strip().lower(),)
            ).fetchone()
        return row is not None

    def email_taken(self, email: str) -> bool:
        if not email:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM users WHERE email_key = ?", (email.strip().lower(),)
            ).fetchone()
        return row is not None

    # -- cases (fairness tracker) -----------------------------------------
    def add_case(self, case: dict) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO cases (case_id, doc, ts) VALUES (?, ?, ?)",
                (case["case_id"], json.dumps(case), case.get("timestamp") or utcnow()),
            )

    def list_cases(self, limit: Optional[int] = None) -> list[dict]:
        sql = "SELECT doc FROM cases ORDER BY seq ASC"
        params: tuple = ()
        if limit:
            sql += " LIMIT ?"
            params = (int(limit),)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(r["doc"]) for r in rows]

    def update_case(self, case_id: str, changes: dict) -> Optional[dict]:
        with self._tx() as conn:
            row = conn.execute("SELECT doc FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if not row:
                return None
            record = json.loads(row["doc"])
            record.update(changes)
            conn.execute("UPDATE cases SET doc = ? WHERE case_id = ?", (json.dumps(record), case_id))
        return record

    def clear_cases(self) -> int:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM cases")
            return cur.rowcount

    # -- key/value (notes, snapshots, meta) --------------------------------
    def get_kv(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_kv(self, key: str, value: Any) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    # -- audit -------------------------------------------------------------
    def append_audit(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        target: str = "",
        outcome: str = "ok",
        detail: str = "",
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO audit (ts, actor, role, action, target, outcome, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (utcnow(), actor, role, action, target, outcome, detail),
            )

    def list_audit(self, query: str = "", level: str = "", limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, actor, role, action, target, outcome, detail FROM audit"
                " ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        entries = [
            {
                "event": f"{r['action']} {r['target']}".strip(),
                "actor": r["actor"],
                "role": r["role"],
                "level": "admin" if r["role"] == "admin" else "info",
                "outcome": r["outcome"],
                "detail": r["detail"],
                "timestamp": r["ts"],
            }
            for r in rows
        ]
        if query:
            q = query.lower()
            entries = [e for e in entries if q in e["event"].lower() or q in e["actor"].lower()]
        if level:
            entries = [e for e in entries if e["level"] == level]
        return entries


# ---------------------------------------------------------------------------
#  One-time migration from the legacy JSON files
# ---------------------------------------------------------------------------

LEGACY_FILES = (
    "patients.json",
    "doctors.json",
    "notes.json",
    "activity.json",
    "case_history.json",
)


def migrate_legacy_json(store: Store, source_dir: str | Path) -> dict:
    """Import legacy JSON files into SQLite once, then leave them in place.

    Returns a summary suitable for logging.  Idempotent: files are only imported
    when the corresponding table/content is empty.
    """
    source = Path(source_dir)
    summary: dict[str, str] = {}

    patients_file = source / "patients.json"
    if patients_file.exists() and store.count_patients() == 0:
        try:
            records: Iterable[dict] = json.loads(patients_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            summary["patients"] = f"skipped ({exc})"
        else:
            count = 0
            for record in records:
                if "name" not in record:
                    continue
                store.create_patient(record)
                count += 1
            summary["patients"] = f"imported {count}"
    elif patients_file.exists():
        summary["patients"] = "skipped (database already populated)"

    doctors_file = source / "doctors.json"
    if doctors_file.exists() and not store.list_users("admin") and not store.list_users("doctor"):
        try:
            data = json.loads(doctors_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            summary["users"] = f"skipped ({exc})"
        else:
            count = 0
            for admin in data.get("admins", []):
                store.create_user({**admin, "role": "admin", "email": admin.get("email", "")})
                count += 1
            for doctor in data.get("doctors", []):
                store.create_user({**doctor, "role": "doctor"})
                count += 1
            summary["users"] = f"imported {count}"

    notes_file = source / "notes.json"
    if notes_file.exists() and store.get_kv("notes") is None:
        try:
            store.set_kv("notes", json.loads(notes_file.read_text(encoding="utf-8")))
            summary["notes"] = "imported"
        except (json.JSONDecodeError, OSError) as exc:
            summary["notes"] = f"skipped ({exc})"

    history_file = source / "case_history.json"
    if history_file.exists() and not store.list_cases():
        try:
            data = json.loads(history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            summary["cases"] = f"skipped ({exc})"
        else:
            for case in data.get("cases", []):
                case.setdefault("case_id", case.get("case_id") or uuid.uuid4().hex[:12])
                store.add_case(case)
            summary["cases"] = f"imported {len(data.get('cases', []))}"

    for name, result in summary.items():
        logger.info("Legacy migration %s: %s", name, result)
    return summary
