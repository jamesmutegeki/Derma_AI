"""S4-3 -- the approved gate actions are real, and no more than they are.

Pathway `1A 2A 3A 4A` separates three kinds of thing:

* **2A / 3A are decisions made today** and must be visibly in force, with their
  limits stated (self-review, not audit; synthetic data only) rather than
  glossed;
* **4A is a request**, and the documentation must not describe a pending
  exemption as an approval;
* **1A is work**, and until a real checkpoint is frozen the gate stays unmet --
  no document may imply otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path


def _read(app_dir: Path, relative: str) -> str:
    return (app_dir / relative).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 2A -- the runbook is signed, and the signature says what it is worth
# --------------------------------------------------------------------------

def test_runbook_is_signed_and_dated(app_dir):
    text = _read(app_dir, "docs/OPERATIONS.md")
    assert "### Signature" in text
    signature = text.split("### Signature", 1)[1]
    assert "2026-10-30" in signature
    assert "J. Mutegeki" in signature


def test_runbook_signature_admits_the_lack_of_independent_review(app_dir):
    signature = _read(app_dir, "docs/OPERATIONS.md").split("### Signature", 1)[1]
    lowered = signature.lower()
    assert "not been independently audited" in lowered
    assert "single-engineer" in lowered


def test_runbook_does_not_sign_items_it_cannot_evidence(app_dir):
    text = _read(app_dir, "docs/OPERATIONS.md")
    checklist = text.split("## 6. Go-live checklist", 1)[1].split("### Signature", 1)[0]
    rows = [line for line in checklist.splitlines() if re.match(r"\| \d+ \|", line)]
    assert len(rows) == 10, "the go-live checklist changed shape"

    def date_of(row_number: int) -> str:
        row = next(line for line in rows if line.startswith(f"| {row_number} |"))
        return row.rstrip("|").split("|")[-1].strip()

    # Signed today.
    assert date_of(2) == "2026-10-30"   # runbook reviewed
    assert date_of(3) == "2026-10-30"   # retention policy in force
    # Still open -- signing them would be a false claim.
    for item in (1, 4, 6, 10):
        assert date_of(item) == "", f"go-live item {item} must stay unsigned"


# --------------------------------------------------------------------------
# 3A -- the retention policy is in force, and scoped honestly
# --------------------------------------------------------------------------

def test_retention_policy_is_in_force(app_dir):
    text = _read(app_dir, "SECURITY.md")
    assert "In force from 2026-10-30" in text
    assert "not yet in force" not in text


def test_retention_policy_states_its_scope_and_review_date(app_dir):
    section = _read(app_dir, "SECURITY.md").split("### Retention and backup policy", 1)[1]
    section = section.split("## 5.", 1)[0]
    lowered = section.lower()
    assert "2027-01-28" in section, "a review date is what makes the adoption meaningful"
    assert "synthetic" in lowered and "de-identified" in lowered
    assert "data controller" in lowered


# --------------------------------------------------------------------------
# 4A -- an exemption request is prepared; it is not an approval
# --------------------------------------------------------------------------

def test_exemption_request_is_submission_ready(app_dir):
    text = _read(app_dir, "docs/IRB_EXEMPTION_REQUEST.md")
    lowered = text.lower()
    for required in ("ham10000", "ddi", "scin", "licence", "not human-subjects"):
        assert required in lowered, required
    assert "[institution]" in text  # the fields only the applicant can fill
    assert "determination" in lowered


def test_exemption_request_is_not_described_as_approved(app_dir):
    text = _read(app_dir, "docs/IRB_EXEMPTION_REQUEST.md")
    head = text.split("## 1.", 1)[0].lower()
    assert "not yet submitted" in head
    assert "not approved" in head
    # No sentence may claim the exemption was granted.
    for bad in ("exemption granted", "irb approved", "approval granted", "ethics approved"):
        assert bad not in text.lower()


def test_status_document_matches_reality(app_dir):
    text = _read(app_dir, "REMEDIATION_STATUS.md")
    gates = text.split("## Gate before real patient data", 1)[1]
    assert "not met" in gates                      # S1-1
    assert "determination pending" in gates.lower()  # IRB: requested, not granted
    assert "no independent audit" in gates.lower()
    assert "In force" in gates or "in force" in gates


def test_gate_document_points_at_the_approved_pathway(app_dir):
    text = _read(app_dir, "docs/GATE_OPTIONS.md")
    assert "1A + 2A + 3A + 4A" in text or "1A 2A 3A 4A" in text
