#!/usr/bin/env python3
"""Evaluate the CBM checkpoint on a held-out HAM10000 split.

Fixes over the previous version (which could not run at all):

* ``Subset`` is imported (it was an undefined name, so ``--smoke`` never worked);
* preprocessing comes from :func:`transforms.build_transform` -- the same
  pipeline the server uses, so evaluation cannot drift from training;
* the checkpoint is verified against ``model_manifest.json`` before loading;
* ``--json`` writes a machine-readable report, and only a report produced from
  frozen weights is marked ``valid`` -- those are the only numbers a poster or
  paper may quote.

Examples
--------
    python run_evaluation_ham.py --data-dir dermatology-ai/datasets/ham10000 \
        --ckpt /secure/models/cbm_3class.pt --json reports/eval_ham.json

    python run_evaluation_ham.py --smoke          # plumbing check, invalid results
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from torch.utils.data import DataLoader, Subset

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
from datasetEquity import DermDataset, MultiSourceDermDataset  # noqa: E402
from transforms import build_transform  # noqa: E402


def build_dataset(csv_path: str, data_root: str, flat: bool = False):
    transform = build_transform("eval")
    if flat:
        return DermDataset(csv_path=csv_path, img_dir=data_root, transform=transform)
    return MultiSourceDermDataset(csv_path=csv_path, data_root=data_root, transform=transform)


def assert_no_train_val_overlap(train_csv: str, val_csv: str) -> None:
    """Fail loudly if the hold-out shares images with the training split."""
    train_df, val_df = pd.read_csv(train_csv), pd.read_csv(val_csv)
    overlap = set(train_df["image_id"].astype(str)) & set(val_df["image_id"].astype(str))
    if overlap:
        raise AssertionError(
            f"train/val overlap: {len(overlap)} shared image_ids, e.g. {list(overlap)[:5]}"
        )
    print(f"[OK] zero train/val overlap (train={len(train_df)}, val={len(val_df)})")


def deterministic_val_split(dataset, seed: int = 42, train_frac: float = 0.80):
    """Deterministic hold-out when the dataset arrives unsplit."""
    rng = np.random.default_rng(seed)
    indices = rng.permutation(len(dataset))
    split = int(train_frac * len(indices))
    return Subset(dataset, indices[split:].tolist())


def evaluate(model, loader, device):
    labels, preds, probs = [], [], []
    model.eval()
    with torch.no_grad():
        for images, batch_labels, _fitz in loader:
            logits, _concepts = model(images.to(device))
            batch_probs = F.softmax(logits, dim=1)
            labels.extend(batch_labels.cpu().numpy().tolist())
            preds.extend(torch.argmax(batch_probs, dim=1).cpu().numpy().tolist())
            probs.extend(batch_probs.cpu().numpy().tolist())

    precision, recall, f1, support = precision_recall_fscore_support(
        labels, preds, labels=[0, 1, 2], zero_division=0
    )
    auroc = []
    for index in range(3):
        y_true = [1 if label == index else 0 for label in labels]
        y_score = [row[index] for row in probs]
        try:
            auroc.append(roc_auc_score(y_true, y_score))
        except ValueError:
            auroc.append(float("nan"))

    metrics = {
        "n": len(labels),
        "accuracy": accuracy_score(labels, preds),
        "per_class": {
            CLASS_NAMES[i]: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
                "auroc": float(auroc[i]),
            }
            for i in range(3)
        },
        "confusion_matrix": confusion_matrix(labels, preds, labels=[0, 1, 2]).tolist(),
    }
    return metrics


def evaluate_per_fitzpatrick(model, loader, device) -> dict:
    labels, preds = defaultdict(list), defaultdict(list)
    model.eval()
    with torch.no_grad():
        for images, batch_labels, fitz in loader:
            logits, _ = model(images.to(device))
            batch_preds = torch.argmax(F.softmax(logits, dim=1), dim=1)
            for label, pred, f in zip(batch_labels.cpu().numpy(),
                                      batch_preds.cpu().numpy(),
                                      fitz.cpu().numpy()):
                labels[int(f)].append(int(label))
                preds[int(f)].append(int(pred))

    out = {}
    for fitz_type in range(1, 7):
        if not labels.get(fitz_type):
            continue
        out[str(fitz_type)] = {
            "n": len(labels[fitz_type]),
            "accuracy": float(accuracy_score(labels[fitz_type], preds[fitz_type])),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CBM on a HAM10000 hold-out")
    parser.add_argument("--data-dir", default="dermatology-ai/datasets/ham10000")
    parser.add_argument("--ckpt", default=env_checkpoint())
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--json", default=None, help="Write a JSON report to this path")
    parser.add_argument("--smoke", action="store_true",
                        help="Run on a synthetic dataset with random weights (invalid results)")
    parser.add_argument("--split-seed", type=int, default=42)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if args.smoke:
        csv_path = str(make_synthetic_dataset(Path(args.data_dir) / "smoke"))
        dataset = build_dataset(csv_path, os.path.dirname(csv_path), flat=True)
        split_note = "synthetic smoke dataset (unsplit)"
    else:
        val_csv = os.path.join(args.data_dir, "val_meta.csv")
        train_csv = os.path.join(args.data_dir, "train_meta.csv")
        if os.path.isfile(val_csv):
            if os.path.isfile(train_csv):
                assert_no_train_val_overlap(train_csv, val_csv)
            dataset = build_dataset(val_csv, args.data_dir)
            split_note = "pre-split val_meta.csv"
        else:
            all_csv = os.path.join(args.data_dir, "metadata.csv")
            if not os.path.isfile(all_csv):
                raise FileNotFoundError(
                    f"no val_meta.csv or metadata.csv under {args.data_dir}; "
                    "run scripts/download_datasets.py first"
                )
            full = build_dataset(all_csv, args.data_dir)
            dataset = deterministic_val_split(full, seed=args.split_seed)
            split_note = f"deterministic 80/20, seed {args.split_seed}"

    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    print(f"Evaluating {len(dataset)} images ({split_note})")

    model, provenance = load_verified_model(args.ckpt, device, allow_random=args.smoke)
    metrics = evaluate(model, loader, device)
    per_fitz = evaluate_per_fitzpatrick(model, loader, device)

    print("\n=== Evaluation ===")
    print(f"n = {metrics['n']}")
    print(f"Overall accuracy: {metrics['accuracy']:.4f}")
    for name, row in metrics["per_class"].items():
        print(f"  {name:15s} prec={row['precision']:.4f} rec={row['recall']:.4f} "
              f"f1={row['f1']:.4f} auroc={row['auroc']:.4f} n={row['support']}")
    print("Confusion matrix (rows=true, cols=pred):")
    for row in metrics["confusion_matrix"]:
        print("  ", row)
    if per_fitz:
        print("Per-Fitzpatrick accuracy:", per_fitz)

    report = build_report(dataset="HAM10000", split=split_note, provenance=provenance,
                          metrics=metrics, per_fitzpatrick=per_fitz, smoke=args.smoke)
    write_report(args.json, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
