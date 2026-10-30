"""Launcher for the Dermatology AI system.

Usage::

    python main.py                  # FastAPI dashboard (default)
    python main.py --demo           # synthetic end-to-end pipeline demo (no persistence)
    python main.py --ui             # legacy Gradio researcher UI (needs checkpoints)

``--demo`` is the only mode that generates synthetic cases.  It prints results to
stdout and never writes to the database or the API.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
from pathlib import Path
from typing import List

import numpy as np

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    torch = None
    _TORCH_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
NUM_CONCEPTS = 7
NUM_CLASSES = 3
NUM_FITZ_TYPES = 6

if _TORCH_AVAILABLE:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
else:
    DEVICE = None


# ---------------------------------------------------------------------------
#  Synthetic demo data (demo mode only)
# ---------------------------------------------------------------------------

def generate_synthetic_cases(num_cases: int = 500, seed: int = 0) -> List:
    """Create synthetic triage cases for the pipeline demo.

    These are **not** evaluation data: the concept vectors are drawn from
    label-conditional ranges, so a model evaluated on them measures nothing.
    """
    from constants import TRUE_LABEL_NAMES
    from rl_module import Case

    rng = random.Random(seed)
    fitz_weights = [1, 1, 1, 3, 4, 4]
    label_weights = [0.55, 0.2, 0.1, 0.15]  # includes atypical_lesion -> follow_up
    ranges = {
        0: [(0.0, 0.3), (0.0, 0.3), (0.0, 0.3), (0.0, 0.4), (0.4, 0.7), (0.0, 0.2), (0.0, 0.1)],
        1: [(0.7, 1.0), (0.6, 1.0), (0.5, 1.0), (0.7, 1.0), (0.1, 0.4), (0.3, 0.7), (0.2, 0.6)],
        2: [(0.3, 0.6), (0.3, 0.6), (0.4, 0.8), (0.3, 0.6), (0.6, 0.9), (0.4, 0.7), (0.5, 0.9)],
        3: [(0.4, 0.7), (0.4, 0.7), (0.3, 0.6), (0.2, 0.5), (0.3, 0.6), (0.1, 0.4), (0.0, 0.3)],
    }
    cases = []
    for index in range(num_cases):
        true_label = rng.choices(range(len(TRUE_LABEL_NAMES)), weights=label_weights)[0]
        fitz = rng.choices(range(1, 7), weights=fitz_weights)[0]
        concept = np.array([rng.uniform(low, high) for low, high in ranges[true_label]], dtype=np.float32)
        cases.append(Case(
            concept_embedding=concept,
            fitz_type=fitz,
            true_label=true_label,
            patient_id=f"SYN-{index:04d}",
        ))
    return cases


# ---------------------------------------------------------------------------
#  Dashboard
# ---------------------------------------------------------------------------

def run_dashboard(port: int = 7860, reload: bool = False) -> None:
    import uvicorn

    from server import create_app

    app = create_app()
    logger.info("Starting dashboard on 0.0.0.0:%s", port)
    uvicorn.run(app, host="0.0.0.0", port=port, reload=reload)


# ---------------------------------------------------------------------------
#  Legacy Gradio UI
# ---------------------------------------------------------------------------

def _load_checkpoint_state(path: str) -> dict:
    if not path:
        raise SystemExit(
            "MODEL_CHECKPOINT_PATH is not set. This UI will not run without real weights "
            "(it previously served predictions from a randomly initialised head)."
        )
    if not Path(path).is_file():
        raise SystemExit(f"Checkpoint not found: {path}")
    return torch.load(path, map_location="cpu", weights_only=True)


def run_ui(share: bool = False) -> None:
    if not _TORCH_AVAILABLE:
        raise SystemExit("PyTorch is required for the Gradio UI.")

    from backend import file_sha256
    from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer
    from metrics_tracker import FairnessTracker
    from model import DermatologyCBM
    from rl_module import PPOAgent
    from storage import Store
    from ui import AppState, create_ui

    model_path = os.environ.get("MODEL_CHECKPOINT_PATH", "")
    state_dict = _load_checkpoint_state(model_path)
    num_classes = int(state_dict["classifier.weight"].shape[0])
    model = DermatologyCBM(num_classes=num_classes, num_concepts=NUM_CONCEPTS,
                           hrnet_name="hrnet_w18", pretrained_backbone=False)
    model.load_state_dict(state_dict, strict=True)
    model.eval().to(DEVICE)

    agent = None
    hitl = None
    optimizer = None
    agent_path = os.environ.get("AGENT_CHECKPOINT_PATH", "")
    if agent_path and Path(agent_path).is_file():
        agent = PPOAgent(state_dim=NUM_CONCEPTS + NUM_FITZ_TYPES, action_dim=3, device=DEVICE)
        agent.load(agent_path)
        hitl = HITLPipeline(agent, num_concepts=NUM_CONCEPTS)
        optimizer = OfflinePolicyOptimizer(agent, learning_rate=5e-5)

    data_dir = Path(os.environ.get("DATA_DIR", APP_DIR / "data"))
    store = Store(data_dir)
    tracker = FairnessTracker(store, export_path=str(data_dir / "case_history.csv"))

    app_state = AppState(
        model=model,
        ppo_agent=agent,
        hitl=hitl,
        offline_optimizer=optimizer,
        tracker=tracker,
        device=DEVICE,
        model_version=f"{Path(model_path).name}@{file_sha256(model_path)[:12]}",
        weights_sha256=file_sha256(model_path),
    )
    create_ui(app_state).launch(share=share, server_name="0.0.0.0", server_port=7860)


# ---------------------------------------------------------------------------
#  Synthetic pipeline demo
# ---------------------------------------------------------------------------

def run_demo(episodes: int = 500) -> None:
    """Train/inspect the Triage policy on synthetic cases and print metrics.

    Explicitly labelled synthetic: nothing here is evidence of clinical or
    fairness performance.
    """
    if not _TORCH_AVAILABLE:
        raise SystemExit("PyTorch is required for --demo.")

    from constants import TRUE_LABEL_NAMES, TRUE_LABEL_TO_TRIAGE
    from rl_module import DermTriageEnv, PPOAgent, Rollout

    logger.info("=" * 64)
    logger.info("SYNTHETIC DEMO — not evaluation data, not clinical evidence")
    logger.info("=" * 64)

    cases = generate_synthetic_cases(num_cases=500)
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    env.seed(cases)
    agent = PPOAgent(state_dim=NUM_CONCEPTS + NUM_FITZ_TYPES, action_dim=3, device=DEVICE)

    rollouts: list[Rollout] = []
    for episode in range(1, episodes + 1):
        state = env.reset()
        action, log_prob, value = agent.select_action(state)
        _, reward, _, _ = env.step(action)
        rollouts.append(Rollout(states=[state], actions=[action], rewards=[reward],
                                dones=[True], log_probs=[log_prob], values=[value]))
        if episode % 64 == 0:
            metrics = agent.update(rollouts)
            logger.info("episode %4d | policy_loss %.4f | value_loss %.4f",
                        episode, metrics["policy_loss"], metrics["value_loss"])
            rollouts = []

    logger.info("Triage action distribution by Fitzpatrick type (synthetic):")
    for fitz in range(1, 7):
        subset = [c for c in cases if c.fitz_type == fitz]
        if not subset:
            continue
        states = [env._build_state(c) for c in subset]
        actions = [agent.evaluate(s) for s in states]
        correct = sum(
            1 for c, a in zip(subset, actions) if TRUE_LABEL_TO_TRIAGE[c.true_label] == a
        )
        logger.info("  Fitz %s | n=%3d | agreement with catalogue %5.1f%% | actions %s",
                    fitz, len(subset), 100 * correct / len(subset),
                    {name: actions.count(i) for i, name in enumerate(["routine", "follow_up", "urgent"])})

    logger.info("Catalogue: %s", TRUE_LABEL_NAMES)
    logger.info("Reminder: these cases are generated from label-conditional ranges.")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Dermatology AI launcher")
    parser.add_argument("--dashboard", action="store_true", help="run the FastAPI dashboard (default)")
    parser.add_argument("--ui", action="store_true", help="run the legacy Gradio UI")
    parser.add_argument("--share", action="store_true", help="public Gradio link (implies --ui)")
    parser.add_argument("--demo", action="store_true", help="run the synthetic pipeline demo")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 7860)))
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--episodes", type=int, default=500)
    args = parser.parse_args()

    if args.demo:
        run_demo(episodes=args.episodes)
    elif args.ui or args.share:
        run_ui(share=args.share)
    else:
        run_dashboard(port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
