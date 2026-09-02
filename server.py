"""
FastAPI-based API server serving the Dermatology AI dashboard.

Provides REST endpoints that bridge the new HTML dashboard to the
existing Python backend (model, PPO agent, HITL pipeline, tracker).

Usage:
    python server.py                          # start on port 7860 (default)
    python server.py --port 8000              # custom port
    python server.py --reload                 # auto-reload on file changes
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import io as python_io
import csv
from typing import Optional, List

import bcrypt
import numpy as np
import uvicorn

try:
    import torch
except ImportError:
    torch = None
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Password helpers (bcrypt)
# ---------------------------------------------------------------------------

def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        logger.error("Password check failed — hash may be corrupted")
        return False

def _migrate_passwords(data: dict):
    """Hash any plaintext passwords found in the data. Idempotent."""
    changed = False
    for a in data.get("admins", []):
        p = a.get("password", "")
        if p and not p.startswith("$2b$"):
            a["password"] = _hash_password(p)
            changed = True
    for d in data.get("doctors", []):
        p = d.get("password", "")
        if p and not p.startswith("$2b$"):
            d["password"] = _hash_password(p)
            changed = True
    if changed:
        _save_doctors(data)

# ---------------------------------------------------------------------------
#  Auth sessions
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}
_SESSION_TTL = timedelta(hours=8)

def _create_session(user_info: dict) -> str:
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    _sessions[token] = {**user_info, "created_at": now.isoformat(), "expires_at": (now + _SESSION_TTL).isoformat()}
    return token

def _get_current_user(token: str = ""):
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    sess = _sessions[token]
    expires = sess.get("expires_at")
    if expires and datetime.now(timezone.utc) > datetime.fromisoformat(expires):
        del _sessions[token]
        raise HTTPException(status_code=401, detail="Session expired.")
    return sess

from fastapi import Header
async def require_auth(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "") if authorization else ""
    return _get_current_user(token)

async def require_admin(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "") if authorization else ""
    user = _get_current_user(token)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user

# ---------------------------------------------------------------------------
#  Activity log
# ---------------------------------------------------------------------------

ACTIVITY_PATH = Path(__file__).parent / "activity.json"

def _load_activity() -> list:
    if ACTIVITY_PATH.exists():
        try:
            return json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_activity(entries: list):
    ACTIVITY_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")

def _log_activity(event: str, actor: str = "system", level: str = "info"):
    entries = _load_activity()
    entries.append({
        "event": event,
        "actor": actor,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save_activity(entries[-200:])  # keep last 200

# ---------------------------------------------------------------------------
#  Patient persistence
# ---------------------------------------------------------------------------

PATIENTS_PATH = Path(__file__).parent / "patients.json"
NOTES_PATH = Path(__file__).parent / "notes.json"

def _load_patients() -> list:
    if PATIENTS_PATH.exists():
        try:
            return json.loads(PATIENTS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return []

def _save_patients(data: list):
    PATIENTS_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

def _load_notes() -> dict:
    if NOTES_PATH.exists():
        try:
            return json.loads(NOTES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def _save_notes(data: dict):
    NOTES_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

# ---------------------------------------------------------------------------
#  Pydantic models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_institution: bool = False


class LoginResponse(BaseModel):
    success: bool
    token: str
    physician: dict
    message: str


class PatientRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    name: str
    id: str = ""
    age: str = ""
    gender: str = ""
    fitz: str = ""
    contact: str = ""
    history: str = ""
    diagnosis: str = ""
    body_site: str = ""
    status: str = "active"

class VisitRequest(BaseModel):
    date: str = ""
    desc: str = ""
    tag: str = "routine"
    diagnosis: str = ""
    ai_findings: str = ""
    treatment_notes: str = ""
    doctor_name: str = ""
    lesion_location: str = ""
    lesion_size: str = ""

class OverrideRequest(BaseModel):
    case_id: str
    clinician_action: int


class NotesSaveRequest(BaseModel):
    case_id: str
    notes: str


# ---------------------------------------------------------------------------
#  Admin models
# ---------------------------------------------------------------------------

DOCTOR_PERMISSIONS = [
    "view_patient", "edit_patient", "upload_images",
    "run_diagnosis", "override_triage", "view_analytics",
    "view_history", "export_data",
]

DOCTORS_PATH = Path(__file__).parent / "doctors.json"


def _load_doctors() -> dict:
    if DOCTORS_PATH.exists():
        try:
            return json.loads(DOCTORS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {"admins": [], "doctors": []}

def _save_doctors(data: dict):
    DOCTORS_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _init_admin():
    data = _load_doctors()
    if not any(a.get("username") == "admin" for a in data["admins"]):
        data["admins"].append({
            "id": "admin-001",
            "username": "admin",
            "password": _hash_password("admin123"),
            "name": "System Administrator",
        })
    _migrate_passwords(data)
    _save_doctors(data)


def _seed_demo_patients():
    patients = _load_patients()
    if patients:
        return  # already seeded
    demo_active = {
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
                "lesion_size": "6mm x 4mm"
            },
            {
                "id": "VIS-20260402-0002",
                "date": "2026-04-02",
                "desc": "Routine skin check — no significant findings. ABCD criteria unremarkable.",
                "tag": "routine",
                "diagnosis": "No suspicious lesions detected",
                "ai_findings": "Asymmetry: 0.12 | Border: 0.08 | Color: 0.15 | Diameter: 0.10\nAll concept scores low. Triage: Routine monitoring.",
                "treatment_notes": "Annual skin check complete. Patient advised on sun protection and monthly self-exams. Return in 12 months.",
                "doctor_name": "Dr. James Doe",
                "lesion_location": "Full body",
                "lesion_size": "N/A"
            },
            {
                "id": "VIS-20251218-0003",
                "date": "2025-12-18",
                "desc": "Urgent referral — rapid-growing nodule on right forearm. Biopsy scheduled but patient deferred.",
                "tag": "urgent",
                "diagnosis": "Suspicious nodule (rule out SCC)",
                "ai_findings": "Asymmetry: 0.91 | Border: 0.88 | Color: 0.79 | Diameter: 0.85\nHigh concern. Triage: Urgent — Biopsy Recommended.",
                "treatment_notes": "Biopsy recommended and scheduled. Patient expressed anxiety and deferred procedure. Discussed risks of delay. Prescribed topical corticosteroid for inflammation. Follow-up in 1 week.",
                "doctor_name": "Dr. Mercy Okonkwo",
                "lesion_location": "Right forearm, dorsal aspect",
                "lesion_size": "12mm x 8mm, raised 3mm"
            }
        ],
        "created_at": "2025-12-01T00:00:00+00:00"
    }
    demo_completed = {
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
                "lesion_size": "8mm x 6mm"
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
                "lesion_size": "8mm x 6mm"
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
                "lesion_size": "N/A"
            }
        ],
        "created_at": "2025-10-10T00:00:00+00:00"
    }
    demo_followup = {
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
            {"id": "VIS-20260310-0001", "date": "2026-03-10", "desc": "Excision of dysplastic nevus on right shoulder. Clear margins achieved.", "tag": "followup", "diagnosis": "Dysplastic Nevus — excised", "ai_findings": "Moderate atypia. No melanoma identified.", "treatment_notes": "Excisional biopsy performed. Wound closed primarily. Follow-up in 3 months.", "doctor_name": "Dr. Mercy Okonkwo", "lesion_location": "Right shoulder", "lesion_size": "5mm x 4mm"},
            {"id": "VIS-20260610-0001", "date": "2026-06-10", "desc": "3-month follow-up — wound healed well. No signs of recurrence.", "tag": "routine", "diagnosis": "Healing well — no recurrence", "ai_findings": "Low risk. No suspicious features.", "treatment_notes": "Patient reassured. Next follow-up in 6 months.", "doctor_name": "Dr. Mercy Okonkwo", "lesion_location": "Right shoulder", "lesion_size": "N/A"}
        ],
        "created_at": "2026-03-08T00:00:00+00:00"
    }
    demo_consultation = {
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
            {"id": "VIS-20260601-0001", "date": "2026-06-01", "desc": "Initial consultation — rapid-growing nodule on left forearm. Biopsy scheduled.", "tag": "urgent", "diagnosis": "Suspicious nodule (rule out SCC)", "ai_findings": "Asymmetry: 0.78 | Border: 0.69 | Color: 0.71 | Diameter: 0.82\nHigh concern.", "treatment_notes": "Biopsy scheduled. Patient counseled on SCC risks and treatment options.", "doctor_name": "Dr. James Doe", "lesion_location": "Left forearm, extensor surface", "lesion_size": "10mm x 7mm, raised 2mm"}
        ],
        "created_at": "2026-06-01T00:00:00+00:00"
    }
    patients.append(demo_active)
    patients.append(demo_completed)
    patients.append(demo_followup)
    patients.append(demo_consultation)
    _save_patients(patients)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class DoctorCreateRequest(BaseModel):
    username: str
    password: str
    name: str
    email: str
    nin: str = ""
    title: str = "Dermatologist"
    permissions: dict = Field(default_factory=lambda: {p: True for p in DOCTOR_PERMISSIONS})


class DoctorUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    nin: Optional[str] = None
    title: Optional[str] = None
    active: Optional[bool] = None
    permissions: Optional[dict] = None
    photo: Optional[str] = None


class AdminPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class DoctorResetPasswordRequest(BaseModel):
    new_password: str


class BulkDoctorAction(BaseModel):
    doctor_ids: List[str]
    active: bool


class PermissionsUpdate(BaseModel):
    permissions: dict


# ---------------------------------------------------------------------------
#  App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    # Ensure admin data exists
    _init_admin()
    _seed_demo_patients()

    app = FastAPI(
        title="Dermatology AI — Clinical API",
        version="2.0.0",
        description="Backend API for the Dermatology AI Clinical Decision Support Dashboard",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    #  Lazy backend initialisation
    # -----------------------------------------------------------------------
    _backend = None

    def get_backend():
        nonlocal _backend
        if _backend is not None:
            return _backend
        try:
            from model import DermatologyCBM, CONCEPT_NAMES
            from rl_module import PPOAgent, DermTriageEnv, FITZPATRICK_LABELS, TRIAGE_NAMES
            from hitl_pipeline import HITLPipeline, OfflinePolicyOptimizer
            from metrics_tracker import FairnessTracker
            from main import generate_mock_cases, train_ppo_agent, seed_tracker

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            logger.info("Initialising HRNet-CBM model on %s ...", device)
            model = DermatologyCBM(
                num_classes=3, num_concepts=7,
                hrnet_name="hrnet_w18", pretrained_backbone=True,
                freeze_backbone=False,
            ).to(device)
            model = model.float()
            model.eval()

            logger.info("Initialising PPO agent ...")
            agent = PPOAgent(state_dim=7 + 6, action_dim=3, lr=3e-4, device=device)
            cases = generate_mock_cases(num_cases=500)
            agent_path = "agent_params.pt"
            if os.path.exists(agent_path):
                try:
                    agent.load(agent_path)
                    logger.info("Loaded saved PPO agent from %s", agent_path)
                except Exception as e:
                    logger.warning("Failed to load PPO agent, retraining: %s", e)
                    env = DermTriageEnv(num_concepts=7)
                    agent = train_ppo_agent(agent, env, cases, num_episodes=2000)
                    agent.save(agent_path)
            else:
                env = DermTriageEnv(num_concepts=7)
                agent = train_ppo_agent(agent, env, cases, num_episodes=2000)
                agent.save(agent_path)

            logger.info("Initialising HITL pipeline ...")
            hitl = HITLPipeline(agent, num_concepts=7)
            optimizer = OfflinePolicyOptimizer(agent, learning_rate=5e-5)

            logger.info("Initialising fairness tracker ...")
            tracker = FairnessTracker(persist_path="case_history.json")
            seed_tracker(agent, cases, tracker, hitl)

            from ui import AppState
            app_state = AppState(
                model=model, ppo_agent=agent, hitl=hitl,
                offline_optimizer=optimizer, tracker=tracker, device=device,
            )
            _backend = app_state
            logger.info("Backend initialised successfully.")
        except ImportError as e:
            logger.warning("Backend modules not available (%s). Running in API-only mode.", e)
            _backend = None
        return _backend

    # -----------------------------------------------------------------------
    #  Routes — Static files
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent / "dashboard.html"
        if not html_path.exists():
            return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/measles_child.jpg")
    async def get_measles_image():
        img_path = Path(__file__).parent / "measles_child.jpg"
        if not img_path.exists():
            return HTMLResponse(status_code=404)
        return FileResponse(img_path, media_type="image/jpeg")

    @app.get("/bg_vitiligo.jpg")
    async def get_bg_vitiligo():
        img_path = Path(__file__).parent / "bg_vitiligo.jpg"
        if not img_path.exists():
            return HTMLResponse(status_code=404)
        return FileResponse(img_path, media_type="image/jpeg")

    @app.get("/bg_acne_skin.jpg")
    async def get_bg_acne_skin():
        img_path = Path(__file__).parent / "bg_acne_skin.jpg"
        if not img_path.exists():
            return HTMLResponse(status_code=404)
        return FileResponse(img_path, media_type="image/jpeg")

    @app.get("/robots.txt", response_class=HTMLResponse)
    async def robots_txt():
        return """User-agent: *
Allow: /
Sitemap: https://dermai.onrender.com/sitemap.xml
"""

    @app.get("/sitemap.xml", response_class=HTMLResponse)
    async def sitemap_xml():
        return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://dermai.onrender.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""

    @app.get("/api/health")
    async def health():
        backend = get_backend()
        return {
            "status": "healthy",
            "backend_loaded": backend is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # -----------------------------------------------------------------------
    #  Routes — Login / Auth
    # -----------------------------------------------------------------------

    @app.post("/api/login", response_model=LoginResponse)
    async def login(req: LoginRequest):
        if not req.email or not req.password:
            raise HTTPException(status_code=400, detail="Email and password required")
        doc_data = _load_doctors()
        doctor = None
        for d in doc_data["doctors"]:
            if d.get("email") == req.email or d.get("username") == req.email.split("@")[0]:
                if _check_password(req.password, d.get("password", "")):
                    doctor = d
                    break
        if not doctor:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        doctor["last_login"] = datetime.now(timezone.utc).isoformat()
        _save_doctors(doc_data)
        name = doctor.get("name", req.email.split("@")[0].replace(".", " ").title())
        initials = "".join(w[0] for w in name.split()[:2])
        physician = {
            "name": name,
            "email": doctor.get("email", req.email),
            "initials": initials,
            "title": doctor.get("title", "Board-Certified Dermatologist"),
            "id": doctor.get("id", ""),
            "nin": doctor.get("nin", ""),
            "photo": doctor.get("photo", ""),
            "permissions": doctor.get("permissions", {}),
        }
        token = _create_session({"role": "doctor", **physician})
        _log_activity(f"Doctor {physician['name']} logged in", actor=physician["name"])
        return LoginResponse(
            success=True,
            token=token,
            physician=physician,
            message="Authentication successful. HIPAA-compliant session established.",
        )

    # -----------------------------------------------------------------------
    #  Routes — Patient
    # -----------------------------------------------------------------------

    @app.get("/api/patients")
    async def list_patients(query: str = "", fitz: str = "", _auth=Depends(require_auth)):
        patients = _load_patients()
        if query:
            q = query.lower()
            patients = [p for p in patients if q in p.get("name", "").lower() or q in p.get("id", "").lower()]
        if fitz:
            patients = [p for p in patients if p.get("fitz", "").lower() == fitz.lower()]
        return {"patients": patients}

    @app.get("/api/patients/{patient_id}")
    async def get_patient(patient_id: str, _auth=Depends(require_auth)):
        patients = _load_patients()
        for p in patients:
            if p["id"] == patient_id:
                return {"patient": p}
        raise HTTPException(status_code=404, detail="Patient not found.")

    @app.post("/api/patients", status_code=201)
    async def create_patient(req: PatientRequest, _auth=Depends(require_auth)):
        patients = _load_patients()
        new_id = req.id or f"PAT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{len(patients) + 1:04d}"
        existing_ids = {p["id"] for p in patients}
        if new_id in existing_ids:
            max_n = 0
            today = datetime.now(timezone.utc).strftime('%Y%m%d')
            for pid in existing_ids:
                if pid.startswith(f"PAT-{today}-"):
                    try:
                        n = int(pid.split("-")[-1])
                        if n > max_n:
                            max_n = n
                    except ValueError:
                        pass
            new_id = f"PAT-{today}-{max_n + 1:04d}"
            while new_id in existing_ids:
                max_n += 1
                new_id = f"PAT-{today}-{max_n + 1:04d}"
        patient = {
            "id": new_id,
            "name": req.name,
            "age": req.age,
            "gender": req.gender,
            "fitz": req.fitz,
            "contact": req.contact,
            "history": req.history,
            "diagnosis": req.diagnosis,
            "body_site": req.body_site,
            "status": req.status,
            "visits": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        patients.append(patient)
        _save_patients(patients)
        return {"status": "created", "patient": patient}

    @app.put("/api/patients/{patient_id}")
    async def update_patient(patient_id: str, req: PatientRequest, _auth=Depends(require_auth)):
        patients = _load_patients()
        for i, p in enumerate(patients):
            if p["id"] == patient_id:
                patients[i] = {
                    "id": patient_id,
                    "name": req.name,
                    "age": req.age,
                    "gender": req.gender,
                    "fitz": req.fitz,
                    "contact": req.contact,
                    "history": req.history,
                    "diagnosis": req.diagnosis,
                    "body_site": req.body_site,
                    "status": req.status,
                    "visits": p.get("visits", []),
                    "created_at": p.get("created_at", datetime.now(timezone.utc).isoformat()),
                }
                _save_patients(patients)
                return {"status": "updated", "patient": patients[i]}
        raise HTTPException(status_code=404, detail="Patient not found.")

    @app.delete("/api/patients/{patient_id}")
    async def delete_patient(patient_id: str, _auth=Depends(require_auth)):
        patients = _load_patients()
        new_list = [p for p in patients if p["id"] != patient_id]
        if len(new_list) == len(patients):
            raise HTTPException(status_code=404, detail="Patient not found.")
        _save_patients(new_list)
        return {"status": "deleted", "patient_id": patient_id}

    # -----------------------------------------------------------------------
    #  Routes — Visits
    # -----------------------------------------------------------------------

    @app.get("/api/patients/{patient_id}/visits")
    async def list_visits(patient_id: str, _auth=Depends(require_auth)):
        patients = _load_patients()
        for p in patients:
            if p["id"] == patient_id:
                return {"visits": p.get("visits", [])}
        raise HTTPException(status_code=404, detail="Patient not found.")

    @app.get("/api/patients/{patient_id}/visits/{visit_id}")
    async def get_visit(patient_id: str, visit_id: str, _auth=Depends(require_auth)):
        patients = _load_patients()
        for p in patients:
            if p["id"] == patient_id:
                for v in p.get("visits", []):
                    if v.get("id") == visit_id:
                        return {"visit": v}
                raise HTTPException(status_code=404, detail="Visit not found.")
        raise HTTPException(status_code=404, detail="Patient not found.")

    @app.post("/api/patients/{patient_id}/visits", status_code=201)
    async def create_visit(patient_id: str, req: VisitRequest, _auth=Depends(require_auth)):
        patients = _load_patients()
        for i, p in enumerate(patients):
            if p["id"] == patient_id:
                visits = p.get("visits", [])
                visit = {
                    "id": f"VIS-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}",
                    "date": req.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "desc": req.desc,
                    "tag": req.tag,
                    "diagnosis": req.diagnosis,
                    "ai_findings": req.ai_findings,
                    "treatment_notes": req.treatment_notes,
                    "doctor_name": req.doctor_name,
                    "lesion_location": req.lesion_location,
                    "lesion_size": req.lesion_size,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                visits.append(visit)
                patients[i]["visits"] = visits
                _save_patients(patients)
                return {"status": "created", "visit": visit}
        raise HTTPException(status_code=404, detail="Patient not found.")

    @app.delete("/api/patients/{patient_id}/visits/{visit_id}")
    async def delete_visit(patient_id: str, visit_id: str, _auth=Depends(require_auth)):
        patients = _load_patients()
        for i, p in enumerate(patients):
            if p["id"] == patient_id:
                visits = p.get("visits", [])
                new_visits = [v for v in visits if v.get("id") != visit_id]
                if len(new_visits) == len(visits):
                    raise HTTPException(status_code=404, detail="Visit not found.")
                patients[i]["visits"] = new_visits
                _save_patients(patients)
                return {"status": "deleted", "visit_id": visit_id}
        raise HTTPException(status_code=404, detail="Patient not found.")

    # -----------------------------------------------------------------------
    #  Routes — Diagnosis
    # -----------------------------------------------------------------------

    @app.post("/api/diagnose")
    async def diagnose(
        file: UploadFile = File(...),
        fitzpatrick: int = Form(4),
    ):
        backend = get_backend()
        if backend is None:
            return _mock_diagnosis()

        if fitzpatrick < 1 or fitzpatrick > 6:
            raise HTTPException(status_code=422, detail="Fitzpatrick type must be between 1 and 6.")
        if file.content_type and not file.content_type.startswith("image/"):
            raise HTTPException(status_code=422, detail="Uploaded file must be an image.")

        contents = await file.read()
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(contents)).convert("RGB")
        arr = np.array(img)

        from ui import preprocess
        tensor = preprocess(arr, backend.device)

        with torch.no_grad():
            logits, concepts = backend.model(tensor)
            pred_class = logits.argmax(dim=1).item()

        from model import CONCEPT_NAMES
        concept_dict = {
            CONCEPT_NAMES[i]: round(concepts[0, i].item(), 4)
            for i in range(len(CONCEPT_NAMES))
        }

        state_vec = np.concatenate([
            concepts[0].cpu().numpy(),
            np.eye(6, dtype=np.float32)[fitzpatrick - 1],
        ])
        model_action = backend.ppo_agent.evaluate(state_vec)

        from rl_module import TRIAGE_NAMES, FITZPATRICK_LABELS
        triage_name = TRIAGE_NAMES[model_action]

        case_id = backend.next_case_id()
        from metrics_tracker import CaseRecord
        backend.tracker.register_case(CaseRecord(
            case_id=case_id, fitz_type=fitzpatrick,
            true_label=pred_class, model_triage=model_action,
            concepts=concepts[0].cpu().numpy().tolist(),
        ))

        return {
            "case_id": case_id,
            "concepts": concept_dict,
            "triage": triage_name,
            "triage_index": model_action,
            "predicted_class": ["benign", "melanoma", "kaposi_sarcoma"][pred_class],
            "fitzpatrick": fitzpatrick,
            "fitzpatrick_label": FITZPATRICK_LABELS[fitzpatrick - 1],
        }

    def _mock_diagnosis():
        return {
            "case_id": f"MOCK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}",
            "concepts": {
                "asymmetry": 0.82, "border_irregularity": 0.73,
                "color_variegation": 0.65, "diameter_large": 0.44,
                "melanin_density": 0.31, "inflammation": 0.58,
                "ulceration": 0.12,
            },
            "triage": "follow_up",
            "triage_index": 1,
            "predicted_class": "melanoma",
            "fitzpatrick": 4,
            "fitzpatrick_label": "Olive",
        }

    # -----------------------------------------------------------------------
    #  Routes — Overrides
    # -----------------------------------------------------------------------

    @app.post("/api/override")
    async def submit_override(req: OverrideRequest, _auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            return {"status": "recorded", "case_id": req.case_id, "action": req.clinician_action}
        backend.tracker.register_override(req.case_id, req.clinician_action)
        return {"status": "recorded", "case_id": req.case_id, "action": req.clinician_action}

    # -----------------------------------------------------------------------
    #  Routes — Notes
    # -----------------------------------------------------------------------

    @app.post("/api/notes")
    async def save_notes(req: NotesSaveRequest, _auth=Depends(require_auth)):
        notes = _load_notes()
        notes[req.case_id] = req.notes
        _save_notes(notes)
        return {"status": "saved", "case_id": req.case_id}

    @app.get("/api/notes/{case_id}")
    async def get_notes(case_id: str, _auth=Depends(require_auth)):
        notes = _load_notes()
        return {"case_id": case_id, "notes": notes.get(case_id, "")}

    # -----------------------------------------------------------------------
    #  Routes — Analytics
    # -----------------------------------------------------------------------

    @app.get("/api/analytics")
    async def get_analytics(_auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            return {"metrics": _mock_analytics()}
        try:
            metrics = backend.tracker.compute_metrics()
        except Exception:
            metrics = _mock_analytics()
        return {"metrics": metrics}

    def _mock_analytics():
        return {
            "total_cases": 487,
            "overall_accuracy": 0.843,
            "override_rate": 0.12,
            "accuracy_gap": 0.027,
            "legacy_accuracy": 0.872,
            "target_accuracy": 0.845,
        }

    # -----------------------------------------------------------------------
    #  Routes — History
    # -----------------------------------------------------------------------

    @app.get("/api/history")
    async def get_history(query: str = "", fitz_filter: int = 0, limit: int = 50, _auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            return {"cases": _mock_history(limit)}
        from ui import search_history
        import pandas as pd
        df = search_history(query, fitz_filter, backend)
        if isinstance(df, pd.DataFrame) and "Info" not in df.columns:
            return {"cases": df.head(limit).to_dict(orient="records")}
        return {"cases": []}

    def _mock_history(limit=50):
        try:
            from rl_module import FITZPATRICK_LABELS, TRIAGE_NAMES
        except ImportError:
            FITZPATRICK_LABELS = ["", "Light", "Fair", "Olive", "Brown", "Dark Brown", "Black"]
            TRIAGE_NAMES = ["routine", "follow_up", "urgent"]
        import random
        cases = []
        for i in range(min(limit, 20)):
            fitz = random.randint(1, 6)
            mt = random.randint(0, 2)
            override = random.random() < 0.12
            cases.append({
                "case_id": f"UI-20260522-{i+1:04d}",
                "date": "2026-05-22",
                "fitzpatrick": FITZPATRICK_LABELS[fitz - 1],
                "model_triage": TRIAGE_NAMES[mt],
                "final_triage": TRIAGE_NAMES[random.randint(0, 2)] if override else TRIAGE_NAMES[mt],
                "override": override,
            })
        return cases

    # -----------------------------------------------------------------------
    #  Routes — System
    # -----------------------------------------------------------------------

    @app.post("/api/offline-update")
    async def run_offline_update(_auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            return {"status": "simulated", "message": "Offline update completed (mock)."}
        buffer = backend.hitl.correction_buffer
        if len(buffer) < 2:
            return {"status": "skipped", "message": "Not enough overrides (need >= 2)."}
        metrics = backend.optimizer.optimise(buffer)
        backend.tracker.snapshot("after_offline_update")
        backend.tracker.save()
        return {
            "status": "completed",
            "policy_loss": metrics.get("policy_loss", "N/A"),
            "buffer_size": len(buffer),
        }

    @app.get("/api/export")
    async def export_data(_auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            output = python_io.StringIO()
            w = csv.writer(output)
            w.writerow(["case_id", "timestamp", "fitz_type", "true_label", "model_triage", "clinician_triage", "is_override", "reward"])
            return StreamingResponse(python_io.BytesIO(output.getvalue().encode()), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=case_history.csv"})
        backend.tracker.export_csv()
        csv_path = Path(__file__).parent / "case_history.csv"
        if csv_path.exists():
            return FileResponse(str(csv_path), media_type="text/csv", filename="case_history.csv")
        return {"status": "exported", "filename": "case_history.csv"}

    @app.post("/api/reset")
    async def reset_tracker(_auth=Depends(require_auth)):
        backend = get_backend()
        if backend is None:
            return {"status": "reset"}
        backend.tracker.cases.clear()
        backend.tracker._snapshots.clear()
        backend.tracker.save()
        return {"status": "reset"}

    # -----------------------------------------------------------------------
    #  Routes — Admin
    # -----------------------------------------------------------------------

    @app.get("/api/admin/permissions")
    async def get_permissions(_auth=Depends(require_admin)):
        return {"permissions": DOCTOR_PERMISSIONS}

    @app.post("/api/admin/login")
    async def admin_login(req: AdminLoginRequest):
        data = _load_doctors()
        for admin in data["admins"]:
            if admin["username"] == req.username and _check_password(req.password, admin.get("password", "")):
                info = {"id": admin["id"], "name": admin["name"], "username": admin["username"], "role": "admin", "photo": admin.get("photo", "")}
                token = _create_session(info)
                _log_activity(f"Admin {admin['name']} logged in", actor=admin["name"], level="admin")
                return {
                    "success": True,
                    "token": token,
                    "admin": info,
                    "message": "Admin authenticated.",
                }
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")

    @app.get("/api/admin/doctors")
    async def list_doctors(_auth=Depends(require_admin)):
        data = _load_doctors()
        doctors = []
        for d in data["doctors"]:
            doc = {k: v for k, v in d.items() if k != "password"}
            doctors.append(doc)
        return {"doctors": doctors}

    @app.post("/api/admin/doctors")
    async def create_doctor(req: DoctorCreateRequest, _auth=Depends(require_admin)):
        try:
            data = _load_doctors()
            if any(d["username"] == req.username for d in data["doctors"]):
                return JSONResponse(
                    status_code=409,
                    content={"detail": "Username already exists.", "field": "username"}
                )
            if any(d["email"] == req.email for d in data["doctors"]):
                return JSONResponse(
                    status_code=409,
                    content={"detail": "Email already exists.", "field": "email"}
                )
            doctor = {
                "id": f"doc-{uuid.uuid4().hex[:6]}",
                "username": req.username,
                "password": _hash_password(req.password),
                "name": req.name,
                "email": req.email,
                "nin": req.nin,
                "title": req.title,
                "active": True,
                "permissions": req.permissions,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_login": None,
            }
            data["doctors"].append(doctor)
            _save_doctors(data)
            _log_activity(f"Created doctor {req.name} ({req.username})", actor="admin", level="admin")
            return {"status": "created", "doctor": {k: v for k, v in doctor.items() if k != "password"}}
        except HTTPException:
            raise
        except Exception:
            logger.exception("Failed to create doctor")
            return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    @app.get("/api/admin/doctors/{doctor_id}")
    async def get_doctor(doctor_id: str, _auth=Depends(require_admin)):
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                return {"doctor": {k: v for k, v in d.items() if k != "password"}}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    @app.put("/api/admin/doctors/{doctor_id}")
    async def update_doctor(doctor_id: str, req: DoctorUpdateRequest, _auth=Depends(require_admin)):
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                if req.name is not None: d["name"] = req.name
                if req.email is not None: d["email"] = req.email
                if req.nin is not None: d["nin"] = req.nin
                if req.title is not None: d["title"] = req.title
                if req.active is not None: d["active"] = req.active
                if req.permissions is not None: d["permissions"] = req.permissions
                if req.photo is not None: d["photo"] = req.photo
                _save_doctors(data)
                return {"status": "updated", "doctor": {k: v for k, v in d.items() if k != "password"}}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    @app.delete("/api/admin/doctors/{doctor_id}")
    async def deactivate_doctor(doctor_id: str, _auth=Depends(require_admin)):
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                d["active"] = False
                _save_doctors(data)
                return {"status": "deactivated", "doctor_id": doctor_id}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    @app.post("/api/admin/doctors/{doctor_id}/reset-password")
    async def reset_doctor_password(doctor_id: str, req: DoctorResetPasswordRequest, _auth=Depends(require_admin)):
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                d["password"] = _hash_password(req.new_password)
                _save_doctors(data)
                return {"status": "password_reset", "doctor_id": doctor_id}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    @app.put("/api/admin/doctors/{doctor_id}/permissions")
    async def save_doctor_permissions(doctor_id: str, req: PermissionsUpdate, _auth=Depends(require_admin)):
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                d["permissions"] = req.permissions
                _save_doctors(data)
                return {"status": "saved", "doctor_id": doctor_id, "permissions": d["permissions"]}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    # -----------------------------------------------------------------------
    #  Routes — Doctor self-service (update own profile)
    # -----------------------------------------------------------------------

    @app.put("/api/doctors/me")
    async def update_self(req: DoctorUpdateRequest, _auth=Depends(require_auth)):
        doctor_id = _auth.get("id")
        data = _load_doctors()
        for d in data["doctors"]:
            if d["id"] == doctor_id:
                if req.name is not None: d["name"] = req.name
                if req.email is not None: d["email"] = req.email
                if req.nin is not None: d["nin"] = req.nin
                if req.title is not None: d["title"] = req.title
                if req.photo is not None: d["photo"] = req.photo
                _save_doctors(data)
                return {"status": "updated"}
        raise HTTPException(status_code=404, detail="Doctor not found.")

    # -----------------------------------------------------------------------
    #  Routes — Admin: Change own password
    # -----------------------------------------------------------------------

    @app.post("/api/admin/change-password")
    async def admin_change_password(req: AdminPasswordChangeRequest, _auth=Depends(require_admin)):
        data = _load_doctors()
        admin_id = _auth.get("id")
        for admin in data["admins"]:
            if admin["id"] == admin_id and _check_password(req.current_password, admin.get("password", "")):
                admin["password"] = _hash_password(req.new_password)
                _save_doctors(data)
                _log_activity("Admin changed password", actor="admin", level="admin")
                return {"status": "changed"}
        raise HTTPException(status_code=403, detail="Current password is incorrect.")

    # -----------------------------------------------------------------------
    #  Routes — Admin: Bulk doctor actions
    # -----------------------------------------------------------------------

    @app.post("/api/admin/doctors/bulk")
    async def bulk_doctor_action(req: BulkDoctorAction, _auth=Depends(require_admin)):
        data = _load_doctors()
        count = 0
        for d in data["doctors"]:
            if d["id"] in req.doctor_ids:
                d["active"] = req.active
                count += 1
        _save_doctors(data)
        _log_activity(f"Bulk {'activated' if req.active else 'deactivated'} {count} doctor(s)", actor="admin", level="admin")
        return {"status": "updated", "count": count}

    # -----------------------------------------------------------------------
    #  Routes — Admin: Active sessions
    # -----------------------------------------------------------------------

    @app.get("/api/admin/sessions")
    async def list_sessions(_auth=Depends(require_admin)):
        now = datetime.now(timezone.utc)
        active = []
        expired = []
        for token, sess in list(_sessions.items()):
            expires = sess.get("expires_at")
            if expires and now > datetime.fromisoformat(expires):
                expired.append(token)
            else:
                active.append({"name": sess.get("name"), "role": sess.get("role"), "expires_at": sess.get("expires_at")})
        for t in expired:
            del _sessions[t]
        return {"active_sessions": active, "count": len(active)}

    @app.post("/api/admin/sessions/{token}/revoke")
    async def revoke_session(token: str, authorization: str = Header(""), _auth=Depends(require_admin)):
        current_token = authorization.replace("Bearer ", "") if authorization else ""
        if token == current_token:
            raise HTTPException(status_code=400, detail="Cannot revoke your own session.")
        if token in _sessions:
            del _sessions[token]
            return {"status": "revoked"}
        raise HTTPException(status_code=404, detail="Session not found.")

    # -----------------------------------------------------------------------
    #  Routes — Admin: Activity log with filtering
    # -----------------------------------------------------------------------

    @app.get("/api/admin/activity")
    async def get_activity(query: str = "", level: str = "", _auth=Depends(require_admin)):
        entries = _load_activity()[-200:]
        if query:
            q = query.lower()
            entries = [e for e in entries if q in e.get("event", "").lower() or q in e.get("actor", "").lower()]
        if level:
            entries = [e for e in entries if e.get("level", "") == level]
        return {"activity": entries[-50:]}

    # -----------------------------------------------------------------------
    #  Routes — Admin: Patient CSV export
    # -----------------------------------------------------------------------

    @app.get("/api/admin/patients/export")
    async def export_patients_csv(_auth=Depends(require_admin)):
        patients = _load_patients()
        output = python_io.StringIO()
        w = csv.writer(output)
        w.writerow(["ID", "Name", "Age", "Gender", "Fitzpatrick", "Contact", "Diagnosis", "Body Site", "Status", "Visit Count"])
        for p in patients:
            w.writerow([
                p.get("id", ""), p.get("name", ""), p.get("age", ""),
                p.get("gender", ""), p.get("fitz", ""), p.get("contact", ""),
                p.get("diagnosis", ""), p.get("body_site", ""), p.get("status", ""),
                len(p.get("visits", [])),
            ])
        return StreamingResponse(
            python_io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=patients.csv"},
        )

    # -----------------------------------------------------------------------
    #  Routes — Admin: Analytics data for charts
    # -----------------------------------------------------------------------

    @app.get("/api/admin/analytics-data")
    async def admin_analytics_data(_auth=Depends(require_admin)):
        patients = _load_patients()
        diagnoses = {}
        fitz_counts = {}
        triage_counts = {"routine": 0, "followup": 0, "urgent": 0}
        status_counts = {"active": 0, "followup": 0, "consultation": 0, "completed": 0}
        for p in patients:
            d = p.get("diagnosis", "unknown")
            diagnoses[d] = diagnoses.get(d, 0) + 1
            f = p.get("fitz", "Unknown")
            fitz_counts[f] = fitz_counts.get(f, 0) + 1
            s = p.get("status", "active")
            status_counts[s] = status_counts.get(s, 0) + 1
            for v in p.get("visits", []):
                t = v.get("tag", "routine")
                if t in triage_counts:
                    triage_counts[t] += 1
        return {
            "diagnosis_distribution": [{"label": k, "value": v} for k, v in sorted(diagnoses.items())],
            "fitzpatrick_distribution": [{"label": k, "value": v} for k, v in sorted(fitz_counts.items())],
            "triage_distribution": [{"label": k, "value": v} for k, v in sorted(triage_counts.items())],
            "status_distribution": [{"label": k, "value": v} for k, v in sorted(status_counts.items())],
            "total_patients": len(patients),
        }

    return app


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Dermatology AI Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=7860, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on file changes")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    app = create_app()
    logger.info("Dermatology AI Dashboard server starting on %s:%d", args.host, args.port)

    try:
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Server shut down gracefully.")
    except SystemExit:
        pass
