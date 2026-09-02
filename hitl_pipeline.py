"""
Human-in-the-Loop (HITL) & Active Learning Pipeline.

Provides:
    - ClinicianOverride: dataclass for a single manual override.
    - HITLPipeline: orchestrates daily clinician overrides and feeds corrections
      into the PPO agent via offline policy optimisation.
    - OfflinePolicyOptimizer: uses clinician corrections as ground-truth
      reward signals to update the PPO policy.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
import torch

from rl_module import (
    PPOAgent,
    Rollout,
    fairness_weighted_reward,
    TRUE_LABEL_TO_TRIAGE,
)

logger = logging.getLogger(__name__)


@dataclass
class ClinicianOverride:
    """Record of a single clinician override during a daily session.

    Attributes:
        patient_id:    unique patient identifier.
        concept_embed: CBM concept scores (7-dim) that formed the state.
        fitz_type:     Fitzpatrick skin type (1-6).
        true_label:    ground-truth diagnosis (set after biopsy / expert review).
        model_action:  triage action chosen by the PPO agent (0=routine, 1=follow-up, 2=urgent).
        clinician_action: triage action chosen by the clinician (the correction).
        timestamp:     ISO-format timestamp.
        notes:         optional free-text notes from the clinician.
    """

    patient_id: str
    concept_embed: List[float]
    fitz_type: int
    true_label: int
    model_action: int
    clinician_action: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""


class HITLPipeline:
    """Orchestrates the clinician-in-the-loop workflow.

    The daily workflow:
        1. Model processes cases → generates CBM embeddings + triage.
        2. Clinician reviews a subset and provides override decisions.
        3. Overrides are stored in a correction buffer.
        4. Offline policy optimisation updates the PPO agent.
    """

    def __init__(
        self,
        ppo_agent: PPOAgent,
        num_concepts: int = 7,
        buffer_capacity: int = 5000,
    ):
        self.ppo_agent = ppo_agent
        self.num_concepts = num_concepts
        self.num_fitz = 6
        self.state_dim = num_concepts + self.num_fitz

        self.correction_buffer: List[ClinicianOverride] = []
        self.buffer_capacity = buffer_capacity
        self.override_log: List[ClinicianOverride] = []

    def process_case(
        self,
        patient_id: str,
        concept_embed: np.ndarray,
        fitz_type: int,
        true_label: int,
        clinician_action: Optional[int] = None,
    ) -> Tuple[int, Optional[ClinicianOverride]]:
        """Run model triage and (optionally) record clinician override.

        Args:
            patient_id: patient identifier.
            concept_embed: CBM concept scores (7-dim).
            fitz_type: Fitzpatrick type (1-6).
            true_label: ground-truth label.
            clinician_action: if provided, this is the clinician's override.

        Returns:
            (model_action, override_record_or_None)
        """
        state = self._build_state(concept_embed, fitz_type)
        model_action = self.ppo_agent.evaluate(state)

        override = None
        if clinician_action is not None and clinician_action != model_action:
            override = ClinicianOverride(
                patient_id=patient_id,
                concept_embed=concept_embed.tolist(),
                fitz_type=fitz_type,
                true_label=true_label,
                model_action=model_action,
                clinician_action=clinician_action,
            )
            self._add_to_buffer(override)

        return model_action, override

    def _build_state(self, concept_embed: np.ndarray, fitz_type: int) -> np.ndarray:
        fitz_onehot = np.zeros(self.num_fitz, dtype=np.float32)
        fitz_onehot[fitz_type - 1] = 1.0
        return np.concatenate([concept_embed.astype(np.float32), fitz_onehot])

    def _add_to_buffer(self, override: ClinicianOverride):
        self.correction_buffer.append(override)
        self.override_log.append(override)
        if len(self.correction_buffer) > self.buffer_capacity:
            self.correction_buffer.pop(0)


class OfflinePolicyOptimizer:
    """Offline policy optimisation using clinician corrections.

    Uses clinician overrides as ground-truth signals to compute
    corrected rewards and update the PPO policy.
    """

    def __init__(
        self,
        ppo_agent: PPOAgent,
        learning_rate: float = 1e-4,
        num_epochs: int = 5,
        batch_size: int = 32,
    ):
        self.ppo_agent = ppo_agent
        self.num_epochs = num_epochs
        self.batch_size = batch_size

        for param_group in self.ppo_agent.optimizer.param_groups:
            param_group["lr"] = learning_rate

    def optimise(self, overrides: List[ClinicianOverride]) -> dict:
        """Run offline PPO update from clinician correction data.

        For each override, the *clinician's action* is treated as the
        ground-truth action, and a corrected reward is computed using
        the fairness-weighted reward function.

        Returns:
            dict of training metrics (policy_loss, value_loss, etc.)
        """
        if len(overrides) < 2:
            logger.warning("Not enough overrides for offline update (need >= 2).")
            return {}

        rollouts = self._overrides_to_rollouts(overrides)
        metrics = self.ppo_agent.update(
            rollouts,
            epochs=self.num_epochs,
            batch_size=min(self.batch_size, len(overrides)),
        )
        logger.info("Offline policy update complete: %s", metrics)
        return metrics

    def _overrides_to_rollouts(self, overrides: List[ClinicianOverride]) -> List[Rollout]:
        rollouts = []
        for ov in overrides:
            concept = np.array(ov.concept_embed, dtype=np.float32)
            state = np.concatenate([
                concept,
                np.eye(6, dtype=np.float32)[ov.fitz_type - 1],
            ])

            reward = fairness_weighted_reward(
                ov.clinician_action,
                ov.true_label,
                ov.fitz_type,
            )

            import torch
            state_t = torch.FloatTensor(state).to(self.ppo_agent.device).unsqueeze(0)
            action_t = torch.LongTensor([ov.clinician_action]).to(self.ppo_agent.device)
            with torch.no_grad():
                _, log_prob, _, value = self.ppo_agent.network.get_action_and_value(state_t, action_t)

            rollout = Rollout(
                states=[state],
                actions=[ov.clinician_action],
                rewards=[reward],
                dones=[True],
                log_probs=[log_prob.item()],
                values=[value.item()],
            )
            rollouts.append(rollout)
        return rollouts
