"""
HPIDraft schema for constrained HPI generation.

The HPI agent will emit a JSON object conforming to this schema. The
schema constrains EVERY clinical assertion to a small set of validated
fields. The downstream renderer converts the JSON into clinical prose
via deterministic templates — the LLM never writes free prose, so it
cannot introduce contradictions, hallucinate values, mismatch sex
pronouns, or insert meta-commentary.

Design principles:
  - Every value the LLM emits must be CROSS-CHECKABLE against
    deterministic ground truth (PSA Curve, PSH, PATHOLOGY, etc.).
  - All controlled vocabularies are explicit enums.
  - Optional fields can be null/empty when truly absent — the
    renderer skips them rather than inventing content.
  - Dates are ISO-8601 strings (YYYY-MM-DD or YYYY-MM or YYYY) to
    eliminate format ambiguity.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Controlled vocabularies (enums)
# ---------------------------------------------------------------------------

VISIT_TYPES = {"follow-up", "consult", "new-patient", "post-op", "pre-op"}

SEX_VALUES = {"male", "female"}

TREATMENT_MODALITIES = {
    "prostatectomy", "radiation", "brachytherapy", "focal-therapy",
    "active-surveillance", "ADT", "chemotherapy", "immunotherapy",
    "TURP", "TURBT", "nephrectomy", "cystectomy",
    "ureteroscopy", "shock-wave-lithotripsy", "PCNL",
    "orchiectomy", "varicocelectomy", "hydrocelectomy",
    "cystoscopy-with-treatment",
}

TREATMENT_STATUSES = {"completed", "ongoing", "discontinued", "declined", "scheduled"}

PSA_DIRECTIONS = {"increased", "decreased", "stable", "fluctuating"}

PROCEDURE_TYPES = {
    "biopsy", "cystoscopy", "urodynamics", "mri", "ct", "ultrasound",
    "psma-pet", "bone-scan", "dexa", "iv-pyelogram",
    "retrograde-pyelogram", "voiding-cystogram",
}

# Common LLM variants that should normalize to canonical enum values.
# Applied case-insensitively before enum membership check, so the LLM
# can emit human-readable forms without triggering ENUM_VIOLATION.
_ENUM_SYNONYMS = {
    # PROCEDURE_TYPES
    "prostate biopsy": "biopsy",
    "transrectal biopsy": "biopsy",
    "tru-cut biopsy": "biopsy",
    "needle biopsy": "biopsy",
    "renal biopsy": "biopsy",
    "kidney biopsy": "biopsy",
    "bladder biopsy": "biopsy",
    "mp-mri": "mri",
    "mpmri": "mri",
    "prostate mri": "mri",
    "ct scan": "ct",
    "ct urogram": "ct",
    "ct abdomen/pelvis": "ct",
    "renal ultrasound": "ultrasound",
    "transrectal ultrasound": "ultrasound",
    "trus": "ultrasound",
    "psma pet": "psma-pet",
    "bone scan": "bone-scan",
    "dexa scan": "dexa",
    # TREATMENT_MODALITIES
    "radical prostatectomy": "prostatectomy",
    "robotic prostatectomy": "prostatectomy",
    "open prostatectomy": "prostatectomy",
    "rrp": "prostatectomy",
    "rarp": "prostatectomy",
    "xrt": "radiation",
    "ebrt": "radiation",
    "external beam radiation": "radiation",
    "external beam radiotherapy": "radiation",
    "radiation therapy": "radiation",
    "radiotherapy": "radiation",
    "imrt": "radiation",
    "sbrt": "radiation",
    "stereotactic body radiation therapy": "radiation",
    "androgen deprivation therapy": "ADT",
    "adt": "ADT",
    "hormone therapy": "ADT",
    "hormonal therapy": "ADT",
    "active surveillance": "active-surveillance",
    "watchful waiting": "active-surveillance",
    "focal therapy": "focal-therapy",
    "hifu": "focal-therapy",
    "cryoablation": "focal-therapy",
    "cryotherapy": "focal-therapy",
    "partial nephrectomy": "nephrectomy",
    "radical nephrectomy": "nephrectomy",
    "robotic nephrectomy": "nephrectomy",
    # VISIT_TYPES
    "followup": "follow-up",
    "f/u": "follow-up",
    "new patient": "new-patient",
    "preop": "pre-op",
    "postop": "post-op",
    # SEX_VALUES
    "m": "male",
    "f": "female",
}


def normalize_enum_value(value: Any) -> Any:
    """Map common LLM variants to canonical enum values.

    Case-insensitive lookup. Returns the original value when no synonym
    is found, so the enum validator still rejects truly unknown values."""
    if not isinstance(value, str):
        return value
    canonical = _ENUM_SYNONYMS.get(value.strip().lower())
    return canonical if canonical is not None else value

VERIFIED_IN_SOURCES = {
    "PSH", "PATHOLOGY", "IMAGING", "PSA_CURVE", "MEDICATIONS",
    "ALLERGIES", "PMH", "procedure_findings", "GU_NOTE",
    "BANNER", "STAGE1_LABS",
}

UROLOGIC_MEDS = {
    # alpha-blockers
    "tamsulosin", "alfuzosin", "silodosin", "doxazosin", "terazosin",
    # 5-ARIs
    "finasteride", "dutasteride",
    # anticholinergics
    "oxybutynin", "solifenacin", "trospium", "tolterodine",
    "fesoterodine", "darifenacin",
    # beta-3 agonists
    "mirabegron", "vibegron",
    # PDE5
    "sildenafil", "tadalafil", "vardenafil", "avanafil",
    # ICI
    "alprostadil", "trimix",
    # GnRH analogs / antagonists
    "leuprolide", "goserelin", "degarelix", "relugolix", "lupron", "eligard",
    # anti-androgens
    "bicalutamide", "enzalutamide", "apalutamide", "darolutamide",
    "abiraterone",
    # chemo (GU-relevant)
    "docetaxel", "cabazitaxel", "mitomycin-c", "bcg",
    # other
    "phenazopyridine", "testosterone", "clomiphene", "anastrozole",
}


# ---------------------------------------------------------------------------
# Date format
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$"
)


def _is_valid_date(s: Any) -> bool:
    """Accept YYYY, YYYY-MM, YYYY-MM-DD."""
    if s is None or s == "":
        return True  # optional fields
    if not isinstance(s, str):
        return False
    return bool(_DATE_RE.match(s))


# ---------------------------------------------------------------------------
# Schema definition (Python-dict form, used by validator)
# ---------------------------------------------------------------------------

# Each field is described by:
#   type     : "string" | "number" | "integer" | "boolean" |
#              "object" | "array" | "enum" | "date"
#   required : bool (default False)
#   enum     : set of allowed values (only when type == "enum")
#   items    : sub-schema for "array"
#   schema   : sub-schema for "object"
#   nullable : bool (default True for non-required)

INTRO_SCHEMA = {
    "type": "object",
    "required": True,
    "schema": {
        "name": {"type": "string", "required": True},  # from banner
        "age": {"type": "integer", "required": True},   # from banner
        "sex": {"type": "enum", "enum": SEX_VALUES, "required": True},
        "visit_type": {"type": "enum", "enum": VISIT_TYPES, "required": True},
        "visit_reason": {"type": "string", "required": True},
    },
}

PRIOR_DIAGNOSIS_SCHEMA = {
    "type": "object",
    "required": False,
    "schema": {
        "primary_dx": {"type": "string"},
        "dx_date": {"type": "date"},        # YYYY or YYYY-MM
        "gleason": {"type": "string"},      # "3+3" / "3+4" / null
        "grade_group": {"type": "integer"}, # 1-5
        "risk_category": {"type": "string"},  # very-low/low/intermediate/high/null
        "verified_in": {"type": "enum", "enum": VERIFIED_IN_SOURCES},
    },
}

TREATMENT_EVENT_SCHEMA = {
    "type": "object",
    "schema": {
        "modality": {"type": "enum", "enum": TREATMENT_MODALITIES, "required": True},
        "status": {"type": "enum", "enum": TREATMENT_STATUSES, "required": True},
        "date": {"type": "date"},
        "verified_in": {"type": "enum", "enum": VERIFIED_IN_SOURCES, "required": True},
        "narrative_note": {"type": "string"},  # optional one-clause detail
    },
}

PSA_TRAJECTORY_SCHEMA = {
    "type": "object",
    "required": False,
    "schema": {
        # All fields optional so the LLM can emit an empty/all-null
        # trajectory for patients with no PSA (e.g. RCC). The fact
        # validator still cross-checks any non-null value against the
        # PSA Curve, and the renderer skips trajectories with no
        # current_value. So nothing is lost by relaxing required here.
        "current_value": {"type": "number"},  # ng/mL — from PSA CURVE
        "current_date": {"type": "date"},
        "prior_value": {"type": "number"},
        "prior_date": {"type": "date"},
        "peak_value": {"type": "number"},
        "peak_date": {"type": "date"},
        "direction": {"type": "enum", "enum": PSA_DIRECTIONS},
        "narrative_descriptor": {"type": "string"},  # "stable", "rising", "declining"
    },
}

PROCEDURE_FINDING_SCHEMA = {
    "type": "object",
    "schema": {
        "procedure_type": {"type": "enum", "enum": PROCEDURE_TYPES, "required": True},
        "date": {"type": "date", "required": True},
        # finding optional — LLM correctly emits null when the source
        # records the procedure occurred but has no result text. The
        # renderer omits the "showed ..." clause when finding is absent.
        "finding": {"type": "string"},
        "verified_in": {"type": "enum", "enum": VERIFIED_IN_SOURCES, "required": True},
    },
}

CURRENT_REGIMEN_ITEM_SCHEMA = {
    "type": "object",
    "schema": {
        "medication": {"type": "string", "required": True},  # validated against UROLOGIC_MEDS
        "indication": {"type": "string"},
        "verified_in": {"type": "enum", "enum": VERIFIED_IN_SOURCES, "required": True},
    },
}

INTERVAL_STATUS_SCHEMA = {
    "type": "object",
    "required": False,
    "schema": {
        "last_visit_date": {"type": "date"},
        "summary": {"type": "string"},  # 1-2 sentences anchored to last visit
        "denies": {"type": "array", "items": {"type": "string"}},
    },
}

# Top-level schema
HPI_DRAFT_SCHEMA = {
    "type": "object",
    "required": True,
    "schema": {
        "intro": INTRO_SCHEMA,
        "prior_diagnosis": PRIOR_DIAGNOSIS_SCHEMA,
        "treatment_history": {
            "type": "array",
            "items": TREATMENT_EVENT_SCHEMA,
        },
        "psa_trajectory": PSA_TRAJECTORY_SCHEMA,
        "procedure_findings": {
            "type": "array",
            "items": PROCEDURE_FINDING_SCHEMA,
        },
        "current_regimen": {
            "type": "array",
            "items": CURRENT_REGIMEN_ITEM_SCHEMA,
        },
        "interval_status": INTERVAL_STATUS_SCHEMA,
        "today_reason": {"type": "string", "required": True},
    },
}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class ValidationError:
    """One precise validation failure."""
    __slots__ = ("path", "code", "message", "found", "expected")

    def __init__(self, path: str, code: str, message: str,
                 found: Any = None, expected: Any = None):
        self.path = path
        self.code = code
        self.message = message
        self.found = found
        self.expected = expected

    def __repr__(self):
        return f"<ValidationError {self.path}: {self.message}>"


def _validate_field(value: Any, field_schema: Dict, path: str,
                    errors: List[ValidationError]) -> None:
    """Validate a single field against its schema. Appends to errors."""
    ftype = field_schema.get("type")

    if value is None:
        if field_schema.get("required"):
            errors.append(ValidationError(
                path, "REQUIRED_MISSING",
                f"required field '{path}' is null/missing",
            ))
        return

    if ftype == "string":
        if not isinstance(value, str):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected string, got {type(value).__name__}",
                found=value,
            ))
        elif field_schema.get("required") and not value.strip():
            errors.append(ValidationError(
                path, "REQUIRED_EMPTY",
                f"required string '{path}' is empty",
            ))
    elif ftype == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected number, got {type(value).__name__}",
                found=value,
            ))
    elif ftype == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected integer, got {type(value).__name__}",
                found=value,
            ))
    elif ftype == "boolean":
        if not isinstance(value, bool):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected boolean, got {type(value).__name__}",
                found=value,
            ))
    elif ftype == "date":
        if not _is_valid_date(value):
            errors.append(ValidationError(
                path, "INVALID_DATE",
                f"date '{value}' must be YYYY, YYYY-MM, or YYYY-MM-DD",
                found=value,
            ))
    elif ftype == "enum":
        allowed = field_schema.get("enum", set())
        canonical = normalize_enum_value(value)
        if canonical not in allowed:
            errors.append(ValidationError(
                path, "ENUM_VIOLATION",
                f"value '{value}' not in allowed enum",
                found=value,
                expected=sorted(allowed),
            ))
    elif ftype == "object":
        if not isinstance(value, dict):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected object, got {type(value).__name__}",
            ))
            return
        sub_schema = field_schema.get("schema", {})
        for sub_field, sub_field_schema in sub_schema.items():
            sub_value = value.get(sub_field)
            _validate_field(sub_value, sub_field_schema,
                            f"{path}.{sub_field}", errors)
    elif ftype == "array":
        if not isinstance(value, list):
            errors.append(ValidationError(
                path, "TYPE_MISMATCH",
                f"expected array, got {type(value).__name__}",
            ))
            return
        item_schema = field_schema.get("items", {})
        for i, item in enumerate(value):
            _validate_field(item, item_schema,
                            f"{path}[{i}]", errors)
    else:
        errors.append(ValidationError(
            path, "UNKNOWN_TYPE",
            f"schema type '{ftype}' not recognized",
        ))


def _normalize_enums_in_place(node: Any, field_schema: Dict) -> None:
    """Walk a draft node alongside its schema and rewrite enum-shaped string
    values to their canonical form. Mutates the node in place so downstream
    consumers (renderer, fact validator) see canonical enum values."""
    ftype = field_schema.get("type")
    if ftype == "object" and isinstance(node, dict):
        sub_schema = field_schema.get("schema", {})
        for sub_field, sub_field_schema in sub_schema.items():
            if sub_field not in node:
                continue
            sub_value = node[sub_field]
            sub_type = sub_field_schema.get("type")
            if sub_type == "enum" and isinstance(sub_value, str):
                node[sub_field] = normalize_enum_value(sub_value)
            else:
                _normalize_enums_in_place(sub_value, sub_field_schema)
    elif ftype == "array" and isinstance(node, list):
        item_schema = field_schema.get("items", {})
        for i, item in enumerate(node):
            item_type = item_schema.get("type")
            if item_type == "enum" and isinstance(item, str):
                node[i] = normalize_enum_value(item)
            else:
                _normalize_enums_in_place(item, item_schema)


def validate_hpi_draft(draft: Any) -> List[ValidationError]:
    """Validate an HPIDraft against HPI_DRAFT_SCHEMA.

    Returns a list of ValidationError objects (empty list = valid).
    Pure schema validation only — does not cross-check against ground
    truth (see hpi_fact_validator.py for that).

    Normalizes LLM enum synonyms (e.g. "prostate biopsy" -> "biopsy")
    in place before validation, so downstream consumers see canonical
    enum values.
    """
    if not isinstance(draft, dict):
        return [ValidationError("$", "TYPE_MISMATCH",
                                f"top-level must be object, got {type(draft).__name__}")]
    _normalize_enums_in_place(draft, HPI_DRAFT_SCHEMA)
    errors: List[ValidationError] = []
    schema = HPI_DRAFT_SCHEMA.get("schema", {})
    for field, field_schema in schema.items():
        value = draft.get(field)
        _validate_field(value, field_schema, field, errors)
    return errors


def is_valid(draft: Any) -> bool:
    """Convenience: true iff no validation errors."""
    return len(validate_hpi_draft(draft)) == 0


def format_errors(errors: List[ValidationError]) -> str:
    """Format errors as a human-readable string for prompts/logs."""
    if not errors:
        return "(no errors)"
    lines = [f"{len(errors)} validation error(s):"]
    for e in errors:
        line = f"  - {e.path}: [{e.code}] {e.message}"
        if e.expected is not None:
            line += f" (allowed: {e.expected})"
        if e.found is not None:
            line += f" (got: {e.found!r})"
        lines.append(line)
    return "\n".join(lines)
