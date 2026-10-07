"""Organ-agnostic pathology-finding inventory — the completeness ground truth.

Enumerates EVERY discrete pathology finding in a block of text, across ALL
GU cancers (not prostate-only). This is the deterministic ledger the eval uses
BOTH ways:
  - completeness (recall): every source finding must appear in the note
    (catches OMISSIONS — the 76%-missing-Gleason problem)
  - grounding (precision): every finding the note cites must be in the source
    (catches FABRICATION / wrong grade — CRAWFORD 4+3 -> 3+3)

A finding is a normalized token like "gleason:4+3", "gg:2", "grade:isup:3",
"stage:pt3a", "histology:urothelial-carcinoma", "nodes:0/18", "margin:positive",
"invasion:lvi". Extraction is presence-based pattern matching, not clinical
judgment — so a missed pattern under-reports (conservative), never fabricates.
"""
from __future__ import annotations

import re
from typing import Set

# --- grading systems (organ-appropriate) ---
_GLEASON = re.compile(r"gleason(?:'s)?\s+(?:score\s+|grade\s+)?(\d)\s*\+\s*(\d)", re.I)
_GG = re.compile(r"(?:grade\s+group|\bGG)\s*[:=]?\s*([1-5])\b", re.I)
_OTHER_GRADE = re.compile(
    r"\b(fuhrman|isup|who|nuclear)\s+(?:nuclear\s+)?grade\s+([1-4]|IV|III|II|I)\b", re.I)
_UROTHELIAL_GRADE = re.compile(
    r"\b(high|low)[\s-]grade\s+(?:papillary\s+)?urothelial", re.I)

# --- staging ---
_STAGE_T = re.compile(r"\b[ypr]?[cp]?T([0-4])([a-d])?\b")
_STAGE_N = re.compile(r"\b[ypr]?[cp]?N([0-3])\b")
_STAGE_M = re.compile(r"\b[cp]?M([01x])\b")

# --- histology diagnoses (organ-agnostic) ---
_HISTOLOGY = {
    "adenocarcinoma": r"adenocarcinoma",
    "urothelial-carcinoma": r"urothelial\s+(?:cell\s+)?carcinoma|transitional\s+cell\s+carcinoma|\bTCC\b",
    "renal-cell-carcinoma": r"renal\s+cell\s+carcinoma|\bRCC\b",
    "clear-cell": r"clear[\s-]cell",
    "papillary": r"papillary\s+(?:renal|carcinoma)",
    "chromophobe": r"chromophobe",
    # Penile/GU SCC only — exclude dermatologic "squamous cell carcinoma of
    # skin" (a common PMH item, not urologic pathology) and the bare "SCC"
    # abbreviation (too ambiguous). "SCCa" is the penile-cancer form.
    "squamous-cell-carcinoma": r"squamous\s+cell\s+carcinoma(?![^.\n]{0,20}skin)|\bSCCa\b",
    "seminoma": r"\bseminoma\b",
    "germ-cell": r"germ\s+cell\s+tumou?r|non[\s-]?seminoma|embryonal|yolk\s+sac|teratoma|choriocarcinoma",
    "sarcomatoid": r"sarcomatoid",
    "small-cell": r"small[\s-]cell\s+carcinoma|neuroendocrine",
    # NOTE: benign entities (myelolipoma, adenoma) are intentionally NOT counted
    # as findings the note must report — they are benign incidentals, not cancer
    # pathology, and the composer correctly omits them.
}

# --- key descriptors ---
_DESCRIPTORS = {
    "margin:positive": r"positive\s+(?:surgical\s+)?margin|margin(?:s)?\s+(?:are\s+)?positive",
    "margin:negative": r"negative\s+(?:surgical\s+)?margin|margin(?:s)?\s+(?:are\s+)?negative",
    "invasion:epe": r"extra[\s-]?prostatic\s+extension|\bEPE\b",
    "invasion:svi": r"seminal\s+vesicle\s+invasion|\bSVI\b",
    "invasion:lvi": r"lymphovascular\s+invasion|\bLVI\b",
    "invasion:pni": r"perineural\s+invasion|\bPNI\b",
    "invasion:muscle": r"muscularis\s+propria|muscle[\s-]invasiv",
    "cis": r"carcinoma\s+in\s+situ|\bCIS\b",
    "asap": r"\bASAP\b|atypical\s+small\s+acinar",
    "pin": r"high[\s-]grade\s+PIN|\bHGPIN\b",
}

_NODES = re.compile(r"(\d+)\s*/\s*(\d+)\s+(?:(?:lymph\s+)?nodes|LN)\b", re.I)


def pathology_findings(text: str) -> Set[str]:
    """Return the set of normalized pathology findings present in ``text``."""
    if not text:
        return set()
    out: Set[str] = set()
    for a, b in _GLEASON.findall(text):
        out.add(f"gleason:{a}+{b}")
    for g in _GG.findall(text):
        out.add(f"gg:{g}")
    for sys_, g in _OTHER_GRADE.findall(text):
        out.add(f"grade:{sys_.lower()}:{g.upper()}")
    for hl in _UROTHELIAL_GRADE.findall(text):
        out.add(f"uro-grade:{hl.lower()}")
    for t, sub in _STAGE_T.findall(text):
        out.add(f"stage:t{t}{(sub or '').lower()}")
    for n in _STAGE_N.findall(text):
        out.add(f"stage:n{n}")
    for key, pat in _HISTOLOGY.items():
        if re.search(pat, text, re.I):
            out.add(f"histology:{key}")
    for key, pat in _DESCRIPTORS.items():
        if re.search(pat, text, re.I):
            out.add(key)
    for a, b in _NODES.findall(text):
        out.add(f"nodes:{a}/{b}")
    return out


# Findings we hold the note strictly accountable for (objective + high-value).
# Descriptors/stage are informative but noisier in free text, so completeness is
# reported on this core plus (separately) the full set.
_CORE_PREFIXES = ("gleason:", "gg:", "grade:", "uro-grade:", "histology:")


def core_findings(text: str) -> Set[str]:
    return {f for f in pathology_findings(text)
            if f.startswith(_CORE_PREFIXES)}
