# Dataset card -- PASSION for Dermatology

> **Status 2026-10-30: access request unanswered.** The maintainers have not
> replied to repeated access requests, so this dataset is currently
> **unavailable** to the project. It is documented here for completeness and is
> **not** part of any implemented pipeline. See
> [`DATASET_ALTERNATIVES.md`](./DATASET_ALTERNATIVES.md) for the replacement
> plan.

| Field | Value |
| --- | --- |
| Full name | PASSION for Dermatology (paediatric dermatology, Sub-Saharan Africa) |
| Source | PASSION project, https://passionderm.github.io/ ; described in the MICCAI 2024 paper (arXiv:2411.04584) |
| Access | Access-controlled release (child medical images). Request form; no reply as of 2026-10-30. Not redistributable |
| Size | **4,901 images from 1,653 patients** (paper, MICCAI 2024) |
| Labels | **Four paediatric conditions**: atopic dermatitis, dermatophytosis, scabies, impetigo |
| Fitzpatrick | Skin types IV-VI |
| Sites | Cote d'Ivoire, Malawi, Tanzania, Madagascar |
| Licence | Research use under the PASSION access agreement; ethics approval per project |
| Known biases | Phone-camera clinical images (not dermoscopy); paediatric population only; four conditions only |
| Used for | **Nothing at present.** No loader or evaluation script runs against it |
| Caveat | The four PASSION conditions do **not** map onto `benign` / `melanoma` / `kaposi_sarcoma`. PASSION could only ever have served as an external triage/fairness cohort -- it cannot train the three-class head |

## Correction log

The first version of this card said "~19k clinical images" and "12 disease
categories". Both figures were wrong: they were not taken from the PASSION
publication and are not supported by it. The MICCAI 2024 paper reports 4,901
images, 1,653 patients and four conditions. Corrected 2026-10-30; the earlier
figures had not been used in any result, because no PASSION data was ever
obtained.

## Why it was wanted

PASSION was attractive for three reasons, all of which remain true of the
replacement candidates:

1. African, primarily dark skin (Fitzpatrick IV-VI) -- the population this
   project is aimed at.
2. Clinical (phone-camera) images, matching how the intended deployment would
   capture images.
3. A published, peer-reviewed benchmark with a defined split.

None of these require the PASSION brand specifically; the replacement analysis
in `DATASET_ALTERNATIVES.md` is built around the same three constraints.
