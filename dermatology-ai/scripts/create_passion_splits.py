#!/usr/bin/env python3
"""Create train/val splits for PASSION dataset at patient level."""

from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

METADATA_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/metadata.csv")
TRAIN_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/train_meta.csv")
VAL_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/val_meta.csv")

# Load metadata
df = pd.read_csv(METADATA_CSV)
print(f"Total images: {len(df)}")
print(f"Unique subjects: {df['subject_id'].nunique()}")

# Create patient-level split
subjects = df[['subject_id', 'label', 'fitzpatrick_type']].drop_duplicates()
print(f"\nPatient-level label distribution:\n{subjects['label'].value_counts()}")
print(f"Patient-level Fitzpatrick distribution:\n{subjects['fitzpatrick_type'].value_counts().sort_index()}")

# Create stratification column combining label and fitzpatrick (excluding rare fitzpatrick 1)
subjects_strat = subjects.copy()
subjects_strat['strat'] = subjects_strat['label'] + '_' + subjects_strat['fitzpatrick_type'].astype(str)

# Check stratification counts
strat_counts = subjects_strat['strat'].value_counts()
print(f"\nStratification counts (min: {strat_counts.min()}):")
# Remove classes with only 1 member
valid_strat = strat_counts[strat_counts >= 2].index
subjects_valid = subjects_strat[subjects_strat['strat'].isin(valid_strat)]
subjects_invalid = subjects_strat[~subjects_strat['strat'].isin(valid_strat)]

print(f"Valid for stratification: {len(subjects_valid)} subjects")
print(f"Invalid (singletons): {len(subjects_invalid)} subjects")
print(f"Singleton strata: {subjects_invalid['strat'].tolist()}")

# Stratified split on valid subjects
train_subjects_valid, val_subjects_valid = train_test_split(
    subjects_valid,
    test_size=0.2,
    random_state=42,
    stratify=subjects_valid['strat']
)

# Randomly assign invalid subjects
import numpy as np

np.random.seed(42)
invalid_split = np.random.rand(len(subjects_invalid)) < 0.8
train_subjects_invalid = subjects_invalid[invalid_split]
val_subjects_invalid = subjects_invalid[~invalid_split]

# Combine
train_subjects = pd.concat([train_subjects_valid, train_subjects_invalid])
val_subjects = pd.concat([val_subjects_valid, val_subjects_invalid])

print(f"\nTrain subjects: {len(train_subjects)}")
print(f"Val subjects: {len(val_subjects)}")

# Get image-level splits
train_df = df[df['subject_id'].isin(train_subjects['subject_id'])]
val_df = df[df['subject_id'].isin(val_subjects['subject_id'])]

print(f"\nTrain images: {len(train_df)}")
print(f"Val images: {len(val_df)}")

# Verify no subject overlap
train_subj = set(train_df['subject_id'].unique())
val_subj = set(val_df['subject_id'].unique())
print(f"Subject overlap: {len(train_subj & val_subj)}")

# Save
train_df.to_csv(TRAIN_CSV, index=False)
val_df.to_csv(VAL_CSV, index=False)

print(f"\n✅ Saved train split to {TRAIN_CSV}")
print(f"✅ Saved val split to {VAL_CSV}")

# Verify
print("\n=== Train split ===")
print(f"Label distribution:\n{train_df['label'].value_counts()}")
print(f"Fitzpatrick distribution:\n{train_df['fitzpatrick_type'].value_counts().sort_index()}")
print(f"Unique subjects: {train_df['subject_id'].nunique()}")

print("\n=== Val split ===")
print(f"Label distribution:\n{val_df['label'].value_counts()}")
print(f"Fitzpatrick distribution:\n{val_df['fitzpatrick_type'].value_counts().sort_index()}")
print(f"Unique subjects: {val_df['subject_id'].nunique()}")
