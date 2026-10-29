"""Shared plumbing for ``run_evaluation_ham.py`` and ``run_evaluation_passion.py``.

Why this module exists: both evaluation scripts used to build their own
preprocessing pipeline (which drifted from training) and the PASSION script
imported a ``dermatology_ai`` package that does not exist, so neither could run.
Everything that decides *what the numbers mean* now lives here once:

* the eval transform comes from :func:`transforms.build_transform`;
* the checkpoint is verified against ``model_manifest.json`` before it is loaded;
* a report is marked ``valid`` only when a frozen checkpoint was used;
* ``--smoke`` can exercise the whole path with random weights, but the resulting
  report is explicitly ``valid: false`` and cannot be frozen into the manifest.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

CLASS_NAMES = ["benign", "melanoma", "kaposi_sarcoma"]


def add_app_to_path() -> None:
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))


def load_verified_model(checkpoint: str | None, device, allow_random: bool):
    """Load the CBM, verifying it against the manifest.

    Returns ``(model, provenance)`` where ``provenance`` contains
    ``{"checkpoint": path|None, "sha256": str, "weights": "frozen"|"random"}``.
    Raises ``SystemExit`` if the checkpoint is missing unless ``allow_random``.
    """
    add_app_to_path()
    import torch

    from backend import file_sha256, load_manifest, manifest_error
    from model import DermatologyCBM

    if not checkpoint or not Path(checkpoint).is_file():
        if not allow_random:
            raise SystemExit(
                f"Checkpoint not found: {checkpoint!r}. Pass --ckpt, or use --smoke to "
                "exercise the script with random weights (the report will be invalid)."
            )
        print("!" * 78)
        print("SMOKE MODE: random weights. The numbers produced are MEANINGLESS and the")
        print("report is written with valid=false so it cannot be frozen into the manifest.")
        print("!" * 78)
        model = DermatologyCBM(num_classes=3, num_concepts=7, hrnet_name="hrnet_w18",
                               pretrained_backbone=False, freeze_backbone=False).to(device)
        model.eval()
        return model, {"checkpoint": None, "sha256": "", "weights": "random"}

    sha = file_sha256(checkpoint)
    manifest = load_manifest()
    problem = manifest_error(manifest, sha)
    if problem:
        raise SystemExit(f"Checkpoint rejected by the manifest: {problem}")

    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    num_classes = int(state["classifier.weight"].shape[0])
    problem = manifest_error(manifest, sha, num_classes)
    if problem:
        raise SystemExit(f"Checkpoint rejected by the manifest: {problem}")

    model = DermatologyCBM(
        num_classes=num_classes,
        num_concepts=7,
        hrnet_name="hrnet_w18",
        pretrained_backbone=False,  # weights come from the checkpoint
        freeze_backbone=False,
    ).to(device)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, {"checkpoint": str(checkpoint), "sha256": sha, "weights": "frozen"}


def build_report(*, dataset: str, split: str, provenance: dict, metrics: dict,
                 per_fitzpatrick: dict | None = None, smoke: bool = False) -> dict:
    """Assemble the JSON report that a manifest / poster may cite."""
    frozen = provenance.get("weights") == "frozen"
    return {
        "dataset": dataset,
        "split": split,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "smoke": bool(smoke),
        # A report is only citable when real, verified weights produced it.
        "valid": bool(frozen and not smoke),
        "checkpoint": provenance,
        "metrics": metrics,
        "per_fitzpatrick": per_fitzpatrick or {},
        "notes": [
            "Produced by scripts/eval_common.py consumers; do not hand-edit.",
            "valid=false reports must not be quoted anywhere.",
        ],
    }


def write_report(path: str | None, report: dict) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nWrote evaluation report: {target} (valid={report['valid']})")


def make_synthetic_dataset(directory: Path, n_per_class: int = 4, size: int = 64) -> Path:
    """Create a tiny on-disk dataset so the evaluation path can be exercised.

    Returns the metadata CSV path.  Images are solid-colour noise-free PNGs --
    enough to prove the pipeline runs, not enough to mean anything.
    """
    import numpy as np
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    rows = ["image_id,label,fitzpatrick_type"]
    for label_index, label in enumerate(CLASS_NAMES):
        for i in range(n_per_class):
            image_id = f"smoke_{label}_{i}"
            pixels = np.full((size, size, 3), 40 + 50 * label_index, dtype=np.uint8)
            Image.fromarray(pixels).save(directory / f"{image_id}.jpg", quality=90)
            rows.append(f"{image_id},{label},{(i % 6) + 1}")
    csv_path = directory / "smoke_meta.csv"
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return csv_path


def env_checkpoint() -> str | None:
    return os.environ.get("MODEL_CHECKPOINT_PATH") or None
