#!/usr/bin/env python3
"""Create image-level metadata CSV for PASSION dataset from GitHub label.csv and PASSION_split.csv.

The local dataset has 4016 images named AA########_#.jpg
The GitHub label.csv has 1653 subject-level rows with conditions_PASSION and fitzpatrick
The GitHub PASSION_split.csv has 1655 subject-level train/test splits

This script creates an image-level metadata.csv with columns:
- image_id: e.g., AA00970008_1
- label: Eczema, Fungal, Scabies, Others
- fitzpatrick_type: 1-6
- subject_id: AA00970008
- split: TRAIN/TEST (from PASSION_split.csv)
"""

import pandas as pd
from pathlib import Path

# Paths
LABEL_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/label.csv")
SPLIT_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/PASSION_split.csv")
IMAGES_DIR = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion_raw/PASSION_MICCAI_2024/images")
OUTPUT_CSV = Path("/mnt/d/Dermatology_AI/dermatology-ai/datasets/passion/metadata.csv")

# Load label data
labels_df = pd.read_csv(LABEL_CSV)
print(f"Labels shape: {labels_df.shape}")
print(f"Unique subjects in labels: {labels_df['subject_id'].nunique()}")
print(f"Conditions: {labels_df['conditions_PASSION'].unique()}")
print(f"Fitzpatrick range: {labels_df['fitzpatrick'].min()} - {labels_df['fitzpatrick'].max()}")

# Load split data
split_df = pd.read_csv(SPLIT_CSV)
print(f"\nSplit shape: {split_df.shape}")
print(f"Split distribution:\n{split_df['Split'].value_counts()}")

# Merge labels and splits
merged = labels_df.merge(split_df, on='subject_id', how='left')
print(f"\nMerged shape: {merged.shape}")
print(f"Missing splits: {merged['Split'].isna().sum()}")

# Get list of actual image files
image_files = list(IMAGES_DIR.glob("*.jpg"))
print(f"\nTotal image files: {len(image_files)}")

# Extract subject_id and image_index from filenames
image_records = []
for img_path in image_files:
    stem = img_path.stem  # e.g., AA00970008_1
    parts = stem.rsplit('_', 1)
    if len(parts) == 2:
        subject_id, image_idx = parts
        image_records.append({
            'image_id': stem,
            'subject_id': subject_id,
            'image_index': int(image_idx)
        })

images_df = pd.DataFrame(image_records)
print(f"Unique subjects in images: {images_df['subject_id'].nunique()}")

# Merge images with labels/splits
final_df = images_df.merge(
    merged[['subject_id', 'conditions_PASSION', 'fitzpatrick', 'Split']],
    on='subject_id',
    how='inner'
)

print(f"\nFinal merged shape: {final_df.shape}")
print(f"Label distribution:\n{final_df['conditions_PASSION'].value_counts()}")
print(f"Fitzpatrick distribution:\n{final_df['fitzpatrick'].value_counts().sort_index()}")
print(f"Split distribution:\n{final_df['Split'].value_counts()}")

# Rename columns to standard format
final_df = final_df.rename(columns={
    'conditions_PASSION': 'label',
    'fitzpatrick': 'fitzpatrick_type',
    'Split': 'split'
})

# Select and order columns
final_df = final_df[['image_id', 'label', 'fitzpatrick_type', 'subject_id', 'split', 'image_index']]

# Save
final_df.to_csv(OUTPUT_CSV, index=False)
print(f"\n✅ Saved metadata to {OUTPUT_CSV}")
print(f"Shape: {final_df.shape}")

# Verify
print("\nVerification:")
df = pd.read_csv(OUTPUT_CSV)
print(f"Columns: {df.columns.tolist()}")
print(f"Shape: {df.shape}")
print(f"Label counts:\n{df['label'].value_counts()}")
print(f"Fitzpatrick counts:\n{df['fitzpatrick_type'].value_counts().sort_index()}")
print(f"Split counts:\n{df['split'].value_counts()}")
print(f"Unique subjects: {df['subject_id'].nunique()}")
