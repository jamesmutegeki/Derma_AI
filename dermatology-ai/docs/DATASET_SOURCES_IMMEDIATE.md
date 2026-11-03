# Data you can have today (no request form, no waiting)

**Date:** 2026-11-03
**Question being answered:** *which dataset can I actually start with, now, without
waiting for a human to reply?*

PASSION has not answered. Fitzpatrick17k wants a Google Form. DDI wants an
agreement. eSkinHealth publishes no link at all. That whole category is dead
weight for a project with a deadline, so this page only lists sources where the
data (or the answer) arrives **immediately**.

---

## The short answer

| Rank | Source | Time to data | What it is | Use it for |
| --- | --- | --- | --- | --- |
| **1** | **PAD-UFES-20** | **~10 minutes** (direct download, 3.35 GB, no account) | 2,298 smartphone clinical images, 1,373 patients, 1,641 lesions, six diagnoses, **Fitzpatrick skin type per patient**, all cancers biopsy-proven | **Training** — the closest thing to how your app will actually see skin: a phone photo, not a dermatoscope |
| **2** | **DermaMNIST** (`pip install medmnist`) | **~60 seconds** (20 MB) | 7,007 HAM10000 images, 28×28 (224×224 via MedMNIST+) | **Today's smoke test** and CI — proves the pipeline end to end before any big download |
| **3** | **SCIN** | ~30 minutes (public GCS bucket) | 10,000+ crowdsourced images, dermatologist labels, **self-reported *and* dermatologist-estimated Fitzpatrick + Monk skin tone** | **Tone-stratified evaluation** — the only immediate source with two independent tone labels |
| **4** | **HAM10000** | you already have it (Dataverse) | 10,015 dermatoscopic images | Training/eval baseline, and the anchor for comparability with published work |
| **5** | **DDI** | request (usually days) | 656 images, 570 patients, FST I–VI balanced, pathologically confirmed | Small dark-skin check — worth filing, not worth blocking on |

**Start with 1 + 2 this week.** They are complements, not alternatives: DermaMNIST
tells you the code works in a minute, PAD-UFES-20 tells you whether the model
works on phone photographs of real lesions.

---

## 1. PAD-UFES-20 — the one to start with

| Field | Value |
| --- | --- |
| What | 2,298 clinical images from smartphones; 1,373 patients; 1,641 lesions |
| Labels | BCC 845, MEL 52, SCC (incl. Bowen's), ACK, NEK/SEK, NEV — six classes |
| Reference standard | **All cancers biopsy-proven** (BCC, SCC, MEL = 100%); others by dermatologist consensus |
| Skin tone | **Fitzpatrick skin type per patient** in the metadata |
| Metadata | up to 22 clinical features: age, lesion location, diameter, skin type |
| Licence | **CC BY 4.0** — attribution only, commercial use permitted (still: this project is non-commercial) |
| Access | **Direct download, no account, no form** |
| Download | `https://prod-dcd-datasets-cache-zipfiles.s3.eu-west-1.amazonaws.com/zr7vgbcyr2-1.zip` (3.35 GB) |
| DOI | 10.17632/zr7vgbcyr2.1 (Pacheco et al., *Data in Brief* 2020) |
| Ethics | Collected under UFES ethics approval 500002/478 and Plataforma Brasil 4.007.097 |

**Why it fits this project better than anything else available today:** the images
are phone photographs taken in a public clinic for low-income patients. Your
deployment is a phone photograph taken in a clinic. That is the same distribution,
which HAM10000 (dermatoscope, specialist clinic, Austria) is not.

**Why it is not a solution on its own:**

* **52 melanomas.** That is the whole malignant-melanoma signal. Any melanoma
  recall you report will have a confidence interval roughly 12 points wide — so
  report the interval or don't report the number.
* Brazilian population, mostly Fitzpatrick II–III. It contains darker skin types
  but it is not an African cohort; do not let it stand in for one.
* Six classes, none of which is Kaposi sarcoma. BCC and SCC must be **excluded**,
  not folded into `benign` (they are malignant), and ACK is pre-malignant.
* One patient can contribute several lesions and one lesion several images →
  split by **patient**, not by image.

Mapping for this project (`scripts/label_maps/padufes20.json`):

| PAD-UFES-20 `diagnostic` | This project |
| --- | --- |
| `MEL` | `melanoma` |
| `NEV`, `SEK` | `benign` |
| `ACK` | *skip* — pre-malignant |
| `BCC`, `SCC` | *skip* — malignant, not our classes |
| — | `kaposi_sarcoma` has **no** source here |

## 2. DermaMNIST — a dataset in one pip command

```bash
pip install medmnist
python -c "
from medmnist import DermaMNIST
d = DermaMNIST(split='train', download=True)
print(len(d), d.info['label'])   # 7007 train+val+test, 7 HAM10000 classes
"
```

| Field | Value |
| --- | --- |
| Size | 20 MB (28×28) or ~1.09 GB (MedMNIST+ at 224×224) |
| Licence | **CC BY-NC 4.0** |
| Provenance | HAM10000, re-split and downsized (Yang et al., *Scientific Data* 2023) |
| Use it for | CI, smoke runs, teaching, ablation plumbing — **never** for a clinical claim |

If a number comes from a 28×28 DermaMNIST model, it says more about anti-aliasing
than about skin. `tests/` uses data this small deliberately; posters must not.

## 3. SCIN — the fairness half

```python
from google.cloud import storage
bucket = storage.Client("dx-scin-public").bucket("dx-scin-public-data")
# dataset/scin_cases.csv   -> sFST, eFST, eMST, subject_id
# dataset/scin_labels.csv  -> dermatologist_label_1..3, weighted_skin_condition_label
# dataset/images/          -> 10,000+ JPEGs
```

Free-tier GCS, no request, no account beyond a Google Cloud project. Licence:
SCIN Data Use License (non-commercial, no re-identification). Already documented
in `docs/DATASET_CARD_SCIN.md`, including the plan for tone-stratified reporting.

## Sources deliberately **not** on this list

| Source | Why not |
| --- | --- |
| PASSION | No answer after repeated requests. Treat as unavailable until a letter arrives |
| Fitzpatrick17k | Google Form + many dead source URLs, and images remain under the atlases' terms |
| DDI | Request-based; small (656). Worth one email, not worth waiting |
| eSkinHealth | Paper provides no reachable link, and its own headline counts disagree with its appendix table |
| **Kaggle "DermNet" scrapes** | Scraped from dermnet.com against that site's terms, no licence for redistribution, and the 23 categories do not include Kaposi sarcoma anyway. A project that has an ethics section should not build on a scrape |
| "Africanized HAM10000" (HF) | Estimated tone via KMeans, **synthetic** EHR. Fabricated metadata dressed as data |

---

## What this means for the Kaposi sarcoma pause

Nothing here changes it: **no immediately available public dataset contains
Kaposi sarcoma.** That is the honest reason gate 1A is paused, and it is worth
saying in exactly those terms rather than as "we are still looking".

The practical consequence is a two-lane project, which is what
[`ROADMAP.md`](./ROADMAP.md) sets out:

* **Lane A (buildable now):** `benign` vs `melanoma` triage, trained on
  PAD-UFES-20 + HAM10000, evaluated tone-stratified on SCIN. Ships without the
  third class.
* **Lane B (partner-gated):** the Kaposi sarcoma head, unlocked by a cohort under
  an approved protocol — the only route that is both lawful and scientifically
  real in Uganda.
