"""Note-level accuracy scorers for the VAUCDA eval harness.

Architecture-agnostic: every scorer compares a GENERATED note (plain text)
against a per-patient GOLD spec and the SOURCE chart. Nothing here knows or
cares whether the note came from the current hybrid pipeline, a holistic
composer, or anything else — so the same eval fairly A/Bs any approach.

Each scorer returns a Metric(name, passed, score, detail). Checks are
deterministic (string/regex against note + source) so runs are reproducible;
an optional LLM-judge layer can be added later without changing this contract.

The five metrics map to the accuracy dimensions that matter clinically:
  1. primary_diagnosis   — the note is centered on the RIGHT diagnosis/organ
  2. no_false_diagnosis  — no forbidden/hallucinated diagnosis asserted
  3. no_cross_cancer      — no cancer for an organ the patient doesn't have
  4. psa_grounded         — every PSA value in the note exists in the source
  5. completeness         — all required sections present and non-trivial
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Metric:
    name: str
    passed: bool
    score: float          # 0.0–1.0
    detail: str = ""


@dataclass
class PatientResult:
    patient_id: str
    metrics: List[Metric] = field(default_factory=list)

    def get(self, name: str) -> Optional[Metric]:
        return next((m for m in self.metrics if m.name == name), None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Organ → the words that signal that organ is the subject of a phrase.
_ORGAN_TERMS = {
    "penile": ["penile", "penis", "glans"],
    "renal": ["renal", "kidney", "nephr"],
    "bladder": ["bladder", "urothelial", "turbt"],
    "prostate": ["prostate", "prostatic"],
    "testicular": ["testicular", "testis", "testicle", "orchiectomy"],
    "upper_tract": ["ureter", "renal pelvis", "upper tract", "upper-tract"],
    "adrenal": ["adrenal"],
    "urethral": ["urethra"],
}
_CANCER_TERMS = ["cancer", "carcinoma", "malignan", "adenocarcinoma", "tumor",
                 "tumour", "sarcoma", "seminoma", "squamous cell"]
# "indeterminate" framing a note should use for an unbiopsied lesion.
_INDETERMINATE_TERMS = ["uncertain significance", "indeterminate", "mass",
                        "lesion", "concerning for", "suspicious for",
                        "elevated psa", "rising psa", "under evaluation",
                        "workup", "surveillance"]


def _hpi(note: str) -> str:
    m = re.search(r"(?ims)^HPI:\s*(.*?)(?=\n[A-Z][A-Z /]{2,}:|\nIPSS|\Z)", note)
    return (m.group(1) if m else "")


def _cc(note: str) -> str:
    m = re.search(r"(?im)^CC:\s*(.*)$", note)
    return (m.group(1) if m else "")


def _lead(note: str, n_sents: int = 3) -> str:
    """CC + first few HPI sentences — where the primary diagnosis is framed."""
    hpi = _hpi(note)
    sents = re.split(r"(?<=[.!?])\s+", hpi)
    return (_cc(note) + " " + " ".join(sents[:n_sents])).lower()


# Context that makes a following cancer mention NOT a positive assertion that
# THIS patient currently has that cancer: negation, hedging/workup framing, or
# a family-history reference.
_NONASSERT_RE = re.compile(
    r"\b(no|not|without|denies|negative\s+for|ruled?\s+out|r/o|"
    r"no\s+evidence\s+of|no\s+patholog\w*|without\s+patholog\w*|"
    r"treatment[-\s]naive\s+(?:for|of)|screening\s+for|surveillance\s+for|"
    r"work[-\s]?up\s+for|risk\s+of|concern(?:ing)?\s+for|suspicion\s+for|"
    r"absence\s+of|free\s+of|clear\s+of|no\s+history\s+of|remission|"
    r"family\s+history|father|mother|brother|sister|paternal|maternal|fhx|"
    r"aggressive|definitive|whether\s+to|benefit\s+of)\b")
# Words that make an organ mention benign / uncertain rather than a cancer.
_BENIGN_CTX_RE = re.compile(
    r"\b(benign|adenoma|cyst|stone|calcul\w+|nodule|uncertain|"
    r"indeterminate|hypertroph\w+|BPH)\b", re.IGNORECASE)


# Context AFTER the phrase that also makes it a non-assertion, e.g. "prostate
# cancer screening / surveillance / workup / monitoring / risk".
_TRAILING_NONASSERT_RE = re.compile(
    r"^\W*(screening|surveillance|work[-\s]?up|monitoring|risk|prevention|"
    r"prophylaxis|guideline)\b")


def _is_asserted(text_lc: str, start: int, end: Optional[int] = None,
                 window: int = 60) -> bool:
    """True if a mention spanning [start, end) is a positive current assertion —
    not negated / hedged / family-history (checked BEFORE it) and not a
    screening/surveillance framing (checked AFTER it)."""
    if _NONASSERT_RE.search(text_lc[max(0, start - window):start]):
        return False
    if end is not None and _TRAILING_NONASSERT_RE.search(text_lc[end:end + 25]):
        return False
    return True


def _has_negation_before(text_lc: str, idx: int, window: int = 60) -> bool:
    return not _is_asserted(text_lc, idx, window=window)


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

def score_primary_diagnosis(note: str, gold: Dict) -> Metric:
    """The note's lead (CC + HPI opening) must be framed around the gold organ
    with the gold malignancy level (cancer / indeterminate / benign)."""
    g = gold.get("primary_diagnosis")
    if not g:
        return Metric("primary_diagnosis", True, 1.0, "no gold (skipped)")
    organ = g["organ"]
    malignancy = g.get("malignancy", "cancer")
    lead = _lead(note)
    organ_terms = _ORGAN_TERMS.get(organ, [organ])
    organ_hit = any(t in lead for t in organ_terms)
    if not organ_hit:
        return Metric("primary_diagnosis", False, 0.0,
                      f"lead not centered on {organ} (terms {organ_terms} absent)")
    # Malignancy framing near the organ mention.
    if malignancy == "cancer":
        ok = any(t in lead for t in _CANCER_TERMS)
        return Metric("primary_diagnosis", ok, 1.0 if ok else 0.5,
                      f"{organ} present; cancer framing "
                      + ("present" if ok else "MISSING"))
    if malignancy == "indeterminate":
        # Must NOT assert cancer for this organ, but should flag uncertainty.
        asserts_cancer = any(t in lead for t in _CANCER_TERMS)
        flags_uncertain = any(t in lead for t in _INDETERMINATE_TERMS)
        ok = flags_uncertain and not asserts_cancer
        return Metric("primary_diagnosis", ok, 1.0 if ok else 0.3,
                      f"{organ} present; indeterminate framing="
                      f"{flags_uncertain}, wrongly-cancer={asserts_cancer}")
    # benign
    asserts_cancer = any(t in lead for t in _CANCER_TERMS)
    ok = not asserts_cancer
    return Metric("primary_diagnosis", ok, 1.0 if ok else 0.0,
                  f"{organ} present; benign, wrongly-cancer={asserts_cancer}")


def score_no_false_diagnosis(note: str, gold: Dict) -> Metric:
    """None of the gold 'forbidden_diagnoses' may appear as a positive assertion
    (negated mentions are fine — 'no prostate cancer')."""
    forbidden = gold.get("forbidden_diagnoses", [])
    if not forbidden:
        return Metric("no_false_diagnosis", True, 1.0, "no forbidden list")
    note_lc = note.lower()
    hits = []
    for phrase in forbidden:
        # Word-boundary at the start so "bladder cancer" doesn't match inside
        # "gallbladder cancer"; only count positive current assertions.
        pat = r"(?<![a-z])" + re.escape(phrase.lower())
        for m in re.finditer(pat, note_lc):
            if _is_asserted(note_lc, m.start(), m.end()):
                hits.append(phrase)
                break
    ok = not hits
    return Metric("no_false_diagnosis", ok, 1.0 if ok else 0.0,
                  "clean" if ok else f"asserted forbidden dx: {hits}")


def score_no_cross_cancer(note: str, gold: Dict) -> Metric:
    """No cancer asserted for an organ other than the patient's own cancer
    organ(s). Catches the multi-cancer leak class (penile patient with a
    fabricated bladder/prostate cancer)."""
    allowed = set(gold.get("cancer_organs", []))
    g = gold.get("primary_diagnosis") or {}
    if g.get("organ"):
        allowed.add(g["organ"])  # the patient's own organ is never a "leak"
    note_lc = note.lower()
    leaks = []
    _MALIG = r"(?:cancer|carcinoma|adenocarcinoma|malignan\w+)"
    for organ, terms in _ORGAN_TERMS.items():
        if organ in allowed:
            continue
        found = False
        for t in terms:
            # Tight, word-bounded binding of the organ to a malignancy noun,
            # in either order, e.g. "renal cell carcinoma" / "cancer of the
            # kidney". \b stops "renal" matching inside "adrenal".
            pat = (rf"(?<![a-z]){re.escape(t)}[a-z\s-]{{0,20}}{_MALIG}"
                   rf"|{_MALIG}\s+of\s+(?:the\s+)?{re.escape(t)}(?![a-z])")
            for m in re.finditer(pat, note_lc):
                span = note_lc[max(0, m.start() - 30):m.end() + 10]
                if _BENIGN_CTX_RE.search(span):
                    continue  # "adrenal adenoma", "renal cyst", etc.
                if _is_asserted(note_lc, m.start(), m.end()):
                    leaks.append(f"{organ}:{t}")
                    found = True
                    break
            if found:
                break
    ok = not leaks
    return Metric("no_cross_cancer", ok, 1.0 if ok else 0.0,
                  "clean" if ok else f"cross-cancer leak: {sorted(set(leaks))}")


_PSA_IN_NOTE_RE = re.compile(r"(\d+\.?\d*)\s*ng/mL", re.IGNORECASE)


def score_psa_grounded(note: str, gold: Dict, source_psa_values: List[float]) -> Metric:
    """Every PSA-context value cited in the note must exist in the source PSA
    set (±0.05). A cited value not in the source is a fabrication. Also honors
    an explicit gold 'forbidden_psa' list (known-wrong values)."""
    # Only look at PSA-context numbers: those within ~60 chars after a 'PSA' token.
    note_lc = note.lower()
    cited: List[float] = []
    for m in _PSA_IN_NOTE_RE.finditer(note):
        before = note_lc[max(0, m.start() - 60):m.start()]
        if "psa" not in before:
            continue
        # Skip thresholds / reference ranges / conditionals ("if PSA > 20",
        # "PSA above 10", ">20 ng/mL") — those aren't the patient's value.
        near = note_lc[max(0, m.start() - 30):m.start()]
        # NB: only suppress genuine threshold / delta / conditional contexts —
        # NOT "PSA remains stable at 8.52" (a real cited value). "if PSA remains
        # 10" is still caught by the \bif\b clause.
        if re.search(r"[<>≥≤]|greater\s+than|less\s+than|above|below|"
                     r"exceed\w*|threshold|reference|\bif\b|at\s+least|"
                     r"over\s+|under\s+|increase\s+of|rise\s+of|"
                     r"increases?\s+by|rises?\s+by|\bby\s+|increment|change\s+of",
                     near):
            continue
        try:
            cited.append(float(m.group(1)))
        except ValueError:
            continue
    if not cited:
        return Metric("psa_grounded", True, 1.0, "no PSA cited")
    forbidden = set(gold.get("forbidden_psa", []))
    src = source_psa_values or []
    bad = []
    for v in cited:
        if any(abs(v - f) < 0.05 for f in forbidden):
            bad.append(f"{v}(forbidden)")
        elif src and not any(abs(v - s) < 0.05 for s in src):
            bad.append(f"{v}(not-in-source)")
    ok = not bad
    return Metric("psa_grounded", ok, 1.0 if ok else 0.0,
                  f"cited {cited}; " + ("all grounded" if ok else f"BAD: {bad}"))


def score_completeness(note: str, gold: Dict) -> Metric:
    """All required sections present and non-trivial (header + some content)."""
    required = gold.get("required_sections",
                        ["CC", "HPI", "ASSESSMENT", "PLAN"])
    missing = []
    for sec in required:
        # header like "CC:" / "HPI:" / "ASSESSMENT:" ... then non-space content
        m = re.search(rf"(?im)^{re.escape(sec)}:\s*(.*)$", note)
        if not m or len(m.group(1).strip()) < 3:
            # allow multi-line sections: check something follows the header
            if m:
                after = note[m.end():m.end() + 80].strip()
                if after:
                    continue
            missing.append(sec)
    ok = not missing
    return Metric("completeness", ok, 1.0 - len(missing) / max(1, len(required)),
                  "all present" if ok else f"missing/empty: {missing}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def score_note(patient_id: str, note: str, gold: Dict,
               source_psa_values: List[float]) -> PatientResult:
    r = PatientResult(patient_id=patient_id)
    r.metrics.append(score_primary_diagnosis(note, gold))
    r.metrics.append(score_no_false_diagnosis(note, gold))
    r.metrics.append(score_no_cross_cancer(note, gold))
    r.metrics.append(score_psa_grounded(note, gold, source_psa_values))
    r.metrics.append(score_completeness(note, gold))
    return r


METRIC_NAMES = [
    "primary_diagnosis", "no_false_diagnosis", "no_cross_cancer",
    "psa_grounded", "completeness",
]
