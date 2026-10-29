"""FastAPI backend for the Dermatology AI clinical dashboard.

Design rules (see ``SECURITY.md`` and ``CODE_REVIEW.md``):

* **No fabricated data.**  If the model is not loaded, ``/api/diagnose`` returns
  ``503``.  There is no mock-diagnosis, mock-analytics or mock-history path.
* **One authorization dependency set.**  Admin routes use ``require_admin``;
  doctor routes use ``require_permission(<flag>)``.  Both live in ``auth.py``.
* **Bearer tokens, not cookies.**  No CSRF token is required or accepted,
  because a cross-site request cannot attach an ``Authorization`` header.
* Persistence is SQLite (``storage.py``); paths come from ``DATA_DIR``.

Environment
-----------
``DATA_DIR``                 directory for ``derma.db`` (default ``./data``)
``MODEL_CHECKPOINT_PATH``    DermatologyCBM state_dict; unset -> diagnose returns 503
``AGENT_CHECKPOINT_PATH``    PPO triage agent; unset -> triage reported as unavailable
``ADMIN_BOOTSTRAP_PASSWORD`` initial admin password (else generated and logged once)
``ALLOWED_ORIGINS``          comma-separated CORS allow-list
``TRUST_PROXY``              "1" to use the first ``X-Forwarded-For`` hop for rate limiting
``LOGIN_RATE_LIMIT``         per-IP limit for login endpoints (default ``5/minute``)
``DEMO_MODE``                "1" to seed demo data at startup (still no fake diagnoses)
"""

from __future__ import annotations

import csv
import io as python_io
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from PIL import Image
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from auth import (
    LoginThrottle,
    Session,
    SessionStore,
    check_password,
    current_token,
    hash_password,
    rate_limit_key,
    require_admin,
    require_auth,
    require_permission,
    validate_password,
)
from backend import Backend, BackendStatus, ModelUnavailable, file_sha256
from constants import (
    DOCTOR_PERMISSIONS,
    FITZPATRICK_LABELS,
    TRIAGE_NAMES,
    TRUE_LABEL_TO_TRIAGE,
)
from metrics_tracker import FairnessTracker
from schemas import (
    AdminLoginRequest,
    AdminPasswordChangeRequest,
    BulkDoctorAction,
    DoctorCreateRequest,
    DoctorResetPasswordRequest,
    DoctorUpdateRequest,
    LoginRequest,
    LoginResponse,
    NotesSaveRequest,
    OverrideRequest,
    PatientRequest,
    PermissionsUpdate,
    VisitRequest,
)
from storage import Store, migrate_legacy_json

# SECURITY: bound PIL's decompression-bomb protection globally.
Image.MAX_IMAGE_PIXELS = 10_000_000

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_REQUEST_SIZE = MAX_UPLOAD_SIZE + 1024 * 1024

CLASS_NAMES = ["benign", "melanoma", "kaposi_sarcoma"]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _data_dir(explicit: Optional[str | Path] = None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("DATA_DIR", APP_DIR / "data"))


def _audit(store: Store, session: Optional[Session], action: str, target: str = "",
           outcome: str = "ok", detail: str = "") -> None:
    actor = "anonymous"
    if session is not None:
        # ``name`` is missing on service accounts; never write NULL to a NOT NULL column.
        actor = (session.user.get("name") or session.user.get("username")
                 or session.user_id or session.sid or "unknown")
    store.append_audit(
        actor=actor,
        role=(session.role if session else "anonymous"),
        action=action,
        target=target,
        outcome=outcome,
        detail=detail,
    )


def _generate_password(length: int = 20) -> str:
    """Generate a random password that passes :func:`auth.validate_password`."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
    symbols = "!@#$%^&*-_=+?"
    while True:
        core = "".join(secrets.choice(alphabet) for _ in range(length - 4))
        candidate = (
            core[:length // 2]
            + secrets.choice("23456789")
            + secrets.choice(symbols)
            + secrets.choice("abcdefghijkmnopqrstuvwxyz")
            + secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
            + core[length // 2:]
        )
        if validate_password(candidate)[0]:
            return candidate


def _bootstrap_admin(store: Store) -> Optional[str]:
    """Ensure an ``admin`` account exists.  Returns the generated password once.

    SECURITY FIX: the generated password is written to
    ``<data_dir>/INITIAL_ADMIN_PASSWORD.txt`` with mode ``0600`` and only that
    path is logged.  The previous implementation logged the bcrypt *hash*, which
    is both a disclosure and useless to the operator.
    """
    if store.find_user(identifier="admin", role="admin"):
        return None

    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "")
    generated = False
    if not password:
        # SECURITY FIX: generate a password that satisfies the policy instead of
        # logging a bcrypt hash of a random string nobody can recover.
        password = _generate_password()
        generated = True

    store.create_user({
        "id": "admin-001",
        "role": "admin",
        "username": "admin",
        "email": os.environ.get("ADMIN_EMAIL", ""),
        "password": hash_password(password),
        "name": "System Administrator",
        "active": True,
    })

    if generated:
        credential_file = Path(store.data_dir) / "INITIAL_ADMIN_PASSWORD.txt"
        credential_file.write_text(password + "\n", encoding="utf-8")
        try:
            os.chmod(credential_file, 0o600)
        except OSError:  # pragma: no cover - exotic filesystems
            logger.warning("Could not restrict permissions on %s", credential_file)
        logger.warning("=" * 64)
        logger.warning(
            "Initial admin password written to %s (mode 0600). "
            "Sign in, change it, then delete the file.", credential_file,
        )
        logger.warning("=" * 64)
    return password


# ---------------------------------------------------------------------------
#  Application factory
# ---------------------------------------------------------------------------

def create_app(
    data_dir: Optional[str | Path] = None,
    model_path: Optional[str] = None,
    agent_path: Optional[str] = None,
    initialise_backend: bool = True,
    demo_mode: Optional[bool] = None,
) -> FastAPI:
    store = Store(_data_dir(data_dir))
    migrate_legacy_json(store, APP_DIR)

    sessions = SessionStore()
    throttle = LoginThrottle()
    tracker = FairnessTracker(store, export_path=str(store.data_dir / "case_history.csv"))
    backend = Backend(store, tracker, model_path=model_path, agent_path=agent_path)

    bootstrap_password = _bootstrap_admin(store)

    if demo_mode is None:
        demo_mode = os.environ.get("DEMO_MODE", "0") == "1"

    login_rate_limit = os.environ.get("LOGIN_RATE_LIMIT", "5/minute")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if demo_mode:
            # Explicit opt-in only: synthetic cohort, every record flagged
            # ``simulated``.  Never used for metrics ground truth.
            from seed_demo import seed_demo_patients

            seeded = await run_in_threadpool(seed_demo_patients, store)
            if seeded:
                logger.warning("DEMO_MODE: seeded %d simulated patients (not evaluation data)", seeded)
        if initialise_backend:
            await run_in_threadpool(backend.initialise)
        logger.info("Startup complete: model_ready=%s agent_ready=%s (%s)",
                    backend.status.model_ready, backend.status.agent_ready, backend.status.reason)
        yield
        store.close()

    app = FastAPI(
        title="Dermatology AI -- Clinical API",
        version="3.0.0",
        description=(
            "Research/educational decision-support prototype. Not a medical device. "
            "No clinical validation. Model output must never be used for treatment decisions."
        ),
        lifespan=lifespan,
    )

    app.state.store = store
    app.state.sessions = sessions
    app.state.throttle = throttle
    app.state.tracker = tracker
    app.state.backend = backend
    app.state.bootstrap_password = bootstrap_password
    app.state.demo_mode = demo_mode

    # -- middleware --------------------------------------------------------
    allowed_origins = [
        origin.strip()
        for origin in os.environ.get("ALLOWED_ORIGINS", "http://localhost:7860").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Reject oversized bodies before reading them into memory.
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        if declared > MAX_REQUEST_SIZE:
            return JSONResponse({"detail": "Request body too large."}, status_code=413)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # CSRF: there is no CSRF token, and that is intentional.
    #
    # Authentication is a bearer token in the ``Authorization`` header, never a
    # cookie (``tests/test_s0_2_authz_matrix.py::test_cookie_bearer_is_not_accepted``).
    # A cross-site page cannot attach that header without a CORS preflight, and
    # CORS only allows the configured ``ALLOWED_ORIGINS``.  The old per-route
    # CSRF check therefore added no protection -- it only broke every dashboard
    # write with a 403.  If cookies are ever introduced, add double-submit CSRF
    # (or SameSite=Strict) in the same change.  See SECURITY.md section 2.
    limiter = Limiter(key_func=rate_limit_key)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -- static ------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index():
        html_path = APP_DIR / "dashboard.html"
        if not html_path.exists():
            return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    def _image_response(name: str):
        path = APP_DIR / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path)

    @app.get("/dashboard.js", response_class=Response)
    def dashboard_js():
        # SECURITY FIX: the dashboard script is a separate file so the page can be
        # served under ``script-src 'self'`` with no 'unsafe-inline'.
        js_path = APP_DIR / "dashboard.js"
        if not js_path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return Response(js_path.read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/measles_child.jpg")
    def measles_image():
        return _image_response("measles_child.jpg")

    @app.get("/bg_vitiligo.jpg")
    def vitiligo_image():
        return _image_response("bg_vitiligo.jpg")

    @app.get("/bg_acne_skin.jpg")
    def acne_image():
        return _image_response("bg_acne_skin.jpg")

    @app.get("/robots.txt", response_class=HTMLResponse)
    def robots():
        return "User-agent: *\nDisallow: /\n"

    # -- health ------------------------------------------------------------
    @app.get("/api/health")
    def health():
        """Liveness only -- must never touch the model or the database."""
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/ready")
    def ready():
        status: BackendStatus = backend.status
        return {
            "model_ready": status.model_ready,
            "agent_ready": status.agent_ready,
            "reason": status.reason,
            "model_version": status.model_version,
            "weights_sha256": status.weights_sha256,
            "device": status.device,
            "demo_mode": bool(demo_mode),
        }

    # -- auth --------------------------------------------------------------
    @app.post("/api/login", response_model=LoginResponse)
    @limiter.limit(login_rate_limit)
    def login(request: Request, payload: LoginRequest):
        retry = throttle.retry_after(payload.email)
        if retry:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.",
                                headers={"Retry-After": str(retry)})

        doctor = store.find_user(identifier=payload.email, role="doctor")
        if doctor is None or not check_password(payload.password, doctor.get("password", "")):
            throttle.register_failure(payload.email)
            _audit(store, None, "login_failed", payload.email, outcome="denied")
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if not doctor.get("active", True):
            _audit(store, None, "login_deactivated", doctor.get("username", ""), outcome="denied")
            raise HTTPException(status_code=403, detail="This account has been deactivated.")

        throttle.reset(payload.email)
        store.update_user(doctor["id"], {"last_login": datetime.now(timezone.utc).isoformat()})
        token, session = sessions.create("doctor", doctor)
        _audit(store, session, "login", doctor.get("username", ""))
        physician = {
            "id": doctor["id"],
            "name": doctor.get("name", ""),
            "email": doctor.get("email", ""),
            "title": doctor.get("title", ""),
            "nin": doctor.get("nin", ""),
            "photo": doctor.get("photo", ""),
            "permissions": doctor.get("permissions", {}),
        }
        return LoginResponse(success=True, token=token, physician=physician,
                             message="Authentication successful.", sid=session.sid)

    @app.post("/api/admin/login")
    @limiter.limit(login_rate_limit)
    def admin_login(request: Request, payload: AdminLoginRequest):
        retry = throttle.retry_after(payload.username)
        if retry:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.",
                                headers={"Retry-After": str(retry)})

        admin = store.find_user(identifier=payload.username, role="admin")
        if admin is None or not check_password(payload.password, admin.get("password", "")):
            throttle.register_failure(payload.username)
            _audit(store, None, "admin_login_failed", payload.username, outcome="denied")
            raise HTTPException(status_code=401, detail="Invalid admin credentials.")

        throttle.reset(payload.username)
        token, session = sessions.create("admin", admin)
        _audit(store, session, "admin_login", admin.get("username", ""))
        return {
            "success": True,
            "token": token,
            "sid": session.sid,
            "admin": {
                "id": admin["id"],
                "name": admin.get("name", ""),
                "username": admin.get("username", ""),
                "role": "admin",
                "photo": admin.get("photo", ""),
            },
            "message": "Admin authenticated.",
        }

    @app.post("/api/logout")
    def logout(request: Request, session: Session = Depends(require_auth),
               authorization: str = Header("")):
        sessions.revoke_token(current_token(authorization))
        _audit(store, session, "logout", session.user.get("name", ""))
        return {"status": "logged_out"}

    @app.get("/api/me")
    def me(session: Session = Depends(require_auth)):
        return {"role": session.role, "user": session.user, "sid": session.sid}

    # -- patients ----------------------------------------------------------
    @app.get("/api/patients")
    def list_patients(
        session: Session = Depends(require_permission("view_patient")),
        query: str = Query("", max_length=120),
        fitz: str = Query("", max_length=4),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        patients = store.list_patients(query=query, fitz=fitz, limit=limit, offset=offset)
        _audit(store, session, "list_patients", f"n={len(patients)}")
        return {"patients": patients, "total": store.count_patients(), "limit": limit, "offset": offset}

    @app.get("/api/patients/{patient_id}")
    def get_patient(patient_id: str, session: Session = Depends(require_permission("view_patient"))):
        patient = store.get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found.")
        _audit(store, session, "read_patient", patient_id)
        return {"patient": patient}

    @app.post("/api/patients", status_code=201)
    def create_patient(payload: PatientRequest, session: Session = Depends(require_permission("edit_patient"))):
        patient = store.create_patient(payload.model_dump())
        _audit(store, session, "create_patient", patient["id"])
        return {"status": "created", "patient": patient}

    @app.put("/api/patients/{patient_id}")
    def update_patient(patient_id: str, payload: PatientRequest,
                       session: Session = Depends(require_permission("edit_patient"))):
        patient = store.update_patient(patient_id, payload.model_dump())
        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found.")
        _audit(store, session, "update_patient", patient_id)
        return {"status": "updated", "patient": patient}

    @app.delete("/api/patients/{patient_id}")
    def delete_patient(patient_id: str, session: Session = Depends(require_permission("edit_patient"))):
        if not store.delete_patient(patient_id):
            raise HTTPException(status_code=404, detail="Patient not found.")
        _audit(store, session, "delete_patient", patient_id)
        return {"status": "deleted", "patient_id": patient_id}

    # -- visits ------------------------------------------------------------
    @app.get("/api/patients/{patient_id}/visits")
    def list_visits(patient_id: str, session: Session = Depends(require_permission("view_history"))):
        if store.get_patient(patient_id) is None:
            raise HTTPException(status_code=404, detail="Patient not found.")
        return {"visits": store.list_visits(patient_id)}

    @app.post("/api/patients/{patient_id}/visits", status_code=201)
    def create_visit(patient_id: str, payload: VisitRequest,
                     session: Session = Depends(require_permission("edit_patient"))):
        visit = store.add_visit(patient_id, payload.model_dump())
        if visit is None:
            raise HTTPException(status_code=404, detail="Patient not found.")
        _audit(store, session, "create_visit", f"{patient_id}/{visit['id']}")
        return {"status": "created", "visit": visit}

    @app.delete("/api/patients/{patient_id}/visits/{visit_id}")
    def delete_visit(patient_id: str, visit_id: str,
                     session: Session = Depends(require_permission("edit_patient"))):
        if not store.delete_visit(patient_id, visit_id):
            raise HTTPException(status_code=404, detail="Visit not found.")
        _audit(store, session, "delete_visit", f"{patient_id}/{visit_id}")
        return {"status": "deleted", "visit_id": visit_id}

    # -- diagnosis ---------------------------------------------------------
    @app.post("/api/diagnose")
    async def diagnose(
        request: Request,
        file: UploadFile = File(...),
        fitzpatrick: int = Form(4),
        session: Session = Depends(require_permission("run_diagnosis")),
    ):
        if not 1 <= fitzpatrick <= 6:
            raise HTTPException(status_code=422, detail="Fitzpatrick type must be between 1 and 6.")
        if not backend.ready:
            raise HTTPException(status_code=503, detail={
                "error": "model_unavailable",
                "reason": backend.status.reason,
            })

        contents = await file.read(MAX_UPLOAD_SIZE + 1)
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

        import filetype
        kind = filetype.guess(contents)
        if kind is None or not kind.mime.startswith("image/"):
            raise HTTPException(status_code=422, detail="Uploaded file must be a valid image.")

        try:
            with Image.open(python_io.BytesIO(contents)) as handle:
                handle.verify()
            image = Image.open(python_io.BytesIO(contents)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Image decode failed: %s", exc)
            raise HTTPException(status_code=422, detail="Invalid or corrupted image file.") from exc

        array = np.array(image)
        try:
            result = await run_in_threadpool(backend.diagnose, array, fitzpatrick)
        except ModelUnavailable as exc:
            raise HTTPException(status_code=503, detail={
                "error": "model_unavailable", "reason": str(exc)}) from exc

        _audit(store, session, "diagnose", result["case_id"],
               detail=f"fitz={fitzpatrick} class={result['predicted_class']}")
        client_ip = request.client.host if request.client else "unknown"
        logger.info("diagnosis case=%s fitz=%s ip=%s", result["case_id"], fitzpatrick, client_ip)
        return result

    # -- overrides / notes -------------------------------------------------
    @app.post("/api/override")
    def submit_override(payload: OverrideRequest,
                        session: Session = Depends(require_permission("override_triage"))):
        if not tracker.register_override(payload.case_id, payload.clinician_action):
            raise HTTPException(status_code=404, detail="Unknown case_id.")
        _audit(store, session, "override", payload.case_id,
               detail=f"action={payload.clinician_action}")
        return {"status": "recorded", "case_id": payload.case_id, "action": payload.clinician_action}

    @app.post("/api/notes")
    def save_notes(payload: NotesSaveRequest,
                   session: Session = Depends(require_permission("edit_patient"))):
        notes = store.get_kv("notes", {}) or {}
        notes[payload.case_id] = payload.notes
        store.set_kv("notes", notes)
        _audit(store, session, "save_notes", payload.case_id)
        return {"status": "saved", "case_id": payload.case_id}

    @app.get("/api/notes/{case_id}")
    def get_notes(case_id: str, session: Session = Depends(require_permission("view_patient"))):
        notes = store.get_kv("notes", {}) or {}
        _audit(store, session, "read_notes", case_id)
        return {"case_id": case_id, "notes": notes.get(case_id, "")}

    # -- analytics / history / export --------------------------------------
    @app.get("/api/analytics")
    def analytics(session: Session = Depends(require_permission("view_analytics"))):
        return {"metrics": tracker.compute_metrics()}

    @app.get("/api/history")
    def history(
        session: Session = Depends(require_permission("view_history")),
        query: str = Query("", max_length=120),
        fitz_filter: int = Query(0, ge=0, le=6),
        limit: int = Query(50, ge=1, le=200),
    ):
        cases = tracker.cases
        if fitz_filter:
            cases = [c for c in cases if c.fitz_type == fitz_filter]
        if query:
            cases = [c for c in cases if query.lower() in c.case_id.lower()]
        rows = []
        for case in cases[-limit:]:
            final = case.clinician_triage if case.is_override else case.model_triage
            rows.append({
                "case_id": case.case_id,
                "date": case.timestamp[:10],
                "fitzpatrick": FITZPATRICK_LABELS[case.fitz_type - 1],
                "model_triage": TRIAGE_NAMES[case.model_triage] if case.model_triage is not None else "",
                "final_triage": TRIAGE_NAMES[final] if final is not None else "",
                "override": case.is_override,
                "ground_truth_confirmed": case.ground_truth_confirmed,
                "source": case.source,
            })
        _audit(store, session, "read_history", f"n={len(rows)}")
        return {"cases": rows}

    @app.get("/api/export")
    def export_cases(session: Session = Depends(require_permission("export_data"))):
        target = Path(store.data_dir) / "case_history.csv"
        tracker.export_csv(str(target))
        _audit(store, session, "export_cases", str(target))
        return FileResponse(str(target), media_type="text/csv", filename="case_history.csv")

    @app.post("/api/reset")
    def reset_tracker(session: Session = Depends(require_admin)):
        removed = tracker.reset()
        _audit(store, session, "reset_tracker", detail=f"removed={removed}")
        return {"status": "reset", "removed": removed}

    @app.post("/api/offline-update")
    def offline_update(session: Session = Depends(require_admin)):
        # The HITL buffer lives with the model runtime; without an agent there is
        # nothing to update, and we say so instead of pretending.
        if not backend.status.agent_ready:
            raise HTTPException(status_code=503, detail={
                "error": "agent_unavailable",
                "reason": backend.status.reason if not backend.status.agent_ready else "agent not loaded",
            })
        raise HTTPException(status_code=501, detail="Offline policy optimisation is not exposed by this build.")

    # -- admin: doctors ----------------------------------------------------
    @app.get("/api/admin/permissions")
    def list_permission_flags(session: Session = Depends(require_admin)):
        return {"permissions": DOCTOR_PERMISSIONS}

    @app.get("/api/admin/doctors")
    def list_doctors(session: Session = Depends(require_admin)):
        # ``list_users`` already strips password hashes (see storage.public_user).
        return {"doctors": store.list_users("doctor")}

    @app.post("/api/admin/doctors", status_code=201)
    def create_doctor(payload: DoctorCreateRequest, session: Session = Depends(require_admin)):
        if store.username_taken(payload.username):
            raise HTTPException(status_code=409, detail="Username already exists.")
        if store.email_taken(payload.email):
            raise HTTPException(status_code=409, detail="Email already exists.")
        valid, message = validate_password(payload.password)
        if not valid:
            raise HTTPException(status_code=400, detail=message)

        doctor = store.create_user({
            "role": "doctor",
            "username": payload.username,
            "password": hash_password(payload.password),
            "name": payload.name,
            "email": payload.email,
            "nin": payload.nin,
            "title": payload.title,
            "active": True,
            "permissions": payload.permissions,
        })
        _audit(store, session, "create_doctor", payload.username)
        return {"status": "created", "doctor": doctor}

    @app.post("/api/admin/doctors/bulk")
    def bulk_doctor_action(payload: BulkDoctorAction, session: Session = Depends(require_admin)):
        updated = 0
        for doctor_id in payload.doctor_ids:
            if store.update_user(doctor_id, {"active": payload.active}) is not None:
                updated += 1
                if not payload.active:
                    sessions.revoke_user(doctor_id)
        _audit(store, session, "bulk_doctor_action",
               detail=f"active={payload.active} n={updated}")
        return {"status": "updated", "count": updated}

    @app.get("/api/admin/doctors/{doctor_id}")
    def get_doctor(doctor_id: str, session: Session = Depends(require_admin)):
        doctor = store.get_user(doctor_id)
        if not doctor or doctor.get("role") != "doctor":
            raise HTTPException(status_code=404, detail="Doctor not found.")
        return {"doctor": {k: v for k, v in doctor.items() if k != "password"}}

    @app.put("/api/admin/doctors/{doctor_id}")
    def update_doctor(doctor_id: str, payload: DoctorUpdateRequest,
                      session: Session = Depends(require_admin)):
        doctor = store.get_user(doctor_id)
        if not doctor or doctor.get("role") != "doctor":
            raise HTTPException(status_code=404, detail="Doctor not found.")
        changes = payload.model_dump(exclude_none=True)
        if "email" in changes and store.email_taken(changes["email"]) and \
                changes["email"].lower() != (doctor.get("email") or "").lower():
            raise HTTPException(status_code=409, detail="Email already exists.")
        updated = store.update_user(doctor_id, changes)
        if changes.get("active") is False:
            sessions.revoke_user(doctor_id)
        _audit(store, session, "update_doctor", doctor_id,
               detail=",".join(sorted(changes.keys())))
        return {"status": "updated", "doctor": updated}

    @app.delete("/api/admin/doctors/{doctor_id}")
    def deactivate_doctor(doctor_id: str, session: Session = Depends(require_admin)):
        doctor = store.get_user(doctor_id)
        if not doctor or doctor.get("role") != "doctor":
            raise HTTPException(status_code=404, detail="Doctor not found.")
        store.update_user(doctor_id, {"active": False})
        revoked = sessions.revoke_user(doctor_id)
        _audit(store, session, "deactivate_doctor", doctor_id, detail=f"sessions_revoked={revoked}")
        return {"status": "deactivated", "doctor_id": doctor_id, "sessions_revoked": revoked}

    @app.post("/api/admin/doctors/{doctor_id}/reset-password")
    def reset_doctor_password(doctor_id: str, payload: DoctorResetPasswordRequest,
                              session: Session = Depends(require_admin)):
        doctor = store.get_user(doctor_id)
        if not doctor or doctor.get("role") != "doctor":
            raise HTTPException(status_code=404, detail="Doctor not found.")
        valid, message = validate_password(payload.new_password)
        if not valid:
            raise HTTPException(status_code=400, detail=message)
        store.update_user(doctor_id, {"password": hash_password(payload.new_password)})
        sessions.revoke_user(doctor_id)
        _audit(store, session, "reset_doctor_password", doctor_id)
        return {"status": "password_reset", "doctor_id": doctor_id}

    @app.put("/api/admin/doctors/{doctor_id}/permissions")
    def save_doctor_permissions(doctor_id: str, payload: PermissionsUpdate,
                                session: Session = Depends(require_admin)):
        doctor = store.get_user(doctor_id)
        if not doctor or doctor.get("role") != "doctor":
            raise HTTPException(status_code=404, detail="Doctor not found.")
        updated = store.update_user(doctor_id, {"permissions": payload.permissions})
        _audit(store, session, "update_permissions", doctor_id)
        return {"status": "saved", "doctor_id": doctor_id, "permissions": updated["permissions"]}

    @app.put("/api/doctors/me")
    def update_self(payload: DoctorUpdateRequest, session: Session = Depends(require_auth)):
        if session.role != "doctor":
            raise HTTPException(status_code=403, detail="Only doctor accounts have a profile.")
        allowed = {"name", "email", "nin", "title", "photo"}
        changes = {k: v for k, v in payload.model_dump(exclude_none=True).items() if k in allowed}
        if not changes:
            raise HTTPException(status_code=400, detail="No editable fields supplied.")
        if "email" in changes and store.email_taken(changes["email"]):
            raise HTTPException(status_code=409, detail="Email already exists.")
        store.update_user(session.user_id, changes)
        _audit(store, session, "update_self", session.user_id)
        return {"status": "updated"}

    @app.post("/api/admin/change-password")
    def admin_change_password(payload: AdminPasswordChangeRequest,
                              session: Session = Depends(require_admin)):
        admin = store.get_user(session.user_id)
        if admin is None or not check_password(payload.current_password, admin.get("password", "")):
            _audit(store, session, "change_password", outcome="denied")
            raise HTTPException(status_code=403, detail="Current password is incorrect.")
        valid, message = validate_password(payload.new_password)
        if not valid:
            raise HTTPException(status_code=400, detail=message)
        store.update_user(session.user_id, {"password": hash_password(payload.new_password)})
        _audit(store, session, "change_password", "admin")
        return {"status": "changed"}

    # -- admin: sessions / activity / exports ------------------------------
    @app.get("/api/admin/sessions")
    def list_sessions(session: Session = Depends(require_admin)):
        return {"active_sessions": sessions.list_active()}

    @app.post("/api/admin/sessions/{sid}/revoke")
    def revoke_session(sid: str, session: Session = Depends(require_admin)):
        if sid == session.sid:
            raise HTTPException(status_code=400, detail="Cannot revoke your own session.")
        if not sessions.revoke_sid(sid):
            raise HTTPException(status_code=404, detail="Session not found.")
        _audit(store, session, "revoke_session", sid)
        return {"status": "revoked", "sid": sid}

    @app.get("/api/admin/activity")
    def activity(
        session: Session = Depends(require_admin),
        query: str = Query("", max_length=120),
        level: str = Query("", max_length=16),
        limit: int = Query(50, ge=1, le=200),
    ):
        return {"activity": store.list_audit(query=query, level=level, limit=limit)[:50]}

    @app.get("/api/admin/patients/export")
    def export_patients(session: Session = Depends(require_admin)):
        patients = store.list_patients(limit=10_000)
        _buffer = python_io.StringIO()
        writer = csv.writer(_buffer)
        writer.writerow(["ID", "Name", "Age", "Gender", "Fitzpatrick", "Contact",
                         "Diagnosis", "Body Site", "Status", "Visit Count"])
        for patient in patients:
            writer.writerow([
                patient.get("id", ""), patient.get("name", ""), patient.get("age", ""),
                patient.get("gender", ""), patient.get("fitz", ""), patient.get("contact", ""),
                patient.get("diagnosis", ""), patient.get("body_site", ""),
                patient.get("status", ""), len(patient.get("visits", [])),
            ])
        _audit(store, session, "export_patients", f"n={len(patients)}")
        return StreamingResponse(
            python_io.BytesIO(_buffer.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=patients.csv"},
        )

    @app.get("/api/admin/analytics-data")
    def admin_analytics_data(session: Session = Depends(require_admin)):
        patients = store.list_patients(limit=10_000)
        diagnoses: dict[str, int] = {}
        fitz_counts: dict[str, int] = {}
        triage_counts = {"routine": 0, "followup": 0, "urgent": 0}
        status_counts = {"active": 0, "followup": 0, "consultation": 0, "completed": 0}
        for patient in patients:
            diagnosis = patient.get("diagnosis", "unknown")
            diagnoses[diagnosis] = diagnoses.get(diagnosis, 0) + 1
            fitz = patient.get("fitz", "Unknown")
            fitz_counts[fitz] = fitz_counts.get(fitz, 0) + 1
            status = patient.get("status", "active")
            status_counts[status] = status_counts.get(status, 0) + 1
            for visit in patient.get("visits", []):
                tag = visit.get("tag", "routine")
                if tag in triage_counts:
                    triage_counts[tag] += 1
        return {
            "diagnosis_distribution": [{"label": k, "value": v} for k, v in sorted(diagnoses.items())],
            "fitzpatrick_distribution": [{"label": k, "value": v} for k, v in sorted(fitz_counts.items())],
            "triage_distribution": [{"label": k, "value": v} for k, v in sorted(triage_counts.items())],
            "status_distribution": [{"label": k, "value": v} for k, v in sorted(status_counts.items())],
            "total_patients": len(patients),
        }

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dermatology AI Dashboard Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 7860)))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    uvicorn.run(create_app(), host=args.host, port=args.port, reload=args.reload)
