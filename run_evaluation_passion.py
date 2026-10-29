#!/usr/bin/env python3
"""Evaluate the CBM checkpoint on the PASSION for Dermatology cohort.

Fixes over the previous version (which could not run at all):

* it imported ``dermatology_ai.datasetEquity`` / ``dermatology_ai.model`` -- a
  package that does not exist in this repository; the modules are top-level;
* it built its own preprocessing pipeline instead of using
  :func:`transforms.build_transform`, so evaluation drifted from training;
* it loaded the checkpoint without checking it against ``model_manifest.json``;
* it printed numbers that could not be recorded anywhere.

Usage
-----
    python scripts/download_passion.py            # once, to standardise the data
    python run_evaluation_passion.py --data-dir data/passion \
        --ckpt /secure/models/cbm_3class.pt --json reports/eval_passion.json

    python run_evaluation_passion.py --smoke      # plumbing check, invalid results
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from torch.utils.data import DataLoader

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "dermatology-ai"))
sys.path.insert(0, os.path.join(HERE, "dermatology-ai", "scripts"))

from eval_common import (  # noqa: E402
    CLASS_NAMES,
    build_report,
    env_checkpoint,
    load_verified_model,
    make_synthetic_dataset,
    write_report,
)
from datasetEquity import DermDataset  # noqa: E402
from transforms import build_transform  # noqa: E402


def evaluate(model, loader, device):
    labels, preds = [], []
    fitz_labels, fitz_preds = defaultdict(list), defaultdict(list)
    model.eval()
    with torch.no_grad():
        for images, batch_labels, fitz in loader:
            logits, _ = model(images.to(device))
            batch_preds = torch.argmax(F.softmax(logits, dim=1), dim=1)
            labels.extend(batch_labels.numpy().tolist())
            preds.extend(batch_preds.cpu().numpy().tolist())
            for label, pred, f in zip(batch_labels.numpy(), batch_preds.cpu().numpy(), fitz.numpy()):
                fitz_labels[int(f)].append(int(label))
                fitz_preds[int(f)].append(int(pred))

    precision, recall, f1, support = precision_recall_fscore_support(
        labels, preds, labels=[0, 1, 2], zero_division=0
    )
    metrics = {
        "n": len(labels),
        "accuracy": accuracy_score(labels, preds),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i in range(3)
        },
        "confusion_matrix": confusion_matrix(labels, preds, labels=[0, 1, 2]).tolist(),
    }
    per_fitz = {
        str(fitz): {"n": len(fitz_labels[fitz]),
                    "accuracy": float(accuracy_score(fitz_labels[fitz], fitz_preds[fitz]))}
        for fitz in sorted(fitz_labels)
    }
    return metrics, per_fitz


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CBM on PASSION (African skin tones)")
    parser.add_argument("--data-dir", default="dermatology-ai/datasets/passion")
    parser.add_argument("--ckpt", default=env_checkpoint())
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--json", default=None)
    parser.add_argument("--smoke", action="store_true",
                        help="Run on a synthetic dataset with random weights (invalid results)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if args.smoke:
        smoke_dir = Path(args.data_dir) / "smoke"
        csv_path = str(make_synthetic_dataset(smoke_dir))
        image_dir = str(smoke_dir)
        split_note = "synthetic smoke dataset (unsplit)"
    else:
        csv_path = os.path.join(args.data_dir, "metadata.csv")
        image_dir = os.path.join(args.data_dir, "images")
        if not os.path.isfile(csv_path) or not os.path.isdir(image_dir):
            raise FileNotFoundError(
                f"expected {csv_path} and {image_dir}; run scripts/download_passion.py first"
            )
        split_note = "PASSION metadata.csv (no hold-out declared in the CSV)"

    dataset = DermDataset(csv_path=csv_path, img_dir=image_dir, transform=build_transform("eval"))
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    print(f"Evaluating {len(dataset)} images")

    model, provenance = load_verified_model(args.ckpt, device, allow_random=args.smoke)
    metrics, per_fitz = evaluate(model, loader, device)

    print("\n=== PASSION evaluation ===")
    print(f"n = {metrics['n']}")
    print(f"Overall accuracy: {metrics['accuracy']:.4f}")
    for name, row in metrics["per_class"].items():
        print(f"  {name:15s} prec={row['precision']:.4f} rec={row['recall']:.4f} "
              f"f1={row['f1']:.4f} n={row['support']}")
    print("Confusion matrix (rows=true, cols=pred):")
    for row in metrics["confusion_matrix"]:
        print("  ", row)
    print("Per-Fitzpatrick accuracy:", per_fitz)

    report = build_report(dataset="PASSION", split=split_note, provenance=provenance,
                          metrics=metrics, per_fitzpatrick=per_fitz, smoke=args.smoke)
    write_report(args.json, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
