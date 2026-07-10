"""Shared chief-complaint quality checks.

These source-grounded checks are the single definition used BOTH by the offline
audit (``eval/audit_cc.py``) and by the runtime CC verifier
(``agents/cc_composer.py``), so a CC the composer accepts is exactly a CC the
audit would pass.

Each check answers a yes/no defect question about a chief-complaint string given
the raw source chart:

  A) benign_incidental_leads   — the CC LEADS with an adrenal/cyst framed as
     "mass"/"uncertain significance"/"neoplasm" while the source radiology calls
     that finding BENIGN (myelolipoma / washout adenoma / simple cyst). A benign
     incidental must not be the visit's chief complaint (MOLINA).
  B) uncertain_mislabels_cancer — the CC calls a renal/bladder lesion "of
     uncertain significance" while the source documents a tissue-confirmed,
     definitively-treated cancer of that organ (Hx of RCC s/p nephrectomy). A
     resected, pathology-proven cancer is not "uncertain" (FLORES). A genuinely
     untreated "possible RCC / consideration of nephrectomy" (KIND) is NOT
     flagged.
"""
from __future__ import annotations

import re

# --- source characterizations ------------------------------------------------
_ADRENAL_BENIGN = re.compile(
    r"adrenal[^.\n]{0,90}?(myelolipoma|adenoma|washout|<\s*10\s*HU|lipid[\s-]poor|"
    r"macroscopic fat|fat[\s-]containing|benign)|myelolipoma", re.I)
# An ESTABLISHED prior cancer: history/known-of the carcinoma AND definitive
# treatment already completed (s/p resection/ablation). Excludes newly-found or
# scheduled-for-treatment lesions (MARTINEZ: TURBT scheduled; RIPLEY: none).
_RENAL_CA_TREATED = re.compile(
    r"(hx|history|known)\s+of\s+(right|left|bilateral\s+)?(rcc|renal\s+cell\s+carcinoma)"
    r"[^.\n]{0,60}?(s/?p|resect|nephrectomy|ablation|ned)", re.I)
_BLADDER_CA_TREATED = re.compile(
    r"(hx|history|known)\s+of[^.\n]{0,30}?(bladder\s+cancer|urothelial\s+carcinoma)"
    r"[^.\n]{0,60}?(s/?p|resect|turbt|cystectomy|ned)", re.I)

_LEAD_INCIDENTAL = re.compile(r"uncertain significance|mass|neoplasm", re.I)


def cc_body(note: str) -> str:
    """Extract the CC line from a rendered note (empty string if absent)."""
    m = re.search(r"(?im)^CC:\s*(.+)$", note)
    return m.group(1).strip() if m else ""


def lead_clause(cc: str) -> str:
    """The CC's first finding clause (before ';' or ' and '), lower-cased."""
    return re.split(r";| and ", cc, maxsplit=1)[0].lower()


def benign_incidental_leads(cc: str, source: str) -> bool:
    """A) the CC leads with a radiology-benign adrenal/cyst incidental."""
    lead = lead_clause(cc)
    return bool(
        ("adrenal" in lead or "cyst" in lead)
        and _LEAD_INCIDENTAL.search(lead)
        and _ADRENAL_BENIGN.search(source)
        and "adrenal" in lead)


def uncertain_mislabels_cancer(cc: str, source: str) -> bool:
    """B) the CC calls a renal/bladder lesion 'uncertain' when the source shows a
    confirmed, definitively-treated cancer of that organ."""
    cc_lc = cc.lower()
    if re.search(r"(renal|kidney)[^;]{0,40}?of uncertain significance", cc_lc) \
            and _RENAL_CA_TREATED.search(source):
        return True
    if re.search(r"bladder[^;]{0,40}?of uncertain significance", cc_lc) \
            and _BLADDER_CA_TREATED.search(source):
        return True
    return False
