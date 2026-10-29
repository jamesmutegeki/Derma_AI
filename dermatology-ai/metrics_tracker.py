"""Fairness / performance metrics over registered cases.

Ground-truth rules (this is the core correctness fix of the review):

* A case's *prediction* is never used as its ground truth.  ``predicted_label``
  is what the model said; ``ground_truth_label`` is set only when a clinician
  confirms it (biopsy / expert review) and ``ground_truth_confirmed`` is true.
* ``clinical_accuracy`` is computed **only** over confirmed cases.
* Agreement between the model and the clinician is reported separately as
  ``model_vs_clinician_agreement`` -- it is not accuracy.
* Empty Fitzpatrick groups are reported as ``None`` and excluded from the
  accuracy gap instead of being averaged in as 0.0 accuracy.

The module is torch-free: it can be used by the API and by tests without the
deep-learning stack installed.
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from constants import (
    FITZPATRICK_LABELS,
    NUM_FITZ_TYPES,
    TRIAGE_NAMES,
    TRUE_LABEL_TO_TRIAGE,
)

logger = logging.getLogger(__name__)

MALIGNANT_LABELS = (1, 2)


@dataclass
class CaseRecord:
    case_id: str
    fitz_type: int
    #: Model output (0 benign, 1 melanoma, 2 Kaposi sarcoma).  Never ground truth.
    predicted_label: Optional[int] = None
    model_triage: Optional[int] = None
    #: Set only when a clinician has confirmed the diagnosis.
    ground_truth_label: Optional[int] = None
    ground_truth_confirmed: bool = False
    clinician_triage: Optional[int] = None
    is_override: bool = False
    reward: float = 0.0
    concepts: List[float] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    offline_updated: bool = False
    source: str = "live"
    #: Free-text note for why the ground truth is (or is not) confirmed.
    ground_truth_source: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        cleaned = {k: v for k, v in data.items() if k in known}
        # Legacy records stored the model output as ``true_label``; that was the
        # bug this class exists to prevent, so it is deliberately not migrated
        # into ground truth.
        cleaned.pop("true_label", None)
        return cls(**cleaned)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FairnessTracker:
    """Case registry backed by :class:`storage.Store`."""

    LEGACY_LABEL = "Fitz I-III"
    TARGET_LABEL = "Fitz IV-VI"

    def __init__(self, store, export_path: Optional[str] = None):
        self.store = store
        self.export_path = export_path

    # ------------------------------------------------------------------
    #  Registration
    # ------------------------------------------------------------------

    def register_case(self, record: CaseRecord) -> CaseRecord:
        self.store.add_case(record.to_dict())
        return record

    def register_override(self, case_id: str, clinician_triage: int) -> bool:
        cases = self.store.list_cases()
        for case in reversed(cases):
            if case.get("case_id") == case_id:
                model_triage = case.get("model_triage")
                self.store.update_case(case_id, {
                    "clinician_triage": clinician_triage,
                    "is_override": model_triage != clinician_triage,
                })
                return True
        return False

    def confirm_ground_truth(self, case_id: str, label: int, source: str = "clinician") -> bool:
        if label not in (0, 1, 2):
            raise ValueError("ground truth label must be 0, 1 or 2")
        updated = self.store.update_case(case_id, {
            "ground_truth_label": label,
            "ground_truth_confirmed": True,
            "ground_truth_source": source,
        })
        return updated is not None

    @property
    def cases(self) -> List[CaseRecord]:
        return [CaseRecord.from_dict(c) for c in self.store.list_cases()]

    def snapshot(self, tag: str = "") -> None:
        snapshots = self.store.get_kv("snapshots", []) or []
        snapshots.append({
            "tag": tag,
            **self.compute_metrics(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.store.set_kv("snapshots", snapshots[-200:])

    @property
    def snapshots(self) -> List[dict]:
        return self.store.get_kv("snapshots", []) or []

    def reset(self) -> int:
        removed = self.store.clear_cases()
        self.store.set_kv("snapshots", [])
        return removed

    # ------------------------------------------------------------------
    #  Metrics
    # ------------------------------------------------------------------

    def compute_metrics(self) -> dict:
        records = self.cases
        if not records:
            return {
                "total_cases": 0,
                "confirmed_cases": 0,
                "clinical_accuracy": None,
                "model_vs_clinician_agreement": None,
                "override_rate": 0.0,
                "accuracy_gap": None,
                "per_type": {f"fitz_{i}": _empty_group() for i in range(1, NUM_FITZ_TYPES + 1)},
                "demographic_parity": {},
                "equalized_odds": {},
                "notes": ["No cases registered yet."],
            }

        by_type: Dict[int, List[CaseRecord]] = defaultdict(list)
        for record in records:
            by_type[record.fitz_type].append(record)

        per_type: dict[str, dict] = {}
        gap_groups: Dict[int, Optional[float]] = {}

        for fitz in range(1, NUM_FITZ_TYPES + 1):
            group = by_type.get(fitz, [])
            confirmed = [c for c in group if c.ground_truth_confirmed and c.ground_truth_label is not None]
            triaged = [c for c in group if c.model_triage is not None]
            overridden = [c for c in group if c.is_override]

            if not group:
                per_type[f"fitz_{fitz}"] = _empty_group()
                gap_groups[fitz] = None
                continue

            correct = [
                c for c in confirmed
                if TRUE_LABEL_TO_TRIAGE[c.ground_truth_label] == c.model_triage
            ]
            accuracy = round(len(correct) / len(confirmed), 4) if confirmed else None
            gap_groups[fitz] = accuracy

            # Clinical recall over confirmed malignant cases (safety metric).
            malignant = [c for c in confirmed if c.ground_truth_label in MALIGNANT_LABELS]
            malignant_urgent = [
                c for c in malignant if c.model_triage == 2
            ]
            critical_miss_rate = (
                round(1 - len(malignant_urgent) / len(malignant), 4) if malignant else None
            )

            per_type[f"fitz_{fitz}"] = {
                "count": len(group),
                "confirmed_count": len(confirmed),
                "accuracy": accuracy,
                "urgent_rate": round(
                    sum(1 for c in triaged if c.model_triage == 2) / len(triaged), 4
                ) if triaged else None,
                "critical_miss_rate": critical_miss_rate,
                "override_rate": round(len(overridden) / len(group), 4),
            }

        confirmed_all = [c for c in records if c.ground_truth_confirmed and c.ground_truth_label is not None]
        clinical_accuracy = None
        if confirmed_all:
            clinical_accuracy = round(
                sum(
                    1 for c in confirmed_all
                    if TRUE_LABEL_TO_TRIAGE[c.ground_truth_label] == c.model_triage
                ) / len(confirmed_all),
                4,
            )

        comparable = [c for c in records if c.clinician_triage is not None and c.model_triage is not None]
        agreement = round(
            sum(1 for c in comparable if c.clinician_triage == c.model_triage) / len(comparable), 4
        ) if comparable else None

        group_accuracies = [v for v in gap_groups.values() if v is not None]
        complete = len(group_accuracies) == NUM_FITZ_TYPES
        accuracy_gap = None
        legacy_accuracy = None
        target_accuracy = None
        if complete:
            legacy_accuracy = round(float(np.mean([gap_groups[i] for i in (1, 2, 3)])), 4)
            target_accuracy = round(float(np.mean([gap_groups[i] for i in (4, 5, 6)])), 4)
            accuracy_gap = round(legacy_accuracy - target_accuracy, 4)

        demographic_parity = {}
        equalized_odds = {}
        for fitz in range(1, NUM_FITZ_TYPES + 1):
            group = by_type.get(fitz, [])
            triaged = [c for c in group if c.model_triage is not None]
            if triaged:
                demographic_parity[FITZPATRICK_LABELS[fitz - 1]] = round(
                    sum(1 for c in triaged if c.model_triage == 2) / len(triaged), 4
                )
            confirmed_malignant = [
                c for c in group
                if c.ground_truth_confirmed and c.ground_truth_label in MALIGNANT_LABELS
                and c.model_triage is not None
            ]
            if confirmed_malignant:
                equalized_odds[FITZPATRICK_LABELS[fitz - 1]] = round(
                    sum(1 for c in confirmed_malignant if c.model_triage == 2) / len(confirmed_malignant), 4
                )

        notes: list[str] = []
        if not confirmed_all:
            notes.append(
                "No biopsy-confirmed ground truth yet: clinical_accuracy is undefined. "
                "model_vs_clinician_agreement is reported instead."
            )
        elif not complete:
            missing = [FITZPATRICK_LABELS[i - 1] for i, v in gap_groups.items() if v is None]
            notes.append(f"Accuracy gap not reported: no confirmed cases for Fitzpatrick {', '.join(missing)}.")

        return {
            "total_cases": len(records),
            "confirmed_cases": len(confirmed_all),
            "clinical_accuracy": clinical_accuracy,
            "model_vs_clinician_agreement": agreement,
            "override_rate": round(sum(1 for c in records if c.is_override) / len(records), 4),
            "accuracy_gap": accuracy_gap,
            "legacy_accuracy": legacy_accuracy,
            "target_accuracy": target_accuracy,
            "critical_miss_rate": per_type and _overall_critical_miss(confirmed_all),
            "per_type": per_type,
            "demographic_parity": demographic_parity,
            "equalized_odds": equalized_odds,
            "notes": notes,
        }

    # ------------------------------------------------------------------
    #  Plot helpers (plotly-compatible figures)
    # ------------------------------------------------------------------

    def accuracy_by_type_chart(self):
        import plotly.graph_objects as go

        per_type = self.compute_metrics().get("per_type", {})
        types = list(FITZPATRICK_LABELS)
        values = [
            per_type.get(f"fitz_{i}", {}).get("accuracy") for i in range(1, NUM_FITZ_TYPES + 1)
        ]
        plotted = [0.0 if v is None else v for v in values]
        labels = ["n/a" if v is None else f"{v:.1%}" for v in values]
        colors = ["#4CAF50" if i < 4 else "#FF9800" for i in range(1, NUM_FITZ_TYPES + 1)]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=types, y=plotted, marker_color=colors, text=labels, textposition="outside"))
        fig.update_layout(
            title="Clinical accuracy by Fitzpatrick type (confirmed cases only)",
            yaxis=dict(tickformat=".0%", range=[0, 1.1]),
            height=400,
        )
        return fig

    def urgent_rate_chart(self):
        import plotly.graph_objects as go

        parity = self.compute_metrics().get("demographic_parity", {})
        types = list(FITZPATRICK_LABELS)
        rates = [parity.get(t) or 0.0 for t in types]
        colors = ["#4CAF50" if i < 4 else "#e74c3c" for i in range(1, NUM_FITZ_TYPES + 1)]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=types, y=rates, marker_color=colors, text=[f"{r:.1%}" for r in rates], textposition="outside"))
        fig.update_layout(
            title="Demographic parity: urgent-triage rate by Fitzpatrick type",
            yaxis=dict(tickformat=".0%", range=[0, 1]),
            height=400,
        )
        return fig

    def confusion_matrix_chart(self):
        import plotly.figure_factory as ff

        matrix = np.zeros((len(TRIAGE_NAMES), len(TRIAGE_NAMES)), dtype=int)
        for case in self.cases:
            if not case.ground_truth_confirmed or case.ground_truth_label is None:
                continue
            if case.model_triage is None or not 0 <= case.model_triage < len(TRIAGE_NAMES):
                continue
            expected = TRUE_LABEL_TO_TRIAGE[case.ground_truth_label]
            matrix[expected, case.model_triage] += 1
        fig = ff.create_annotated_heatmap(
            matrix, x=TRIAGE_NAMES, y=TRIAGE_NAMES, colorscale="Blues", showscale=True
        )
        fig.update_layout(title="Triage confusion matrix (confirmed cases)", height=400)
        return fig

    def override_pie(self):
        import plotly.graph_objects as go

        metrics = self.compute_metrics()
        total = metrics.get("total_cases", 0)
        rate = metrics.get("override_rate", 0.0) or 0.0
        n_override = round(total * rate)
        fig = go.Figure(go.Pie(
            labels=["Agreed with model", "Clinician override"],
            values=[max(total - n_override, 0), n_override],
            marker_colors=["#4CAF50", "#FF9800"],
            hole=0.4,
        ))
        fig.update_layout(title=f"Clinician override rate ({rate:.1%})", height=300)
        return fig

    def trend_chart(self):
        import plotly.graph_objects as go

        snapshots = self.snapshots
        if len(snapshots) < 2:
            return None
        times = [s.get("timestamp", str(i)) for i, s in enumerate(snapshots)]
        accuracy = [s.get("clinical_accuracy") for s in snapshots]
        agreement = [s.get("model_vs_clinician_agreement") for s in snapshots]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times, y=[a if a is not None else None for a in accuracy],
            mode="lines+markers", name="Clinical accuracy", line=dict(color="green"),
        ))
        fig.add_trace(go.Scatter(
            x=times, y=[a if a is not None else None for a in agreement],
            mode="lines+markers", name="Model/clinician agreement", line=dict(color="blue"),
        ))
        fig.update_layout(title="Metric trends", yaxis=dict(tickformat=".0%"), height=350)
        return fig

    # ------------------------------------------------------------------
    #  Export
    # ------------------------------------------------------------------

    def export_csv(self, path: Optional[str] = None) -> str:
        target = path or self.export_path or "case_history.csv"
        rows = [case.to_dict() for case in self.cases]
        with open(target, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "case_id", "timestamp", "fitz_type", "predicted_label", "model_triage",
                "ground_truth_label", "ground_truth_confirmed", "clinician_triage",
                "is_override", "source",
            ])
            for row in rows:
                writer.writerow([
                    row["case_id"], row["timestamp"], row["fitz_type"],
                    _blank(row["predicted_label"]), _blank(row["model_triage"]),
                    _blank(row["ground_truth_label"]), row["ground_truth_confirmed"],
                    _blank(row["clinician_triage"]), row["is_override"], row["source"],
                ])
        return target


def _blank(value):
    return "" if value is None else value


def _empty_group() -> dict:
    return {
        "count": 0,
        "confirmed_count": 0,
        "accuracy": None,
        "urgent_rate": None,
        "critical_miss_rate": None,
        "override_rate": None,
    }


def _overall_critical_miss(confirmed) -> Optional[float]:
    malignant = [c for c in confirmed if c.ground_truth_label in MALIGNANT_LABELS]
    if not malignant:
        return None
    missed = sum(1 for c in malignant if c.model_triage != 2)
    return round(missed / len(malignant), 4)
