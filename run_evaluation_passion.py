#!/usr/bin/env python3
"""Evaluation of the CBM checkpoint on the PASSION for Dermatology dataset.

Prerequisites (run once):
  1. Download the PASSION dataset from https://passionderm.github.io/ .
     The downloaded archive should contain a CSV (e.g. `metadata.csv`) and an
     `images/` directory with JPEG files.
  2. Extract the archive so that the CSV and images live under a folder, e.g.:
        data/passion/metadata.csv
        data/passion/images/<image_id>.jpg
  3. Run the download script to standardize: python scripts/download_passion.py
  4. Ensure the Python environment has the requirements from
     `dermatology-ai/requirements.txt` (torch, timm, albumentations, etc.).

The script performs a deterministic 80/20 train-val split (seed 42), loads
the pre-trained CBM checkpoint (`dermatology-ai/model_checkpoints/cbm_3class.pt`),
runs inference on the validation set, and prints the same set of metrics as
the HAM10000 script.
"""

import os
import sys
import random
import argparse

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    roc_auc_score,
)
import albumentations as A
from albumentations.pytorch import ToTensorV2

# Project imports (relative to repository root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dermatology_ai.datasetEquity import DermDataset
from dermatology_ai.model import DermatologyCBM
from dermatology_ai.samplesEquity import MelaninNormalization


def build_dataset(csv_path, img_dir):
    """Create a DermDataset with the PASSION transforms.
    The CSV must contain columns: `image_id`, `label`, `fitzpatrick_type`.
    """
    transform = A.Compose([
        MelaninNormalization(),
        A.Resize(224, 224),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    return DermDataset(csv_path=csv_path, img_dir=img_dir, transform=transform)


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
    """Evaluate per-Fitzpatrick skin type."""
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

    print("\n=== Per-Fitzpatrick Evaluation ===")
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
    parser = argparse.ArgumentParser(
        description='Evaluate CBM on PASSION (African-skin-tone) dataset'
    )
    parser.add_argument(
        '--data-dir', default='dermatology-ai/datasets/passion', help='Root folder with metadata.csv and images/'
    )
    parser.add_argument(
        '--ckpt', default='dermatology-ai/model_checkpoints/cbm_3class.pt', help='Path to CBM checkpoint'
    )
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'Using device: {device}')

    # Load model
    print(f'Loading CBM checkpoint from {args.ckpt}')
    model = DermatologyCBM(
        num_classes=3,
        num_concepts=7,
        hrnet_name='hrnet_w18',
        pretrained_backbone=True,
        freeze_backbone=False,
    ).to(device)
    state = torch.load(args.ckpt, map_location=device)
    model.load_state_dict(state)

    # Build PASSION dataset
    csv_path = os.path.join(args.data_dir, 'val_meta.csv')
    img_dir = os.path.join(args.data_dir, 'images')
    if not os.path.isfile(csv_path) or not os.path.isdir(img_dir):
        raise FileNotFoundError(
            f'Cannot find CSV at {csv_path} or image folder at {img_dir}.\n'
            'Please run the download script first: python scripts/download_passion.py'
        )
    full_ds = build_dataset(csv_path, img_dir)
    val_loader = DataLoader(full_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Evaluate overall
    acc, prec, rec, f1, auroc, conf = evaluate(model, val_loader, device)

    print('\n=== PASSION evaluation (20% hold-out) ===')
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