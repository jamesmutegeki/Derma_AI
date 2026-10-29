"""S0-5 -- metrics are computed, never fabricated.

Acceptance criteria
-------------------
1. A case's prediction is never used as its ground truth.
2. Clinical accuracy is computed only over *confirmed* ground truth; with no
   confirmed case it is ``None`` (not ``0.0``, not a hard-coded number).
3. Model-vs-clinician agreement is reported separately from accuracy.
4. Fitzpatrick groups with no cases are ``None`` and excluded from the accuracy
   gap instead of being averaged in as zero accuracy.
5. ``/api/analytics`` on an empty database reports zero cases and no accuracy.
"""

from __future__ import annotations

import pytest

from metrics_tracker import CaseRecord, FairnessTracker
from storage import Store


@pytest.fixture()
def tracker(tmp_path):
    store = Store(tmp_path / "data")
    yield FairnessTracker(store, export_path=str(tmp_path / "cases.csv"))
    store.close()


def _case(**kwargs) -> CaseRecord:
    base = dict(case_id="case-1", fitz_type=4, predicted_label=1, model_triage=2)
    base.update(kwargs)
    return CaseRecord(**base)


def test_prediction_is_not_ground_truth(tracker):
    tracker.register_case(CaseRecord(case_id="c1", fitz_type=4, predicted_label=2, model_triage=2))
    metrics = tracker.compute_metrics()
    assert metrics["total_cases"] == 1
    assert metrics["confirmed_cases"] == 0
    assert metrics["clinical_accuracy"] is None
    assert metrics["per_type"]["fitz_4"]["accuracy"] is None


def test_accuracy_only_counts_confirmed_cases(tracker):
    tracker.register_case(_case(case_id="c1", model_triage=2))
    tracker.register_case(_case(case_id="c2", model_triage=2))
    tracker.confirm_ground_truth("c1", 0, source="biopsy")   # benign -> expected routine
    metrics = tracker.compute_metrics()
    assert metrics["confirmed_cases"] == 1
    assert metrics["clinical_accuracy"] == 0.0


def test_agreement_is_not_accuracy(tracker):
    tracker.register_case(_case(case_id="c1", model_triage=2))
    tracker.register_override("c1", clinician_triage=0)
    metrics = tracker.compute_metrics()
    assert metrics["model_vs_clinician_agreement"] == 0.0
    assert metrics["clinical_accuracy"] is None
    assert metrics["override_rate"] == 1.0


def test_empty_fitz_groups_are_none_and_excluded_from_the_gap(tracker):
    tracker.register_case(_case(case_id="c1", fitz_type=4, model_triage=2))
    tracker.register_case(_case(case_id="c2", fitz_type=4, model_triage=2))
    tracker.confirm_ground_truth("c1", 1, source="biopsy")   # melanoma -> urgent = correct
    tracker.confirm_ground_truth("c2", 0, source="biopsy")   # benign -> urgent = wrong
    metrics = tracker.compute_metrics()

    assert metrics["per_type"]["fitz_1"]["count"] == 0
    assert metrics["per_type"]["fitz_1"]["accuracy"] is None
    assert metrics["per_type"]["fitz_4"]["accuracy"] == 0.5
    assert "fitz_1" not in (metrics.get("demographic_parity") or {})
    assert "fitz_1" not in (metrics.get("equalized_odds") or {})


def test_no_fabricated_numbers_anywhere(tracker):
    metrics = tracker.compute_metrics()
    assert metrics["total_cases"] == 0
    assert metrics["clinical_accuracy"] is None
    assert metrics["accuracy_gap"] is None
    assert metrics["override_rate"] == 0.0
    assert any("No cases" in note for note in metrics["notes"])

    # The review's fabricated figures must not reappear.
    blob = repr(metrics)
    for fake in ("0.843", "0.027", "84.3"):
        assert fake not in blob


def test_analytics_endpoint_is_empty_and_honest(client, make_doctor, auth):
    token, _doctor = make_doctor()
    response = client.get("/api/analytics", headers=auth(token))
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["total_cases"] == 0
    assert metrics["clinical_accuracy"] is None
    assert metrics["accuracy_gap"] is None
