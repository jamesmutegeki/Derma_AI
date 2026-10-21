**Disclaimer:** This tool is for research and educational purposes only. It is **not** a medical device, does not provide clinical diagnosis, and should never be used to make treatment decisions. Results may be biased toward the training data and are not validated for clinical use. Always consult a qualified dermatologist or physician.

# Applications

Collection of my web applications and software projects.

## Projects

- [**Explainable Dermatology AI: Combining RL and XAI for Transparent Treatment and Diagnosis**](./dermatology-ai/) — AI-powered dermatology triage and diagnosis support system with clinician-in-the-loop (HITL) reinforcement learning.
- [**Explainable Dermatology AI Poster**](./dermatology-ai/poster.html/)



# Derma_AI — Agent Task Instructions

**Repository:** https://github.com/jamesmutegeki/Derma_AI

## 📋 Execution Protocol (READ IN ORDER — DO NOT SKIP)

**Step 1 — Read `AGENTS.md` first.**
Locate and read the `AGENTS.md` file in the repository root before doing anything else. This file defines the agent's operating rules, constraints, and conventions. Do not proceed until it has been fully read and understood.

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
