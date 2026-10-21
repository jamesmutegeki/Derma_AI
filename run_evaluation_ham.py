#!/usr/bin/env python3
"""Evaluation of the CBM checkpoint on a 20% hold-out of the HAM10000 dataset.

The script:
  1. Loads the pretrained CBM checkpoint (`dermatology-ai/model_checkpoints/cbm_3class.pt`).
  2. Builds a deterministic 80/20 train-val split (seed 42) using the original HAM10000 CSV.
  3. Runs inference on the validation set.
  4. Prints overall accuracy, per-class precision/recall/F1, AUROC (one-vs-rest) and the confusion matrix.

Prerequisites: a Python environment with the dependencies listed in
`dermatology-ai/requirements.txt` (torch, timm, albumentations, scikit-learn, etc.).
"""

import os
import sys
import random
import argparse

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    roc_auc_score,
)
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2

# Project imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dermatology-ai'))
from datasetEquity import DermDataset, MultiSourceDermDataset
from model import DermatologyCBM
from samplesEquity import MelaninNormalization


class EvalTransform:
    """Wrapper to make albumentations work with DermDataset's PIL image input."""
    def __init__(self, transform):
        self.transform = transform

    def __call__(self, pil_img):
        out = self.transform(image=np.array(pil_img.convert("RGB")))
        return out["image"]


def build_dataset(csv_path, data_root):
    base_transform = A.Compose([
        MelaninNormalization(),
        A.Resize(224, 224),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    transform = EvalTransform(base_transform)
    return MultiSourceDermDataset(csv_path=csv_path, data_root=data_root, transform=transform)


def deterministic_val_split(dataset, seed=42, train_frac=0.80):
    random.seed(seed)
    indices = list(range(len(dataset)))
    random.shuffle(indices)
    split = int(train_frac * len(indices))
    val_idx = indices[split:]
    return Subset(dataset, val_idx)


def evaluate(model, loader, device):
    all_labels = []
    all_preds = []
    all_probs = []
    model.eval()
    with torch.no_grad():
        for imgs, labels, _ in loader:
            imgs = imgs.to(device)
            logits, _ = model(imgs)
            probs = F.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            all_labels.extend(labels.cpu().numpy())
            all_preds.extend(preds.cpu().numpy())
            all_probs.extend(probs.cpu().numpy())
    acc = accuracy_score(all_labels, all_preds)
    prec, rec, f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, average=None, labels=[0, 1, 2]
    )
    conf = confusion_matrix(all_labels, all_preds, labels=[0, 1, 2])
    auroc = []
    for i in range(3):
        y_true = [1 if l == i else 0 for l in all_labels]
        y_score = [p[i] for p in all_probs]
        try:
            auc = roc_auc_score(y_true, y_score)
        except ValueError:
            auc = float('nan')
        auroc.append(auc)
    return acc, prec, rec, f1, auroc, conf


def evaluate_per_fitzpatrick(model, loader, device):
    """Evaluate per-Fitzpatrick skin type (HAM10000 uses placeholder Fitzpatrick=3)."""
    from collections import defaultdict
    fitz_labels = defaultdict(list)
    fitz_preds = defaultdict(list)
    fitz_probs = defaultdict(list)

    model.eval()
    with torch.no_grad():
        for imgs, labels, fitz in loader:
            imgs = imgs.to(device)
            logits, _ = model(imgs)
            probs = F.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)

            for l, p, pr, f in zip(labels.cpu().numpy(), preds.cpu().numpy(), probs.cpu().numpy(), fitz.cpu().numpy()):
                fitz_labels[int(f)].append(l)
                fitz_preds[int(f)].append(p)
                fitz_probs[int(f)].append(pr)

    print("\n=== Per-Fitzpatrick Evaluation (HAM10000 uses placeholder Fitz=3) ===")
    class_names = ['benign', 'melanoma', 'kaposi_sarcoma']
    for fitz in range(1, 7):
        if fitz not in fitz_labels or len(fitz_labels[fitz]) == 0:
            continue
        labels = fitz_labels[fitz]
        preds = fitz_preds[fitz]
        probs = fitz_probs[fitz]
        n = len(labels)
        acc = accuracy_score(labels, preds)
        print(f"\n  Fitzpatrick Type {fitz} (n={n}):")
        print(f"    Accuracy: {acc:.4f}")
        prec, rec, f1, _ = precision_recall_fscore_support(
            labels, preds, average=None, labels=[0, 1, 2]
        )
        for i, name in enumerate(class_names):
            if i < len(prec):
                print(f"    {name:15s} – Prec: {prec[i]:.4f}  Rec: {rec[i]:.4f}  F1: {f1[i]:.4f}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate CBM on HAM10000 (20% hold-out)')
    parser.add_argument('--data-dir', default='dermatology-ai/datasets/ham10000', help='Root folder containing HAM10000 CSV and images')
    parser.add_argument('--ckpt', default='dermatology-ai/model_checkpoints/smoke_cbm.pt', help='Path to CBM checkpoint')
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')

    # Load model - smoke_cbm.pt is 2-class (binary: benign/melanoma)
    # Check checkpoint to determine num_classes
    state = torch.load(args.ckpt, map_location=device)
    num_classes = 2 if 'classifier.weight' in state and state['classifier.weight'].shape[0] == 2 else 3
    print(f'Detected model classes: {num_classes}')

    model = DermatologyCBM(
        num_classes=num_classes,
        num_concepts=7,
        hrnet_name='hrnet_w18',
        pretrained_backbone=True,
        freeze_backbone=False,
    ).to(device)
    model.load_state_dict(state)

    # Build dataset - use the pre-split validation metadata
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'dermatology-ai', 'datasets', 'val_meta.csv')
    data_root = os.path.join(base_dir, 'dermatology-ai', 'datasets')
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f'CSV not found at {csv_path}')
    full_ds = build_dataset(csv_path, data_root)
    val_loader = DataLoader(full_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Evaluate
    acc, prec, rec, f1, auroc, conf = evaluate(model, val_loader, device)

    print('\n=== HAM10000 evaluation (20% hold-out) ===')
    print(f'Overall accuracy: {acc:.4f}')
    class_names = ['benign', 'melanoma', 'kaposi_sarcoma']
    for i, name in enumerate(class_names):
        print(
            f'  {name:15s} – Prec: {prec[i]:.4f}  Rec: {rec[i]:.4f}  '
            f'F1: {f1[i]:.4f}  AUROC: {auroc[i]:.4f}'
        )
    print('\nConfusion matrix (rows=true, cols=pred):')
    print(conf)

    # Per-Fitzpatrick evaluation
    evaluate_per_fitzpatrick(model, val_loader, device)


if __name__ == '__main__':
    main()