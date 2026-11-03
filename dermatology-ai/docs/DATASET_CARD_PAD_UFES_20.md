# Dataset card -- PAD-UFES-20

| Field | Value |
| --- | --- |
| Full name | PAD-UFES-20: patient data and clinical images collected from smartphones |
| Source | Pacheco et al., *Data in Brief* 2020; Mendeley Data, DOI 10.17632/zr7vgbcyr2.1 |
| Access | **Immediate, no request.** Direct download (~3.35 GB) from the Mendeley cache bucket |
| Size | 2,298 images, 1,641 lesions, 1,373 patients |
| Labels | BCC, SCC (incl. Bowen's), MEL, ACK, SEK, NEV |
| Reference standard | All cancers (BCC/MEL/SCC) **biopsy-proven**; others by dermatologist consensus |
| Fitzpatrick metadata | **Yes** -- skin type recorded per patient |
| Licence | **CC BY 4.0** (attribution) |
| Known biases | Brazilian public-clinic population, mostly Fitzpatrick II-III; multiple lesions per patient; phone cameras of varying quality; only 52 melanomas |
| Used for | **Training lane A** (`benign` vs `melanoma`) with PAD-UFES-20 + HAM10000 |
| Caveat | No Kaposi sarcoma. BCC/SCC/ACK are excluded, never merged into `benign`. Split by patient, not by image |

## Why this dataset matters here

HAM10000 is dermatoscopic and Austrian; this project's deployment is a phone
photograph in a clinic. PAD-UFES-20 is the only immediately available corpus
whose *capture conditions* match the intended use, and it carries both a
biopsy-confirmed melanoma label and a Fitzpatrick label -- the two things the
fairness analysis needs.

## What must not be claimed from it

- Not an African cohort. Skin-type strata are skewed light; per-tone numbers must
  report the group sizes.
- 52 melanomas: any recall estimate carries a wide interval. Report it with the
  interval, or report the class as too small to evaluate.
- No Kaposi sarcoma, so it does not change the gate 1A pause.
