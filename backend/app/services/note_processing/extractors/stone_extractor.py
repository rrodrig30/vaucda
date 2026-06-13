"""
Stone-Related Labs Extractor

Extracts labs related to kidney stone evaluation:
- 24-hour urine tests (VA STONERISK PROFILE, plain-label panels, Litholink)
- Stone composition analysis
- Comprehensive Metabolic Panel (CMP)
- Parathyroid Hormone (PTH)
"""

import re
from typing import Optional, Tuple


# Mapping of raw lab labels (uppercase) to display labels.
# Each tuple is (display_label, category) where category is one of:
#   'ss'  - supersaturation index
#   'met' - metabolic excretion / urine chemistry
#   'env' - urine environment (pH, volume)
STONERISK_LABEL_MAP = {
    'CALCIUM OXALATE': ('CaOx Supersaturation', 'ss'),
    'CAOX SS': ('CaOx Supersaturation', 'ss'),
    'CAOX SUPERSATURATION': ('CaOx Supersaturation', 'ss'),
    'BRUSHITE': ('Brushite Supersaturation (CaPO4)', 'ss'),
    'CALCIUM PHOSPHATE': ('CaPO4 Supersaturation', 'ss'),
    'CAP SS': ('CaPO4 Supersaturation', 'ss'),
    'CAPO4 SS': ('CaPO4 Supersaturation', 'ss'),
    'SODIUM URATE': ('Sodium Urate SS', 'ss'),
    'STRUVITE': ('Struvite SS', 'ss'),
    'URIC ACID SS': ('Uric Acid SS', 'ss'),

    'CREATININE URINE': ('Creatinine (mg/day)', 'met'),
    'URINE CREATININE': ('Creatinine (mg/day)', 'met'),
    'CALCIUM URINE': ('Calcium (mg/day)', 'met'),
    'URINE CALCIUM': ('Calcium (mg/day)', 'met'),
    'OXALATE URINE': ('Oxalate (mg/day)', 'met'),
    'URINE OXALATE': ('Oxalate (mg/day)', 'met'),
    'CITRATE URINE': ('Citrate (mg/day)', 'met'),
    'URINE CITRATE': ('Citrate (mg/day)', 'met'),
    'URIC ACID URINE': ('Uric Acid (mg/day)', 'met'),
    'URINE URIC ACID': ('Uric Acid (mg/day)', 'met'),
    'MAGNESIUM URINE': ('Magnesium (mg/day)', 'met'),
    'URINE MAGNESIUM': ('Magnesium (mg/day)', 'met'),
    'SODIUM URINE': ('Sodium (mEq/day)', 'met'),
    'URINE SODIUM': ('Sodium (mEq/day)', 'met'),
    'POTASSIUM URINE': ('Potassium (mEq/day)', 'met'),
    'URINE POTASSIUM': ('Potassium (mEq/day)', 'met'),
    'PHOSPHATE URINE': ('Phosphate (mg/day)', 'met'),
    'URINE PHOSPHATE': ('Phosphate (mg/day)', 'met'),
    'PHOSPHORUS URINE': ('Phosphate (mg/day)', 'met'),
    'AMMONIUM URINE': ('Ammonium (mEq/day)', 'met'),
    'URINE AMMONIUM': ('Ammonium (mEq/day)', 'met'),
    'SULFATE URINE': ('Sulfate (mmol/day)', 'met'),
    'URINE SULFATE': ('Sulfate (mmol/day)', 'met'),
    'CHLORIDE URINE': ('Chloride (mEq/day)', 'met'),
    'URATE URINE': ('Urate (mg/day)', 'met'),
    'URINE URATE': ('Urate (mg/day)', 'met'),

    'PH URINE': ('Urine pH', 'env'),
    'URINE PH': ('Urine pH', 'env'),
    'TOTAL URINE VOLUME': ('Volume (L/day)', 'env'),
    'URINE VOLUME': ('Volume (L/day)', 'env'),
    'VOLUME': ('Volume (L/day)', 'env'),
}


def _normalize_label(raw_label: str) -> str:
    """Strip site-code suffixes like '(442)' and squeeze whitespace."""
    cleaned = re.sub(r'\s*\(\d+\)\s*', ' ', raw_label)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().upper()
    return cleaned


# Shared per-line parser for VistA stone-panel formats.
#
#   "<LABEL>(NNN)   <value> [H|L]   <unit?>   Ref: ..."
#
# Used by both the VA STONERISK PROFILE matcher (which gates on the
# 'STONERISK PROFILE(24HR UR.)(442)' header) and the bare-'Specimen: URINE,
# 24 HR' matcher (which sees the same line shapes under a different header).
# Keeping a single pattern avoids per-matcher drift.
_STONERISK_LINE_RE = re.compile(
    r'^\s*([A-Z][A-Z\s]+?)\s*\(\d+\)\s+'
    r'(\d+\.?\d*)\s*([HL])?'
    r'(?:\s+[A-Za-z/]+)?'
    r'(?:\s+\S.*)?$',
    re.IGNORECASE,
)


def _lookup_label(raw_label: str) -> Optional[Tuple[str, str]]:
    """Look up a stonerisk label in the canonical map, accepting variants."""
    normalized = _normalize_label(raw_label)
    if normalized in STONERISK_LABEL_MAP:
        return STONERISK_LABEL_MAP[normalized]
    # Try without trailing 'URINE' or with leading 'URINE'
    no_urine = re.sub(r'\bURINE\b', '', normalized).strip()
    if no_urine in STONERISK_LABEL_MAP:
        return STONERISK_LABEL_MAP[no_urine]
    return None


def extract_stone_labs(clinical_document: str) -> str:
    """
    Extract stone-related lab results from clinical documents with collection dates.

    Coverage:
    - VA STONERISK PROFILE(24HR UR.)(442) blocks (with site codes)
    - Plain-label "24-HOUR URINE METABOLIC STONE PANEL" blocks
    - Litholink (external lab) format
    - Stone composition analysis (mineral percentages)
    - PTH (Parathyroid Hormone)
    - 24-hour urine excretions (Ca, Ox, Cit, UA, Mg, Na, P, NH4, sulfate)
    - Supersaturations (CaOx, CaPO4/Brushite, Sodium Urate, Struvite, Uric Acid)
    - Urine pH and total volume
    - CMP-style stone-relevant chemistries (PTH, Calcium, Uric Acid, Phosphate, ALP)

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted stone-related lab results with dates, or "" if not found
    """
    stone_results = []

    # Track current collection date as we parse downward
    current_collection_date = None
    for line in clinical_document.split('\n'):
        date_match = re.search(
            r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
            line
        )
        if not date_match:
            date_match = re.search(
                r'Collection date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
                line
            )
        if date_match:
            current_collection_date = date_match.group(1)

    # ==========================================================================
    # 1. STONE LABS section (VA reverse format inside an existing section)
    # ==========================================================================
    stone_section_match = re.search(
        r'====+\s*STONE\s+(?:RELATED\s+)?LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if stone_section_match:
        stone_section = stone_section_match.group(1)

        for line in stone_section.split('\n'):
            line = line.strip()
            if not line:
                continue

            va_reverse_match = re.match(
                r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+'
                r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$',
                line
            )
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()
                stone_results.append(f"{test_name}: {value_ref} - {date_str}")

    # ==========================================================================
    # 2. General LABS section: pull stone-marker lines (CMP style)
    # ==========================================================================
    general_labs_section_match = re.search(
        r'====+\s*LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if general_labs_section_match:
        general_labs_section = general_labs_section_match.group(1)

        stone_markers = [
            'PTH', 'PARATHYROID', 'CALCIUM', 'URIC ACID',
            'PHOSPHORUS', 'PHOSPHATE', 'ALKALINE PHOSPHATASE',
            'MAGNESIUM',
        ]

        for line in general_labs_section.split('\n'):
            line = line.strip()
            if not line or line.startswith('Lipids:') or line.startswith('-'):
                continue

            va_reverse_match = re.match(
                r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+'
                r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$',
                line
            )
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()

                test_name_upper = test_name.upper()
                if any(marker in test_name_upper for marker in stone_markers):
                    result_str = f"{test_name}: {value_ref} - {date_str}"
                    if result_str not in stone_results:
                        stone_results.append(result_str)

    # ==========================================================================
    # 3. CMP fallback (only for legacy free-text documents WITHOUT a
    #    structured ===== LABS ===== section, since otherwise CMP values
    #    are already collected by the general lab extractor).
    # ==========================================================================
    has_structured_labs = bool(general_labs_section_match)
    if not has_structured_labs:
        # Linear-time scan instead of a backtracking regex. The previous
        # `((?:[^\n]+\n?){1,15}?)` pattern combined with the lookahead
        # caused catastrophic backtracking on large inputs that lacked a
        # terminator (PTH/ASSESSMENT:/PLAN:/=====) — measured to spin a
        # worker thread at 100% CPU for hours on a 254KB document.
        header_re = re.compile(
            r'(?:CMP|Comprehensive\s+Metabolic\s+Panel)[:\s]*$',
            re.IGNORECASE,
        )
        terminator_re = re.compile(
            r'^\s*(?:PTH|ASSESSMENT:|PLAN:|====+)',
            re.IGNORECASE,
        )
        cmp_results = ""
        for header_match in header_re.finditer(clinical_document):
            after = clinical_document[header_match.end():]
            # Take at most the next 15 non-empty lines, stopping at a
            # known terminator. Splitting line-wise is O(n).
            following_lines = after.split('\n', 16)[1:16]
            body_lines = []
            for line in following_lines:
                if terminator_re.match(line):
                    break
                body_lines.append(line)
            collected = '\n'.join(body_lines).strip()
            if collected:
                cmp_results = re.sub(r' +', ' ', collected)
                cmp_results = re.sub(r'\n{3,}', '\n', cmp_results)
                break  # use first match only

        if cmp_results:
            header = "Comprehensive Metabolic Panel"
            if current_collection_date:
                header += f" ({current_collection_date})"
            stone_results.append(f"{header}:\n{cmp_results}")

    pth_pattern = (
        r'(?:PTH|Parathyroid\s+Hormone)[:\s]+(\d+\.?\d*)\s*'
        r'(pg/mL|pg/ml)?(?:\s*\(?'
        r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\)?)?'
    )

    pth_seen = set()
    for match in re.finditer(pth_pattern, clinical_document, re.IGNORECASE):
        value = match.group(1).strip()
        unit = match.group(2).strip() if match.group(2) else "pg/mL"
        inline_date = match.group(3).strip() if match.group(3) else ""
        date = inline_date if inline_date else current_collection_date

        result_str = f"PTH: {value} {unit}"
        if date:
            result_str += f" ({date})"

        if result_str not in pth_seen:
            stone_results.append(result_str)
            pth_seen.add(result_str)

    # ==========================================================================
    # 4. VA STONERISK PROFILE (24HR UR.) — site-code format
    # ==========================================================================
    va_profile = extract_va_stonerisk_profile(clinical_document)
    if va_profile:
        stone_results.append(va_profile)

    # ==========================================================================
    # 4b. VistA 'Specimen: URINE, 24 HR' bare-header format
    # Same per-line shape as the STONERISK PROFILE, different enclosing header.
    # Only run when the STONERISK PROFILE matcher did not fire, otherwise the
    # same panel would render twice.
    # ==========================================================================
    if not va_profile:
        specimen_panel = extract_specimen_24hr_urine_panel(clinical_document)
        if specimen_panel:
            stone_results.append(specimen_panel)

    # ==========================================================================
    # 5. Plain-label 24-hour urine metabolic stone panel
    # ==========================================================================
    plain_panel = extract_plain_label_stone_panel(clinical_document)
    if plain_panel:
        stone_results.append(plain_panel)

    # ==========================================================================
    # 6. Litholink (external lab)
    # ==========================================================================
    litholink_results = extract_litholink_format(clinical_document)
    if litholink_results:
        stone_results.append(litholink_results)

    # ==========================================================================
    # 7. Stone composition analysis (header-style: STONE ANALYSIS:, etc.)
    # ==========================================================================
    composition = extract_stone_composition(clinical_document)
    if composition:
        stone_results.append(composition)

    # ==========================================================================
    # 7b. VistA 'Specimen: CALCULUS' stone composition block
    # ==========================================================================
    calculus = extract_specimen_calculus_composition(clinical_document)
    if calculus:
        stone_results.append(calculus)

    if not stone_results:
        return ""

    return '\n\n'.join(stone_results)


def _format_stonerisk_block(
    key_values: dict,
    date: str,
    header_prefix: str = "24-Hour Urine Stone Risk Analysis",
) -> str:
    """Render a parsed stonerisk dict into the canonical Stone Labs block."""
    if not key_values:
        return ""

    header = header_prefix
    if date:
        header += f" ({date})"
    header += ":"

    supersaturation, metabolic, environment = [], [], []
    for label, payload in key_values.items():
        category = payload.get('category', 'met')
        value = payload['value']
        line = f"  {label}: {value}"
        if category == 'ss':
            supersaturation.append(line)
        elif category == 'env':
            environment.append(line)
        else:
            metabolic.append(line)

    parts = [header]
    if supersaturation:
        parts.append("Supersaturation:")
        parts.extend(supersaturation)
    if metabolic:
        parts.append("Metabolic:")
        parts.extend(metabolic)
    if environment:
        parts.append("Environment:")
        parts.extend(environment)
    return '\n'.join(parts)


def extract_va_stonerisk_profile(clinical_document: str) -> str:
    """
    Extract VA STONERISK PROFILE (24HR UR.) format with (NNN) site codes.

    Format:
        STONERISK PROFILE(24HR UR.)(442)
             CALCIUM OXALATE(442)     0.85   ...
                   BRUSHITE (442)     2.62 H ...
        ...
        TOTAL URINE VOLUME(442)     1.64 L  L/day  ...
    """
    stonerisk_pattern = (
        r'STONERISK\s+PROFILE\s*\(24HR\s+UR\.?\)\s*\(\d+\)\s*\n'
        r'(.*?)(?=\n\s*(?:Comment:|Report\s+Released|Provider:|=====|$))'
    )

    match = re.search(
        stonerisk_pattern,
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""

    profile_block = match.group(1).strip()
    if not profile_block:
        return ""

    # Locate collection date in nearby context
    date = ""
    pre_context = clinical_document[:match.start()]
    date_match = re.search(
        r'Specimen\s+Collection\s+Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
        pre_context,
        re.IGNORECASE
    )
    if not date_match:
        scan_window = clinical_document[:match.start() + 500]
        date_match = re.search(
            r'Report\s+Released\s+Date/Time:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
            scan_window,
            re.IGNORECASE
        )
    if date_match:
        date = date_match.group(1)

    key_values = {}
    for line in profile_block.split('\n'):
        m = _STONERISK_LINE_RE.match(line.rstrip())
        if not m:
            continue
        raw_label = m.group(1).strip()
        value = m.group(2)
        flag = m.group(3) or ""
        lookup = _lookup_label(raw_label)
        if not lookup:
            continue
        display_label, category = lookup
        formatted_value = f"{value} ({flag})" if flag else value
        key_values[display_label] = {'value': formatted_value, 'category': category}

    return _format_stonerisk_block(key_values, date)


def extract_specimen_24hr_urine_panel(clinical_document: str) -> str:
    """
    Extract VistA-style 24-hour urine metabolic stone panel introduced by a
    bare 'Specimen: URINE, 24 HR' header (no 'STONERISK PROFILE' header).

    Real-world VistA dumps frequently use:

        Specimen: URINE, 24 HR..    QST 25 1205
           Specimen Collection Date: Feb 14, 2025@08:57
              Test name            Result   units    Ref.   range   Site Code
        CALCIUM OXALATE(442)        0.86             Ref: SEE BELOW [11120]
        BRUSHITE (442)              0.97             Ref: SEE BELOW [11120]
        ...
        AMMONIUM URINE (442)         29  mEq/day     14 - 62        [11120]
        Comment: ...

    The per-line shape is identical to the STONERISK PROFILE format; only the
    enclosing header differs. We reuse ``_STONERISK_LINE_RE`` so the two
    matchers cannot drift apart.
    """
    header_re = re.compile(
        r'^[ \t]*Specimen:\s*URINE,\s*24\s*HR\b.*$',
        re.IGNORECASE,
    )
    # Sentinels that mean "the 24-hr-urine block is over."
    sentinel_re = re.compile(
        r'^[ \t]*(?:'
        r'Comment:'
        r'|Report\s+Released'
        r'|Provider:'
        r'|Specimen:\s*(?!URINE,\s*24\s*HR)'  # another, different specimen
        r'|={5,}'
        r'|IMAGING\b'
        r'|MEDICATIONS\b'
        r'|ALLERGIES\b'
        r'|ASSESSMENT:'
        r'|PLAN:'
        r'|PATHOLOGY\b'
        r')',
        re.IGNORECASE,
    )
    date_re = re.compile(
        r'Specimen\s+Collection\s+Date:\s*'
        r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
        re.IGNORECASE,
    )

    lines = clinical_document.split('\n')
    rendered_blocks = []
    seen_label_sets = []  # for dedup across multiple headers
    i = 0
    while i < len(lines):
        if not header_re.match(lines[i]):
            i += 1
            continue

        # Walk forward; cap at 80 lines so a malformed dump can't run away.
        date = ""
        key_values = {}
        j = i + 1
        scanned = 0
        while j < len(lines) and scanned < 80:
            current = lines[j].rstrip()
            if sentinel_re.match(current):
                break
            scanned += 1
            j += 1

            if not current.strip():
                # Tolerate one blank line, then break if the next non-blank
                # line is not a stone-panel value (avoids gobbling unrelated
                # follow-on sections separated by a blank line).
                # Look ahead one non-blank line:
                k = j
                while k < len(lines) and not lines[k].strip():
                    k += 1
                if k >= len(lines) or sentinel_re.match(lines[k].rstrip()) \
                        or not _STONERISK_LINE_RE.match(lines[k].rstrip()):
                    break
                continue

            # Capture date once
            if not date:
                dm = date_re.search(current)
                if dm:
                    date = dm.group(1)

            line_m = _STONERISK_LINE_RE.match(current)
            if not line_m:
                continue
            raw_label = line_m.group(1).strip()
            value = line_m.group(2)
            flag = line_m.group(3) or ""
            lookup = _lookup_label(raw_label)
            if not lookup:
                continue
            display_label, category = lookup
            formatted_value = f"{value} ({flag})" if flag else value
            key_values[display_label] = {
                'value': formatted_value,
                'category': category,
            }

        if key_values:
            label_set = frozenset(key_values.keys())
            # Dedup: if a previous header rendered the same label set on the
            # same date, skip. (Identical re-emission of one report.)
            if not any(label_set == prev for prev in seen_label_sets):
                block = _format_stonerisk_block(key_values, date)
                if block:
                    rendered_blocks.append(block)
                    seen_label_sets.append(label_set)
        i = j

    return '\n\n'.join(rendered_blocks)


def extract_plain_label_stone_panel(clinical_document: str) -> str:
    """
    Extract plain-label "24-HOUR URINE METABOLIC STONE PANEL" / similar headers.

    Format:
        24-HOUR URINE METABOLIC STONE PANEL (6/21/2025):
        CALCIUM OXALATE: 1.29
        BRUSHITE: 0.75
        SODIUM URATE: 1.11
        STRUVITE: 0.68
        CREATININE URINE: 927 mg/day (600-1800)
        ...
        TOTAL URINE VOLUME: 1.43 L L/day (>2.00)
        ASSESSMENT: Hypocitraturia, ...

    Also matches: "24-hour urine stone risk profile (DATE):"
                  "24-Hour Urine (DATE):"
                  "STONE RISK PROFILE (DATE):"
    """
    header_re = re.compile(
        r'^\s*(?:'
        r'24[\s\-]?(?:HOUR|HR)\s+URINE'
        r'(?:\s+(?:METABOLIC\s+)?STONE(?:\s+RISK)?(?:\s+PROFILE|\s+PANEL)?)?'
        r'|STONE\s+RISK\s+PROFILE'
        r')'
        r'\s*[:\-(]?\s*'
        r'\(?\s*('
        r'(?:[A-Za-z]{3}\s+\d{1,2},\s+\d{4})'
        r'|(?:\d{1,2}/\d{1,2}/\d{2,4})'
        r')?\s*\)?\s*:?\s*$',
        re.IGNORECASE
    )

    lines = clinical_document.split('\n')
    blocks = []
    i = 0
    while i < len(lines):
        m = header_re.match(lines[i])
        if not m:
            i += 1
            continue
        date = m.group(1) or ""
        # Collect contiguous label: value lines until blank line / next section
        body_lines = []
        j = i + 1
        while j < len(lines):
            current = lines[j].rstrip()
            if not current.strip():
                break
            # Stop at next section marker
            if re.match(r'^={5,}', current) or re.match(
                r'^\s*(?:IMAGING|MEDICATIONS|ALLERGIES|ASSESSMENT|PLAN|'
                r'PHYSICAL\s+EXAM|ROS)\b',
                current,
                re.IGNORECASE
            ):
                break
            # Stop at another panel header
            if header_re.match(current):
                break
            body_lines.append(current)
            j += 1
        if body_lines:
            blocks.append((date, body_lines))
        i = j

    if not blocks:
        return ""

    rendered_blocks = []
    for date, body_lines in blocks:
        key_values = {}
        for line in body_lines:
            # "LABEL: value units (ref)"  — split on first colon
            m = re.match(
                r'^\s*([A-Za-z][A-Za-z0-9\s/]+?)\s*:\s*'
                r'([\-\d\.]+)\s*([HL])?\s*(.*)$',
                line
            )
            if not m:
                continue
            raw_label = m.group(1).strip()
            # Skip "ASSESSMENT:" trailers in the panel
            if _normalize_label(raw_label) == 'ASSESSMENT':
                continue
            value = m.group(2)
            flag = m.group(3) or ""
            tail = m.group(4).strip()
            lookup = _lookup_label(raw_label)
            if not lookup:
                continue
            display_label, category = lookup
            # Preserve unit / ref from the tail when present
            value_str = value
            if flag:
                value_str += f" ({flag})"
            if tail:
                value_str += f" {tail}"
            key_values[display_label] = {
                'value': value_str.strip(),
                'category': category,
            }

        block = _format_stonerisk_block(
            key_values,
            date,
            header_prefix="24-Hour Urine Metabolic Stone Panel",
        )
        if block:
            rendered_blocks.append(block)

    return '\n\n'.join(rendered_blocks)


def extract_litholink_format(clinical_document: str) -> str:
    """
    Extract Litholink 24-hour urine format (external lab).

    Format:
        Litholink done on the outside: 2/17/25
        Vol: 3.53
        CaOX ss: 2.9
        U Ca: 242
        U Ox: 28
        U Citrate: 789
        24 hr pH: 6.403
    """
    # Linear-time scan rather than a backtracking regex. The previous
    # `((?:[^\n]+\n?){1,12}?)` body capture was vulnerable to catastrophic
    # backtracking on large inputs lacking the lookahead terminator.
    header_re = re.compile(
        r'Litholink\s+(?:done\s+)?(?:on\s+the\s+)?(?:outside)?:?\s*'
        r'(\d{1,2}/\d{1,2}/\d{2,4})?\s*$',
        re.IGNORECASE,
    )
    terminator_re = re.compile(
        r'^\s*(?:===|LABS\b|IMAGING\b|MEDICATIONS\b)',
        re.IGNORECASE,
    )

    date = ""
    values_block = ""
    for header_match in header_re.finditer(clinical_document):
        date = header_match.group(1).strip() if header_match.group(1) else ""
        after = clinical_document[header_match.end():]
        following_lines = after.split('\n', 13)[1:13]
        body_lines = []
        for line in following_lines:
            if terminator_re.match(line):
                break
            body_lines.append(line)
        candidate = '\n'.join(body_lines).strip()
        if candidate:
            values_block = candidate
            break

    if not values_block:
        return ""

    key_values = {}
    litho_patterns = [
        (r'Vol:\s*(\d+\.?\d*)', 'Volume (L)', 'env'),
        (r'CaOX\s+ss:\s*(\d+\.?\d*)', 'CaOx SS', 'ss'),
        (r'CaP\s+ss:\s*(\d+\.?\d*)', 'CaPO4 SS', 'ss'),
        (r'U\s*Ca:\s*(\d+)', 'Calcium (mg/day)', 'met'),
        (r'U\s*Ox:\s*(\d+)', 'Oxalate (mg/day)', 'met'),
        (r'U\s*Citrate:\s*(\d+)', 'Citrate (mg/day)', 'met'),
        (r'U\s*UA:\s*(\d+\.?\d*)', 'Uric Acid (mg/day)', 'met'),
        (r'U\s*Mg:\s*(\d+\.?\d*)', 'Magnesium (mg/day)', 'met'),
        (r'U\s*Na:\s*(\d+\.?\d*)', 'Sodium (mEq/day)', 'met'),
        (r'U\s*P:\s*(\d+\.?\d*)', 'Phosphate (mg/day)', 'met'),
        (r'U\s*NH4:\s*(\d+\.?\d*)', 'Ammonium (mEq/day)', 'met'),
        (r'24\s*hr\s*pH:\s*(\d+\.?\d*)', 'Urine pH', 'env'),
    ]

    for pattern, label, category in litho_patterns:
        val_match = re.search(pattern, values_block, re.IGNORECASE)
        if val_match:
            key_values[label] = {'value': val_match.group(1), 'category': category}

    if not key_values:
        return ""

    return _format_stonerisk_block(
        key_values,
        date,
        header_prefix="Litholink 24-Hour Urine",
    )


# Maps raw VistA calculus-analysis labels to their clinical names.
# 'cls' tags the type:
#   'phys'  - physical descriptor (color, size, weight)
#   'comp'  - mineral/component composition
_CALCULUS_LABEL_MAP = {
    'COLOR-CALCULI':                  ('Color', 'phys'),
    'SIZE-CALCULI':                   ('Size', 'phys'),
    'WEIGHT-CALCULI':                 ('Weight', 'phys'),
    'CA OXALATE DIHYDATE-CALCULI':    ('Calcium Oxalate Dihydrate', 'comp'),
    'CA OXALATE DIHYDRATE-CALCULI':   ('Calcium Oxalate Dihydrate', 'comp'),
    'CA OXALATE MONOHYDR.-CALCULI':   ('Calcium Oxalate Monohydrate', 'comp'),
    'CA OXALATE MONOHYDRATE-CALCULI': ('Calcium Oxalate Monohydrate', 'comp'),
    'CALCIUM PHOSPHATE-CALCULI':      ('Calcium Phosphate', 'comp'),
    'SODIUM-ACID URATE':              ('Sodium Acid Urate', 'comp'),
    'AMMONIUM ACID-URATE':            ('Ammonium Acid Urate', 'comp'),
    'CYSTINE-CALCULI':                ('Cystine', 'comp'),
    'CELLULAR MATERIAL-CACULI':       ('Cellular Material', 'comp'),  # source typo
    'CELLULAR MATERIAL-CALCULI':      ('Cellular Material', 'comp'),
    'URIC ACID DIHYDRATE':            ('Uric Acid Dihydrate', 'comp'),
    'URIC ACID-CALCULI':              ('Uric Acid', 'comp'),
    'HYDROXYAPATITE-CALCULI':         ('Hydroxyapatite', 'comp'),
    'CAHPO4 (BRUSHITE)':              ('Brushite (CaHPO4)', 'comp'),
}


def extract_specimen_calculus_composition(clinical_document: str) -> str:
    """
    Extract VistA 'Specimen: CALCULUS' stone analysis blocks.

    Real-world VistA dumps use:

        Specimen: CALCULUS.         SFB 21 29360
           Specimen Collection Date: Oct 08, 2021@08:00
             Test name             Result   units      Ref. range   Site Code
        COLOR-CALCULI               Brown                            [11401]
        SIZE-CALCULI                  3x2  mm                        [11401]
        WEIGHT-CALCULI                 70  mg                        [11401]
        CA OXALATE DIHYDATE-CALCULI    20  %                         [11401]
        CA OXALATE MONOHYDR.-CALCULI   80  %                         [11401]
        CALCIUM PHOSPHATE-CALCULI     canc                           [11401]
        ...
        Comment: ...

    Lines with a 'canc' (cancelled / not detected) result are omitted from
    the rendered output - listing them adds noise without clinical signal.
    The 'PLEASE NOTE-CALCULI' narrative anchor is also skipped.
    """
    header_re = re.compile(
        r'^[ \t]*Specimen:\s*CALCULUS\b.*$',
        re.IGNORECASE,
    )
    # Line: LABEL  (optional spaces)  value  (optional unit / flag / ref)  [NNNNN]
    line_re = re.compile(
        r'^\s*([A-Z][A-Z0-9\s/\.\-\(\)]+?)\s{2,}'
        r'([A-Za-z0-9./\-]+)'
        r'(?:\s+([HL]))?'
        r'(?:\s+\S.*?)?'
        r'\s*\[\d+\]\s*$',
        re.IGNORECASE,
    )
    date_re = re.compile(
        r'Specimen\s+Collection\s+Date:\s*'
        r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
        re.IGNORECASE,
    )
    sentinel_re = re.compile(
        r'^[ \t]*(?:'
        r'Comment:'
        r'|={5,}'
        r'|Report\s+Released'
        r'|Provider:'
        r'|Reporting\s+Lab:'
        r'|Specimen:'  # next specimen block
        r')',
        re.IGNORECASE,
    )

    lines = clinical_document.split('\n')
    rendered_blocks = []
    seen_blocks = set()
    i = 0
    while i < len(lines):
        if not header_re.match(lines[i]):
            i += 1
            continue

        date = ""
        physical = []   # ordered: color, size, weight
        composition = []  # detected components only
        j = i + 1
        scanned = 0
        while j < len(lines) and scanned < 60:
            current = lines[j].rstrip()
            # Sentinel terminates the block, but ONLY when we have already
            # seen at least one composition line (otherwise the next
            # 'Specimen:' header could be the same line we're walking past
            # in a degenerate dump). In practice the header itself is at i,
            # so 'Specimen:' here means the *next* block.
            if scanned > 0 and sentinel_re.match(current):
                break
            scanned += 1
            j += 1
            if not current.strip():
                continue

            # Capture date once.
            if not date:
                dm = date_re.search(current)
                if dm:
                    date = dm.group(1)
                    continue

            m = line_re.match(current)
            if not m:
                continue
            raw_label = re.sub(r'\s+', ' ', m.group(1)).strip().upper()
            value = m.group(2).strip()
            # Skip the narrative comment anchor.
            if raw_label.startswith('PLEASE NOTE'):
                continue
            mapping = _CALCULUS_LABEL_MAP.get(raw_label)
            if not mapping:
                continue
            display_label, cls = mapping
            # Skip components reported as 'canc' (cancelled / not detected).
            if cls == 'comp' and value.lower() in {'canc', 'cancelled', 'cancel'}:
                continue
            # Attach unit for composition % when not already present in value.
            if cls == 'comp' and value.replace('.', '', 1).isdigit():
                display_value = f"{value}%"
            elif cls == 'phys' and display_label == 'Weight' and value.isdigit():
                display_value = f"{value} mg"
            elif cls == 'phys' and display_label == 'Size' and re.match(r'^\d', value):
                display_value = f"{value} mm"
            else:
                display_value = value

            entry = f"  {display_label}: {display_value}"
            if cls == 'phys':
                physical.append(entry)
            else:
                composition.append(entry)

        if not (physical or composition):
            i = j
            continue

        header = "Stone Composition (Calculus Analysis)"
        if date:
            header += f" ({date})"
        header += ":"

        parts = [header]
        if physical:
            parts.append("Physical:")
            parts.extend(physical)
        if composition:
            parts.append("Composition:")
            parts.extend(composition)
        block = '\n'.join(parts)

        # Dedup identical blocks (same date + same payload).
        key = (date, tuple(physical), tuple(composition))
        if key not in seen_blocks:
            rendered_blocks.append(block)
            seen_blocks.add(key)
        i = j

    return '\n\n'.join(rendered_blocks)


def extract_stone_composition(clinical_document: str) -> str:
    """
    Extract stone composition analysis results.

    Recognizes labeled sections like:
        STONE ANALYSIS:
        STONE COMPOSITION:
        STONE ANALYSIS RESULT:
        Calculus Analysis:
        STONE ANALYSIS - LABORATORY:

    And captures composition lines like:
        Calcium Oxalate Monohydrate: 70%
        Calcium Oxalate: 100%
        Uric Acid: 50%
        Carbonate Apatite: 30%
        Cystine: trace

    Also captures inline references such as:
        "passed a calcium oxalate stone"
    only when present in a labeled stone analysis context.
    """
    headers = [
        r'STONE\s+ANALYSIS(?:\s+RESULT)?',
        r'STONE\s+COMPOSITION',
        r'CALCULUS\s+ANALYSIS',
        r'STONE\s+ANALYSIS\s*[-–]\s*LABORATORY',
    ]
    header_re = re.compile(
        r'^\s*(?:' + '|'.join(headers) + r')\s*[:\-]?\s*'
        r'(?:\(([^)]+)\))?\s*[:\-]?\s*$',
        re.IGNORECASE
    )

    lines = clinical_document.split('\n')
    blocks = []
    i = 0
    while i < len(lines):
        m = header_re.match(lines[i])
        if not m:
            i += 1
            continue
        date = m.group(1) or ""
        body = []
        j = i + 1
        while j < len(lines):
            current = lines[j].rstrip()
            if not current.strip():
                break
            if re.match(r'^={5,}', current):
                break
            if header_re.match(current):
                break
            if re.match(
                r'^\s*(?:IMAGING|MEDICATIONS|ALLERGIES|ASSESSMENT|PLAN|'
                r'PHYSICAL\s+EXAM|ROS|PATHOLOGY|LABS)\b',
                current,
                re.IGNORECASE,
            ):
                break
            body.append(current)
            j += 1
        if body:
            blocks.append((date, body))
        i = j

    if not blocks:
        return ""

    component_re = re.compile(
        r'^\s*(?:[-•*]\s*)?'
        r'([A-Za-z][A-Za-z\s\-\(\)]+?)'
        r'\s*[:\-]\s*'
        r'(\d+\.?\d*\s*%|\d+\.?\d*|trace|present|TRACE|PRESENT|'
        r'predominant|PREDOMINANT)'
        r'\s*$',
        re.IGNORECASE
    )

    rendered = []
    for date, body in blocks:
        components = []
        free_text = []
        for line in body:
            m = component_re.match(line)
            if m:
                name = re.sub(r'\s+', ' ', m.group(1)).strip()
                value = m.group(2).strip()
                components.append(f"  {name}: {value}")
            else:
                stripped = line.strip()
                if stripped:
                    free_text.append(f"  {stripped}")
        if not components and not free_text:
            continue
        header = "Stone Composition"
        if date:
            header += f" ({date})"
        header += ":"
        out = [header]
        out.extend(components if components else free_text)
        rendered.append('\n'.join(out))

    return '\n\n'.join(rendered)
