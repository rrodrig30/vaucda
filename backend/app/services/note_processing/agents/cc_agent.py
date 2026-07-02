"""
Chief Complaint (CC) Agent

Combines CCs from all notes, focusing on urologic concerns.

A urology clinic CC must always be urologic. This agent enforces that
invariant by:
  1. Filtering extracted CCs to keep only those containing a urologic
     keyword (so a stray "annual physical" or "back pain" CC carried
     over from an old non-urologic visit can't be the final CC).
  2. Falling back to a CC derived from the patient's urologic context
     (pathology, PMH, PSA trend) when no urologic CC is extracted.
  3. Returning a generic "Urology follow-up" sentinel only as the last
     resort — never an empty string. The renderer no longer needs the
     "CC: Unknown" branch.
"""

import re
from typing import List, Dict, Optional, Tuple
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


# Urologic-content marker. If a CC string contains ANY of these tokens,
# we treat it as urologic and pass it through. Order doesn't matter;
# the alternation runs case-insensitive. Tokens are intentionally broad
# (substring match where useful — "prostat" catches prostate /
# prostatitis / prostatectomy / prostatomegaly without 5 separate rules).
UROLOGIC_KEYWORDS = re.compile(
    r'(?:'
    r'prostat|psa\b|gleason|adenocarcinoma|grade\s+group|'
    r'\bbph\b|hyperplasia|'
    r'erectile|impoten|libido|hypogonad|low\s+t|testosterone|'
    r'kidney|renal|hydronephrosis|nephrolith|nephrectom|'
    r'stone|calcul|urolithiasis|'
    r'bladder|cystitis|cystoscop|hematuria|incontinen|overactive\s+bladder|'
    r'\boab\b|urinary|\bluts\b|voiding|nocturia|frequency|urgency|dysuria|'
    r'retention|urethr|stricture|'
    r'testic|scrotum|orchi|varicocel|hydrocel|spermatocel|'
    r'fertilit|infertilit|semen|sperm|'
    r'penil|peyron|priapism|'
    r'ureter|ureteral|stent|pyelo|turp|turbt|prostatect|'
    r'adrenal|myelolipoma|pheochromocytoma|'
    r'urolog|\bgu\b|genitourinary|micturition|enuresis|urodynamic|uroflow|'
    r'foley|catheter|'
    r'circumcis|phimosis|paraphimosis|epididym|'
    r'gross\s+hematuria|microscopic\s+hematuria|'
    r'rising\s+psa|elevated\s+psa|psa\s+kinetics|'
    r'bladder\s+cancer|kidney\s+cancer|prostate\s+cancer|testicular\s+cancer'
    r')',
    re.IGNORECASE,
)


def _is_urologic_text(text: str) -> bool:
    """True iff `text` contains any urologic keyword."""
    return bool(text) and bool(UROLOGIC_KEYWORDS.search(text))


# Primary diagnosis -> CC string, in priority order. Earlier entries take
# precedence when multiple match (e.g. prostate-cancer + BPH -> prostate
# cancer wins because the patient is being followed for the cancer).
#
# Each pattern matches BOTH word orderings VA charts use, e.g. both
# "prostate cancer" AND "malignant neoplasm of prostate". The PMH list
# routinely uses the ICD-style reversed phrasing.
_DERIVED_CC_RULES = [
    (re.compile(
        r'\bprostat(?:e|ic)\s+(?:cancer|adenocarcinoma|carcinoma|malignan)'
        r'|(?:malignant\s+)?neoplasm\s+of\s+(?:the\s+)?prostat'
        r'|prostat(?:e|ic)\s+neoplasm',
        re.I,
     ),
     "Follow-up for prostate cancer"),
    (re.compile(
        r'\bbladder\s+(?:cancer|carcinoma|urothelial|malignan)'
        r'|(?:malignant\s+)?neoplasm\s+of\s+(?:the\s+)?bladder'
        r'|urothelial\s+(?:carcinoma|cancer)',
        re.I,
     ),
     "Follow-up for bladder cancer"),
    (re.compile(
        r'\b(?:renal|kidney)\s+(?:cell\s+)?(?:cancer|carcinoma|mass|tumor|malignan)'
        r'|(?:malignant\s+)?neoplasm\s+of\s+(?:the\s+)?(?:kidney|renal)',
        re.I,
     ),
     "Follow-up for kidney cancer"),
    (re.compile(
        r'\btesticular\s+(?:cancer|carcinoma|mass|tumor)'
        r'|(?:malignant\s+)?neoplasm\s+of\s+(?:the\s+)?test(?:is|icle)',
        re.I,
     ),
     "Follow-up for testicular cancer"),
    (re.compile(
        r'\bpenile\s+(?:cancer|carcinoma|malignan)'
        r'|(?:malignant\s+)?neoplasm\s+of\s+(?:the\s+)?penis',
        re.I,
     ),
     "Follow-up for penile cancer"),
    (re.compile(r'\b(?:benign\s+prostatic\s+hyperplasia|BPH)\b', re.I),
     "Follow-up for benign prostatic hyperplasia"),
    (re.compile(r'\b(?:nephrolithiasis|urolithiasis|kidney\s+stones?|renal\s+calcul|ureteral\s+stone)\b', re.I),
     "Follow-up for urolithiasis"),
    (re.compile(r'\b(?:elevated|rising)\s+psa\b|\bpsa\b.*\bmonitor', re.I),
     "Follow-up for elevated PSA"),
    (re.compile(r'\b(?:gross|microscopic)?\s*hematuria\b', re.I),
     "Follow-up for hematuria"),
    (re.compile(r'\berectile\s+dysfunction\b|\bED\b', re.I),
     "Follow-up for erectile dysfunction"),
    (re.compile(r'\bhypogonad|low\s+testosterone', re.I),
     "Follow-up for hypogonadism"),
    (re.compile(r'\b(?:overactive\s+bladder|OAB|urge\s+incontinence)\b', re.I),
     "Follow-up for overactive bladder"),
    (re.compile(r'\b(?:stress\s+(?:urinary\s+)?incontinence|urinary\s+incontinence)\b', re.I),
     "Follow-up for urinary incontinence"),
    (re.compile(r'\b(?:LUTS|lower\s+urinary\s+tract\s+symptoms|voiding\s+symptoms)\b', re.I),
     "Follow-up for lower urinary tract symptoms"),
    (re.compile(r'\b(?:varicocele|hydrocele|spermatocele|epididymal\s+cyst)\b', re.I),
     "Follow-up for scrotal condition"),
    (re.compile(r'\b(?:peyronie|priapism|phimosis|paraphimosis)\b', re.I),
     "Follow-up for penile condition"),
    (re.compile(r'\b(?:urethral\s+stricture|urethral\s+narrowing)\b', re.I),
     "Follow-up for urethral stricture"),
    (re.compile(r'\b(?:male\s+infertility|infertility|low\s+sperm|azoospermia|oligospermia)\b', re.I),
     "Follow-up for male infertility"),
    (re.compile(r'\badrenal\s+(?:mass|myelolipoma|adenoma|tumor|incidentaloma|nodule)\b', re.I),
     "Follow-up for adrenal mass"),
    (re.compile(r'\b(?:UTI|urinary\s+tract\s+infection|recurrent\s+UTI|pyelonephritis)\b', re.I),
     "Follow-up for urinary tract infection"),
    (re.compile(r'\bcystocele\b|\b(?:pelvic\s+organ\s+)?prolapse\b', re.I),
     "Follow-up for pelvic organ prolapse"),
]


def _derive_cc_from_context(
    pmh: Optional[str],
    pathology: Optional[str],
    psa_data: Optional[str],
) -> str:
    """Derive a urologic CC from clinical context when no extracted CC works.

    Searches PMH then pathology then PSA data for the highest-priority
    urologic diagnosis. Returns a CC like "Follow-up for prostate cancer"
    or, if nothing matches, the safe generic "Urology follow-up".
    """
    haystack = '\n'.join(s for s in (pmh, pathology, psa_data) if s)
    if haystack:
        for pat, cc in _DERIVED_CC_RULES:
            if pat.search(haystack):
                return cc
    return "Urology follow-up"


def _apply_terminology(cc_text: str) -> str:
    """Standardize 'consult' → 'follow-up', drop 'New patient', strip a stale
    leading age phrase."""
    cc_text = re.sub(r'\bConsult\s+for\b', 'Follow-up for', cc_text, flags=re.IGNORECASE)
    cc_text = re.sub(r'\bconsult\b', 'follow-up', cc_text, flags=re.IGNORECASE)
    cc_text = re.sub(r'^\s*New\s+patient\s+', '', cc_text, flags=re.IGNORECASE)
    # A CC should not restate the patient's age — the banner and HPI own it, and
    # a source-note age is frequently stale (the CREWS 62-vs-63 mismatch). Strip
    # a leading "<N>-year-old male/female" phrase and re-capitalize.
    stripped = re.sub(
        r'^\s*(?:an?\s+)?\d{1,3}[\s-]year[\s-]old\s+(?:male|female|man|woman)\s+',
        '', cc_text, flags=re.IGNORECASE)
    if stripped != cc_text and stripped:
        cc_text = stripped[0].upper() + stripped[1:]
    return cc_text.strip()


# Completed-treatment phrasings VA charts use. Each tuple is (regex,
# canonical type). The first match wins; order matters only when a
# single document could legitimately have more than one (e.g. salvage
# RT after RP — but in that case the patient's *current* status is
# what matters; the recency check below picks the most recent).
_TREATMENT_PATTERNS = [
    ('prostatectomy', re.compile(
        r'\bs/?p\s+(?:radical\s+)?prostatectomy\b'
        r'|\b(?:status\s+post|post)[-\s]+(?:radical\s+)?prostatectomy\b'
        r'|\bunderwent\s+(?:robotic\s+|robotic[-\s]assisted\s+|open\s+|laparoscopic\s+)?(?:radical\s+)?prostatectomy\b'
        r'|\bprostatectomy\s+(?:on|completed|performed)\b'
        r'|\bhad\s+(?:a\s+)?(?:radical\s+)?prostatectomy\b'
        # PSH-style "S/P RALP" / "S/P RARP" / "S/P RRP" — completion
        # context implicit in the "s/p" prefix.
        r'|\bs/?p\s+(?:RALP|RARP|RRP)\b'
        r'|\b(?:status\s+post|post)[-\s]+(?:RALP|RARP|RRP)\b',
        re.IGNORECASE,
    )),
    ('radiation', re.compile(
        # Require an EXPLICIT completion / past-tense verb immediately
        # adjacent to the radiation term. The earlier
        # "\bdefinitive\s+(?:radiation|...)" clause matched any
        # discussion of "definitive radiation therapy" — including
        # "discussed definitive radiation therapy" — flipping
        # treatment-naive patients to TREATED.
        r'\bcompleted\s+(?:external\s+beam\s+)?(?:radiation|radiotherapy|EBRT|XRT|IMRT)\b'
        r'|\b(?:external\s+beam\s+)?(?:radiation|radiotherapy|EBRT|XRT|IMRT)\s+(?:therapy\s+)?(?:completed|finished|ended)\b'
        r'|\bs/?p\s+(?:radiation|radiotherapy|EBRT|XRT|IMRT)\b'
        r'|\b(?:status\s+post|post)[-\s]+(?:radiation|radiotherapy|EBRT|XRT|IMRT)\b'
        r'|\b(?:underwent|received)\s+(?:definitive\s+)?(?:external\s+beam\s+)?(?:radiation|radiotherapy|EBRT|XRT|IMRT)\b',
        re.IGNORECASE,
    )),
    ('brachytherapy', re.compile(
        r'\bs/?p\s+brachytherapy\b'
        r'|\bcompleted\s+brachytherapy\b'
        r'|\bunderwent\s+brachytherapy\b'
        r'|\bseed\s+implant(?:ation)?\b'
        r'|\b(?:status\s+post|post)[-\s]+brachytherapy\b',
        re.IGNORECASE,
    )),
    ('focal therapy', re.compile(
        # Require completion verb for focal therapy too. Bare "focal
        # therapy" or "cryotherapy" mentions in option-discussion prose
        # ("we discussed focal therapy") would otherwise trigger.
        r'\bunderwent\s+(?:HIFU|high[-\s]?intensity\s+focused\s+ultrasound|'
        r'cryotherapy|cryoablation|focal\s+therapy)\b'
        r'|\bcompleted\s+(?:HIFU|high[-\s]?intensity\s+focused\s+ultrasound|'
        r'cryotherapy|cryoablation|focal\s+therapy)\b'
        r'|\bs/?p\s+(?:HIFU|cryotherapy|cryoablation|focal\s+therapy)\b'
        r'|\b(?:status\s+post|post)[-\s]+(?:HIFU|cryotherapy|cryoablation|focal\s+therapy)\b',
        re.IGNORECASE,
    )),
]


# Discussion / intent / consideration markers that, when they precede a
# treatment match, mean the patient is being COUNSELED about that option,
# not that the treatment has been performed. The detector must skip
# matches whose preceding ~80 characters contain any of these — without
# this filter, a single sentence like "we discussed definitive radiation
# therapy as an option" promotes the patient to s/p-radiation status.
_DISCUSSION_NEGATION_RE = re.compile(
    r'\b(?:discuss(?:ed|ing|ion)?|consider(?:ed|ing|ation)?|'
    r'offer(?:ed|ing)?|interest(?:ed)?\s+in|may\s+benefit|'
    r'option(?:s)?\s+(?:of|for|include|are|to)|'
    r'candidate\s+(?:for|of)|recommend(?:ed|ing|ation)?|'
    r'plan(?:ned|ning)?\s+(?:for|to)|consult(?:ed|ation)?\s+(?:for|to)|'
    r'referred\s+(?:for|to)|scheduled\s+(?:for|to)|'
    r'await(?:ing|s)?|elect(?:ed)?(?:\s+against)?|declined|'
    r'refused|deferred|under\s+consideration|'
    r'including|consist(?:ing|s)\s+of|such\s+as|'
    r'pursuing|pursue)\b',
    re.IGNORECASE,
)


def _detect_treatment_history(
    psh: Optional[str],
    clinical_document: Optional[str],
) -> Optional[Dict[str, str]]:
    """Detect whether definitive treatment for prostate cancer was completed.

    Returns {"type": <type>} when a completion marker is found, else None.

    PSH is the most reliable haystack — completed procedures get logged
    there. The raw clinical document is a fallback that requires
    additional negation filtering, because prose like "we discussed
    definitive radiation therapy as an option" otherwise registers as
    "s/p radiation". For each match in the raw document, we look back
    ~80 chars for discussion / intent / option-listing markers and skip
    matches that have them.
    """
    # PSH first — completion verbs in PSH are reliable.
    if psh:
        for t_type, pat in _TREATMENT_PATTERNS:
            if pat.search(psh):
                return {"type": t_type}
    if not clinical_document:
        return None
    for t_type, pat in _TREATMENT_PATTERNS:
        for m in pat.finditer(clinical_document):
            # Look back ~80 chars for option-discussion language.
            window_start = max(0, m.start() - 80)
            preceding = clinical_document[window_start:m.start()]
            if _DISCUSSION_NEGATION_RE.search(preceding):
                continue
            # Also reject when the match itself sits inside a "options
            # discussed including [X, Y, Z]" list. Look forward ~30
            # chars for comma-separated options. Skip if a comma-or-and
            # delimiter is within 30 chars of the match end and another
            # treatment-keyword (RALP/AS/XRT/EBRT/IMRT/surgery/etc.)
            # appears nearby — that pattern is an enumeration of
            # options, not a completion statement.
            tail = clinical_document[m.end():m.end() + 50]
            if (re.search(r'^\s*[,]\s*and\s+\w+', tail, re.IGNORECASE)
                or re.search(r'^\s*,\s+(?:and\s+)?(?:AS|RALP|RP|RARP|'
                             r'EBRT|XRT|IMRT|surgery|prostatectomy|'
                             r'observation|active\s+surveillance|'
                             r'brachytherapy)\b',
                             tail, re.IGNORECASE)):
                continue
            return {"type": t_type}
    return None


# Treatment-type → display label used in reframed CCs.
_TREATMENT_LABEL = {
    'radiation': 'radiation therapy',
    'prostatectomy': 'prostatectomy',
    'brachytherapy': 'brachytherapy',
    'focal therapy': 'focal therapy',
}


def _assess_psa_trend(psa_data: Optional[str]) -> Dict[str, Optional[float]]:
    """Parse a PSA curve / list and return {current, max, ratio, trend}.

    Accepts the project's standard PSA-curve format
    ("[r] MMM DD, YYYY HH:MM    VALUE [H]") plus plain "PSA TOTAL  N.NN"
    lines. PSA curves in this codebase are stored reverse-chronological
    so the first numeric is the most recent. The `ratio` field
    (current / max) is what the reframer uses as a coarse "responding"
    indicator; the `trend` is computed against the second-most-recent
    value.
    """
    result: Dict[str, Optional[float]] = {
        'current': None, 'max': None, 'min': None, 'ratio': None,
        'trend': None,
    }
    if not psa_data:
        return result

    values: List[float] = []
    for raw_line in psa_data.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        # Skip "PSA CURVE:" header and similar non-data lines.
        if not re.search(r'\d', line):
            continue
        # The PSA value is the LAST decimal number on the line. This
        # robustly handles every format the codebase produces:
        #   "[r] Dec 26, 2025 14:41    0.38"           (PSA curve)
        #   "Dec 26, 2025 14:41: 0.38"                 (extract_psa output)
        #   "PSA TOTAL  5.99 H  ng/mL  0.2 - 4.0"      (lab line — see filter below)
        #   "5.79 H"                                    (bare value)
        # Skip lines that look like a lab-reference range (the trailing
        # numbers are the reference bounds, not the value); those lines
        # show the PSA value as the FIRST number, so we extract differently.
        is_lab_range_line = bool(re.search(
            r'\bPSA\b.*?\d+(?:\.\d+)?\s*H?\b.*?\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?',
            line, re.IGNORECASE,
        ))
        if is_lab_range_line:
            # Take the first numeric value after "PSA"
            m = re.search(
                r'\bPSA\s*(?:TOTAL)?\s+(\d+(?:\.\d+)?)',
                line, re.IGNORECASE,
            )
            if m:
                try:
                    values.append(float(m.group(1)))
                except ValueError:
                    pass
            continue
        # Default: last decimal number on the line.
        nums = re.findall(r'\d+\.\d+', line)
        if nums:
            try:
                values.append(float(nums[-1]))
                continue
            except ValueError:
                pass
        # Fall back to last integer (some entries lack a decimal point).
        nums = re.findall(r'\b\d+\b', line)
        if nums:
            # Skip the obvious time/date components: 1-2 digit values that
            # look like HH or DD aren't useful as PSA values.
            last = int(nums[-1])
            if last >= 0:
                # Reject unrealistically high values (likely a year).
                if last < 1000:
                    values.append(float(last))

    if not values:
        return result

    current = values[0]
    max_v = max(values)
    min_v = min(values)
    result['current'] = current
    result['max'] = max_v
    result['min'] = min_v
    result['ratio'] = (current / max_v) if max_v > 0 else None
    if len(values) >= 2:
        prev = values[1]
        if prev > 0 and current < prev * 0.95:
            result['trend'] = 'falling'
        elif prev > 0 and current > prev * 1.05:
            result['trend'] = 'rising'
        else:
            result['trend'] = 'stable'
    return result


# CC phrasings that become *stale* the moment definitive treatment has
# been completed with a good biochemical response. "active surveillance"
# is explicitly excluded — that's a valid management pattern, not stale.
_STALE_CC_INDICATORS = re.compile(
    r'\bpersistent\s+(?:prostate\s+)?(?:cancer|disease|malignancy|carcinoma|tumor)\b'
    r'|\bactive\s+(?:prostate\s+)?(?:cancer|disease|malignancy|carcinoma|tumor)\b'
    r'|\buntreated\s+(?:prostate\s+)?(?:cancer|disease|malignancy|carcinoma|tumor)\b'
    r'|\brising\s+psa\b'
    r'|\belevated\s+psa\b'
    r'|\bconcerning\s+psa\b',
    re.IGNORECASE,
)


def _is_biochemically_responding(
    treatment_type: str,
    psa: Dict[str, Optional[float]],
) -> Optional[bool]:
    """Coarse biochemical-response classifier.

    Returns True (responding), False (likely recurrence), or None
    (insufficient PSA data to decide). Thresholds:

      - Post-prostatectomy: response = current < 0.2 ng/mL. Detectable
        PSA after RP is the standard biochemical-recurrence threshold.

      - Post-radiation / brachytherapy / focal therapy: Phoenix
        criterion is PSA nadir + 2.0 ng/mL. We approximate the nadir
        as the minimum PSA value in the series (which is correct as
        long as the series spans treatment AND the patient at some
        point reached their post-treatment nadir). If current PSA is
        more than 2.0 above this approximated nadir, classify as
        recurrence. Otherwise — and as a secondary check — accept
        either ratio (current/max) < 0.5 OR absolute current < 2.0
        ng/mL as evidence of response.
    """
    current = psa.get('current')
    if current is None:
        return None
    if treatment_type == 'prostatectomy':
        return current < 0.2

    # Radiation / brachy / focal — Phoenix-like check first.
    min_v = psa.get('min')
    if min_v is not None and current - min_v > 2.0:
        # PSA climbed >2.0 ng/mL above its observed nadir — recurrence.
        return False

    max_v = psa.get('max')
    ratio = psa.get('ratio')
    if max_v is None or max_v <= 0:
        return current < 2.0
    if ratio is not None and ratio < 0.5:
        return True
    return current < 2.0


# A CC that names a prostate-cancer diagnosis without specifying a
# post-treatment qualifier is also stale once definitive treatment has
# been completed. "Prostate cancer", "Follow-up for prostate cancer",
# "PCa follow-up" all need to become "Follow-up after <treatment> for
# prostate cancer" so the CC reflects current state. We DON'T want to
# overwrite a CC that's already post-treatment-aware (e.g. "Follow-up
# after radiation therapy for prostate cancer") or that explicitly
# refers to current treatment ("on active surveillance", "on ADT").
_BARE_PROSTATE_CANCER_CC = re.compile(
    r'(?:^|\b)'
    r'(?:follow[-\s]?up\s+(?:for|of)\s+)?'
    r'(?:prostate\s+(?:cancer|adenocarcinoma|carcinoma|malignancy)'
    r'|PCa|prostate\s+ca\b)',
    re.IGNORECASE,
)
_ALREADY_POST_TREATMENT_CC = re.compile(
    r'\b(?:after\s+(?:radiation|prostatectomy|brachytherapy|focal|treatment|XRT|EBRT|IMRT)'
    r'|post[-\s](?:radiation|prostatectomy|brachytherapy|XRT|EBRT|IMRT)'
    r'|s/?p\s+(?:radiation|prostatectomy|brachytherapy|XRT|EBRT|IMRT)'
    r'|biochemical\s+recurrence)',
    re.IGNORECASE,
)
_CURRENT_MGMT_CC = re.compile(
    r'\b(?:active\s+surveillance|on\s+ADT|on\s+androgen\s+deprivation|'
    r'on\s+leuprolide|on\s+lupron|on\s+degarelix)',
    re.IGNORECASE,
)


def _reframe_post_treatment_cc(
    cc: str,
    treatment: Optional[Dict[str, str]],
    psa: Dict[str, Optional[float]],
) -> str:
    """Replace stale or generic prostate-cancer CCs with a clinically
    accurate post-treatment CC when the data supports it.

    The reframer now fires in EITHER of two cases:
      A. CC contains a stale-management marker (persistent / active /
         rising PSA / elevated PSA / etc.) — historical behavior.
      B. CC names a bare prostate-cancer diagnosis without a
         post-treatment qualifier (e.g. "Prostate cancer", "Follow-up
         for prostate cancer", "PCa follow-up") AND the patient is
         clearly post-treatment with biochemical response.

    No-op when:
      - no completed definitive treatment is detected, OR
      - PSA data is insufficient to confirm response, OR
      - CC already mentions a post-treatment qualifier
        ("after radiation", "s/p XRT", "biochemical recurrence"), OR
      - CC explicitly describes current management mode
        ("on active surveillance", "on ADT").
    """
    if not cc or not treatment:
        return cc
    if _ALREADY_POST_TREATMENT_CC.search(cc):
        return cc
    if _CURRENT_MGMT_CC.search(cc):
        return cc

    # Decide which gate to use: stale-marker (existing) or bare-PCa-CC
    # (new). At least one must match for us to consider reframing.
    is_stale = bool(_STALE_CC_INDICATORS.search(cc))
    is_bare_pca = bool(_BARE_PROSTATE_CANCER_CC.search(cc))
    if not (is_stale or is_bare_pca):
        return cc

    t_type = treatment.get('type', '')
    responding = _is_biochemically_responding(t_type, psa)
    if responding is None:
        # Can't confirm response from PSA — leave CC alone rather than
        # risk a wrong reframe.
        return cc

    label = _TREATMENT_LABEL.get(t_type, t_type or 'treatment')
    if responding:
        return f"Follow-up after {label} for prostate cancer"
    return f"Follow-up for biochemical recurrence after {label} for prostate cancer"


def _phase_driven_cc(
    current_phase: Optional[str],
    current_active_treatments: Optional[List[str]],
) -> Optional[str]:
    """Generate a CC directly from the deterministic phase verdict.

    Phase-driven CCs are clinically correct by construction: when the
    timeline + phase classifier say the patient is on mCRPC combination
    therapy, the CC must say so — regardless of what stale prior-visit
    CCs are floating around. This bypasses the LLM-combine path that
    has been producing wrong CCs like "Follow-up for prostate cancer on
    ADT with rising PSA" for a patient whose PSA is actually falling.

    Returns None for phases where the CC depends on more nuanced context
    (TREATMENT_NAIVE / POST_TREATMENT_SURVEILLANCE / UNCERTAIN) — the
    existing logic handles those well.
    """
    if not current_phase:
        return None

    def _has(meds_keyword: str) -> bool:
        if not current_active_treatments:
            return False
        kw = meds_keyword.lower()
        return any(kw in m.lower() for m in current_active_treatments)

    has_ar = any(_has(k) for k in ("abiraterone", "enzalutamide", "apalutamide", "darolutamide"))
    has_adt = any(_has(k) for k in ("eligard", "leuprolide", "lupron", "degarelix"))

    if current_phase == "METASTATIC_CASTRATION_RESISTANT":
        bits = []
        if has_adt:
            bits.append("Eligard/ADT")
        if has_ar:
            ar_names = []
            if _has("abiraterone"):
                ar_names.append("abiraterone")
            if _has("enzalutamide"):
                ar_names.append("enzalutamide")
            if _has("apalutamide"):
                ar_names.append("apalutamide")
            if _has("darolutamide"):
                ar_names.append("darolutamide")
            if ar_names:
                bits.append(" + ".join(ar_names))
        suffix = f" on {' + '.join(bits)}" if bits else ""
        return f"Follow-up of metastatic castration-resistant prostate cancer{suffix}"

    if current_phase == "METASTATIC_HORMONE_SENSITIVE":
        suffix = " on ADT" if has_adt else ""
        if has_ar:
            suffix += " with AR-pathway intensification"
        return f"Follow-up of metastatic prostate cancer{suffix}"

    if current_phase == "SALVAGE_OR_RESTART":
        return "Follow-up after restart of androgen-deprivation therapy for prostate cancer"

    if current_phase == "BIOCHEMICAL_RECURRENCE":
        return "Evaluation of biochemical recurrence after prior treatment for prostate cancer"

    if current_phase == "ON_INITIAL_TREATMENT":
        if has_adt and has_ar:
            return "Follow-up during ADT and AR-pathway therapy for prostate cancer"
        if has_adt:
            return "Follow-up during androgen-deprivation therapy for prostate cancer"
        return "Follow-up during treatment for prostate cancer"

    if current_phase == "PROGRESSION":
        return "Follow-up of prostate cancer with disease progression on prior therapy"

    # POST_TREATMENT_SURVEILLANCE: name the prior modality (radiation /
    # prostatectomy / focal therapy / brachytherapy) when the timeline
    # can identify it from the most recent COMPLETED treatment event.
    if current_phase == "POST_TREATMENT_SURVEILLANCE":
        # Modality inference is done by the caller via the patient_facts
        # timeline; here we return the templated baseline and let the
        # caller's reframe-step append modality detail if available.
        return "Follow-up for prostate cancer surveillance after prior treatment"

    # TREATMENT_NAIVE / UNCERTAIN — fall through to the existing logic
    # which derives the CC from PMH / pathology / PSA candidates plus the
    # multi-CC reconciliation path.
    return None


# Mapping of (PMH keyword regex, canonical CC phrase) — ordered by
# clinical priority. The first match wins. Used for TREATMENT_NAIVE
# patients where there is no prior cancer-directed therapy to anchor
# the CC and we need to derive it from the primary urologic concern.
_TX_NAIVE_CC_RULES: Tuple[Tuple[str, str], ...] = (
    (r"\bhematuria\b", "Follow-up for hematuria"),
    (r"\belevated\s+PSA\b|\brising\s+PSA\b|\bPSA\s+elevation\b",
     "Follow-up for elevated PSA"),
    (r"\b(?:bladder|urothelial)\s+cancer\b|\bTCC\b",
     "Follow-up for bladder cancer"),
    (r"\b(?:renal|kidney)\s+(?:mass|cell|cancer)\b|\bRCC\b",
     "Follow-up for renal mass"),
    (r"\b(?:nephrolithiasis|urolithiasis|kidney\s+stone|renal\s+stone)\b",
     "Follow-up for nephrolithiasis"),
    (r"\b(?:BPH|benign\s+prostatic\s+hyperplasia|LUTS|lower\s+urinary\s+tract|"
     r"outflow\s+obstruction)\b",
     "Follow-up for benign prostatic hyperplasia and lower urinary tract symptoms"),
    (r"\b(?:overactive\s+bladder|OAB|urgency\s+incontinence|"
     r"urge\s+incontinence)\b",
     "Follow-up for overactive bladder"),
    (r"\b(?:stress\s+incontinence|SUI|urinary\s+incontinence)\b",
     "Follow-up for urinary incontinence"),
    (r"\b(?:erectile\s+dysfunction|ED)\b",
     "Follow-up for erectile dysfunction"),
    (r"\b(?:recurrent\s+UTI|chronic\s+UTI|urinary\s+tract\s+infection)\b",
     "Follow-up for recurrent urinary tract infection"),
    (r"\bvaricocele\b", "Follow-up for varicocele"),
    (r"\bhypogonadism\b|\blow\s+testosterone\b",
     "Follow-up for hypogonadism"),
    (r"\bperonie\w*\s+disease\b", "Follow-up for Peyronie's disease"),
    (r"\b(?:male\s+)?infertility\b|\bsemen\s+analysis\b",
     "Follow-up for male infertility"),
)


def _most_recent_completed_modality(timeline: List) -> Optional[str]:
    """Identify the most recent definitive treatment for naming in the
    POST_TREATMENT_SURVEILLANCE CC. Maps the raw modality token to a
    human-readable phrase.
    """
    if not timeline:
        return None

    def _canon(m: str) -> Optional[str]:
        s = (m or "").lower()
        if "radiation" in s or s in ("xrt", "ebrt", "imrt", "sbrt", "igrt"):
            return "radiation therapy"
        if "brachytherapy" in s or "seed" in s:
            return "brachytherapy"
        if "prostatectomy" in s or s in ("ralp", "rarp", "rrp"):
            return "radical prostatectomy"
        if "focal" in s or s in ("hifu", "tulsa"):
            return "focal therapy"
        return None

    # Walk events latest-first
    best: Optional[Tuple[str, str]] = None
    for e in timeline:
        if getattr(e, "event_type", "") != "TREATMENT_COMPLETED":
            continue
        canon = _canon(getattr(e, "modality", ""))
        if not canon:
            continue
        dk = getattr(e, "date_key", "") or ""
        if best is None or dk > best[0]:
            best = (dk, canon)
    return best[1] if best else None


def _primary_cancer_anchored_cc(
    gu_notes: List[Dict[str, str]],
    document_pmh: Optional[str],
    document_pathology: Optional[str],
    document_psh: Optional[str],
    clinical_document: Optional[str],
) -> Optional[str]:
    """Return the patient's own most-recent CC that names the primary
    urologic cancer, when source confirms the cancer.

    Anchors to: prostate cancer, renal cell carcinoma, bladder cancer.
    Detection scans PMH + pathology + PSH + raw doc (capped) because
    extract_pmh() returns "" for many real charts (only supports VA
    ALL PROBLEMS LIST format) — pathology, PSH s/p entries, and the
    raw document are reliable cancer-signal sources.

    Returns the EARLIEST-in-list (most-recent) matching CC, with
    length as tiebreaker. Picks "Prostate cancer on Active
    Surveillance" over an older "Follow-up after prostate cancer
    treatment." Falls through (returns None) when no cancer signal
    exists or no CC mentions it.
    """
    all_ccs_raw = [n.get("CC", "") for n in gu_notes if n.get("CC")]
    urologic_ccs = [cc for cc in all_ccs_raw if _is_urologic_text(cc)]
    if not urologic_ccs:
        return None
    cancer_context = " ".join((
        (document_pmh or "").lower(),
        (document_pathology or "").lower(),
        (document_psh or "").lower(),
        (clinical_document or "").lower()[:50000],  # cap scan for perf
    ))
    cancer_anchors: List[str] = []
    if ("prostate cancer" in cancer_context
            or "prostatic adenocarcinoma" in cancer_context
            or re.search(r'\bmalignant\s+neoplasm\s+of\s+(?:the\s+)?prostate\b',
                          cancer_context)
            or re.search(r'\bgleason\s+\d', cancer_context)
            or re.search(r'\bs/p\s+(?:imrt|radical\s+prostatectomy|ralp|rrp|brachy)\b',
                          cancer_context)):
        cancer_anchors.append("prostate cancer")
    if ("renal cell carcinoma" in cancer_context
            or "kidney cancer" in cancer_context
            or re.search(r'\bclear[\s-]cell\s+(?:rcc|renal)\b', cancer_context)):
        cancer_anchors.append("renal cell carcinoma")
        cancer_anchors.append("renal cell")
    if ("bladder cancer" in cancer_context
            or "urothelial carcinoma" in cancer_context
            or "urothelial cancer" in cancer_context):
        cancer_anchors.append("bladder cancer")
        cancer_anchors.append("urothelial")
    # Length floor: refuse to override the downstream paths with a
    # terse, low-information CC like "Prostate Cancer". Such bare
    # cancer-name CCs ARE technically anchored but the LLM-combine /
    # phase-driven paths usually produce a more informative variant
    # ("Evaluation of biochemical recurrence after prior treatment for
    # prostate cancer", "Follow-up after prostatectomy for prostate
    # cancer"). Williams + Fritz regressed when the anchor returned
    # bare cancer names from a single short source CC.
    MIN_ANCHORED_CC_CHARS = 25
    for anchor_key in cancer_anchors:
        matching = [(i, c) for i, c in enumerate(urologic_ccs)
                    if anchor_key in c.lower()]
        if not matching:
            continue
        # Prefer EARLIEST + LONGEST among informative candidates only.
        informative = [(i, c) for i, c in matching
                       if len(c.strip()) >= MIN_ANCHORED_CC_CHARS]
        if informative:
            informative.sort(key=lambda x: (x[0], -len(x[1])))
            return informative[0][1]
        # All candidates are bare cancer names — fall through to
        # downstream paths so they can synthesize a richer CC.
        return None
    return None


def _treatment_naive_cc_from_pmh(document_pmh: str) -> Optional[str]:
    """Derive a CC for a treatment-naive patient from PMH + pathology
    keywords. Returns None when no recognizable urologic primary
    concern is present (the caller falls back to the existing path).
    """
    if not document_pmh:
        return None
    for pattern, cc in _TX_NAIVE_CC_RULES:
        if re.search(pattern, document_pmh, re.IGNORECASE):
            return cc
    return None


_GU_ORGAN_WORD = {
    "renal": "renal mass", "bladder": "bladder tumor",
    "upper_tract": "upper-tract urothelial tumor", "testicular": "testicular mass",
    "penile": "penile lesion", "adrenal": "adrenal mass",
}


_INJECTION_CC_RE = re.compile(
    r"^\s*(?:eligard|lupron|leuprolide|zoladex|goserelin|degarelix|firmagon|"
    r"trelstar|triptorelin|orgovyx|relugolix)\b[^,.\n]*\binjection\b", re.IGNORECASE)
_PHASE_WORD = {
    "METASTATIC_CASTRATION_RESISTANT": "metastatic castration-resistant ",
    "METASTATIC_HORMONE_SENSITIVE": "metastatic hormone-sensitive ",
    "BIOCHEMICAL_RECURRENCE": "biochemically recurrent ",
}


def _reframe_injection_cc(cc: str, current_phase: Optional[str]) -> str:
    """A bare depot-injection CC ('Eligard injection for prostate cancer') is
    technically the visit reason but clinically thin. Reframe it to name the
    disease state + therapy, keeping the scheduled injection."""
    if not cc:
        return cc
    m = _INJECTION_CC_RE.search(cc)
    if not m:
        return cc
    drug = m.group(0).split()[0]
    drug = drug[0].upper() + drug[1:].lower()
    phase_word = _PHASE_WORD.get(current_phase or "", "")
    return (f"Follow-up of {phase_word}prostate cancer on androgen deprivation "
            f"therapy for scheduled {drug} injection")


def _cc_from_gu_diagnoses(diags: Optional[List]) -> str:
    """Build a CC anchored on non-prostate GU diagnoses (renal / bladder / ...).

    Returns "" when there is no actionable non-prostate diagnosis (so the
    existing prostate-oriented CC logic runs unchanged). A confirmed cancer is
    named by its diagnosis; an indeterminate mass is framed as 'of uncertain
    significance' (never 'benign'); a resolved benign finding is not the CC.
    """
    if not diags:
        return ""
    parts: List[str] = []
    for d in diags:
        cat = getattr(d, "category", "")
        if cat == "benign":
            continue  # a resolved benign finding is not the visit's primary CC
        if cat == "cancer":
            phrase = getattr(d, "name", "") or _GU_ORGAN_WORD.get(getattr(d, "organ", ""), "")
        else:  # indeterminate
            organ = getattr(d, "organ", "")
            phrase = f"{_GU_ORGAN_WORD.get(organ, organ)} of uncertain significance"
        status = getattr(d, "status", "")
        if status:
            phrase += f" ({status})"
        if phrase:
            parts.append(phrase)
    if not parts:
        return ""
    return "Follow-up of " + " and ".join(parts)


def synthesize_cc(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    document_pmh: Optional[str] = None,
    document_pathology: Optional[str] = None,
    document_psa: Optional[str] = None,
    document_psh: Optional[str] = None,
    clinical_document: Optional[str] = None,
    current_phase: Optional[str] = None,
    current_active_treatments: Optional[List[str]] = None,
    clinical_timeline: Optional[List] = None,
    other_gu_diagnoses: Optional[List] = None,
    patient_sex: Optional[str] = None,
    prostate_cancer_status: Optional[str] = None,
) -> str:
    """Synthesize a urology Chief Complaint.

    The CC must always be urologic and must reflect the patient's
    *current* clinical state. Process:
      1. Collect candidate CCs from GU notes (non-GU notes are excluded
         per project policy — those CCs are about non-urologic issues).
      2. Filter to CCs that contain at least one urologic keyword.
      3. If 1 candidate survives, return it (with terminology cleanup).
      4. If multiple survive, LLM-synthesize a single urologic CC.
      5. If zero survive, derive a CC from the patient's PMH /
         pathology / PSA data so the rendered note still has a sensible
         urologic CC instead of an empty / "Unknown" placeholder.
      6. POST-TREATMENT REFRAME (always last): if the resulting CC
         contains stale framing like "persistent prostate cancer",
         "rising PSA", or "elevated PSA" BUT the document shows that
         definitive treatment was completed AND the PSA trend confirms
         biochemical response, replace the CC with a clinically
         accurate post-treatment CC. This prevents an outdated CC
         carried forward from a pre-treatment visit ("persistent
         prostate cancer") from contradicting the rest of the chart
         (PSA 15.59 → 0.38 over 22 months post-XRT, for instance).

    Args:
        gu_notes: List of GU note dicts.
        non_gu_notes: Unused — kept for API compatibility.
        document_pmh: Past medical history text (document-level extract).
        document_pathology: Pathology results text (document-level).
        document_psa: PSA values block (document-level).
        document_psh: Past surgical history (used to detect completed
            radiation / prostatectomy / brachytherapy).
        clinical_document: Full raw document, scanned for treatment-
            completion phrases that aren't captured in PSH.

    Returns:
        Non-empty urologic CC string. Never "" — falls back to
        "Urology follow-up" as the final safety net.
    """
    # 0-pre. Non-prostate GU primary anchor (runs BEFORE the prostate anchor).
    # Renal masses and bladder tumors are frequently the PRIMARY reason for the
    # visit; without a structured signal the CC defaults to a prostate/PSA or
    # PMH-derived complaint (e.g. "erectile dysfunction" for a bladder-tumor
    # patient, or a prostate narrative for a female renal-mass patient).
    gu_cc = _cc_from_gu_diagnoses(other_gu_diagnoses)
    if gu_cc:
        # Dual-primary patients (prostate cancer + renal/bladder) should read
        # both problems; append a concise prostate clause when applicable.
        # A female patient can never have prostate cancer — no prostate clause.
        if ((patient_sex or "").lower() != "female"
                and (prostate_cancer_status or "").upper() in ("PRESENT", "TREATED")):
            gu_cc += "; prostate cancer follow-up"
        return _apply_terminology(gu_cc)

    # 0. Primary-cancer anchor (runs FIRST — outranks phase classifier).
    # When source unambiguously shows a urologic cancer AND >=1 of the
    # patient's own GU note CCs explicitly names that cancer, that CC
    # is authoritative regardless of what the phase classifier or
    # PMH-derive heuristics say. This catches the Woods failure mode:
    # phase classifier mislabeled an 11-year s/p-IMRT patient as
    # TREATMENT_NAIVE, which routed CC selection through a PMH-derive
    # path that picked "Follow-up for hematuria" from a 2012
    # microhematuria PMH entry — even though the patient's actual
    # recent CC is "Follow-up for prostate cancer, nephrolithiasis,
    # and LUTS." The anchor here would have prevented that.
    anchored_cc = _primary_cancer_anchored_cc(
        gu_notes, document_pmh, document_pathology, document_psh,
        clinical_document,
    )
    if anchored_cc:
        return _apply_terminology(_reframe_injection_cc(anchored_cc, current_phase))

    # Phase-driven CC short-circuit. When the deterministic phase
    # classifier has a high-confidence verdict (mCRPC, mHSPC, salvage,
    # biochemical recurrence, on-initial-treatment, progression), the CC
    # is computed directly from the phase + active treatments. This
    # bypasses the LLM-combine path that was producing stale CCs like
    # "Follow-up for prostate cancer on ADT with rising PSA" for a
    # patient now on mCRPC combination therapy whose PSA is actually
    # responding. The post-treatment-surveillance / treatment-naive /
    # uncertain phases fall through to the existing logic which handles
    # them well.
    phase_cc = _phase_driven_cc(current_phase, current_active_treatments)
    if phase_cc:
        # For POST_TREATMENT_SURVEILLANCE, prefer to name the specific
        # modality (radiation / prostatectomy / focal / brachytherapy)
        # when the timeline lets us identify the most recent COMPLETED
        # treatment. The phase CC alone says "after prior treatment";
        # naming the modality makes the CC clinically informative.
        if current_phase == "POST_TREATMENT_SURVEILLANCE" and clinical_timeline:
            mod = _most_recent_completed_modality(clinical_timeline)
            if mod:
                phase_cc = f"Follow-up for prostate cancer surveillance after {mod}"
        return _apply_terminology(phase_cc)

    # TREATMENT_NAIVE: derive the CC from the primary urologic concern
    # in PMH. This bypasses the LLM-combine path for the common cases
    # (BPH, elevated PSA workup, nephrolithiasis, ED, hematuria) where
    # the source notes' prior CCs frequently drift toward stale or
    # unrelated complaints. When PMH does not contain a recognizable
    # urologic concern, fall through to the existing logic.
    if current_phase == "TREATMENT_NAIVE":
        naive_cc = _treatment_naive_cc_from_pmh(document_pmh or "")
        if naive_cc:
            return _apply_terminology(naive_cc)

    # Pre-compute treatment + PSA signals once; the reframe step uses
    # both regardless of which extraction path produced the CC.
    treatment = _detect_treatment_history(document_psh, clinical_document)
    psa_state = _assess_psa_trend(document_psa)

    # 1. Collect CC candidates from GU notes only.
    # Recency filter: when a urologic CC from the last 18 months exists,
    # drop CCs from older notes. Otherwise an ancient consult ("Left
    # testicular pain" from a 2020 UROLOGY CONSULT) competes with the
    # most-recent annual followup CC and the LLM-combine step merges
    # the stale complaint into today's CC.
    from datetime import datetime, timedelta
    _now = datetime.now()
    _recent_cutoff = _now - timedelta(days=548)
    def _note_dt(n):
        d = (n.get("_source_date") or "").strip()
        if not d:
            return None
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(d, fmt)
            except (ValueError, TypeError):
                continue
        return None
    _recent_notes_with_cc = [
        n for n in gu_notes
        if n.get("CC") and _note_dt(n) and _note_dt(n) >= _recent_cutoff
    ]
    if _recent_notes_with_cc:
        all_ccs = [n["CC"] for n in _recent_notes_with_cc]
    else:
        all_ccs = [note["CC"] for note in gu_notes if note.get("CC")]

    # 2. Filter to urologic-containing CCs. Drop empties / pure
    # non-urologic complaints ("annual physical", "back pain").
    urologic_ccs = [cc for cc in all_ccs if _is_urologic_text(cc)]

    # (Cancer-anchor preference handled at function entry; if it fired,
    # we returned early. The shortcut + LLM-combine paths below run only
    # when no anchored CC matched.)

    cc: str
    # Shortcut: if all urologic candidates are identical (case-insensitive,
    # whitespace-normalized), skip the LLM call and return that CC. This
    # prevents the LLM-combine path from drifting to a generic "Urology
    # follow-up" when 2-3 prior notes all carry the same CC ("Adrenal
    # myelolipoma" → "Urology follow-up" was the failure mode).
    _normalized_ccs = {re.sub(r'\s+', ' ', cc.strip().lower()) for cc in urologic_ccs}
    if len(urologic_ccs) >= 1 and len(_normalized_ccs) == 1:
        cc = _apply_terminology(urologic_ccs[0])
    elif len(urologic_ccs) == 1:
        # 3. Single urologic CC: clean.
        cc = _apply_terminology(urologic_ccs[0])
    elif len(urologic_ccs) > 1:
        # 4. Multiple urologic CCs: LLM-combine.
        instructions = """
Focus on urologically relevant complaints only. Include:
- Genitourinary symptoms (erectile dysfunction, BPH, urinary symptoms, etc.)
- Prostate issues (elevated PSA, prostate cancer, etc.)
- Kidney/bladder issues
- Sexual health concerns
- Male fertility concerns

EXCLUDE non-urologic complaints (shoulder pain, general wellness visits, etc.) unless they have urologic implications.
Keep the final CC concise (1-2 lines).

IMPORTANT TERMINOLOGY:
- Replace "Consult for" with "Follow-up for" (this is a followup visit, not a new consult)
- Replace "consult" with "follow-up" in all contexts

CRITICAL: Provide ONLY the concise chief complaint. NO meta-commentary, NO explanations, NO preamble like "Here is" or "Based on". Just the chief complaint itself.
"""
        synthesized = combine_sections_with_llm(
            section_name="Chief Complaint",
            section_instances=urologic_ccs,
            instructions=instructions,
        )
        cleaned = _apply_terminology(clean_llm_commentary(synthesized))
        # Reject LLM CCs that are meta-commentary, refusal messages, or
        # generic non-CCs that should never appear as a chief complaint.
        nonsense_ccs = (
            re.compile(r'no\s+urolog', re.IGNORECASE),
            re.compile(r'no\s+(?:specific|relevant)\s+', re.IGNORECASE),
            re.compile(r'^there\s+(?:is|are)\s+', re.IGNORECASE),
            re.compile(r'\bnot\s+(?:provided|specified|documented|available)\b',
                       re.IGNORECASE),
            re.compile(r'^based\s+on\b', re.IGNORECASE),
            re.compile(r'^the\s+patient\s+(?:does\s+not|has\s+no)\b',
                       re.IGNORECASE),
            re.compile(r'^I\s+(?:will|cannot|can\'t|am\s+unable)\b',
                       re.IGNORECASE),
        )
        is_nonsense = any(p.search(cleaned) for p in nonsense_ccs) if cleaned else True
        if cleaned and _is_urologic_text(cleaned) and not is_nonsense:
            cc = cleaned
        else:
            # LLM output drifted off-topic or was a refusal — derive from
            # context (PMH / pathology / PSA). If context-derive also
            # returns the generic "Urology follow-up" sentinel, prefer
            # the first urologic CC we collected (it's better than
            # nothing).
            derived = _derive_cc_from_context(
                document_pmh, document_pathology, document_psa,
            )
            if derived == "Urology follow-up" and urologic_ccs:
                cc = _apply_terminology(urologic_ccs[0])
            else:
                cc = derived
    else:
        # 5. Zero urologic CCs — derive from context.
        cc = _derive_cc_from_context(
            document_pmh, document_pathology, document_psa,
        )

    # Bare depot-injection CCs get named-disease framing before the
    # post-treatment reframe.
    cc = _reframe_injection_cc(cc, current_phase)

    # 6. Post-treatment reframe. No-op when treatment isn't completed,
    # the CC has no stale markers, or PSA data is insufficient. When
    # all three conditions are met (stale CC + completed treatment +
    # decisive PSA state), rewrites to "Follow-up after <treatment>
    # for prostate cancer" or "Follow-up for biochemical recurrence
    # after <treatment>..." as appropriate.
    return _reframe_post_treatment_cc(cc, treatment, psa_state)
