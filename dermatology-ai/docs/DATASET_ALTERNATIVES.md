# Dataset alternatives to PASSION for Dermatology

**Date:** 2026-10-30
**Trigger:** PASSION for Dermatology has not answered access requests. The
project needs a decision, not another request.
**Scope:** which public or obtainable dermatology dataset should replace
PASSION, and what each one can and cannot support.

---

## 1. What PASSION was actually for

It is worth being explicit, because it changes the answer. PASSION is **not** a
malignancy dataset. Per the MICCAI 2024 paper (arXiv:2411.04584) it contains
4,901 images from 1,653 patients across four **paediatric** conditions --
atopic dermatitis, dermatophytosis, scabies and impetigo -- in Cote d'Ivoire,
Malawi, Tanzania and Madagascar, with skin types IV-VI.

So PASSION could only ever have played two roles:

| Role | What it needs | Does PASSION do it? |
| --- | --- | --- |
| **R1. External fairness / triage evaluation on dark skin** | African population, tone labels, clinical (phone-camera) images | Yes -- this was its entire value |
| **R2. Training or validating `melanoma` / `kaposi_sarcoma`** | Pathologically confirmed malignant lesions in dark skin | **No** -- it has neither melanoma nor KS |

Nothing in the current codebase loads PASSION: there is no
`run_evaluation_passion.py`, no loader, and `model_manifest.json` does not
reference it. **The blocker is real, but it is a scope/claims problem, not a
build problem.**

Anything that replaces PASSION only needs to satisfy **R1**. R2 has no public
answer at this size in dark skin, and no dataset below pretends otherwise.

---

## 2. Candidates, compared

| Dataset | Size | Population | Tone labels | Access friction | Licence | R1 | R2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **SCIN** | 10,000+ images / 5,000+ contributions | US, crowdsourced | **sFST + eFST + Monk (eMST)** | **None** -- public GCS bucket `dx-scin-public-data` | SCIN Data Use License | **Best** | No (US; mostly inflammatory/infectious) |
| **DDI** | 656 images / 570 patients | US, Stanford clinic | FST I-II 208, III-IV 241, V-VI 207; **pathologically confirmed** | Request agreement | Research agreement | Adequate | **Partial, small** -- malignant group only |
| **eSkinHealth** | 5,623 images / 1,639 cases, 47 diseases | **Cote d'Ivoire + Ghana**, rural clinics | Metadata yes; FST not headline | **No public link in the paper** -- author contact only | CC BY-NC-SA 4.0 (stated) | **Best African fit** | No (skin NTDs: Buruli ulcer, yaws, leprosy, scabies) |
| **Fitzpatrick17k** | 16,577 images, 114 conditions | US, atlas-sourced | FST I-VI (Scale AI + Centaur Labs) | **Broken source URLs**; full set via Google Form to authors | Source atlases' terms | Adequate | **Partial** -- melanoma present, label provenance weak |
| **SkinCAP / SkinCaRe** | 4,000 images, 178 diseases | derives from Fitzpatrick17k + DDI | inherits parents | Hugging Face | annotations CC-BY-4.0; images under parents' terms | Adequate | No (subsample of DDI/F17k) |
| "Africanized HAM10000" (HF) | HAM10000 + **estimated** tone + **synthetic** EHR | n/a | KMeans-LAB estimate, 88.9% FST I-II | Immediate | unclear | **Reject** | **Reject** |

### Why each was ranked where it is

**SCIN -- first choice.** It is the only candidate that is both large enough to
stratify by skin tone and obtainable today with no human in the loop. Two
independent tone labels (self-reported and dermatologist-estimated) let the
fairness analysis show whether results depend on *how* tone was measured -- a
methodological point no other candidate supports. Weakness is the population:
US crowdsourced, not African, and dominated by conditions with no malignancy
counterpart.

**DDI -- second, already integrated.** Small but pathologically confirmed and
tone-balanced, which makes it the only candidate that can put a number on
malignant-vs-benign behaviour across tone groups. 656 images means wide
confidence intervals; it is corroborating evidence, not a benchmark. Access is
by request, so the same silence that killed PASSION could kill this; the request
is already drafted in `docs/OPERATIONS.md` §7.

**eSkinHealth -- best African fit, blocked on access.** 5,623 on-site clinical
images from Cote d'Ivoire and Ghana, expert-consensus diagnoses, lesion masks
and 69 clinical concepts: everything R1 wants and the closest thing to a
PASSION twin. But the paper provides no reachable data link (its "available
here" carries no URL), and the headline counts are internally inconsistent
(5,623/1,639/47 in the text vs 5,769/1,679/48 when its own appendix table is
summed). Treat it as *a letter to the authors*, not a plan. Worth sending --
low cost, high upside -- but nothing may depend on it.

**Fitzpatrick17k -- supplementary only.** Largest breadth with tone labels, but
many source image URLs are dead and the full set needs a Google Form, so it has
the same access risk as PASSION; images remain under the atlases' terms, and
label provenance is weaker than DDI's. Good for a sensitivity check, not a
primary benchmark.

**SkinCAP -- useful annotations, redundant images.** Its value is the
dermatologist observation-first captions for concept-level explanation; its
images are a subset of Fitzpatrick17k + DDI, so it adds no new patients.

**"Africanized HAM10000" -- do not use.** Tone labels are KMeans estimates in
LAB space, not Fitzpatrick assessments, and the EHR fields are synthetic. Citing
it as evidence of African performance would be fabrication with extra steps. It
appears here as a documented example of the failure mode this project must
avoid.

---

## 3. Recommendation

**Adopt SCIN as the replacement for PASSION's role, keep DDI, and treat
eSkinHealth as an open letter rather than a dependency.**

Concretely:

1. **Now:** SCIN becomes the external fairness/triage evaluation cohort. Add
   `DATASET_CARD_SCIN.md` (done), the adapter preset and label map (done), and
   later `run_evaluation_scin.py`.
2. **Now:** stop describing PASSION as a planned evaluation set. The card is
   marked unavailable and the access request is treated as failed.
3. **In parallel, zero-cost:** send one email to the eSkinHealth authors
   (Cote d'Ivoire/Ghana cohort, CC BY-NC-SA). If it lands, it upgrades the
   African evidence substantially.
4. **If real malignancy numbers in dark skin are required:** DDI is the only
   option; file the request and accept n=656.
5. **Never:** claim African performance from SCIN, or claim three-class
   accuracy from a mapped-label cohort. SCIN is US data; mapped labels are not
   diagnoses.

### What this changes in the write-up

The honest statement becomes: *"External tone-stratified evaluation uses SCIN
(US, crowdsourced, two tone schemes); DDI provides a small pathologically
confirmed malignancy check; no African clinical cohort is currently available
to this project, and PASSION access has not been granted."* That is a
limitation, stated as one -- not a gap papered over.

---

## 4. Integration status

| Item | State |
| --- | --- |
| `scripts/prepare_dataset.py` | **done** -- converts any source CSV into `metadata.csv` + `images/`, with a full `conversion_report.json` |
| `scripts/label_maps/{scin,ddi,fitzpatrick17k}.json` | **done** -- explicit maps; unmapped labels are skipped, never coerced |
| `docs/DATASET_CARD_SCIN.md` | **done** |
| `docs/DATASET_CARD_PASSION.md` | **corrected** -- 4,901 images / 1,653 patients / four conditions; marked unavailable |
| `run_evaluation_scin.py` | **not written** -- needs the data downloaded first; per the honesty rule, no number may be quoted before it exists |
| SCIN download itself | **not performed** -- the bucket is ~tens of GB; do it on the machine that will train/evaluate, not in CI |

`/api/diagnose` remains **503** regardless of dataset choice: the gate is the
frozen checkpoint (S1-1), not the data. See
[`GATE_OPTIONS.md`](./GATE_OPTIONS.md).

---

## 5. Problems found while doing this analysis (reported, not fixed)

Per the repository rule, these are surfaced rather than patched silently.

1. **`scripts/download_passion.py` describes a dataset that does not exist.**
   Its `CLASS_MAPPING` assumes twelve classes -- `nevus`,
   `seborrheic_keratosis`, `lentigo`, `dermatofibroma`, `melanoma`,
   `kaposi_sarcoma`, `actinic_keratosis`, `basal_cell_carcinoma`,
   `squamous_cell_carcinoma`, eczema, psoriasis -- and excludes BCC/SCC. The real
   PASSION cohort has four paediatric conditions and none of those labels. The
   script also **defaults a missing Fitzpatrick value to `3`**, which fabricates
   metadata. It cannot currently run (the URL is a placeholder that makes it
   exit early), so nothing downstream is contaminated, but it is misleading and
   would fail if anyone obtained access.
   *Proposed fix (needs your go-ahead):* delete the class mapping and the
   Fitzpatrick default, reduce the script to "locate a downloaded archive, hand
   its CSV to `scripts/prepare_dataset.py`", and mark it unsupported until
   access is granted.
2. **`MODEL_CARD.md` called PASSION a "Ugandan cohort".** Corrected: the cohort
   is Cote d'Ivoire, Malawi, Tanzania and Madagascar.
3. **`docs/DATASET_CARD_PASSION.md` claimed "~19k images" and "12 disease
   categories".** Both were unsupported; corrected to 4,901 images / 1,653
   patients / four conditions, and the card now records the correction.
4. **`README.md` and the poster still describe PASSION as the African evaluation
   set** in places. Left untouched for now, since the replacement decision is
   yours.
