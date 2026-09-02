"""
Comprehensive demo data seeder for Dermatology AI.
Run: python seed_demo.py
"""

from __future__ import annotations

import json
import uuid
import bcrypt
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).parent

DOCTOR_PERMISSIONS = [
    "view_patient", "edit_patient", "upload_images",
    "run_diagnosis", "override_triage", "view_analytics",
    "view_history", "export_data",
]


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _ts(days_ago: int = 0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# =========================================================================
#  PATIENTS — 14 diverse patients across all Fitzpatrick types & conditions
# =========================================================================

PATIENTS = [
    {
        "id": "PAT-2024-0847",
        "name": "Sarah Mwangi",
        "age": "34 yrs (DOB: 1991-03-14)",
        "gender": "female",
        "fitz": "IV",
        "contact": "+254 712 345 678",
        "history": "3-month history of pigmented lesion on left upper back. Patient reports recent change in shape and intermittent pruritus. No personal or family history of melanoma.",
        "diagnosis": "melanoma",
        "body_site": "upper_back",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260510-0001",
                "date": "2026-05-10",
                "desc": "Initial consult — lesion mapping & dermoscopic photography. AI flagged asymmetry > 0.7. Recommended 2-week follow-up.",
                "tag": "followup",
                "diagnosis": "Superficial Spreading Melanoma (suspected)",
                "ai_findings": "Asymmetry: 0.82 | Border irregularity: 0.73 | Color variegation: 0.65 | Diameter: 0.44\nABCD criteria: High risk. Triage: Follow-up (2 weeks).",
                "treatment_notes": "Patient counseled on melanoma warning signs. Dermoscopic photography taken. Scheduled for follow-up in 2 weeks for re-assessment and possible biopsy.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Left upper back",
                "lesion_size": "6mm x 4mm",
                "created_at": _ts(18),
            },
            {
                "id": "VIS-20260402-0002",
                "date": "2026-04-02",
                "desc": "Routine skin check — no significant findings. ABCD criteria unremarkable.",
                "tag": "routine",
                "diagnosis": "No suspicious lesions detected",
                "ai_findings": "Asymmetry: 0.12 | Border: 0.08 | Color: 0.15 | Diameter: 0.10\nAll concept scores low. Triage: Routine monitoring.",
                "treatment_notes": "Annual skin check complete. Patient advised on sun protection and monthly self-exams.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Full body",
                "lesion_size": "N/A",
                "created_at": _ts(56),
            },
            {
                "id": "VIS-20251218-0003",
                "date": "2025-12-18",
                "desc": "Urgent referral — rapid-growing nodule on right forearm. Biopsy scheduled but patient deferred.",
                "tag": "urgent",
                "diagnosis": "Suspicious nodule (rule out SCC)",
                "ai_findings": "Asymmetry: 0.91 | Border: 0.88 | Color: 0.79 | Diameter: 0.85\nHigh concern. Triage: Urgent — Biopsy Recommended.",
                "treatment_notes": "Biopsy recommended and scheduled. Patient expressed anxiety and deferred procedure. Discussed risks of delay. Follow-up in 1 week.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Right forearm, dorsal aspect",
                "lesion_size": "12mm x 8mm, raised 3mm",
                "created_at": _ts(161),
            },
        ],
        "created_at": _ts(180),
    },
    {
        "id": "PAT-2024-0912",
        "name": "John Kamau",
        "age": "52 yrs (DOB: 1974-08-22)",
        "gender": "male",
        "fitz": "V",
        "contact": "+254 723 456 789",
        "history": "Completed treatment for BCC on left cheek. Treated with Mohs surgery — clear margins confirmed. No recurrence at 6-month follow-up.",
        "diagnosis": "bcc",
        "body_site": "face",
        "status": "completed",
        "visits": [
            {
                "id": "VIS-20251015-0001",
                "date": "2025-10-15",
                "desc": "Initial diagnosis — biopsy-confirmed BCC on left cheek.",
                "tag": "urgent",
                "diagnosis": "Basal Cell Carcinoma (confirmed)",
                "ai_findings": "Nodular BCC with ulceration. Low-risk subtype. Triage: Treatment recommended.",
                "treatment_notes": "Biopsy performed. Mohs surgery scheduled.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Left cheek",
                "lesion_size": "8mm x 6mm",
                "created_at": _ts(225),
            },
            {
                "id": "VIS-20251120-0001",
                "date": "2025-11-20",
                "desc": "Mohs surgery — clear margins achieved. Wound closed with linear repair.",
                "tag": "followup",
                "diagnosis": "BCC — completely excised",
                "ai_findings": "N/A — surgical specimen",
                "treatment_notes": "Mohs surgery performed. Clear margins. Patient recovering well.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Left cheek",
                "lesion_size": "8mm x 6mm",
                "created_at": _ts(189),
            },
            {
                "id": "VIS-20260522-0001",
                "date": "2026-05-22",
                "desc": "6-month follow-up — no signs of recurrence. Patient discharged.",
                "tag": "routine",
                "diagnosis": "No recurrence — treatment complete",
                "ai_findings": "No suspicious findings. Triage: Routine.",
                "treatment_notes": "Patient discharged from follow-up. Advised on annual skin checks and sun protection.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Left cheek",
                "lesion_size": "N/A",
                "created_at": _ts(6),
            },
        ],
        "created_at": _ts(230),
    },
    {
        "id": "PAT-2025-0031",
        "name": "Grace Achieng",
        "age": "28 yrs (DOB: 1998-09-05)",
        "gender": "female",
        "fitz": "VI",
        "contact": "+254 734 567 890",
        "history": "Dysplastic nevus on right shoulder. Scheduled for 3-month follow-up after initial excision. Healing well, no recurrence noted.",
        "diagnosis": "dysplastic_nevus",
        "body_site": "right_arm",
        "status": "followup",
        "visits": [
            {
                "id": "VIS-20260310-0001",
                "date": "2026-03-10",
                "desc": "Excision of dysplastic nevus on right shoulder. Clear margins achieved.",
                "tag": "followup",
                "diagnosis": "Dysplastic Nevus — excised",
                "ai_findings": "Moderate atypia. No melanoma identified. Triage: Follow-up in 3 months.",
                "treatment_notes": "Excisional biopsy performed. Wound closed primarily. Follow-up in 3 months.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Right shoulder",
                "lesion_size": "5mm x 4mm",
                "created_at": _ts(79),
            },
            {
                "id": "VIS-20260610-0001",
                "date": "2026-06-10",
                "desc": "3-month follow-up — wound healed well. No signs of recurrence.",
                "tag": "routine",
                "diagnosis": "Healing well — no recurrence",
                "ai_findings": "Low risk. No suspicious features. Triage: Routine monitoring.",
                "treatment_notes": "Patient reassured. Next follow-up in 6 months.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Right shoulder",
                "lesion_size": "N/A",
                "created_at": _ts(0),
            },
        ],
        "created_at": _ts(82),
    },
    {
        "id": "PAT-2025-0042",
        "name": "Peter Omondi",
        "age": "45 yrs (DOB: 1981-11-30)",
        "gender": "male",
        "fitz": "IV",
        "contact": "+254 745 678 901",
        "history": "Referred by GP for suspicious lesion on left forearm. Patient reports new growth over past 6 weeks. No prior skin cancer history.",
        "diagnosis": "scc",
        "body_site": "left_arm",
        "status": "consultation",
        "visits": [
            {
                "id": "VIS-20260601-0001",
                "date": "2026-06-01",
                "desc": "Initial consultation — rapid-growing nodule on left forearm. Biopsy scheduled.",
                "tag": "urgent",
                "diagnosis": "Suspicious nodule (rule out SCC)",
                "ai_findings": "Asymmetry: 0.78 | Border: 0.69 | Color: 0.71 | Diameter: 0.82\nHigh concern. Triage: Urgent — Biopsy Recommended.",
                "treatment_notes": "Biopsy scheduled. Patient counseled on SCC risks and treatment options.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Left forearm, extensor surface",
                "lesion_size": "10mm x 7mm, raised 2mm",
                "created_at": _ts(0),
            },
        ],
        "created_at": _ts(0),
    },
    {
        "id": "PAT-2026-0101",
        "name": "Emma Larsen",
        "age": "22 yrs (DOB: 2004-06-15)",
        "gender": "female",
        "fitz": "I",
        "contact": "+254 701 111 222",
        "history": "Lifelong severe acne vulgaris unresponsive to topical treatments. Multiple courses of oral antibiotics with partial response. Reports significant psychosocial impact.",
        "diagnosis": "actinic_keratosis",
        "body_site": "face",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260515-0101",
                "date": "2026-05-15",
                "desc": "Consultation for severe acne. Prescribed isotretinoin 20mg daily after normal LFTs.",
                "tag": "followup",
                "diagnosis": "Acne vulgaris (Grade III-IV)",
                "ai_findings": "Inflammation: 0.78 | Bacterial colonization indicators elevated. Triage: Follow-up for treatment monitoring.",
                "treatment_notes": "Started isotretinoin. LFTs and lipid panel normal. Pregnancy test negative. Contraception counseling provided.",
                "doctor_name": "Dr. Sarah Kimani",
                "lesion_location": "Face — cheeks, chin, forehead",
                "lesion_size": "Multiple lesions 2-5mm",
                "created_at": _ts(13),
            },
            {
                "id": "VIS-20260601-0102",
                "date": "2026-06-01",
                "desc": "1-month follow-up — moderate improvement. Mild dryness managed with moisturizer.",
                "tag": "routine",
                "diagnosis": "Acne vulgaris — improving",
                "ai_findings": "Inflammation: 0.45 | Reduced lesion count ~40%. Triage: Continue treatment.",
                "treatment_notes": "Continuing isotretinoin. Dryness controlled with emollients. LFTs stable.",
                "doctor_name": "Dr. Sarah Kimani",
                "lesion_location": "Face",
                "lesion_size": "Lesions 1-3mm",
                "created_at": _ts(0),
            },
        ],
        "created_at": _ts(30),
    },
    {
        "id": "PAT-2026-0102",
        "name": "Michael Ochieng",
        "age": "60 yrs (DOB: 1966-02-28)",
        "gender": "male",
        "fitz": "VI",
        "contact": "+254 702 222 333",
        "history": "Long-standing psoriasis vulgaris. Previous treatments include topical steroids and UV phototherapy. Recently flaring due to stress.",
        "diagnosis": "actinic_keratosis",
        "body_site": "chest",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260420-0201",
                "date": "2026-04-20",
                "desc": "Severe psoriasis flare. 40% BSA involvement. Started on methotrexate.",
                "tag": "urgent",
                "diagnosis": "Psoriasis vulgaris (severe flare)",
                "ai_findings": "Inflammation: 0.89 | Plaque thickness elevated. Triage: Urgent — systemic therapy indicated.",
                "treatment_notes": "Methotrexate 15mg weekly initiated. FBC, LFTs, renal function baseline checked. Referred to rheumatology for joint assessment.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Trunk, arms, legs — 40% BSA",
                "lesion_size": "Plaques 2-8cm",
                "created_at": _ts(38),
            },
            {
                "id": "VIS-20260518-0202",
                "date": "2026-05-18",
                "desc": "Treatment follow-up — 50% improvement. Tolerating methotrexate well.",
                "tag": "followup",
                "diagnosis": "Psoriasis — improving on methotrexate",
                "ai_findings": "Inflammation: 0.52 | Reduced plaque thickness. Triage: Continue current therapy.",
                "treatment_notes": "Methotrexate continued. LFTs stable. Patient reports significant quality of life improvement.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Trunk, arms",
                "lesion_size": "Plaques 1-4cm",
                "created_at": _ts(10),
            },
        ],
        "created_at": _ts(45),
    },
    {
        "id": "PAT-2026-0103",
        "name": "Aisha Patel",
        "age": "31 yrs (DOB: 1995-08-10)",
        "gender": "female",
        "fitz": "III",
        "contact": "+254 703 333 444",
        "history": "New patient referred for mole mapping. Family history of melanoma (father diagnosed age 55). Patient has >50 nevi with several atypical appearing.",
        "diagnosis": "dysplastic_nevus",
        "body_site": "lower_back",
        "status": "followup",
        "visits": [
            {
                "id": "VIS-20260501-0301",
                "date": "2026-05-01",
                "desc": "Total body photography and mole mapping. 3 atypical nevi identified for short-term monitoring.",
                "tag": "followup",
                "diagnosis": "Multiple atypical nevi — high-risk phenotype",
                "ai_findings": "Asymmetry: 0.45 | Border: 0.38 | Color: 0.42\nAtypical features in 3 lesions. Triage: Follow-up in 3 months.",
                "treatment_notes": "Total body photography completed. Patient educated on self-examination. Monthly self-checks advised.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Lower back, left thigh, right shoulder",
                "lesion_size": "Lesions 3-6mm",
                "created_at": _ts(27),
            },
        ],
        "created_at": _ts(28),
    },
    {
        "id": "PAT-2026-0104",
        "name": "David Andersen",
        "age": "68 yrs (DOB: 1958-03-22)",
        "gender": "male",
        "fitz": "II",
        "contact": "+254 704 444 555",
        "history": "Retired farmer with significant sun exposure history. Multiple actinic keratoses on scalp, face, and forearms. Previously treated with cryotherapy and 5-FU.",
        "diagnosis": "actinic_keratosis",
        "body_site": "scalp",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260410-0401",
                "date": "2026-04-10",
                "desc": "Widespread actinic keratoses on scalp and face. Field treatment with 5-FU initiated.",
                "tag": "followup",
                "diagnosis": "Actinic keratoses (Grade I-II), widespread",
                "ai_findings": "Solar elastosis: severe. Keratinocyte atypia indicators elevated. Triage: Field treatment recommended.",
                "treatment_notes": "5-FU 5% cream applied to scalp and face. Cryotherapy to 8 hypertrophic lesions. Sun protection counseling reinforced.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Scalp, face, forearms",
                "lesion_size": "Multiple lesions 2-8mm",
                "created_at": _ts(48),
            },
            {
                "id": "VIS-20260522-0402",
                "date": "2026-05-22",
                "desc": "6-week follow-up — marked improvement. Mild residual erythema.",
                "tag": "routine",
                "diagnosis": "Actinic keratoses — 70% clearance",
                "ai_findings": "Reduced cellular atypia indicators. Triage: Routine surveillance.",
                "treatment_notes": "Good response to 5-FU. Residual lesions treated with cryotherapy. Schedule annual skin check.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Scalp, face",
                "lesion_size": "Residual lesions 1-3mm",
                "created_at": _ts(6),
            },
        ],
        "created_at": _ts(50),
    },
    {
        "id": "PAT-2026-0105",
        "name": "Fatima Hassan",
        "age": "41 yrs (DOB: 1985-05-05)",
        "gender": "female",
        "fitz": "IV",
        "contact": "+254 705 555 666",
        "history": "Presenting with pigmented lesion on right cheek noticed 2 months ago. History of melasma exacerbated by pregnancy. Lesion has irregular borders.",
        "diagnosis": "melanoma",
        "body_site": "face",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260528-0501",
                "date": "2026-05-28",
                "desc": "Initial assessment — pigmented lesion with irregular borders on right cheek. Dermoscopy shows atypical pigment network.",
                "tag": "urgent",
                "diagnosis": "Suspicious pigmented lesion (rule out lentigo maligna)",
                "ai_findings": "Asymmetry: 0.76 | Border irregularity: 0.81 | Color variegation: 0.69\nAtypical pigment network detected. Triage: Urgent — Biopsy recommended.",
                "treatment_notes": "Incisional biopsy performed. Results pending. Patient very anxious — reassurance provided.",
                "doctor_name": "Dr. Sarah Kimani",
                "lesion_location": "Right cheek",
                "lesion_size": "7mm x 5mm",
                "created_at": _ts(0),
            },
        ],
        "created_at": _ts(1),
    },
    {
        "id": "PAT-2026-0106",
        "name": "James Kiprop",
        "age": "25 yrs (DOB: 2001-10-12)",
        "gender": "male",
        "fitz": "V",
        "contact": "+254 706 666 777",
        "history": "Recurrent cherry angiomas and hemangiomas on trunk. New lesion on abdomen that bleeds easily. No trauma recalled.",
        "diagnosis": "hemangioma",
        "body_site": "abdomen",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260520-0601",
                "date": "2026-05-20",
                "desc": "Examination of vascular lesion on abdomen. Clinically consistent with cherry angioma. Patient reassured.",
                "tag": "routine",
                "diagnosis": "Cherry angioma — benign vascular lesion",
                "ai_findings": "Vascular pattern: benign. No atypical features. Triage: Routine — no intervention needed.",
                "treatment_notes": "Lesion is benign. Patient educated about cherry angiomas. Offered laser removal for cosmetic concerns. No treatment elected.",
                "doctor_name": "Dr. Grace Wanjiku",
                "lesion_location": "Abdomen, right lower quadrant",
                "lesion_size": "4mm x 3mm",
                "created_at": _ts(8),
            },
        ],
        "created_at": _ts(9),
    },
    {
        "id": "PAT-2026-0107",
        "name": "Rose Nabatanzi",
        "age": "55 yrs (DOB: 1971-07-18)",
        "gender": "female",
        "fitz": "VI",
        "contact": "+254 707 777 888",
        "history": "Recurrent BCC on nose. Second recurrence after initial excision 2 years ago. Mohs surgery recommended.",
        "diagnosis": "bcc",
        "body_site": "face",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260508-0701",
                "date": "2026-05-08",
                "desc": "Recurrent BCC on nasal ala. Mohs surgery planned.",
                "tag": "urgent",
                "diagnosis": "Recurrent Basal Cell Carcinoma",
                "ai_findings": "Nodular BCC with infiltrative features. Triage: Urgent — Mohs surgery indicated.",
                "treatment_notes": "Mohs surgery scheduled. Patient counseled on recurrence risks. Sun protection reinforced.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Nasal ala, left side",
                "lesion_size": "6mm x 4mm",
                "created_at": _ts(20),
            },
        ],
        "created_at": _ts(21),
    },
    {
        "id": "PAT-2026-0108",
        "name": "Liam O'Sullivan",
        "age": "8 yrs (DOB: 2018-04-03)",
        "gender": "male",
        "fitz": "I",
        "contact": "+254 708 888 999",
        "history": "Pediatric referral for congenital nevus on left calf. Parents report recent growth proportional to child's growth. No concerning features on exam.",
        "diagnosis": "dysplastic_nevus",
        "body_site": "left_leg",
        "status": "followup",
        "visits": [
            {
                "id": "VIS-20260605-0801",
                "date": "2026-06-05",
                "desc": "Pediatric dermatology consult for congenital nevus. Benign features. Annual monitoring advised.",
                "tag": "routine",
                "diagnosis": "Congenital melanocytic nevus — benign features",
                "ai_findings": "Asymmetry: 0.15 | Border: 0.12 | Color: 0.18\nLow-risk features. Triage: Routine monitoring.",
                "treatment_notes": "Parents reassured. Lesion photographed for baseline. Annual review scheduled. No intervention needed at this time.",
                "doctor_name": "Dr. Sarah Kimani",
                "lesion_location": "Left calf, posterior aspect",
                "lesion_size": "15mm x 10mm",
                "created_at": _ts(0),
            },
        ],
        "created_at": _ts(1),
    },
    {
        "id": "PAT-2026-0109",
        "name": "Hannah Wambui",
        "age": "47 yrs (DOB: 1979-09-25)",
        "gender": "female",
        "fitz": "III",
        "contact": "+254 709 999 000",
        "history": "Chronic hand eczema unresponsive to potent topical steroids. Occupational exposure to irritants as a hairdresser. Patch testing positive to nickel and fragrance.",
        "diagnosis": "actinic_keratosis",
        "body_site": "chest",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260315-0901",
                "date": "2026-03-15",
                "desc": "Severe hand dermatitis. Started on dupilumab after insurance approval.",
                "tag": "followup",
                "diagnosis": "Chronic hand eczema (occupational)",
                "ai_findings": "Inflammation: 0.85 | Barrier disruption indicators elevated. Triage: Follow-up — biologic therapy.",
                "treatment_notes": "Dupilumab 300mg loading dose administered. Emollients and barrier creams advised. Work restrictions discussed.",
                "doctor_name": "Dr. Grace Wanjiku",
                "lesion_location": "Bilateral hands, interdigital spaces",
                "lesion_size": "Diffuse involvement",
                "created_at": _ts(74),
            },
            {
                "id": "VIS-20260428-0902",
                "date": "2026-04-28",
                "desc": "6-week follow-up — significant improvement. Patient very satisfied.",
                "tag": "routine",
                "diagnosis": "Hand eczema — 80% improved on dupilumab",
                "ai_findings": "Inflammation: 0.32 | Skin barrier improving. Triage: Continue current therapy.",
                "treatment_notes": "Dupilumab maintenance continued. Patient able to return to work with modified duties.",
                "doctor_name": "Dr. Grace Wanjiku",
                "lesion_location": "Hands",
                "lesion_size": "Mild residual on fingers",
                "created_at": _ts(30),
            },
        ],
        "created_at": _ts(80),
    },
    {
        "id": "PAT-2026-0110",
        "name": "Samuel Mutua",
        "age": "72 yrs (DOB: 1954-01-14)",
        "gender": "male",
        "fitz": "V",
        "contact": "+254 710 000 111",
        "history": "Long-standing vitiligo since age 25. Stable for years but recent spread on face and hands causing distress. Has tried topical tacrolimus and narrowband UVB.",
        "diagnosis": "actinic_keratosis",
        "body_site": "face",
        "status": "active",
        "visits": [
            {
                "id": "VIS-20260525-1001",
                "date": "2026-05-25",
                "desc": "Vitiligo follow-up — new depigmented patches on face. Started on ruxolitinib cream.",
                "tag": "followup",
                "diagnosis": "Vitiligo (active, segmental)",
                "ai_findings": "Melanin density: 0.12 | Melanocyte activity reduced. Triage: Follow-up for repigmentation monitoring.",
                "treatment_notes": "Ruxolitinib 1.5% cream started twice daily to facial patches. NB-UVB phototherapy resumed. Repigmentation typically takes 3-6 months.",
                "doctor_name": "Dr. Sarah Kimani",
                "lesion_location": "Face — perioral, periorbital; dorsal hands",
                "lesion_size": "Patchy depigmentation 2-6cm",
                "created_at": _ts(3),
            },
        ],
        "created_at": _ts(4),
    },
]

# =========================================================================
#  DOCTORS — 8 diverse clinicians
# =========================================================================

DOCTORS = {
    "admins": [
        {
            "id": "admin-001",
            "username": "admin",
            "password": _hash_password("admin123"),
            "name": "System Administrator",
        },
    ],
    "doctors": [
        {
            "id": "doc-james-doe",
            "username": "james.doe",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. James Doe",
            "email": "j.doe@hospital.org",
            "nin": "NIN-9876543210",
            "title": "Board-Certified Dermatologist",
            "active": True,
            "permissions": {p: True for p in DOCTOR_PERMISSIONS},
            "created_at": _ts(180),
            "last_login": _ts(0),
        },
        {
            "id": "doc-mercy-okonkwo",
            "username": "mercy.okonkwo",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. Mercy Okonkwo",
            "email": "m.okonkwo@hospital.org",
            "nin": "NIN-1234567890",
            "title": "Senior Dermatology Resident",
            "active": True,
            "permissions": {p: True for p in DOCTOR_PERMISSIONS},
            "created_at": _ts(150),
            "last_login": _ts(1),
        },
        {
            "id": "doc-sarah-kimani",
            "username": "sarah.kimani",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. Sarah Kimani",
            "email": "s.kimani@hospital.org",
            "nin": "NIN-5678901234",
            "title": "Pediatric Dermatologist",
            "active": True,
            "permissions": {p: True for p in DOCTOR_PERMISSIONS},
            "created_at": _ts(120),
            "last_login": _ts(0),
        },
        {
            "id": "doc-grace-wanjiku",
            "username": "grace.wanjiku",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. Grace Wanjiku",
            "email": "g.wanjiku@hospital.org",
            "nin": "NIN-3456789012",
            "title": "Consultant Dermatologist",
            "active": True,
            "permissions": {p: True for p in DOCTOR_PERMISSIONS},
            "created_at": _ts(90),
            "last_login": _ts(2),
        },
        {
            "id": "doc-peter-kamau",
            "username": "peter.kamau",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. Peter Kamau",
            "email": "p.kamau@hospital.org",
            "nin": "NIN-7890123456",
            "title": "Dermatology Registrar",
            "active": True,
            "permissions": {
                "view_patient": True,
                "edit_patient": True,
                "upload_images": True,
                "run_diagnosis": True,
                "override_triage": False,
                "view_analytics": True,
                "view_history": True,
                "export_data": False,
            },
            "created_at": _ts(60),
            "last_login": None,
        },
        {
            "id": "doc-linda-nyambura",
            "username": "linda.nyambura",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. Linda Nyambura",
            "email": "l.nyambura@hospital.org",
            "nin": "NIN-9012345678",
            "title": "Dermatopathologist",
            "active": True,
            "permissions": {
                "view_patient": True,
                "edit_patient": False,
                "upload_images": True,
                "run_diagnosis": True,
                "override_triage": False,
                "view_analytics": True,
                "view_history": True,
                "export_data": False,
            },
            "created_at": _ts(45),
            "last_login": None,
        },
        {
            "id": "doc-inactive-john",
            "username": "john.mbugua",
            "password": _hash_password("Doctor123!"),
            "name": "Dr. John Mbugua",
            "email": "j.mbugua@hospital.org",
            "nin": "NIN-4567890123",
            "title": "Board-Certified Dermatologist (On Leave)",
            "active": False,
            "permissions": {p: True for p in DOCTOR_PERMISSIONS},
            "created_at": _ts(200),
            "last_login": _ts(90),
        },
    ],
}

# =========================================================================
#  ACTIVITY LOG
# =========================================================================

ACTIVITY = [
    {"event": "System initialized — Dermatology AI v2.0.0", "actor": "system", "level": "info", "timestamp": _ts(90)},
    {"event": "Admin System Administrator logged in", "actor": "System Administrator", "level": "admin", "timestamp": _ts(85)},
    {"event": "Created doctor Dr. James Doe (james.doe)", "actor": "admin", "level": "admin", "timestamp": _ts(80)},
    {"event": "Created doctor Dr. Mercy Okonkwo (mercy.okonkwo)", "actor": "admin", "level": "admin", "timestamp": _ts(75)},
    {"event": "Created doctor Dr. Sarah Kimani (sarah.kimani)", "actor": "admin", "level": "admin", "timestamp": _ts(70)},
    {"event": "Created doctor Dr. Grace Wanjiku (grace.wanjiku)", "actor": "admin", "level": "admin", "timestamp": _ts(65)},
    {"event": "Created doctor Dr. Peter Kamau (peter.kamau)", "actor": "admin", "level": "admin", "timestamp": _ts(55)},
    {"event": "Created doctor Dr. Linda Nyambura (linda.nyambura)", "actor": "admin", "level": "admin", "timestamp": _ts(40)},
    {"event": "Bulk demo patients seeded (14 patients)", "actor": "system", "level": "info", "timestamp": _ts(30)},
    {"event": "Doctor Dr. James Doe logged in", "actor": "Dr. James Doe", "level": "info", "timestamp": _ts(18)},
    {"event": "Patient Sarah Mwangi — initial consult completed", "actor": "Dr. James Doe", "level": "info", "timestamp": _ts(18)},
    {"event": "AI diagnosis run for PAT-2024-0847 — Triage: Follow-up", "actor": "system", "level": "info", "timestamp": _ts(18)},
    {"event": "Doctor Dr. Mercy Okonkwo logged in", "actor": "Dr. Mercy Okonkwo", "level": "info", "timestamp": _ts(17)},
    {"event": "Patient John Kamau — Mohs surgery completed", "actor": "Dr. Mercy Okonkwo", "level": "info", "timestamp": _ts(16)},
    {"event": "Clinician override recorded for PAT-2024-0912", "actor": "Dr. Mercy Okonkwo", "level": "info", "timestamp": _ts(16)},
    {"event": "Doctor Dr. Sarah Kimani logged in", "actor": "Dr. Sarah Kimani", "level": "info", "timestamp": _ts(13)},
    {"event": "Dupilumab therapy initiated for PAT-2026-0109", "actor": "Dr. Grace Wanjiku", "level": "info", "timestamp": _ts(10)},
    {"event": "Doctor Dr. Grace Wanjiku logged in", "actor": "Dr. Grace Wanjiku", "level": "info", "timestamp": _ts(8)},
    {"event": "Offline policy update completed — 12 corrections applied", "actor": "system", "level": "info", "timestamp": _ts(6)},
    {"event": "Admin System Administrator logged in", "actor": "System Administrator", "level": "admin", "timestamp": _ts(5)},
    {"event": "Fairness audit report generated", "actor": "Admin", "level": "admin", "timestamp": _ts(4)},
    {"event": "Doctor Dr. Mercy Okonkwo changed triage for PAT-2025-0042", "actor": "Dr. Mercy Okonkwo", "level": "warning", "timestamp": _ts(2)},
    {"event": "Doctor Dr. James Doe logged in", "actor": "Dr. James Doe", "level": "info", "timestamp": _ts(1)},
    {"event": "System health check — all services operational", "actor": "system", "level": "info", "timestamp": _ts(0)},
]

# =========================================================================
#  NOTES — sample clinical notes for demo patients
# =========================================================================

NOTES = {
    "PAT-2024-0847": """Clinical Assessment:
Patient presents with a 3-month history of a pigmented lesion on the left upper back. Lesion exhibits asymmetry, border irregularity, and color variegation. ABCD criteria suggestive of dysplastic nevus vs. early melanoma.

Differential:
1. Superficial spreading melanoma (suspicious)
2. Dysplastic nevus (likely)
3. Seborrheic keratosis (less likely)

Plan:
- Recommend excisional biopsy with 2mm margins
- Follow-up in 2 weeks for histopathology results
- Sun protection counseling""",

    "PAT-2024-0912": """Follow-up Note:
6-month post-Mohs surgery follow-up. Wound healed well with minimal scarring. No clinical evidence of recurrence. Patient asymptomatic.

Assessment: Treatment complete — BCC fully excised with clear margins.
Plan: Discharge from routine follow-up. Annual skin checks advised.
Patient educated on sun protection and self-examination.""",

    "PAT-2025-0042": """Initial Consultation:
45-year-old male referred by GP for suspicious lesion on left forearm. Lesion is a rapidly growing nodule over 6 weeks. Patient has no prior skin cancer history but significant sun exposure as outdoor worker.

Exam: 10mm x 7mm raised nodule on left forearm extensor surface. Firm to palpation. Mild tenderness.

Impression: Suspicious for SCC. Urgent biopsy recommended.
Plan: Shave biopsy scheduled. Results in 5-7 business days.""",
}

# =========================================================================
#  SEED FUNCTION
# =========================================================================

def seed_all():
    print("Seeding demo data for Dermatology AI...")

    # Patients
    patients_path = HERE / "patients.json"
    patients_path.write_text(json.dumps(PATIENTS, indent=2, default=str), encoding="utf-8")
    print(f"  OK {len(PATIENTS)} patients written to patients.json")

    # Doctors
    doctors_path = HERE / "doctors.json"
    doctors_path.write_text(json.dumps(DOCTORS, indent=2, default=str), encoding="utf-8")
    print(f"  OK {len(DOCTORS['doctors'])} doctors + {len(DOCTORS['admins'])} admin written to doctors.json")

    # Activity
    activity_path = HERE / "activity.json"
    activity_path.write_text(json.dumps(ACTIVITY, indent=2), encoding="utf-8")
    print(f"  OK {len(ACTIVITY)} activity entries written to activity.json")

    # Notes
    notes_path = HERE / "notes.json"
    notes_path.write_text(json.dumps(NOTES, indent=2), encoding="utf-8")
    print(f"  OK {len(NOTES)} patient notes written to notes.json")

    print("\nDemo data seeded successfully!")
    print("\nLogin credentials:")
    print("  Admin:   username = admin     / password = admin123")
    print("  Doctors: email   = <doctor email> / password = Doctor123!")
    print("           e.g. j.doe@hospital.org / Doctor123!")


if __name__ == "__main__":
    seed_all()
