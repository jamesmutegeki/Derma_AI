#!/usr/bin/env python3
"""Enforce the retention policy.

The retention table lives in ``SECURITY.md`` §4. This script is the only
sanctioned way to delete records, and it defaults to ``--dry-run`` so an
operator sees what would go before it goes.

    python scripts/purge_records.py                        # dry run, prints counts
    python scripts/purge_records.py --apply                # delete
    python scripts/purge_records.py --apply --audit-days 730 --patient-days 1825

Rules:

* patients older than ``--patient-days`` (default 1825 = 5 years after creation)
  and their visits are deleted;
* audit rows older than ``--audit-days`` (default 730) are deleted;
* **user accounts are never purged** -- deactivate them instead, so the audit
  trail keeps a resolvable actor;
* every purge writes its own audit rows (before deleting, and in a way that
  survives the purge itself).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from storage import Store  # noqa: E402


def cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def plan(store: Store, patient_days: int, audit_days: int) -> dict[str, list[str]]:
    """Return the ids that *would* be deleted (never deletes anything)."""
    patient_cutoff = cutoff(patient_days)
    audit_cutoff = cutoff(audit_days)

    patients = [
        row["id"] for row in store.list_patients(limit=100_000)
        if str(row.get("created_at", "")) < patient_cutoff
    ]
    audits = [
        row for row in store.list_audit(limit=100_000)
        if str(row.get("timestamp", "")) < audit_cutoff
    ]
    return {"patients": patients, "audit_entries": [row.get("timestamp", "") for row in audits]}


def apply(store: Store, plan_result: dict[str, list[str]], audit_days: int) -> dict[str, int]:
    deleted_patients = 0
    for patient_id in plan_result["patients"]:
        if store.delete_patient(patient_id):
            deleted_patients += 1

    deleted_audit = store.purge_audit_before(cutoff(audit_days))

    # Record the purge itself *after* deleting, so the record survives.
    store.append_audit(
        actor="retention-job",
        role="system",
        action="purge_records",
        target=f"patients={deleted_patients},audit={deleted_audit}",
        detail=f"patient_days={plan_result.get('patient_days')},audit_days={audit_days}",
    )
    return {"patients": deleted_patients, "audit_entries": deleted_audit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the Derma-AI retention policy")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--patient-days", type=int, default=1825)
    parser.add_argument("--audit-days", type=int, default=730)
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir or os.environ.get("DATA_DIR", APP_DIR / "data"))
    store = Store(data_dir)
    try:
        pending = plan(store, args.patient_days, args.audit_days)
        print(f"data dir : {data_dir}")
        print(f"patients older than {args.patient_days}d : {len(pending['patients'])}")
        print(f"audit rows older than {args.audit_days}d : {len(pending['audit_entries'])}")

        if not args.apply:
            print("dry run: nothing deleted. Re-run with --apply to enforce the policy.")
            return 0

        pending["patient_days"] = args.patient_days
        result = apply(store, pending, args.audit_days)
        print(f"deleted patients: {result['patients']}, audit rows: {result['audit_entries']}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
