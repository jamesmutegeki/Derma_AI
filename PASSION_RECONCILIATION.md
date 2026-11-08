# Authoritative PASSION Dataset Reconciliation — LOCAL SUBSET

Generated: 2026-11-09

**IMPORTANT**: This working copy contains a **4,016-image local subset** of the published PASSION dataset (4,901 images on GitHub). All results below are reported "on the 4,016-image local subset" — never as PASSION as a whole.

| Source | Images | Subjects | Conditions | Fitzpatrick Range | Split | Notes |
|--------|--------|----------|------------|-------------------|-------|-------|
| metadata.csv | 4016 | 1363 | 4 (Eczema, Fungal, Scabies, Others) | 1-6 (no type 2) | TRAIN: 3220, TEST: 796 | Primary manifest (local subset) |
| label.csv | N/A | 1653 | 4 | N/A | N/A | Subject-level metadata (GitHub) |
| PASSION_split.csv | N/A | 1655 | N/A | N/A | TRAIN: 1324, TEST: 331 | Subject-level splits (GitHub) |
| Image files on disk | 4016 | N/A | N/A | N/A | N/A | 0 missing from metadata.csv |

## Corrupted Images (on local subset)

| Image ID | Subject | Condition | Fitzpatrick | Status |
|----------|---------|-----------|-------------|--------|
| AA00971771_4.jpg | AA00971771 | Eczema | 5 | **Truncated (5 bytes not processed)** — REMOVED from val_meta.csv |

**Total corrupted in local subset: 1** (AA00971771_4.jpg). This was 1 of 14 images for subject AA00971771. Removed from val_meta.csv to prevent evaluation errors. The remaining 13 images for this subject are valid.

## Key Findings (on 4,016-image local subset)

- **metadata.csv** is the authoritative image-level manifest: 4,016 images, 1,363 subjects
- **label.csv** has 1,653 subjects (some subjects may not have images in local metadata.csv)
- **PASSION_split.csv** has 1,655 subjects with TRAIN/TEST splits (from GitHub)
- **0 images** referenced in metadata.csv are missing from disk
- **Fitzpatrick type 2 is absent** from the dataset
- **All conditions are inflammatory/infectious (Eczema, Fungal, Scabies, Others), NOT benign neoplasms** — critical for fairness evaluation interpretation
- **Published PASSION release: 4,901 images** (per GitHub). This local subset has 4,016 (885 images / ~292 subjects not downloaded). Results are NOT generalizable to the full PASSION cohort.

## Split Reconciliation (local subset)

| Level | Source | TRAIN | TEST/VAL | Total |
|-------|--------|-------|----------|-------|
| Subject | PASSION_split.csv (GitHub) | 1,324 | 331 | 1,655 |
| Image | metadata.csv (local) | 3,220 | 796 | 4,016 |
| Our val_meta.csv (patient-level 80/20) | create_passion_splits.py | ~2,733 | ~1,283 | ~4,016 |

Note: Our patient-level 80/20 split (seed=42) differs from the original PASSION TRAIN/TEST split. We use patient-level stratification to prevent data leakage.

## Corrupted Image Detail

- **AA00971771_4.jpg**: Truncated (5 bytes not processed)
- Removed from val_meta.csv to prevent evaluation errors
- This was 1 of 14 images for subject AA00971771 (Eczema, Fitzpatrick 5)
- Subject AA00971771 retains 13 valid images in the local subset