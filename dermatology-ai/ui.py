"""Legacy Gradio clinician UI (optional; the FastAPI dashboard is the main app).

Launch with ``python main.py --ui``.  Requires a real checkpoint: the UI will
refuse to start without ``MODEL_CHECKPOINT_PATH`` rather than show random
predictions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from PIL import Image as PILImage

try:  # optional dependency: the Gradio UI is not needed for the API/dashboard
    import gradio as gr
except ImportError:  # pragma: no cover - exercised only without gradio installed
    gr = None  # type: ignore[assignment]

from constants import FITZPATRICK_LABELS, TRIAGE_NAMES, TRUE_LABEL_NAMES
from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer
from metrics_tracker import CaseRecord, FairnessTracker
from model import CONCEPT_NAMES, DermatologyCBM, XAIExplainer
from rl_module import PPOAgent
from transforms import build_transform

logger = logging.getLogger(__name__)

TRIAGE_COLORS = {"routine": "#4CAF50", "follow_up": "#FF9800", "urgent": "#e74c3c"}

# Built on first use, not at import time: importing this module must not require
# albumentations/torchvision to be present.
_EVAL_TRANSFORM: Optional[object] = None


def eval_transform():
    global _EVAL_TRANSFORM
    if _EVAL_TRANSFORM is None:
        _EVAL_TRANSFORM = build_transform("eval")
    return _EVAL_TRANSFORM


class AppState:
    """Holds the model, agent and pipelines for the Gradio app."""

    def __init__(
        self,
        model: DermatologyCBM,
        ppo_agent: Optional[PPOAgent],
        hitl: Optional[HITLPipeline],
        offline_optimizer: Optional[OfflinePolicyOptimizer],
        tracker: FairnessTracker,
        device: torch.device,
        model_version: str = "",
        weights_sha256: str = "",
    ):
        self.model = model
        self.ppo_agent = ppo_agent
        self.hitl = hitl
        self.optimizer = offline_optimizer
        self.tracker = tracker
        self.device = device
        self.model_version = model_version
        self.weights_sha256 = weights_sha256
        self._xai = None
        self._case_counter = 0

    @property
    def xai(self):
        if self._xai is None:
            self._xai = XAIExplainer(self.model, self.device)
        return self._xai

    def next_case_id(self) -> str:
        self._case_counter += 1
        return f"UI-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{self._case_counter:04d}"


# ---------------------------------------------------------------------------
#  Preprocessing
# ---------------------------------------------------------------------------

def preprocess(image: np.ndarray, device: torch.device) -> torch.Tensor:
    """Deterministic, train-parity preprocessing (see TRANSFORM_PARITY.md)."""
    pil = PILImage.fromarray(image).convert("RGB")
    return eval_transform()(pil).unsqueeze(0).to(device)


# ---------------------------------------------------------------------------
#  Tab 1 - Diagnosis
# ---------------------------------------------------------------------------

EMPTY_DIAGNOSIS_OUTPUTS = (None, "Public. Upload an image.", "", "", {}, "", "", "")


def run_diagnosis(
    image: Optional[np.ndarray],
    fitz_dropdown: int,
    true_label_dropdown: int,
    state: AppState,
) -> Tuple:
    if image is None:
        return (None, "Please upload an image.", "", "", None, "", "", "")

    fitz_type = int(fitz_dropdown)
    tensor = preprocess(image, state.device)

    with torch.no_grad():
        logits, concepts = state.model(tensor)
        probabilities = torch.softmax(logits, dim=1)[0]
        pred_class = int(probabilities.argmax().item())
    concept_vector = concepts[0].cpu().numpy()

    concept_dict = {name: round(float(concept_vector[i]), 4) for i, name in enumerate(CONCEPT_NAMES)}

    try:
        state.model.eval()
        cam = state.xai.grad_cam(tensor.clone().requires_grad_())
        cam_resized = np.array(
            PILImage.fromarray((cam * 255).astype(np.uint8)).resize((image.shape[1], image.shape[0]))
        )
        overlay = (image * 0.5 + np.stack([cam_resized] * 3, axis=-1) * 0.5).astype(np.uint8)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Grad-CAM failed: %s", exc)
        overlay = image

    concept_md = "### Concept scores\n"
    for name in CONCEPT_NAMES:
        value = concept_dict[name]
        pct = int(value * 100)
        colour = "#e74c3c" if value > 0.6 else ("#f39c12" if value > 0.3 else "#4CAF50")
        label = name.replace("_", " ").title()
        concept_md += (
            f"**{label}**\n"
            f'<div style="background:#e0e0e0;border-radius:8px;height:20px;width:100%">'
            f'<div style="background:{colour};border-radius:8px;height:20px;width:{pct}%"></div>'
            f"</div> `{value:.2f}`\n\n"
        )

    model_action = None
    if state.ppo_agent is not None:
        state_vector = np.concatenate([concept_vector, np.eye(6, dtype=np.float32)[fitz_type - 1]])
        model_action = int(state.ppo_agent.evaluate(state_vector))
        triage_name = TRIAGE_NAMES[model_action]
        triage_md = (
            f'<div style="background:{TRIAGE_COLORS[triage_name]};color:white;padding:12px 24px;'
            f'border-radius:12px;font-size:1.4em;font-weight:bold;text-align:center">'
            f'{triage_name.replace("_", " ").title()}</div>'
        )
    else:
        triage_md = "### Triage\n*Triage agent not loaded — no recommendation available.*"

    detail = (
        f"**Predicted class:** {['benign', 'melanoma', 'kaposi_sarcoma'][pred_class]} "
        f"({float(probabilities[pred_class]):.1%} confidence)\n"
        f"**Fitzpatrick type:** {FITZPATRICK_LABELS[fitz_type - 1]} (type {fitz_type})\n"
        f"**Model:** `{state.model_version or 'unversioned'}`"
    )

    case_id = state.next_case_id()
    state.tracker.register_case(CaseRecord(
        case_id=case_id,
        fitz_type=fitz_type,
        predicted_label=pred_class,
        model_triage=model_action,
        ground_truth_label=int(true_label_dropdown),
        ground_truth_confirmed=False,  # simulated label, not a clinician confirmation
        concepts=[float(v) for v in concept_vector],
        source="simulation",
    ))

    session_data = {
        "case_id": case_id,
        "model_action": model_action,
        "true_label": int(true_label_dropdown),
        "fitz_type": fitz_type,
        "concepts": [float(v) for v in concept_vector],
    }
    return (overlay, concept_md, triage_md, detail, session_data, f"Case {case_id}", "", "")


def override_triage(session_data: Optional[dict], new_action: int, state: AppState) -> Tuple:
    if not session_data:
        return ("No active case.", "", gr.update(), gr.update())
    case_id = session_data["case_id"]
    concepts = np.array(session_data.get("concepts") or [0.0] * len(CONCEPT_NAMES), dtype=np.float32)
    if state.hitl is not None:
        state.hitl.process_case(
            patient_id=case_id,
            concept_embed=concepts,
            fitz_type=session_data["fitz_type"],
            true_label=session_data["true_label"],
            clinician_action=int(new_action),
        )
    state.tracker.register_override(case_id, int(new_action))
    message = f"Override recorded: {TRIAGE_NAMES[int(new_action)]}"
    return (message, message, gr.update(variant="secondary"), gr.update(variant="primary"))


def agree_with_model(session_data: Optional[dict], state: AppState) -> Tuple:
    if not session_data:
        return ("No active case.", "", gr.update(), gr.update())
    return (f"Agreed — no override recorded for {session_data['case_id']}.", "",
            gr.update(variant="primary"), gr.update(variant="secondary"))


# ---------------------------------------------------------------------------
#  Tab 2 - Analytics
# ---------------------------------------------------------------------------

def refresh_analytics(state: AppState) -> Tuple:
    metrics = state.tracker.compute_metrics()
    accuracy = metrics.get("clinical_accuracy")
    agreement = metrics.get("model_vs_clinician_agreement")
    summary = (
        f"**Clinical accuracy (confirmed cases):** "
        f"{'n/a' if accuracy is None else f'{accuracy:.1%}'}  |  "
        f"**Model/clinician agreement:** {'n/a' if agreement is None else f'{agreement:.1%}'}  |  "
        f"**Override rate:** {metrics.get('override_rate', 0):.1%}  |  "
        f"**Cases:** {metrics.get('total_cases', 0)}"
    )
    notes = " • ".join(metrics.get("notes", [])) or "Metrics are computed from registered cases only."
    return (
        state.tracker.accuracy_by_type_chart(),
        state.tracker.urgent_rate_chart(),
        state.tracker.confusion_matrix_chart(),
        state.tracker.override_pie(),
        state.tracker.trend_chart(),
        summary,
        notes,
    )


# ---------------------------------------------------------------------------
#  Tab 3 - History
# ---------------------------------------------------------------------------

def search_history(query: str, filter_fitz: int, state: AppState) -> pd.DataFrame:
    cases = state.tracker.cases
    if filter_fitz:
        cases = [c for c in cases if c.fitz_type == filter_fitz]
    if query:
        cases = [c for c in cases if query.lower() in c.case_id.lower()]
    rows = []
    for case in cases[-200:]:
        final = case.clinician_triage if case.is_override else case.model_triage
        rows.append({
            "Case ID": case.case_id,
            "Date": case.timestamp[:10],
            "Fitzpatrick": FITZPATRICK_LABELS[case.fitz_type - 1],
            "Model triage": TRIAGE_NAMES[case.model_triage] if case.model_triage is not None else "",
            "Final triage": TRIAGE_NAMES[final] if final is not None else "",
            "Confirmed": "yes" if case.ground_truth_confirmed else "no",
            "Override": "yes" if case.is_override else "",
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame({"Info": ["No cases found."]})


# ---------------------------------------------------------------------------
#  Tab 4 - Settings
# ---------------------------------------------------------------------------

def run_offline_update(state: AppState) -> str:
    if state.optimizer is None or state.hitl is None:
        return "Offline optimisation requires a loaded triage agent."
    buffer = state.hitl.correction_buffer
    if len(buffer) < 2:
        return "Not enough overrides (need at least 2)."
    metrics = state.optimizer.optimise(buffer)
    state.tracker.snapshot("after_offline_update")
    loss = metrics.get("policy_loss")
    return "Offline update complete." + (f" Policy loss: {loss:.4f}" if loss is not None else "")


def export_data(state: AppState) -> str:
    path = state.tracker.export_csv()
    return f"Case history exported to {path}"


# ---------------------------------------------------------------------------
#  UI
# ---------------------------------------------------------------------------

def create_ui(state: AppState):
    if gr is None:  # pragma: no cover - only when gradio is not installed
        raise RuntimeError(
            "Gradio is not installed. Install it with `pip install gradio` or use "
            "`python main.py --dashboard` for the FastAPI clinical dashboard."
        )
    with gr.Blocks(title="Dermatology AI — researcher UI") as demo:
        gr.Markdown(
            "# Dermatology AI — researcher UI\n"
            "**Research/educational prototype. Not a medical device. "
            "Not validated for clinical use.**"
        )

        session = gr.State({})
        app_state = gr.State(state)

        with gr.Tabs():
            with gr.Tab("Diagnosis"):
                with gr.Row():
                    with gr.Column():
                        image_input = gr.Image(label="Upload image", height=350)
                        with gr.Row():
                            fitz_input = gr.Dropdown(
                                choices=[(f"Type {i} — {FITZPATRICK_LABELS[i - 1]}", i) for i in range(1, 7)],
                                value=4, label="Fitzpatrick type", interactive=True,
                            )
                            true_label_input = gr.Dropdown(
                                choices=[(name.replace("_", " ").title(), i) for i, name in enumerate(TRUE_LABEL_NAMES)],
                                value=0, label="Reference label (simulation)", interactive=True,
                            )
                        diagnose_btn = gr.Button("Run diagnosis", variant="primary")
                    with gr.Column():
                        triage_display = gr.Markdown("### Triage\n*Awaiting image...*")
                        case_id_display = gr.Markdown("")
                        detail_display = gr.Markdown("")
                overlay_output = gr.Image(label="Grad-CAM overlay", height=300)
                concept_output = gr.Markdown("### Concept scores\n*Awaiting analysis...*")
                override_dropdown = gr.Dropdown(
                    choices=[(name.replace("_", " ").title(), i) for i, name in enumerate(TRIAGE_NAMES)],
                    value=1, label="Override triage", interactive=False,
                )
                with gr.Row():
                    agree_btn = gr.Button("Agree with model", variant="secondary", size="sm")
                    override_btn = gr.Button("Submit override", variant="secondary", size="sm")
                override_msg = gr.Markdown("")
                extra_msg = gr.Markdown("")

                diagnose_btn.click(
                    fn=run_diagnosis,
                    inputs=[image_input, fitz_input, true_label_input, app_state],
                    outputs=[overlay_output, concept_output, triage_display, detail_display,
                             session, case_id_display, override_msg, extra_msg],
                ).then(
                    fn=lambda data: (
                        gr.update(interactive=True),
                        gr.update(interactive=True),
                        gr.update(interactive=True, value=(data or {}).get("model_action") or 1),
                    ),
                    inputs=[session],
                    outputs=[agree_btn, override_btn, override_dropdown],
                )
                agree_btn.click(fn=agree_with_model, inputs=[session, app_state],
                                outputs=[override_msg, extra_msg, agree_btn, override_btn])
                override_btn.click(fn=override_triage, inputs=[session, override_dropdown, app_state],
                                   outputs=[override_msg, extra_msg, agree_btn, override_btn])

            with gr.Tab("Analytics"):
                gr.Markdown("### Fairness & performance (confirmed cases only)")
                summary_md = gr.Markdown("Click refresh.")
                notes_md = gr.Markdown("")
                refresh_btn = gr.Button("Refresh", variant="primary")
                with gr.Row():
                    acc_chart = gr.Plot(label="Clinical accuracy by Fitzpatrick type")
                    parity_chart = gr.Plot(label="Urgent-triage rate (demographic parity)")
                with gr.Row():
                    cm = gr.Plot(label="Confusion matrix")
                    pie = gr.Plot(label="Overrides")
                trend = gr.Plot(label="Trends")
                refresh_btn.click(
                    fn=refresh_analytics, inputs=[app_state],
                    outputs=[acc_chart, parity_chart, cm, pie, trend, summary_md, notes_md],
                )

            with gr.Tab("History"):
                with gr.Row():
                    search_input = gr.Textbox(label="Search by case ID")
                    filter_fitz = gr.Dropdown(
                        choices=[("All", 0)] + [(f"Type {FITZPATRICK_LABELS[i - 1]}", i) for i in range(1, 7)],
                        value=0, label="Filter by Fitzpatrick",
                    )
                history_table = gr.Dataframe(label="Recent cases", interactive=False)
                search_btn = gr.Button("Search", variant="primary")
                search_btn.click(fn=search_history, inputs=[search_input, filter_fitz, app_state],
                                 outputs=[history_table])

            with gr.Tab("Settings"):
                gr.Markdown("### Research data management")
                update_btn = gr.Button("Run offline update", variant="primary")
                update_status = gr.Markdown("")
                export_btn = gr.Button("Export case history CSV")
                export_status = gr.Markdown("")
                update_btn.click(fn=run_offline_update, inputs=[app_state], outputs=[update_status])
                export_btn.click(fn=export_data, inputs=[app_state], outputs=[export_status])

    return demo
