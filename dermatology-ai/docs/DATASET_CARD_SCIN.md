# Dataset card -- SCIN (Skin Condition Image Network)

> **Recommended replacement for PASSION for the evaluation role.** Chosen
> because, unlike PASSION, DDI, Fitzpatrick17k and eSkinHealth, it is
> **downloadable without a request form**, and it ships dermatologist-assessed
> skin-tone labels in two schemes. See
> [`DATASET_ALTERNATIVES.md`](./DATASET_ALTERNATIVES.md).

| Field | Value |
| --- | --- |
| Full name | SCIN -- Skin Condition Image Network |
| Source | Google Research; Ward et al., "Creating an Empirical Dermatology Dataset Through Crowdsourcing With Web Search Advertisements" (JAMA Network Open, 2024); DOI 10.5281/zenodo.10819503 |
| Code/data docs | https://github.com/google-research-datasets/scin |
| Access | **Public.** Google Cloud Storage bucket `dx-scin-public-data`, no request form, no account beyond GCS |
| Size | 10,000+ images from 5,000+ contributions (the paper's release); the accompanying paper table lists 10,408 images |
| Labels | Free-text dermatologist differential-diagnosis labels per image (typically several per case) |
| Skin-tone metadata | **Two independent schemes**: participant self-reported Fitzpatrick (sFST) and dermatologist-estimated Fitzpatrick (eFST) + Monk Skin Tone (eMST) |
| Licence | SCIN Data Use License (non-commercial, no re-identification, attribution); images contributed with informed consent for research use |
| Known issues | 15 duplicate images (42 occurrences), 48 gradable cases with no label, 1 missing file -- all documented by the maintainers |
| Used for | **Planned**: external fairness/triage evaluation only (`run_evaluation_scin.py`, not yet written) |
| Caveat | US crowdsourced population, not African. Conditions are dominated by inflammatory and infectious dermatoses. **No melanoma or Kaposi sarcoma cohort of usable size**, so SCIN can evaluate calibration and tone-stratified behaviour of the triage head, **not** the three-class malignancy head |

## What SCIN does and does not buy this project

**Does:** the project currently cannot make any tone-stratified claim, because
HAM10000 has no Fitzpatrick metadata and DDI (656 images) is too small to
stratify. SCIN supplies both self-reported and expert-estimated tone at a size
where per-stratum numbers have a chance of meaning something -- and it does so
without an access negotiation.

**Does not:** it cannot train or validate `melanoma` / `kaposi_sarcoma`
detection. Any table that reports three-class accuracy on SCIN would be
reporting on mapped, partially artificial classes. Per the project's honesty
rule, such numbers must be reported as "mapped-label evaluation, not clinical
accuracy", or not reported at all.

## Ingestion plan

1. Download `dataset/scin_cases.csv`, `dataset/scin_labels.csv` and the images
   from `gs://dx-scin-public-data`.
2. Join on `case_id`; take `dermatologist_label_1` as the primary label and
   `eFST` as the tone label (keep `sFST`/`eMST` in the report for sensitivity).
3. Convert with the shipped adapter:

   ```bash
   python scripts/prepare_dataset.py --source scin \
       --input <scin>/joined.csv \
       --images-root <scin>/images \
       --image-column image_path --label-column dermatologist_label_1 \
       --fitz-column eFST \
       --label-map scripts/label_maps/scin.json \
       --output datasets/scin
   ```

4. Read `conversion_report.json` before training. It lists every unmapped label
   and every missing image. Extend `scripts/label_maps/scin.json` deliberately;
   never widen the map just to raise the row count.

The label map currently routes most SCIN conditions to `skip`, because forcing
them into `benign` would silently redefine the class. Expect a low conversion
rate -- that is the correct outcome, and it is why SCIN cannot stand in for a
malignancy benchmark.
