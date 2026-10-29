"""Domain constants shared by the RL, metrics and API layers.

Kept torch-free so that the API, metrics tracker and tests can import them
without pulling in the deep-learning stack.
"""

from __future__ import annotations

FITZPATRICK_LABELS = ["I", "II", "III", "IV", "V", "VI"]
NUM_FITZ_TYPES = len(FITZPATRICK_LABELS)

TRIAGE_NAMES = ["routine", "follow_up", "urgent"]
NUM_TRIAGE_ACTIONS = len(TRIAGE_NAMES)
TRIAGE_ACTIONS = list(range(NUM_TRIAGE_ACTIONS))

#: Actions that may be recorded for a case (used to validate API input).
VALID_TRIAGE_ACTIONS = frozenset(TRIAGE_ACTIONS)

#: Diagnosis labels used by the *triage* layer.
#:
#: ``atypical_lesion`` is a triage-catalogue category, not an output of the
#: three-class vision head: it models the clinically common
#: "indeterminate / needs short-interval review" case that warrants
#: ``follow_up``.  See ``MODEL_CARD.md`` for the distinction.
TRUE_LABEL_NAMES = ["benign", "melanoma", "kaposi_sarcoma", "atypical_lesion"]

#: Expected triage for each true label.
#:
#: benign -> routine, melanoma -> urgent, Kaposi sarcoma -> urgent,
#: atypical / indeterminate -> follow-up (short-interval review).
TRUE_LABEL_TO_TRIAGE = {0: 0, 1: 2, 2: 2, 3: 1}

#: Human-readable description used in docs and API responses.
TRIAGE_RATIONALE = {
    0: "Benign-appearing lesion: routine monitoring.",
    1: "Indeterminate / atypical lesion: short-interval follow-up.",
    2: "Suspicious for malignancy: urgent dermatology review / biopsy.",
}

#: Permission flags understood by the API.
DOCTOR_PERMISSIONS = [
    "view_patient",
    "edit_patient",
    "upload_images",
    "run_diagnosis",
    "override_triage",
    "view_analytics",
    "view_history",
    "export_data",
]
