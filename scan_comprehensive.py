"""
Comprehensive section-by-section audit of all 34 patient notes.

Cross-references rendered output sections against source test files to
catch issues a pattern-only scanner can't (missing labs, hallucinated
treatments, dropped panels, narrative leaks, template placeholders).

Severity:
  CRITICAL — clinical safety risk (fabricated treatment, wrong drug,
             hallucinated lab value)
  HIGH     — wrong info (date mismatch, swapped value, narrative leak
             into wrong section)
  MEDIUM   — missing info from source (lab panel dropped, allergy
             missed, imaging absent)
  LOW      — cosmetic / formatting (sparse output, suboptimal ordering)
"""
import os
import re
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

ROOT = Path("/home/exx/PycharmProjects/vaucda")
TESTS = ROOT / "tests"
OUTPUT = ROOT / "logs" / "output.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def split_patients(text):
    parts = re.split(r'(?=^Patient:\s)', text, flags=re.MULTILINE)
    return [p for p in parts if p.strip().startswith("Patient:")]


def find_test_file(patient_name):
    """Match output patient to test file. Patient format e.g. 'KENNETH SHAWN Everett'."""
    last = patient_name.split()[-1].upper()
    candidates = sorted(TESTS.glob(f"*{last}*.txt"))
    if candidates:
        return candidates[0]
    return None


def section(note, header_re):
    """Extract a section's body from the rendered note."""
    m = re.search(header_re, note, re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    # Find next section header (top-level section markers vary)
    next_section = re.search(
        r'\n(?:=+\s*[A-Z][A-Z\s/&]+\s*=+|'
        r'^(?:CC|HPI|IPSS|DIETARY|SOCIAL|FAMILY|SEXUAL|PAST MEDICAL|'
        r'PAST SURGICAL|PSA CURVE|MEDICATIONS|ALLERGIES|PATHOLOGY|'
        r'GENERAL ROS|PHYSICAL|ASSESSMENT|PROBLEM|PLAN|Time of Start|'
        r'\[NEXT PATIENT\])\b)',
        note[start:], re.MULTILINE,
    )
    end = start + (next_section.start() if next_section else len(note) - start)
    return note[start:end].strip()


def patient_name(note):
    m = re.search(r'^Patient:\s*([^\(\|]+)', note)
    return m.group(1).strip() if m else "?"


def patient_age(note):
    m = re.search(r'Age:\s*(\d{1,3})', note)
    return int(m.group(1)) if m else None


def patient_sex(note):
    m = re.search(r'Sex:\s*([A-Z]+)', note)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Section scanners — each returns list of (severity, code, msg) tuples
# ---------------------------------------------------------------------------

def scan_patient_banner(note, source):
    f = []
    age = patient_age(note)
    # DOB from source?
    dob_m = re.search(r'DOB:\s*(\d{1,2}/\d{1,2}/\d{4})', source)
    if age and dob_m:
        try:
            dob = datetime.strptime(dob_m.group(1), '%m/%d/%Y')
            # Today's date from VISIT DATE: line
            vd_m = re.search(r'DATE:\s*(\d{1,2}/\d{1,2}/\d{4})', source)
            visit = datetime.strptime(vd_m.group(1), '%m/%d/%Y') if vd_m else datetime.now()
            computed = visit.year - dob.year - ((visit.month, visit.day) < (dob.month, dob.day))
            if abs(age - computed) > 0:
                f.append(("HIGH", "BANNER_AGE_WRONG",
                          f"banner age={age}, computed={computed} from DOB {dob_m.group(1)}"))
        except Exception:
            pass
    return f


def scan_cc(note, source):
    f = []
    cc = section(note, r'^CC:\s*')
    if not cc or cc.strip() in ("", "Urology follow-up"):
        f.append(("MED", "CC_GENERIC", f"CC='{cc.strip()}'"))
    # Editorializing
    if re.search(r'no\s+urolog|there\s+(is|are)\s+no\s+|cannot\s+determine|'
                 r'based\s+on|i\s+will|i\'ll', cc, re.IGNORECASE):
        f.append(("HIGH", "CC_META_LEAK", f"CC='{cc.strip()[:100]}'"))
    # Markdown
    if '**' in cc or re.search(r'\[(?:Last|First|Patient|Insert)', cc):
        f.append(("HIGH", "CC_PLACEHOLDER", f"CC='{cc.strip()[:100]}'"))

    # Cross-reference output CC against source's most-recent stated CC.
    # When source explicitly mentions prostate cancer / RCC / bladder cancer
    # follow-up in its CC, output CC must reference the same primary dx.
    # Catches cases like Woods (source: "Follow-up for prostate cancer,
    # nephrolithiasis, and LUTS" -> output: "Follow-up for hematuria")
    # and Cann (source: "Prostate cancer on Active Surveillance" ->
    # output: "Follow-up for recurrent UTI").
    src_cc_matches = re.findall(
        r'(?im)^\s*CC\s*:\s*([^\n]+)', source,
    )
    if src_cc_matches and cc:
        # Inspect the SHORTEST source CC line (most direct statement —
        # avoids 3-line wrapped narrative CCs that include everything).
        # Fall back to most-recent if all are similar length.
        src_cc = min(src_cc_matches, key=len).strip().rstrip('.')
        cc_lower = cc.lower()
        # Primary-cancer / surveillance signals the output must echo
        primary_signals = (
            "prostate cancer", "active surveillance",
            "renal cell carcinoma", "kidney cancer",
            "bladder cancer", "urothelial",
            "testicular cancer", "germ cell",
            "biochemical recurrence",
        )
        for sig in primary_signals:
            if sig in src_cc.lower() and sig.split()[0] not in cc_lower:
                # The primary diagnosis is in source CC but its leading
                # noun is missing from output CC.
                f.append(("HIGH", "CC_PRIMARY_MISMATCH",
                          f"source CC names {sig!r}; output CC: '{cc.strip()[:80]}'"))
                break
    return f


def scan_hpi(note, source):
    f = []
    hpi = section(note, r'^HPI:\s*')
    if not hpi:
        f.append(("CRITICAL", "HPI_EMPTY", "no HPI section"))
        return f
    if hpi.strip() == "No prior urologic history documented":
        f.append(("HIGH", "HPI_FALLBACK_SENTINEL",
                  "HPI rendered as fallback sentinel"))
        return f
    # Markdown / scaffolding
    if '**' in hpi:
        f.append(("HIGH", "HPI_MARKDOWN_LEAK", f"** in HPI: {hpi[:120]}"))
    if re.search(r'\[(?:Last|First|Patient|Insert|TBD|List|Placeholder)',
                 hpi, re.IGNORECASE):
        f.append(("HIGH", "HPI_PLACEHOLDER",
                  f"placeholder in HPI: {hpi[:120]}"))
    if re.search(r'\bMr\.\s+\[|Ms\.\s+\[|Dr\.\s+\[', hpi):
        f.append(("HIGH", "HPI_NAME_PLACEHOLDER",
                  "stripped-name placeholder in HPI"))
    if re.search(r'^\s*(?:Patient\s+Name|Age|Sex|DOB):\s', hpi, re.MULTILINE):
        f.append(("MED", "HPI_DEMO_SCAFFOLDING",
                  "demographic scaffolding line in HPI"))
    # Meta-commentary
    if re.search(r'\bBased\s+on\b.*?I\s+(?:will|have|\'ll)\b', hpi, re.IGNORECASE):
        f.append(("HIGH", "HPI_META_INTRO",
                  "'Based on...I will' meta intro in HPI"))
    if re.search(r'\bI\'ve\s+followed\b|\bI\s+have\s+followed\b', hpi,
                 re.IGNORECASE):
        f.append(("HIGH", "HPI_META_OUTRO",
                  "'I've followed the rules' meta outro"))
    if re.search(r'\bThis\s+rewritten\s+HPI\b', hpi, re.IGNORECASE):
        f.append(("HIGH", "HPI_META_REFERENCE",
                  "'this rewritten HPI' meta"))
    # Word doubling
    for m in re.finditer(r'\b(\w+(?:\s+\w+){0,2})\s+\1\b', hpi, re.IGNORECASE):
        if len(m.group(1)) > 4:  # ignore "is is", "in in" false positives
            f.append(("MED", "HPI_WORD_DOUBLING",
                      f"'{m.group(1)} {m.group(1)}'"))
            break  # report once
    # PSA contradictions
    for s in re.split(r'(?<=[.!?])\s+', hpi):
        sl = s.lower()
        if ('rising' in sl or 'risen' in sl or 'increased' in sl) and \
           ('decreased' in sl or 'declined' in sl or 'declining' in sl) and \
           'psa' in sl:
            f.append(("HIGH", "HPI_PSA_CONTRADICTION", s[:140]))
            break
    # Treatment hallucination — claims X but PSH doesn't list X
    psh_text = section(note, r'^PAST SURGICAL HISTORY:\s*').lower()
    pathology_text = section(note, r'^PATHOLOGY RESULTS:\s*').lower()
    # Prostatectomy claim
    if re.search(r'\b(?:underwent|completed|s/?p|status\s+post|had)\s+'
                 r'(?:a\s+|the\s+)?(?:radical\s+)?prostatectomy\b',
                 hpi, re.IGNORECASE):
        if not re.search(r'prostatectomy|ralp|rarp|rrp', psh_text):
            f.append(("CRITICAL", "HPI_PROSTATECTOMY_HALLUCINATION",
                      "HPI claims prostatectomy with no PSH evidence"))
    # XRT/EBRT claim
    if re.search(r'\b(?:underwent|completed|received|s/?p|status\s+post)\s+'
                 r'(?:definitive\s+|external\s+beam\s+)?'
                 r'(?:radiation|radiotherapy|EBRT|XRT|IMRT|SBRT|brachy)',
                 hpi, re.IGNORECASE):
        if not re.search(r'radiation|xrt|ebrt|imrt|sbrt|brachy|seed',
                         psh_text + ' ' + pathology_text):
            f.append(("CRITICAL", "HPI_RADIATION_HALLUCINATION",
                      "HPI claims radiation with no PSH/path evidence"))
    # Biopsy claim (prostate)
    if re.search(r'\b(?:underwent|had|completed|s/?p)\s+'
                 r'(?:a\s+|the\s+|prior\s+)?(?:transrectal\s+)?'
                 r'prostate\s+biops(?:y|ies)\b'
                 r'|prostate\s+biopsy\s+(?:revealed|showed|demonstrated)',
                 hpi, re.IGNORECASE):
        if not re.search(r'prostate\s+biops|trus\s*[/-]?bx|gleason|adenocarcinoma',
                         pathology_text + ' ' + psh_text):
            f.append(("CRITICAL", "HPI_BIOPSY_HALLUCINATION",
                      "HPI claims prostate biopsy with no PATH/PSH evidence"))
    # Internal contradiction within the HPI itself. Catches the Woods
    # failure mode where v2's visit_reason said "low-risk ... on active
    # surveillance" while the rest of the HPI correctly said "high
    # risk" + "completed radiation therapy". The LLM hallucinated
    # framing inconsistent with its own validated facts.
    hpi_l_low = hpi.lower()
    has_low_risk = bool(re.search(r"\b(?:very[\s-]?low[\s-]?risk|low[\s-]?risk)\b", hpi_l_low))
    has_high_risk = bool(re.search(r"\bhigh[\s-]?risk\b", hpi_l_low))
    if has_low_risk and has_high_risk:
        f.append(("HIGH", "HPI_INTERNAL_CONTRADICTION",
                  "HPI mixes 'low-risk' and 'high-risk' framing"))
    mentions_as = bool(re.search(r"\bactive\s+surveillance\b", hpi_l_low))
    mentions_completed_definitive = bool(re.search(
        r"\bcompleted\s+(?:radical\s+)?(?:radiation|imrt|ebrt|xrt|brachy|"
        r"prostatectomy|sbrt|nephrectomy|cystectomy)",
        hpi_l_low,
    )) or bool(re.search(
        r"\bs/p\s+(?:imrt|radical\s+prostatectomy|ralp|rrp|rarp|radiation|"
        r"ebrt|xrt|brachy|nephrectomy|cystectomy)",
        hpi_l_low,
    ))
    if mentions_as and mentions_completed_definitive:
        f.append(("HIGH", "HPI_INTERNAL_CONTRADICTION",
                  "HPI says 'active surveillance' AND mentions completed "
                  "definitive treatment in the same paragraph"))

    # Treatment-tense mismatch — HPI uses future/planning language
    # ("we will proceed with radiation", "plan to undergo prostatectomy",
    # "would be for ADT") for a treatment the SOURCE explicitly marks
    # as s/p or completed. Catches the Woods failure mode where v1 LLM
    # regurgitated 2015 pre-treatment plan as if current despite source
    # clearly showing s/p IMRT for 11 years.
    sl = source.lower()
    treatment_completed_in_src = {
        'radiation':   bool(re.search(r's/p\s+(?:imrt|ebrt|xrt|radiation|brachy|sbrt)'
                                       r'|status\s+post\s+(?:imrt|radiation|ebrt|xrt)'
                                       r'|imrt\s+completed|radiation\s+therapy\s+completed'
                                       r'|completed\s+(?:imrt|radiation|ebrt|xrt)',
                                       sl)),
        'prostatectomy': bool(re.search(r's/p\s+(?:radical\s+)?prostatectomy'
                                         r'|status\s+post\s+(?:radical\s+)?prostatectomy'
                                         r'|prostatectomy\s+completed|s/p\s+ralp'
                                         r'|s/p\s+rrp|s/p\s+rarp',
                                         sl)),
        'adt':         bool(re.search(r's/p\s+adt|status\s+post\s+adt'
                                       r'|adt\s+completed|completed\s+adt'
                                       r'|years\s+of\s+adt|adt\s+for\s+\d+\s+(?:months|years)',
                                       sl)),
    }
    hpi_l = hpi.lower()
    future_treatment_patterns = (
        (r'\b(?:we\s+will|plan\s+to|planning\s+to|will\s+proceed\s+with|'
         r'would\s+be\s+for|our\s+plan\s+(?:would\s+be|is)\s+(?:for|to))\s+'
         r'(?:[^.]{0,80}?)(radiation|imrt|ebrt|xrt|brachy)', 'radiation'),
        (r'\b(?:we\s+will|plan\s+to|planning\s+to|will\s+proceed\s+with|'
         r'scheduled\s+for)\s+'
         r'(?:[^.]{0,80}?)(prostatectomy|ralp|rrp|rarp)', 'prostatectomy'),
        (r'\b(?:we\s+will|plan\s+to|will\s+initiate|will\s+start|'
         r'would\s+be\s+for)\s+(?:[^.]{0,80}?)(adt|androgen\s+ablation|'
         r'androgen\s+deprivation)', 'adt'),
    )
    for pat, modality in future_treatment_patterns:
        m = re.search(pat, hpi_l)
        if m and treatment_completed_in_src.get(modality):
            f.append(("HIGH", "HPI_PLANS_COMPLETED_TREATMENT",
                      f"HPI uses future tense for {modality} "
                      f"but source has s/p {modality} (sentence: "
                      f"'{m.group(0)[:120]}')"))
            break

    # Non-urologic finding leakage
    non_uro = ['bile duct', 'gallbladder', 'small bowel', 'cholelith',
               'nasopharyng', 'parotid', 'thyroid nodule', 'pulmonary embolism',
               'abdominal aortic']
    for term in non_uro:
        if term in hpi.lower():
            uro_anchors_present = bool(re.search(
                r'\b(?:psa|prostate|kidney|renal|bladder|urinary|biopsy|'
                r'urolog)\b', hpi, re.IGNORECASE,
            ))
            if not uro_anchors_present or hpi.lower().count(term) > 1:
                f.append(("MED", "HPI_NONUROLOGIC_LEAK",
                          f"'{term}' in HPI"))
                break
    # Trailing fragments
    if re.search(r'(?:^|\.\s+)(?:Note\s+that|Please\s+note\s+that)[^.]*$',
                 hpi, re.IGNORECASE):
        f.append(("MED", "HPI_TRAILING_FRAGMENT", "'Note that...' trailing"))
    # Truncated ending (no terminal period in last 50 chars)
    if hpi and not hpi.rstrip().endswith(('.', '!', '?', ')', '"')):
        f.append(("LOW", "HPI_NO_TERMINAL_PUNCT",
                  f"HPI doesn't end with terminal punct: ...{hpi[-60:]}"))
    # Length checks
    word_count = len(hpi.split())
    if word_count < 20:
        f.append(("HIGH", "HPI_TOO_SHORT", f"only {word_count} words"))
    return f


def scan_labs(note, source):
    f = []
    labs = section(note, r'^=+\s*LABS\s*=+')
    if not labs:
        # No labs at all — check if source has labs
        if re.search(r'\bCHAM\b|\bSLT\s*-|CBC\s+Coll', source):
            f.append(("HIGH", "LABS_MISSING_ENTIRELY",
                      "Source has labs but LABS section absent"))
        return f
    # Narrative leak detection — line starts with date + colon + prose
    for line in labs.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Lab lines look like "TEST  VALUE  UNIT  RANGE  (DATE)" or
        # "DATE  TEST  VALUE". Narrative leak: "DATE: <prose without
        # numeric value in first 80 chars>"
        m = re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}:\s+(.+)$', line)
        if m:
            body = m.group(1)
            # If body has prose markers (multiple sentences, no value)
            has_numeric = bool(re.search(r'\d+\.?\d*\s*(?:mg|ng|U|mEq|mmol|%|/)', body))
            has_prose = bool(re.search(
                r'\b(?:patient|year-?old|placed\s+on|underwent|biopsy|'
                r'reported|denies|complained|approximately)\b',
                body, re.IGNORECASE,
            ))
            if not has_numeric and has_prose:
                f.append(("HIGH", "LABS_NARRATIVE_LEAK",
                          f"narrative line in LABS: {line[:100]}"))
                break
    # Missing comprehensive metabolic panel
    has_cmp_in_source = bool(re.search(
        r'\bCHAM\s*\d+|\b(?:CREATININE|UREA NITROGEN|GLUCOSE|SODIUM|POTASSIUM)\b.*\bSERUM\b',
        source,
    ))
    if has_cmp_in_source:
        # Output should have creatinine + a few BMP analytes
        bmp_in_output = [
            t for t in ('creatinine', 'glucose', 'sodium', 'potassium', 'chloride')
            if t in labs.lower()
        ]
        if len(bmp_in_output) < 3:
            f.append(("MED", "LABS_CMP_INCOMPLETE",
                      f"Source has CMP, output has {bmp_in_output}"))
    # Missing CBC
    if re.search(r'\bWBC\b.*\bHGB\b|\bCBC\b.*Coll', source):
        cbc_terms = ['wbc', 'hgb', 'hct']
        cbc_hits = sum(1 for t in cbc_terms if t in labs.lower())
        if cbc_hits == 0:
            f.append(("MED", "LABS_CBC_MISSING",
                      "Source has CBC but output lacks WBC/HGB/HCT"))
    return f


def scan_psa(note, source):
    f = []
    psa_section = section(note, r'^PSA CURVE:\s*')
    if not psa_section:
        # Check if source has PSA values
        if re.search(r'\bPSA\s+TOTAL\s+\d|\bPSA\b.*\bSERUM\b|\[r\]\s+\w{3}\s+\d', source):
            f.append(("HIGH", "PSA_CURVE_MISSING",
                      "Source has PSA but output has no PSA CURVE"))
        return f
    # Check ordering: should be reverse chronological
    dates = []
    for line in psa_section.split('\n'):
        m = re.search(r'(\w{3}\s+\d{1,2},\s+\d{4})', line)
        if m:
            try:
                dates.append(datetime.strptime(m.group(1), '%b %d, %Y'))
            except ValueError:
                pass
    if len(dates) >= 2:
        # Should be non-increasing (newest first)
        out_of_order = sum(1 for i in range(len(dates)-1)
                           if dates[i] < dates[i+1])
        if out_of_order:
            f.append(("LOW", "PSA_OUT_OF_ORDER",
                      f"{out_of_order} PSA dates out of order"))
    return f


def scan_pathology(note, source):
    f = []
    path = section(note, r'^PATHOLOGY RESULTS:\s*')
    if not path or 'None documented' in path:
        # Check if source has biopsy
        if re.search(r'\bMICROSCOPIC\s+EXAM\b|\bA\.\s+PROSTATE.*BIOPS|'
                     r'\d{1,2}/\d{1,2}/\d{2,4}\s+(?:Prostate\s+)?Biopsy:|'
                     r'GLEASON\s+SCORE', source, re.IGNORECASE):
            f.append(("HIGH", "PATH_MISSING_WHEN_SOURCE_HAS_BIOPSY",
                      "Source has biopsy/pathology but output says 'None documented'"))
        return f
    # Phantom: layman / consent / discharge text
    for line in path.split('\n'):
        sl = line.lower()
        if any(p in sl for p in ('layman', 'discussed in', 'consent form',
                                 'admit to level of care',
                                 'expected date of discharge')):
            f.append(("HIGH", "PATH_PHANTOM", f"{line[:140]}"))
            break
    # FDA disclaimer
    if re.search(r'food\s+and\s+drug|fda\s+does\s+not\s+require', path,
                 re.IGNORECASE):
        f.append(("MED", "PATH_FDA_LEAK", "FDA disclaimer in pathology"))
    # No date in first entry
    first = path.strip().split('\n', 1)[0]
    has_date_in_first_5_lines = bool(re.search(
        r'\d{1,2}/\d{1,2}/\d{2,4}|\w{3}\s+\d{1,2},\s+\d{4}',
        '\n'.join(path.strip().split('\n')[:5]),
    ))
    if not has_date_in_first_5_lines:
        f.append(("LOW", "PATH_NO_DATE",
                  f"pathology has no date in first 5 lines: {first[:60]}"))
    return f


def scan_psh(note, source):
    f = []
    psh = section(note, r'^PAST SURGICAL HISTORY:\s*')
    if not psh:
        return f
    # "None" alongside real entries
    lines = [l.strip() for l in psh.split('\n') if l.strip()]
    if len(lines) >= 2:
        for l in lines:
            stripped = re.sub(r'^\d+\.\s*', '', l).strip().rstrip('.').lower()
            if stripped in ('none', 'n/a', 'denies', 'no surgical history'):
                f.append(("MED", "PSH_NONE_SENTINEL", f"{l}"))
                break
    # Duplicate canonical procedures
    canonical = []
    for l in lines:
        stripped = re.sub(r'^\d+\.\s*', '', l).strip().lower()
        # Get first few content words
        words = stripped.split()
        if words:
            canonical.append(words[0])
    dupes = [c for c in canonical if canonical.count(c) > 1]
    if len(set(dupes)) > 0:
        f.append(("LOW", "PSH_DUP_ROOT", f"{sorted(set(dupes))[:3]}"))
    # Truncated entries (sentence fragments)
    for l in lines:
        if len(l) < 6 or (l.endswith(',') or l.endswith('(')) and \
           not re.search(r'\d{4}|\d{1,2}/\d{1,2}', l):
            f.append(("LOW", "PSH_FRAGMENT", f"{l[:100]}"))
            break
    return f


def scan_medications(note, source):
    f = []
    meds = section(note, r'^MEDICATIONS:\s*')
    if not meds:
        return f
    if 'Not documented' in meds:
        if re.search(r'\bRXOP\b|\bActive Outpatient\b', source):
            f.append(("HIGH", "MEDS_MISSING_WHEN_SOURCE_HAS",
                      "Source has RXOP but output says 'Not documented'"))
    return f


def scan_allergies(note, source):
    f = []
    allerg = section(note, r'^ALLERGIES:\s*')
    if not allerg:
        return f
    if 'No known drug allergies' in allerg or 'NKDA' in allerg:
        # Check if source has real allergies
        if re.search(r'\bAR\s+-\s+Allergy|^A\s+[A-Z][A-Z]+\b', source,
                     re.MULTILINE):
            # Source has Allergy section — count real entries
            ar_block = re.search(r'-+\s+AR\s+-\s+Allergy[^-]*?\n(.*?)(?=\n-+|\Z)',
                                 source, re.DOTALL)
            if ar_block:
                body = ar_block.group(1)
                # Count A-prefixed lines
                count = len(re.findall(r'^A\s+\S+', body, re.MULTILINE))
                if count >= 1:
                    f.append(("HIGH", "ALLERGIES_MISSED",
                              f"Source has {count} allergy entries but output is NKDA"))
    return f


def scan_pmh(note, source):
    f = []
    pmh = section(note, r'^PAST MEDICAL HISTORY:\s*')

    # Cross-reference: if source has a populated PMH/Active-Problem list
    # AND output PMH is empty, that's a HIGH safety finding. Without this
    # check the empty-PMH failure mode is invisible — exactly how the
    # extractor's missing-format-support bug went undetected across two
    # batches (44/44 patients silently shipping with no PMH).
    src_has_pmh = (
        re.search(r'(?im)^\s*PAST\s+MEDICAL\s+HISTORY\s*:\s*\n[^\n]*\w', source)
        or re.search(r'(?im)^\s*PAST\s+MEDICAL\s+HX\s*:\s*Active\s+Problem', source)
        or re.search(r'(?im)Active\s+Problems?\s+List', source)
        or re.search(r'(?im)Provider\s+Narrative.*?(?:SCT|ICD)', source, re.DOTALL)
    )
    if (not pmh or len(pmh.strip()) < 5) and src_has_pmh:
        f.append(("HIGH", "PMH_EMPTY_WITH_SOURCE_DIAGNOSES",
                  "PMH section empty/missing but source has populated PMH"))
        return f

    if not pmh:
        return f
    # Code leaks
    for line in pmh.split('\n'):
        if re.search(r'\((?:SCT|SNOMED|ICD-?\d|N99\.89)\b', line, re.IGNORECASE):
            f.append(("MED", "PMH_CODE_LEAK", f"{line.strip()[:120]}"))
            break
    return f


def scan_imaging(note, source):
    f = []
    imaging = section(note, r'^=+\s*IMAGING\s*=+')
    if not imaging:
        return f
    # Undated entries
    for line in imaging.split('\n'):
        if '(undated)' in line.lower():
            f.append(("MED", "IMAGING_UNDATED", f"{line[:120]}"))
            break
    # Cystoscopy with CT/MRI text
    cysto = re.search(r'CYSTOSCOPY\s*\([^\)]*\):\s*\n([^\n]+)', imaging,
                      re.IGNORECASE)
    if cysto:
        content = cysto.group(1).lower()
        if any(p in content for p in ('evaluation of solid organs',
                                      'intravenous contrast',
                                      'hydronephrosis', 'kidney/ureters',
                                      'multiplanar reformats')):
            f.append(("HIGH", "IMAGING_CYSTO_CT_LEAK",
                      f"cysto block has CT text: {content[:120]}"))
    return f


def scan_pe(note, source):
    f = []
    pe = section(note, r'^PHYSICAL EXAM(?:INATION)?:\s*')
    if not pe:
        return f
    # Empty PROSTATE: line
    if re.search(r'^PROSTATE:\s*$', pe, re.MULTILINE):
        f.append(("LOW", "PE_PROSTATE_EMPTY", "PROSTATE: line empty"))
    return f


def scan_social(note, source):
    f = []
    soc = section(note, r'^SOCIAL HISTORY:\s*')
    if not soc:
        return f
    # Template placeholders
    if re.search(r'\[(?:insert|specify|describe|TBD|placeholder)',
                 soc, re.IGNORECASE):
        f.append(("HIGH", "SOCIAL_PLACEHOLDER",
                  "template placeholder in social hx"))
    return f


def scan_family(note, source):
    f = []
    fam = section(note, r'^FAMILY HISTORY:\s*')
    if not fam:
        return f
    # Orphan parent labels
    if re.search(r'^(?:Father|Mother|Brother|Sister):\s*\n', fam,
                 re.MULTILINE):
        f.append(("LOW", "FAMILY_ORPHAN_LABEL",
                  "orphan parent label in family hx"))
    # No information boilerplate
    if 'No information provided' in fam or 'Unknown medical history' in fam:
        f.append(("LOW", "FAMILY_NOINFO_BOILER",
                  "'No information provided' boilerplate"))
    return f


def scan_ipss(note, source):
    f = []
    ipss = section(note, r'^IPSS:\s*')
    if not ipss:
        return f
    # Check that today's column is empty (chart prep — not interviewed yet)
    # Find today's column header
    today_m = re.search(r'(\d{1,2}/\d{1,2}/\d{2})\s*\|\s*$', ipss, re.MULTILINE)
    if today_m:
        # OK — today's column expected to be empty
        pass
    # Check if all prior columns are empty (suggests no IPSS history)
    has_any_value = bool(re.search(r'\|\s*\d+\s*\|', ipss))
    if not has_any_value and re.search(r'\bIPSS\b', source):
        f.append(("LOW", "IPSS_ALL_EMPTY",
                  "IPSS table has no historical values"))
    return f


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

SCANNERS = [
    scan_patient_banner, scan_cc, scan_hpi, scan_labs, scan_psa,
    scan_pathology, scan_psh, scan_medications, scan_allergies, scan_pmh,
    scan_imaging, scan_pe, scan_social, scan_family, scan_ipss,
]


def main():
    with open(OUTPUT) as f:
        text = f.read()
    patients = split_patients(text)

    print(f"Scanning {len(patients)} patients with {len(SCANNERS)} section scanners\n")

    all_findings = []  # (patient, sev, code, msg)
    by_patient = defaultdict(list)
    by_code = defaultdict(list)

    for note in patients:
        name = patient_name(note)
        tf = find_test_file(name)
        source = tf.read_text(encoding='utf-8', errors='replace') if tf else ""
        for sc in SCANNERS:
            try:
                for sev, code, msg in sc(note, source):
                    all_findings.append((name, sev, code, msg))
                    by_patient[name].append((sev, code, msg))
                    by_code[code].append((name, sev, msg))
            except Exception as e:
                print(f"!!! {sc.__name__} crashed on {name}: {e}")

    # ---------- Summary by severity ----------
    sev_counts = defaultdict(int)
    for _, sev, _, _ in all_findings:
        sev_counts[sev] += 1
    print("=== SEVERITY SUMMARY ===")
    for sev in ('CRITICAL', 'HIGH', 'MED', 'LOW'):
        print(f"  {sev:8s}  {sev_counts[sev]}")
    print(f"  TOTAL   {len(all_findings)}\n")

    # ---------- By code (most frequent first) ----------
    print("=== FINDINGS BY CODE ===")
    for code in sorted(by_code, key=lambda c: (-len(by_code[c]), c)):
        entries = by_code[code]
        sev = entries[0][1]
        print(f"\n[{sev}] {code} ({len(entries)} occurrence(s))")
        for name, _, msg in entries[:10]:
            print(f"    {name}: {msg[:160]}")
        if len(entries) > 10:
            print(f"    ... and {len(entries) - 10} more")

    # ---------- Per-patient summary ----------
    print("\n\n=== PER-PATIENT SUMMARY ===")
    for name in sorted(by_patient, key=lambda n: (
        -sum(1 for s, _, _ in by_patient[n] if s == 'CRITICAL'),
        -sum(1 for s, _, _ in by_patient[n] if s == 'HIGH'),
        -len(by_patient[n]),
    )):
        sev_breakdown = defaultdict(int)
        for sev, _, _ in by_patient[name]:
            sev_breakdown[sev] += 1
        parts = []
        for sev in ('CRITICAL', 'HIGH', 'MED', 'LOW'):
            if sev_breakdown[sev]:
                parts.append(f"{sev_breakdown[sev]} {sev}")
        print(f"  {name:40s}  {', '.join(parts) if parts else 'clean'}")


if __name__ == "__main__":
    main()
