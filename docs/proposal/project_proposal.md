# Explainable Dermatology AI: Combining RL and XAI for Transparent Treatment and Diagnosis

**Project Proposal — Chapters 1–3**

**Student**: James Mutegeki (M24B23/007)  
**Program**: BSc Computer Science  
**Institution**: Uganda Christian University  
**Date**: October 2026  
**Repository**: https://github.com/jamesmutegeki/Derma_AI

---

> **Disclaimer**: This tool is for research and educational purposes only. It is **not** a medical device, does not provide clinical diagnosis, and should never be used to make treatment decisions. Results may be biased toward the training data and are not validated for clinical use. Always consult a qualified dermatologist or physician.

---

## Chapter 1 — Introduction

### 1.1 Problem Statement

Dermatology AI systems have achieved dermatologist-level accuracy on benchmark datasets (Esteva et al., 2017; Tschandl et al., 2020), yet **clinical adoption in East Africa remains near zero**. A 2026 roadmap analysis for Uganda Cancer Institute and Mbarara Hospital identified four critical gaps blocking deployment:

1. **No African skin-tone data at scale** — Public datasets (HAM10000, ISIC) are predominantly Fitzpatrick I–III; models trained on them exhibit 10–20% accuracy drops on Fitzpatrick IV–VI (Daneshjou et al., 2022).
2. **No clinician-in-the-loop (HITL) reinforcement learning** — Models are static after training; they cannot learn from clinician corrections during real-world use.
3. **No operational fairness monitoring** — Fairness audits are retrospective (training-time only); no live per-Fitzpatrick accuracy tracking exists in deployed systems.
4. **No integrated web-first deployment with telemetry** — Research prototypes lack clinician-facing UIs, authentication, audit logging, and telemetry for continuous improvement.

### 1.2 Research Objective

> **Investigate whether a Concept-Bottleneck Model (CBM) combined with Human-in-the-Loop Reinforcement Learning (HITL-RL) improves diagnostic reliability and fairness — particularly for underrepresented skin tones — compared to standard transfer-learning baselines, under low-label and low-bandwidth conditions typical of East African clinical settings.**

Specific sub-objectives:
- **O1**: Build a multi-disease CBM (7 interpretable concepts → 3 diagnoses) with explicit Fitzpatrick skin-type conditioning.
- **O2**: Implement a PPO-style RL triage agent (routine / follow-up / urgent) with fairness-weighted rewards that penalize critical misses on darker skin types more heavily.
- **O3**: Deploy an operational fairness monitor that tracks per-Fitzpatrick accuracy and critical-miss rates in real time.
- **O4**: Deliver a web-first clinical dashboard (FastAPI + Gradio + HTML) with clinician authentication, case review, override logging, and CSV export.

### 1.3 Contributions

| # | Contribution | Novelty |
|---|--------------|---------|
| C1 | **African skin-tone dataset integration** — PASSION for Dermatology (~19k images, Fitz I–VI balanced, Nigerian/Kenyan/SA sources) combined with HAM10000, synthetic, and ISIC data | First CBM trained on PASSION + HAM10000 for multi-disease (benign/melanoma/Kaposi sarcoma) with Fitzpatrick conditioning |
| C2 | **Interpretability via 7-concept bottleneck** — Asymmetry, Border Irregularity, Color Variegation, Diameter, Melanin Density, Inflammation, Ulceration — mapped to clinical ABCD+ criteria | Concept scores exposed to clinicians; Grad-CAM + Integrated Gradients (Captum) heatmaps for audit |
| C3 | **HITL PPO-style RL loop** — Clinician overrides update the triage policy via offline policy optimization; fairness-weighted reward function | First dermatology RL system with dynamic Fitzpatrick multipliers (×2/3/4 for types IV/V/VI) |
| C4 | **Operational fairness monitoring** — Live per-Fitzpatrick triage accuracy, critical-miss rates, override rates, demographic parity/equalized odds tracking | Runs in production dashboard; not retrospective |
| C5 | **Web-first clinical deployment** — FastAPI REST API, Gradio clinician UI, HTML analytics dashboard, bcrypt auth, UUID sessions, activity logging | End-to-end system ready for Uganda Cancer Institute / Mbarara Hospital pilot |

### 1.4 Scope & Deliverables

| Deliverable | Format | Location |
|-------------|--------|----------|
| Project Proposal (Chapters 1–3) | Markdown + PDF | `docs/proposal/` |
| Literature Review Paper | LaTeX/Overleaf + PDF | `docs/papers/` |
| Research Poster | HTML (printable) | `dermatology-ai/poster.html` |
| Trained Model Checkpoints | PyTorch `.pt` | `dermatology-ai/model_checkpoints/` |
| Evaluation Report | `.docx` | `docs/reports/project_update_report.docx` |
| Source Code | Python/HTML/JS | `dermatology-ai/` |

---

## Chapter 2 — Literature Review

### 2.1 Vision Models in Dermatology AI (2020–Present)

| Model | Typical AUC / Acc. | Pros | Cons | Key References |
|-------|-------------------|------|------|----------------|
| **ResNet-50/101** | AUC ~0.92–0.96 (ISIC-2020, HAM10000) | Well-studied, widely pretrained | Large params, slower inference | [1, 2] |
| **EfficientNet-B0–B7** | AUC ~0.95–0.97 (Fitzpatrick-17k, HAM10000) | Best accuracy/param ratio | Complex scaling logic | [2, 3] |
| **DenseNet-121/201** | AUC ~0.95–0.97 (ISIC-2018) | Dense connectivity → strong gradient flow | Memory-intensive | [3, 4] |
| **MobileNet-V2/V3** | AUC ~0.93 (HAM10000, <1M params) | Tiny footprint, ideal for edge | Slightly lower absolute accuracy | [4, 5] |
| **ViT-B/L** | AUC ~0.96–0.98 (large ISIC splits, IN-21k pretrain) | Global self-attention | Needs large data, high compute | [5, 6] |
| **Swin-T/B** | AUC ~0.97 (ISIC-2020, DermNet-2023) | Hierarchical windows = efficiency + accuracy | Complex implementation | [6, 7] |
| **Hybrid Conv-Transformer (SkinFormer, ConvNeXt-V2)** | AUC ~0.98 (largest public collections) | Conv inductive bias + transformer global reasoning | Very large, data-hungry | [7, 8] |
| **HRNet-W18** (this work) | AUC ~0.95–0.97 (multi-resolution) | Preserves fine-grained spatial detail; multi-scale feature pyramids | Less common in dermatology literature | [9] |

**Why HRNet-W18?** The Concept Bottleneck requires high-resolution feature maps for concept localization (asymmetry, border, ulceration). HRNet's parallel multi-resolution branches maintain spatial fidelity better than single-path CNNs or ViTs, making it uniquely suited for concept-level interpretability.

### 2.2 African-Focused Dermatology Datasets (2020–Present)

| Dataset | Size | Disease Classes | Fitzpatrick Coverage | Access | Relevance |
|---------|------|-----------------|---------------------|--------|-----------|
| **PASSION for Dermatology (2024)** | ~19k | 12 (pigmented, inflammatory, infectious) | Balanced I–VI (explicitly enriched for dark skin) | Open (academic registration) | **Primary choice** — designed to close diversity gap; Nigerian, Kenyan, SA sources |
| **eSkinHealth (2025)** | ~8k | NTDs (leprosy, yaws, Buruli ulcer) | Predominantly IV–VI | Open (arXiv/GitHub) | Directly targets sub-Saharan prevalent diseases |
| **Fitzpatrick-17k (2019–2023)** | 17k | 114 labels (broad taxonomy) | Full I–VI distribution | Public (GitHub/HF) | Standard benchmark for skin-tone-aware models |
| **HAM10000 (2018–2024)** | 10k | 7 (melanoma vs. benign) | Mostly I–III (limited dark skin) | Public (Zenodo/Kaggle) | Frequently combined with darker-skin datasets |
| **DDI (2023)** | 656 | 3 | 208 I–II / 241 III–IV / 207 V–VI | Request (Stanford AIMI), DOI 10.71718/kqee-3z39 | Pathologically confirmed; best-characterised dark-skin benchmark despite its size |
| **SCIN (2024)** | 25k | 100+ | ~30% dark-skin images | Open (HF/GitHub) | Globally representative, fine-grained taxonomy |
| **Mendeley Skin Disease (2023)** | 3k | 12 | No explicit Fitzpatrick tags (visual: many darker tones) | Open CC-BY (Mendeley) | Quick prototyping with African images |

**Selection for this project**: **PASSION for Dermatology** as primary African dataset (explicit Fitzpatrick enrichment, multi-disease, open academic access), supplemented by HAM10000 (melanoma benchmark), synthetic data (controlled Fitzpatrick balance), and ISIC/Fitzpatrick17k CSVs for metadata alignment.

### 2.3 Concept Bottleneck Models & Explainable AI in Dermatology

| Approach | Key Idea | Dermatology Application |
|----------|----------|------------------------|
| **Concept Bottleneck Models (Koh et al., 2020)** | Predict human-interpretable concepts → final class | MONET (Sawada & Nakamura, 2022): unsupervised concepts; this work: 7 *medically-defined* concepts (ABCD+) |
| **Post-hoc XAI (Grad-CAM, LIME, SHAP)** | Explain black-box predictions | Widely used (Selvaraju et al., 2017; Ribeiro et al., 2016; Lundberg & Lee, 2017); limited by faithfulness |
| **Integrated Gradients (Captum)** | Path-integral attribution from baseline | Axiomatic guarantees; used here for concept attribution heatmaps |
| **Interventional CBM** | Allow clinician to edit concept predictions at inference | Enables "what-if" reasoning; implemented via `get_concepts()` + classifier intervention |

**Gap**: Prior work uses CBMs for *static* interpretability. No system combines CBM with **HITL-RL** where clinician corrections on concept/triage level feed back into model updates.

### 2.4 Fairness & Bias Mitigation in Dermatology AI

| Strategy | Method | Limitation |
|----------|--------|------------|
| **Data augmentation** (dark-skin augment, melanin normalization) | `samplesEquity.py`: LAB equalization, hue/saturation shifts, noise | Training-time only; no operational monitoring |
| **Reweighting / resampling** | WeightedRandomSampler in training | Addresses class imbalance, not deployment drift |
| **Adversarial debiasing** | CIRCLe, Skin-Deep-Unlearning | Complex; requires sensitive attribute labels at training |
| **Fairness-aware RL** (this work) | Dynamic Fitzpatrick multipliers in reward: ×1.0 (I–III), ×2.0 (IV), ×3.0 (V), ×4.0 (VI) | **Novel**: penalty scales at decision time; combined with live fairness tracker |

### 2.5 Clinician-in-the-Loop & Reinforcement Learning in Medical AI

| System | HITL Mechanism | RL Component |
|--------|----------------|--------------|
| Tschandl et al. (2020) | Human–AI collaboration study | None (static model) |
| PanDerm / DermFM-Zero | Foundation models, frozen | None |
| **This work** | Clinician overrides triage → stored in correction buffer → offline PPO update | **PPO with GAE**, clipped surrogate, entropy bonus; state = 7 concepts + 6 Fitz one-hot |

**Key insight**: The triage action space (routine/follow-up/urgent) is discrete and low-dimensional, making it ideal for PPO. The fairness-weighted reward directly addresses the accuracy gap without requiring retraining the vision backbone.

---

## Chapter 3 — Methodology

### 3.1 System Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   INPUT     │────▶│  PREPROCESS  │────▶│  CONCEPT         │────▶│   HITL / RL  │
│  Images +   │     │  Albument-   │     │  BOTTLENECK      │     │   LOOP       │
│  Metadata   │     │  ations +    │     │  HRNet-W18       │     │   PPO Agent  │
│  (HAM/PASS/ │     │  Melanin     │     │  7 concepts →    │     │   Fairness-  │
│   Syn/ISIC) │     │  Normaliz.   │     │  3 classes +     │     │   weighted   │
└─────────────┘     └──────────────┘     │  6 Fitz one-hot  │     │   rewards    │
                                         └────────┬─────────┘     └──────┬───────┘
                                                  │                    │
                                         ┌────────▼────────┐     ┌──────▼───────┐
                                         │ FAIRNESS        │     │ WEB DEPLOY   │
                                         │ MONITOR         │     │ FastAPI +    │
                                         │ datasetEquity   │     │ Gradio +     │
                                         │ metrics_tracker │     │ HTML Dash    │
                                         └────────┬────────┘     └──────┬───────┘
                                                  │                    │
                                                  └────────┬───────────┘
                                                           ▼
                                                ┌────────────────────┐
                                                │ OUTPUTS            │
                                                │ Diagnosis + Concepts│
                                                │ Updated Weights    │
                                                │ Fairness Reports   │
                                                │ Case History Export│
                                                └────────────────────┘
```

### 3.2 Dataset Pipeline

#### 3.2.1 Data Sources & Preprocessing

| Source | Images | Classes | Fitzpatrick | Preprocessing |
|--------|--------|---------|-------------|---------------|
| HAM10000 | ~10k | Binary (melanoma/benign) | Placeholder=3 | `MelaninNormalization` + `dark_skin_aug` |
| PASSION | ~19k | 12 → mapped to 3 | Native I–VI | Same equity-aware pipeline |
| Synthetic | 1,000 | 3 (benign/melanoma/KS) | Controlled I–VI | Generated with concept embeddings |
| ISIC 2019/2020 | Metadata only | — | — | Future: download images |

**Transforms (training)**:
```python
MelaninNormalization()  # LAB L-channel histogram equalization
+ dark_skin_aug transforms (brightness/contrast, hue/sat, compression, noise, rotate, flip)
+ Resize(224,224) + ImageNet Normalize + ToTensorV2
```

**Transforms (validation)**: Resize + ImageNet Normalize + ToTensorV2 only.

#### 3.2.2 Stratified Splits

- HAM10000: 85/15 train/val stratified on original `dx` (melanoma vs. benign), Fitzpatrick placeholder = 3
- PASSION: 80/20 deterministic split (seed=42) preserving class and Fitzpatrick distributions
- Synthetic: Used for PPO case generation (carries real Fitzpatrick labels)

### 3.3 Concept Bottleneck Model (CBM)

#### 3.3.1 Architecture

```python
DermatologyCBM(
    backbone=HRNetFeatureExtractor("hrnet_w18", pretrained=True, features_only=True, out_indices=(0,)),
    concept_bottleneck=ConceptBottleneck(
        in_features=backbone.num_features,  # 270 for HRNet-W18 stage-1 output
        num_concepts=7,
        hidden_dim=in_features // 2
    ),
    classifier=Linear(7, num_classes=3)
)
```

#### 3.3.2 Concept Definitions (Medical Grounding)

| Index | Concept | Clinical Basis | Range |
|-------|---------|----------------|-------|
| 0 | Asymmetry | ABCD criterion A | [0,1] |
| 1 | Border Irregularity | ABCD criterion B | [0,1] |
| 2 | Color Variegation | ABCD criterion C | [0,1] |
| 3 | Diameter Large | ABCD criterion D (>6mm) | [0,1] |
| 4 | Melanin Density | Fitzpatrick proxy; pigment density | [0,1] |
| 5 | Inflammation | Erythema, edema markers | [0,1] |
| 6 | Ulceration | Surface breakdown; high-risk marker | [0,1] |

#### 3.3.3 Training Objective

```
L_total = CE(y, ŷ) + λ_concept · BCE(c, ĉ)   [λ_concept = 0 for frozen-concept training]
```

Current implementation: **Frozen backbone + trainable concept head + classifier** (3 epochs, AdamW lr=1e-3, batch=32).

### 3.4 HITL Reinforcement Learning Pipeline

#### 3.4.1 Environment: `DermTriageEnv`

- **State** (13-dim): `[concept_embedding (7)] + [Fitzpatrick one-hot (6)]`
- **Action** (3): `{0: routine, 1: follow_up, 2: urgent}`
- **Reward**: Fairness-weighted (see 3.4.2)
- **Episode**: Single-step (one case per episode)

#### 3.4.2 Fairness-Weighted Reward Function

```python
TRUE_LABEL_TO_TRIAGE = {0: 0, 1: 2, 2: 2}  # benign→routine, melanoma/KS→urgent
FITZPATRICK_MULTIPLIER = {1: 1.0, 2: 1.0, 3: 1.0, 4: 2.0, 5: 3.0, 6: 4.0}

def fairness_weighted_reward(action, true_label, fitz_type):
    expected = TRUE_LABEL_TO_TRIAGE[true_label]
    mult = FITZPATRICK_MULTIPLIER[fitz_type]
    
    if action == expected:
        return {2: 5.0, 0: 1.0, 1: 2.0}[expected]  # correct
    elif action < expected:  # under-triage
        if expected == 2 and action == 0: return -20.0 * mult  # critical miss
        if expected == 2 and action == 1: return -10.0 * mult  # delayed care
        return -5.0 * mult
    else:  # over-triage
        return -3.0 if expected == 0 else -1.0
```

**Effect**: Critical misses (melanoma/KS → routine) on Fitzpatrick VI incur –80.0 reward vs. –20.0 on Fitzpatrick I–III, forcing the policy to learn higher sensitivity for darker skin.

#### 3.4.3 PPO Agent

- **Network**: Shared MLP (128→128 Tanh) → Actor (3) + Critic (1)
- **GAE**: λ=0.95, γ=0.99
- **Clipped surrogate**: ε=0.2
- **Entropy bonus**: 0.01
- **Updates**: 10 epochs, batch=64, max_grad_norm=0.5
- **Training**: 2000 episodes, update every 64 steps

#### 3.4.4 HITL Workflow (`hitl_pipeline.py`)

1. **Case arrives** → CBM extracts concepts → PPO recommends triage
2. **Clinician reviews** → Accepts or overrides triage
3. **Override logged** → Stored in `correction_buffer` (patient_id, clinician_action)
4. **Offline update** (triggered manually or on buffer ≥ N) → `OfflinePolicyOptimizer` runs PPO update on buffered corrections
5. **Fairness tracker** snapshots metrics pre/post update

### 3.5 Fairness Monitoring (`metrics_tracker.py`, `datasetEquity.py`)

| Metric | Computation | Alert Threshold |
|--------|-------------|-----------------|
| Per-Fitzpatrick triage accuracy | `correct_fitz / total_fitz` | < 70% any group |
| Critical-miss rate (melanoma/KS → not urgent) | `misses_fitz / total_fitz` | Fitz IV–VI > Fitz I–III + 5% |
| Override rate | `overrides / total_cases` | > 20% (model uncertainty) |
| Demographic parity | `P(triage=urgent \| fitz)` | Max pairwise diff > 0.15 |
| Equalized odds | `P(triage=urgent \| label, fitz)` | Max diff across Fitz > 0.10 |

**Dashboard**: Real-time Plotly charts in `dashboard.html`; CSV export via `/api/export`.

### 3.6 Web Deployment Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| REST API | FastAPI + Uvicorn | `/api/diagnose`, `/api/override`, `/api/analytics`, `/api/admin/*` |
| Clinician UI | Gradio 6.x (`ui.py`) | Image upload, concept display, heatmap, triage override |
| Analytics Dashboard | HTML/JS (`dashboard.html`) | Fairness charts, case history, doctor management |
| Authentication | bcrypt + UUID sessions | Role-based (admin/doctor), 8hr TTL |
| Persistence | JSON files (`patients.json`, `doctors.json`, `case_history.json`, `activity.json`) | Zero-DB deployment for low-resource settings |
| Deployment | Render (`render.yaml`) | Free tier compatible; `PORT` env var |

### 3.7 Evaluation Protocol

| Phase | Dataset | Metrics | Comparison |
|-------|---------|---------|------------|
| **Baseline** | HAM10000 20% hold-out | Acc, Prec/Rec/F1 (per-class), AUROC (OvR), Confusion Matrix | Transfer-learning ResNet-50/EfficientNet-B0 |
| **Proposed (CBM)** | HAM10000 20% hold-out | Same + concept extraction fidelity | vs. Baseline |
| **Proposed + PASSION** | PASSION 20% hold-out | Same + per-Fitzpatrick breakdown | vs. CBM without PASSION |
| **Fairness Audit** | Synthetic (Fitz I–VI balanced) | Per-Fitz accuracy, critical-miss rate, demographic parity | Pre vs. post HITL-RL update |
| **HITL Simulation** | Synthetic cases + injected overrides | Policy improvement (reward), override reduction | Pre vs. post offline update |

**Statistical testing**: McNemar's test for paired accuracy comparison; bootstrap CI (95%) for AUROC; χ² for fairness metric differences.

---

## References

[1] Esteva A. et al. (2017). Dermatologist-level classification with deep neural networks. *Nature*, 542, 115–118.  
[2] Tschandl P. et al. (2020). Human–computer collaboration for skin cancer recognition. *Nat. Med.*, 26(8), 1229–1234.  
[3] Daneshjou R. et al. (2022). Disparities in dermatology AI on diverse clinical image set. *Sci. Adv.*, 8(32).  
[4] Sawada Y., Nakamura K. (2022). Concept bottleneck model with additional unsupervised concepts. *IEEE Access*, 10, 41758–41765.  
[5] Koh P.W. et al. (2020). Concept bottleneck models. *ICML*.  
[6] Selvaraju R.R. et al. (2017). Grad-CAM: Visual explanations from deep networks. *ICCV*.  
[7] Ribeiro M.T. et al. (2016). "Why should I trust you?": Explaining the predictions of any classifier. *KDD*.  
[8] Lundberg S.M., Lee S.I. (2017). A unified approach to interpreting model predictions. *NIPS*.  
[9] Wang J. et al. (2020). Deep high-resolution representation learning for visual recognition. *TPAMI*. (HRNet)  
[10] PASSION for Dermatology Consortium (2024). *PASSION: A diverse dermatology dataset for global skin health*. arXiv:2401.xxxxx.  
[11] Roadmap PDF (Sept 2026): *Dermatology AI for Uganda/East Africa* — gap analysis for African data, HITL RL, fairness monitoring, integrated web-first deployment.

---

*End of Project Proposal (Chapters 1–3)*