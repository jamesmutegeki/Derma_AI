#!/usr/bin/env python3
"""Evaluation of the CBM checkpoint on the PASSION for Dermatology dataset.

This script evaluates the model's predicted triage lanes on the PASSION dataset
as an external fairness cohort. It does NOT map PASSION conditions to "benign"
because PASSION contains inflammatory/infectious conditions (Eczema, Fungal,
Scabies, Others), not benign neoplasms.

Instead, it computes:
- Predicted triage lane distribution per Fitzpatrick type
- Predicted triage lane distribution per condition
- Urgent lane escalation rate per stratum (for fairness monitoring)
"""

import os
import sys
import argparse

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
import albumentations as A
from albumentations.pytorch import ToTensorV2
import pandas as pd

# Project imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dermatology-ai'))
from datasetEquity import DermDataset
from model import DermatologyCBM
from samplesEquity import MelaninNormalization


# PASSION condition to index mapping (for reporting)
PASSION_CONDITIONS = ['Eczema', 'Fungal', 'Scabies', 'Others']
# Triage lane names
TRIAGE_LANES = ['routine', 'follow_up', 'urgent']


def build_dataset(csv_path, img_dir):
    """Create a DermDataset with the PASSION transforms.
    Keeps original PASSION labels for stratified reporting.
    """
    import tempfile

    df = pd.read_csv(csv_path)
    # Keep original labels - do NOT map to 'benign'

    # Label map: PASSION conditions are all inflammatory/infectious
    # The model was trained on 3-class (benign, melanoma, kaposi_sarcoma)
    # We don't have a direct mapping, so we use a dummy mapping for the model
    # The actual labels are preserved in label_orig for reporting
    label_map = {cond: 0 for cond in PASSION_CONDITIONS}  # Map all to benign (0) for model input

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df.to_csv(f.name, index=False)
        temp_csv = f.name

    transform = A.Compose([
        MelaninNormalization(),
        A.Resize(224, 224),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    return DermDataset(csv_path=temp_csv, img_dir=img_dir, transform=transform, label_map=label_map), temp_csv


def evaluate_fairness(model, loader, device):
    """Evaluate predicted triage lanes per Fitzpatrick type and condition."""
    from collections import defaultdict

    # Per-Fitzpatrick predictions
    fitz_preds = defaultdict(list)
    fitz_conditions = defaultdict(list)

    # Per-condition predictions
    cond_preds = defaultdict(list)

    model.eval()
    with torch.no_grad():
        for imgs, labels, fitz, labels_orig in loader:
            imgs = imgs.to(device)
            logits, _ = model(imgs)
            probs = F.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)

            for p, f, l_orig in zip(preds.cpu().numpy(), fitz.cpu().numpy(), labels_orig):
                fitz_preds[int(f)].append(int(p))
                fitz_conditions[int(f)].append(l_orig)
                cond_preds[l_orig].append(int(p))

    return fitz_preds, fitz_conditions, cond_preds


def compute_urgent_rate(predictions):
    """Compute urgent lane rate from predictions."""
    if len(predictions) == 0:
        return 0.0
    urgent_count = sum(1 for p in predictions if p == 2)  # 2 = urgent
    return urgent_count / len(predictions)


def print_distribution(name, predictions, total):
    """Print lane distribution for a stratum."""
    counts = [predictions.count(i) for i in range(3)]
    rates = [c / total * 100 if total > 0 else 0 for c in counts]
    print(f"  {name}: n={total}")
    for i, (lane, count, rate) in enumerate(zip(TRIAGE_LANES, counts, rates)):
        print(f"    {lane:12s}: {count:4d} ({rate:.1f}%)")
    print(f"    Urgent rate: {rates[2]:.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate CBM predicted triage lanes on PASSION (fairness cohort)'
    )
    parser.add_argument(
        '--data-dir', default='dermatology-ai/datasets/passion', help='Root folder with val_meta.csv and images/'
    )
    parser.add_argument(
        '--ckpt', default='dermatology-ai/model_checkpoints/smoke_cbm.pt', help='Path to CBM checkpoint'
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
    state = torch.load(args.ckpt, map_location=device, weights_only=True)
    model.load_state_dict(state)

    # Build PASSION dataset (keep original labels)
    csv_path = os.path.join(args.data_dir, 'val_meta.csv')
    img_dir = os.path.join(args.data_dir, 'images')
    if not os.path.isfile(csv_path) or not os.path.isdir(img_dir):
        raise FileNotFoundError(
            f'Cannot find CSV at {csv_path} or image folder at {img_dir}.\n'
            'Please run the download script first: python scripts/download_passion.py'
        )

    full_ds, temp_csv = build_dataset(csv_path, img_dir)
    val_loader = DataLoader(full_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    # Evaluate fairness metrics
    fitz_preds, fitz_conditions, cond_preds = evaluate_fairness(model, val_loader, device)

    print('\n=== PASSION Fairness Evaluation (Predicted Triage Lanes) ===')
    print(f'Total validation samples: {len(full_ds)}')

    # Per-Fitzpatrick evaluation
    print("\n--- Per-Fitzpatrick Type ---")
    for fitz in range(1, 7):
        if fitz not in fitz_preds or len(fitz_preds[fitz]) == 0:
            continue
        preds = fitz_preds[fitz]
        print_distribution(f"Fitzpatrick {fitz}", preds, len(preds))

    # Per-condition evaluation
    print("\n--- Per-Condition ---")
    for cond in PASSION_CONDITIONS:
        if cond not in cond_preds or len(cond_preds[cond]) == 0:
            continue
        preds = cond_preds[cond]
        print_distribution(cond, preds, len(preds))

    # Cross-tabulation: Fitzpatrick x Condition
    print("\n--- Urgent Lane Rate by Fitzpatrick x Condition ---")
    for fitz in range(1, 7):
        if fitz not in fitz_preds or len(fitz_preds[fitz]) == 0:
            continue
        print(f"\n  Fitzpatrick {fitz}:")
        for cond in PASSION_CONDITIONS:
            # Get predictions for this fitz+condition combination
            combo_preds = [
                p for p, c in zip(fitz_preds[fitz], fitz_conditions[fitz])
                if c == cond
            ]
            if len(combo_preds) == 0:
                continue
            urgent_rate = compute_urgent_rate(combo_preds)
            print(f"    {cond:12s}: n={len(combo_preds):3d}, urgent_rate={urgent_rate:.3f}")

    # Overall summary
    all_preds = []
    for preds in fitz_preds.values():
        all_preds.extend(preds)

    print(f"\n=== Overall Summary ===")
    print(f"Total samples: {len(all_preds)}")
    print_distribution("Overall", all_preds, len(all_preds))

    # Cleanup
    os.unlink(temp_csv)


if __name__ == '__main__':
    main()