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


# --- liver-directed-therapy guard --------------------------------------------
# TACE / TARE / Y-90 / (chemo|radio)embolization are liver-directed (HCC) and
# are NOT used to treat renal / urothelial / prostate primaries. On a dual-organ
# patient (kidney RCC + liver HCC) the LLM can mis-attach the hepatic plan to the
# GU chief complaint (RIVERA: "renal cell carcinoma under evaluation for TACE and
# SBRT" — the TACE belongs to the concurrent HCC). "Ablation" is intentionally
# EXCLUDED: renal cryo/microwave ablation is a legitimate RCC treatment.
_LT_CORE = (r"TACE|TARE|Y[-\s]?90|SIRT|trans[-\s]?arterial\s+(?:chemo[-\s]?)?"
            r"emboli\w+|chemo[-\s]?emboli\w+|radio[-\s]?emboli\w+")
_LT_TRAIL = re.compile(r"\s*(?:,|and)\s+(?:" + _LT_CORE + r")\b", re.I)
_LT_LEAD = re.compile(r"\b(?:" + _LT_CORE + r")\s+(?:,|and)\s+", re.I)
_LT_ANY = re.compile(r"\b(?:" + _LT_CORE + r")\b", re.I)
_HEPATIC = re.compile(r"\b(liver|hepatic|hepatocellular|hcc)\b", re.I)
# a GU / non-hepatic malignancy subject in the surrounding text
_GU_CANCER_SUBJ = re.compile(
    r"\b(renal\s+cell|rcc|renal\s+mass|kidney|urotheli\w+|bladder|prostate|"
    r"ureter\w*|upper[-\s]tract|penile|testic\w+|adrenal)\b", re.I)


# a connector left with no object after a therapy token is removed. Matched only
# when immediately followed by a clause/paren boundary ()  ;  ,  .  or end), so a
# connector with a real object ("pending SBRT") is never touched.
_DANGLING = re.compile(
    r"\s*[,;]?\s*\b(?:s/?p|for|with|via|using|and|or|pending|planned|"
    r"scheduled(?:\s+for)?|being\s+evaluated\s+for|under\s+evaluation\s+for|"
    r"evaluation\s+for|consideration\s+(?:of|for)|managed\s+with|treated\s+with|"
    r"receiving|to\s+undergo|undergoing)\s*(?=[)\];.,]|$)", re.I)


def _drop_liver_therapy_tokens(s: str) -> str:
    """Remove liver-directed therapy tokens plus an adjacent conjunction/comma,
    then tidy dangling connectors and emptied parentheticals."""
    s = _LT_TRAIL.sub("", s)          # "SBRT and TACE" -> "SBRT"
    s = _LT_LEAD.sub("", s)           # "TACE and SBRT" -> "SBRT"
    s = _LT_ANY.sub("", s)            # bare "TACE" -> ""
    # peel orphaned connectors until stable ("(pending SBRT; being evaluated for)"
    # -> "(pending SBRT)"; "... s/p )" -> "...")
    for _ in range(4):
        new = _DANGLING.sub("", s)
        if new == s:
            break
        s = new
    # emptied parenthetical: "(under evaluation for )" / "( )" -> gone
    s = re.sub(r"\(\s*(?:under\s+evaluation\s+for|pending|evaluation\s+for|for)?\s*\)",
               "", s, flags=re.I)
    s = re.sub(r"\s+([)\].,;])", r"\1", s)
    s = re.sub(r"\(\s*[;,]\s*", "(", s)   # "(; pending SBRT)" -> "(pending SBRT)"
    s = re.sub(r"[;,]\s*\)", ")", s)      # "(pending SBRT;)" -> "(pending SBRT)"
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" ,;")


def strip_liver_directed_therapy(cc: str) -> str:
    """Guard: strip liver-directed therapy from a NON-hepatic GU chief complaint.
    No-op when no such therapy is present or when the CC's lead clause is itself
    hepatic (a genuine liver primary leading the note)."""
    if not cc or not _LT_ANY.search(cc):
        return cc
    if _HEPATIC.search(lead_clause(cc)):
        return cc
    return _drop_liver_therapy_tokens(cc) or cc


def scrub_liver_therapy_prose(text: str) -> str:
    """Guard for narrative sections (Assessment): remove a liver-directed therapy
    only from sentences whose subject is a GU cancer AND that carry no hepatic
    referent — so a legitimately hepatic sentence ("TACE for the HCC") is left
    intact while a mis-attached "RCC ... managed with TACE" is corrected."""
    if not text or not _LT_ANY.search(text):
        return text
    out = []
    for sent in re.split(r"(?<=[.;])\s+", text):
        if (_LT_ANY.search(sent) and _GU_CANCER_SUBJ.search(sent)
                and not _HEPATIC.search(sent)):
            out.append(_drop_liver_therapy_tokens(sent))
        else:
            out.append(sent)
    return " ".join(p for p in out if p)
