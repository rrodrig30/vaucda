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
    # Match all the ways a penile primary is written: "penile carcinoma/cancer",
    # "squamous cell carcinoma of (the) penis", "SCCa of the penis", "carcinoma
    # of penis", "cancer of the penis". The old pattern required "of THE penis"
    # and missed the chart's "Squamous cell carcinoma of penis" (CASTANEDA).
    ("penile",
     r"penile\s+(?:squamous\s+cell\s+)?(?:carcinoma|cancer)"
     r"|(?:squamous\s+cell\s+|verrucous\s+)?(?:carcinoma|cancer|SCCa?)\s+of\s+"
     r"(?:the\s+)?penis",
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
# Radiology characterization that makes an adrenal lesion benign (no follow-up
# needed if biochemically inactive).
_ADRENAL_BENIGN_CTX = re.compile(
    r"myelolipoma|adenoma|washout|lipid[\s-]poor|<\s*10\s*HU|"
    r"\bbenign\b|\bstable\b", re.IGNORECASE)
# Pathognomonic-benign adrenal terms — safe to trust DOCUMENT-WIDE (there is
# normally a single adrenal lesion, and these terms never describe a malignancy).
# Catches the case where the radiology characterization ("myelolipoma favored")
# is in a different paragraph than the "adrenal mass" problem-list phrase, so the
# narrow ±90-char guard would miss it (MOLINA).
_ADRENAL_BENIGN_STRONG = re.compile(
    r"myelolipoma|washout|<\s*10\s*HU|lipid[\s-]poor|adrenal\s+adenoma",
    re.IGNORECASE)

_BENIGN = [
    ("renal", r"angiomyolipoma|\bAML\b|simple\s+(?:renal\s+)?cyst|Bosniak\s+(?:I|II|1|2)\b", "benign renal lesion"),
    # A "no evidence of malignancy" line only means BENIGN BLADDER when it is
    # actually about the bladder — otherwise a generic negative (e.g. "0/18
    # lymph nodes; no evidence of malignancy" in a penile-cancer chart) wrongly
    # manufactures a bladder diagnosis that then hijacks the HPI anchor
    # (CASTANEDA). Require a bladder / cystoscopy / urine-cytology anchor.
    ("bladder", r"benign\s+(?:bladder|urothelium|TURBT)|"
     r"(?:TURBT|(?:bladder|cold[\s-]cup)\s+biopsy)\s+(?:pathology\s+)?"
     r"(?:showed|revealed|with)\s+benign|"
     r"(?:bladder|urothelium|cystoscop\w+|TURBT|urine\s+cytolog\w+|"
     r"bladder\s+wash)[^.\n]{0,40}?no\s+(?:evidence\s+of\s+)?"
     r"(?:malignancy|carcinoma|tumou?r)\b", "benign bladder pathology"),
]

# A malignancy term is only category=cancer when PATHOLOGY-CONFIRMED nearby. In a
# hedged / differential / counseling context ("options include...", "concerning
# for...", "cannot exclude RCC") the same words describe a possibility, not a
# diagnosis — an unbiopsied mass must read as INDETERMINATE (urologist rule).
_CONFIRM = re.compile(
    r"biopsy|biopsy[\s-]proven|patholog|\bpath\b|proven|confirmed|"
    r"consistent\s+with|positive\s+for|resected|nephrectomy\s+specimen|"
    r"(?:showed|revealed|demonstrated)\s+[^.\n]{0,40}(?:carcinoma|malignan)|"
    # Definitive local therapy already COMPLETED (s/p) proves a tissue diagnosis:
    # you do not remove a kidney or ablate a renal tumor for an unconfirmed mass.
    # Keyed on s/p so a merely PLANNED / "consideration of" nephrectomy (KIND)
    # does NOT confirm — only a completed resection/ablation (FLORES) does.
    # "Nx" is the surgical abbreviation for nephrectomy here (Partial/Radical Nx);
    # bare "Nx" is avoided because it is also the TNM node stage.
    r"s/?p\s+(?:partial\s+|radical\s+)?nephrectomy|(?:partial|radical)\s+nx\b|"
    r"s/?p\s+(?:microwave\s+|cryo\s*|radiofrequency\s+|RF\s+|thermal\s+)?ablation|"
    # An ESTABLISHED prior diagnosis (history/known of RCC / urothelial ca /
    # bladder cancer) is itself confirmation — it is not "of uncertain
    # significance" anymore (FLORES: "Hx of Right RCC ...").
    r"(?:hx|history|known)\s+of\s+(?:right\s+|left\s+|bilateral\s+)?"
    r"(?:rcc\b|renal\s+cell|urothelial\s+carcinoma|bladder\s+cancer)|"
    r"Fuhrman|nuclear\s+grade|grade\s+group|WHO\s+grade|"
    # carcinoma-in-situ and explicit TNM staging are, by definition, a
    # pathology-confirmed malignancy.
    r"carcinoma\s+in\s+situ|\bCIS\b|\bTis\b|\bpT[0-4]|\bcT[0-4]", re.IGNORECASE)
_HEDGE = re.compile(
    r"possible|probable|suspicious\s+for|concerning\s+for|worrisome(?:\s+for)?|"
    r"could\s+be|cannot\s+(?:exclude|rule\s+out)|rule\s+out|\br/o\b|differential|"
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

# "Ablation" is organ-ambiguous (renal tumor ablation vs. saphenous-vein RFA vs.
# cardiac ablation), so an ablation status is only pinned to a renal/organ dx
# when it sits in that organ's context and NOT a competing vascular/cardiac one.
# Nephrectomy / TURBT / active-surveillance are organ-specific enough to trust.
_ORGAN_ANCHOR = {
    "renal": re.compile(r"renal|kidney|nephr|interpolar|upper[\s-]?pole|"
                        r"lower[\s-]?pole|the\s+mass|the\s+lesion|the\s+tumou?r",
                        re.IGNORECASE),
    "bladder": re.compile(r"bladder|urotheli|intravesical|cystoscop", re.IGNORECASE),
    "upper_tract": re.compile(r"ureter|renal\s+pelvis|upper[\s-]tract", re.IGNORECASE),
}
_NONRENAL_ABLATION = re.compile(
    r"saphenous|varicose|\bvein\b|venous|\bGSV\b|coronary|cardiac|atrial|"
    r"pulmonary\s+vein|hepatic|\bliver\b|thyroid|endometrial|\bnerve\b|prostate",
    re.IGNORECASE)
# A definitive procedure named in a PLANNING context is a recommendation, not a
# status that has happened (KIND / RIVERA: "consultation for ... nephrectomy").
_PLANNED_CTX = re.compile(
    r"recommend|consult|consideration\s+of|\bversus\b|\bvs\.?\b|plan(?:ned|s)?\s+for|"
    r"refer(?:ral)?|option|candidate\s+for|would\s+be|discuss|consider(?:ing)?|"
    # a comma-series of mutually-exclusive treatments (…, ablation, SBRT,
    # surveillance as per NCCN) is a counseling menu, not a completed status
    r"\bSBRT\b|as\s+per\s+NCCN|per\s+NCCN\s+guideline",
    re.IGNORECASE)


def _status_for(organ: str, text: str, sre: "re.Pattern") -> str:
    """First status match that actually pertains to *organ* and has HAPPENED.

    Organ-ambiguous statuses (ablation, active surveillance) must sit in the
    organ's own context — so a saphenous-vein radiofrequency ablation or a
    PROSTATE active-surveillance mention is not pinned to a renal mass
    (GONZALES). A definitive local therapy (nephrectomy / ablation) counts only
    when completed, not merely planned/recommended (KIND, RIVERA)."""
    anchor = _ORGAN_ANCHOR.get(organ)
    for sm in sre.finditer(text):
        phrase = sm.group(0)
        low = phrase.lower()
        window = text[max(0, sm.start() - 70):sm.end() + 70]
        if "ablation" in low and _NONRENAL_ABLATION.search(window):
            continue
        # organ-ambiguous: require the organ's own context nearby
        if ("ablation" in low or "surveillance" in low) and anchor and not anchor.search(window):
            continue
        # definitive therapy only counts if done, not planned
        if ("nephrectomy" in low or "ablation" in low) and "s/p" not in low \
                and _PLANNED_CTX.search(window):
            continue
        return _clean(phrase)
    return ""


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
            # Radiology-benign guard: an adrenal lesion the report characterizes
            # as a myelolipoma / adenoma / washout / <10 HU / benign / stable is
            # BENIGN, not "of uncertain significance" — so it does not lead the
            # CC over the patient's actual cancer (CHATMAN/MOLINA/CRAWFORD).
            if organ == "adrenal" and (
                    _ADRENAL_BENIGN_CTX.search(text[max(0, m.start() - 60):m.end() + 90])
                    or _ADRENAL_BENIGN_STRONG.search(text)):
                consider("adrenal", "benign", "benign adrenal lesion",
                         _clean(m.group(0)))
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
            dx.status = _status_for(organ, text, sre)
    order = {"cancer": 0, "indeterminate": 1, "benign": 2}
    return sorted(by_organ.values(), key=lambda d: (order[d.category], d.organ))
