"""S2-4 -- operational readiness is written down and testable.

This is a gate item: no real patient data until it is signed off.

Acceptance criteria
-------------------
1. `docs/OPERATIONS.md` covers monitoring, backup/restore, retention, incident
   response, rollback and a go-live checklist.
2. The go-live checklist gates on S1-1, this item (S2-4), the retention policy
   and IRB approval.
3. Every script the runbook tells an operator to run exists and is executable.
4. `SECURITY.md` and the runbook agree on the gate list.
"""

from __future__ import annotations

import re

import pytest

REQUIRED_SECTIONS = (
    "daily checks",
    "backup and restore",
    "retention",
    "monitoring and alerting",
    "security incidents",
    "go-live checklist",
    "rollback",
)


@pytest.fixture(scope="module")
def runbook(app_dir):
    return (app_dir / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")


def test_runbook_covers_every_operational_concern(runbook):
    lowered = runbook.lower()
    missing = [section for section in REQUIRED_SECTIONS if section not in lowered]
    assert not missing, f"runbook is missing sections: {missing}"


def test_gate_items_are_explicit(runbook):
    for item in ("S1-1", "S2-4", "Retention and backup policy", "IRB"):
        assert item in runbook, f"go-live checklist does not gate on {item}"
    assert "not a medical device" in runbook.lower()
    assert "do not delete evidence" in runbook.lower()


def test_every_script_in_the_runbook_exists(app_dir, runbook):
    referenced = set(re.findall(r"scripts/([a-z_]+\.py|ci_grep\.sh)", runbook))
    assert referenced, "the runbook must reference the operational scripts"
    missing = [name for name in referenced if not (app_dir / "scripts" / name).is_file()]
    assert not missing, f"runbook references missing scripts: {missing}"


def test_security_doc_and_runbook_agree_on_the_gate(app_dir, runbook):
    security = (app_dir / "SECURITY.md").read_text(encoding="utf-8")
    for item in ("S1-1", "S2-4", "IRB"):
        assert item in security, f"SECURITY.md §8 does not mention {item}"
    assert "SECURITY.md" in runbook


def test_incident_response_names_containment_actions(runbook):
    lowered = runbook.lower()
    for action in ("revoke", "audit", "notify", "restore"):
        assert action in lowered, f"incident response does not cover {action}"
