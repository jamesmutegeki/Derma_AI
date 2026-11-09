# Derma_AI Evidence Atlas

> From a promising prototype to defensible research evidence.

**Project:** Explainable Dermatology AI · CBM + clinician-in-the-loop RL + fairness monitoring  
**Lead:** James Mutegeki · Uganda / East Africa research prototype  
**Status snapshot:** `pre-triage-removal@2d23065`, checked 2026-11-08  
**Training:** Paused / placeholder · **Validated real-data metrics:** 0

> **Research boundary:** Research and educational use only. Not a medical device, not a clinical diagnosis system, and not a basis for treatment decisions. Qualified clinicians must review any real-world use.

**Interactive view:** [open the Evidence Atlas](docs/roadmap/index.html). **Canonical source:** `docs/roadmap/status.json`.

## Snapshot interpretation

Remote repository contents and GitHub check metadata inspected. Local 15/15 PASSION and 11/11 definition-of-done results are reported, not independently reproduced in this audit.

**Evidence-backed checklist:** 2/34 (6%). This measures accepted tasks, not code volume or clinical readiness.

| Status | Count | Meaning |
| --- | ---: | --- |
| Done | 2 | Acceptance criteria met with inspectable evidence |
| Partial | 7 | Implementation exists, but validation or integration is incomplete |
| Reported | 0 | A result was reported, but not independently reproduced here |
| To do | 15 | Defined work not yet completed |
| Blocked | 8 | Requires an external resource, permission, person, or decision |
| Needs repair | 2 | A verified contradiction or broken acceptance contract |

## North star

Test whether concept-based explanations, fairness-aware triage, and reviewed clinician feedback improve reliability and equity over a standard transfer-learning baseline, without pretending the system is clinically validated.

## Evidence gates

| Gate | Status | Rule |
| --- | --- | --- |
| G1 · Reproducibility gate | Needs repair | A clean clone must run the declared tests and readiness checks without copied files; the exact pushed commit must have a green CI run. |
| G2 · Data rights & ethics gate | Blocked | Licences, access terms, de-identification, retention, and IRB/REC determination must be documented before restricted or local patient data are used. |
| G3 · Real KS cohort gate | Blocked | Kaposi sarcoma training requires real, permissioned, clinician-reviewed images. Synthetic images may support smoke tests, not a real-data claim. |
| G4 · Concept supervision gate | Blocked | The seven concepts need agreed definitions, observable labels or an explicit weak-supervision design, and clinician review before concept scores are presented as meaningful. |
| G5 · Evaluation integrity gate | To do | Lock leakage-free splits, evaluate diagnosis and triage separately, report uncertainty and missing strata, and never tune on the test set. |
| G6 · Human-use safety gate | To do | No silent mock diagnosis, honest readiness, reviewed offline updates, rollback, privacy controls, and explicit ethics/stakeholder approval before any real-world pilot. |

## The seven-station route

| Station | Window | Outcome | Progress |
| --- | --- | --- | --- |
| P0 · Basecamp: Restore the truth | Week 1 | The repository, status documents, tests, and CI all describe the same reality. | 2/6 |
| P1 · Data Pass: Rights, cohort, and data contracts | Weeks 1–3 | Every image has a lawful source, a trustworthy label, a split assignment, and a documented role. | 0/5 |
| P2 · Concept Ridge: Make explanations meaningful | Weeks 2–4 | The seven bottleneck outputs correspond to defined, reviewable visual evidence rather than arbitrary hidden units. | 0/4 |
| P3 · Training Ascent: Run reproducible learning | Weeks 4–6 after gates | A baseline, CBM candidate, and triage policy are trained from documented real data with reproducible artifacts. | 0/5 |
| P4 · Evaluation Observatory: Measure what matters | Weeks 6–8 | A sealed-test report answers the research question with uncertainty, subgroup detail, and negative results preserved. | 0/5 |
| P5 · Clinical Review Camp: Make the human loop safe | Weeks 7–9 | A research dashboard can be reviewed safely, with honest fallbacks, traceable feedback, and no autonomous clinical use. | 0/5 |
| P6 · Research Summit: Package evidence and decide | Weeks 9–10 | A reproducible academic package states what worked, what failed, and what is still not safe to claim. | 0/4 |

Windows are indicative. External data, ethics, annotation, and stakeholder gates can extend the schedule.

## Next moves

1. **P0.1 — Repair the fresh-clone acceptance contract** (Needs repair): Reconcile definition_of_done.sh with the actual persistence design: storage.py and scripts/backup_db.py are missing.
2. **P1.2 — Build and audit a real Kaposi sarcoma cohort** (Blocked): Request Fitzpatrick17k images and audit its 156 KS-labelled candidates for diagnosis, image quality, provenance, and skin-tone metadata.
3. **P1.3 — Obtain ethics and governance decisions** (Blocked): Ask the institution whether each public dataset and any local collection requires approval, exemption, or a data agreement.
4. **P0.2 — Restore CI on the exact remote commit** (Blocked): Recover the workflow from commit 9f3d6bf and adapt it to the repaired full test contract.

## Detailed roadmap

### P0 · Basecamp — Restore the truth

**Window:** Week 1 · **Status:** Needs repair · **Progress:** 2/6 · **Depends on:** Entry station

**Outcome:** The repository, status documents, tests, and CI all describe the same reality.

*Why this station matters:* A polished demo is not progress if a fresh clone cannot reproduce the claimed checks.

- [x] **P0.0 — Inventory the existing prototype** · `Done` · P0 · Project lead · effort S

  **How:**
  1. Keep the existing CBM, PPO, HITL, fairness tracker, API, and dashboard modules as the prototype inventory.
  2. Treat code presence as implementation evidence, not proof of clinical or runtime validity.

  **Done when:**
  - [x] Each major component maps to a source file and a later validation task.

  **Evidence on record:**
  - model.py, rl_module.py, hitl_pipeline.py, metrics_tracker.py, server.py, dashboard.html exist at 2d23065.

  **Artifacts:** `dermatology-ai/model.py`; `dermatology-ai/rl_module.py`; `dermatology-ai/hitl_pipeline.py`

- [ ] **P0.1 — Repair the fresh-clone acceptance contract** · `Needs repair` · P0 · Backend + ML engineer · effort L

  **How:**
  1. Reconcile definition_of_done.sh with the actual persistence design: storage.py and scripts/backup_db.py are missing.
  2. Align create_app(initialise_backend=False) and /api/ready with the server, or revise the contract explicitly; do not fake readiness.
  3. Run the full declared pytest suite from a new clone with no copied untracked files.

  **Done when:**
  - [ ] Every check exercises a tracked implementation.
  - [ ] A clean clone passes without manual file copying.
  - [ ] Readiness is false with a reason when no validated checkpoint is loaded.

  **Evidence on record:**
  - storage.py, scripts/backup_db.py, and /api/ready are absent at the snapshot; create_app() takes no initialise_backend argument.

  **Artifacts:** `dermatology-ai/scripts/definition_of_done.sh`; `dermatology-ai/server.py`

- [ ] **P0.2 — Restore CI on the exact remote commit** · `Blocked` · P0 · Repository maintainer · effort M

  **How:**
  1. Recover the workflow from commit 9f3d6bf and adapt it to the repaired full test contract.
  2. Publish through an authorized GitHub connection or the repository web interface; never place tokens in source or chat.
  3. Inspect the Actions run for the resulting SHA, not an older commit.

  **Done when:**
  - [ ] .github/workflows/ci.yml exists at remote HEAD.
  - [ ] The exact HEAD has a successful CI run covering lint, tests, acceptance checks, and documentation links.

  **Evidence on record:**
  - No workflow exists at 2d23065; GitHub returned zero check runs for that commit.

  **Artifacts:** `.github/workflows/ci.yml`

- [ ] **P0.3 — Restore missing evidence documents** · `To do` · P1 · Project lead · effort M

  **How:**
  1. Create or correctly link TRAINING.md, GATE_OPTIONS.md, IRB_EXEMPTION_REQUEST.md, and both dataset cards.
  2. Record only decisions actually made; do not recreate a signed freeze or retention policy from a stale summary.

  **Done when:**
  - [ ] All status-document links resolve in a fresh clone.
  - [ ] Each claimed approval has a real approving body, date, and evidence reference.

  **Evidence on record:**
  - The five referenced training/governance/dataset-card files are missing at 2d23065.

  **Artifacts:** `dermatology-ai/docs/TRAINING.md`; `dermatology-ai/docs/GATE_OPTIONS.md`; `dermatology-ai/docs/IRB_EXEMPTION_REQUEST.md`

- [x] **P0.4 — Preserve research-only framing and document navigation** · `Done` · P0 · Project lead · effort S

  **How:**
  1. Keep the disclaimer in the model card and dashboard.
  2. Keep README links to the model card, security policy, operations runbook, and remediation status.

  **Done when:**
  - [x] Disclaimers and links are present in the pushed tree.

  **Evidence on record:**
  - MODEL_CARD.md and dashboard.html contain the research-only disclaimer; README links were verified at 2d23065.

  **Artifacts:** `README.md`; `dermatology-ai/MODEL_CARD.md`; `dermatology-ai/dashboard.html`

- [ ] **P0.5 — Correct stale research claims** · `To do` · P1 · Research lead · effort M

  **How:**
  1. Replace legacy PASSION claims of roughly 19k images/12 classes with the verified release scope and local-subset distinction.
  2. Remove unsupported first-of-kind, deployment-ready, and clinical-adoption claims unless independently supported.
  3. Align proposal, model card, dataset cards, and poster with the evidence ledger.

  **Done when:**
  - [ ] No active document presents placeholder or synthetic results as validated performance.
  - [ ] Dataset counts and roles are consistent across documents.

  **Evidence on record:**
  - Legacy proposal and Project_Explained documents contain dataset counts and novelty claims not supported by the current evidence.

  **Artifacts:** `docs/proposal/project_proposal.md`; `docs/Project_Explained.md`; `dermatology-ai/MODEL_CARD.md`

### P1 · Data Pass — Rights, cohort, and data contracts

**Window:** Weeks 1–3 · **Status:** Blocked · **Progress:** 0/5 · **Depends on:** P0.1

**Outcome:** Every image has a lawful source, a trustworthy label, a split assignment, and a documented role.

*Why this station matters:* More images do not fix wrong labels, leakage, or a missing Kaposi sarcoma cohort.

- [ ] **P1.1 — Secure dataset access and licence register** · `Partial` · P0 · Research lead · effort M

  **How:**
  1. Obtain HAM10000 from its official record, request PASSION and Fitzpatrick17k images through their access routes, and download SKINCON annotations.
  2. Record licence, access date, permitted storage, redistribution limits, and citation for each source.
  3. Keep raw images and restricted data out of Git.

  **Done when:**
  - [ ] A data register lists source, version/hash, permission, local path, and allowed compute location.
  - [ ] PASSION is marked external fairness evaluation only.

  **Evidence on record:**
  - PASSION downloader still contains a placeholder URL; reconciliation reports a 4,016-image local subset, not the full release.

  **Artifacts:** `dermatology-ai/docs/DATA_REGISTER.md`; `dermatology-ai/DATASET_CARD_PASSION.md`

- [ ] **P1.2 — Build and audit a real Kaposi sarcoma cohort** · `Blocked` · P0 · Dermatologist + research lead · effort L

  **How:**
  1. Request Fitzpatrick17k images and audit its 156 KS-labelled candidates for diagnosis, image quality, provenance, and skin-tone metadata.
  2. Plan a Uganda-specific cohort through the supervisor and UCI/Mbarara collaborators after ethics/data agreements.
  3. Record inclusion/exclusion decisions and label confidence; do not equate an atlas label with biopsy confirmation.

  **Done when:**
  - [ ] A permissioned real-image KS manifest exists with reviewed labels and patient/lesion grouping.
  - [ ] Train/validation/test counts and missing metadata are reported honestly.
  - [ ] The cohort is sufficient for the pre-specified research question or the scope is formally reduced.

  **Evidence on record:**
  - Fitzpatrick17k public metadata contains 156 rows labelled kaposi sarcoma; images require access and clinical audit.

  **Artifacts:** `dermatology-ai/docs/KS_COHORT.md`; `data manifests outside Git`

- [ ] **P1.3 — Obtain ethics and governance decisions** · `Blocked` · P0 · Supervisor + IRB/REC · effort L

  **How:**
  1. Ask the institution whether each public dataset and any local collection requires approval, exemption, or a data agreement.
  2. Define consent/waiver, de-identification, access control, retention, deletion, and incident response.
  3. Do not collect local patient images or run a clinician-participant study before the required determination.

  **Done when:**
  - [ ] Written determinations and agreements are referenced without exposing sensitive personal data.
  - [ ] The approved use matches the actual training/evaluation plan.

  **Evidence on record:**
  - IRB exemption remains pending in the project status; the referenced request file is absent from the pushed tree.

  **Artifacts:** `dermatology-ai/docs/IRB_EXEMPTION_REQUEST.md`; `dermatology-ai/docs/DATA_GOVERNANCE.md`

- [ ] **P1.4 — Lock leakage-free splits and label semantics** · `To do` · P0 · ML engineer · effort L

  **How:**
  1. Group by patient or lesion before splitting; lock train/validation/test assignments and hashes.
  2. Correct HAM10000 mappings so BCC/AKIEC are not silently labelled benign; document exclusions or a revised taxonomy.
  3. Keep PASSION out of three-class training and treat dermoscopic versus clinical photographs as a domain-shift variable.

  **Done when:**
  - [ ] Automated tests prove zero group overlap across splits.
  - [ ] Every training row has a valid class and source; unknown skin tone is unknown, not a fabricated type 3.
  - [ ] The test split is sealed until candidate selection is complete.

  **Evidence on record:**
  - The notebook still maps non-melanoma HAM classes to benign and can combine PASSION into training.

  **Artifacts:** `dermatology-ai/notebooks/01_train_cbm.py`; `split manifests`

- [ ] **P1.5 — Prepare compute, storage, and environment** · `To do` · P1 · ML engineer · effort M

  **How:**
  1. Pin the Python/PyTorch environment and record hardware, seeds, and package versions.
  2. Use permitted cloud GPU data only; keep restricted PASSION/local data on approved storage.
  3. Reserve space for datasets, checkpoints, logs, and backups outside Git.

  **Done when:**
  - [ ] A new environment reproduces the smoke run.
  - [ ] Checkpoint and report storage paths are configured and backed up.

  **Evidence on record:**
  - Requirements are lower-bounded rather than locked; the notebook hardcodes CPU and legacy local paths.

  **Artifacts:** `requirements lock`; `dermatology-ai/docs/TRAINING.md`

### P2 · Concept Ridge — Make explanations meaningful

**Window:** Weeks 2–4 · **Status:** Blocked · **Progress:** 0/4 · **Depends on:** P1.1, P1.3

**Outcome:** The seven bottleneck outputs correspond to defined, reviewable visual evidence rather than arbitrary hidden units.

*Why this station matters:* A layer named concept is not interpretable merely because it has seven outputs.

- [ ] **P2.1 — Agree the concept dictionary** · `To do` · P0 · Dermatologist + research lead · effort M

  **How:**
  1. Define each concept, positive/negative examples, visibility rules, and whether it is observable without scale or patient history.
  2. Review diameter_large and melanin_density carefully; do not treat image pigment as a validated Fitzpatrick label.

  **Done when:**
  - [ ] A clinician-reviewed dictionary exists.
  - [ ] Unobservable concepts are removed, reframed, or explicitly marked as limitations.

  **Evidence on record:**
  - The model defines seven names, but the current training loss supervises class labels only.

  **Artifacts:** `dermatology-ai/docs/CONCEPT_DICTIONARY.md`

- [ ] **P2.2 — Acquire concept supervision** · `Blocked` · P0 · Dermatologist annotators · effort L

  **How:**
  1. Map SKINCON annotations only where definitions genuinely match; ulcer and erythema are candidates, not automatic equivalents.
  2. Have clinicians label missing concepts and resolve disagreements on a double-annotated subset.
  3. Keep missing labels masked rather than converting them to negative labels.

  **Done when:**
  - [ ] Annotation coverage and inter-rater agreement are reported per concept.
  - [ ] The training manifest distinguishes expert labels, mapped labels, and weak labels.

  **Evidence on record:**
  - SKINCON provides 48 expert clinical concepts, not the exact seven used by this project.

  **Artifacts:** `concept annotation manifest`; `dermatology-ai/docs/CONCEPT_DICTIONARY.md`

- [ ] **P2.3 — Implement and test concept supervision** · `To do` · P0 · ML engineer · effort L

  **How:**
  1. Add masked concept loss and a documented joint or sequential training strategy.
  2. Compare class-only and concept-supervised variants under identical splits.
  3. Test concept intervention through the classifier without leaking class labels into concept targets.

  **Done when:**
  - [ ] Unit tests cover missing labels, loss masking, and intervention behavior.
  - [ ] Ablation results show whether concept supervision helps or harms.

  **Evidence on record:**
  - No concept-loss implementation was found in the current Python training path.

  **Artifacts:** `dermatology-ai/model.py`; `dermatology-ai/notebooks/01_train_cbm.py`; `concept tests`

- [ ] **P2.4 — Validate explanation faithfulness** · `Partial` · P1 · ML engineer + clinician · effort M

  **How:**
  1. Use deterministic inference preprocessing and document any normalization boundary.
  2. Run attribution sanity checks and clinician review of concept/heatmap agreement.
  3. Report explanations as model evidence, not clinical justification.

  **Done when:**
  - [ ] Repeated inference is deterministic for a fixed checkpoint.
  - [ ] Explanation checks and failure examples are recorded.

  **Evidence on record:**
  - Grad-CAM and Integrated Gradients code exists; faithfulness and clinical agreement have not been validated.

  **Artifacts:** `dermatology-ai/model.py`; `explanation evaluation report`

### P3 · Training Ascent — Run reproducible learning

**Window:** Weeks 4–6 after gates · **Status:** Blocked · **Progress:** 0/5 · **Depends on:** P0.1, P1.2, P1.3, P1.4, P2.1, P2.2

**Outcome:** A baseline, CBM candidate, and triage policy are trained from documented real data with reproducible artifacts.

*Why this station matters:* Training is not done when a loop finishes; it is done when the run can be trusted and repeated.

- [ ] **P3.1 — Repair the training entry point** · `Partial` · P0 · ML engineer · effort M

  **How:**
  1. Replace hardcoded paths with configuration, add the real KS source resolver, and select CPU/GPU explicitly.
  2. Prevent PASSION evaluation data and synthetic KS from entering a real-data training claim.
  3. Run a tiny smoke batch before any long run.

  **Done when:**
  - [ ] The smoke run works from a clean environment.
  - [ ] The resolved manifest contains only permitted training sources.

  **Evidence on record:**
  - MultiSourceDermDataset has no Kaposi cohort source and the notebook retains legacy path/domain assumptions.

  **Artifacts:** `dermatology-ai/notebooks/01_train_cbm.py`; `dermatology-ai/datasetEquity.py`

- [ ] **P3.2 — Train the standard baseline** · `To do` · P1 · ML engineer · effort M

  **How:**
  1. Train a standard transfer-learning classifier on the same locked splits and preprocessing budget.
  2. Select hyperparameters using validation data only and save the run configuration.

  **Done when:**
  - [ ] A baseline checkpoint and validation report exist.
  - [ ] The comparison protocol is fixed before viewing test results.

  **Evidence on record:**
  - No validated baseline run is recorded.

  **Artifacts:** `baseline run directory outside Git`

- [ ] **P3.3 — Train the concept-supervised CBM** · `Blocked` · P0 · ML engineer · effort L

  **How:**
  1. Train on the audited real cohort with masked concept supervision and class imbalance handling.
  2. Track validation performance, calibration, concept coverage, and subgroup counts; use early stopping.
  3. Save candidate checkpoints externally with data/config/code hashes.

  **Done when:**
  - [ ] A candidate checkpoint is reproducible from the recorded run.
  - [ ] No test-set tuning occurs.
  - [ ] Synthetic-only KS is not reported as real-data performance.

  **Evidence on record:**
  - model_manifest.json remains placeholder with checkpoint sha256 null.

  **Artifacts:** `candidate checkpoint`; `run config`; `training log`

- [ ] **P3.4 — Train and justify the triage policy** · `To do` · P1 · ML + clinician · effort L

  **How:**
  1. Have clinicians approve the diagnosis-to-lane mapping and reward trade-offs before training.
  2. Compare a simple rule baseline, contextual-bandit formulation, and PPO on the same offline cases.
  3. Run reward-weight ablations and inspect over-triage as well as critical misses.

  **Done when:**
  - [ ] The policy beats or honestly fails against simpler baselines under the pre-specified protocol.
  - [ ] Reward choices have clinical rationale and recorded review.

  **Evidence on record:**
  - The environment is a single-step decision problem; PPO novelty/benefit is not yet demonstrated.

  **Artifacts:** `dermatology-ai/rl_module.py`; `triage evaluation report`

- [ ] **P3.5 — Freeze a candidate, not a claim** · `Blocked` · P0 · Project lead · effort S

  **How:**
  1. Align checkpoint paths across notebook, server, manifest, and operations docs.
  2. Record SHA-256, code commit, data versions, seed, environment, and selection rule.
  3. Update the model card with actual limitations and validation results only.

  **Done when:**
  - [ ] The manifest validates against the real artifact.
  - [ ] The server loads the intended candidate and reports readiness honestly.

  **Evidence on record:**
  - Manifest points to models/best_model.pth while the notebook saves model_checkpoints/cbm_3class.pt.

  **Artifacts:** `dermatology-ai/model_manifest.json`; `dermatology-ai/MODEL_CARD.md`

### P4 · Evaluation Observatory — Measure what matters

**Window:** Weeks 6–8 · **Status:** To do · **Progress:** 0/5 · **Depends on:** P3.2, P3.3, P3.4, P1.4

**Outcome:** A sealed-test report answers the research question with uncertainty, subgroup detail, and negative results preserved.

*Why this station matters:* Accuracy alone can hide critical misses, calibration failures, and unequal performance.

- [ ] **P4.1 — Evaluate diagnosis on sealed real test data** · `To do` · P0 · ML engineer · effort M

  **How:**
  1. Report per-class sensitivity/specificity, balanced accuracy, AUROC/AUPRC where valid, calibration, and confidence intervals.
  2. State sample sizes and undefined metrics instead of filling zeros.
  3. Evaluate each frozen candidate once under the locked protocol.

  **Done when:**
  - [ ] A machine-readable report and human-readable summary are saved with the checkpoint hash.
  - [ ] No metrics are invented or copied from unrelated benchmarks.

  **Evidence on record:**
  - No validated real-data metrics exist.

  **Artifacts:** `evaluation report`; `predictions manifest`

- [ ] **P4.2 — Audit fairness with uncertainty** · `To do` · P0 · ML + clinician · effort L

  **How:**
  1. Report triage TPR/FNR and gaps by verified skin-tone group with counts and confidence intervals.
  2. Pre-specify acceptable trade-offs with clinicians; do not invent passing thresholds after seeing results.
  3. Explain why demographic parity may be inappropriate when disease prevalence differs.

  **Done when:**
  - [ ] Small/missing strata are flagged.
  - [ ] Reward weighting is compared with an unweighted baseline.
  - [ ] Conclusions distinguish observed gaps from statistical certainty.

  **Evidence on record:**
  - Fairness code exists, but no real evaluation output is recorded.

  **Artifacts:** `fairness report`; `dermatology-ai/metrics_tracker.py`

- [ ] **P4.3 — Repair and run external PASSION monitoring** · `Partial` · P0 · ML engineer · effort M

  **How:**
  1. Use the actual triage policy for lanes; do not treat diagnosis class index 2 as the urgent lane.
  2. Aggregate by subject, preserve original conditions, clean temporary files, and use deterministic preprocessing.
  3. Report escalation distributions only, not diagnostic accuracy against unrelated inflammatory labels.

  **Done when:**
  - [ ] The evaluator consumes the frozen CBM and triage artifacts.
  - [ ] Subject-level outputs reconcile to the local subset manifest.
  - [ ] The report states subset and missing-Fitzpatrick limitations.

  **Evidence on record:**
  - PASSION helpers and 15 tests are tracked/reportedly passing; the evaluation script still conflates class predictions with triage lanes.

  **Artifacts:** `run_evaluation_passion.py`; `dermatology-ai/scripts/passion_metrics.py`

- [ ] **P4.4 — Evaluate concepts and explanations** · `To do` · P1 · Clinician + ML engineer · effort M

  **How:**
  1. Measure concept agreement on held-out expert labels and the effect of correct concept interventions.
  2. Run attribution sanity checks and collect structured clinician ratings on a blinded sample.
  3. Report disagreement and unobservable concepts.

  **Done when:**
  - [ ] Concept utility is compared with the class-only baseline.
  - [ ] Explanation claims are bounded by the measured evidence.

  **Evidence on record:**
  - No concept-consistency or clinician explanation-agreement results are recorded.

  **Artifacts:** `concept evaluation report`

- [ ] **P4.5 — Run the research ablations** · `To do` · P1 · Research lead · effort L

  **How:**
  1. Compare baseline, CBM, CBM plus fairness-weighted triage, and reviewed offline feedback under matched conditions.
  2. Simulate low-label and low-bandwidth constraints explicitly rather than assuming them.
  3. Use repeated seeds or appropriate uncertainty estimates and preserve negative results.

  **Done when:**
  - [ ] Each claimed contribution has a comparison or is downgraded to future work.
  - [ ] The report separates simulated HITL evidence from real clinician evidence.

  **Evidence on record:**
  - The proposal claims low-label/low-bandwidth and HITL benefits without completed comparisons.

  **Artifacts:** `ablation matrix`; `research results report`

### P5 · Clinical Review Camp — Make the human loop safe

**Window:** Weeks 7–9 · **Status:** Partial · **Progress:** 0/5 · **Depends on:** P0.1, P3.5

**Outcome:** A research dashboard can be reviewed safely, with honest fallbacks, traceable feedback, and no autonomous clinical use.

*Why this station matters:* A clinician button does not make an unvalidated update safe.

- [ ] **P5.1 — Make backend readiness and fallbacks honest** · `Needs repair` · P0 · Backend engineer · effort M

  **How:**
  1. Remove silent fixed-payload diagnosis from the authenticated inference path; return an explicit unavailable state.
  2. Load only the declared checkpoint and expose /api/ready with model/data provenance.
  3. Keep demo payloads in a clearly labelled demo route or fixture.

  **Done when:**
  - [ ] No random/pretrained-only model is presented as trained.
  - [ ] Unavailable backend never returns a plausible fabricated diagnosis.
  - [ ] Contract tests cover ready, unauthenticated, and unavailable states.

  **Evidence on record:**
  - _fallback_diagnosis returns a fixed melanoma/follow-up payload; /api/ready is absent at the snapshot.

  **Artifacts:** `dermatology-ai/server.py`; `API contract tests`

- [ ] **P5.2 — Validate offline HITL updates** · `Partial` · P0 · ML + clinician · effort L

  **How:**
  1. Audit PPO importance ratios, stored log-probabilities, reward ground truth, and selection bias from overrides-only data.
  2. Require reviewed corrections, versioned updates, shadow evaluation, and rollback before activation.
  3. Keep concept corrections distinct from diagnosis and triage corrections.

  **Done when:**
  - [ ] Update tests prove old/new policy quantities are handled correctly.
  - [ ] A bad update can be rejected or rolled back.
  - [ ] No live patient-driven learning occurs without approval.

  **Evidence on record:**
  - HITL buffer and optimizer exist; the offline path recomputes log-probabilities with the current network and lacks a validated promotion gate.

  **Artifacts:** `dermatology-ai/hitl_pipeline.py`; `HITL validation report`

- [ ] **P5.3 — Run a synthetic clinician review session** · `To do` · P1 · Research lead + clinician · effort M

  **How:**
  1. Use clearly labelled synthetic cases and a written session script.
  2. Measure agreement, override reasons, review time, and explanation usefulness.
  3. Obtain any required ethics determination for human participants before recruitment.

  **Done when:**
  - [ ] Session notes and structured results are saved without patient data.
  - [ ] Findings feed a prioritized UI/HITL change list.

  **Evidence on record:**
  - No completed clinician review session is recorded.

  **Artifacts:** `usability protocol`; `session report`

- [ ] **P5.4 — Verify privacy, security, and recovery** · `Partial` · P0 · Backend engineer · effort L

  **How:**
  1. Test authentication, CSRF, rate limits, upload validation, access control, audit logs, and PII protection.
  2. Implement and test the actual backup/restore path used by the app.
  3. Never log raw images or secrets; define retention and deletion drills.

  **Done when:**
  - [ ] Security and restore tests pass in CI.
  - [ ] The runbook matches the implemented storage system.
  - [ ] Sensitive runtime data remain outside Git.

  **Evidence on record:**
  - Several hardening changes exist, but the declared SQLite backup modules are missing and full integration coverage is unverified.

  **Artifacts:** `dermatology-ai/SECURITY.md`; `dermatology-ai/docs/OPERATIONS.md`; `integration tests`

- [ ] **P5.5 — Deploy a bounded research demo** · `To do` · P2 · Backend + frontend · effort M

  **How:**
  1. Deploy with research-only banner, explicit model status, restricted access, health/readiness telemetry, and synthetic/demo separation.
  2. Use relative browser URLs and approved environment configuration.
  3. Keep real inference disabled until the safety and ethics gates pass.

  **Done when:**
  - [ ] A reviewer can exercise the intended workflow without mistaking demo output for diagnosis.
  - [ ] Logs and rollback steps are documented.

  **Evidence on record:**
  - Deployment configuration exists, but a verified safe research deployment is not recorded.

  **Artifacts:** `dermatology-ai/render.yaml`; `deployment checklist`

### P6 · Research Summit — Package evidence and decide

**Window:** Weeks 9–10 · **Status:** To do · **Progress:** 0/4 · **Depends on:** P4.1, P4.2, P4.3, P4.5, P5.3

**Outcome:** A reproducible academic package states what worked, what failed, and what is still not safe to claim.

*Why this station matters:* The finish line is defensible evidence, not a green badge or a polished poster alone.

- [ ] **P6.1 — Write the evidence-led results report** · `To do` · P0 · Research lead · effort L

  **How:**
  1. Structure around research questions, methods, sealed-test results, fairness, ablations, limitations, and negative findings.
  2. Link every number to a run, checkpoint, data version, and script.
  3. Keep clinical validation and regulatory clearance out of claims.

  **Done when:**
  - [ ] A reviewer can trace every result to evidence.
  - [ ] Unsupported novelty/performance statements are removed.

  **Evidence on record:**
  - No validated results report exists.

  **Artifacts:** `docs/reports/`; `dermatology-ai/MODEL_CARD.md`

- [ ] **P6.2 — Package poster, demo, and reproduction guide** · `Partial` · P1 · Project lead · effort M

  **How:**
  1. Update poster/slides from the final report, not legacy placeholders.
  2. Provide one-command environment/test/evaluation instructions and artifact hashes.
  3. Include a failure/limitations panel in the poster and demo.

  **Done when:**
  - [ ] A fresh reviewer reproduces the headline table and demo walkthrough.
  - [ ] All document links resolve.

  **Evidence on record:**
  - Poster, slides, and report scaffolds exist; final evidence is absent.

  **Artifacts:** `dermatology-ai/poster.html`; `dermatology-ai/slides.html`; `README.md`

- [ ] **P6.3 — Hold supervisor and stakeholder review** · `Blocked` · P1 · Supervisor + UCI/Mbarara reviewers · effort M

  **How:**
  1. Present the evidence package, limitations, and safety boundary.
  2. Record requested changes and whether the academic prototype is accepted.
  3. Do not treat prototype acceptance as pilot authorization.

  **Done when:**
  - [ ] Written review notes and next-step decision exist.
  - [ ] Open safety/ethics issues have named owners.

  **Evidence on record:**
  - Stakeholder alignment remains an external dependency in the project roadmap.

  **Artifacts:** `stakeholder review notes`

- [ ] **P6.4 — Make a separate pilot decision** · `Blocked` · P2 · Institution + clinical partners · effort L

  **How:**
  1. Require a separate protocol, ethics/regulatory review, monitoring plan, stop rules, training, and incident response.
  2. Use shadow mode before any influence on care.
  3. Keep this outside the current academic completion claim unless separately approved.

  **Done when:**
  - [ ] All institutional requirements are satisfied in writing.
  - [ ] The system remains research-only until that decision explicitly changes scope.

  **Evidence on record:**
  - No pilot approval or clinical validation is recorded.

  **Artifacts:** `future pilot protocol`

## Full project explanation

### 1. What this project is

Derma_AI is a research prototype for explainable, equity-aware dermatology triage in Uganda/East Africa. It combines a concept-bottleneck image classifier, a small reinforcement-learning triage policy, clinician feedback, fairness monitoring, and a web dashboard.

The research question is comparative: do concept supervision, fairness-weighted triage, and reviewed offline feedback improve reliability and equity over a standard transfer-learning baseline under constrained labels and bandwidth? The project is not currently a validated diagnostic product.

- Target conditions in code: benign, melanoma, and Kaposi sarcoma.
- Target triage actions in code: routine, follow-up, and urgent.
- Planned clinical context: Uganda Cancer Institute and Mbarara Hospital, subject to real agreements and approvals.
- Current boundary: research/education only; no autonomous diagnosis or treatment decision.

### 2. End-to-end pipeline

An image and metadata enter a deterministic preprocessing path. HRNet-W18 extracts visual features; a seven-output bottleneck is intended to represent clinical concepts; a linear head maps those concepts to three diagnosis classes. A separate PPO-style policy receives seven concept scores plus a six-value Fitzpatrick encoding and chooses one of three triage actions.

A clinician can review the output and submit a correction. Corrections enter an offline buffer; a candidate policy update must be evaluated and approved before promotion. The dashboard and fairness tracker record outcomes, overrides, subgroup counts, and audit information. Heatmaps are supporting model evidence, not clinical proof.

- Input → quality/permission checks → preprocessing → HRNet features.
- Features → seven concept scores → three class logits.
- Concepts + skin-tone encoding → triage policy → proposed lane.
- Clinician review → correction buffer → offline candidate update → validation → promote or rollback.
- Cases and predictions → fairness/uncertainty reports → research dashboard and export.

### 3. What each part owns

The codebase already contains the main scaffolding. The roadmap distinguishes a file existing from the behavior being validated.

| Component | Files | Responsibility | Current boundary |
| --- | --- | --- | --- |
| Vision + concepts | model.py | HRNet-W18, seven concept outputs, three-class head, Grad-CAM/Integrated Gradients | Concept supervision and explanation faithfulness unvalidated |
| Data pipeline | datasetEquity.py, samplesEquity.py, notebooks/01_train_cbm.py | Load images, transforms, splits, training entry point | Label mapping, source resolution, paths, and leakage controls need repair |
| Triage policy | rl_module.py | Single-step environment, fairness-weighted reward, PPO actor-critic | Must be compared with simpler rule/bandit baselines |
| Human feedback | hitl_pipeline.py | Override buffer and offline optimizer | Update validity, selection bias, review, and rollback unproven |
| Fairness monitor | metrics_tracker.py, scripts/passion_metrics.py | Subgroup metrics, overrides, PASSION escalation summaries | No real-data outputs; empty-stratum and uncertainty handling need audit |
| Application | server.py, dashboard.html, ui.py | API, dashboard, authentication, review workflow | Readiness/fallback contract and full integration tests incomplete |
| Governance | MODEL_CARD.md, SECURITY.md, docs/OPERATIONS.md | Scope, limitations, security and operations | Several referenced evidence files are missing |

### 4. Data strategy that matches the labels

The datasets cannot be blended as though they describe the same task. HAM10000 is dermoscopic and has no real Kaposi sarcoma class. PASSION contains inflammatory/infectious conditions and is used here as an external fairness/escalation cohort, not as benign/melanoma/KS ground truth. Fitzpatrick17k is a possible source of real KS-labelled candidates, but access and clinician audit are required. SKINCON can supply some expert concept annotations, not a complete match for the seven project concepts.

| Source | Role | Key caution |
| --- | --- | --- |
| HAM10000 | Lesion classification source after explicit label correction | Do not map BCC/AKIEC to benign; no native Fitzpatrick ground truth |
| Fitzpatrick17k | Candidate real KS and skin-tone-labelled clinical images | 156 KS-labelled metadata rows are candidates, not an approved cohort |
| PASSION | External subject-level escalation/fairness monitoring | Local subset is 4,016 images; conditions do not match the three diagnosis classes |
| SKINCON | Partial expert concept supervision | Map definitions carefully; annotate missing concepts |
| Synthetic cases | Smoke tests, UI demos, controlled RL experiments | Never substitute for real KS validation |
| Uganda cohort | Future local relevance and external validation | Requires ethics, agreements, de-identification, and clinician labels |

### 5. What counts as evidence

Use a locked, group-aware train/validation/test design. Select models on validation data, then evaluate frozen candidates on sealed test data. Compare a standard classifier, a concept-supervised CBM, fairness-weighted triage, and reviewed feedback under matched conditions. Report uncertainty and subgroup counts; preserve negative results.

- Diagnosis: per-class sensitivity/specificity, balanced accuracy, discrimination where valid, calibration, confidence intervals.
- Triage: critical-miss rate, over-triage, lane agreement, and clinician-reviewed outcomes.
- Fairness: subgroup TPR/FNR gaps with counts and uncertainty; pre-specified trade-offs rather than post-hoc thresholds.
- Concepts: expert agreement, intervention effect, and attribution sanity checks.
- Human loop: override reasons, review time, update rejection/rollback, and simulated versus real feedback distinction.
- PASSION: predicted escalation distributions by subject/condition/skin tone only; not diagnostic accuracy.

### 6. Decisions that protect the research

These are design risks, not reasons to abandon the project. They determine whether the final claims are credible.

- Domain shift: dermoscopic HAM images and clinical atlas/phone photographs are not interchangeable.
- Concept observability: diameter needs scale; pigment intensity is not a validated Fitzpatrick diagnosis.
- Single-step RL: the current environment is closer to a contextual bandit; PPO must earn its complexity through comparison.
- Override-only feedback is selected data; clinician action is not automatically pathology ground truth.
- Skin-tone multipliers encode a value judgment and require clinician review plus over-triage analysis.
- Fallback diagnosis is a safety hazard even if renamed from mock to fallback.
- Small KS samples may support a feasibility study, not a broad clinical performance claim.
- IRB exemption, data licence, and stakeholder interest are three different permissions.

### 7. Four different meanings of done

Use separate finish lines so a UI milestone cannot masquerade as training or clinical readiness.

| Level | Finish line | Current state |
| --- | --- | --- |
| Code complete | Declared contracts work in a clean clone and exact-head CI | Blocked by acceptance/CI gaps |
| Training complete | Reproducible real-data candidate, hash, config, and validation report | Not done; placeholder |
| Research complete | Sealed-test comparisons, fairness, ablations, limitations, and review | Not done; no validated metrics |
| Pilot ready | Separate ethics/regulatory approval, safety case, monitoring, and stop rules | Out of current scope |

### 8. How to keep the roadmap alive

Use the dashboard for exploration and the JSON file for versioned truth. A task is done only when its acceptance criteria have evidence. Browser edits are local drafts until exported, reviewed, and committed.

- Daily: update the one task you moved; add a commit, run ID, report path, or decision reference.
- Weekly: review blockers, choose the next three moves, and rebuild the dashboard/Markdown from JSON.
- At a gate: attach the evidence, name the reviewer, and record the decision; do not convert blocked to done by optimism.
- When a result changes scope: add a changelog entry and update dependent tasks rather than silently rewriting history.
- Never store patient data, secrets, raw restricted images, or access tokens in the tracker.

## Resource map

| Resource | Role | Source | Caution |
| --- | --- | --- | --- |
| HAM10000 | Lesion classification source | [HAM10000](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/DBW86T) | Follow the official terms; correct label semantics before training. |
| Fitzpatrick17k | Real KS candidates + skin-tone metadata | [Fitzpatrick17k](https://github.com/mattgroh/fitzpatrick17k) | Request images through the repository route; clinician-audit the 156 KS-labelled candidates. |
| PASSION | External fairness cohort | [PASSION](https://passionderm.github.io/) | Request access; respect non-redistribution terms; keep evaluation-only. |
| SKINCON | Partial expert concept annotations | [SKINCON](https://skincon-dataset.github.io/) | Definitions do not exactly match the seven project concepts. |
| Kaggle Notebooks | GPU compute for permitted data | [Kaggle Notebooks](https://www.kaggle.com/docs/efficient-gpu-usage) | Quota applies; do not upload restricted data unless its terms allow it. |
| Institution + clinical partners | Ethics, local cohort, clinician review | Institution + clinical partners | Supervisor → IRB/REC → UCI/Mbarara data agreement; no shortcut through code. |

## Evidence ledger

### Verified in this audit

- Remote pre-triage-removal HEAD is 2d23065.
- Model manifest is placeholder with null checkpoint SHA-256.
- PASSION scripts, tests, manifest, model card, security policy, operations runbook, and README links are tracked.
- No GitHub workflow or check run exists for 2d23065.
- Definition-of-done references missing storage/backup modules and an incompatible app factory/readiness contract.
- The training script still contains malignant-to-benign mapping and PASSION training mixing.
- No real-data evaluation metrics or validated frozen checkpoint are recorded.

### Reported, not independently reproduced

- The user reported 15/15 PASSION tests and 11/11 definition-of-done checks locally.
- Those totals were not independently reproduced in this roadmap audit and do not establish remote CI or full integration coverage.

### Claims that must be corrected

- PASSION is not a 19k/12-class benign-melanoma-KS training dataset for this project.
- A smoke checkpoint is not a frozen validated model.
- Renaming mock helpers to fallback does not make fixed clinical payloads safe.
- A local pass with copied files is not a fresh-clone pass.
- Prototype or stakeholder interest is not pilot authorization.

## Update protocol

1. Update the task in the dashboard or edit `docs/roadmap/status.json` directly.
2. If using the dashboard, export `status.json` and replace the canonical file.
3. Run `python3 docs/roadmap/build.py`.
4. Review the diff and commit JSON, `docs/roadmap/index.html`, and `ROADMAP.md` together.
5. Use `python3 docs/roadmap/build.py --check` in CI to catch drift.
6. Close a gate only with evidence and a named reviewer; never convert a reported result to verified by relabeling it.

Do not place patient data, secrets, restricted images, or access tokens in this tracker.

## Changelog

| Date | Change | Evidence |
| --- | --- | --- |
| 2026-11-08 | Created the Evidence Atlas, interactive tracker, and versioned Markdown roadmap from the verified 2d23065 snapshot. | Repository inspection and GitHub check metadata; no application behavior changed. |

---
*Generated from `docs/roadmap/status.json`. Edit the source, not the generated files.*
