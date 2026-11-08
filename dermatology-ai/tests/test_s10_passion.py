#!/usr/bin/env python3
"""Tests for PASSION dataset integration (Option B: external fairness cohort).

This module tests:
1. Patient-level split correctness (no subject_id overlap between train/val)
2. Tone-stratified evaluation (Fitzpatrick IV-VI each have ≥ 20 samples)
3. Fairness gate (urgent lane escalation rate on benign PASSION ≤ 0.35 per stratum)
4. Concepts pass-through (CBM returns 7 concept scores per image)
"""

import pytest
import pandas as pd
import torch
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datasetEquity import DermDataset
from model import DermatologyCBM, CONCEPT_NAMES


# --- Fixtures ---

@pytest.fixture(scope="module")
def passion_metadata():
    """Load PASSION metadata CSV."""
    path = Path(__file__).parent.parent / "datasets" / "passion" / "metadata.csv"
    assert path.exists(), f"Metadata not found at {path}. Run create_passion_metadata.py first."
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def passion_train_meta():
    """Load PASSION train split."""
    path = Path(__file__).parent.parent / "datasets" / "passion" / "train_meta.csv"
    assert path.exists(), f"Train split not found at {path}. Run create_passion_splits.py first."
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def passion_val_meta():
    """Load PASSION validation split."""
    path = Path(__file__).parent.parent / "datasets" / "passion" / "val_meta.csv"
    assert path.exists(), f"Val split not found at {path}. Run create_passion_splits.py first."
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def passion_val_dataset(passion_val_meta):
    """Create DermDataset for PASSION validation set."""
    import tempfile
    
    df = passion_val_meta.copy()
    df['label'] = 'benign'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df.to_csv(f.name, index=False)
        csv_path = f.name
    
    img_dir = Path(__file__).parent.parent / "datasets" / "passion_raw" / "PASSION_MICCAI_2024" / "images"
    
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    transform = A.Compose([
        A.Resize(224, 224),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    
    dataset = DermDataset(csv_path=csv_path, img_dir=str(img_dir), transform=transform)
    
    yield dataset
    
    Path(csv_path).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def cbm_model():
    """Load CBM checkpoint for testing."""
    ckpt_path = Path(__file__).parent.parent / "model_checkpoints" / "cbm_3class.pt"
    if not ckpt_path.exists():
        pytest.skip(f"Checkpoint not found at {ckpt_path}")
    
    model = DermatologyCBM(
        num_classes=3,
        num_concepts=7,
        hrnet_name='hrnet_w18',
        pretrained_backbone=True,
        freeze_backbone=False,
    )
    state = torch.load(ckpt_path, map_location='cpu', weights_only=True)
    model.load_state_dict(state)
    model.eval()
    return model


# --- Test 1: Patient-level split correctness ---

def test_patient_level_split_no_overlap(passion_train_meta, passion_val_meta):
    """Test that no subject_id appears in both train and val splits."""
    train_subjects = set(passion_train_meta['subject_id'].unique())
    val_subjects = set(passion_val_meta['subject_id'].unique())
    
    overlap = train_subjects & val_subjects
    assert len(overlap) == 0, f"Subject overlap between train and val: {overlap}"


def test_patient_level_split_coverage(passion_train_meta, passion_val_meta, passion_metadata):
    """Test that train + val covers all subjects in metadata."""
    train_subjects = set(passion_train_meta['subject_id'].unique())
    val_subjects = set(passion_val_meta['subject_id'].unique())
    all_subjects = set(passion_metadata['subject_id'].unique())
    
    combined = train_subjects | val_subjects
    assert combined == all_subjects, f"Missing subjects: {all_subjects - combined}"


# --- Test 2: Tone-stratified evaluation ---

def test_fitzpatrick_iv_vi_min_samples(passion_val_meta):
    """Test that Fitzpatrick IV, V, VI each have ≥ 20 samples in validation set."""
    fitz_counts = passion_val_meta['fitzpatrick_type'].value_counts()
    
    for fitz in [4, 5, 6]:
        count = fitz_counts.get(fitz, 0)
        assert count >= 20, f"Fitzpatrick type {fitz} has only {count} samples (< 20 minimum)"


def test_fitzpatrick_distribution_reported(passion_val_meta):
    """Test that Fitzpatrick distribution is reported for validation set."""
    fitz_counts = passion_val_meta['fitzpatrick_type'].value_counts().sort_index()
    
    assert len(fitz_counts) >= 3, "Should have at least 3 Fitzpatrick types in val set"
    print(f"\nValidation set Fitzpatrick distribution:\n{fitz_counts}")


# --- Test 3: Fairness gate ---

def test_urgent_lane_escalation_rate_gate(passion_val_dataset, cbm_model):
    """Test that urgent lane escalation rate on benign PASSION images ≤ 0.35 per stratum."""
    from torch.utils.data import DataLoader
    import torch.nn.functional as F
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    cbm_model = cbm_model.to(device)
    
    loader = DataLoader(passion_val_dataset, batch_size=32, shuffle=False, num_workers=0)
    
    from collections import defaultdict
    fitz_predictions = defaultdict(list)
    
    with torch.no_grad():
        for imgs, labels, fitz in loader:
            imgs = imgs.to(device)
            logits, _ = cbm_model(imgs)
            probs = F.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            
            for p, f in zip(preds.cpu().numpy(), fitz.cpu().numpy()):
                fitz_predictions[int(f)].append(int(p))
    
    for fitz in [3, 4, 5, 6]:
        if fitz not in fitz_predictions or len(fitz_predictions[fitz]) == 0:
            continue
            
        preds = fitz_predictions[fitz]
        total = len(preds)
        urgent_count = sum(1 for p in preds if p in [1, 2])
        urgent_rate = urgent_count / total
        
        print(f"Fitzpatrick {fitz}: {total} samples, urgent_rate={urgent_rate:.3f}")
        
        assert urgent_rate <= 0.35, (
            f"Fitzpatrick {fitz} urgent lane escalation rate {urgent_rate:.3f} "
            f"exceeds threshold 0.35 (urgent={urgent_count}/{total})"
        )


def test_overall_urgent_lane_rate(passion_val_dataset, cbm_model):
    """Test overall urgent lane escalation rate on PASSION benign cohort."""
    from torch.utils.data import DataLoader
    import torch.nn.functional as F
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    cbm_model = cbm_model.to(device)
    
    loader = DataLoader(passion_val_dataset, batch_size=32, shuffle=False, num_workers=0)
    
    all_preds = []
    with torch.no_grad():
        for imgs, labels, fitz in loader:
            imgs = imgs.to(device)
            logits, _ = cbm_model(imgs)
            probs = F.softmax(logits, dim=1)
            preds = torch.argmax(probs, dim=1)
            all_preds.extend(preds.cpu().numpy())
    
    total = len(all_preds)
    urgent_count = sum(1 for p in all_preds if p in [1, 2])
    urgent_rate = urgent_count / total
    
    print(f"\nOverall: {total} samples, urgent_rate={urgent_rate:.3f}")
    
    assert urgent_rate <= 0.40, (
        f"Overall urgent lane escalation rate {urgent_rate:.3f} exceeds 0.40 "
        f"(urgent={urgent_count}/{total})"
    )


# --- Test 4: Concepts pass-through ---

def test_cbm_returns_7_concepts(passion_val_dataset, cbm_model):
    """Test that CBM returns 7 concept scores per image."""
    from torch.utils.data import DataLoader
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    cbm_model = cbm_model.to(device)
    
    loader = DataLoader(passion_val_dataset, batch_size=4, shuffle=False, num_workers=0)
    
    with torch.no_grad():
        for imgs, labels, fitz in loader:
            imgs = imgs.to(device)
            logits, concepts = cbm_model(imgs)
            
            assert concepts.shape[1] == 7, f"Expected 7 concepts, got {concepts.shape[1]}"
            assert (concepts >= 0).all() and (concepts <= 1).all(), "Concept scores should be in [0, 1]"
            assert logits.shape[1] == 3, f"Expected 3-class logits, got {logits.shape[1]}"
            break


def test_concept_names_match_constant():
    """Test that CONCEPT_NAMES constant has 7 entries matching the model."""
    assert len(CONCEPT_NAMES) == 7, f"CONCEPT_NAMES should have 7 entries, has {len(CONCEPT_NAMES)}"
    expected = [
        "asymmetry",
        "border_irregularity", 
        "color_variegation",
        "diameter_large",
        "melanin_density",
        "inflammation",
        "ulceration"
    ]
    assert CONCEPT_NAMES == expected, f"CONCEPT_NAMES mismatch: {CONCEPT_NAMES}"


# --- Test 5: Dataset integrity ---

def test_passion_metadata_has_required_columns(passion_metadata):
    """Test that PASSION metadata has all required columns."""
    required = ['image_id', 'label', 'fitzpatrick_type', 'subject_id', 'split']
    for col in required:
        assert col in passion_metadata.columns, f"Missing column: {col}"


def test_passion_labels_are_inflammatory_conditions(passion_metadata):
    """Test that PASSION labels are the 4 inflammatory conditions."""
    expected_conditions = {'Eczema', 'Fungal', 'Scabies', 'Others'}
    actual = set(passion_metadata['label'].unique())
    assert actual == expected_conditions, f"Unexpected conditions: {actual - expected_conditions}"


def test_passion_fitzpatrick_range(passion_metadata):
    """Test that Fitzpatrick types are in valid range 1-6."""
    fitz = passion_metadata['fitzpatrick_type']
    assert fitz.min() >= 1, f"Fitzpatrick min {fitz.min()} < 1"
    assert fitz.max() <= 6, f"Fitzpatrick max {fitz.max()} > 6"


def test_passion_images_exist(passion_metadata):
    """Test that all image files in metadata exist on disk."""
    img_dir = Path(__file__).parent.parent / "datasets" / "passion_raw" / "PASSION_MICCAI_2024" / "images"
    
    missing = []
    for img_id in passion_metadata['image_id'].head(100):
        img_path = img_dir / f"{img_id}.jpg"
        if not img_path.exists():
            missing.append(img_id)
    
    assert len(missing) == 0, f"Missing images (sample): {missing[:10]}"


# --- Test 6: Patient-level aggregation (from passion_metrics) ---

def test_patient_level_aggregation_logic():
    """Test the patient-level aggregation logic from passion_metrics."""
    from scripts.passion_metrics import (
        PredictionRecord,
        compute_patient_level_aggregation,
        compute_urgent_lane_rate
    )
    
    records = [
        PredictionRecord("subj_A", "Eczema", 4, 2),
        PredictionRecord("subj_A", "Eczema", 4, 2),
        PredictionRecord("subj_A", "Eczema", 4, 0),
        PredictionRecord("subj_B", "Fungal", 5, 1),
        PredictionRecord("subj_B", "Fungal", 5, 1),
        PredictionRecord("subj_B", "Fungal", 5, 0),
    ]
    
    patient_records = compute_patient_level_aggregation(records)
    
    assert len(patient_records) == 2, "Should have 2 patient records"
    
    subj_a = next(r for r in patient_records if r.subject_id == "subj_A")
    assert subj_a.triage_lane == 2, f"Subject A should be urgent, got {subj_a.triage_lane}"
    
    subj_b = next(r for r in patient_records if r.subject_id == "subj_B")
    assert subj_b.triage_lane == 1, f"Subject B should be follow_up, got {subj_b.triage_lane}"


def test_urgent_lane_rate_computation():
    """Test urgent lane rate computation with known fixture."""
    from scripts.passion_metrics import (
        PredictionRecord,
        compute_urgent_lane_rate,
        build_test_fixture_basic
    )
    
    records = build_test_fixture_basic()
    result = compute_urgent_lane_rate(records)
    
    assert result['overall'] == 0.25, f"Expected 0.25, got {result['overall']}"
    assert result['by_fitzpatrick'][4] == 0.5, "Fitzpatrick 4: 1 urgent out of 2"
    assert result['by_fitzpatrick'][5] == 0.0, "Fitzpatrick 5: 0 urgent out of 2"
    assert result['by_condition']['Eczema'] == 0.5, "Eczema: 1 urgent out of 2"
    assert result['by_condition']['Fungal'] == 0.0, "Fungal: 0 urgent out of 2"


def test_empty_stratum_not_in_results():
    """Test that empty stratum is not present in results (not 0.0)."""
    from scripts.passion_metrics import (
        PredictionRecord,
        compute_urgent_lane_rate,
        build_test_fixture_empty_stratum
    )

    records = build_test_fixture_empty_stratum()
    # Only Fitzpatrick 4 and 5, no 3 or 6
    result = compute_urgent_lane_rate(records)

    # Empty strata should not appear in results (not 0.0)
    assert 3 not in result['by_fitzpatrick'], "Empty stratum 3 should not be in results"
    assert 6 not in result['by_fitzpatrick'], "Empty stratum 6 should not be in results"

    # But present strata should have correct values
    assert result['by_fitzpatrick'][4] == 0.0, "Fitzpatrick 4 should have rate 0.0 (0/1 urgent)"
    assert result['by_fitzpatrick'][5] == 1.0, "Fitzpatrick 5 should have rate 1.0 (1/1 urgent)"
    assert result['by_condition']['Eczema'] == 0.0, "Eczema should have rate 0.0"
    assert result['by_condition']['Fungal'] == 1.0, "Fungal should have rate 1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
