#!/usr/bin/env python3
"""Pure functions for PASSION evaluation metrics.

This module provides pure, testable functions for computing PASSION-specific
metrics from raw prediction records. No ML framework dependencies.

PASSION is an external fairness cohort measuring escalation behaviour on
dark skin (Fitzpatrick III-VI). Since all PASSION lesions are benign
inflammatory conditions (no melanoma, no Kaposi sarcoma), we report:

- urgent_lane_rate: proportion of cases sent to urgent lane (vs routine/follow-up)
- lane_distribution: counts per lane (routine, follow_up, urgent) by stratum
- patient_level_aggregation: metrics aggregated by subject_id (one subject = one vote)

An empty stratum returns "not yet measured" rather than 0.0 to distinguish
absence of data from a true zero rate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

# Triage lane indices
TRIAGE_LANES = ["routine", "follow_up", "urgent"]
TRIAGE_NAMES = TRIAGE_LANES  # Alias for compatibility

# PASSION condition groups
PASSION_CONDITIONS = ["Eczema", "Fungal", "Scabies", "Others"]


@dataclass
class PredictionRecord:
    """A single prediction record for metric computation."""
    subject_id: str
    condition: str
    fitzpatrick: int
    triage_lane: int  # 0=routine, 1=follow_up, 2=urgent


def compute_urgent_lane_rate(records: list[PredictionRecord]) -> dict[str, Any]:
    """Compute urgent lane rate overall and by stratum.

    Args:
        records: List of PredictionRecord objects

    Returns:
        Dict with keys:
        - 'overall': float or "not yet measured"
        - 'by_fitzpatrick': dict[int, float | str]
        - 'by_condition': dict[str, float | str]
    """
    if not records:
        return {
            "overall": "not yet measured",
            "by_fitzpatrick": {},
            "by_condition": {},
        }

    # Overall
    total = len(records)
    urgent_count = sum(1 for r in records if r.triage_lane == 2)
    overall = urgent_count / total if total > 0 else "not yet measured"

    # By Fitzpatrick
    by_fitz = defaultdict(lambda: {"total": 0, "urgent": 0})
    for r in records:
        by_fitz[r.fitzpatrick]["total"] += 1
        if r.triage_lane == 2:
            by_fitz[r.fitzpatrick]["urgent"] += 1

    by_fitz_result = {}
    for fitz, counts in sorted(by_fitz.items()):
        if counts["total"] > 0:
            by_fitz_result[fitz] = counts["urgent"] / counts["total"]
        else:
            by_fitz_result[fitz] = "not yet measured"

    # By condition
    by_cond = defaultdict(lambda: {"total": 0, "urgent": 0})
    for r in records:
        by_cond[r.condition]["total"] += 1
        if r.triage_lane == 2:
            by_cond[r.condition]["urgent"] += 1

    by_cond_result = {}
    for cond, counts in sorted(by_cond.items()):
        if counts["total"] > 0:
            by_cond_result[cond] = counts["urgent"] / counts["total"]
        else:
            by_cond_result[cond] = "not yet measured"

    return {
        "overall": overall,
        "by_fitzpatrick": by_fitz_result,
        "by_condition": by_cond_result,
    }


def compute_lane_distribution(records: list[PredictionRecord]) -> dict[str, Any]:
    """Compute triage lane distribution overall and by stratum.

    Args:
        records: List of PredictionRecord objects

    Returns:
        Dict with keys:
        - 'overall': dict[str, int] (lane -> count)
        - 'by_fitzpatrick': dict[int, dict[str, int]]
        - 'by_condition': dict[str, dict[str, int]]
    """
    if not records:
        return {
            "overall": {lane: 0 for lane in TRIAGE_LANES},
            "by_fitzpatrick": {},
            "by_condition": {},
        }

    # Overall
    overall = {lane: 0 for lane in TRIAGE_LANES}
    for r in records:
        if 0 <= r.triage_lane < len(TRIAGE_LANES):
            overall[TRIAGE_LANES[r.triage_lane]] += 1

    # By Fitzpatrick
    by_fitz = defaultdict(lambda: {lane: 0 for lane in TRIAGE_LANES})
    for r in records:
        if 0 <= r.triage_lane < len(TRIAGE_LANES):
            by_fitz[r.fitzpatrick][TRIAGE_LANES[r.triage_lane]] += 1

    by_fitz_result = {fitz: dict(counts) for fitz, counts in sorted(by_fitz.items())}

    # By condition
    by_cond = defaultdict(lambda: {lane: 0 for lane in TRIAGE_LANES})
    for r in records:
        if 0 <= r.triage_lane < len(TRIAGE_LANES):
            by_cond[r.condition][TRIAGE_LANES[r.triage_lane]] += 1

    by_cond_result = {cond: dict(counts) for cond, counts in sorted(by_cond.items())}

    return {
        "overall": overall,
        "by_fitzpatrick": by_fitz_result,
        "by_condition": by_cond_result,
    }


def compute_patient_level_aggregation(
    image_records: list[PredictionRecord]
) -> list[PredictionRecord]:
    """Aggregate image-level predictions to patient-level by subject_id.

    Uses majority vote for triage lane (ties broken by highest lane index).
    Condition and Fitzpatrick are taken from the first record (assumed consistent).

    Args:
        image_records: List of image-level PredictionRecord objects

    Returns:
        List of patient-level PredictionRecord objects (one per subject_id)
    """
    if not image_records:
        return []

    # Group by subject_id
    by_subject = defaultdict(list)
    for r in image_records:
        by_subject[r.subject_id].append(r)

    patient_records = []
    for subject_id, records in by_subject.items():
        # Majority vote for triage lane
        triage_votes = [r.triage_lane for r in records]
        # Count votes per lane
        vote_counts = defaultdict(int)
        for v in triage_votes:
            vote_counts[v] += 1
        # Tie-break: highest lane index wins
        patient_triage = max(vote_counts.items(), key=lambda x: (x[1], x[0]))[0]

        # Condition and Fitzpatrick from first record (assumed same for all images)
        first = records[0]
        patient_records.append(PredictionRecord(
            subject_id=subject_id,
            condition=first.condition,
            fitzpatrick=first.fitzpatrick,
            triage_lane=patient_triage,
        ))

    return patient_records


def compute_all_metrics(
    image_records: list[PredictionRecord]
) -> dict[str, Any]:
    """Compute all PASSION metrics at image and patient level.

    Args:
        image_records: List of image-level PredictionRecord objects

    Returns:
        Dict with all metrics, suitable for JSON serialization
    """
    # Image-level metrics
    image_urgent = compute_urgent_lane_rate(image_records)
    image_lanes = compute_lane_distribution(image_records)

    # Patient-level metrics
    patient_records = compute_patient_level_aggregation(image_records)
    patient_urgent = compute_urgent_lane_rate(patient_records)
    patient_lanes = compute_lane_distribution(patient_records)

    return {
        "image_level": {
            "urgent_lane_rate": image_urgent,
            "lane_distribution": image_lanes,
        },
        "patient_level": {
            "urgent_lane_rate": patient_urgent,
            "lane_distribution": patient_lanes,
            "total_subjects": len(patient_records),
        },
    }


# --- Test fixtures with known answers ---

def build_test_fixture_basic() -> list[PredictionRecord]:
    """Build a basic test fixture with known answers.

    4 cases: 1 urgent, 1 follow_up, 2 routine
    2 Fitzpatrick types (4, 5)
    2 conditions (Eczema, Fungal)
    Expected: urgent_lane_rate = 0.25
    """
    return [
        PredictionRecord("subj_1", "Eczema", 4, 2),   # urgent
        PredictionRecord("subj_2", "Eczema", 4, 1),   # follow_up
        PredictionRecord("subj_3", "Fungal", 5, 0),   # routine
        PredictionRecord("subj_4", "Fungal", 5, 0),   # routine
    ]


def build_test_fixture_patient_aggregation() -> list[PredictionRecord]:
    """Build test fixture for patient-level aggregation.

    1 subject with 5 images: 2 routine, 3 urgent -> majority urgent
    1 subject with 3 images: 2 follow_up, 1 routine -> majority follow_up
    Expected: 2 subjects, 1 urgent, 1 follow_up
    """
    return [
        # Subject A: 5 images
        PredictionRecord("subj_A", "Eczema", 4, 0),  # routine
        PredictionRecord("subj_A", "Eczema", 4, 0),  # routine
        PredictionRecord("subj_A", "Eczema", 4, 2),  # urgent
        PredictionRecord("subj_A", "Eczema", 4, 2),  # urgent
        PredictionRecord("subj_A", "Eczema", 4, 2),  # urgent
        # Subject B: 3 images
        PredictionRecord("subj_B", "Fungal", 5, 1),  # follow_up
        PredictionRecord("subj_B", "Fungal", 5, 1),  # follow_up
        PredictionRecord("subj_B", "Fungal", 5, 0),  # routine
    ]


def build_test_fixture_empty_stratum() -> list[PredictionRecord]:
    """Build test fixture with an empty Fitzpatrick stratum.

    Only Fitzpatrick 4 and 5 present, no 3 or 6.
    """
    return [
        PredictionRecord("subj_1", "Eczema", 4, 0),  # routine
        PredictionRecord("subj_2", "Fungal", 5, 2),  # urgent
    ]


if __name__ == "__main__":
    # Quick self-test
    print("=== Basic fixture ===")
    records = build_test_fixture_basic()
    metrics = compute_all_metrics(records)
    import json
    print(json.dumps(metrics, indent=2, default=str))

    print("\n=== Patient aggregation fixture ===")
    records = build_test_fixture_patient_aggregation()
    metrics = compute_all_metrics(records)
    print(json.dumps(metrics, indent=2, default=str))

    print("\n=== Empty stratum fixture ===")
    records = build_test_fixture_empty_stratum()
    metrics = compute_all_metrics(records)
    print(json.dumps(metrics, indent=2, default=str))