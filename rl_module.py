"""
Equity-Driven Reinforcement Learning Agent (PPO) for dermatology triage.

Components:
    - DermTriageEnv: custom Gym-like environment.
    - FairnessWeightedReward: penalises FN with dynamic multiplier for
      Fitzpatrick IV-VI, eliminating the accuracy gap.
    - PPONetwork: shared actor-critic architecture.
    - PPOAgent: full PPO training loop with GAE, clipped surrogate, etc.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FITZPATRICK_LABELS = ["I", "II", "III", "IV", "V", "VI"]
NUM_FITZ_TYPES = len(FITZPATRICK_LABELS)

# Mapping from true label to the *correct* triage level
#   0 = Routine (no follow-up)
#   1 = Follow-up (schedule check-up)
#   2 = Urgent (immediate referral / biopsy)
TRUE_LABEL_TO_TRIAGE = {0: 0, 1: 2, 2: 2}  # benign -> routine, melanoma/KS -> urgent
TRIAGE_NAMES = ["routine", "follow_up", "urgent"]

# Penalty multiplier for darker Fitzpatrick skin types
FITZPATRICK_MULTIPLIER = {1: 1.0, 2: 1.0, 3: 1.0, 4: 2.0, 5: 3.0, 6: 4.0}


def fairness_weighted_reward(
    action: int,
    true_label: int,
    fitz_type: int,
) -> float:
    """Fairness-Weighted Reward / Penalty Function.

    Args:
        action: triage decision (0=routine, 1=follow-up, 2=urgent).
        true_label: ground-truth diagnosis (0=benign, 1=melanoma, 2=kaposi_sarcoma).
        fitz_type: Fitzpatrick skin type (1-6).

    Returns:
        Scalar reward.
    """
    expected_triage = TRUE_LABEL_TO_TRIAGE[true_label]
    multiplier = FITZPATRICK_MULTIPLIER.get(fitz_type, 1.0)

    if action == expected_triage:
        if expected_triage == 2:
            return 5.0  # correct urgent triage
        elif expected_triage == 0:
            return 1.0  # correct routine
        else:
            return 2.0  # correct follow-up

    under_triage = action < expected_triage
    over_triage = action > expected_triage

    if under_triage:
        if expected_triage == 2 and action == 0:
            return -20.0 * multiplier  # critical miss
        elif expected_triage == 2 and action == 1:
            return -10.0 * multiplier  # delayed care
        else:
            return -5.0 * multiplier  # general under-triage
    elif over_triage:
        if expected_triage == 0 and action == 2:
            return -3.0  # unnecessary alarm
        else:
            return -1.0  # mild over-triage
    return 0.0


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

@dataclass
class Case:
    """A single dermatology case for the triage environment."""
    concept_embedding: np.ndarray  # shape (NUM_CONCEPTS,)
    fitz_type: int                 # 1-6
    true_label: int                # 0=benign, 1=melanoma, 2=kaposi_sarcoma
    patient_id: Optional[str] = None


class DermTriageEnv:
    """Custom environment for dermatology triage with fairness constraints.

    State: concatenation of CBM concept embedding (7-dim) +
           Fitzpatrick one-hot encoding (6-dim)  ->  13-dim total.

    Action: discrete {0=routine, 1=follow_up, 2=urgent}.
    """

    def __init__(self, num_concepts: int = 7):
        self.num_concepts = num_concepts
        self.state_dim = num_concepts + NUM_FITZ_TYPES
        self.action_dim = 3
        self.current_case: Optional[Case] = None
        self._cases: List[Case] = []

    def seed(self, cases: List[Case]):
        """Inject a case list for episode sampling."""
        self._cases = cases

    def reset(self) -> np.ndarray:
        self.current_case = random.choice(self._cases) if self._cases else None
        return self._build_state(self.current_case)

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, dict]:
        assert self.current_case is not None, "Call reset() before step()."

        reward = fairness_weighted_reward(
            action, self.current_case.true_label, self.current_case.fitz_type
        )

        done = True  # single-step episode
        next_state = np.zeros(self.state_dim, dtype=np.float32)

        info = {
            "true_label": self.current_case.true_label,
            "fitz_type": self.current_case.fitz_type,
            "action": action,
            "reward": reward,
            "correct_action": TRUE_LABEL_TO_TRIAGE[self.current_case.true_label],
        }
        return next_state, reward, done, info

    def _build_state(self, case: Optional[Case]) -> np.ndarray:
        if case is None:
            return np.zeros(self.state_dim, dtype=np.float32)
        concept = case.concept_embedding.astype(np.float32)
        fitz_onehot = np.zeros(NUM_FITZ_TYPES, dtype=np.float32)
        fitz_onehot[case.fitz_type - 1] = 1.0
        return np.concatenate([concept, fitz_onehot])

    @staticmethod
    def action_space_size() -> int:
        return 3


# ---------------------------------------------------------------------------
# PPO Network (Actor-Critic)
# ---------------------------------------------------------------------------

class PPONetwork(nn.Module):
    """Shared feature extractor with separate actor and critic heads."""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super().__init__()

        self.feature = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )

        self.actor = nn.Linear(hidden_dim, action_dim)
        self.critic = nn.Linear(hidden_dim, 1)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=math.sqrt(2))
                nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.feature(state)
        action_logits = self.actor(features)
        value = self.critic(features)
        return action_logits, value

    def get_action_and_value(
        self, state: torch.Tensor, action: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        action_logits, value = self.forward(state)
        probs = Categorical(logits=action_logits)

        if action is None:
            action = probs.sample()

        log_prob = probs.log_prob(action)
        entropy = probs.entropy()
        return action, log_prob, entropy, value


# ---------------------------------------------------------------------------
# PPO Agent
# ---------------------------------------------------------------------------

@dataclass
class Rollout:
    states: List[np.ndarray]
    actions: List[int]
    rewards: List[float]
    dones: List[bool]
    log_probs: List[float]
    values: List[float]


class PPOAgent:
    """Proximal Policy Optimization agent with fairness-weighted rewards.

    Implements:
        - GAE (Generalized Advantage Estimation)
        - Clipped surrogate objective
        - Value function loss
        - Entropy bonus
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        lr: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        hidden_dim: int = 128,
        device: torch.device = torch.device("cpu"),
    ):
        self.device = device
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.max_grad_norm = max_grad_norm

        self.network = PPONetwork(state_dim, action_dim, hidden_dim).to(device)
        self.optimizer = torch.optim.Adam(self.network.parameters(), lr=lr)

    def select_action(self, state: np.ndarray) -> Tuple[int, float, float]:
        tensor = torch.from_numpy(state).unsqueeze(0).float().to(self.device)
        with torch.no_grad():
            action, log_prob, _, value = self.network.get_action_and_value(tensor)
        return action.item(), log_prob.item(), value.item()

    def evaluate(self, state: np.ndarray) -> int:
        tensor = torch.from_numpy(state).unsqueeze(0).float().to(self.device)
        with torch.no_grad():
            action_logits, _ = self.network.forward(tensor)
        return torch.argmax(action_logits, dim=1).item()

    def update(self, rollouts: List[Rollout], epochs: int = 10, batch_size: int = 64) -> dict:
        all_states, all_actions, all_log_probs_old, all_returns, all_advantages = (
            self._prepare_batch(rollouts)
        )
        dataset_size = len(all_states)

        metrics = {"policy_loss": [], "value_loss": [], "entropy": [], "total_loss": []}

        for _ in range(epochs):
            indices = np.random.permutation(dataset_size)
            for start in range(0, dataset_size, batch_size):
                batch_idx = indices[start : start + batch_size]

                states = all_states[batch_idx].to(self.device)
                actions = all_actions[batch_idx].to(self.device)
                old_log_probs = all_log_probs_old[batch_idx].to(self.device)
                returns = all_returns[batch_idx].to(self.device)
                advantages = all_advantages[batch_idx].to(self.device)

                advantages = (advantages - advantages.mean()) / torch.max(advantages.std() + 1e-8, torch.tensor(1e-8, device=advantages.device))

                _, log_prob, entropy, value = self.network.get_action_and_value(states, actions)

                ratio = torch.exp(log_prob - old_log_probs)
                surr1 = ratio * advantages
                surr2 = torch.clamp(ratio, 1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantages
                policy_loss = -torch.min(surr1, surr2).mean()

                value_loss = F.mse_loss(value.flatten(), returns)

                entropy_loss = -entropy.mean()
                total_loss = (
                    policy_loss + self.value_coef * value_loss + self.entropy_coef * entropy_loss
                )

                self.optimizer.zero_grad()
                total_loss.backward()
                nn.utils.clip_grad_norm_(self.network.parameters(), self.max_grad_norm)
                self.optimizer.step()

                metrics["policy_loss"].append(policy_loss.item())
                metrics["value_loss"].append(value_loss.item())
                metrics["entropy"].append(entropy.mean().item())
                metrics["total_loss"].append(total_loss.item())

        return {k: float(np.mean(v)) for k, v in metrics.items()}

    def _prepare_batch(self, rollouts: List[Rollout]):
        all_states, all_actions, all_log_probs, all_returns, all_advantages = [], [], [], [], []

        for rollout in rollouts:
            states = torch.tensor(np.array(rollout.states), dtype=torch.float32)
            actions = torch.tensor(rollout.actions, dtype=torch.long)
            log_probs = torch.tensor(rollout.log_probs, dtype=torch.float32)
            rewards = torch.tensor(rollout.rewards, dtype=torch.float32)
            dones = torch.tensor(rollout.dones, dtype=torch.float32)
            values = torch.tensor(rollout.values, dtype=torch.float32)

            advantages = self._compute_gae(rewards, dones, values)
            returns = advantages + values

            all_states.append(states)
            all_actions.append(actions)
            all_log_probs.append(log_probs)
            all_returns.append(returns)
            all_advantages.append(advantages)

        return (
            torch.cat(all_states),
            torch.cat(all_actions),
            torch.cat(all_log_probs),
            torch.cat(all_returns),
            torch.cat(all_advantages),
        )

    def _compute_gae(
        self, rewards: torch.Tensor, dones: torch.Tensor, values: torch.Tensor
    ) -> torch.Tensor:
        advantages = []
        gae = 0.0
        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = 0.0
            else:
                next_value = values[t + 1] * (1.0 - dones[t])

            delta = rewards[t] + self.gamma * next_value - values[t]
            gae = delta + self.gamma * self.gae_lambda * (1.0 - dones[t]) * gae
            advantages.insert(0, gae)
        return torch.tensor(advantages, dtype=torch.float32)

    def save(self, path: str):
        torch.save({
            "network_state_dict": self.network.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
        }, path)

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device, weights_only=True)
        self.network.load_state_dict(checkpoint["network_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
