# Dermatology AI — Project Milestones & Overview

> Source: `README.md`, `Dermatology_AI_Uganda_Roadmap.pdf` (Sept 2026), `git log`, code inspection (`dermatology-ai/`)
>
> Status: **Pre-Phase 1** — Awaiting stakeholder alignment (Roadmap). Core application is built; testing, deployment, and clinical validation remain.

---

## What this project is (Explanation)

**Dermatology AI** is an AI-powered clinical decision-support system for dermatology treatment and diagnosis, designed specifically for deployment in Uganda/East Africa (Uganda Cancer Institute & Mbarara Hospital).

### Core idea
It combines a **Concept-Bottleneck Model** (CBM) — interpretable, concept-level explanations grounded in medical features — with **Clinician-in-the-Loop (HITL) reinforcement learning** (RL/PPO) so doctors can correct or confirm predictions and the system learns from that feedback continuously.

### Why this approach?
The external `Dermatology_AI_Uganda_Roadmap.pdf` (Sept 2026) explicitly identified gaps in existing open-source dermatology AI:
- No African skin-tone data at scale
- No RL/HITL loop after training
- No operational fairness monitoring (only training-time debiasing)
- No integrated web-first deployment with telemetry

This project was built to close those gaps: fairness scripts (`datasetEquity.py`, `samplesEquity.py`), a FastAPI dashboard (`server.py`), Gradio clinician UI (`main.py --ui`, `ui.py`), and synthetic/mock case generation (`main.py`) to test the HITL loop before clinical deployment.

### Tech stack (short)
- **ML:** PyTorch (`torch>=2.1`), `torchvision`, `timm`, `albumentations`, `captum`, `scikit-learn`
- **Web/API:** FastAPI (`fastapi`, `uvicorn`), Gradio (`gradio>=6.0`), `bcrypt` auth, UUID sessions
- **Data:** JSON/CSV patients (`patients.json`, `doctors.json`, `case_history.json/csv`), image datasets (`ham10000/`, `fitzpatrick17k/`, `isic2019/`, `isic2020/`, `synthetic/`)
- **Visual/Reporting:** `matplotlib`, `plotly`, `Pillow`, `dashboard.html`, `poster.html`, `slides.html`

### How it was built (architecture)
1. **Synthetic data generation** (`main.py`) creates mock patients with concept embeddings + Fitzpatrick skin-type weights.
2. **Concept bottleneck** (`model.py`) maps inputs to 7 interpretable concepts, then to 3 diagnosis classes (with Fitzpatrick awareness).
3. **RL / HITL loop** (`rl_module.py`, `hitl_pipeline.py`) uses `Case` objects and PPO-style actions; clinician feedback updates the model.
4. **Fairness tracking** (`metrics_tracker.py`, `datasetEquity.py`) logs performance and checks representation.
5. **Web delivery** (`server.py` REST API + `ui.py` Gradio + `dashboard.html`) bridges backend to clinicians; `render.yaml` supports deployment.

---

## Milestones

### 📋 Original / Planned Milestones (from README, Roadmap PDF, git history)

1. **Clinical decision-support system** (explicit — `README.md`; commit `05b2921`) — AI treatment/diagnosis with concept-level explanations.
2. **Clinician-in-the-Loop (HITL) RL pipeline** (explicit — README / `hitl_pipeline.py`) — doctors correct predictions; system learns.
3. **Concept-bottleneck interpretability** (explicit — Roadmap gap + `model.py`) — frozen/explainable concepts, not black-box.
4. **African skin-tone fairness + equity monitoring** (explicit — Roadmap: "no real African skin-tone data at scale, no operational fairness monitoring"; `datasetEquity.py`, `samplesEquity.py`).
5. **Integrated web-first deployment with telemetry** (explicit — Roadmap gap + `server.py`, `dashboard.html`, `render.yaml`, `activity.json`).
6. **Data curation / dataset ingestion** (inferred — `download_datasets.py`, `datasets/` folders, `fitzpatrick17k.csv`).
7. **Poster / dissemination materials** (inferred — `poster.html`, `slides.html`, `deliverables/` PDF script, `Dermatology_AI_Uganda_Roadmap.pdf`).
8. **Pre-Phase 1 stakeholder alignment** (explicit — Roadmap PDF, Sept 2026: "Awaiting Stakeholder Alignment").

---

### ✅ Completed Milestones

| # | Milestone | Evidence / Proof |
|---|-----------|------------------|
| 1 | **Repo initialization + restructuring** | `05b2921` initial; `a7ede08` moved into `dermatology-ai/`; `6f10c41` fixed ID/path bugs; clean directory now (duplicate root files removed) |
| 2 | **Concept-bottleneck model** | `dermatology-ai/model.py` (7 concepts, 3 classes); `notebooks/01_train_cbm.ipynb` present |
| 3 | **HITL / RL pipeline** | `rl_module.py` (`Case` class, PPO actions); `hitl_pipeline.py`; `main.py` synthetic case generator (`generate_mock_cases`) |
| 4 | **Web UI (Gradio)** | `ui.py`; `main.py --ui` launcher |
| 5 | **Dashboard backend (FastAPI)** | `server.py` (FastAPI, `bcrypt` auth, UUID sessions, endpoints for patients/doctors/cases) |
| 6 | **Fairness / equity tooling** | `datasetEquity.py`, `samplesEquity.py`; melanin-normalization references in code |
| 7 | **Metrics tracking + export** | `metrics_tracker.py`; `case_history.json`/`case_history.csv` persistence |
| 8 | **Synthetic / demo data pipeline** | `main.py` mock generator; `seed_demo.py`; `patients.json` / `doctors.json` |
| 9 | **HTML dashboard + poster / slides** | `dashboard.html`, `poster.html`, `slides.html`; `README.md` links updated |
| 10 | **Model checkpoints** | `model_checkpoints/smoke_cbm.pt`; `agent_params.pt` |
| 11 | **Dashboard UI fix wave (latest)** | `18981b2` — queue popup, notif auto-dismiss, compact profile, password toggle, admin login white-screen fix, scroll limit |

---

### 🔜 Remaining Milestones

| # | Milestone | What is needed | Dependencies | Complexity |
|---|-----------|----------------|--------------|------------|
| 1 | **Formal test suite / CI** | Run/verify `_run_tests.py`, `_full_test.py`, `_smoke_test.py`; add `pytest` pipeline; coverage report | None | Medium |
| 2 | **Data quality / consistency check** | Verify `patients.json`, `doctors.json`, `case_history.json`, dataset CSVs after consolidation; remove `fitzpatrick17k` lock file if stale | Milestone 1 (tests validate data) | Small |
| 3 | **Dataset pipeline completion** | Complete ingestion/curation for `datasets/fitzpatrick17k/`, `isic2019/`, `isic2020/`; verify image counts match indexes | Milestone 2 | Medium |
| 4 | **Deployment + telemetry** | Confirm `render.yaml` deployment; wire `activity.json` / server logs to live telemetry; ensure `server.py` runs stable under load | Milestone 3 (clean data) | Medium–Large |
| 5 | **Documentation (subfolder README + guides)** | Add `dermatology-ai/README.md`; document `model.py` choices, `server.py` endpoints, `notebooks/` usage, training hyperparameters | None (can parallel) | Small |
| 6 | **Security / audit hardening** | Rate-limiting middleware; audit logging for admin/doctor actions; file-upload validation in `server.py` | Milestone 4 (deployment context) | Small–Medium |
| 7 | **Stakeholder alignment / clinical validation** | Sign-off at Uganda Cancer Institute / Mbarara Hospital per Roadmap; clinical pilot protocol; ethics/IRB as needed | Milestones 4–6 (credible demo) | **Large (external)** |

---

## Quick reference: done vs not done

- ✅ **Built:** model, HITL loop, APIs, UI, fairness tools, data, posters
- ❌ **Not done:** automated tests, full dataset curation, live deployment, docs, security audit, stakeholder sign-off
- ⏳ **Blocked / external:** Pre-Phase 1 stakeholder alignment (Roadmap PDF)

---

*File created after full directory analysis (reorganization completed: duplicates removed, scripts organized, datasets consolidated, personal docs archived).*
