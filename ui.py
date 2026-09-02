"""
Gradio-based Doctor UI for the Dermatology AI HITL system.

Four tabs:
    1. Diagnosis       — upload image, view Grad-CAM + concepts + triage + override
    2. Analytics       — fairness metrics dashboard (accuracy gap, FN rates, etc.)
    3. Patient History — browse/search past cases and overrides
    4. System Settings — trigger offline policy updates, export data
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import gradio as gr
import numpy as np
import pandas as pd
import torch
from PIL import Image as PILImage

from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer
from metrics_tracker import FairnessTracker, CaseRecord
from model import CONCEPT_NAMES, DermatologyCBM, XAIExplainer
from rl_module import FITZPATRICK_LABELS, PPOAgent, TRIAGE_NAMES, TRUE_LABEL_TO_TRIAGE

logger = logging.getLogger(__name__)

TRIAGE_COLORS = {"routine": "#4CAF50", "follow_up": "#FF9800", "urgent": "#e74c3c"}


class AppState:
    """Singleton holding all model / agent / pipeline references for the UI."""

    def __init__(
        self,
        model: DermatologyCBM,
        ppo_agent: PPOAgent,
        hitl: HITLPipeline,
        offline_optimizer: OfflinePolicyOptimizer,
        tracker: FairnessTracker,
        device: torch.device,
    ):
        self.model = model
        self.ppo_agent = ppo_agent
        self.hitl = hitl
        self.optimizer = offline_optimizer
        self.tracker = tracker
        self.device = device
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


# ====================================================================
#  Image preprocessing
# ====================================================================

def preprocess(image: np.ndarray, device: torch.device) -> torch.Tensor:
    img = PILImage.fromarray(image).convert("RGB").resize((224, 224))
    arr = np.array(img, dtype=np.float32) / np.float32(255.0)
    arr = (arr - np.float32([0.485, 0.456, 0.406])) / np.float32([0.229, 0.224, 0.225])
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device)
    return tensor


# ====================================================================
#  Tab 1 – Diagnosis
# ====================================================================

def run_diagnosis(
    image: Optional[np.ndarray],
    fitz_dropdown: int,
    true_label_dropdown: int,
    state: AppState,
) -> Tuple:
    if image is None:
        return (None, "Please upload an image.", "", gr.update(), gr.update(), gr.update(), gr.update(), None, "", gr.update(), gr.update(), gr.update())

    fitz_type = int(fitz_dropdown)
    true_label = int(true_label_dropdown)
    tensor = preprocess(image, state.device)

    with torch.no_grad():
        logits, concepts = state.model(tensor)
        pred_class = logits.argmax(dim=1).item()

    concept_dict = {CONCEPT_NAMES[i]: round(concepts[0, i].item(), 4) for i in range(len(CONCEPT_NAMES))}

    # Grad-CAM overlay
    try:
        state.model.eval()
        cam = state.xai.grad_cam(tensor.clone().requires_grad_())
        cam_resized = np.array(PILImage.fromarray((cam * 255).astype(np.uint8)).resize((image.shape[1], image.shape[0])))
        overlay = (image * 0.5 + np.stack([cam_resized] * 3, axis=-1) * 0.5).astype(np.uint8)
    except Exception as e:
        logger.warning("Grad-CAM failed: %s", e)
        overlay = image

    # Build concept score bars (markdown progress bars)
    concept_md = "### Concept Scores  \n"
    for name in CONCEPT_NAMES:
        val = concept_dict[name]
        pct = int(val * 100)
        bar_color = "#e74c3c" if val > 0.6 else ("#f39c12" if val > 0.3 else "#4CAF50")
        label = name.replace("_", " ").title()
        concept_md += f"**{label}**  " + chr(10) * 1
        concept_md += (
            '<div style="background:#e0e0e0;border-radius:8px;height:20px;width:100%">'
            f'<div style="background:{bar_color};border-radius:8px;height:20px;width:{pct}%"></div>'
            f"</div> `{val:.2f}`" + chr(10) * 2
        )

    # Build state for PPO
    state_vec = np.concatenate([concepts[0].cpu().numpy(), np.eye(6, dtype=np.float32)[fitz_type - 1]])
    model_action = state.ppo_agent.evaluate(state_vec)
    triage_name = TRIAGE_NAMES[model_action]
    triage_color = TRIAGE_COLORS[triage_name]
    triage_md = f'<div style="background:{triage_color};color:white;padding:12px 24px;border-radius:12px;font-size:1.4em;font-weight:bold;text-align:center">{triage_name.replace("_", " ").title()}</div>'

    # Detail text
    detail = f"**Predicted class:** {['benign', 'melanoma', 'kaposi_sarcoma'][pred_class]}\n**Fitzpatrick type:** {FITZPATRICK_LABELS[fitz_type - 1]} (type {fitz_type})"

    # Record case
    case_id = state.next_case_id()
    case_record = CaseRecord(
        case_id=case_id,
        fitz_type=fitz_type,
        true_label=true_label,
        model_triage=model_action,
        concepts=concepts[0].cpu().numpy().tolist(),
    )
    state.tracker.register_case(case_record)

    # Store in session state
    session_data = {"case_id": case_id, "model_action": model_action, "true_label": true_label, "fitz_type": fitz_type}

    return (overlay, concept_md, triage_md, detail, session_data, f"Case {case_id}")


def agree_with_model(session_data: dict, state: AppState) -> Tuple:
    if session_data is None:
        return ("No active case.", "", gr.update(), gr.update())
    case_id = session_data["case_id"]
    return (f"✅ Agreed — no override recorded for {case_id}.", "", gr.update(variant="primary"), gr.update(variant="secondary"))


def override_triage(session_data: dict, new_action: int, state: AppState) -> Tuple:
    if session_data is None:
        return ("No active case.", "", gr.update(), gr.update())
    case_id = session_data["case_id"]
    old_action = session_data["model_action"]

    state.hitl.process_case(
        patient_id=case_id,
        concept_embed=np.array(session_data.get("concepts", [0.0] * 7)),
        fitz_type=session_data["fitz_type"],
        true_label=session_data["true_label"],
        clinician_action=new_action,
    )
    state.tracker.register_override(case_id, new_action)
    msg = f"🩺 Override recorded: {TRIAGE_NAMES[old_action]} → {TRIAGE_NAMES[new_action]}"
    return (msg, f"Overridden to {TRIAGE_NAMES[new_action].replace('_', ' ').title()}", gr.update(variant="secondary"), gr.update(variant="primary"))


# ====================================================================
#  Tab 2 – Analytics Dashboard
# ====================================================================

def refresh_analytics(state: AppState) -> Tuple:
    metrics = state.tracker.compute_metrics()
    if not metrics:
        return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), "No data yet.", "0")

    acc_chart = state.tracker.accuracy_by_type_chart()
    fn_chart = state.tracker.fn_rate_chart()
    gauge = state.tracker.accuracy_gauge()
    cm = state.tracker.confusion_matrix_chart()
    pie = state.tracker.override_pie()
    trend = state.tracker.trend_chart()

    gap = metrics.get("accuracy_gap", 0)
    gap_color = "🟢" if gap <= 0.02 else ("🟡" if gap <= 0.05 else "🔴")
    summary = (
        f"{gap_color} **Accuracy Gap:** {gap:.2%}  |  "
        f"**Overall Accuracy:** {metrics.get('overall_accuracy', 0):.1%}  |  "
        f"**Override Rate:** {metrics.get('override_rate', 0):.1%}  |  "
        f"**Total Cases:** {metrics.get('total_cases', 0)}"
    )
    detail = f"**Legacy (I-III):** {metrics.get('legacy_accuracy', 0):.1%}  •  **Target (IV-VI):** {metrics.get('target_accuracy', 0):.1%}"
    return (acc_chart, fn_chart, gauge, cm, pie, trend, summary, detail)


# ====================================================================
#  Tab 3 – Patient History
# ====================================================================

def search_history(query: str, filter_fitz: int, state: AppState) -> pd.DataFrame:
    cases = state.tracker.cases
    if filter_fitz > 0:
        cases = [c for c in cases if c.fitz_type == filter_fitz]
    if query:
        cases = [c for c in cases if query.lower() in c.case_id.lower()]

    rows = []
    for c in cases[-200:]:
        actual = c.clinician_triage if c.is_override else c.model_triage
        rows.append({
            "Case ID": c.case_id,
            "Date": c.timestamp[:10],
            "Fitzpatrick": FITZPATRICK_LABELS[c.fitz_type - 1],
            "Model Triage": TRIAGE_NAMES[c.model_triage],
            "Final Triage": TRIAGE_NAMES[actual],
            "Override": "✅" if c.is_override else "—",
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame({"Info": ["No cases found."]})


# ====================================================================
#  Tab 4 – System Settings
# ====================================================================

def run_offline_update(state: AppState) -> str:
    buffer = state.hitl.correction_buffer
    if len(buffer) < 2:
        return "⚠️ Not enough overrides (need ≥ 2)."
    metrics = state.optimizer.optimise(buffer)
    state.tracker.snapshot("after_offline_update")
    state.tracker.save()
    loss = metrics.get('policy_loss', None)
    if loss is None:
        return "✅ Offline update complete (no loss data)."
    return f"✅ Offline update complete. Policy loss: {loss:.4f}"

def export_data(state: AppState) -> str:
    state.tracker.export_csv()
    return "✅ Case history exported to case_history.csv"

def reset_tracker(state: AppState) -> str:
    state.tracker.cases.clear()
    state.tracker._snapshots.clear()
    state.tracker.save()
    return "🔄 Tracker reset."


# ====================================================================
#  Build UI
# ====================================================================

def create_ui(state: AppState) -> gr.Blocks:
    css = """
    .triage-badge { padding: 8px 16px; border-radius: 8px; font-weight: bold; color: white; display: inline-block; }
    .metric-card { background: #f8f9fa; border-radius: 12px; padding: 16px; margin: 8px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    footer { display: none !important; }
    /* Prevent text selection and I-beam cursor on all static/navigation text */
    nav, nav *, .tabs, .tab-nav, .tab-nav *, .gr-tabs, .gr-tabs *,
    label, .gr-label, .gr-box-title, .gr-form > label,
    h1, h2, h3, h4, h5, h6, p, .gr-markdown, .gr-markdown *,
    .gr-panel, .gr-panel .gr-panel-title, .gr-accordion, .gr-accordion *,
    .gr-button, .gr-button *, button.gr-button,
    span.gr-text-sm, .gr-form-text, .gr-form-json-label,
    .prose, .prose * { user-select: none; -webkit-user-select: none; }
    /* Buttons must show pointer cursor, never I-beam */
    .gr-button, .gr-button *, button, [role="button"] { cursor: pointer; }
    /* Restore text selection for actual input fields */
    input, textarea, [contenteditable="true"], select { user-select: text; -webkit-user-select: text; }
    /* Remove caret from all non-input elements */
    nav, .tabs, .gr-tabs, label, h1, h2, h3, h4, h5, h6, p, span, div:not(input):not(textarea):not([contenteditable]) { caret-color: transparent; }
    """

    with gr.Blocks(title="Dermatology AI — HITL System") as demo:
        gr.Markdown(
            "# 🏥 Dermatology AI — Human-in-the-Loop Triage System\n"
            "Tailored for **Ugandan healthcare** — optimised for **Fitzpatrick IV–VI** skin types."
        )

        session = gr.State({})
        app_state = gr.State(state)

        with gr.Tabs() as tabs:
            # ==============================================================
            # TAB 1 – DIAGNOSIS
            # ==============================================================
            with gr.Tab("🔬 Diagnosis", id=0):
                gr.Markdown("### Upload a dermoscopic image for AI-assisted triage")
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1):
                        image_input = gr.Image(label="Upload Image", height=350)
                        with gr.Row():
                            fitz_input = gr.Dropdown(
                                choices=[(f"Type {i} — {FITZPATRICK_LABELS[i-1]}", i) for i in range(1, 7)],
                                value=4, label="Fitzpatrick Skin Type", interactive=True,
                                info="Assessed by clinician"
                            )
                            true_label_input = gr.Dropdown(
                                choices=[("Benign", 0), ("Melanoma", 1), ("Kaposi Sarcoma", 2)],
                                value=0, label="Ground Truth (for simulation)", interactive=True,
                                info="Known diagnosis (simulated)"
                            )
                        diagnose_btn = gr.Button("🔍 Run Diagnosis", variant="primary", size="lg")

                    with gr.Column(scale=1):
                        triage_display = gr.Markdown("### Triage Recommendation\n*Awaiting image...*")
                        case_id_display = gr.Markdown("")
                        detail_display = gr.Markdown("")

                with gr.Row():
                    overlay_output = gr.Image(label="Grad-CAM Overlay", height=300)

                with gr.Row():
                    concept_output = gr.Markdown("### Concept Scores\n*Awaiting analysis...*")

                with gr.Row():
                    gr.Markdown("### 👨‍⚕️ Clinician Override")
                with gr.Row():
                    override_dropdown = gr.Dropdown(
                        choices=[("Routine (0)", 0), ("Follow-up (1)", 1), ("Urgent (2)", 2)],
                        value=0, label="Override Triage Decision", interactive=False
                    )
                with gr.Row():
                    agree_btn = gr.Button("✅ Agree with Model", variant="secondary", size="sm")
                    override_btn = gr.Button("🩺 Submit Override", variant="secondary", size="sm")
                override_msg = gr.Markdown("")

                diagnose_btn.click(
                    fn=run_diagnosis,
                    inputs=[image_input, fitz_input, true_label_input, app_state],
                    outputs=[overlay_output, concept_output, triage_display, detail_display, session, case_id_display],
                ).then(
                    fn=lambda data: (
                        gr.update(variant="secondary", interactive=True),
                        gr.update(variant="secondary", interactive=True),
                        gr.update(visible=True, interactive=True, value=data.get("model_action", 0)),
                    ),
                    inputs=[session],
                    outputs=[agree_btn, override_btn, override_dropdown],
                )
                agree_btn.click(fn=agree_with_model, inputs=[session, app_state], outputs=[override_msg, override_dropdown, agree_btn, override_btn])
                override_btn.click(fn=override_triage, inputs=[session, override_dropdown, app_state], outputs=[override_msg, override_dropdown, agree_btn, override_btn])

            # ==============================================================
            # TAB 2 – ANALYTICS DASHBOARD
            # ==============================================================
            with gr.Tab("📊 Analytics Dashboard", id=1):
                gr.Markdown("### Fairness & Performance Metrics")
                summary_md = gr.Markdown("Click *Refresh* to load data.")
                detail_md = gr.Markdown("")
                refresh_btn = gr.Button("🔄 Refresh Dashboard", variant="primary")

                with gr.Row():
                    with gr.Column(scale=2):
                        acc_chart = gr.Plot(label="Accuracy by Fitzpatrick Type")
                    with gr.Column(scale=1):
                        gauge = gr.Plot(label="Accuracy Gap Gauge")

                with gr.Row():
                    fn_chart = gr.Plot(label="False Negative Rate by Type")
                    pie = gr.Plot(label="Override Distribution")

                with gr.Row():
                    cm = gr.Plot(label="Confusion Matrix")
                    trend = gr.Plot(label="Metric Trends")

                refresh_btn.click(
                    fn=refresh_analytics,
                    inputs=[app_state],
                    outputs=[acc_chart, fn_chart, gauge, cm, pie, trend, summary_md, detail_md],
                )

            # ==============================================================
            # TAB 3 – PATIENT HISTORY
            # ==============================================================
            with gr.Tab("📋 Patient History", id=2):
                with gr.Row():
                    search_input = gr.Textbox(label="Search by Case ID", placeholder="e.g. UI-20260522-0001")
                    filter_fitz = gr.Dropdown(
                        choices=[("All", 0)] + [(f"Type {FITZPATRICK_LABELS[i-1]}", i) for i in range(1, 7)],
                        value=0, label="Filter by Fitzpatrick"
                    )
                history_table = gr.Dataframe(label="Recent Cases", interactive=False)
                search_btn = gr.Button("🔍 Search", variant="primary")

                search_btn.click(fn=search_history, inputs=[search_input, filter_fitz, app_state], outputs=[history_table])

            # ==============================================================
            # TAB 4 – SYSTEM SETTINGS
            # ==============================================================
            with gr.Tab("⚙️ System Settings", id=3):
                gr.Markdown("### Offline Policy Optimisation")
                gr.Markdown(
                    "Uses accumulated clinician overrides to update the PPO agent's policy. "
                    "Requires at least **2 overrides** in the buffer."
                )
                update_btn = gr.Button("▶️ Run Offline Update", variant="primary")
                update_status = gr.Markdown("")

                gr.Markdown("---")
                gr.Markdown("### Data Management")
                with gr.Row():
                    export_btn = gr.Button("📥 Export CSV")
                    reset_btn = gr.Button("🔄 Reset Tracker", variant="stop")

                export_status = gr.Markdown("")
                reset_status = gr.Markdown("")

                update_btn.click(fn=run_offline_update, inputs=[app_state], outputs=[update_status])
                export_btn.click(fn=export_data, inputs=[app_state], outputs=[export_status])
                reset_btn.click(fn=reset_tracker, inputs=[app_state], outputs=[reset_status])

    return demo
