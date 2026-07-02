"""
HPI (History of Present Illness) Agent

Combines HPIs from all notes with Assessments and Plans, focusing on current urologic HPI.

Includes HALLUCINATION DETECTION via deterministic fact verification.
All synthesized HPI is checked against ground truth extracted from source.
"""

from typing import List, Dict, Optional, Tuple, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..patient_status_facts import PatientStatusFacts
from ..llm_helper import combine_sections_with_llm, synthesize_with_llm
from .history_cleaners import clean_llm_commentary
from ..extractors.hpi_fact_verifier import (
    HPIFactVerifier,
    HPIVerificationResult,
    verify_hpi_against_source
)
import re
import logging

logger = logging.getLogger(__name__)


def _build_treatment_status_block(
    psh: Optional[str],
    clinical_document: Optional[str],
    psa_data: Optional[str],
) -> str:
    """Deterministic "TREATMENT STATUS" block for the HPI prompt.

    The LLM repeatedly truncates the HPI before reaching treatment-
    completion events when the source contains BOTH older "pending
    treatment" notes AND newer "completed treatment" notes — it anchors
    on the older framing. This block restates the patient's current
    treatment posture in unambiguous text so the prompt cannot miss it.

    Detects:
      - Definitive prostate-cancer treatment that has been COMPLETED
        (XRT / prostatectomy / brachytherapy / focal therapy), via the
        same regexes the CC agent uses (kept in sync via import).
      - Whether ADT is part of the regimen (lupron / leuprolide /
        degarelix / bicalutamide phrases — detected separately because
        many patients get XRT without ADT, as in this case).
      - Whether PSA shows biochemical response post-treatment.

    Returns "" when no treatment-completion signal is found in PSH or
    the raw document, so non-treated patients aren't given a spurious
    "post-treatment" framing.
    """
    if not (psh or clinical_document):
        return ""

    # Import lazily to avoid a circular import at module load.
    from .cc_agent import (
        _detect_treatment_history, _assess_psa_trend,
        _is_biochemically_responding, _TREATMENT_LABEL,
    )

    treatment = _detect_treatment_history(psh or '', clinical_document or '')
    if not treatment:
        return ""

    t_type = treatment.get('type', '')
    label = _TREATMENT_LABEL.get(t_type, t_type or 'treatment')

    lines = [
        "TREATMENT STATUS (deterministic — use these statements as ground "
        "truth, they override any contradictory claim in the prior-visit "
        "HPI snapshots):",
        f"- Patient has COMPLETED definitive {label} for prostate cancer.",
    ]

    # ADT detection. Look for current-tense ADT markers in source. If
    # neither current ADT nor a clear "no ADT" signal is present, skip
    # the statement — better silent than wrong.
    src_blob = '\n'.join(s for s in (psh, clinical_document) if s)
    adt_active = re.search(
        r'\b(?:currently\s+on|on\s+)\s*(?:ADT|androgen\s+deprivation|'
        r'leuprolide|lupron|degarelix|eligard|firmagon|bicalutamide)\b',
        src_blob, re.IGNORECASE,
    )
    adt_completed = re.search(
        r'\b(?:completed|finished|stopped|discontinued)\s+'
        r'(?:ADT|androgen\s+deprivation|leuprolide|lupron|degarelix)\b',
        src_blob, re.IGNORECASE,
    )
    adt_explicitly_no = re.search(
        r'\b(?:without\s+ADT|no\s+ADT|did\s+not\s+receive\s+ADT|'
        r'XRT\s+without\s+(?:concurrent\s+)?ADT|radiation\s+without\s+ADT)\b',
        src_blob, re.IGNORECASE,
    )
    if adt_active:
        lines.append("- Patient is currently on androgen-deprivation therapy.")
    elif adt_completed:
        lines.append("- Patient previously received ADT (now completed).")
    elif adt_explicitly_no:
        lines.append("- Patient did NOT receive ADT.")

    # PSA biochemical response.
    psa_state = _assess_psa_trend(psa_data)
    responding = _is_biochemically_responding(t_type, psa_state)
    if responding is True:
        cur = psa_state.get('current')
        peak = psa_state.get('max')
        if cur is not None and peak is not None:
            lines.append(
                f"- PSA shows biochemical response post-treatment "
                f"(current {cur} ng/mL vs peak {peak} ng/mL)."
            )
        else:
            lines.append("- PSA shows biochemical response post-treatment.")
    elif responding is False:
        lines.append(
            "- PSA pattern is concerning for biochemical recurrence "
            "(per Phoenix criteria — current value is > nadir + 2 ng/mL "
            "for radiation, or > 0.2 ng/mL after prostatectomy)."
        )

    lines.append(
        "- The HPI MUST narrate the completed treatment and its outcome. "
        "It MUST NOT describe the patient as awaiting treatment, "
        "pending treatment, or still considering treatment options, "
        "because the source documents treatment as already finished."
    )
    return '\n'.join(lines)


_NONUROLOGIC_MED_TERMS = {
    # Cardiovascular / antihypertensive / antilipid / antiplatelet /
    # anticoagulant agents — never urologic.
    "amlodipine", "lisinopril", "metoprolol", "atenolol", "carvedilol",
    "losartan", "valsartan", "olmesartan", "hydrochlorothiazide", "hctz",
    "chlorthalidone", "furosemide", "spironolactone", "diltiazem",
    "verapamil", "warfarin", "apixaban", "rivaroxaban", "dabigatran",
    "clopidogrel", "aspirin", "atorvastatin", "rosuvastatin", "simvastatin",
    "pravastatin", "ezetimibe", "fenofibrate", "gemfibrozil",
    # Allergy / respiratory / ENT
    "cetirizine", "loratadine", "fexofenadine", "diphenhydramine",
    "fluticasone", "mometasone", "budesonide", "albuterol", "montelukast",
    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "ranitidine", "famotidine",
    "polyethylene glycol", "miralax", "docusate", "senna",
    # Psych / neuro
    "sertraline", "fluoxetine", "paroxetine", "citalopram", "escitalopram",
    "bupropion", "venlafaxine", "duloxetine", "trazodone", "mirtazapine",
    "gabapentin", "pregabalin", "lamotrigine", "levetiracetam",
    "glatiramer", "interferon",
    # Diabetes / endocrine non-androgen
    "metformin", "glipizide", "insulin", "levothyroxine",
    # Misc
    "naloxone", "lactobacillus",
}

_NONUROLOGIC_LAB_TERMS = {
    "glucose", "bun", "sodium", "potassium", "chloride", "co2",
    "anion gap", "specific gravity", "egfr", "hgb a1c",
    "hemoglobin a1c", "ldl", "hdl", "triglyceride", "cholesterol",
    "tsh", "vitamin d", "vitamin b12", "ferritin", "alkaline phosphatase",
    "ast", "alt",
}

# Non-urologic anatomy / findings — if a sentence mentions these AND has
# no urologic anchor, the sentence is irrelevant to the urology HPI and
# gets stripped. Catches cases where the LLM lifted text from prior CT
# or ED-discharge narrative ("interval increased extent of dilated small
# bowel loops...", "mildly dilated bile ducts and soft tissue attenuation
# filling defects in the common bile duct", "gallbladder pathology").
_NONUROLOGIC_FINDING_TERMS = {
    "small bowel", "bowel obstruction", "bowel ischemia",
    "bile duct", "biliary", "gallbladder", "cholelith",
    "hepatic", "hepatomeg", "liver lesion",
    "pancreas", "pancreatitis",
    "splenomeg",
    "pulmonary embolism", "pleural effusion", "atelectasis",
    "abdominal aortic aneurysm",
    "myocardial infarction", "coronary artery",
    "stroke", "cerebrovascular",
    "nasopharyngeal", "oropharyngeal", "parotid",
    "lymphadenopathy of neck",
    "diabetic retinopathy", "macular",
    "thyroid nodule",
}

# Urologic anchors — if a sentence contains one of these tokens, the
# stripper keeps it even if it also names a non-urologic med/lab
# (because the urologic relevance is established).
_UROLOGIC_ANCHORS = {
    "psa", "prostate", "prostatic", "urolog", "urinary", "urine",
    "urination", "lut", "bph", "ipss", "void", "voiding", "stream",
    "frequency", "nocturia", "hesitancy", "hematuria", "dysuria",
    "incontinence", "retention",
    "kidney", "renal", "nephro", "stone", "calculus",
    "bladder", "ureter", "urethra", "scrotum", "scrotal",
    "testis", "testicle", "testicular", "epididym", "spermato",
    "varicocele", "hydrocele",
    "erectile", "ed", "libido", "sexual dysfunction", "pde5", "sildenafil",
    "tadalafil", "vardenafil",
    "tamsulosin", "alfuzosin", "silodosin", "doxazosin", "terazosin",
    "finasteride", "dutasteride",
    "oxybutynin", "solifenacin", "mirabegron", "vibegron", "tolterodine",
    "leuprolide", "goserelin", "degarelix", "relugolix",
    "bicalutamide", "enzalutamide", "apalutamide", "darolutamide",
    "abiraterone", "lupron", "eligard",
    "creatinine",  # creatinine IS urologically relevant (renal function)
}


def _strip_nonurologic_sentences(hpi: str) -> str:
    """Drop HPI sentences that name only non-urologic meds / labs.

    The HPI prompt forbids enumerating non-urologic medications and
    non-urologic labs, but the LLM still emits sentences like:
      "He also takes Cetirizine for allergies and Fluticasone Prop
       for nasal allergies."
      "Recent laboratory results include a specific gravity of 1.011,
       an EGFR CKD EPI of 82, a glucose level of 102 mg/dL, and a
       creatinine level of 1.0 mg/dL."
    These rot the signal-to-noise of the HPI. Drop them deterministically.

    A sentence is dropped iff it names ≥1 non-urologic term AND contains
    NO urologic anchor. Sentences that mention a non-urologic agent in a
    urologic context (e.g., "held apixaban for cystoscopy") are kept.
    """
    if not hpi or not hpi.strip():
        return hpi

    # Sentence split that survives "ng/mL", "Mr.", etc. — same heuristic
    # as the dedupe helper.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', hpi.strip())

    kept = []
    for s in sentences:
        s_low = s.lower()
        # Med-list-dump detector: any sentence that names ≥2 distinct
        # medication agents is a list dump and belongs in the
        # MEDICATIONS section, not the HPI prose — even when one of the
        # meds happens to be urologic (e.g., "His meds include
        # amlodipine, lisinopril, sildenafil, rosuvastatin"). The HPI
        # should mention a urologic med in clinical context (e.g.,
        # "started tamsulosin for LUTS"), not as an enumeration.
        non_uro_hits = sum(1 for term in _NONUROLOGIC_MED_TERMS if term in s_low)
        uro_med_terms = (
            "tamsulosin", "alfuzosin", "silodosin", "doxazosin",
            "terazosin", "finasteride", "dutasteride",
            "oxybutynin", "solifenacin", "mirabegron", "vibegron",
            "tolterodine", "leuprolide", "goserelin", "degarelix",
            "relugolix", "bicalutamide", "enzalutamide", "apalutamide",
            "darolutamide", "abiraterone", "lupron", "eligard",
            "sildenafil", "tadalafil", "vardenafil", "avanafil",
            "trimix", "alprostadil",
        )
        uro_med_hits = sum(1 for term in uro_med_terms if term in s_low)
        total_med_hits = non_uro_hits + uro_med_hits
        if total_med_hits >= 2:
            # Med-list dump — drop entire sentence.
            continue

        has_non_uro = (non_uro_hits > 0) or any(
            term in s_low for term in _NONUROLOGIC_LAB_TERMS
        ) or any(term in s_low for term in _NONUROLOGIC_FINDING_TERMS)
        if not has_non_uro:
            kept.append(s)
            continue
        # Word-boundary match for urologic anchors. Substring match was
        # producing false positives — e.g., "ed" matched inside
        # "showed"/"obtained"/"examined", causing every CT-finding
        # sentence to be falsely flagged as urologic and kept.
        has_uro = any(
            re.search(rf"\b{re.escape(anchor)}\b", s_low)
            for anchor in _UROLOGIC_ANCHORS
        )
        if has_uro:
            kept.append(s)
            continue
        # Sentence names non-urologic content with no urologic anchor —
        # drop it.

    result = ' '.join(kept).strip()
    return result if result else hpi


def reflow_hpi(hpi: str) -> str:
    """Collapse a choppy one-sentence-per-line HPI into flowing prose.

    Pure whitespace / line-break normalization — NO content is added, removed,
    or reworded, so accuracy is untouched; only readability improves. The LLM
    sometimes renders each skeleton beat on its own line ("He was diagnosed...\\n
    He completed...\\n..."); this joins those into a connected paragraph and
    keeps the closing "Today's visit ..." sentence as its own short paragraph.
    """
    if not hpi or not hpi.strip():
        return hpi
    body = hpi.strip()
    label = ""
    m = re.match(r"^(HPI:\s*)", body, re.IGNORECASE)
    if m:
        label, body = m.group(1), body[m.end():]
    body = re.sub(r"\s*\n+\s*", " ", body)      # all internal breaks -> spaces
    body = re.sub(r"[ \t]{2,}", " ", body).strip()
    # 2-paragraph shape: put the closing visit-reason sentence on its own line.
    body = re.sub(r"\s+(Today'?s visit\b)", r"\n\n\1", body, count=1)
    return label + body


def _dedupe_hpi_sentences(hpi: str) -> str:
    """Remove sentence-level redundancy that survives the LLM prompt.

    Removes any subsequent sentence that:
      (a) is a near-duplicate of an earlier sentence (high token
          overlap), OR
      (b) consists primarily of facts already stated earlier (a PSA
          value, lab phrase, or treatment phrase that appears verbatim
          earlier and the sentence carries no new clinical content).

    The deletion is conservative: it never removes the first mention
    of a fact and never collapses two sentences whose word sets
    differ by more than 40% (i.e. genuinely different sentences
    survive).

    Operates on the final LLM output, AFTER fact verification, AFTER
    clean_llm_commentary. Idempotent.
    """
    if not hpi or not hpi.strip():
        return hpi

    # Split into sentences while preserving paragraph breaks. The
    # period-after-letter rule handles abbreviated phrases like
    # "5 mg." poorly, so we split on ". " followed by capital letter.
    paragraphs = re.split(r'\n\s*\n', hpi)
    out_paragraphs: List[str] = []
    seen_signatures: List[set] = []

    # A "token signature" is the set of clinically-loaded tokens in a
    # sentence: numbers, PSA / Gleason / GG / treatment / mg / ng-mL
    # mentions, drug names, organ names. We use that to detect when
    # two sentences are about the same thing. Stopwords / generic
    # filler words are stripped so "He returns for followup" and "The
    # patient returns for followup" don't both match each other.
    STOPWORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'has', 'have',
        'had', 'he', 'she', 'his', 'her', 'patient', 'this', 'that',
        'with', 'and', 'or', 'but', 'for', 'on', 'in', 'at', 'to',
        'of', 'currently', 'now', 'previously', 'noted', 'recently',
        'mr', 'mrs', 'ms', 'dr',
    }

    def _signature(sentence: str) -> set:
        # Lowercase, strip punctuation, drop stopwords.
        tokens = re.findall(r"[A-Za-z0-9.+/-]+", sentence.lower())
        return {t for t in tokens if t not in STOPWORDS and len(t) > 1}

    # LLM "summary restatement" lead phrases. These ALWAYS restate
    # facts already narrated earlier — the HPI is a narrative, the
    # narrative IS the summary, so a sentence beginning with one of
    # these is virtually always redundant filler. Drop every such
    # sentence (even the first); if the sentence carries unique new
    # facts, the LLM should phrase it in the running narrative, not
    # as a summary aside.
    SUMMARY_LEADS = re.compile(
        r'^\s*(?:'
        r"The patient is currently"
        r"|The patient's current"
        r"|His current (?:PSA|status|chief complaint|treatment)"
        r"|Her current (?:PSA|status|chief complaint|treatment)"
        r"|Currently, the patient"
        r"|At present, (?:the patient|he|she)"
        r"|To summarize"
        r"|In summary"
        r"|Overall, the patient"
        r')',
        re.IGNORECASE,
    )

    for para in paragraphs:
        # Split on sentence terminators followed by whitespace + capital.
        # Keep separators by using look-behind / look-ahead.
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', para.strip())
        kept_sentences: List[str] = []
        for sent in sentences:
            sent_stripped = sent.strip()
            if not sent_stripped:
                continue
            # Summary-restatement leads — drop unconditionally.
            if SUMMARY_LEADS.match(sent_stripped):
                logger.debug(
                    "HPI dedupe: dropped summary-restatement sentence: %r",
                    sent_stripped[:120],
                )
                continue
            sig = _signature(sent_stripped)
            if not sig:
                # Sentence is mostly stopwords (e.g. "He is doing well.")
                # — keep it; not redundancy material.
                kept_sentences.append(sent_stripped)
                seen_signatures.append(sig)
                continue
            # Compare against every earlier signature in this HPI.
            is_redundant = False
            for prev_sig in seen_signatures:
                if not prev_sig:
                    continue
                overlap = len(sig & prev_sig)
                # Two thresholds:
                #   1. ≥80% of the new sentence's tokens already
                #      appeared earlier → near-duplicate sentence.
                #   2. ≥60% overlap AND new sentence has no token
                #      with a digit (no fresh value introduced) → a
                #      "summary" sentence that just restates earlier
                #      content.
                ratio_self = overlap / max(1, len(sig))
                has_new_value = any(re.search(r'\d', t) for t in (sig - prev_sig))
                if ratio_self >= 0.8 and not has_new_value:
                    is_redundant = True
                    break
                if ratio_self >= 0.6 and not has_new_value and len(sig) >= 4:
                    is_redundant = True
                    break
            if is_redundant:
                logger.debug(
                    "HPI dedupe: dropped redundant sentence "
                    "(no new tokens, overlap=%.0f%%): %r",
                    ratio_self * 100, sent_stripped[:120],
                )
                continue
            kept_sentences.append(sent_stripped)
            seen_signatures.append(sig)
        if kept_sentences:
            out_paragraphs.append(' '.join(kept_sentences))

    return '\n\n'.join(out_paragraphs).strip()


_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%b %d %Y",
)


def _parse_any_date(s: str):
    """Best-effort parse for the date formats this codebase emits."""
    from datetime import datetime
    if not s:
        return None
    s = s.strip().rstrip(",")
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _months_ago(dt) -> Optional[int]:
    from datetime import datetime
    if dt is None:
        return None
    now = datetime.now()
    return (now.year - dt.year) * 12 + (now.month - dt.month)


def _recency_label(dt) -> str:
    """Classify an event date as CURRENT (≤6 mo), RECENT (6-12 mo),
    or HISTORICAL (>12 mo). Used to tag imaging / labs / visits in the
    HPI prompt so the LLM cannot call a 3-year-old MRI "recent"."""
    m = _months_ago(dt)
    if m is None:
        return "[UNDATED]"
    if m <= 6:
        return f"[CURRENT — {m} mo ago]"
    if m <= 12:
        return f"[RECENT — {m} mo ago]"
    years = m / 12
    if years < 2:
        return f"[HISTORICAL — {m} mo ago]"
    return f"[HISTORICAL — ~{years:.1f} yr ago]"


def _relabel_imaging_for_recency(imaging_data: Optional[str]) -> str:
    """Re-emit the imaging block with explicit recency tags per study,
    sorted newest-first. The LLM otherwise anchors on whichever study
    appears first in source order — frequently a 3-year-old MRI from a
    resolved hospitalization — and writes "recent imaging shows...".

    Parses each study by its leading "(MM/DD/YYYY)" tag (the format
    the imaging extractor emits). Studies without a parseable date are
    placed last and tagged [UNDATED]."""
    if not imaging_data or not imaging_data.strip():
        return imaging_data or ""
    # Split on blank lines so each study (header + body) stays together.
    chunks = [c.strip() for c in re.split(r'\n\s*\n', imaging_data) if c.strip()]
    entries = []
    date_re = re.compile(r'\((\d{1,2})/(\d{1,2})/(\d{4})\)')
    from datetime import datetime
    for c in chunks:
        m = date_re.search(c)
        if m:
            try:
                dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            except ValueError:
                dt = None
        else:
            dt = None
        entries.append((dt, c))
    # Sort: dated first by descending date, undated last.
    entries.sort(key=lambda e: (e[0] is None, -(e[0].toordinal() if e[0] else 0)))
    lines = []
    for dt, chunk in entries:
        tag = _recency_label(dt)
        lines.append(f"{tag} {chunk}")
    return "\n\n".join(lines)


def _build_temporal_anchor_block(
    psa_data: Optional[str],
    imaging_data: Optional[str],
    gu_notes: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Deterministic 'when is now' block. Lists today's date, the 6-month
    cutoff, and the most-recent dated event per modality so the LLM has
    no excuse to call an old event 'recent'.

    Without this the LLM applies 'recent' / 'recently' / 'persistent' to
    multi-year-old findings (2023 MRI for resolved pyelonephritis becomes
    'recent imaging shows persistent UTI/cystitis' in a 2026 note)."""
    from datetime import datetime, timedelta
    today = datetime.now()
    cutoff_6mo = today - timedelta(days=183)
    cutoff_12mo = today - timedelta(days=365)

    lines = [
        "TEMPORAL ANCHOR (READ FIRST — non-negotiable):",
        f"- TODAY = {today.strftime('%Y-%m-%d')} "
        f"({today.strftime('%B %d, %Y')}).",
        f"- The word 'recent' / 'recently' / 'lately' applies ONLY to "
        f"events on or after {cutoff_6mo.strftime('%Y-%m-%d')} "
        f"(within the last 6 months).",
        f"- For any event older than that, USE THE EXPLICIT DATE "
        f"(e.g., 'CT in March 2025', 'MRI in July 2023'). Never call "
        f"it 'recent'.",
    ]

    # Most-recent PSA date
    if psa_data:
        psa_date_re = re.compile(
            r'(?:\[[a-z]+\]\s+)?'
            r'([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})'
        )
        psa_dates = []
        for line in psa_data.split('\n'):
            m = psa_date_re.search(line.strip())
            if m:
                dt = _parse_any_date(m.group(1))
                if dt:
                    psa_dates.append(dt)
        if psa_dates:
            most_recent = max(psa_dates)
            lines.append(
                f"- Most-recent PSA date: "
                f"{most_recent.strftime('%Y-%m-%d')} "
                f"{_recency_label(most_recent)}"
            )

    # Most-recent imaging date (uses imaging-block "(MM/DD/YYYY)" tags)
    if imaging_data:
        date_re = re.compile(r'\((\d{1,2})/(\d{1,2})/(\d{4})\)')
        img_dates = []
        for m in date_re.finditer(imaging_data):
            try:
                img_dates.append(datetime(int(m.group(3)),
                                          int(m.group(1)),
                                          int(m.group(2))))
            except ValueError:
                continue
        if img_dates:
            most_recent = max(img_dates)
            lines.append(
                f"- Most-recent imaging date: "
                f"{most_recent.strftime('%Y-%m-%d')} "
                f"{_recency_label(most_recent)}"
            )
            stale_imgs = [d for d in img_dates if d < cutoff_12mo]
            if stale_imgs:
                stale_years = sorted({d.year for d in stale_imgs})
                year_str = ", ".join(str(y) for y in stale_years)
                lines.append(
                    f"- Imaging from {year_str} is HISTORICAL. If those "
                    f"findings have been re-evaluated by newer studies, "
                    f"describe the historical findings with their year "
                    f"AND the current status (e.g., 'July 2023 MRI "
                    f"showed X during the pyelonephritis episode; "
                    f"follow-up CT in March 2025 demonstrated "
                    f"resolution')."
                )

    # Most-recent GU-visit date (helps LLM frame as 'since last visit on
    # <date>' rather than fabricating a today-symptom complaint)
    if gu_notes:
        visit_dates = []
        for n in gu_notes:
            d = _parse_any_date(n.get("_source_date", "") or n.get("date", ""))
            if d:
                visit_dates.append(d)
        if visit_dates:
            most_recent = max(visit_dates)
            lines.append(
                f"- Most-recent urology visit: "
                f"{most_recent.strftime('%Y-%m-%d')} "
                f"{_recency_label(most_recent)}. The patient has NOT "
                f"been interviewed since that date — do not fabricate "
                f"new same-day subjective complaints."
            )

    return "\n".join(lines)


def _strip_stale_recent_qualifier(hpi: str) -> str:
    """Strip / rewrite 'recent' qualifiers that point at >6-month-old
    events. Catches the common LLM failure where it writes 'recent
    imaging studies have shown X' about an MRI from 3 years ago.

    Conservative — only rewrites when (a) the same sentence contains a
    year that is >1 calendar year before TODAY, OR (b) the sentence
    references 'imaging' / 'MRI' / 'CT' but no date at all (in which
    case 'recent' is ambiguous and is dropped). Otherwise pass through."""
    if not hpi or not hpi.strip():
        return hpi
    from datetime import datetime
    this_year = datetime.now().year
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', hpi.strip())
    out = []
    year_re = re.compile(r'\b(20\d{2})\b')
    qualifier_re = re.compile(
        r'\b(recent(?:ly)?|lately|just)\b',
        re.IGNORECASE,
    )
    # Pattern that flags an "undated recent imaging" claim — almost
    # always stale (the LLM is paraphrasing a 2023 study as 'recent'
    # because no temporal anchor told it not to).
    undated_recent_img_re = re.compile(
        r'\brecent(?:ly)?\s+(?:imaging|MRI|CT|ultrasound|study|studies)\b',
        re.IGNORECASE,
    )
    month_re = re.compile(
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        r'(?:[a-z]+)?\s+\d{1,2},?\s+\d{4}\b'
        r'|\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        re.IGNORECASE,
    )
    for s in sentences:
        years = [int(y) for y in year_re.findall(s)]
        has_date = bool(month_re.search(s))
        # Case A: explicit old year + recent qualifier in same sentence.
        old_year_present = any(y <= this_year - 2 for y in years)
        if old_year_present and qualifier_re.search(s):
            s = qualifier_re.sub("", s)
            s = re.sub(r'\s{2,}', ' ', s).strip()
            s = re.sub(r'^(imaging|MRI|CT|ultrasound|study)', r'The \1', s)
            out.append(s)
            continue
        # Case B: "recent imaging/MRI/CT/study" with NO date in the
        # sentence — drop entirely. The TEMPORAL ANCHOR block has
        # provided authoritative dates for the truly recent studies;
        # any free-floating "recent imaging" sentence without a date
        # is the LLM paraphrasing a stale finding. The truly-recent
        # study will be cited explicitly in another sentence.
        if undated_recent_img_re.search(s) and not has_date:
            continue
        out.append(s)
    return " ".join(out).strip()


def _reconcile_psa_direction(hpi: str, psa_data: Optional[str]) -> str:
    """When the deterministic PSA direction is 'decreased' but the HPI
    still says 'rising' / 'elevated PSA levels' framing, rewrite the
    framing. Catches the Chavez-style self-contradiction
    ('rising PSA levels, which have decreased from 1.84 to 0.79')."""
    if not hpi or not psa_data:
        return hpi
    # Reuse the delta block's parsing.
    values = []
    for raw_line in psa_data.split('\n'):
        line = raw_line.strip()
        nums = re.findall(r'\d+\.\d+', line)
        if nums:
            try:
                values.append(float(nums[-1]))
            except ValueError:
                pass
    if len(values) < 2:
        return hpi
    cur, prev = values[0], values[1]
    if cur >= prev - 0.05:
        return hpi  # not clearly decreasing → don't touch

    # Rewrite "rising PSA" / "rising PSA levels" / "elevated PSA levels"
    # framings to "previously elevated PSA, now declining" when applied
    # to the current trajectory. Don't touch historical-tense uses
    # ("PSA rose to 4.28 in 2023" is a valid statement of past history).
    patterns = [
        (re.compile(r'\brising\s+PSA(?:\s+levels)?\b', re.IGNORECASE),
         "previously elevated PSA, now declining"),
        (re.compile(r'\belevated\s+PSA(?:\s+levels)?\b(?!\s+in\s+\d{4})',
                    re.IGNORECASE),
         "previously elevated PSA, now declining"),
        (re.compile(r'\bcurrently\s+undergoing\s+evaluation\s+for\s+new\s+disease\b',
                    re.IGNORECASE),
         "now on PSA surveillance following normalization"),
    ]
    out = hpi
    for pat, repl in patterns:
        out = pat.sub(repl, out)
    return out


def _scrub_unsupported_biopsy_claims(
    hpi: str,
    pathology_data: Optional[str],
    psh_data: Optional[str],
) -> str:
    """Drop HPI sentences that claim a prostate biopsy was performed when
    PATHOLOGY RESULTS shows no biopsy and PSH lists none.

    Root cause this fixes: the LLM completes the narrative "PSA spike →
    biopsy" pattern even when no biopsy is in the source. It also
    inverts "No prostate pathology on file" → "(pathology on file)" by
    dropping the negation. Both produce a fabricated biopsy claim in
    an otherwise factual HPI.

    Detection: any sentence containing "underwent a prostate biopsy",
    "biopsy revealed/showed/demonstrated", "prostate biopsy (pathology
    on file)", or similar — AND the rendered PATHOLOGY data is empty
    / "None documented" / contains no prostate-biopsy entry — AND PSH
    contains no prostate biopsy entry.

    Action: strip the offending CLAUSE within the sentence (preferred)
    or the whole sentence if the claim is sentence-spanning. Surgical
    precision avoids wiping out the legitimate facts in the same
    sentence (e.g., the real PSA spike + UTI context).
    """
    if not hpi:
        return hpi

    pathology_blob = (pathology_data or "").lower()
    psh_blob = (psh_data or "").lower()

    # Does the rendered pathology / PSH have a real prostate-biopsy entry?
    has_real_prostate_biopsy = bool(
        re.search(r"prostate\s+biops|prostatic\s+biops|trus\s*[/-]?\s*bx|"
                  r"transrectal\s+(?:ultrasound[\s\-]?)?biops|"
                  r"prostate\s+cores|gleason\s+(?:score|grade)",
                  pathology_blob + "\n" + psh_blob)
    )
    if has_real_prostate_biopsy:
        return hpi  # Real biopsy exists — claim is legitimate

    # Pattern that matches the hallucinated biopsy claim and the
    # parenthetical "(pathology on file)" tail. The clause-strip
    # captures the verb + biopsy noun + optional parenthetical.
    biopsy_claim_re = re.compile(
        r"(?:\s+and\s+|\s*;\s*|\s*,\s*|\s+)?"
        r"(?:has\s+(?:had|undergone)|"
        r"(?:he|she|the\s+patient)\s+(?:has\s+)?(?:had|undergone)|"
        r"underwent|completed|received|"
        r"is\s+s/?p|status\s+post|s/?p)\s+"
        r"(?:a\s+|an\s+|the\s+)?"
        r"(?:prior\s+|previous\s+|recent\s+)?"
        r"(?:transrectal\s+|TRUS\s*[/\-]?\s*)?"
        r"prostate\s+biops(?:y|ies)"
        r"(?:\s*\((?:pathology\s+on\s+file|results?\s+(?:pending|on\s+file)|"
        r"see\s+pathology|cores\s+sampled)[^)]*\))?",
        re.IGNORECASE,
    )

    # Also catch "biopsy revealed/showed/demonstrated/confirmed X" when X
    # references prostate pathology (Gleason, adenocarcinoma, etc.) — these
    # claims similarly imply a biopsy occurred.
    biopsy_finding_claim_re = re.compile(
        r"(?:prostate\s+|TRUS\s+|transrectal\s+)biops(?:y|ies)\s+"
        r"(?:revealed|showed|demonstrated|confirmed|noted|found)\s+"
        r"[^.]*?(?:gleason|adenocarcinoma|grade\s+group|GG\s*\d|"
        r"cores?\s+positive|benign|negative\s+for\s+malignancy)[^.]*?\.",
        re.IGNORECASE,
    )

    # "pathology on file" parenthetical alone (when the LLM dropped the
    # "no" negation from "No prostate pathology on file"). This is rare
    # but extremely high-confidence as a hallucination.
    pathology_on_file_re = re.compile(
        r"\(\s*(?:prostate\s+)?pathology\s+on\s+file\s*\)",
        re.IGNORECASE,
    )

    out = hpi

    # Drop full biopsy-finding sentences (rare, but cleanest when caught)
    out = biopsy_finding_claim_re.sub("", out)

    # Strip the biopsy-claim clause WITHIN sentences. This preserves the
    # surrounding facts (PSA values, UTI context, dates) that are real.
    out = biopsy_claim_re.sub("", out)

    # Strip orphan "(pathology on file)" parenthetical
    out = pathology_on_file_re.sub("", out)

    # Cleanup: normalize whitespace, drop orphan connectives left after
    # clause removal, collapse double-punctuation.
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    # "he and experienced" / "the patient and reports" → "he experienced"
    # — the conjunction is left dangling because the first conjunct was
    # the biopsy clause we just removed.
    out = re.sub(
        r"\b(he|she|the\s+patient|patient)\s+and\s+(?=[a-z])",
        r"\1 ",
        out, flags=re.IGNORECASE,
    )
    # "; and experienced" / ", and experienced" with nothing between
    # the punctuation and "and" — drop the leading "and".
    out = re.sub(r"([.;,])\s*and\s+(?=[a-z])", r"\1 ", out)
    out = re.sub(r"\.\s*\.", ".", out)
    out = re.sub(r",\s*\.", ".", out)
    out = re.sub(r";\s*\.", ".", out)
    # Tidy any stray ";  " or ",  " from removed clauses
    out = re.sub(r"\s{2,}", " ", out)
    # Strip leading punctuation/whitespace left by a sentence-initial
    # biopsy clause being stripped.
    out = re.sub(r"^\s*[.,;:]+\s*", "", out)
    return out.strip()


def _scrub_psa_hallucinations(hpi: str, psa_data: Optional[str]) -> str:
    """Replace fabricated PSA values in the HPI with the true current value.

    The LLM occasionally substitutes a PSA-context number with a non-PSA
    numeric that appears nearby in the source — most commonly a value
    from a TUMOR SCREENS reference-range row that shares the same table
    as the PSA column ("Ref range high  4  ...  34  38.6" → "PSA ...
    risen to 38.6 ng/mL"). The existing HPIFactVerifier only matches
    "PSA <number>" but the LLM phrases it as "PSA has risen to ... ng/mL"
    with prose between PSA and the number, so the verifier misses it.

    This scrubber:
      1. Parses the deterministic PSA list from psa_data (truth set).
      2. Finds every "<value> ng/mL" mention in the HPI.
      3. For mentions that sit within ~150 chars of a "PSA" / "PSA-
         value" token AND whose value is NOT a known PSA value (±0.05),
         rewrites that value to the most-recent true PSA, with date.

    Conservative — only rewrites when (a) PSA context is established
    in the same vicinity, AND (b) the cited value is not within 0.05
    ng/mL of ANY known PSA value. ng/mL values for other analytes
    (testosterone, vitamin D, etc.) are not affected because they are
    rarely PSA-adjacent in the prose.
    """
    if not hpi or not psa_data:
        return hpi
    # Parse known PSA values + the current (most-recent) one with date.
    psa_entries = []  # list of (value_float, date_str)
    for raw_line in psa_data.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        date_match = re.match(
            r'(?:\[[a-z]+\]\s+)?'
            r'([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
            line,
        )
        nums = re.findall(r'\d+\.\d+', line)
        if not nums:
            continue
        try:
            val = float(nums[-1])
        except ValueError:
            continue
        date_str = date_match.group(1) if date_match else ""
        psa_entries.append((val, date_str))
    if not psa_entries:
        return hpi
    known_values = {round(v, 2) for v, _ in psa_entries}
    cur_val, cur_date = psa_entries[0]  # reverse-chronological → most-recent first

    def _is_known(v: float) -> bool:
        return any(abs(v - k) < 0.05 for k in known_values)

    # Scan every "<value> ng/mL" mention. For each, look 200 chars
    # BEFORE for the nearest analyte name (PSA / testosterone / etc.).
    # If the nearest analyte is PSA — AND the value isn't a known PSA
    # value — it's a hallucination. Non-greedy regex advancing past
    # the first PSA-ng/mL pair was missing the second ng/mL in
    # sentences like "PSA was 4.47 ng/mL ... risen to 38.6 ng/mL".
    ngml_re = re.compile(r'(\d+\.?\d*)\s*ng/mL', re.IGNORECASE)
    # Other analyte tokens whose presence between PSA and the value
    # means the value belongs to the OTHER analyte, not PSA. Keep this
    # list small and high-precision.
    other_analyte_re = re.compile(
        r'\b(?:testosterone|testos|free\s+T|estradiol|estrogens?|'
        r'vitamin\s+[A-Z]|B12|cobalamin|prolactin|cortisol|TSH|'
        r'T4|T3|LH|FSH|HCG|AFP|LDH|alkaline|hemoglobin|HgB|'
        r'creatinine|BUN|glucose|A1C|calcium|albumin|protein|'
        r'CEA|CA[\-\s]?(?:125|15[\-\s]?3|19[\-\s]?9|27[\-\s]?29)|'
        r'PSA[\-\s]?F|free\s+PSA|%\s*free\s+PSA)\b',
        re.IGNORECASE,
    )
    psa_token_re = re.compile(r'(?<![A-Za-z\-])PSA(?!\s*[-/])\b', re.IGNORECASE)

    out_parts = []
    pos = 0
    for m in ngml_re.finditer(hpi):
        cited_str = m.group(1)
        try:
            cited = float(cited_str)
        except ValueError:
            continue
        # Look 200 chars BEFORE the value for the nearest analyte token.
        lookback_start = max(0, m.start() - 200)
        before = hpi[lookback_start:m.start()]
        # Find last PSA position
        last_psa = None
        for pm in psa_token_re.finditer(before):
            last_psa = pm.end()
        if last_psa is None:
            continue
        # Find last OTHER analyte position
        last_other = None
        for om in other_analyte_re.finditer(before):
            last_other = om.end()
        # If a non-PSA analyte sits AT or AFTER the PSA mention (closer
        # to the value), the value belongs to that analyte — leave
        # alone. Use >= so "Free PSA" (which contains the PSA token but
        # is also a distinct analyte) wins on tie.
        if last_other is not None and last_other >= last_psa:
            continue
        if _is_known(cited):
            continue
        # Hallucinated. Replace just this ng/mL value with the current PSA + date.
        out_parts.append(hpi[pos:m.start()])
        date_suffix = f" on {cur_date}" if cur_date else ""
        out_parts.append(f"{cur_val} ng/mL{date_suffix}")
        pos = m.end()
    out_parts.append(hpi[pos:])
    return ''.join(out_parts)


def _build_psa_delta_block(psa_data: Optional[str]) -> str:
    """Build a deterministic "PSA since prior visit" summary.

    The LLM frequently overlooks the most recent vs prior delta when
    given a long PSA curve — it instead anchors on whichever older
    value was emphasized in a stale HPI snapshot. This function pre-
    computes the current PSA, the prior PSA, the peak PSA, and the
    direction of change as plain text that the prompt can quote
    verbatim. Returns "" if fewer than 2 values are parseable.
    """
    if not psa_data:
        return ""
    # Re-use the same parsing logic as cc_agent so behaviour is shared.
    # Locally inlined to avoid a circular import.
    values: List[Tuple[str, float]] = []
    for raw_line in psa_data.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        # Capture optional leading date+time so we can label values.
        date_match = re.match(
            r'(?:\[[a-z]+\]\s+)?'
            r'([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
            line,
        )
        date_label = date_match.group(1) if date_match else ''
        # Take the last decimal number on the line as the PSA value.
        nums = re.findall(r'\d+\.\d+', line)
        if nums:
            try:
                values.append((date_label, float(nums[-1])))
            except ValueError:
                pass
    if len(values) < 2:
        return ""
    # PSA curve is reverse-chronological → first value is most recent.
    cur_date, cur_v = values[0]
    prev_date, prev_v = values[1]
    peak_v = max(v for _, v in values)
    if cur_v < prev_v - 0.05:
        direction = 'decreased'
    elif cur_v > prev_v + 0.05:
        direction = 'increased'
    else:
        direction = 'unchanged'
    cur_label = f" on {cur_date}" if cur_date else ""
    prev_label = f" on {prev_date}" if prev_date else ""
    return (
        "PSA SINCE PRIOR VISIT (use these exact values in the HPI):\n"
        f"- Current PSA: {cur_v} ng/mL{cur_label}\n"
        f"- Prior PSA:   {prev_v} ng/mL{prev_label}\n"
        f"- Direction:   {direction}\n"
        f"- Peak PSA observed in this series: {peak_v} ng/mL\n"
        "When the HPI references PSA, it MUST cite the current value above."
    )


def synthesize_hpi(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    imaging_data: Optional[str] = None,
    cross_specialty_context: Optional[str] = None,
    visit_progression: Optional[str] = None,
    prior_ap_context: Optional[str] = None,
    psh_data: Optional[str] = None,
    clinical_document: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    authoritative_facts: Optional[str] = None,
    patient_facts: Optional["PatientStatusFacts"] = None,
    hpi_skeleton: Optional[str] = None,
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize HPI from GU notes with clinical context.

    Note: Stage 1 only includes HPIs from previous notes. Assessment and Plan
    are NOT available as they are Stage 2 (completed after patient visit).

    Focus on creating a current UROLOGY HPI from available GU notes,
    enriched with recent lab results, pathology, and imaging findings
    so the HPI reflects the patient's current clinical status.

    INCLUDES HALLUCINATION DETECTION:
    - Extracts ground truth PSA values, lab results, and findings from source BEFORE synthesis
    - Verifies all claims in LLM output against ground truth
    - Flags or corrects any hallucinated content (e.g., fabricated PSA values)

    PRIOR A&P CONTEXT INTEGRATION:
    - Uses prior Assessment and Plan context to inform HPI narrative
    - Provides awareness of what was previously diagnosed and planned
    - Enables temporal continuity in follow-up visit HPIs

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries (NOT USED - kept for API compatibility)
        psa_data: Raw PSA values extracted from document (optional)
        pathology_data: Raw pathology results extracted from document (optional)
        labs_data: Raw lab results extracted from document (optional)
        imaging_data: Raw imaging results extracted from document (optional)
        cross_specialty_context: Urologic content from non-GU specialty notes (optional)
        visit_progression: Narrative of what changed since last visit (optional)
        prior_ap_context: Formatted prior Assessment & Plan context (optional)
        verify_facts: If True (default), verify synthesis against source facts
        return_verification: If True, return (text, HPIVerificationResult) tuple

    Returns:
        Synthesized HPI text focused on current urologic status.
        If return_verification=True, returns (text, HPIVerificationResult) tuple.
    """
    # Collect HPIs from GU notes ONLY
    # Non-GU HPIs are excluded to prevent contamination with irrelevant content
    # (headaches, dizziness, ankle pain, etc. should not appear in urology HPI)
    #
    # Each HPI is a SNAPSHOT from a prior visit, not a description of
    # today's encounter. Prefix each one with the source visit date so
    # the synthesis LLM sees a temporal ordering instead of treating
    # all HPIs as concurrent inputs. Without this label the LLM
    # routinely merges multi-year histories as if they all happened at
    # the same encounter (e.g. saying "patient on active surveillance"
    # for a patient who completed XRT 18 months ago — because an old
    # surveillance-era HPI is presented at the same level as the most
    # recent one).
    # If we received ground-truth patient_facts, import the sanitizer lazily
    # so we can pre-scrub each prior HPI before it reaches the LLM. Prior
    # HPIs are themselves LLM-generated by previous (possibly buggy) runs;
    # treating their text as inviolate just propagates last run's
    # confabulated focal-therapy / Phoenix sentences forward.
    _sanitize_prior_hpi = None
    if patient_facts is not None:
        from ..patient_status_facts import sanitize_context_against_facts as _scaf

        def _sanitize_prior_hpi(text: str) -> str:
            cleaned, _ = _scaf(text, patient_facts)
            return cleaned

    # Recency filter for prior HPIs: when a recent urology note exists,
    # drop HPIs from notes older than 18 months. Otherwise an ancient
    # consult's ER narrative ("received morphine with pain relief,
    # discharged with urology consult") is presented to the LLM as a
    # peer of recent visits and gets woven into today's HPI.
    from datetime import datetime as _dt, timedelta as _td
    _now = _dt.now()
    _recent_cutoff = _now - _td(days=548)
    def _note_dt2(n):
        d = (n.get("_source_date") or "").strip()
        if not d:
            return None
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return _dt.strptime(d, fmt)
            except (ValueError, TypeError):
                continue
        return None
    _gu_notes_for_hpi = gu_notes
    if any(_note_dt2(n) and _note_dt2(n) >= _recent_cutoff and n.get("HPI")
           for n in gu_notes):
        _gu_notes_for_hpi = [
            n for n in gu_notes
            if (_note_dt2(n) is None) or (_note_dt2(n) >= _recent_cutoff)
        ]

    hpi_instances = []
    for note in _gu_notes_for_hpi:
        hpi_text = note.get("HPI")
        if not hpi_text:
            continue
        if _sanitize_prior_hpi is not None:
            hpi_text = _sanitize_prior_hpi(hpi_text)
            # If the sanitizer stripped everything substantive, skip this
            # prior HPI rather than feeding the LLM an empty entry.
            if not hpi_text.strip():
                continue
        src_date = (note.get("_source_date") or "").strip()
        src_title = (note.get("_source_title") or "").strip()
        if src_date and src_title:
            header = f"[Prior visit dated {src_date} — {src_title}]"
        elif src_date:
            header = f"[Prior visit dated {src_date}]"
        elif src_title:
            header = f"[Prior visit ({src_title})]"
        else:
            header = "[Prior visit, undated]"
        hpi_instances.append(f"{header}\n{hpi_text}")

    # Non-GU notes: EXCLUDED from HPI synthesis
    # Reason: Non-GU HPIs contain non-urological content that confuses the LLM
    # and results in HPI discussing headaches, mental health, orthopedic issues, etc.
    # for note in non_gu_notes:
    #     if note.get("HPI"):
    #         hpi_instances.append(f"Non-GU HPI: {note['HPI']}")

    # If no GU-note HPIs exist but we have clinical context (PSA,
    # pathology, imaging, prior A&P) — write a UROLOGIC HPI from the
    # context alone rather than returning empty. The renderer used to
    # display "HPI: Unknown" in this case; that's never acceptable for
    # a urology note. Falling through to the LLM-synthesis path below
    # with no hpi_instances list lets the prompt generate a narrative
    # purely from the clinical-data context section. We require at
    # least one piece of urologic context (PSA / pathology / imaging /
    # cross-specialty / visit-progression / prior-AP) before doing this
    # — otherwise there's truly nothing to write about.
    has_clinical_context = any(
        (s or '').strip()
        for s in (psa_data, pathology_data, imaging_data,
                  cross_specialty_context, visit_progression, prior_ap_context)
    )
    if not hpi_instances and not has_clinical_context:
        return ""
    if not hpi_instances:
        # Sentinel placeholder so combine_sections_with_llm has something
        # to operate on; the prompt instructions and CLINICAL DATA
        # CONTEXT below tell the LLM to derive the HPI from context.
        hpi_instances = [
            "[NO PRIOR UROLOGY NOTE AVAILABLE — synthesize HPI from the "
            "CLINICAL DATA CONTEXT below, focusing strictly on urologic "
            "issues.]"
        ]

    # If only one instance AND no ground-truth enforcement is required,
    # short-circuit and pass the prior HPI through with light text cleanup.
    # When authoritative_facts IS provided we deliberately fall through to
    # LLM synthesis: prior HPIs are LLM-generated by previous (possibly
    # buggy) runs and may contain confabulated treatments / Phoenix-
    # criteria / biochemical-recurrence framing that violate the ground
    # truth. Forcing LLM synthesis with the authoritative facts block lets
    # the prompt rewrite the contaminated prior HPI using deterministic
    # source values. The cost is one extra LLM call per single-prior-visit
    # patient; the safety benefit (no carry-forward of last-run
    # hallucinations) is worth it.
    if len(hpi_instances) == 1 and not (authoritative_facts and authoritative_facts.strip()):
        # Remove our internal labels
        result = hpi_instances[0]
        # Strip our internal "[Prior visit dated ... — TITLE]" header
        # the snapshot loop prepended. Without this strip, the line
        # would render verbatim in the HPI section.
        result = re.sub(r'^\s*\[Prior\s+visit[^\]]*\]\s*\n+', '', result)
        result = result.replace("Non-GU HPI: ", "")
        # Replace "consult" with "followup" terminology
        result = re.sub(r'\burology\s+consult\b', 'urology followup', result, flags=re.IGNORECASE)
        result = re.sub(r'\bconsult\s+for\b', 'followup for', result, flags=re.IGNORECASE)
        result = re.sub(r'\bfor\s+a\s+urology\s+consult\b', 'for a urology followup', result, flags=re.IGNORECASE)
        # Run the LLM-commentary cleaner — prior HPIs are themselves
        # LLM-generated by prior runs and frequently carry
        # "Mr., a 65-year-old", "Patient Name:", "Based on the provided
        # data..." scaffolding that bypassed the cleaner because this
        # short-circuit path didn't call it.
        result = clean_llm_commentary(result)
        return result

    # Build clinical context section from available data.
    # Patient demographics first — the LLM tends to either invent an
    # age (often "72-year-old male" by default) or carry one over
    # stale from prior notes if we don't anchor it. Putting age and
    # sex up front prevents that.
    clinical_context = ""
    context_parts = []

    # AUTHORITATIVE GROUND TRUTH must appear FIRST so the LLM treats every
    # subsequent context block (including prior-visit HPI snapshots) as
    # subordinate to it. Built deterministically from PMH + PSH +
    # pathology by patient_status_facts; lists cancer_status,
    # treatment_naive, phoenix_applicable and the ABSOLUTE RULES the LLM
    # must follow. Without this the HPI agent has been observed to write
    # "completed definitive focal therapy for prostate cancer" / "Phoenix
    # biochemical-recurrence" for treatment-naive patients by pattern-
    # matching against rising-PSA templates.
    if authoritative_facts and authoritative_facts.strip():
        context_parts.append(authoritative_facts)

    # TEMPORAL ANCHOR — answers "when is now?" deterministically so the
    # LLM cannot call a 3-year-old MRI "recent". Placed near the top so
    # every downstream context block (PSA list, imaging list, prior-
    # visit HPIs) is read through the recency rules. Uses today's date,
    # most-recent PSA date, most-recent imaging date, and most-recent
    # urology-visit date.
    temporal_anchor = _build_temporal_anchor_block(
        psa_data=psa_data,
        imaging_data=imaging_data,
        gu_notes=_gu_notes_for_hpi,
    )
    if temporal_anchor:
        context_parts.append(temporal_anchor)

    # PHASE 2: deterministic HPI story skeleton — placed AFTER the ground-
    # truth block so the LLM sees both. The skeleton is the structured
    # story (intro / diagnosis / treatment timeline / PSA trajectory /
    # procedure findings / current regimen / today symptoms) the LLM is
    # required to render. It collapses the "synthesize from prior HPIs"
    # failure mode where ADT-restart events were lost because the source
    # prose came from prior visits written before the restart.
    if hpi_skeleton and hpi_skeleton.strip():
        context_parts.append(hpi_skeleton)

    demo_lines = []
    if patient_name:
        demo_lines.append(f"Name: {patient_name}")
    if patient_age:
        demo_lines.append(f"Age at this visit: {patient_age} years")
    if patient_sex:
        demo_lines.append(f"Sex: {patient_sex}")
    if demo_lines:
        context_parts.append(
            "PATIENT DEMOGRAPHICS (use ONLY these values for age/sex in the HPI; "
            "do NOT use any age you may see referenced elsewhere in the source notes — "
            "those reflect the patient's age at the time of an old note, not now):\n"
            + "\n".join(demo_lines)
        )
    if psa_data and psa_data.strip():
        context_parts.append(f"RECENT PSA VALUES:\n{psa_data}")
        # Always emit a deterministic "since prior visit" PSA summary so
        # the LLM cannot miss the current-vs-prior delta. _build_psa_delta
        # returns "" if it can't parse two values (in which case the
        # plain RECENT PSA VALUES block above is what the LLM gets).
        psa_delta_block = _build_psa_delta_block(psa_data)
        if psa_delta_block:
            context_parts.append(psa_delta_block)
    # Deterministic TREATMENT STATUS block — always added when the
    # document shows completed definitive prostate-cancer therapy.
    # Prevents the LLM from anchoring on older "pending treatment"
    # snapshots and writing an HPI that says the patient is still
    # awaiting therapy when treatment has actually been completed.
    treatment_status_block = _build_treatment_status_block(
        psh_data, clinical_document, psa_data,
    )
    if treatment_status_block:
        context_parts.append(treatment_status_block)
    if pathology_data and pathology_data.strip():
        context_parts.append(f"PATHOLOGY RESULTS:\n{pathology_data}")
    if labs_data and labs_data.strip():
        # Limit labs to reasonable length for HPI context
        labs_summary = labs_data[:1500] if len(labs_data) > 1500 else labs_data
        context_parts.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")
    if imaging_data and imaging_data.strip():
        # Re-label imaging block with recency tags ([CURRENT 0-6 mo],
        # [RECENT 6-12 mo], [HISTORICAL >12 mo]) and sort newest first.
        # Otherwise the LLM picks whichever study appears first in the
        # source and calls it "recent" — frequently a 3-year-old MRI
        # from a resolved hospitalization.
        relabeled = _relabel_imaging_for_recency(imaging_data)
        imaging_summary = relabeled[:2000] if len(relabeled) > 2000 else relabeled
        context_parts.append(
            "IMAGING FINDINGS (each study is tagged with its recency — "
            "use only [CURRENT] studies as 'recent'; cite [HISTORICAL] "
            "studies by their explicit date and frame as historical):\n"
            f"{imaging_summary}"
        )

    # Add cross-specialty urologic context (from non-GU notes)
    if cross_specialty_context and cross_specialty_context.strip():
        context_parts.append(f"CROSS-SPECIALTY UROLOGIC FINDINGS:\n{cross_specialty_context}")

    # Add visit progression analysis (what changed since last visit)
    if visit_progression and visit_progression.strip():
        context_parts.append(f"VISIT PROGRESSION (since last urology visit):\n{visit_progression}")

    # Add prior Assessment & Plan context (for temporal continuity in follow-up visits)
    if prior_ap_context and prior_ap_context.strip():
        context_parts.append(f"PRIOR ASSESSMENT & PLAN CONTEXT:\n{prior_ap_context}")

    if context_parts:
        clinical_context = "\n\n=== CLINICAL DATA CONTEXT (reference these findings in the HPI where relevant) ===\n" + "\n\n".join(context_parts) + "\n=== END CLINICAL DATA CONTEXT ===\n"

    authoritative_directive = ""
    if authoritative_facts:
        authoritative_directive = (
            "\n=== AUTHORITATIVE GROUND TRUTH ENFORCEMENT (READ THIS FIRST) ===\n"
            "The first block inside CLINICAL DATA CONTEXT above (titled\n"
            "'PATIENT GROUND TRUTH') was derived deterministically from the\n"
            "source documents. It is the single source of truth for this\n"
            "patient's cancer status, treatment history, and Phoenix-criteria\n"
            "applicability. The ABSOLUTE RULES at the end of that block are\n"
            "non-negotiable.\n"
            "\n"
            "If TREATMENT_NAIVE is True, the patient has NEVER received any\n"
            "prostate-cancer treatment. Do NOT write 'completed focal therapy',\n"
            "'s/p prostatectomy', 'after radiation', 'underwent ADT', or any\n"
            "synonym. A prior-visit HPI snapshot that says such a thing is\n"
            "WRONG (last LLM-run hallucination) and must NOT be carried\n"
            "forward.\n"
            "\n"
            "If PROSTATE_CANCER_STATUS is ABSENT, do NOT diagnose prostate\n"
            "cancer in the HPI. Do NOT invoke 'biochemical recurrence',\n"
            "'Phoenix criteria', 'nadir+2', 'salvage', or 'post-treatment'.\n"
            "Rising PSA in such a patient is a workup question for new\n"
            "disease, not recurrence of treated disease.\n"
            "\n"
            "MULTI-CANCER: PROSTATE_CANCER_STATUS is organ-specific — ABSENT\n"
            "does NOT mean the patient is cancer-free. If an\n"
            "OTHER_UROLOGIC_DIAGNOSES block is present, those renal / bladder /\n"
            "other non-prostate diagnoses are frequently the PRIMARY reason for\n"
            "the visit: CENTER the HPI on them (the mass/tumor, its size and\n"
            "trajectory, imaging, biopsy/pathology status, and management) and\n"
            "do NOT default to a prostate/PSA narrative. An 'indeterminate'\n"
            "mass is NEITHER cancer NOR benign — call it a mass/lesion of\n"
            "uncertain significance; NEVER call an unbiopsied mass 'benign'.\n"
            "If PATIENT_SEX is female, prostate cancer, PSA screening,\n"
            "prostatectomy and ADT are anatomically IMPOSSIBLE — never write\n"
            "any prostate-cancer narrative for her.\n"
        )

    # PHASE 2 directive: when a deterministic skeleton was provided, the
    # LLM's job is to RENDER it, not to synthesize from scratch. Strong
    # framing on this dramatically reduces drift compared to free-form
    # synthesis from prior-visit prose.
    skeleton_directive = ""
    if hpi_skeleton and hpi_skeleton.strip():
        skeleton_directive = (
            "\n=== HPI RENDERING MODE (READ BEFORE WRITING) ===\n"
            "A deterministic HPI STORY SKELETON appears inside CLINICAL DATA\n"
            "CONTEXT above (look for '=== HPI STORY SKELETON ==='). That\n"
            "skeleton is the authoritative structure of TODAY's HPI. Your\n"
            "task is to RENDER the skeleton into fluent clinical prose, not\n"
            "to invent additional structure or facts.\n"
            "\n"
            "Hard rules for skeleton rendering:\n"
            "  1. Walk skeleton sections 1-7 IN ORDER. Do not reorder them\n"
            "     and do not skip a section that has content.\n"
            "  2. Every TREATMENT HISTORY bullet must appear in the prose,\n"
            "     with its date and verb, but COMBINE the bullets into flowing\n"
            "     compound sentences (chain them with commas/semicolons in\n"
            "     chronological order) — do NOT write one short sentence per\n"
            "     bullet and do NOT start each with 'He'. A RESTARTED event\n"
            "     MUST be rendered as a restart — never as 'continued' or\n"
            "     'completed' or 'finished'. A DECLINED event MUST be\n"
            "     rendered as a decline — never as 'received'.\n"
            "  3. Every entry in CURRENT REGIMEN must be acknowledged in\n"
            "     the prose (the patient is taking those medications now —\n"
            "     downstream agents will drop them if you do not).\n"
            "  4. PROCEDURE FINDINGS (cystoscopy / urodynamics / biopsy /\n"
            "     DEXA / TURBT / cystolitholapaxy / etc.) must be cited by\n"
            "     date and finding when present in the skeleton.\n"
            "  5. PSA TRAJECTORY in the skeleton is the only allowed PSA\n"
            "     narrative. Do not introduce different PSA values.\n"
            "  6. Do NOT invent dates, treatments, biopsies, imaging\n"
            "     findings, or clinical decisions that are not in the\n"
            "     skeleton. If you would otherwise need to do so, omit\n"
            "     the claim.\n"
            "  7. Output 1-2 paragraphs of CONTINUOUS, connected narrative\n"
            "     prose (compound sentences that chain related events). Do\n"
            "     NOT place each fact on its own line, do NOT begin multiple\n"
            "     consecutive sentences with 'He', no bullets, no\n"
            "     meta-commentary. Start directly with the INTRO sentence.\n"
        )

    # Use LLM to synthesize comprehensive HPI
    instructions = f"""
Create a current, comprehensive UROLOGY HPI that synthesizes all available urologic information from the source notes into a cohesive narrative for TODAY'S visit.

HPI STRUCTURE & STYLE (write for a clinician to read quickly — non-negotiable):
- Write flowing, connected NARRATIVE PROSE — the SAME readable style as a good
  Assessment paragraph. Do NOT write a staccato list of short sentences that
  each begin with "He" ("He was diagnosed... He completed... He is
  currently..."), do NOT put each fact on its own line, and do NOT produce
  bullets or "X on DATE - X completed". State each fact exactly ONCE.
- CHAIN the diagnosis and treatment course into ONE OR TWO compound sentences
  using commas and semicolons, in CHRONOLOGICAL order. Example of the required
  style: "Mr. Foster is an 82-year-old man with prostate adenocarcinoma
  diagnosed in 2000 (Gleason 4+3, cT2N0M0/pT3aN0), treated with radical
  prostatectomy that year, with biochemical recurrence in 2021 managed by
  external-beam radiation completed in November 2021, and androgen-deprivation
  therapy plus a second radiation course initiated in July 2024 for metastatic
  disease." Combine treatments that share a date or episode into a single
  clause rather than a separate sentence each.
- OPEN with that diagnosis-and-stage sentence: the cancer, date of diagnosis,
  grade (Gleason/Grade Group for prostate, Fuhrman for renal, WHO grade for
  bladder), and BOTH clinical and pathologic stage when available. Do not bury
  the stage later.
- For a definitive treatment report its COMPLETION; do NOT also list a separate
  initiation date for that same course, and never state an initiation AFTER its
  completion.
- Then the PSA trajectory (lead with the current value), then today's visit
  reason and interval status — as continuous prose, not a list. Be concise and
  precise, with no repetition.

{clinical_context}
{authoritative_directive}
{skeleton_directive}

PRE-VISIT / CHART-PREP FRAMING (READ FIRST — non-negotiable):
- This HPI is generated from a chart extract assembled BEFORE the patient
  is seen today. The patient has NOT yet been interviewed. NO new symptom
  history, ROS positive, or "today the patient reports..." statement can
  be invented.
- "Today" in this HPI means: the reason listed on the visit roster
  (annual followup, PSA followup, ED followup, etc.) — NOT a fresh
  symptom complaint.
- All subjective symptom statements MUST be anchored to their source
  date. Correct: "At the last urology visit on 06/30/2025, he reported
  stable urinary function..." Incorrect: "He reports stable urinary
  function" (this implies a same-day interview that has not happened).
- If a prior visit documented a symptom, frame it as "as of the
  [DATE] visit" or "since the prior visit, no interval documentation
  of [symptom]". Do NOT lift the prior-visit subjective narrative and
  re-present it as today's complaint.
- The opening sentence pattern for a followup is:
  "<Name> is a <age>-year-old <sex> who returns for <visit-reason-from-
  source>." NOT "<Name> presents with [symptoms]" unless the source
  contains a same-day chief-complaint statement.
- A follow-up visit's job is to assess interval change and confirm the
  prior plan. Frame it that way. Do not turn it into a re-presentation
  of original disease.

CRITICAL TEMPORAL INVARIANTS (read before doing anything else):
- The HPI entries below are PRIOR-VISIT SNAPSHOTS, each labeled with
  "[Prior visit dated <DATE> — <NOTE TITLE>]". The newest snapshot is
  NOT today. Today's clinical reality may differ substantially —
  treatment may have been completed since, PSA may have changed,
  imaging may have been done. Treat each prior HPI as a record of how
  things stood on its specific date, and DO NOT carry forward any
  prior statement that the CLINICAL DATA CONTEXT contradicts.
- Whenever a value (PSA, Gleason, treatment status, etc.) appears in
  both a prior HPI and the CLINICAL DATA CONTEXT, the CLINICAL DATA
  CONTEXT wins. The HPI you write must use TODAY'S current PSA, not
  a stale one from a prior snapshot.
- If "PSA SINCE PRIOR VISIT" appears in the context above, you MUST
  quote the current PSA value in the HPI narrative. Do not invent a
  different value, do not omit it, do not use the prior value as
  "current".
- If a prior-visit HPI describes the patient as e.g. "on active
  surveillance with rising PSA" but the data context shows definitive
  treatment was completed and PSA is now responding, the HPI you
  write must reflect the POST-TREATMENT current state, not the stale
  surveillance era.
- Frame each historical fact with its date (e.g. "underwent radical
  prostatectomy in June 2024" not "underwent radical prostatectomy").
  This makes time elapsed explicit instead of letting the reader
  guess.

STRUCTURE:
0. TEMPORAL FRAMING (CRITICAL for followup visits):
   - If VISIT PROGRESSION data is provided, this is a FOLLOWUP visit
   - Start by referencing what was recommended at the last visit
   - Describe what has happened since (completed procedures, test results, ongoing treatments)
   - Then present the patient's current status and reason for today's visit
   - Example opening (generic structure ONLY — substitute the patient's actual diagnosis/procedure from the source notes; do NOT carry "prostate biopsy" or any specific clinical detail from this example into the output):
       "<Patient> returns for followup of <DIAGNOSIS-FROM-SOURCE>. At the last visit, <RECOMMENDATION-FROM-SOURCE>. Since then, <COMPLETED-EVENT-FROM-SOURCE>. Today, <REASON-FOR-VISIT-FROM-SOURCE>."
1. Start with the patient's current chief complaint and presenting urologic issue
2. Include relevant history from past visits in chronological flow
3. Document urologic symptoms, test results, and diagnoses that are mentioned
4. Write in narrative paragraph form (not bullet points)
5. The HPI is ONE INTEGRATED NARRATIVE. Use 1-2 paragraphs maximum.
   Do NOT produce three or four short paragraphs that each restate
   the same facts (PSA value, treatments, labs) — that pattern is
   the most common reason this HPI gets sent back for rewrite.

TEMPORAL ANCHORING (MANDATORY — every clinical event needs a date):
- Every PSA value, biopsy result, imaging study, and treatment event MUST
  carry an explicit date (month + year, or year if month is unknown).
  Bad: "subsequent MRI demonstrated...". Good: "MRI in April 2025
  demonstrated...". Bad: "recent biopsy showed Gleason 4+3". Good:
  "July 2023 biopsy showed Gleason 4+3".
- The words "recent", "recently", "lately", and "just" are FORBIDDEN as
  descriptors of any finding more than 6 months before today's visit.
  An MRI from 2023 is not "recent" in 2026. State the date instead.
- "Recent" is acceptable ONLY for events within the last ~3 months
  AND only when an explicit date follows or has just been stated.
- Use one consistent date format throughout the narrative (e.g. always
  "Sep 2023" or always "September 2023" — do not mix).
- Group findings by recency: TODAY's symptoms and current PSA → present
  tense; events from the past 3-6 months → past tense with date; older
  diagnostic / staging / treatment events → past tense with month-year.

CURRENT vs PRIOR TREATMENT (MANDATORY — read TREATMENT_ACTIVE_STATUS):
- If the GROUND TRUTH block lists a CURRENT_TREATMENT_STATUS section,
  every treatment claim you make MUST match its verdict.
- 'DISCONTINUED' for ADT/hormonal therapy means the patient is NOT
  currently receiving it. You MUST NOT write "remains on ADT",
  "continues on ADT", "continuous androgen deprivation therapy", or
  "currently on Eligard/Lupron/leuprolide" for such a patient. Correct
  framings: "previously received [N months/years] of ADT and elected
  against restart in favor of monitoring", "completed a course of ADT
  in [year]", "off ADT since [date]", "intermittent ADT, most recent
  injection [month year]".
- 'COMPLETED' for radiation / prostatectomy / focal therapy means the
  event is in the past — frame as "status post" or "completed in [year]".
  Do NOT write "is undergoing radiation" or "remains on focal therapy".
- 'ACTIVE' means treatment is currently being administered — confirm with
  the most recent dose/injection date in the source before asserting
  "continues on" / "remains on".

INTERNAL CONSISTENCY (MANDATORY — no self-contradiction):
- Read your draft and ensure no two sentences contradict each other.
  Do NOT say "on continuous ADT" in one sentence and "transitioned to
  intermittent" / "declined ADT restart" in another. Pick the framing
  supported by the most recent source statement and stick to it.
- Do NOT both apply Phoenix criteria and state the patient is on
  surveillance with no biochemical recurrence (the latter is consistent
  with Phoenix-not-met; the former implies recurrence). Pick one
  reading and present it cleanly.
- If a treatment is listed as DISCONTINUED above, your entire narrative
  must speak of it in the past tense. Do not slip "currently on" or
  "remains on" anywhere — including the final summary clause.

POST-TREATMENT NARRATIVE ARC (for TREATED patients only):
When the patient has CANCER_STATUS=TREATED, structure the HPI as:
  1. One opening sentence anchoring the diagnosis (year, Gleason/Grade
     Group, key tumor characteristics from source).
  2. Treatment history with dates: what was performed, when, and the
     current status (ACTIVE / DISCONTINUED / COMPLETED) of each.
  3. Post-treatment trajectory: PSA arc with dated values, surveillance
     imaging with dates, and the patient's documented preferences /
     decisions.
  4. Today's reason for visit and current symptom set.
- Each beat should flow into the next chronologically. No backward
  jumps that re-state earlier facts.

NON-REDUNDANCY (MANDATORY — output is rejected if violated):
- Each clinically distinct fact appears EXACTLY ONCE. If a PSA value
  (e.g. "0.22 ng/mL"), a treatment ("monthly Degarelix injections"),
  an imaging finding ("PSMA-avid osseous metastases"), or a lab
  abnormality ("anemia, leukopenia") is mentioned anywhere in the
  HPI, do NOT restate it in a later sentence or "summary" paragraph.
- Do NOT write a closing paragraph that re-summarizes what was just
  narrated. The narrative IS the summary.
- Do NOT use phrasings like "The patient's current chief complaint
  is..." after already covering the chief complaint at the top — the
  CC line above the HPI already states the chief complaint.
- Do NOT lead multiple sentences with "The patient is currently...",
  "The patient's current status is...", "His current PSA is...".
  Each of those leads is allowed AT MOST ONCE.
- If you must reference a fact a second time for context, use a back-
  reference ("the previously noted decline", "this elevation") rather
  than restating the value.

MEDICATION MENTIONS (MANDATORY — HPI is NOT the medication list):
- The MEDICATIONS section of the note enumerates the full active
  outpatient list. Do NOT duplicate it in the HPI prose.
- Only reference a medication in the HPI when it is UROLOGICALLY
  ACTIVE (currently being taken for a urologic reason) or directly
  relevant to a urologic decision being made today. Allowed urologic
  classes: alpha-blockers (tamsulosin, alfuzosin, silodosin,
  doxazosin, terazosin), 5-alpha-reductase inhibitors (finasteride,
  dutasteride), antimuscarinics / anticholinergics (oxybutynin,
  solifenacin, mirabegron, vibegron, tolterodine, trospium,
  fesoterodine, darifenacin), PDE5 inhibitors (sildenafil, tadalafil,
  vardenafil, avanafil), intracavernosal therapy (Trimix, alprostadil),
  GnRH analogues / antagonists (leuprolide, goserelin, degarelix,
  relugolix), anti-androgens (bicalutamide, enzalutamide, apalutamide,
  darolutamide, abiraterone), chemotherapy used for GU cancers
  (docetaxel, cabazitaxel, mitomycin C, BCG), urinary analgesics
  (phenazopyridine), urologic abx where infection is the urologic
  focus, testosterone replacement, and urologic supplements being
  managed by the clinic.
- All other medications (statins, antihypertensives, anticoagulants,
  reflux meds, antidepressants, neurology agents, allergy meds, etc.)
  belong in the MEDICATIONS section ONLY and must not be listed in
  the HPI prose. Mention them only when they directly bear on a
  urologic decision (e.g., apixaban relevant to peri-procedural
  hold).

ANTI-REDUNDANCY EXAMPLE — illustrative ONLY. The patient name, PSA
values, medication names, and findings below are PLACEHOLDERS. They are
NOT this patient's data. Do NOT copy them into your output:
   BAD: "His PSA rose to PLACEHOLDER_VALUE. He has PLACEHOLDER_FINDING
        and is on PLACEHOLDER_MED. Most recent PSA is PLACEHOLDER_VALUE.
        Patient is currently on PLACEHOLDER_MED injections.
        PLACEHOLDER_LABS noted. The patient's current chief complaint
        is PLACEHOLDER_CC, with a value of PLACEHOLDER_VALUE.
        PLACEHOLDER_LABS noted."
   GOOD: "His PSA has risen from PLACEHOLDER_VALUE_A (Sep 2025) to
        PLACEHOLDER_VALUE_B (Jun 2026) despite ongoing PLACEHOLDER_MED,
        with accompanying PLACEHOLDER_LABS on recent labs."

CRITICAL: every patient-specific value (PSA numbers, dates, medication
names, treatment events, lab findings, imaging findings) in your output
MUST be sourced from THIS PATIENT'S CLINICAL DATA CONTEXT above. Never
copy a value from an example, illustration, or template — those are
not patient data.

CONTENT REQUIREMENTS:
- USE all urologically relevant information provided in the source notes
- INCLUDE: GU symptoms, urologic diagnoses, test results (PSA, imaging, pathology), medications, and treatments that are documented
- INCLUDE: Relevant surgical history if mentioned
- SYNTHESIZE information from multiple visits into a coherent story
- MAINTAIN chronological progression when discussing the patient's condition
- CRITICAL: If PSA values, pathology results, or imaging findings are provided in the CLINICAL DATA CONTEXT above, you MUST reference the most recent/relevant ones in the HPI narrative. These are this patient's actual results.
- For PSA: mention the most recent value and trend (rising, stable, declining)
- For pathology: mention Gleason score, grade group, and key findings if present
- For imaging: mention key urologic findings from recent imaging

CROSS-SPECIALTY INTEGRATION (when CROSS-SPECIALTY UROLOGIC FINDINGS provided):
- Integrate urologically-relevant findings from other specialties into the narrative
- Hospital admissions for urologic reasons (urosepsis, hematuria, retention) - include admission details and outcome
- Oncology treatment requests (ADT, chemotherapy) - note what was requested and current status
- Radiation Oncology coordination - note if radiation was recommended, started, or completed
- Cancelled or rescheduled procedures - note the cancellation and reason if documented
- Cardiology/ID clearances or concerns - note relevant clearance status for pending procedures
- ONLY include cross-specialty content that is UROLOGICALLY RELEVANT
- Do NOT include non-urologic findings (pure cardiac, pulmonary, etc.)

PRIOR ASSESSMENT & PLAN INTEGRATION (when PRIOR A&P CONTEXT provided):
- Use prior A&P context to inform the HPI narrative with clinical progression
- Reference what was diagnosed and planned at previous visits
- Mention completed procedures and their results (using ONLY procedures explicitly named in PRIOR A&P CONTEXT or PATHOLOGY RESULTS above — do NOT invent procedure names)
- Note patient treatment decisions when explicitly documented
- Identify what issues remain outstanding from prior visits
- Frame the current visit in context of the clinical progression
- ANTI-HALLUCINATION FOR EXAMPLES: never copy specific diagnoses, Gleason scores, procedure names, or imaging modalities from this prompt. The structure shown is a SHAPE only — every clinical fact in the actual HPI must come from the patient's source notes.
- Generic shape example (do NOT copy any clinical specifics from this — they are placeholders):
    "<Patient> returns for followup of <DIAGNOSIS>. At last visit, <RECOMMENDATION>. Since then, <EVENT/RESULT>. Today, <CURRENT-DECISION-POINT>."

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures or treatments not mentioned in the notes
- DO NOT assume treatments based on diagnoses alone unless explicitly stated
- DO NOT add information from your general medical knowledge
- If a procedure is listed in past surgical history, you may include it
- If test results are mentioned (PSA values, imaging findings), include them
- Use ONLY the PSA values provided in the CLINICAL DATA CONTEXT - do NOT fabricate PSA values

EXCLUDE:
- Non-urologic health issues (cardiac, pulmonary, orthopedic, etc.) unless directly relevant to urologic care
- Administrative details and metadata
- Verbatim repetition - synthesize instead

IMPORTANT TERMINOLOGY:
- Replace "urology consult" with "urology followup" (this is a followup visit, not a new consult)
- Replace "consult for" with "followup for"
- Replace "for a urology consult" with "for a urology followup"
- This is a FOLLOWUP visit, not an initial consultation

IMPORTANT: If the source notes contain urologic consultation details, history, symptoms, or findings, you MUST use that information to create the HPI. Do NOT say "no information available" if urologic data exists in the source notes.

Provide ONLY the clinical narrative HPI. NO meta-commentary, NO explanations like "Based on the notes" or "Here is the HPI". Just the narrative itself, starting directly with the patient presentation.
"""

    if authoritative_facts and authoritative_facts.strip():
        # Bypass combine_sections_with_llm: the "You are a clinical
        # documentation assistant. Your task is to combine multiple
        # entries" boilerplate dilutes the authoritative-facts directive
        # and lets the LLM weight a contaminated prior-HPI Entry 1 more
        # heavily than the abstract ABSOLUTE RULES block. Lead the
        # prompt with the ground truth and a TASK directive framing the
        # prior HPI as suggestive-only source material to be rewritten.
        prompt_parts = [
            authoritative_facts,
            "\n=== TASK ===",
            "Rewrite the patient's History of Present Illness for TODAY'S visit",
            "using ONLY the deterministic CLINICAL DATA CONTEXT below as source",
            "of truth. Treat the PRIOR HPI SNAPSHOT(S) at the end of this prompt",
            "as suggestive context only — they were written by an earlier",
            "automated process that may have confabulated treatments, diagnoses,",
            "or recurrence framing. If any sentence in a prior HPI snapshot",
            "contradicts the GROUND TRUTH block above, that sentence is WRONG",
            "and must NOT appear in your output.",
            "",
            "Apply every ABSOLUTE RULE from the GROUND TRUTH block. If the",
            "patient is TREATMENT_NAIVE, the prior HPI's mention of 'focal",
            "therapy', 'Phoenix criteria', 'biochemical recurrence', 'salvage',",
            "or any 'completed / underwent / s/p <treatment>' phrase is a",
            "confabulation that must be removed and the narrative rewritten",
            "around the actual deterministic findings (PSA values, negative",
            "biopsies, BPH medications, etc.).",
            "",
            instructions,
            "\n=== PRIOR HPI SNAPSHOT(S) (suggestive context only) ===",
        ]
        for i, inst in enumerate(hpi_instances, 1):
            prompt_parts.append(f"\n--- Entry {i} ---\n{inst}\n")
        prompt_parts.append(
            "\n=== OUTPUT ===\n"
            "Provide ONLY the rewritten HPI narrative. No meta-commentary, no\n"
            "explanations. Start directly with the patient name and age."
        )
        final_prompt = "\n".join(prompt_parts)
        synthesized_hpi = synthesize_with_llm(
            prompt=final_prompt,
            temperature=0.0,
        )
    else:
        synthesized_hpi = combine_sections_with_llm(
            section_name="History of Present Illness",
            section_instances=hpi_instances,
            instructions=instructions,
        )

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # Deterministic redundancy removal. Catches the cases where the
    # LLM produces "summary" sentences that restate facts already
    # narrated earlier (e.g. "The patient's current PSA is 30.25
    # ng/mL" after a prior sentence already mentioned 30.25 ng/mL).
    # Only removes sentences with ≥60–80% token overlap to an earlier
    # sentence AND no new value introduced. See _dedupe_hpi_sentences
    # for the exact criteria.
    cleaned_hpi = _dedupe_hpi_sentences(cleaned_hpi)

    # Deterministic non-urologic-content stripper. Prompt-only rules
    # against listing non-urologic medications and labs leak — the LLM
    # still emits "He also takes Cetirizine for allergies and
    # Fluticasone Prop for nasal allergies" and "Recent laboratory
    # results include a specific gravity of 1.011, an EGFR CKD EPI of
    # 82, a glucose level of 102 mg/dL". Strip those sentences here.
    cleaned_hpi = _strip_nonurologic_sentences(cleaned_hpi)

    # Temporal-anchor post-processors. Catch the LLM failures that
    # survive the deterministic temporal-anchor and imaging-recency
    # context blocks: 'recent imaging shows X' for 2023 studies, and
    # 'rising PSA' framing applied to a clearly-declining trajectory.
    cleaned_hpi = _strip_stale_recent_qualifier(cleaned_hpi)
    cleaned_hpi = _reconcile_psa_direction(cleaned_hpi, psa_data)
    # PSA-hallucination scrubber — replaces fabricated PSA-context ng/mL
    # values (e.g., "PSA risen to 38.6 ng/mL" pulled from a TUMOR
    # SCREENS reference-range row) with the deterministic current PSA
    # and date from psa_data.
    cleaned_hpi = _scrub_psa_hallucinations(cleaned_hpi, psa_data)
    # Biopsy-claim scrubber — drop fabricated "underwent prostate biopsy"
    # clauses when PATHOLOGY RESULTS contains no biopsy and PSH lists
    # none. This was the Watley failure mode: the LLM completed the
    # "PSA spike → biopsy" narrative pattern and inverted "No prostate
    # pathology on file" → "(pathology on file)" by dropping the
    # negation. Both anchors (PATHOLOGY + PSH) are deterministic
    # extractors, so we can trust the negative evidence.
    cleaned_hpi = _scrub_unsupported_biopsy_claims(
        cleaned_hpi, pathology_data, psh_data,
    )
    # Final dedup pass — _reconcile_psa_direction can substitute
    # "elevated PSA" → "previously elevated PSA, now declining" and
    # produce duplicates when both "rising PSA" and "elevated PSA"
    # appear in the same sentence ("previously elevated PSA, now
    # declining, previously elevated PSA, now declining"). Run the
    # word-doubling collapse again to catch them.
    from .history_cleaners import _collapse_word_doubling as _cwd
    cleaned_hpi = _cwd(cleaned_hpi)

    # Age-corrector — the LLM occasionally writes a wrong age in the
    # opening sentence (carrying it over from a prior-visit HPI when
    # the patient was younger). Replace any "<wrong N>-year-old"
    # mention with the authoritative current age.
    if patient_age and str(patient_age).isdigit():
        true_age = int(patient_age)
        def _fix_age(m):
            cited = int(m.group(1))
            if cited == true_age:
                return m.group(0)
            # Plausible-age guard: only rewrite ages within ±15 years of
            # the truth (so a "5-year-old MS history" timing reference
            # is NOT rewritten).
            if abs(cited - true_age) > 15:
                return m.group(0)
            return f"{true_age}{m.group(0)[len(m.group(1)):]}"
        cleaned_hpi = re.sub(
            r'\b(\d{1,3})[-\s]year[-\s]old\b',
            _fix_age, cleaned_hpi,
        )

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        for note in gu_notes:
            if note.get("HPI"):
                verifier.extract_facts_from_source(note["HPI"])

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi


def synthesize_consult_hpi(
    consult_reason: str,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None,
    provider_urologic_context: Optional[str] = None,
    reason_for_request: Optional[str] = None,
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize comprehensive HPI for consult requests.

    Per instructions.txt workflow:
    - Initial HPI from Reason for Request / Reason for Consult Request
    - Scan provider notes (Current PC Provider, Requesting Provider) for urologic content
    - Combine and synthesize comprehensive HPI

    Creates a detailed narrative HPI by combining:
    - Patient demographics (name, age)
    - Consult reason (Provisional Diagnosis)
    - Reason for Request / Reason for Consult Request
    - Provider urologic context (from note scanning)
    - Relevant medical history (PMH, PSH)
    - Current medications (urologic focus)
    - Recent imaging findings
    - PCP note information

    Args:
        consult_reason: Brief consult request reason (from Reason for Consult Request)
        patient_name: Patient name (without titles)
        patient_age: Patient age
        pmh: Past medical history
        psh: Past surgical history
        medications: Current medications list
        imaging: Recent imaging reports
        pcp_note_data: Dict with PCP note extractions (social, family, hpi, etc.)
        provider_urologic_context: Urologic content from provider note scanning
        reason_for_request: Additional reason text (Reason For Request field)

    Returns:
        Comprehensive narrative HPI suitable for urology consult
    """
    # Build context sections for LLM synthesis
    context_sections = []

    # Add consult reason (primary driver - from Reason for Consult Request)
    context_sections.append(f"CONSULT REASON (from Reason for Consult Request):\n{consult_reason}")

    # Add Reason For Request if different and provided
    # Per instructions.txt: HPI = Reason for Request + Reason for Consult Request
    if reason_for_request and reason_for_request.strip():
        if reason_for_request.strip() != consult_reason.strip():
            context_sections.append(f"ADDITIONAL REQUEST DETAILS (from Reason For Request):\n{reason_for_request}")

    # Add provider urologic context (from provider note scanning)
    # Per instructions.txt: scan Requesting Provider and Current PC Provider notes
    # for urologic mentions and combine with consult request HPI
    if provider_urologic_context and provider_urologic_context.strip():
        context_sections.append(f"PROVIDER NOTES UROLOGIC CONTEXT:\n{provider_urologic_context}")

    # Add patient demographics
    if patient_name or patient_age or patient_sex:
        demo = []
        if patient_name:
            demo.append(f"Name: {patient_name}")
        if patient_age:
            demo.append(f"Age: {patient_age}")
        if patient_sex:
            demo.append(f"Sex: {patient_sex}")
        context_sections.append(f"PATIENT DEMOGRAPHICS:\n{', '.join(demo)}")

    # Add PMH (focus on urologic conditions)
    if pmh:
        # Extract urologic conditions
        urologic_keywords = [
            'kidney', 'renal', 'stone', 'calculi', 'nephrolithiasis',
            'prostate', 'bph', 'benign prostatic',
            'bladder', 'urinary', 'hematuria', 'incontinence',
            'uti', 'ureter', 'hydronephrosis',
            'psa', 'cancer', 'carcinoma',
            'erectile', 'testosterone', 'hypogonadism'
        ]

        pmh_lines = [line.strip() for line in pmh.split('\n') if line.strip()]
        urologic_pmh = []
        for line in pmh_lines:
            if any(kw in line.lower() for kw in urologic_keywords):
                urologic_pmh.append(line)

        if urologic_pmh:
            context_sections.append(f"RELEVANT MEDICAL HISTORY:\n" + '\n'.join(urologic_pmh[:10]))  # Limit to top 10

    # Add PSH (focus on urologic procedures)
    if psh:
        urologic_proc_keywords = [
            'ureteroscopy', 'lithotripsy', 'turp', 'turbt',
            'prostatectomy', 'cystoscopy', 'nephrectomy',
            'kidney', 'bladder', 'prostate', 'ureter',
            'stone', 'calculus', 'stent'
        ]

        psh_lines = [line.strip() for line in psh.split('\n') if line.strip()]
        urologic_psh = []
        for line in psh_lines:
            if any(kw in line.lower() for kw in urologic_proc_keywords):
                urologic_psh.append(line)

        if urologic_psh:
            context_sections.append(f"RELEVANT SURGICAL HISTORY:\n" + '\n'.join(urologic_psh))

    # Add medications (focus on urologic meds)
    if medications:
        urologic_meds = [
            'tamsulosin', 'flomax', 'finasteride', 'proscar',
            'dutasteride', 'avodart', 'alfuzosin', 'silodosin',
            'testosterone', 'androgel', 'tadalafil', 'cialis',
            'sildenafil', 'viagra', 'oxybutynin', 'tolterodine',
            'solifenacin', 'mirabegron', 'trospium'
        ]

        med_lines = [line.strip() for line in medications.split('\n') if line.strip()]
        urologic_medication_list = []
        for line in med_lines:
            if any(med in line.lower() for med in urologic_meds):
                urologic_medication_list.append(line)

        if urologic_medication_list:
            context_sections.append(f"UROLOGIC MEDICATIONS:\n" + '\n'.join(urologic_medication_list))

    # Add imaging
    if imaging:
        # Limit imaging to reasonable length
        imaging_summary = imaging[:1000] if len(imaging) > 1000 else imaging
        context_sections.append(f"RECENT IMAGING:\n{imaging_summary}")

    # Add PSA data if available
    if psa_data and psa_data.strip():
        context_sections.append(f"PSA VALUES:\n{psa_data}")

    # Add pathology results if available
    if pathology_data and pathology_data.strip():
        pathology_summary = pathology_data[:1500] if len(pathology_data) > 1500 else pathology_data
        context_sections.append(f"PATHOLOGY RESULTS:\n{pathology_summary}")

    # Add lab results if available
    if labs_data and labs_data.strip():
        labs_summary = labs_data[:1000] if len(labs_data) > 1000 else labs_data
        context_sections.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")

    # Add PCP note details if available
    if pcp_note_data:
        if pcp_note_data.get('hpi'):
            context_sections.append(f"PCP NOTE HPI:\n{pcp_note_data['hpi']}")

    # Combine all context
    full_context = '\n\n'.join(context_sections)

    # Build prompt for LLM synthesis
    prompt = f"""You are a clinical documentation assistant creating a History of Present Illness (HPI) for a urology consult.

Create a comprehensive, narrative HPI based on the following information:

{full_context}

SYNTHESIS REQUIREMENTS (per consult workflow):
1. The primary HPI content comes from the CONSULT REASON and ADDITIONAL REQUEST DETAILS
2. The PROVIDER NOTES UROLOGIC CONTEXT contains additional urologic information from the requesting/primary care provider's notes
3. You MUST synthesize ALL of these sources into a cohesive narrative
4. Information from consult request may be sentence fragments - make them complete and coherent
5. Integrate provider note content to add clinical context and background

STRUCTURE:
1. Opening: "[Patient name] is a [age]-year-old [sex from demographics, lowercase] with history of [key urologic conditions] who presents [consult reason]"
2. Detail relevant urologic history chronologically
3. Include recent procedures and their timing/outcomes if mentioned
4. Note current urologic medications and their effectiveness if stated
5. Include pertinent imaging findings if available
6. End with relevant symptoms or clinical concerns

CONTENT REQUIREMENTS:
- USE ONLY information provided in the source data above
- Focus on UROLOGIC conditions and history
- Integrate all provided sections into a cohesive narrative
- Write in third person, past tense for history, present tense for current status
- Use complete sentences in paragraph form (not bullet points)
- Include specific dates, values, and findings when provided
- Mention previous providers if noted in consult reason
- IMPORTANT: The consult reason text may be incomplete or fragmentary - complete the sentences appropriately
- CRITICAL: If PSA values are provided, mention the most recent PSA and trend
- CRITICAL: If pathology results are provided (Gleason score, grade group), include them
- CRITICAL: If lab results are provided, include relevant abnormal findings

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures, medications, symptoms, or findings not mentioned
- DO NOT add provider names unless stated in source
- DO NOT speculate about outcomes or effectiveness unless explicitly stated
- DO NOT include non-urologic conditions unless directly relevant to GU care
- If age is not provided, omit age reference
- If patient name is not provided, use "The patient" or "Patient"
- Use ONLY PSA values from the data provided - do NOT fabricate values

FORMATTING:
- Write 2-3 paragraphs maximum
- First paragraph: patient intro, primary urologic conditions, and consult reason
- Second paragraph (if needed): detailed history, procedures, imaging findings
- Keep concise but comprehensive (target 200-400 words)

EXAMPLE OPENING:
"Mr. Kile is a 74-year-old male with history of recurrent kidney stones and BPH who presents today as a new VA urology patient. He previously followed with a civilian urologist but no longer has outside insurance."

Provide ONLY the narrative HPI. NO meta-commentary, NO explanations. Just the clinical narrative.
"""

    # Call LLM directly with zero temperature for deterministic synthesis
    synthesized_hpi = synthesize_with_llm(
        prompt=prompt,
        temperature=0.0
    )

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        if consult_reason:
            verifier.extract_facts_from_source(consult_reason)
        if reason_for_request:
            verifier.extract_facts_from_source(reason_for_request)
        if provider_urologic_context:
            verifier.extract_facts_from_source(provider_urologic_context)

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        if imaging:
            verifier.extract_facts_from_source(imaging)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"Consult HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected consult HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"Consult HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi
