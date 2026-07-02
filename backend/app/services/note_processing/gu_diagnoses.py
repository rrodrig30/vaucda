"""Non-prostate genitourinary diagnosis detection (multi-cancer ground truth).

The rest of ``patient_status_facts`` models ONLY prostate cancer. For a renal-mass,
bladder-tumor, or other GU patient the prostate-shaped ground truth is silent, so
the CC/HPI/Assessment/Plan agents get no structured anchor for the real primary
diagnosis and default to a prostate/PSA narrative (or, for female patients,
hallucinate prostate cancer). This module supplies the missing structured layer:
the patient's sex and their non-prostate GU diagnoses (organ + category + grade +
status), which ``format_facts_for_prompt`` surfaces as an authoritative block.

Clinical rule (urologist): an unbiopsied mass is NEVER labeled "benign" — it is
"indeterminate" / "of uncertain significance" (VA benefits implications). Only a
pathology-confirmed benign entity (angiomyolipoma, simple cyst, benign TURBT
pathology) is category=benign; a confirmed malignancy is category=cancer;
everything else radiographic is category=indeterminate.
"""
import re
from dataclasses import dataclass, field
from typing import List

_NEG = re.compile(
    r"\b(no|not|without|denies?|negative for|ruled?\s+out|r/o|resolved|"
    r"no evidence of|free of)\b", re.IGNORECASE)
_FAMILY = re.compile(r"\b(family (history|hx)|father|mother|brother|sister|"
                     r"son|daughter|maternal|paternal|sibling)\b", re.IGNORECASE)


def _clean(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip()[:120]


def _negated_or_family(text: str, pos: int, window: int = 70) -> bool:
    pre = text[max(0, pos - window):pos]
    return bool(_NEG.search(pre) or _FAMILY.search(text[max(0, pos - window):pos + window]))


@dataclass
class GUDiagnosis:
    """One non-prostate GU diagnosis with its clinical framing."""
    organ: str            # renal | bladder | upper_tract | testicular | penile | adrenal | other
    category: str         # cancer | indeterminate | benign
    name: str             # human label rendered in the ground-truth block
    grade: str = ""       # cancer-appropriate grade (Fuhrman/nuclear, WHO high/low, stage)
    status: str = ""      # s/p ablation / s/p TURBT / on active surveillance / etc.
    evidence: str = ""    # source quote


def detect_patient_sex(text: str) -> str:
    """Return 'female' | 'male' | '' from the demographics / narrative."""
    if not text:
        return ""
    m = re.search(r"\bsex\b\s*[:=]?\s*(male|female|m|f)\b", text[:6000], re.IGNORECASE)
    if m:
        v = m.group(1).lower()
        return "female" if v in ("female", "f") else "male"
    # Fallback: gendered clinical phrasing near the top of the note.
    head = text[:6000].lower()
    if re.search(r"\b(she|her|female|woman)\b", head) and not re.search(r"\b(he|his|male|man)\b", head):
        return "female"
    if re.search(r"\b(he|his|male|man)\b", head) and not re.search(r"\b(she|her|female|woman)\b", head):
        return "male"
    return ""


# (organ, category, label, compiled pattern). Order matters: the FIRST cancer
# match per organ wins; an indeterminate match only stands if no cancer for that
# organ was found; benign only from an explicit benign entity.
_CANCER = [
    ("renal", r"(clear[\s-]cell|papillary|chromophobe)\s+renal\s+cell\s+carcinoma",
     "renal cell carcinoma"),
    ("renal", r"\brenal\s+cell\s+carcinoma\b|\bRCC\b", "renal cell carcinoma"),
    ("bladder", r"\b(?:high|low)[\s-]grade\s+(?:papillary\s+)?urothelial\s+carcinoma|"
     r"urothelial\s+(?:cell\s+)?carcinoma|transitional\s+cell\s+carcinoma|\bTCC\b|"
     r"muscle[\s-]invasive\s+bladder\s+cancer|\bMIBC\b|\bNMIBC\b", "urothelial carcinoma"),
    ("upper_tract", r"upper[\s-]tract\s+urothelial\s+carcinoma|\bUTUC\b|"
     r"(?:ureter|renal\s+pelvis)\w*\s+urothelial", "upper-tract urothelial carcinoma"),
    ("testicular", r"\b(seminoma|non[\s-]?seminoma|germ\s+cell\s+tumou?r|testicular\s+cancer)\b",
     "testicular germ-cell tumor"),
    ("penile", r"penile\s+(?:squamous\s+cell\s+)?carcinoma|squamous\s+cell\s+carcinoma\s+of\s+the\s+penis",
     "penile carcinoma"),
    ("adrenal", r"adrenocortical\s+carcinoma|adrenal\s+(?:cortical\s+)?carcinoma", "adrenal carcinoma"),
]
_INDETERMINATE = [
    ("renal", r"\brenal\s+mass\b|\brenal\s+lesion\b|\bkidney\s+mass\b|"
     r"enhancing\s+(?:left|right|interpolar|upper[\s-]pole|lower[\s-]pole)?\s*renal\s+mass|"
     r"complex\s+(?:renal\s+)?cyst|Bosniak\s+(?:III|IV|3|4)", "renal mass of uncertain significance"),
    ("bladder", r"\bbladder\s+(?:neck\s+)?(?:mass|tumou?r|lesion)\b|papillary\s+bladder|"
     r"bladder\s+filling\s+defect|intraluminal\s+(?:bladder\s+)?(?:focus|lesion|mass)|"
     r"papillary\s+(?:protrusion|frond)", "bladder tumor of uncertain significance"),
    ("adrenal", r"adrenal\s+(?:mass|nodule|adenoma\??)", "adrenal mass of uncertain significance"),
]
_BENIGN = [
    ("renal", r"angiomyolipoma|\bAML\b|simple\s+(?:renal\s+)?cyst|Bosniak\s+(?:I|II|1|2)\b", "benign renal lesion"),
    ("bladder", r"benign\s+(?:bladder|urothelium|TURBT)|"
     r"(?:TURBT|biopsy)\s+(?:pathology\s+)?(?:showed|revealed|with)\s+benign|"
     r"no\s+(?:evidence\s+of\s+)?(?:malignancy|carcinoma|tumou?r)\b", "benign bladder pathology"),
]

# A malignancy term is only category=cancer when PATHOLOGY-CONFIRMED nearby. In a
# hedged / differential / counseling context ("options include...", "concerning
# for...", "cannot exclude RCC") the same words describe a possibility, not a
# diagnosis — an unbiopsied mass must read as INDETERMINATE (urologist rule).
_CONFIRM = re.compile(
    r"biopsy|biopsy[\s-]proven|patholog|\bpath\b|proven|confirmed|"
    r"consistent\s+with|positive\s+for|resected|nephrectomy\s+specimen|"
    r"(?:showed|revealed|demonstrated)\s+[^.\n]{0,40}(?:carcinoma|malignan)|"
    r"Fuhrman|nuclear\s+grade|grade\s+group|WHO\s+grade|"
    # carcinoma-in-situ and explicit TNM staging are, by definition, a
    # pathology-confirmed malignancy.
    r"carcinoma\s+in\s+situ|\bCIS\b|\bTis\b|\bpT[0-4]|\bcT[0-4]", re.IGNORECASE)
_HEDGE = re.compile(
    r"possible|probable|suspicious\s+for|concerning\s+for|could\s+be|"
    r"cannot\s+(?:exclude|rule\s+out)|rule\s+out|\br/o\b|differential|"
    r"\bversus\b|\bvs\.?\b|option|counsel|\brisk\s+of\b|presumed|favou?r|"
    r"if\s+(?:it\s+)?(?:is|proves)", re.IGNORECASE)

_GRADE = {
    "renal": re.compile(r"Fuhrman\s+(?:grade\s+)?([1-4IV]+)|nuclear\s+grade\s+([1-4])", re.IGNORECASE),
    "bladder": re.compile(r"\b(high[\s-]grade|low[\s-]grade)\b|\b(?:stage\s+)?(Ta|T1|T2|Tis|CIS)\b", re.IGNORECASE),
}
# Organ-specific status so a bladder TURBT isn't attached to a renal mass.
_STATUS = {
    "renal": re.compile(
        r"s/p\s+(?:partial\s+|radical\s+)?nephrectomy|(?:partial|radical)\s+nephrectomy|"
        r"s/p\s+(?:microwave\s+|cryo\s*|radiofrequency\s+|RF\s+|thermal\s+)?ablation|"
        r"(?:microwave|cryo|radiofrequency|thermal)\s+ablation|"
        r"(?:on\s+)?active\s+surveillance", re.IGNORECASE),
    "bladder": re.compile(r"s/p\s+TURBT|\bTURBT\b|intravesical\s+(?:BCG|therapy)", re.IGNORECASE),
    "upper_tract": re.compile(r"nephroureterectomy|ureteroscop", re.IGNORECASE),
}


def _confirmed(text: str, pos: int, window: int = 130) -> bool:
    """A malignancy term counts as a confirmed diagnosis only when a pathology
    confirmation sits nearby and it is not dominated by hedging language."""
    ctx = text[max(0, pos - window):pos + window]
    return bool(_CONFIRM.search(ctx)) and not _HEDGE.search(text[max(0, pos - 60):pos])


def detect_gu_diagnoses(text: str) -> List[GUDiagnosis]:
    """Detect non-prostate GU diagnoses, one entry per organ (highest severity).

    Malignancy is only category=cancer when pathology-confirmed; an unconfirmed
    malignancy term or a bare mass/lesion is category=indeterminate.
    """
    if not text:
        return []
    by_organ = {}  # organ -> GUDiagnosis
    rank = {"cancer": 3, "indeterminate": 2, "benign": 1}

    def consider(organ, category, name, quote):
        cur = by_organ.get(organ)
        if cur and rank[cur.category] >= rank[category]:
            return
        by_organ[organ] = GUDiagnosis(organ=organ, category=category, name=name, evidence=quote)

    # Malignancy terms: confirmed -> cancer; unconfirmed -> indeterminate (mass).
    for organ, pat, label in _CANCER:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if _negated_or_family(text, m.start()):
                continue
            if _confirmed(text, m.start()):
                consider(organ, "cancer", label, _clean(m.group(0)))
            else:
                consider(organ, "indeterminate",
                         {"renal": "renal mass of uncertain significance",
                          "bladder": "bladder tumor of uncertain significance"}.get(organ, label),
                         _clean(m.group(0)))
            break
    for organ, pat, label in _INDETERMINATE:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if _negated_or_family(text, m.start()):
                continue
            consider(organ, "indeterminate", label, _clean(m.group(0)))
            break
    for organ, pat, label in _BENIGN:
        for m in re.finditer(pat, text, re.IGNORECASE):
            if _negated_or_family(text, m.start()):
                continue
            consider(organ, "benign", label, _clean(m.group(0)))
            break

    for organ, dx in by_organ.items():
        gre = _GRADE.get(organ)
        if gre and dx.category == "cancer":
            gm = gre.search(text)
            if gm:
                dx.grade = _clean(next(g for g in gm.groups() if g))
        sre = _STATUS.get(organ)
        if sre:
            sm = sre.search(text)
            if sm:
                dx.status = _clean(sm.group(0))
    order = {"cancer": 0, "indeterminate": 1, "benign": 2}
    return sorted(by_organ.values(), key=lambda d: (order[d.category], d.organ))
