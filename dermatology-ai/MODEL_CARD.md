# Model card -- DermatologyCBM (research prototype)

**This model is not a medical device. It has no clinical validation and must not
be used to make, confirm or delay a diagnosis or treatment decision.**

| Field | Value |
| --- | --- |
| Model name | `DermatologyCBM` (concept-bottleneck, HRNet-W18 backbone) |
| Version | *unset -- no checkpoint is frozen in this repository* |
| Manifest | `model_manifest.json` (`status: placeholder`) |
| Owner | Derma-AI research project (Makerere / UCI collaboration) |
| Intended use | Research and education: exploring concept-level explanations and triage assistance |
| Out of scope | Clinical diagnosis, screening programmes, autonomous triage, any use with real patient data before gate clearance |
| Licence | See `LICENSE` for code; weights are not distributed |

## Architecture

* Backbone: HRNet-W18 (`timm`), ImageNet-initialised, fine-tuned.
* Concept head: 7 concepts -- asymmetry, border, colour, diameter, melanin,
  inflammation, ulceration.
* Classifier: 3 classes -- `benign`, `melanoma`, `kaposi_sarcoma`.
* Explanation: Grad-CAM on the last convolutional block; Integrated Gradients is
  reported as an **approximation** because `MelaninNormalization` is
  non-differentiable (see `model.py`).

The `atypical_lesion` category in `constants.TRUE_LABEL_NAMES` is a *triage*
catalogue entry (it maps to `follow_up`); it is not a fourth vision class.

## Training data

Not established in this repository. The manifest's `training` block is `null`
until a checkpoint is frozen with `scripts/freeze_model.py`, which requires the
dataset, split, seed, epoch count and git commit. Without those fields the
manifest stays `placeholder` and **no number may be quoted from this model**.

Known dataset facts:

* **HAM10000** -- 10,015 dermoscopic images, 7 diagnostic categories. The
  three-class mapping used here collapses them to benign / melanoma / Kaposi
  sarcoma.
* **DDI (Diverse Dermatology Images)** -- **656 images from 570 patients**
  (Fitzpatrick I-II: 208, III-IV: 241, V-VI: 207), pathologically confirmed,
  DOI `10.71718/kqee-3z39`. Earlier documents in this repository described DDI as
  "12k images, 30+ classes"; that was wrong and has been corrected.
* **PASSION** -- Ugandan cohort, accessed separately under its own data-use
  agreement.

## Evaluation

There is no validated evaluation. Any accuracy, AUROC, fairness gap or override
rate must come from a report produced by `run_evaluation_ham.py --json` /
`run_evaluation_passion.py --json`, referenced from the manifest's
`evaluation.report` field. Figures that are not traceable to such a report must
not appear in a poster, slide, README or paper.

Metrics that the code *computes* (once cases exist):

* `clinical_accuracy` -- over clinician-confirmed ground truth only;
* `model_vs_clinician_agreement` -- reported separately, **not** accuracy;
* `override_rate`, per-Fitzpatrick accuracy and critical-miss rate;
* `accuracy_gap` -- computed only across groups that actually contain confirmed
  cases (empty groups are `None`, never zero).

## Ethical considerations and limitations

1. **Skin-tone coverage is unproven.** HAM10000 is overwhelmingly light-skinned;
   performance on Fitzpatrick IV-VI is unknown until measured on DDI/PASSION.
2. **No demographic or clinical metadata** is used; the model sees an image only.
3. **Three classes are not a diagnosis.** Melanoma vs benign vs Kaposi sarcoma
   is a triage prompt for a clinician, not a pathology result.
4. **Distribution shift.** Dermoscopic training images differ from phone-camera
   clinical photos; the app does not detect out-of-distribution inputs.
5. **Melanin normalisation** is applied in both training and serving
   (`transforms.build_transform`); it is a histogram equalisation of the LAB
   L-channel, not a validated skin-tone correction.
6. **Explainability is illustrative.** Grad-CAM highlights regions the network
   used; it is not evidence of correctness.

## Gate before real patient data

`S1-1` (this manifest + model card), `S2-4`, an approved retention/backup policy
and IRB sign-off must all be complete. See `SECURITY.md` §8.
