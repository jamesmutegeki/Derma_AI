"""Model / agent runtime for the dashboard.

Responsibilities:

* load a **real** checkpoint from ``MODEL_CHECKPOINT_PATH`` and verify that its
  classifier head matches the requested class count;
* report, honestly, that no model is available when it cannot load;
* run inference and register the case with the fairness tracker, recording the
  model's prediction as a *prediction* and never as ground truth.

There is no mock/fallback path.  A missing checkpoint means ``ready == False``
and every inference call raises :class:`ModelUnavailable`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from constants import FITZPATRICK_LABELS, TRIAGE_NAMES
from metrics_tracker import CaseRecord, FairnessTracker
from storage import Store

logger = logging.getLogger(__name__)

CLASS_NAMES = ["benign", "melanoma", "kaposi_sarcoma"]


class ModelUnavailable(RuntimeError):
    """Raised when inference is requested but no usable model is loaded."""


@dataclass
class BackendStatus:
    model_ready: bool = False
    agent_ready: bool = False
    reason: str = "not initialised"
    model_version: str = ""
    weights_sha256: str = ""
    device: str = "cpu"

    def as_dict(self) -> dict:
        return asdict(self)


MANIFEST_ENV = "MODEL_MANIFEST_PATH"
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "model_manifest.json"


def load_manifest(path: str | Path | None = None) -> Optional[dict]:
    """Load the model manifest, or ``None`` when there is none.

    A malformed manifest is a hard error inside :meth:`Backend._initialise`,
    never a silently ignored file.
    """
    candidate = Path(path) if path else Path(os.environ.get(MANIFEST_ENV, DEFAULT_MANIFEST))
    if not candidate.is_file():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def manifest_error(manifest: Optional[dict], sha256: str, num_classes: int | None = None) -> str:
    """Return a human-readable reason the checkpoint is not the frozen artefact.

    Empty string means "consistent" (or no manifest to check against).
    """
    if not manifest:
        return ""
    expected = (manifest.get("checkpoint") or {}).get("sha256")
    if expected and expected != sha256:
        return (f"checkpoint hash mismatch: manifest expects {expected[:12]}..., "
                f"file is {sha256[:12]}...")
    if manifest.get("status") == "frozen" and not expected:
        return "manifest is marked frozen but records no checkpoint hash"
    expected_classes = (manifest.get("architecture") or {}).get("num_classes")
    if num_classes is not None and expected_classes is not None and int(expected_classes) != int(num_classes):
        return (f"checkpoint has {num_classes} classes, manifest describes {expected_classes}")
    return ""


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Backend:
    def __init__(
        self,
        store_store: Store,
        tracker: FairnessTracker,
        model_path: Optional[str] = None,
        agent_path: Optional[str] = None,
        device: Optional[str] = None,
        num_concepts: int = 7,
    ):
        self.store = store_store
        self.tracker = tracker
        self.model_path = model_path if model_path is not None else os.environ.get("MODEL_CHECKPOINT_PATH", "")
        self.agent_path = agent_path if agent_path is not None else os.environ.get("AGENT_CHECKPOINT_PATH", "")
        self.device_name = device
        self.num_concepts = num_concepts

        self.manifest_path = os.environ.get(MANIFEST_ENV) or str(DEFAULT_MANIFEST)
        self._lock = threading.Lock()
        self._initialising = False
        self.status = BackendStatus(reason="not initialised")

        self.model = None
        self.agent = None
        self.device = None
        self._transform = None

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.status.model_ready

    def initialise(self) -> BackendStatus:
        """Load model + agent once.  Never raises for a missing checkpoint."""
        with self._lock:
            if self.status.model_ready or self.status.reason == "failed":
                return self.status
            self._initialising = True
            try:
                self._initialise()
            finally:
                self._initialising = False
            return self.status

    def _initialise(self) -> None:
        try:
            import torch
        except ImportError as exc:
            self.status = BackendStatus(reason=f"torch is not installed ({exc})")
            logger.warning("Model unavailable: %s", self.status.reason)
            return

        self.device = torch.device(self.device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.status.device = str(self.device)

        # A frozen artefact can be deliberately withheld from serving -- the
        # current case is gate 1A: the weights exist, but the third class has no
        # training data until a Kaposi sarcoma cohort is obtained, so nothing is
        # allowed to answer a diagnosis request.  Checked before the checkpoint
        # is touched, so a held manifest never even opens the file.
        manifest = load_manifest(self.manifest_path)
        serving = (manifest or {}).get("serving") or {}
        if serving.get("enabled") is False:
            reason = serving.get("reason") or "serving is disabled in the model manifest"
            self.status = BackendStatus(reason=f"model serving is on hold: {reason}",
                                        device=str(self.device))
            logger.warning("Model unavailable: %s", self.status.reason)
            return

        if not self.model_path:
            self.status = BackendStatus(
                reason="MODEL_CHECKPOINT_PATH is not set; no model weights were loaded",
                device=str(self.device),
            )
            logger.warning("Model unavailable: %s", self.status.reason)
            return

        checkpoint = Path(self.model_path)
        if not checkpoint.is_file():
            self.status = BackendStatus(
                reason=f"checkpoint not found at {checkpoint}",
                device=str(self.device),
            )
            logger.error("Model unavailable: %s", self.status.reason)
            return

        try:
            sha = file_sha256(checkpoint)
            manifest = load_manifest(self.manifest_path)

            # ML FIX: verify the hash *before* unpickling, so a file that is not the
            # frozen artefact is never even parsed.  Before this check any file at
            # MODEL_CHECKPOINT_PATH was served as "the model", which made every
            # reported number unattributable.
            problem = manifest_error(manifest, sha)
            if problem:
                raise ValueError(f"rejected by {Path(self.manifest_path).name}: {problem}")

            state = torch.load(str(checkpoint), map_location="cpu", weights_only=True)
            if "classifier.weight" not in state:
                raise ValueError("checkpoint has no 'classifier.weight'; not a DermatologyCBM state_dict")
            num_classes = int(state["classifier.weight"].shape[0])

            problem = manifest_error(manifest, sha, num_classes)
            if problem:
                raise ValueError(f"rejected by {Path(self.manifest_path).name}: {problem}")

            from model import DermatologyCBM

            model = DermatologyCBM(
                num_classes=num_classes,
                num_concepts=self.num_concepts,
                hrnet_name="hrnet_w18",
                pretrained_backbone=False,  # weights come from the checkpoint
                freeze_backbone=False,
            )
            model.load_state_dict(state, strict=True)
            model.eval()
            model = model.to(self.device)

            from transforms import build_transform

            self.model = model
            self._transform = build_transform("eval")
            self.status = BackendStatus(
                model_ready=True,
                agent_ready=False,
                reason="ok",
                model_version=(f"{(manifest or {}).get('checkpoint', {}).get('filename') or checkpoint.name}"
                               f"@{sha[:12]}"),
                weights_sha256=sha,
                device=str(self.device),
            )
            logger.info("Loaded model %s (%d classes, sha256=%s...)",
                        checkpoint.name, num_classes, sha[:12])
        except Exception as exc:  # noqa: BLE001 - reported, never masked
            self.model = None
            self.status = BackendStatus(
                reason=f"failed to load checkpoint: {exc}",
                device=str(self.device),
            )
            logger.exception("Model load failed")
            return

        self._load_agent(torch)

    def _load_agent(self, torch) -> None:
        if not self.agent_path:
            logger.warning("AGENT_CHECKPOINT_PATH is not set; triage will be unavailable")
            return
        path = Path(self.agent_path)
        if not path.is_file():
            logger.warning("Agent checkpoint %s not found; triage will be unavailable", path)
            return
        try:
            from rl_module import PPOAgent, NUM_FITZ_TYPES

            agent = PPOAgent(state_dim=self.num_concepts + NUM_FITZ_TYPES, action_dim=3, device=self.device)
            agent.load(str(path))
            self.agent = agent
            self.status.agent_ready = True
            logger.info("Loaded triage agent from %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent load failed: %s", exc)

    # ------------------------------------------------------------------
    #  Inference
    # ------------------------------------------------------------------

    def diagnose(self, image: np.ndarray, fitzpatrick: int) -> dict:
        if not self.ready:
            raise ModelUnavailable(self.status.reason)
        if self.model is None or self._transform is None:
            raise ModelUnavailable("model not loaded")

        import torch

        tensor = self._transform(image).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits, concepts = self.model(tensor)
            probabilities = torch.softmax(logits, dim=1)[0].cpu().numpy()
            pred_class = int(np.argmax(probabilities))
            concept_vector = concepts[0].cpu().numpy()

        triage_action = None
        if self.agent is not None:
            state = np.concatenate([
                concept_vector.astype(np.float32),
                np.eye(6, dtype=np.float32)[fitzpatrick - 1],
            ])
            triage_action = int(self.agent.evaluate(state))

        from model import CONCEPT_NAMES

        case_id = f"CASE-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        record = CaseRecord(
            case_id=case_id,
            fitz_type=fitzpatrick,
            predicted_label=pred_class,
            model_triage=triage_action,
            ground_truth_label=None,
            ground_truth_confirmed=False,
            concepts=[float(v) for v in concept_vector],
            source="live",
        )
        self.tracker.register_case(record)

        return {
            "case_id": case_id,
            "concepts": {name: round(float(concept_vector[i]), 4) for i, name in enumerate(CONCEPT_NAMES)},
            "probabilities": {CLASS_NAMES[i]: round(float(p), 6) for i, p in enumerate(probabilities)},
            "predicted_class": CLASS_NAMES[pred_class],
            "predicted_class_index": pred_class,
            "triage": TRIAGE_NAMES[triage_action] if triage_action is not None else None,
            "triage_index": triage_action,
            "triage_available": triage_action is not None,
            "fitzpatrick": fitzpatrick,
            "fitzpatrick_label": FITZPATRICK_LABELS[fitzpatrick - 1],
            "model_version": self.status.model_version,
            "weights_sha256": self.status.weights_sha256,
            "ground_truth_confirmed": False,
            "simulated": False,
            "confidence_caveat": (
                "Kaposi sarcoma class is trained on synthetic data only and is unvalidated "
                "on real images."
            ) if pred_class == 2 else None,
        }
