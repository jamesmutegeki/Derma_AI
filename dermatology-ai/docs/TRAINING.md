# Producing the frozen checkpoint (gate S1-1, option 1A)

`/api/diagnose` returns **503** while `model_manifest.json` says
`status: placeholder`. This page is the procedure that closes that gate. It has
not been executed inside this repository's development sandbox, because
HAM10000 is served from `dataverse.harvard.edu` and the sandbox has no route to
it -- so the commands below are the exact ones to run where the data lives.

Everything around the training step is implemented and tested:
`scripts/prepare_dataset.py` (conversion), `scripts/train_model.py` (train),
`scripts/freeze_model.py` (hash + manifest), `scripts/eval_common.py`
(evaluation that refuses to report numbers from unverified weights).

---

## 0. What you need

| Item | Detail |
| --- | --- |
| Disk | ~3 GB for HAM10000 images, ~1 GB for the converted copy |
| Compute | GPU strongly preferred. A free Colab T4 is enough |
| Time | ~1 h on a T4 for 10 epochs at 224 px; see §5 for CPU |
| Licence | HAM10000 is **CC BY-NC 4.0** -- non-commercial research only |

## 1. Obtain the images

HAM10000 (Tschandl et al. 2018) is published at the Harvard Dataverse; the
archive is `HAM10000_images_part_1.zip` + `_part_2.zip` with
`HAM10000_metadata.csv`. `scripts/download_datasets.py` already contains the
dataverse endpoints this project uses.

## 2. Convert to the training layout

```bash
python scripts/prepare_dataset.py \
    --input  <ham>/HAM10000_metadata.csv \
    --images-root <ham>/images \
    --image-column image_id --label-column dx --fitz-column fitzpatrick_type \
    --label-map scripts/label_maps/ham10000.json \
    --group-column lesion_id \
    --output datasets/ham10000 --source HAM10000
```

Notes:

* `--group-column lesion_id` is not optional in spirit. HAM10000 contains
  several images per lesion; without it the validation split leaks.
* HAM10000 has **no Fitzpatrick metadata**. Every `fitzpatrick_type` will be
  `0`, which is reported as an "unknown skin type" bucket. That is not a
  fairness result, and no per-tone claim may be made from this dataset.
* `dx` is collapsed by the label map to `benign` / `melanoma` /
  `kaposi_sarcoma`; `bcc`, `akiec` and `vasc` are excluded, not merged into
  `benign`.
* Read `datasets/ham10000/conversion_report.json` before training. If the
  row count or class counts look wrong, stop there -- do not train and hope.

## 2b. The third class has no training data -- read this before training

HAM10000 contains **no Kaposi sarcoma images** (its seven categories are nv,
mel, bkl, bcc, akiec, vasc, df). Neither does SCIN, and DDI's malignant group is
dominated by carcinomas. As of 2026-10-30 this project has **no public source of
Kaposi sarcoma images at usable scale**, and PASSION (which could have supplied
African oncology images) is inaccessible.

Consequence: a three-class head trained tonight would have `kaposi_sarcoma`
output weight learned entirely from the other two classes. It would look like a
working model and would be untrustworthy for exactly the class that matters most
in Uganda.

`scripts/train_model.py` therefore **refuses to run** when a class has no
training examples, and prints the three legitimate ways forward:

| Option | What it means | Trade-off |
| --- | --- | --- |
| **Obtain a Kaposi sarcoma cohort** | A dermatology/oncology partner (e.g. a national cancer institute) provides images under an approved protocol | Correct, but needs the full ethics route (gate 4B) and time |
| **Serve two classes** | Train and expose `benign` / `melanoma` only; the API contract changes and must be logged in the Breaking-Change Register | Honest and shippable now, but the product loses a class it advertises |
| **`--allow-untrained-classes`** | Train anyway; the report records `untrained_classes: ["kaposi_sarcoma"]` | Only acceptable for a pipeline demonstration, never for a served model |

This is a decision for the owner, not something to paper over. Until it is made,
S1-1 stays open -- and that is the correct state, because the alternative is a
checkpoint that silently cannot do part of its job.

## 3. Train

```bash
python scripts/train_model.py \
    --data-dir datasets/ham10000 \
    --out runs/ham10000-$(date +%F) \
    --epochs 10 --batch-size 32 --img-size 224 --seed 42 \
    --dataset HAM10000 \
    --split "group-aware 80/20 by lesion_id, seed 42"
```

What it does: group-aware stratified split, the same `transforms.build_transform`
pipeline used at serving time, HRNet-W18 backbone (ImageNet-pretrained), a
concept bottleneck into three classes, AdamW, cross-entropy, best-effort
provenance (git commit, seed, epochs, image size, device).

Add `--allow-untrained-classes` only if §2b has been decided and the gap is
being recorded deliberately; the report will then carry
`untrained_classes: ["kaposi_sarcoma"]` and its per-class recall as `null`.

It writes `runs/<name>/checkpoints/model.pt` and `runs/<name>/report.json`, with
per-class metrics, a confusion matrix and a per-skin-type table where groups
with no samples are **absent** rather than zero.

## 4. Freeze

```bash
python scripts/train_model.py ... --freeze        # same command, plus --freeze
```

or, from an existing run:

```bash
python scripts/freeze_model.py \
    --checkpoint runs/ham10000-2026-10-30/checkpoints/model.pt \
    --dataset HAM10000 --split "group-aware 80/20 by lesion_id, seed 42" \
    --seed 42 --epochs 10 --git-commit "$(git rev-parse HEAD)" \
    --metrics-report runs/ham10000-2026-10-30/report.json \
    --out model_manifest.json
```

`train_model.py --freeze` verifies the manifest hash against the checkpoint
afterwards and fails if they disagree or if the status is not `frozen`.

**A `--smoke` run can never be frozen.** Its report is `valid: false` and the
freeze step exits 3 without touching the manifest. That is the guard that keeps
a code-path test from becoming a served model.

## 5. If you only have a CPU

Use a smaller input size and fewer epochs, and say so when you report:

```bash
python scripts/train_model.py --data-dir datasets/ham10000 \
    --out runs/ham10000-cpu --epochs 3 --batch-size 16 --img-size 128 --cpu ...
```

At 128 px expect roughly 1-2 h per epoch on a modern laptop CPU (estimate, not a
measurement). Record the size in the model card: a 128 px model evaluated at the
service's 224 px input is a distribution shift, and the report should admit it.

## 6. After freezing

1. `python -m pytest -q` and `bash scripts/definition_of_done.sh` -- the gate
   should now show S1-1 satisfied.
2. Update `MODEL_CARD.md` with the **measured** figures from `report.json`, and
   only those. "Not yet measured" becomes a number, or stays as it is.
3. Re-run `python run_evaluation_ham.py` against the frozen checkpoint so the
   evaluation report and the manifest agree.
4. If any document, poster or slide quotes a number, it must trace to
   `runs/<name>/report.json` and `model_manifest.json`.
5. Do **not** deploy with real patient images. That still needs the IRB
   determination (`docs/IRB_EXEMPTION_REQUEST.md`) and, for clinical use, a
   regulatory route this project does not pursue.
