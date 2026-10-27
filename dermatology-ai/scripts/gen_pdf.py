from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
import datetime

doc = SimpleDocTemplate(
    "Dermatology_AI_Uganda_Roadmap.pdf",
    pagesize=A4,
    rightMargin=0.75*inch,
    leftMargin=0.75*inch,
    topMargin=0.75*inch,
    bottomMargin=0.75*inch
)

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Title'],
    fontSize=24,
    leading=28,
    spaceAfter=6,
    textColor=HexColor('#1a3c5e'),
    alignment=TA_CENTER
)

subtitle_style = ParagraphStyle(
    'CustomSubtitle',
    parent=styles['Normal'],
    fontSize=13,
    leading=16,
    spaceAfter=4,
    textColor=HexColor('#3d6b8e'),
    alignment=TA_CENTER
)

heading1_style = ParagraphStyle(
    'Heading1Custom',
    parent=styles['Heading1'],
    fontSize=16,
    leading=20,
    spaceBefore=18,
    spaceAfter=8,
    textColor=HexColor('#1a3c5e'),
)

heading2_style = ParagraphStyle(
    'Heading2Custom',
    parent=styles['Heading2'],
    fontSize=13,
    leading=16,
    spaceBefore=14,
    spaceAfter=6,
    textColor=HexColor('#2c5f7c'),
)

body_style = ParagraphStyle(
    'BodyCustom',
    parent=styles['Normal'],
    fontSize=10,
    leading=13,
    spaceAfter=6,
    alignment=TA_JUSTIFY,
    textColor=HexColor('#2d2d2d'),
)

bullet_style = ParagraphStyle(
    'BulletCustom',
    parent=styles['Normal'],
    fontSize=10,
    leading=13,
    spaceAfter=3,
    leftIndent=20,
    bulletIndent=8,
    alignment=TA_JUSTIFY,
    textColor=HexColor('#2d2d2d'),
)

small_style = ParagraphStyle(
    'SmallCustom',
    parent=styles['Normal'],
    fontSize=9,
    leading=11,
    spaceAfter=4,
    textColor=HexColor('#555555'),
)

code_style = ParagraphStyle(
    'CodeCustom',
    parent=styles['Normal'],
    fontSize=9,
    leading=11,
    spaceAfter=4,
    leftIndent=20,
    fontName='Courier',
    textColor=HexColor('#1a3c5e'),
    backColor=HexColor('#f0f4f7'),
)

story = []

story.append(Spacer(1, 1.5*inch))
story.append(Paragraph("Dermatology AI for Uganda/East Africa", title_style))
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("Research Roadmap & Gap Analysis", subtitle_style))
story.append(Spacer(1, 0.4*inch))
story.append(Paragraph("Targeting Deployment at Uganda Cancer Institute & Mbarara Hospital", subtitle_style))
story.append(Spacer(1, 0.6*inch))
story.append(Paragraph(f"Prepared: {datetime.date.today().strftime('%B %d, %Y')}", small_style))
story.append(Paragraph("Status: Pre-Phase 1 \u2014 Awaiting Stakeholder Alignment", small_style))
story.append(PageBreak())

story.append(Paragraph("1. Executive Summary", heading1_style))
story.append(Paragraph(
    "This roadmap synthesizes a landscape review of 50+ open-source dermatology AI projects, "
    "public skin-image datasets, and published fairness/debiasing literature to identify critical "
    "gaps for deploying a clinically reliable, fairness-aware dermatology AI system in Uganda "
    "(Uganda Cancer Institute, Mbarara Hospital). The analysis reveals that no existing project "
    "simultaneously addresses: (a) real African skin-tone data at scale, (b) concept-bottleneck "
    "interpretability with clinician-in-the-loop reinforcement learning, (c) operational fairness "
    "monitoring in low-bandwidth clinical settings, and (d) integrated web-first deployment with "
    "telemetry. This document proposes a phased approach to close these gaps.",
    body_style
))

story.append(Paragraph("2. Landscape Review \u2014 Key Findings", heading1_style))

story.append(Paragraph("2.1 Existing Projects by Category", heading2_style))

projects_data = [
    ["Category", "Representative Projects", "Relevance to This Roadmap", "Critical Gap"],
    ["Concept Bottleneck / Transparency", "MONET (suinleelab, 89\u2605)", "Concept-level explanations grounded in medical literature", "No RL/HITL loop; concepts frozen after training"],
    ["Fairness / Debiasing", "CIRCLe (arezou-pakzad, 19\u2605); Detecting-Melanoma-Fairly (pbevan1, 18\u2605); Skin-Deep-Unlearning (pbevan1, 7\u2605)", "Color-invariant representations; skin-tone detection; artifact debiasing", "Training-time only; no operational fairness monitoring; no African data"],
    ["Data Quality / Curation", "Corrected-Skin-Image-Datasets (kakumarabhishek, 9\u2605) \u2014 Nature Scientific Data 2025", "Identified duplicates in HAM10000; mislabeled Fitzpatrick types in Fitzpatrick17k; released cleaned Fitzpatrick17k-C", "Cleaning is retrospective; no prospective quality pipeline for new African data"],
    ["Foundation Models", "PanDerm, Derm1M (SiyuanYan1, 76\u2605), DermFM-Zero (34\u2605) \u2014 ICCV\u201925 Highlight", "Million-scale vision-language datasets; zero-shot dermatology", "Pre-training data Western-centric; no fine-tuning pipeline for Ugandan phenotypes"],
    ["Student / Single-Shot CNNs", "LesNet, DermNet crawler, FFHQ wrinkles, ASCORAD, 40+ others", "Diverse architectures; some production-grade (DermaSwarm)", "No fairness, no HITL, no concept bottleneck, no deployment strategy"],
]

table = Table(projects_data, colWidths=[1.1*inch, 1.5*inch, 1.8*inch, 1.6*inch])
table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#1a3c5e')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,0), 9),
    ('BACKGROUND', (0,1), (-1,-1), HexColor('#f7f9fc')),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTSIZE', (0,1), (-1,-1), 8.5),
    ('LEADING', (0,1), (-1,-1), 10.5),
]))
story.append(table)
story.append(Spacer(1, 0.15*inch))

story.append(Paragraph("2.2 Identified Loopholes (Gaps in Existing Work)", heading2_style))
story.append(Paragraph(
    "The following are <b>not</b> loops in this project \u2014 they are <b>systemic gaps</b> across the "
    "entire open-source dermatology AI landscape that this roadmap explicitly targets:",
    body_style
))

loopholes = [
    ("<b>Zero real African skin data at scale.</b> Fitzpatrick17k (17k images) has ~15% Type V-VI; "
     "DDI adds ~600 diverse images; ISIC has <5% dark skin. No dataset contains biopsy-confirmed "
     "lesions from sub-Saharan African patients (Kaposi sarcoma, mycetoma, tropical dermatoses)."),
    ("<b>Concept bottleneck models lack reinforcement learning.</b> MONET provides concept explanations "
     "but concepts are fixed post-training. No mechanism for clinicians to correct concepts and "
     "propagate updates via RL."),
    ("<b>Fairness interventions are training-time only.</b> CIRCLe, Detecting-Melanoma-Fairly, and "
     "Skin-Deep-Unlearning debias during training. None monitor fairness drift in production, "
     "especially under distribution shift (rural clinics, mobile capture, different lighting)."),
    ("<b>Synthetic data bypasses IRB but misses real variance.</b> GAN-generated images (synthetic-medical-images, "
     "11\u2605) lack rare disease presentations, co-morbidities, and real-world artifacts (motion blur, "
     "lighting variation, skin prep differences)."),
    ("<b>No integrated web-first deployment for low-bandwidth settings.</b> Most projects are Jupyter "
     "notebooks or local scripts. None address: offline-first PWA, image compression for 2G/3G, "
     "model quantization for mobile inference, or clinician workflow integration."),
    ("<b>HITL is image-level only, not triage-decision level.</b> Existing human feedback loops collect "
     "image labels. None capture the <i>triage decision</i> (refer / treat / monitor) with confidence "
     "calibration for downstream RL."),
    ("<b>Data quality issues propagate silently.</b> Corrected-Skin-Image-Datasets found duplicates in "
     "HAM10000 and Fitzpatrick label errors. No project implements continuous data-quality monitoring "
     "for incoming clinical images."),
    ("<b>No telemetry from real clinics.</b> Performance drop on Ugandan phenotypes vs. Western "
     "benchmarks is unknown because no system has been deployed with instrumentation."),
]

for i, loophole in enumerate(loopholes, 1):
    story.append(Paragraph(f"{i}. {loophole}", bullet_style))

story.append(Spacer(1, 0.1*inch))

story.append(Paragraph("3. Data Acquisition Strategy", heading1_style))

story.append(Paragraph("3.1 Primary Sources (Require Partnership & IRB)", heading2_style))
primary_sources = [
    ("Uganda Cancer Institute (UCI)", "Kaposi sarcoma, HIV-associated dermatoses, biopsy-confirmed labels, Fitzpatrick V-VI, patient demographics, treatment outcomes"),
    ("Mbarara Hospital (MUST/Mbarara University)", "General dermatology: eczema, fungal infections, bacterial infections, tropical ulcers, pigmentary disorders, rural patient population"),
]
for name, desc in primary_sources:
    story.append(Paragraph(f"<b>{name}:</b> {desc}", bullet_style))

story.append(Paragraph("3.2 Secondary Public Datasets (Immediate Use, No IRB)", heading2_style))
secondary_data = [
    ["Dataset", "Size", "Skin Tone Coverage", "Access", "Notes"],
    ["Fitzpatrick17k", "17,124", "Types I\u2013VI (~15% V-VI)", "GitHub/Zenodo", "Use Fitzpatrick17k-C (cleaned labels)"],
    ["DDI (Diverse Dermatology Images)", "~656", "Fitzpatrick III\u2013VI focus", "Stanford/Zenodo", "High-quality clinical + dermoscopy"],
    ["ISIC 2019/2020", "25k+/230k+", "<5% Type V-VI", "ISIC Archive", "Largest; deduplicate via Corrected-Skin-Image-Datasets"],
    ["HAM10000", "10,015", "Mostly I\u2013IV", "Harvard Dataverse", "Known duplicates; use cleaned version"],
    ["PadUFES-20", "2,298", "Brazilian population (III\u2013V)", "GitHub", "Good Latin American representation"],
    ["Derm7pt", "1,011", "Mixed", "GitHub", "7-point checklist annotations"],
    ["PH2", "200", "Mostly I\u2013III", "ISIC", "High-quality dermoscopy only"],
    ["DermNet (crawled)", "~20k+", "Variable", "tcxxxx/DermNet-images-crawler", "Requires crawling; license check needed"],
]
table2 = Table(secondary_data, colWidths=[1.1*inch, 0.6*inch, 1.1*inch, 0.9*inch, 2.0*inch])
table2.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#1a3c5e')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,0), 8.5),
    ('BACKGROUND', (0,1), (-1,-1), HexColor('#f7f9fc')),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTSIZE', (0,1), (-1,-1), 8),
    ('LEADING', (0,1), (-1,-1), 10),
]))
story.append(table2)
story.append(Spacer(1, 0.15*inch))

story.append(Paragraph("4. Proposed System Architecture", heading1_style))

story.append(Paragraph("4.1 Core Design Principles", heading2_style))
principles = [
    "<b>Web-first, offline-capable.</b> PWA with Service Worker; model quantization (INT8/ONNX) for mobile inference; adaptive image compression.",
    "<b>Concept bottleneck with RLHF.</b> Interpretable concepts (ABCD rule, 7-point checklist, pattern analysis) \u2192 clinician corrects concepts \u2192 reward model updates concept weights via PPO.",
    "<b>Fairness as a runtime constraint.</b> Continuous monitoring of TPR/FPR parity across Fitzpatrick types; automatic alerting + model rollback on drift.",
    "<b>Human-in-the-loop at triage decision level.</b> Clinician selects: Refer / Treat / Monitor + confidence. This (image, concepts, decision, confidence) tuple feeds RL replay buffer.",
    "<b>Data quality gates.</b> Automated duplicate detection (perceptual hashing), Fitzpatrick re-estimation, OOD detection on every upload.",
    "<b>Telemetry by default.</b> Structured logging of: inference latency, concept activations, clinician agreement, fairness metrics, data quality flags \u2014 exported to UCI/Mbarara dashboard.",
]
for p in principles:
    story.append(Paragraph(f"\u2022 {p}", bullet_style))

story.append(Paragraph("4.2 High-Level Component Diagram", heading2_style))
story.append(Paragraph(
    "[Mobile/Web PWA] \u2192 [Image Preprocess/Compress] \u2192 [Quantized Backbone (EfficientNet/ConvNeXt)] \u2192 "
    "[Concept Bottleneck Head] \u2192 [Triage Policy Head] \u2192 [Clinician UI: Concepts + Decision + Confidence] \u2192 "
    "[RL Replay Buffer] \u2192 [Nightly PPO Update] \u2192 [Fairness Monitor] \u2192 [Model Registry] \u2192 [Deploy]",
    code_style
))
story.append(Paragraph("4.3 Technology Stack", heading2_style))
stack_data = [
    ["Layer", "Technology", "Rationale"],
    ["Frontend", "React 18 + TypeScript + Vite + PWA (Workbox)", "Offline-first, installable, mobile-optimized"],
    ["Backend API", "FastAPI + Python 3.11 + async SQLAlchemy", "High performance, type safety, easy ML integration"],
    ["ML Runtime", "ONNX Runtime Web / PyTorch Mobile + INT8 quantization", "Runs in browser (WebAssembly) or native mobile"],
    ["Concept Bottleneck", "Custom head on ConvNeXt-Tiny backbone (6.8M params)", "Interpretable concepts; small enough for mobile"],
    ["RLHF", "PPO (stable-baselines3) with concept-level reward model", "Proven algorithm; concept rewards align with clinician mental model"],
    ["Fairness Monitor", "Custom streaming metrics (TPR/FPR parity, calibration curves)", "Real-time; no batch recomputation needed"],
    ["Data Quality", "pHash (imagehash) + CLIP-based OOD detector + Fitzpatrick CNN", "Fast duplicate detection; semantic OOD; skin-tone estimation"],
    ["Database", "PostgreSQL (Supabase) + pgvector for embeddings", "Managed; vector search for similar cases; HIPAA-ready"],
    ["Auth", "Supabase Auth (OIDC) + role-based access (clinician/admin/researcher)", "Standards-compliant; granular permissions"],
    ["Telemetry", "OpenTelemetry \u2192 Grafana Cloud / self-hosted Prometheus", "Vendor-neutral; dashboards for UCI/Mbarara"],
    ["CI/CD", "GitHub Actions \u2192 Docker \u2192 Fly.io / Railway / self-hosted K8s", "GitOps; zero-downtime deploys; rollback on fairness alert"],
]
table3 = Table(stack_data, colWidths=[1.0*inch, 2.3*inch, 2.7*inch])
table3.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#1a3c5e')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,0), 8.5),
    ('BACKGROUND', (0,1), (-1,-1), HexColor('#f7f9fc')),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTSIZE', (0,1), (-1,-1), 8),
    ('LEADING', (0,1), (-1,-1), 10),
]))
story.append(table3)

story.append(PageBreak())

story.append(Paragraph("5. Phased Implementation Roadmap", heading1_style))

phases = [
    ("Phase 0: Foundation & Partnerships (Weeks 1\u20134)", [
        "Execute UCI & Mbarara Data Sharing Agreements + IRB approvals (lead time: 8\u201312 weeks; start immediately)",
        "Establish Supabase project, GitHub repo, CI/CD pipeline, staging environment",
        "Download & preprocess all public datasets (Fitzpatrick17k-C, DDI, ISIC, PadUFES, HAM10000-cleaned)",
        "Build data quality pipeline: pHash dedup, Fitzpatrick re-labeling (using corrected labels as ground truth), OOD baseline",
        "Train initial Fitzpatrick skin-type classifier (Types I\u2013VI) on Fitzpatrick17k-C \u2014 this becomes the runtime skin-tone estimator",
        "Define concept vocabulary (ABCD, 7-point checklist, pattern lexicon) with Ugandan dermatologist input",
    ]),
    ("Phase 1: Concept Bottleneck Baseline (Weeks 5\u201310)", [
        "Train ConvNeXt-Tiny + concept bottleneck head on combined public data (multi-task: diagnosis + concepts)",
        "Implement concept vocabulary as learnable prototypes; loss = diagnosis CE + concept BCE + orthogonality regularization",
        "Evaluate on held-out public test sets + fairness slices (Fitzpatrick I\u2013II vs. V\u2013VI)",
        "Build PWA skeleton: camera capture \u2192 compress \u2192 ONNX inference \u2192 concept visualization \u2192 triage decision UI",
        "Deploy to staging; clinician dry-run with 5 Ugandan dermatologists (remote); collect UX feedback",
    ]),
    ("Phase 2: HITL Data Collection & RLHF Infrastructure (Weeks 11\u201318)", [
        "Deploy PWA to UCI & Mbarara (pilot: 3 clinicians each site) with IRB-approved data collection protocol",
        "Collect: (image, concepts, clinician decision [Refer/Treat/Monitor], confidence [1\u20135], time-to-decision)",
        "Build RL replay buffer; implement concept-level reward: +1 for correct diagnosis + concept agreement, -1 for disagreement",
        "Train reward model (Bradley-Terry on pairwise clinician preferences over concept sets)",
        "Nightly PPO updates on accumulated buffer; fairness gate: only deploy if TPR parity \u0394 < 5% across skin tones",
        "Implement telemetry dashboards: concept agreement rate, decision latency, fairness metrics, data quality flags",
    ]),
    ("Phase 3: Operational Hardening & Scale (Weeks 19\u201330)", [
        "Mobile optimization: INT8 quantization, model pruning, progressive image loading, offline queue sync",
        "Continuous fairness monitoring: streaming TPR/FPR by skin tone, automatic rollback on drift > threshold",
        "Active learning loop: flag low-confidence / high-disagreement / OOD cases for priority clinician review",
        "Expand concept vocabulary with Ugandan-specific patterns (Kaposi variants, tropical ulcer stages, mycetoma grains)",
        "Federated fine-tuning: local updates at each site \u2192 secure aggregation \u2192 global model (privacy-preserving)",
        "Clinical validation study design: prospective non-inferiority vs. specialist referral (primary endpoint: sensitivity for malignancy)",
    ]),
    ("Phase 4: Sustainability & Handoff (Weeks 31\u201340)", [
        "Open-source core platform (MIT/Apache-2); keep Ugandan clinical data under local governance",
        "Train local ML engineers at MUST/Mbarara on model maintenance, fairness auditing, RLHF pipeline",
        "Publish: (a) Ugandan skin lesion dataset (de-identified, with consent), (b) fairness-aware concept bottleneck methodology, (c) deployment lessons",
        "Transition to local ownership: UCI/Mbarara run infrastructure; external team moves to advisory role",
    ]),
]

for phase_title, items in phases:
    story.append(Paragraph(phase_title, heading2_style))
    for item in items:
        story.append(Paragraph(f"\u2022 {item}", bullet_style))
    story.append(Spacer(1, 0.08*inch))

story.append(Paragraph("6. Risk Register & Mitigations", heading1_style))
risks = [
    ["Risk", "Likelihood", "Impact", "Mitigation"],
    ["IRB/regulatory delays at UCI/Mbarara", "High", "High", "Start Phase 0 Week 1; parallel track on public data; engage Uganda National Council for Science & Technology early"],
    ["Insufficient Ugandan data for rare conditions", "High", "High", "Transfer learning from public data + synthetic augmentation (GAN) for rare classes; active learning to prioritize labeling"],
    ["Clinician adoption resistance", "Medium", "High", "Co-design UI from Day 1; minimal clicks; offline-first; show concept explanations not just predictions"],
    ["Fairness drift in production", "Medium", "High", "Streaming fairness monitor with auto-rollback; monthly fairness audit report to ethics board"],
    ["Internet/power instability at clinics", "High", "Medium", "Full offline PWA; background sync; battery-optimized inference; solar charging stations budgeted"],
    ["Model size too large for mobile", "Low", "Medium", "ConvNeXt-Tiny (6.8M) + INT8 quantization \u2192 ~7 MB; test on low-end Android (2GB RAM) early"],
    ["Concept vocabulary misalignment with local practice", "Medium", "Medium", "Weekly concept review sessions with Ugandan dermatologists in Phase 1\u20132; vocab versioning"],
    ["Funding runway", "Medium", "High", "Phased grants: Phase 0\u20131 (seed), Phase 2\u20133 (implementation), Phase 4 (sustainability); leverage Grand Challenges, NIH, Wellcome"],
]
table4 = Table(risks, colWidths=[1.8*inch, 0.7*inch, 0.7*inch, 2.8*inch])
table4.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#1a3c5e')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,0), 8.5),
    ('BACKGROUND', (0,1), (-1,-1), HexColor('#f7f9fc')),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTSIZE', (0,1), (-1,-1), 8),
    ('LEADING', (0,1), (-1,-1), 10),
]))
story.append(table4)

story.append(PageBreak())

story.append(Paragraph("7. Success Metrics (Go/No-Go Gates)", heading1_style))
metrics = [
    ["Phase", "Metric", "Target", "Measurement"],
    ["Phase 1", "Diagnosis AUC (public test, all skin tones)", "\u2265 0.85", "Held-out ISIC/DDI/Fitzpatrick17k-C"],
    ["Phase 1", "Concept F1 (dermatologist-annotated concepts)", "\u2265 0.75", "5 clinicians \u00d7 200 images"],
    ["Phase 1", "TPR parity (Type I\u2013II vs. V\u2013VI)", "\u0394 \u2264 0.05", "Stratified evaluation"],
    ["Phase 2", "Clinician concept agreement rate", "\u2265 70%", "Per-session telemetry"],
    ["Phase 2", "RLHF policy improvement vs. supervised baseline", "\u2265 5% relative AUC gain", "A/B on replay buffer"],
    ["Phase 2", "Median decision latency (capture \u2192 triage)", "\u2264 15 seconds", "PWA telemetry"],
    ["Phase 3", "Sensitivity for malignancy (prospective)", "\u2265 90% (non-inferiority margin -5%)", "Clinical study vs. specialist"],
    ["Phase 3", "Fairness drift detection time", "< 24 hours", "Streaming monitor logs"],
    ["Phase 3", "Offline inference success rate", "\u2265 99%", "Field test: 2G, airplane mode"],
    ["Phase 4", "Local team autonomous deployments", "\u2265 2 per quarter", "GitOps logs"],
]
table5 = Table(metrics, colWidths=[0.7*inch, 2.0*inch, 1.3*inch, 2.0*inch])
table5.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), HexColor('#1a3c5e')),
    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ('FONTSIZE', (0,0), (-1,0), 8.5),
    ('BACKGROUND', (0,1), (-1,-1), HexColor('#f7f9fc')),
    ('GRID', (0,0), (-1,-1), 0.5, HexColor('#cccccc')),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('FONTSIZE', (0,1), (-1,-1), 8),
    ('LEADING', (0,1), (-1,-1), 10),
]))
story.append(table5)

story.append(Spacer(1, 0.2*inch))

story.append(Paragraph("8. Open Questions Requiring Stakeholder Decisions", heading1_style))
story.append(Paragraph(
    "The following must be resolved before Phase 1 kickoff. Each requires explicit agreement from "
    "UCI, Mbarara, and the technical team.",
    body_style
))

questions = [
    ("Data Governance", [
        "Who owns the Ugandan clinical images and derived models? (Recommendation: UCI/Mbarara retain data sovereignty; model weights open-sourced under Apache-2 with data-use restriction)",
        "What de-identification standard? (Recommendation: HIPAA Safe Harbor + facial/landmark removal via segmentation)",
        "Can de-identified data leave Uganda? (Recommendation: No \u2014 training runs on-prem or in Uganda-hosted cloud)",
    ]),
    ("Clinical Workflow", [
        "What is the exact triage decision schema? (Options: Refer/Treat/Monitor vs. Urgent/Routine/Reassure vs. custom)",
        "Who is the \u2018clinician\u2019 for HITL? (Dermatologist, clinical officer, nurse? Different expertise levels need different UI)",
        "Is the AI assistive (clinician decides) or autonomous for certain low-risk classes? (Regulatory implication)",
    ]),
    ("Fairness Definition", [
        "Which parity metric? (TPR parity, FPR parity, equalized odds, calibration parity \u2014 recommend equalized odds + calibration)",
        "What skin-tone grouping? (Fitzpatrick I\u2013II vs. III\u2013IV vs. V\u2013VI, or binary light vs. dark, or Monk Skin Tone Scale)",
        "What drift threshold triggers rollback? (Recommendation: TPR \u0394 > 5% for any malignancy class)",
    ]),
    ("Technical Scope", [
        "Target conditions: Start with \u2018malignancy vs. benign\u2019 binary, or full multi-class (15+ Ugandan-relevant conditions)?",
        "Image type: Clinical (phone camera) only, or include dermoscopy? (Dermoscopy requires hardware procurement)",
        "Language: English only, or Luganda/Runyankore/Rutooro for patient-facing explanations?",
    ]),
    ("Sustainability", [
        "Post-grant infrastructure budget: Who pays for GPU inference, Supabase, monitoring? (Estimate: $500\u20132000/month)",
        "Local ML engineering capacity: Does MUST/Mbarara have staff to maintain, or is capacity-building required?",
        "Publication & IP: Joint authorship policy; patent vs. open-source for novel methods (e.g., concept RLHF)?",
    ]),
]

for category, qlist in questions:
    story.append(Paragraph(f"<b>{category}</b>", heading2_style))
    for q in qlist:
        story.append(Paragraph(f"\u2022 {q}", bullet_style))
    story.append(Spacer(1, 0.05*inch))

story.append(Paragraph("Appendix A: Key References", heading1_style))
refs = [
    "Abhishek et al., 'Investigating the Quality of DermaMNIST and Fitzpatrick17k Datasets', Nature Scientific Data, 2025. (Fitzpatrick17k-C on Zenodo: 10.5281/zenodo.11101337)",
    "Groh et al., 'Evaluating Deep Neural Networks Trained on Clinical Images in Dermatology with the Fitzpatrick 17k Dataset', CVPR 2021.",
    "Daneshjou et al., 'Disparities in Dermatology AI Performance on a Diverse, Curated Clinical Image Set', NEJM AI, 2024. (DDI dataset)",
    "Yan et al., 'Derm1M: A Million-Scale Vision-Language Dataset Aligned with Clinical Ontology Knowledge for Dermatology', ICCV 2025 Highlight.",
    "Yan et al., 'DermFM-Zero: Vision-Language Foundation Model for Zero-Shot Dermatology', 2026.",
    "Pacheco et al., 'CIRCLe: Color Invariant Representation Learning for Unbiased Classification of Skin Lesions', 2023.",
    "Baldock et al., 'Detecting Melanoma Fairly: Skin Tone Detection and Debiasing for Skin Lesion Classification', MICCAI DART 2022.",
    "Tschandl et al., 'The HAM10000 Dataset', Scientific Data, 2018.",
    "Codella et al., 'ISIC Archive', International Skin Imaging Collaboration.",
    "Perez et al., 'PadUFES-20: A Skin Lesion Dataset from Brazilian Patients', 2020.",
]
for ref in refs:
    story.append(Paragraph(f"\u2022 {ref}", ParagraphStyle('Ref', parent=small_style, leftIndent=20, spaceAfter=3)))

story.append(Spacer(1, 0.2*inch))
story.append(Paragraph("Appendix B: GitHub Repositories for Reference Implementation", heading1_style))
github_refs = [
    "https://github.com/kakumarabhishek/Corrected-Skin-Image-Datasets \u2014 Data quality pipeline, Fitzpatrick17k-C",
    "https://github.com/suinleelab/MONET \u2014 Concept bottleneck + medical literature grounding",
    "https://github.com/arezou-pakzad/CIRCLe \u2014 Color-invariant fairness",
    "https://github.com/pbevan1/Detecting-Melanoma-Fairly \u2014 Debiasing + skin tone detection",
    "https://github.com/pbevan1/Skin-Deep-Unlearning \u2014 Artifact debiasing",
    "https://github.com/SiyuanYan1/Derm1M \u2014 Million-scale vision-language dataset",
    "https://github.com/SiyuanYan1/DermFM-Zero \u2014 Zero-shot foundation model",
    "https://github.com/tcxxxx/DermNet-images-crawler \u2014 DermNet crawler",
    "https://github.com/mmu-dermatology-research/isic_duplicate_removal_strategy \u2014 ISIC deduplication",
]
for ref in github_refs:
    story.append(Paragraph(f"\u2022 {ref}", ParagraphStyle('Ref', parent=small_style, leftIndent=20, spaceAfter=3)))

doc.build(story)
print("PDF generated: Dermatology_AI_Uganda_Roadmap.pdf")