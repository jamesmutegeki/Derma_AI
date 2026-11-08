# Authoritative PASSION Dataset Reconciliation Table

Generated: 2026-11-09

| Source | Images | Subjects | Conditions | Fitzpatrick Range | Split | Notes |
|--------|--------|----------|------------|-------------------|-------|-------|
| metadata.csv | 4016 | 1363 | 4 (Eczema, Fungal, Scabies, Others) | 1-6 (no type 2) | TRAIN: 3220, TEST: 796 | Primary manifest |
| label.csv | N/A | 1653 | 4 | N/A | N/A | Subject-level metadata |
| PASSION_split.csv | N/A | 1655 | N/A | N/A | TRAIN: 1324, TEST: 331 | Subject-level splits |
| Image files on disk | 4016 | N/A | N/A | N/A | N/A | 0 metadata entries missing files |

## Key Findings

- **metadata.csv** is the authoritative image-level manifest: 4,016 images, 1,363 subjects
- **label.csv** has 1,653 subjects (some subjects may not have images in metadata.csv)
- **PASSION_split.csv** has 1,655 subjects with TRAIN/TEST splits
- **0 images** referenced in metadata.csv are missing from disk (previously reported missing was the corrupted AA00971771_4.jpg which has been removed from val_meta.csv)
- **Fitzpatrick type 2 is absent** from the dataset
- **All conditions are inflammatory/infectious (Eczema, Fungal, Scabies, Others), NOT benign neoplasms** — this is critical for fairness evaluation interpretation

## Split Reconciliation

| Level | Source | TRAIN | TEST/VAL | Total |
|-------|--------|-------|----------|-------|
| Subject | PASSION_split.csv | 1,324 | 331 | 1,655 |
| Image | metadata.csv | 3,220 | 796 | 4,016 |
| Our val_meta.csv (patient-level 80/20) | create_passion_splits.py | ~2,733 | ~1,283 | ~4,016 |

Note: Our patient-level 80/20 split (seed=42) differs from the original PASSION TRAIN/TEST split. We use patient-level stratification to prevent data leakage.

## Corrupted Image

- **AA00971771_4.jpg**: Truncated (5 bytes not processed)
- Removed from val_meta.csv to prevent evaluation errors
- This was 1 of 14 images for subject AA00971771 (Eczema, Fitzpatrick 5)
