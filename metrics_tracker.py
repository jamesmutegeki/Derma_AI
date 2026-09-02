"""
Fairness Metrics Tracker — monitors accuracy gap & FN rates across
Fitzpatrick skin types to ensure equity for darker skin (IV-VI).

Tracks every case processed, accumulates per-type confusion matrices,
and exposes plotly charts for the analytics dashboard.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from rl_module import FITZPATRICK_LABELS, TRUE_LABEL_TO_TRIAGE, TRIAGE_NAMES


@dataclass
class CaseRecord:
    case_id: str
    fitz_type: int
    true_label: int
    model_triage: int
    clinician_triage: Optional[int] = None
    is_override: bool = False
    reward: float = 0.0
    concepts: List[float] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    offline_updated: bool = False


class FairnessTracker:
    LEGACY_LABEL = "Fitz I-III"
    TARGET_LABEL = "Fitz IV-VI"

    def __init__(self, persist_path: Optional[str] = "case_history.json"):
        self.persist_path = persist_path
        self.cases: List[CaseRecord] = []
        self._snapshots: List[dict] = []  # metric snapshots for trend analysis
        self._load()

    # ------------------------------------------------------------------
    #  Registration
    # ------------------------------------------------------------------

    def register_case(self, record: CaseRecord):
        self.cases.append(record)

    def register_override(self, case_id: str, clinician_triage: int):
        for c in reversed(self.cases):
            if c.case_id == case_id:
                c.clinician_triage = clinician_triage
                c.is_override = c.model_triage != clinician_triage
                c.reward = 0.0  # will be recomputed when needed
                break

    def snapshot(self, tag: str = ""):
        self._snapshots.append({"tag": tag, **self.compute_metrics(), "timestamp": datetime.now(timezone.utc).isoformat()})

    # ------------------------------------------------------------------
    #  Core metrics
    # ------------------------------------------------------------------

    def compute_metrics(self) -> dict:
        if not self.cases:
            return {}

        by_type: Dict[int, List[CaseRecord]] = defaultdict(list)
        for c in self.cases:
            by_type[c.fitz_type].append(c)

        per_type = {}
        total_tp = total_tn = total_fp = total_fn = 0

        for ft in range(1, 7):
            recs = by_type.get(ft, [])
            if not recs:
                per_type[f"fitz_{ft}"] = {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0, "fn_rate": 0.0, "fp_rate": 0.0, "count": 0}
                continue

            tp = tn = fp = fn = 0
            for r in recs:
                expected = TRUE_LABEL_TO_TRIAGE[r.true_label]
                actual = r.clinician_triage if r.is_override else r.model_triage
                if actual == expected:
                    if expected == 2:
                        tp += 1
                    else:
                        tn += 1
                else:
                    if expected == 2:
                        fn += 1
                    else:
                        fp += 1

            total_tp += tp; total_tn += tn; total_fp += fp; total_fn += fn
            n = len(recs)
            acc = (tp + tn) / max(n, 1)
            prec = tp / max(tp + fp, 1)
            rec = tp / max(tp + fn, 1)
            f1_v = 2 * prec * rec / max(prec + rec, 1e-8)
            per_type[f"fitz_{ft}"] = {
                "accuracy": round(acc, 4),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1_v, 4),
                "fn_rate": round(fn / max(fn + tp, 1), 4),
                "fp_rate": round(fp / max(fp + tn, 1), 4),
                "count": n,
            }

        # Aggregate
        n_total = len(self.cases)
        overall_acc = (total_tp + total_tn) / max(n_total, 1)
        overall_prec = total_tp / max(total_tp + total_fp, 1)
        overall_rec = total_tp / max(total_tp + total_fn, 1)
        overall_f1 = 2 * overall_prec * overall_rec / max(overall_prec + overall_rec, 1e-8)

        # Accuracy gap: I-III vs IV-VI
        legacy = [per_type.get(f"fitz_{i}", {}).get("accuracy", 0) for i in range(1, 4)]
        target = [per_type.get(f"fitz_{i}", {}).get("accuracy", 0) for i in range(4, 7)]
        legacy_acc = np.mean(legacy) if legacy else 0
        target_acc = np.mean(target) if target else 0
        accuracy_gap = round(legacy_acc - target_acc, 4)

        # Weighted FN rate
        fn_rates = [per_type.get(f"fitz_{i}", {}).get("fn_rate", 0) for i in range(1, 7)]

        # Override rate
        override_count = sum(1 for c in self.cases if c.is_override)
        override_rate = override_count / max(n_total, 1)

        result = {
            "total_cases": n_total,
            "overall_accuracy": round(overall_acc, 4),
            "overall_precision": round(overall_prec, 4),
            "overall_recall": round(overall_rec, 4),
            "overall_f1": round(overall_f1, 4),
            "accuracy_gap": accuracy_gap,
            "legacy_accuracy": round(legacy_acc, 4),
            "target_accuracy": round(target_acc, 4),
            "override_count": override_count,
            "override_rate": round(override_rate, 4),
            "fn_rate_by_type": {f"fitz_{i}": r["fn_rate"] for i, r in per_type.items()},
            "accuracy_by_type": {f"fitz_{i}": r["accuracy"] for i, r in per_type.items()},
            "per_type": per_type,
        }
        return result

    # ------------------------------------------------------------------
    #  Plot helpers (return plotly-compatible dicts)
    # ------------------------------------------------------------------

    def accuracy_by_type_chart(self) -> dict:
        import plotly.graph_objects as go

        metrics = self.compute_metrics().get("per_type", {})
        types = [FITZPATRICK_LABELS[i - 1] for i in range(1, 7)]
        accs = [metrics.get(f"fitz_{i}", {}).get("accuracy", 0) for i in range(1, 7)]
        colors = ["#4CAF50" if i < 4 else "#FF9800" for i in range(1, 7)]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=types, y=accs, marker_color=colors, text=[f"{a:.1%}" for a in accs], textposition="outside"))
        fig.add_hline(y=np.mean(accs[:3]), line_dash="dot", line_color="green", annotation_text="Avg I-III")
        fig.add_hline(y=np.mean(accs[3:]), line_dash="dot", line_color="red", annotation_text="Avg IV-VI")

        fig.update_layout(title="Triage Accuracy by Fitzpatrick Type", yaxis_title="Accuracy", yaxis=dict(tickformat=".0%", range=[0, 1.1]), height=400, margin=dict(l=40, r=40, t=50, b=40))
        return fig

    def fn_rate_chart(self) -> dict:
        import plotly.graph_objects as go

        metrics = self.compute_metrics().get("per_type", {})
        types = [FITZPATRICK_LABELS[i - 1] for i in range(1, 7)]
        rates = [metrics.get(f"fitz_{i}", {}).get("fn_rate", 0) for i in range(1, 7)]
        colors = ["#4CAF50" if i < 4 else "#e74c3c" for i in range(1, 7)]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=types, y=rates, marker_color=colors, text=[f"{r:.1%}" for r in rates], textposition="outside"))
        fig.update_layout(title="False Negative Rate by Fitzpatrick Type<br><sub>Critical equity metric — lower is better</sub>", yaxis_title="FN Rate", yaxis=dict(tickformat=".0%", range=[0, 1]), height=400, margin=dict(l=40, r=40, t=60, b=40))
        return fig

    def accuracy_gauge(self) -> dict:
        import plotly.graph_objects as go

        gap = self.compute_metrics().get("accuracy_gap", 0)
        color = "green" if gap <= 0.02 else ("orange" if gap <= 0.05 else "red")

        fig = go.Figure(go.Indicator(mode="gauge+number+delta", value=max(gap, 0), delta={"reference": 0, "increasing": {"color": "red"}}, gauge={"axis": {"range": [0, 0.2], "tickformat": ".0%"}, "bar": {"color": color}, "steps": [{"range": [0, 0.02], "color": "#e8f5e9"}, {"range": [0.02, 0.05], "color": "#fff3e0"}, {"range": [0.05, 0.2], "color": "#ffebee"}], "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": gap}}))
        fig.update_layout(title={"text": "Accuracy Gap (I-III − IV-VI)<br><sub>Target: ≤ 2%</sub>"}, height=300)
        return fig

    def confusion_matrix_chart(self) -> dict:
        import plotly.figure_factory as ff

        cm = np.zeros((3, 3), dtype=int)
        for c in self.cases:
            actual = c.clinician_triage if c.is_override else c.model_triage
            expected = TRUE_LABEL_TO_TRIAGE[c.true_label]
            cm[expected, actual] += 1

        fig = ff.create_annotated_heatmap(cm, x=TRIAGE_NAMES, y=TRIAGE_NAMES, colorscale="Blues", showscale=True)
        fig.update_layout(title="Confusion Matrix (Expected vs Actual Triage)", height=400)
        return fig

    def override_pie(self) -> dict:
        import plotly.graph_objects as go

        n_override = sum(1 for c in self.cases if c.is_override)
        n_agree = len(self.cases) - n_override
        fig = go.Figure(go.Pie(labels=["Agreed with Model", "Clinician Override"], values=[n_agree, n_override], marker_colors=["#4CAF50", "#FF9800"], hole=0.4))
        fig.update_layout(title=f"Clinician Override Rate ({self.compute_metrics().get('override_rate', 0):.1%})", height=300)
        return fig

    def trend_chart(self) -> Optional[dict]:
        import plotly.graph_objects as go

        if len(self._snapshots) < 2:
            return None
        times = [s.get("timestamp", str(i)) for i, s in enumerate(self._snapshots)]
        gaps = [s.get("accuracy_gap", 0) for s in self._snapshots]
        accs = [s.get("overall_accuracy", 0) for s in self._snapshots]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=times, y=gaps, mode="lines+markers", name="Accuracy Gap", line=dict(color="red")))
        fig.add_trace(go.Scatter(x=times, y=accs, mode="lines+markers", name="Overall Accuracy", line=dict(color="green")))
        fig.update_layout(title="Metric Trends Over Time", xaxis_title="Snapshot", yaxis_title="Value", yaxis=dict(tickformat=".0%"), height=350)
        return fig

    # ------------------------------------------------------------------
    #  Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if self.persist_path and os.path.exists(self.persist_path):
            try:
                with open(self.persist_path) as f:
                    data = json.load(f)
                self.cases = [CaseRecord(**c) for c in data.get("cases", [])]
                self._snapshots = data.get("snapshots", [])
            except Exception:
                self.cases = []

    def save(self):
        if self.persist_path:
            with open(self.persist_path, "w") as f:
                json.dump({"cases": [asdict(c) for c in self.cases], "snapshots": self._snapshots}, f, indent=2, default=str)

    def export_csv(self, path: str = "case_history.csv"):
        rows = []
        for c in self.cases:
            rows.append({
                "case_id": c.case_id,
                "timestamp": c.timestamp,
                "fitz_type": c.fitz_type,
                "true_label": c.true_label,
                "model_triage": c.model_triage,
                "clinician_triage": c.clinician_triage if c.clinician_triage is not None else "",
                "is_override": c.is_override,
                "reward": c.reward,
            })
        pd.DataFrame(rows).to_csv(path, index=False)
