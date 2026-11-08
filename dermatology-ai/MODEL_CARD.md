# Model Card: Derma_AI Concept Bottleneck Model

## Disclaimer

**This tool is for research and educational purposes only. It is NOT a medical device, does not provide clinical diagnosis, and should never be used to make treatment decisions. Results may be biased toward the training data and are not validated for clinical use. Always consult a qualified dermatologist or physician.**

## Model Overview

- **Model Name**: Derma_AI Concept Bottleneck Model (CBM)
- **Version**: 0.1.0 (placeholder)
- **Architecture**: HRNet-W18 backbone + Concept Bottleneck head
- **Task**: 3-class skin lesion triage (benign, melanoma, Kaposi sarcoma) with 7 interpretable concepts
- **Status**: Placeholder — no frozen checkpoint available

## Intended Use

- **Primary Use**: Research and educational triage support for dermatology
- **Target Users**: Researchers, educators, clinicians (with human-in-the-loop supervision)
- **Out of Scope**: Clinical diagnosis, treatment decisions, standalone medical decision-making

## Training Data

### HAM10000
- 10,015 dermoscopic images
- 7 diagnostic classes (mapped to 3 triage classes)
- Fitzpatrick skin types I-IV (limited dark skin representation)

### PASSION Dataset (Local Subset)
- 4,016 images from Sub-Saharan African patients
- 1,363 subjects
- 4 inflammatory conditions: Eczema, Fungal, Scabies, Others
- Fitzpatrick types 1-6 (no type 2)
- **Note**: This is a local subset of the published 4,901-image PASSION dataset. Results do not generalize to the full cohort.

### Synthetic Data
- Kaposi sarcoma class trained exclusively on synthetic images
- **Critical Limitation**: No real HAM10000 Kaposi sarcoma samples available

## Performance

### Overall Metrics
- No validated metrics available — model is in placeholder status
- PASSION evaluation not yet run

### Fairness (Fitzpatrick-Stratified)
- No metrics produced yet
- Planned evaluation: Urgent lane escalation rate by Fitzpatrick type (IV-VI)

## Limitations

1. **Kaposi Sarcoma**: No real training data — predictions unvalidated
2. **Dark Skin**: Limited representation in HAM10000; PASSION subset provides additional coverage but is inflammatory conditions only
3. **Generalizability**: Model trained on dermoscopic images; clinical photo performance unknown
4. **Class Imbalance**: 3-class mapping from diverse sources introduces label noise

## Ethical Considerations

- **Bias Risk**: Model may underperform on Fitzpatrick V-VI without PASSION evaluation
- **Clinical Safety**: Not a medical device; must not be used for diagnosis
- **Human-in-the-Loop**: Designed for clinician oversight (override mechanism available)

## Model Manifest

See `model_manifest.json` for structured metadata.

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 0.1.0 | 2026-11-09 | Placeholder | PASSION integration complete; evaluation pending |