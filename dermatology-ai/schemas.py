"""Pydantic request models with explicit validation.

Every field that can reach the browser has a length bound; identifiers have a
character pattern.  Free-text clinical fields are length-bounded but not
character-restricted (clinical text legitimately contains ``<``, ``>``, ``&``)
-- the dashboard escapes them at render time and that escaping is tested.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from constants import DOCTOR_PERMISSIONS, TRIAGE_ACTIONS, VALID_TRIAGE_ACTIONS

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NIN_RE = re.compile(r"^[A-Za-z0-9-]{0,20}$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{0,40}$")

PATIENT_STATUSES = {"active", "followup", "consultation", "completed"}
GENDERS = {"female", "male", "other", ""}
FITZ_VALUES = {"I", "II", "III", "IV", "V", "VI", ""}
VISIT_TAGS = {"routine", "followup", "urgent"}


def _reject_control_characters(value: str) -> str:
    if any(ord(ch) < 32 and ch not in ("\n", "\t") for ch in value):
        raise ValueError("Control characters are not allowed")
    return value


# ---------------------------------------------------------------------------
#  Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    remember_institution: bool = False


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        if not USERNAME_RE.match(value):
            raise ValueError("Username must be 3-32 characters: a-z, 0-9, dot, dash, underscore")
        return value


class AdminPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class DoctorResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=12, max_length=128)


# ---------------------------------------------------------------------------
#  Patients and visits
# ---------------------------------------------------------------------------

class PatientRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str = Field(min_length=1, max_length=120)
    id: str = Field(default="", max_length=32)
    age: str = Field(default="", max_length=40)
    gender: str = Field(default="", max_length=16)
    fitz: str = Field(default="", max_length=4)
    contact: str = Field(default="", max_length=40)
    history: str = Field(default="", max_length=5000)
    diagnosis: str = Field(default="", max_length=64)
    body_site: str = Field(default="", max_length=64)
    status: str = Field(default="active", max_length=16)

    @field_validator("name", "history", "diagnosis", "body_site")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        return _reject_control_characters(value)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if value and not IDENTIFIER_RE.match(value):
            raise ValueError("id must be 1-32 characters: letters, digits, dot, dash, underscore")
        return value

    @field_validator("contact")
    @classmethod
    def _contact(cls, value: str) -> str:
        if value and not PHONE_RE.match(value):
            raise ValueError("contact may only contain digits, spaces and + - ( ) .")
        return value

    @field_validator("fitz")
    @classmethod
    def _fitz(cls, value: str) -> str:
        value = value.upper()
        if value not in FITZ_VALUES:
            raise ValueError("fitz must be one of I..VI or empty")
        return value

    @field_validator("gender")
    @classmethod
    def _gender(cls, value: str) -> str:
        value = value.lower()
        if value not in GENDERS:
            raise ValueError("gender must be female, male, other or empty")
        return value

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        value = value.lower()
        if value not in PATIENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(PATIENT_STATUSES)}")
        return value


class VisitRequest(BaseModel):
    date: str = Field(default="", max_length=10)
    desc: str = Field(default="", max_length=2000)
    tag: str = Field(default="routine", max_length=16)
    diagnosis: str = Field(default="", max_length=200)
    ai_findings: str = Field(default="", max_length=4000)
    treatment_notes: str = Field(default="", max_length=4000)
    doctor_name: str = Field(default="", max_length=120)
    lesion_location: str = Field(default="", max_length=120)
    lesion_size: str = Field(default="", max_length=60)

    @field_validator("desc", "diagnosis", "ai_findings", "treatment_notes")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        return _reject_control_characters(value)

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        if value and not DATE_RE.match(value):
            raise ValueError("date must be YYYY-MM-DD or empty")
        return value

    @field_validator("tag")
    @classmethod
    def _tag(cls, value: str) -> str:
        value = value.lower()
        if value not in VISIT_TAGS:
            raise ValueError(f"tag must be one of {sorted(VISIT_TAGS)}")
        return value


class OverrideRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    clinician_action: int = Field(ge=min(TRIAGE_ACTIONS), le=max(TRIAGE_ACTIONS))

    @field_validator("clinician_action")
    @classmethod
    def _action(cls, value: int) -> int:
        if value not in VALID_TRIAGE_ACTIONS:
            raise ValueError("clinician_action must be 0 (routine), 1 (follow-up) or 2 (urgent)")
        return value


class NotesSaveRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=10_000)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str) -> str:
        return _reject_control_characters(value)


# ---------------------------------------------------------------------------
#  Doctors / admin
# ---------------------------------------------------------------------------

def _default_permissions() -> dict[str, bool]:
    return {permission: True for permission in DOCTOR_PERMISSIONS}


class DoctorCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    nin: str = Field(default="", max_length=20)
    title: str = Field(default="Dermatologist", max_length=80)
    permissions: dict[str, bool] = Field(default_factory=_default_permissions)

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME_RE.match(value):
            raise ValueError("username must be 3-32 characters: a-z, 0-9, dot, dash, underscore")
        return value

    @field_validator("name", "title")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        return _reject_control_characters(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not EMAIL_RE.match(value):
            raise ValueError("email is not a valid address")
        return value

    @field_validator("nin")
    @classmethod
    def _nin(cls, value: str) -> str:
        if not NIN_RE.match(value):
            raise ValueError("nin may only contain letters, digits and dashes (max 20)")
        return value

    @field_validator("permissions")
    @classmethod
    def _permissions(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = set(value) - set(DOCTOR_PERMISSIONS)
        if unknown:
            raise ValueError(f"unknown permissions: {sorted(unknown)}")
        return value


class DoctorUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=254)
    nin: Optional[str] = Field(default=None, max_length=20)
    title: Optional[str] = Field(default=None, max_length=80)
    active: Optional[bool] = None
    permissions: Optional[dict[str, bool]] = None
    photo: Optional[str] = Field(default=None, max_length=200_000)

    @field_validator("name", "title")
    @classmethod
    def _no_control_chars(cls, value: Optional[str]) -> Optional[str]:
        return _reject_control_characters(value) if value is not None else value

    @field_validator("email")
    @classmethod
    def _email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if value and not EMAIL_RE.match(value):
            raise ValueError("email is not a valid address")
        return value

    @field_validator("permissions")
    @classmethod
    def _permissions(cls, value: Optional[dict[str, bool]]) -> Optional[dict[str, bool]]:
        if value is None:
            return value
        unknown = set(value) - set(DOCTOR_PERMISSIONS)
        if unknown:
            raise ValueError(f"unknown permissions: {sorted(unknown)}")
        return value


class PermissionsUpdate(BaseModel):
    permissions: dict[str, bool]

    @field_validator("permissions")
    @classmethod
    def _permissions(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = set(value) - set(DOCTOR_PERMISSIONS)
        if unknown:
            raise ValueError(f"unknown permissions: {sorted(unknown)}")
        return value


class BulkDoctorAction(BaseModel):
    doctor_ids: list[str] = Field(min_length=1, max_length=200)
    active: bool


class LoginResponse(BaseModel):
    success: bool
    token: str
    physician: dict
    message: str
    sid: str
