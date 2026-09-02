"""
Integrated demo + Gradio UI launcher for the Dermatology AI HITL system.

Usage:
    python main.py                  # headless demo (CLI)
    python main.py --ui             # launch Gradio web UI
    python main.py --ui --share     # launch with public Gradio link
"""

import argparse
import logging
import os
import random
import sys
from typing import List

import numpy as np

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    torch = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

NUM_CONCEPTS = 7
NUM_CLASSES = 3
NUM_FITZ_TYPES = 6

if _TORCH_AVAILABLE:
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
else:
    DEVICE = None


# ---------------------------------------------------------------------------
#  Synthetic data generation
# ---------------------------------------------------------------------------

def generate_mock_cases(num_cases: int = 500) -> List:
    from rl_module import Case
    cases = []
    fitz_weights = [1, 1, 1, 3, 4, 4]
    for i in range(num_cases):
        true_label = random.choices([0, 1, 2], weights=[0.6, 0.25, 0.15])[0]
        fitz_type = random.choices(range(1, 7), weights=fitz_weights)[0]
        if true_label == 0:
            concept = np.array([random.uniform(0, 0.3), random.uniform(0, 0.3), random.uniform(0, 0.3), random.uniform(0, 0.4), random.uniform(0.4, 0.7), random.uniform(0, 0.2), random.uniform(0, 0.1)])
        elif true_label == 1:
            concept = np.array([random.uniform(0.7, 1.0), random.uniform(0.6, 1.0), random.uniform(0.5, 1.0), random.uniform(0.7, 1.0), random.uniform(0.1, 0.4), random.uniform(0.3, 0.7), random.uniform(0.2, 0.6)])
        else:
            concept = np.array([random.uniform(0.3, 0.6), random.uniform(0.3, 0.6), random.uniform(0.4, 0.8), random.uniform(0.3, 0.6), random.uniform(0.6, 0.9), random.uniform(0.4, 0.7), random.uniform(0.5, 0.9)])
        cases.append(Case(concept_embedding=concept, fitz_type=fitz_type, true_label=true_label, patient_id=f"PAT-{i:04d}"))
    return cases


# ---------------------------------------------------------------------------
#  PPO training
# ---------------------------------------------------------------------------

def train_ppo_agent(agent, env, cases, num_episodes: int = 2000, update_interval: int = 64):
    from rl_module import Rollout
    env.seed(cases)
    rollouts = []
    episode_rewards = []
    for episode in range(1, num_episodes + 1):
        state = env.reset()
        done = False
        ep_reward = 0.0
        while not done:
            action, log_prob, value = agent.select_action(state)
            next_state, reward, done, info = env.step(action)
            rollouts.append(Rollout(states=[state], actions=[action], rewards=[reward], dones=[done], log_probs=[log_prob], values=[value]))
            state = next_state
            ep_reward += reward
        episode_rewards.append(ep_reward)
        if episode % update_interval == 0 and rollouts:
            metrics = agent.update(rollouts)
            avg_reward = np.mean(episode_rewards[-update_interval:])
            logger.info("Episode %5d | Avg Reward %6.2f | Policy loss %.4f | Value loss %.4f", episode, avg_reward, metrics.get("policy_loss", 0.0), metrics.get("value_loss", 0.0))
            rollouts = []
    return agent


def compute_fairness_metrics(agent, cases: List) -> dict:
    from rl_module import TRUE_LABEL_TO_TRIAGE
    metrics = {}
    for fitz in range(1, 7):
        subset = [c for c in cases if c.fitz_type == fitz]
        if not subset:
            continue
        correct = sum(1 for c in subset if agent.evaluate(np.concatenate([c.concept_embedding.astype(np.float32), np.eye(6, dtype=np.float32)[c.fitz_type - 1]])) == TRUE_LABEL_TO_TRIAGE[c.true_label])
        metrics[f"Fitz_{fitz}"] = round(correct / len(subset), 4)
    return metrics


# ---------------------------------------------------------------------------
#  Seed the fairness tracker with benchmark data for the UI dashboard
# ---------------------------------------------------------------------------

def seed_tracker(agent, cases: List, tracker, hitl):
    from rl_module import TRUE_LABEL_TO_TRIAGE
    from metrics_tracker import CaseRecord
    for case in cases:
        state = np.concatenate([case.concept_embedding.astype(np.float32), np.eye(6, dtype=np.float32)[case.fitz_type - 1]])
        model_action = agent.evaluate(state)
        expected = TRUE_LABEL_TO_TRIAGE[case.true_label]

        record = CaseRecord(
            case_id=case.patient_id,
            fitz_type=case.fitz_type,
            true_label=case.true_label,
            model_triage=model_action,
            is_override=False,
        )
        tracker.register_case(record)

        model_action_p, override = hitl.process_case(
            patient_id=case.patient_id,
            concept_embed=case.concept_embedding,
            fitz_type=case.fitz_type,
            true_label=case.true_label,
            clinician_action=None,
        )

    # Inject a few overrides to show on the dashboard
    for i, case in enumerate(cases[:int(len(cases) * 0.12)]):
        expected = TRUE_LABEL_TO_TRIAGE[case.true_label]
        if random.random() < 0.5:
            override_action = expected
        else:
            override_action = random.choice([a for a in range(3) if a != expected])
        hitl.process_case(
            patient_id=case.patient_id,
            concept_embed=case.concept_embedding,
            fitz_type=case.fitz_type,
            true_label=case.true_label,
            clinician_action=override_action,
        )
        tracker.register_override(case.patient_id, override_action)

    tracker.snapshot("initial_benchmark")
    logger.info("Seeded tracker with %d cases + overrides", len(cases))


# ---------------------------------------------------------------------------
#  Headless demo (CLI)
# ---------------------------------------------------------------------------

def run_headless():
    if not _TORCH_AVAILABLE:
        logger.error("PyTorch is required for headless mode. pip install torch")
        sys.exit(1)

    from model import DermatologyCBM, XAIExplainer
    from rl_module import PPOAgent, DermTriageEnv, TRUE_LABEL_TO_TRIAGE
    from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer

    logger.info("=" * 60)
    logger.info("Dermatology AI — Headless Integration Demo")
    logger.info("Device: %s", DEVICE)
    logger.info("=" * 60)

    cases = generate_mock_cases(num_cases=500)
    logger.info("[1] %d cases generated", len(cases))

    logger.info("[2] Initialising HRNet-CBM model...")
    model = DermatologyCBM(num_classes=NUM_CLASSES, num_concepts=NUM_CONCEPTS, hrnet_name="hrnet_w18", pretrained_backbone=True, freeze_backbone=False).to(DEVICE)
    logger.info("    Parameters: %.2fM", sum(p.numel() for p in model.parameters()) / 1e6)

    logger.info("[3] XAI clinical audit...")
    model.eval()
    dummy = torch.randn(1, 3, 224, 224, requires_grad=True).to(DEVICE)
    explainer = XAIExplainer(model, DEVICE)
    cam = explainer.grad_cam(dummy)
    logger.info("    Grad-CAM: %s, [%.4f, %.4f]", cam.shape, cam.min(), cam.max())
    concepts = explainer.concept_attribution(dummy)
    logger.info("    Concepts: %s", concepts)
    explainer.cleanup()

    logger.info("[4] Training PPO agent...")
    state_dim = NUM_CONCEPTS + NUM_FITZ_TYPES
    agent = PPOAgent(state_dim=state_dim, action_dim=3, lr=3e-4, device=DEVICE)
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    agent = train_ppo_agent(agent, env, cases, num_episodes=2000)

    logger.info("    Fairness audit:")
    fm = compute_fairness_metrics(agent, cases)
    for k, v in fm.items():
        logger.info("      %s: %.2f%%", k, v * 100)
    low = [v for k, v in fm.items() if int(k.split("_")[1]) <= 3]
    high = [v for k, v in fm.items() if int(k.split("_")[1]) >= 4]
    if low and high:
        logger.info("    Accuracy gap (I-III vs IV-VI): %.2f%%", (np.mean(low) - np.mean(high)) * 100)

    logger.info("[5] HITL workflow + offline update...")
    hitl = HITLPipeline(agent)
    optimizer = OfflinePolicyOptimizer(agent, learning_rate=5e-5)
    random.shuffle(cases)
    num_override = max(1, int(len(cases) * 0.2))
    for i, case in enumerate(cases[:num_override]):
        clinician_action = TRUE_LABEL_TO_TRIAGE[case.true_label]
        hitl.process_case(
            patient_id=case.patient_id,
            concept_embed=case.concept_embedding,
            fitz_type=case.fitz_type,
            true_label=case.true_label,
            clinician_action=clinician_action,
        )
    logger.info("    Corrections in buffer: %d", len(hitl.correction_buffer))
    if hitl.correction_buffer:
        metrics = optimizer.optimise(hitl.correction_buffer)
        if metrics:
            logger.info("    Offline update: %s", metrics)

    logger.info("=" * 60)
    logger.info("Headless demo complete.")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
#  Gradio UI launcher
# ---------------------------------------------------------------------------

def run_ui(share: bool = False):
    if not _TORCH_AVAILABLE:
        logger.error("PyTorch is required for Gradio UI mode. pip install torch")
        sys.exit(1)

    from model import DermatologyCBM
    from rl_module import PPOAgent, DermTriageEnv
    from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer
    from metrics_tracker import FairnessTracker

    logger.info("=" * 60)
    logger.info("Dermatology AI — Launching Gradio UI")
    logger.info("Device: %s", DEVICE)
    logger.info("=" * 60)

    logger.info("Initialising HRNet-CBM model...")
    model = DermatologyCBM(num_classes=NUM_CLASSES, num_concepts=NUM_CONCEPTS, hrnet_name="hrnet_w18", pretrained_backbone=True, freeze_backbone=False).to(DEVICE)
    model.eval()

    logger.info("Initialising PPO agent...")
    state_dim = NUM_CONCEPTS + NUM_FITZ_TYPES
    agent = PPOAgent(state_dim=state_dim, action_dim=3, lr=3e-4, device=DEVICE)
    cases = generate_mock_cases(num_cases=500)
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    agent = train_ppo_agent(agent, env, cases, num_episodes=2000)

    logger.info("Initialising HITL pipeline...")
    hitl = HITLPipeline(agent, num_concepts=NUM_CONCEPTS)
    optimizer = OfflinePolicyOptimizer(agent, learning_rate=5e-5)

    logger.info("Initialising fairness tracker...")
    tracker = FairnessTracker(persist_path="case_history.json")
    seed_tracker(agent, cases, tracker, hitl)

    logger.info("Building Gradio interface...")
    from ui import create_ui, AppState
    app_state = AppState(model=model, ppo_agent=agent, hitl=hitl, offline_optimizer=optimizer, tracker=tracker, device=DEVICE)

    demo = create_ui(app_state)

    logger.info("Launching UI at http://127.0.0.1:7860")
    demo.launch(share=share, server_name="0.0.0.0", server_port=7860)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def run_dashboard(port: int = 7860, reload: bool = False):
    """Launch the new HTML/CSS dashboard via FastAPI."""
    try:
        from server import create_app

        app = create_app()
        import uvicorn

        logger.info("Starting Dermatology AI Dashboard on 0.0.0.0:%s", port)
        uvicorn.run(app, host="0.0.0.0", port=port, reload=reload)
    except Exception as e:
        logger.error("Cannot start dashboard server: %s", e)
        logger.error("Install required packages: pip install fastapi uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    env_port = int(os.environ.get("PORT", 0))
    parser = argparse.ArgumentParser(description="Dermatology AI — HITL System")
    parser.add_argument("--ui", action="store_true", help="Launch Gradio web UI instead of headless demo")
    parser.add_argument("--share", action="store_true", help="Generate a public Gradio share link (implies --ui)")
    parser.add_argument("--dashboard", action="store_true", help="Launch the redesigned clinical dashboard")
    parser.add_argument("--port", type=int, default=env_port or 7860, help="Dashboard server port (default: 7860 or $PORT)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload dashboard server on file changes")
    args = parser.parse_args()

    if args.dashboard or (not args.ui and not args.share):
        run_dashboard(port=args.port, reload=args.reload)
    elif args.ui or args.share:
        run_ui(share=args.share)
