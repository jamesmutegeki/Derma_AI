# Remediation Status

## Current Status (2026-11-09)

**PASSION harness implemented and committed; dataset present as a local N-image subset; real-data evaluation not yet run; no metrics produced.**

## Completed Work

### PASSION Dataset Integration (Option B: External Fairness Cohort)

- [x] Metadata creation from GitHub sources (`create_passion_metadata.py`)
- [x] Patient-level stratified 80/20 splits (`create_passion_splits.py`, seed=42)
- [x] Corrupted image detection and removal (AA00971771_4.jpg removed from val_meta.csv)
- [x] DatasetEquity.py: Fixed PIL→numpy conversion for Albumentations compatibility
- [x] DatasetEquity.py: Added corrupted image scanning at init time (raises RuntimeError)
- [x] Test suite: 15 hermetic tests using tmp_path fixtures (`test_s10_passion.py`)
- [x] Fairness metrics: Pure functions in `passion_metrics.py` (urgent lane escalation rates by Fitzpatrick/condition)
- [x] Evaluation script: `run_evaluation_passion.py` scores predicted triage lanes only
- [x] Authoritative reconciliation table: `PASSION_RECONCILIATION.md` (4,016 images, 1,363 subjects)

### Test Results

- All 15 S10 tests pass
- No invented thresholds in tests (removed 0.35/0.40 gates per user feedback)
- All tests hermetic (tmp_path fixtures per user feedback)

## Pending Work

### Real-Data Evaluation

- [ ] Run `run_evaluation_passion.py` on trained model checkpoint
- [ ] Produce per-Fitzpatrick and per-condition urgent lane escalation rates
- [ ] Generate fairness report comparing dark skin (Fitzpatrick IV-VI) vs light skin

### Model Training

- [ ] Training currently paused (no Kaposi sarcoma real cohort)
- [ ] Placeholder status maintained in `model_manifest.json`

## Known Issues

1. **Kaposi Sarcoma**: No real training data — predictions unvalidated (confidence caveat included in API response)
2. **PASSION Subset**: Local subset has 4,016/4,901 images (885 images / ~292 subjects not downloaded)
3. **Fitzpatrick Type 2**: Absent from PASSION dataset
4. **Condition Mapping**: PASSION conditions are inflammatory/infectious (NOT benign neoplasms) — affects fairness interpretation

## Gate Status

| Gate | Status | Notes |
|------|--------|-------|
| S1-1 Frozen Weights | PAUSED | Pending Kaposi sarcoma cohort |
| S2-4 Training Freeze | CLOSED | Signed 2026-10-30 |
| Retention Policy | IN FORCE | Since 2026-10-30 |
| IRB Exemption | TRACKED | See `docs/IRB_EXEMPTION_REQUEST.md` |
| Gate Options | TRACKED | See `docs/GATE_OPTIONS.md` |

## Next Steps

1. Obtain/generate Kaposi sarcoma cohort for real training data
2. Run full PASSION evaluation on trained model
3. Submit IRB exemption request
4. Update MODEL_CARD.md with actual evaluation metrics