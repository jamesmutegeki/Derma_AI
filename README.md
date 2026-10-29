**Disclaimer:** This tool is for research and educational purposes only. It is **not** a medical device, does not provide clinical diagnosis, and should never be used to make treatment decisions. Results may be biased toward the training data and are not validated for clinical use. Always consult a qualified dermatologist or physician.

# Applications

Collection of my web applications and software projects.

## Projects

- [**Explainable Dermatology AI: Combining RL and XAI for Transparent Treatment and Diagnosis**](./dermatology-ai/) — AI-powered dermatology triage and diagnosis support system with clinician-in-the-loop (HITL) reinforcement learning.
- [**Explainable Dermatology AI Poster**](./dermatology-ai/poster.html)



## Status

_Last updated 2026-10-30. Nothing here is a clinical claim; see
`dermatology-ai/MODEL_CARD.md` and `dermatology-ai/REMEDIATION_STATUS.md`._

**Available**

- FastAPI clinical API and dashboard (`dermatology-ai/server.py`, `dashboard.html`)
  with Bearer auth, per-route authorization, SQLite storage and an audit trail.
- Concept-bottleneck model code (`model.py`), single train/serve preprocessing
  pipeline (`transforms.py`), fairness metrics over clinician-confirmed cases
  (`metrics_tracker.py`), contextual-bandit triage agent (`rl_module.py`).
- 80+ automated tests and a CI guard (`dermatology-ai/scripts/ci_grep.sh`) that
  fails on fabricated claims or shipped default credentials.
- Evaluation scripts that run end-to-end in `--smoke` mode and write a JSON
  report (`run_evaluation_ham.py`, `run_evaluation_passion.py`).

**Missing**

- **No trained checkpoint is distributed.** `MODEL_CHECKPOINT_PATH` is unset by
  default, so `/api/diagnose` answers 503 by design; `/api/ready` says why.
- No validated accuracy, AUROC or fairness measurement. `model_manifest.json` is
  a `placeholder`; nothing may be quoted until it references a frozen report.
- No dataset is included (HAM10000, PASSION and DDI each have their own terms).
- No encryption at rest, no tested restore, no IRB approval -- so **no real
  patient data** may be loaded yet (`dermatology-ai/SECURITY.md` §8).

**Broken / known limitations**

- The legacy Gradio UI (`python main.py --ui`) is optional and needs `gradio`
  installed plus a real checkpoint.
- Fitzpatrick IV-VI performance is unmeasured; HAM10000 is overwhelmingly light-
  skinned and the model performs no out-of-distance detection.
- `atypical_lesion` exists only in the triage catalogue, not as a vision class.

## Quick start

```bash
cd dermatology-ai
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # optional; every variable is documented there
python main.py --dashboard      # http://localhost:7860  (first run prints where
                                # the generated admin password was written)
python -m pytest -q             # full suite
bash scripts/ci_grep.sh         # claim/credential guard
```

# Derma_AI — Agent Task Instructions

**Repository:** https://github.com/jamesmutegeki/Derma_AI

## 📋 Execution Protocol (READ IN ORDER — DO NOT SKIP)

**Step 1 — Read the current state first.**
Read `dermatology-ai/REMEDIATION_STATUS.md` (what is done, with the acceptance
test that proves it), then `CODE_REVIEW.md` (the findings this work is closing)
and `dermatology-ai/SECURITY.md` (the security and data-handling rules). The
file this step used to reference never existed, so it now points at the
three documents above.

**Step 2 — Read this `README.md` in full.**
Understand the project context, goals, and the complete task list below before touching any code or files.

**Step 3 — Verify environment and resources.**
Check that everything needed is present and functional:
- Required folders/files (e.g., `src/`, `models/`, `data/`, `notebooks/`, templates, datasets, requirements/environment files).
- Dependencies install correctly (`requirements.txt` / `environment.yml` / `package.json`, etc.).
- Existing model(s), weights, and training/inference scripts run without errors.
- Any referenced templates (proposal, journal, poster) are present and usable.

Report clearly what is **available**, what is **missing**, and what is **broken** before continuing. Do not silently skip missing/broken items — flag them.

**Step 4 — Full Project Review (code + everything else).**
Before any implementation:
- Review **every file** in the repository — source code, notebooks, configs, docs, data pipelines, model definitions, training scripts, tests, CI/CD, and documentation.
- Build a clear understanding of the current architecture: how the model is trained, what dataset(s) it currently uses, how inference/testing works, and what's already documented vs. undocumented.
- Identify inconsistencies, outdated docs, dead code, or gaps between what the code does and what is documented.
- Summarize all findings before moving to implementation.

**Step 5 — Execute all tasks below, end to end, without stopping early.**
Work through each task in order. If blocked on one task (e.g., missing journal choice, missing co-author info, ambiguous dataset licensing), note the blocker, make a reasonable assumption/placeholder, and continue — rather than halting. Keep working until all tasks are complete or genuinely blocked.

> ⚠️ **If any issues are discovered in the existing code, data, or model (bugs, broken pipelines, failing tests, data leakage, etc.), STOP and prompt me first with a description of the issue and your proposed fix. Do not apply fixes silently.**

---

## ✅ Tasks

### 1. Complete the Project Proposal
Using the official proposal template:
- [ ] Chapter 1 — Introduction
- [ ] Chapter 2 — Literature Review
- [ ] Chapter 3 — Methodology

### 2. Finalize and Submit the Literature Review Paper
- [ ] Select an appropriate target journal and verify its **Impact Factor**.
- [ ] Confirm the journal **accepts review-type papers**.
- [ ] Select the correct **manuscript template** for that journal.
- [ ] Identify co-authors (positions 1–4): I am the **corresponding author**; the 4th author should be a computing staff member. Flag where their **consent** and **pre-submission review** is still pending (manual/human step).
- [ ] Prepare the **Overleaf document link** and the **corresponding author's email** for submission records.
- [ ] Submit (or prepare the submission package) to the selected journal.

### 3. Develop the Research Poster
- [ ] Summarize the current status of the literature review.
- [ ] Highlight how the review informed the research pipeline: **Methodology** and **Dataset** choices.
- [ ] Produce a poster draft ready for presentation.

### 4. Dataset Expansion — Add an African Dataset
- [ ] Research and select a suitable **African-sourced dermatology/skin dataset** (e.g., diverse skin tone datasets covering African populations — such as the SCIN dataset, DDI, or any peer-reviewed African dermatology image dataset with proper licensing for research use).
- [ ] Verify licensing, ethical sourcing, and consent compliance before use.
- [ ] Integrate it into the existing training pipeline alongside current datasets.
- [ ] Document the dataset source, size, class distribution, and why it was chosen.

### 5. Prepare and Train a Sample Prototype
- [ ] Build/update a working prototype reflecting preliminary results, incorporating the newly added African dataset.
- [ ] Document how it connects to the methodology and dataset described in the literature review.

### 6. Test the Model
- [ ] After training/integration, run evaluation on a held-out test set and report metrics (accuracy, precision, recall, F1, confusion matrix, etc., as applicable).
- [ ] Compare performance before vs. after adding the African dataset.
- [ ] Provide clear, step-by-step **instructions for me to test the model myself** (how to run inference, sample commands, expected inputs/outputs, environment setup).

### 7. Generate a Summary Report (.docx)
- [ ] Write a `.docx` file (e.g., `project_update_report.docx`) summarizing:
  - What was reviewed in the project
  - What was changed/added (including the dataset decision and rationale)
  - Test results and performance comparison
  - Any issues found and how they were resolved (or are pending my input)
  - Outstanding items needing human decision
- [ ] Save it in an appropriate location in the repo (e.g., `docs/reports/`).

### 8. Commit and Push All Changes
- [ ] Commit all changes with clear, descriptive commit messages (group logically — e.g., docs, dataset integration, model training, report).
- [ ] Push all commits to: **https://github.com/jamesmutegeki/Derma_AI**
- [ ] Confirm the push succeeded and share the commit hash(es)/links.

---

## 🔁 Completion Rule
Do not stop after finishing one task — continue sequentially through all tasks above. At the end, produce a short status report covering:
1. What was completed
2. What was blocked, and why
3. Issues found that require my sign-off before being fixed
4. What human input/decision is still needed (e.g., journal choice, co-author consent, poster presentation date, dataset licensing approval)
