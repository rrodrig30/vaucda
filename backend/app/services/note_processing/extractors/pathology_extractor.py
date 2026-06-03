"""
Pathology Report Extractor

Extracts pathology reports from SURGICAL PATHOLOGY format.
"""

import re


def extract_prostate_biopsy(clinical_document: str) -> str:
    """
    Extract prostate biopsy results with adenocarcinoma/Gleason scores.

    This handles the VA MICROSCOPIC EXAM/DIAGNOSIS format:
    ** MICROSCOPIC EXAM/DIAGNOSIS:
      DIAGNOSIS:
      A. PROSTATE, RIGHT MEDIAL APEX, BIOPSY:
        - PROSTATIC ADENOCARCINOMA, GLEASON SCORE 3+3=6/10, GRADE GROUP 1,
          INVOLVING 5% OF TISSUE.

    Args:
        clinical_document: Full clinical document

    Returns:
        Summarized prostate biopsy results, or "" if not found
    """
    all_biopsies = []

    # Find all biopsy sections with dates
    # Pattern: "DATE:\n** MICROSCOPIC EXAM/DIAGNOSIS:" or "Current Path Report:\nDATE:"
    biopsy_sections = []

    # Pattern 1: "M/YYYY:" or "MM/DD/YY:" followed by MICROSCOPIC EXAM
    # Allows content between MICROSCOPIC EXAM and DIAGNOSIS (e.g., MODIFIED REPORT headers)
    date_blocks = re.finditer(
        r'(?:Current\s+Path\s+Report:?\s*\n)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}/\d{4}):\s*\n\s*\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n(?:(?!\s*DIAGNOSIS)[^\n]*\n)*\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:Previous\s+Path|Current\s+Path|Comment:|Note:|\d{1,2}/\d{1,4}:|\*{2}\s*MICROSCOPIC|\s*/es/|Signed|={10,}|$))',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    for match in date_blocks:
        date_str = match.group(1)
        diagnosis_block = match.group(2)
        biopsy_sections.append((date_str, diagnosis_block))

    # Pattern 2: "Previous Path Reports:" sections
    prev_reports = re.finditer(
        r'Previous\s+Path\s+Reports?:?\s*\n(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}/\d{4}):\s*\n\s*\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n(?:(?!\s*DIAGNOSIS)[^\n]*\n)*\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:Comment:|Note:|\d{1,2}/\d{1,4}:|\*{2}\s*MICROSCOPIC|\s*/es/|Signed|={10,}|$))',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    for match in prev_reports:
        date_str = match.group(1)
        diagnosis_block = match.group(2)
        biopsy_sections.append((date_str, diagnosis_block))

    # Pattern 3: FLAT format used by VA "PATHOLOGY RESULTS:" sections, e.g.
    #
    #   2/21/2024 Prostate Biopsy:
    #   A. PROSTATE, TARGET AREA #1, BIOPSY:
    #     - PROSTATIC ADENOCARCINOMA, GLEASON SCORE 3+3 = 6 (GRADE GROUP 1), ...
    #
    #   8/2017 TRUS Bx:
    #   A. PROSTATE, RIGHT, BIOPSY:
    #     -PROSTATIC ADENOCARCINOMA, GLEASON'S GRADE 3 + 3 = 6/10, ...
    #
    # These have NO "MICROSCOPIC EXAM/DIAGNOSIS:" header — Patterns 1/2
    # both miss them, which used to push extraction into the fallback path.
    # The fallback then borrowed a date from the closest preceding
    # "Specimen Collection Date" line — which is also used by PSA serum
    # draw reports — so a post-radiation PSA draw's date got pinned onto
    # an old diagnostic biopsy, making the LLM think a fresh biopsy had
    # just been done. Capturing the flat format here preserves the real
    # biopsy date and short-circuits the ambiguous fallback for these
    # cases.
    flat_pattern = re.compile(
        r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}/\d{4})\s+'
        r'(?:Prostate\s+)?(?:Biopsy|Bx|TRUS\s*Bx)\s*:?\s*\n'
        r'(.*?)'
        r'(?=\n\s*(?:'
        r'(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}/\d{4})\s+'
        r'(?:Prostate\s+)?(?:Biopsy|Bx|TRUS)|'
        r'\*{0,2}\s*MICROSCOPIC|'
        r'MEDICATIONS:|ALLERGIES:|PSA\s+History|'
        r'={10,}|/es/|Signed\s+by|'
        r'PATHOLOGY\s+RESULTS:'
        r')|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for m in flat_pattern.finditer(clinical_document):
        date_str = m.group(1)
        body = m.group(2)
        # Body must contain prostate-biopsy cores; otherwise this matched
        # something else (e.g. a TRUS-guided injection note). Require the
        # lettered "A. PROSTATE, ..., BIOPSY:" core marker that the
        # downstream parser at line 128 actually consumes.
        if not re.search(r'\b[A-N]\.\s*PROSTATE\b[^\n]*\bBIOPS', body, re.IGNORECASE):
            continue
        # Avoid trivially short matches (regex can pick up label-only
        # mentions if the body is empty/sparse).
        if len(body) < 30:
            continue
        biopsy_sections.append((date_str, body))

    # Fallback: Look for ALL MICROSCOPIC EXAM/DIAGNOSIS sections (not just first)
    # Handles MODIFIED REPORT headers between MICROSCOPIC EXAM and DIAGNOSIS
    # Does NOT stop at Comment: to capture full MODIFIED REPORT with amended DIAGNOSIS blocks
    if not biopsy_sections:
        pattern = r'\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n(?:(?!\s*DIAGNOSIS)[^\n]*\n)*\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:\*{2}\s*MICROSCOPIC|\s*/es/|Signed|Performing Laboratory|Previous\s+Path|={10,}|$))'
        for match in re.finditer(pattern, clinical_document, re.IGNORECASE | re.DOTALL):
            # Try multiple date sources in priority order. The previous
            # implementation jumped straight to "Specimen Collection Date"
            # which is shared by PSA serum lab reports — so a post-treatment
            # PSA draw's date would get pinned onto an old diagnostic biopsy,
            # making the LLM think a fresh biopsy had just been done. The
            # ordering below now prefers signals that are unambiguously
            # biopsy-attached.
            date = ""
            preceding = clinical_document[:match.start()]

            # 0. NEW: Date attached to a Biopsy/Bx/TRUS marker in the ~600
            # chars immediately preceding the MICROSCOPIC EXAM block. This
            # catches headers like "2/21/2024 Prostate Biopsy:" or
            # "8/2017 TRUS Bx:" that sit right above the cores.
            local_window = preceding[-600:] if len(preceding) > 600 else preceding
            biopsy_date_matches = list(re.finditer(
                r'(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4})\s+'
                r'(?:Prostate\s+)?(?:Biopsy|Bx|TRUS\s*Bx)',
                local_window,
                re.IGNORECASE,
            ))
            if biopsy_date_matches:
                date = biopsy_date_matches[-1].group(1)

            # 1. VA Specimen Collection Date — BUT only within the SAME
            # pathology report block. We find the nearest preceding
            # report-boundary marker (SURGICAL PATHOLOGY / STANDARD FORM
            # 515 / Performing Laboratory / Reporting Lab) and only search
            # the slice after it. Without this scope limit, the closest
            # preceding Specimen Collection Date is often from an
            # intervening PSA serum draw, not the biopsy itself.
            if not date:
                boundary_match = None
                for bm in re.finditer(
                    r'(?:SURGICAL\s+PATHOLOGY\s+REPORT|STANDARD\s+FORM\s+515|'
                    r'Performing\s+Lab(?:oratory)?[:\s]|'
                    r'Reporting\s+Lab(?:oratory)?[:\s])',
                    preceding,
                    re.IGNORECASE,
                ):
                    boundary_match = bm
                if boundary_match:
                    scoped = preceding[boundary_match.start():]
                else:
                    # Conservative fallback window if no report boundary
                    # marker is present in the preceding text.
                    scoped = preceding[-1500:] if len(preceding) > 1500 else preceding
                spec_dates = list(re.finditer(
                    r'Specimen\s+Collection\s+Date[:\s]+'
                    r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
                    scoped,
                    re.IGNORECASE,
                ))
                if spec_dates:
                    date = spec_dates[-1].group(1)

            # 2. Numeric date prefix (M/D, M/D/YY, M/YYYY) — legacy format
            if not date:
                date_match = re.search(
                    r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}/\d{4}):\s*$',
                    preceding, re.MULTILINE,
                )
                if date_match:
                    date = date_match.group(1)
            # 3. "Date Reported:" or "Report Released" lines (also scoped
            # to same report when possible — same rationale as Strategy 1).
            if not date:
                rep_scope = scoped if 'scoped' in locals() else preceding
                rep_dates = list(re.finditer(
                    r'(?:Date\s+Reported|Report\s+Released\s+Date(?:/Time)?)[:\s]+'
                    r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
                    rep_scope,
                    re.IGNORECASE,
                ))
                if rep_dates:
                    date = rep_dates[-1].group(1)
            biopsy_sections.append((date, match.group(1)))

    for date_str, diagnosis_block in biopsy_sections:
        # Tightened filter: must contain BOTH a prostate-tissue marker
        # AND a biopsy/core marker. Previously a single "prostate" word
        # could let a non-prostate biopsy match (e.g. a penile-plaque
        # biopsy report that mentions "prostate" in passing patient
        # history). This led to a phantom "prostate biopsy" appearing
        # in HPI for a patient with no actual biopsy.
        has_prostate_tissue = bool(re.search(
            r'\b(?:prostate|adenocarcinoma|gleason|grade\s+group|GG\s*\d|'
            r'prostatic\s+adenocarcinoma|HGPIN|ASAP|atypical\s+small\s+acinar)\b',
            diagnosis_block,
            re.IGNORECASE,
        ))
        has_biopsy_proc = bool(re.search(
            r'\b(?:biops(?:y|ies)|core\s+(?:needle\s+)?biops|TRUS\s*[-/]?\s*BX|'
            r'prostatectomy|TURP)\b',
            diagnosis_block,
            re.IGNORECASE,
        ))
        if not (has_prostate_tissue and has_biopsy_proc):
            continue

        # Parse the individual biopsy cores
        core_results = []

        # Pattern for individual core results - handles multiple VA formats:
        # Format 1: "A. PROSTATE, RIGHT MEDIAL APEX, BIOPSY:" (standard)
        # Format 2: "A. PROSTATE GLAND, RIGHT, CORE NEEDLE BIOPSIES:" (older VA format)
        core_pattern = r'([A-L])\.\s*PROSTATE(?:\s+GLAND)?[,\s]+(.+?),\s*(?:CORE\s+(?:NEEDLE\s+)?)?BIOPS(?:Y|IES)[;\s:]*\n?\s*[-•]?\s*(.+?)(?=\n\s*[A-L]\.\s*PROSTATE|\n\s*(?:COMMENT|Comment)|\n\s*$|$)'

        for core_match in re.finditer(core_pattern, diagnosis_block, re.IGNORECASE | re.DOTALL):
            location = core_match.group(2).strip().rstrip(',').lower()
            finding_block = core_match.group(3).strip()

            # Clean up multi-line findings - collapse whitespace but preserve sentence structure
            finding_block = re.sub(r'\n\s+', ' ', finding_block)
            finding_block = re.sub(r'\s+', ' ', finding_block)

            # Parse the finding
            if re.search(r'NEGATIVE FOR MALIGNANCY|NO EVIDENCE OF MALIGNANCY', finding_block, re.IGNORECASE):
                # Check for additional findings like ATROPHY
                extras = []
                if 'ATROPHY' in finding_block.upper():
                    extras.append("atrophy")
                neg_text = "Negative for malignancy"
                if extras:
                    neg_text += f" ({', '.join(extras)})"
                core_results.append(f"- {location.title()}: {neg_text}")
            elif 'FOCAL ATYPICAL SMALL ACINAR PROLIFERATION' in finding_block.upper() or 'ASAP' in finding_block.upper():
                core_results.append(f"- {location.title()}: Focal atypical small acinar proliferation")
            elif 'ADENOCARCINOMA' in finding_block.upper():
                # Extract Gleason/Grade Group from multiple VA formats
                gleason = ""
                grade_group = ""

                # Format 1: "GLEASON GRADE GROUP 2 (3+4)"
                grade_group_match = re.search(r"GLEASON'?S?\s+GRADE\s+GROUP\s+(\d+)\s*\((\d)\s*\+\s*(\d)\)", finding_block, re.IGNORECASE)
                # Format 2: "GLEASON SCORE 3+4 (GRADE GROUP 2)"
                gleason_score_match = re.search(r"GLEASON'?S?\s+SCORE\s+(\d)\s*\+\s*(\d).*?\(GRADE\s+(?:GROUP\s+)?(\d+)\)", finding_block, re.IGNORECASE)

                if grade_group_match:
                    grade_group = grade_group_match.group(1)
                    gleason = f"{grade_group_match.group(2)}+{grade_group_match.group(3)}"
                elif gleason_score_match:
                    gleason = f"{gleason_score_match.group(1)}+{gleason_score_match.group(2)}"
                    grade_group = gleason_score_match.group(3)
                else:
                    # Fallback: "GLEASON'S GRADE 4+3=7/10" or "GLEASON SCORE 3+3" or "GLEASON 3+4"
                    gleason_simple = re.search(r"GLEASON'?S?\s+(?:GRADE\s+|SCORE\s+)?(\d)\s*\+\s*(\d)", finding_block, re.IGNORECASE)
                    if gleason_simple:
                        gleason = f"{gleason_simple.group(1)}+{gleason_simple.group(2)}"
                    else:
                        # Pattern without GLEASON keyword: "3+3=6/10" or "3 + 3 = 6/10"
                        gleason_no_keyword = re.search(r'(\d)\s*\+\s*(\d)\s*=\s*\d+/10', finding_block)
                        if gleason_no_keyword:
                            gleason = f"{gleason_no_keyword.group(1)}+{gleason_no_keyword.group(2)}"

                    grade_simple = re.search(r'GRADE\s+GROUP\s+(\d+)', finding_block, re.IGNORECASE)
                    grade_group = grade_simple.group(1) if grade_simple else ""

                # Extract percentage involvement
                # Format 1: "INVOLVING 1% OF TISSUE" or "INVOLVING LESS THAN 5%"
                percent_match = re.search(r'INVOLVING\s+(?:LESS\s+THAN\s+|<?)?(\d+)\s*%', finding_block, re.IGNORECASE)
                if not percent_match:
                    # Format 2: "INVOLVING 5/6 CORES (50% OF THE TISSUE)"
                    percent_match = re.search(r'INVOLVING\s+\d+/\d+\s+CORES?\s*\((?:LESS\s+THAN\s+|<?)?(\d+)\s*%', finding_block, re.IGNORECASE)
                less_than = "less than " if percent_match and re.search(r'LESS\s+THAN|<\s*\d', finding_block, re.IGNORECASE) else ""
                percent = f"{less_than}{percent_match.group(1)}% of tissue" if percent_match else ""

                # Check for perineural invasion
                pni = ", with perineural invasion" if 'PERINEURAL INVASION' in finding_block.upper() else ""

                # Build core result string
                result_str = f"- {location.title()}: Adenocarcinoma"
                if grade_group and gleason:
                    result_str += f", Gleason Grade Group {grade_group} ({gleason})"
                elif gleason:
                    result_str += f", Gleason {gleason}"
                elif grade_group:
                    result_str += f", Grade Group {grade_group}"
                if percent:
                    result_str += f", {percent}"
                result_str += pni

                core_results.append(result_str)

        if not core_results:
            continue

        # Build summary for this biopsy
        summary_parts = []
        if date_str:
            summary_parts.append(f"{date_str} Prostate biopsy:")
        else:
            summary_parts.append("Prostate biopsy:")

        summary_parts.extend(core_results)
        all_biopsies.append('\n'.join(summary_parts))

    # Deduplicate: if same biopsy appears twice (e.g., repeated in input), keep unique
    seen = set()
    unique_biopsies = []
    for biopsy in all_biopsies:
        # Use the core results portion for comparison (skip date which may differ slightly)
        lines = biopsy.split('\n')
        core_key = '\n'.join(sorted(lines[1:])) if len(lines) > 1 else biopsy
        if core_key not in seen:
            seen.add(core_key)
            unique_biopsies.append(biopsy)

    return '\n\n'.join(unique_biopsies)


def extract_turbt_pathology(clinical_document: str) -> str:
    """
    Extract TURBT (transurethral resection of bladder tumor) pathology results.

    This handles the VA MICROSCOPIC EXAM/DIAGNOSIS format for bladder tumors:
    TURBT 9/11/23
    MICROSCOPIC EXAM/DIAGNOSIS:
      DIAGNOSIS:
      A. URINARY BLADDER, RIGHT POSTERIOR BLADDER WALL, TRANSURETHRAL RESECTION:
        - HIGH GRADE PAPILLARY UROTHELIAL CARCINOMA, NON-INVASIVE.
        - MUSCULARIS PROPRIA IS PRESENT AND IS UNINVOLVED.

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted TURBT pathology results, or "" if not found
    """
    all_turbt_results = []

    # Pattern to find TURBT pathology sections with date
    # Format: "TURBT 9/11/23" followed by MICROSCOPIC EXAM/DIAGNOSIS
    turbt_pattern = r'TURBT\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*\n\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:CT\s+Urogram|Comment:|Note:|\*{2}|\s*/es/|Signed|={10,}|$))'

    for match in re.finditer(turbt_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        date_str = match.group(1)
        diagnosis_block = match.group(2)

        # Check if this contains bladder/urinary/urothelial
        if not re.search(r'bladder|urinary|urothelial', diagnosis_block, re.IGNORECASE):
            continue

        _parse_bladder_specimens(diagnosis_block, date_str, all_turbt_results, prefix="TURBT")

    # Fallback: Find MICROSCOPIC EXAM/DIAGNOSIS sections with bladder content (no TURBT prefix)
    bladder_micro_pattern = r'\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n(?:(?!\s*DIAGNOSIS)[^\n]*\n)*\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:Comment:|/es/|Signed|={10,}|$))'
    for match in re.finditer(bladder_micro_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        diagnosis_block = match.group(1)

        # Only process if this contains bladder content and NOT prostate
        if not re.search(r'bladder|urinary|urothelial', diagnosis_block, re.IGNORECASE):
            continue
        if re.search(r'prostate', diagnosis_block, re.IGNORECASE):
            continue

        # Try to find date before this match
        date = ""
        date_match = re.search(r'(?:Date\s+(?:obtained|Spec\s+taken):\s*)?([A-Za-z]{3}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})', clinical_document[max(0, match.start()-300):match.start()], re.IGNORECASE)
        if date_match:
            date = date_match.group(1)

        _parse_bladder_specimens(diagnosis_block, date, all_turbt_results, prefix="Bladder biopsy")

    return '\n\n'.join(all_turbt_results)


def _parse_bladder_specimens(diagnosis_block: str, date_str: str, results_list: list, prefix: str = "TURBT"):
    """
    Parse bladder specimen results from a DIAGNOSIS block and add to results list.

    Handles formats:
    - "A. URINARY BLADDER, RIGHT POSTERIOR BLADDER WALL, TRANSURETHRAL RESECTION:"
    - "A. BLADDER, RIGHT HEMITRIGONE, BIOPSY:"
    - "A. BLADDER, TRANSURETHRAL RESECTION:"
    - "A. BLADDER, BIOPSY:"
    """
    specimen_results = []

    # Pattern for individual specimen results - handles multiple bladder formats
    specimen_pattern = r'([A-L])\.\s*((?:URINARY\s+)?BLADDER[,\s]+[^:]+?(?:TRANSURETHRAL\s+RESECTION|BIOPSY)?)[;\s:]*\n?\s*((?:[-•]\s*[^\n]+(?:\n\s+[^\n]+)*\n?\s*)+?)(?=\n\s*[A-L]\.\s|$)'

    for spec_match in re.finditer(specimen_pattern, diagnosis_block, re.IGNORECASE | re.DOTALL):
        spec_letter = spec_match.group(1)
        spec_location = spec_match.group(2).strip()
        findings_block = spec_match.group(3).strip()

        # Clean up location - extract just the anatomical location
        location_match = re.search(r'(?:URINARY\s+)?BLADDER[,\s]+([^,]+(?:BLADDER WALL|TUMOR)?)', spec_location, re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip().rstrip(',')
            location = location.title()
        else:
            location = "Bladder"

        # Parse findings - combine multi-line findings
        findings_lines = []
        for line in findings_block.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('•'):
                line = line[1:].strip()
            if line and not line.startswith('(SEE'):
                findings_lines.append(line)

        finding_text = ' '.join(findings_lines)

        # Normalize the finding
        if 'NEGATIVE FOR MALIGNANCY' in finding_text.upper():
            finding_summary = "Negative for malignancy"
            if 'MUSCULARIS PROPRIA' in finding_text.upper():
                finding_summary += ". Muscularis propria present"
        elif 'UROTHELIAL CARCINOMA' in finding_text.upper():
            grade = "High-grade" if 'HIGH' in finding_text.upper() else "Low-grade" if 'LOW' in finding_text.upper() else ""
            papillary = "papillary " if 'PAPILLARY' in finding_text.upper() else ""
            finding_summary = f"{grade} {papillary}urothelial carcinoma".strip()
            if 'NON-INVASIVE' in finding_text.upper() or 'NONINVASIVE' in finding_text.upper():
                finding_summary += ", non-invasive"
            if 'MUSCULARIS PROPRIA' in finding_text.upper():
                if 'UNINVOLVED' in finding_text.upper() or 'NO TUMOR' in finding_text.upper():
                    finding_summary += ". Muscularis propria present and uninvolved"
                elif 'NOT IDENTIFIED' in finding_text.upper() or 'NO MUSCULARIS' in finding_text.upper():
                    finding_summary += ". No muscularis propria identified"
                elif 'INVOLVED' in finding_text.upper():
                    finding_summary += ". Muscularis propria involved"
                else:
                    finding_summary += ". Muscularis propria present"
        else:
            # Use the raw finding text, cleaned up
            finding_summary = finding_text.replace('  ', ' ')

        specimen_results.append(f"{spec_letter}. {location}: {finding_summary}")

    if specimen_results:
        header = f"{prefix} {date_str}:" if date_str else f"{prefix}:"
        results_list.append(header + '\n' + '\n'.join(specimen_results))


def extract_renal_pathology(clinical_document: str) -> str:
    """
    Extract renal mass pathology and post-nephrectomy surgical pathology.

    Handles:
    1. Renal mass biopsy: LEFT RENAL MASS, BIOPSY: MULTILOCULAR CLEAR-CELL RENAL CELL NEOPLASM
    2. Post-nephrectomy: Left kidney final margin - negative for malignancy
    3. Tumor pathology: Left kidney tumor - ccRcc (clear cell renal cell carcinoma)

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted renal pathology results, or "" if not found
    """
    all_renal_results = []

    # ======================================================================
    # Pattern 1: Formal MICROSCOPIC EXAM/DIAGNOSIS format for renal mass biopsy
    # ======================================================================
    renal_biopsy_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4})[^\n]*?\n\s*\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n\s*DIAGNOSIS[:\s]*\n\s*[A-L]\.\s*((?:LEFT|RIGHT)\s+RENAL\s+MASS[,\s]+BIOPSY)[:\s]*\n\s*[-•]?\s*([^\n]+(?:\n\s+[-•]?\s*[^\n]+)*)'

    for match in re.finditer(renal_biopsy_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        date_str = match.group(1)
        specimen = match.group(2).strip()
        findings = match.group(3).strip()

        # Clean up findings - collapse multi-line
        findings = re.sub(r'\n\s+[-•]?\s*', ' ', findings)
        findings = re.sub(r'\s+', ' ', findings)

        # Format: "DATE: SPECIMEN: FINDING"
        result = f"{date_str}: {specimen}: {findings}"
        all_renal_results.append(result)

    # ======================================================================
    # Pattern 1b: MICROSCOPIC EXAM/DIAGNOSIS for KIDNEY PARTIAL NEPHRECTOMY
    # Handles: A. KIDNEY, RIGHT, PARTIAL NEPHRECTOMY:
    #            - CLEAR CELL RENAL CELL CARCINOMA, 4.6 CM.
    # ======================================================================
    nephrectomy_pattern = r'\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*\n\s*DIAGNOSIS[:\s]*\n\s*[A-L]\.\s*KIDNEY[,\s]+((?:LEFT|RIGHT))[,\s]+(?:PARTIAL\s+)?NEPHRECTOMY[:\s]*\n((?:\s*[-•]?\s*[^\n]+\n?)+?)(?=\n\s*(?:Comment|KIDNEY:|SPECIMEN|Tumor\s+Focality|\*{2}|/es/|$))'

    for match in re.finditer(nephrectomy_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        kidney_side = match.group(1).strip()
        findings_block = match.group(2).strip()

        # Parse findings from bullet points
        findings_list = []
        for line in findings_block.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                line = line[1:].strip()
            if line and not line.startswith('SEE COMMENT'):
                findings_list.append(line)

        if findings_list:
            # Try to find a nearby Date obtained
            date_str = ""
            # Look for Date obtained in the 4000 chars before this match
            # (SURGICAL PATHOLOGY sections have lots of metadata between date and diagnosis)
            pre_text = clinical_document[max(0, match.start()-4000):match.start()]
            date_match = re.search(r'Date obtained:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', pre_text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1)

            # Format result
            specimen = f"Kidney, {kidney_side.lower()}, partial nephrectomy"
            findings = '; '.join(findings_list)

            if date_str:
                result = f"{date_str}: {specimen}: {findings}"
            else:
                result = f"{specimen}: {findings}"

            # Deduplicate - don't add if we already have essentially the same result
            is_duplicate = False
            for existing in all_renal_results:
                # Check if the findings are the same (ignoring date differences)
                if findings.lower() in existing.lower() or existing.lower() in result.lower():
                    is_duplicate = True
                    # If current result has a date and existing doesn't, replace it
                    if date_str and ":" not in existing.split(":")[0]:
                        all_renal_results.remove(existing)
                        all_renal_results.append(result)
                    break

            if not is_duplicate:
                all_renal_results.append(result)

    # ======================================================================
    # Pattern 2: Informal "Final path DATE:" format (surgeon's summary)
    # This is common for outside surgeries summarized in urology notes
    # ======================================================================
    informal_path_pattern = r'Final\s+path(?:ology)?\s*(\d{1,2}/\d{1,2}/\d{2,4}):\s*\n?(.*?)(?=\n\n|\n[A-Z][A-Z\s]+:|\n\s*(?:CT|MRI|Impression|Assessment|Plan|HPI|$))'

    for match in re.finditer(informal_path_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        date_str = match.group(1)
        path_content = match.group(2).strip()

        if not path_content:
            continue

        # Parse individual findings
        findings = []
        for line in path_content.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Skip if it's a section header
            if re.match(r'^[A-Z][A-Z\s]+:$', line):
                break
            # Expand common abbreviations
            line = re.sub(r'\bccRcc\b', 'clear cell renal cell carcinoma', line, flags=re.IGNORECASE)
            line = re.sub(r'\bRCC\b', 'renal cell carcinoma', line, flags=re.IGNORECASE)
            findings.append(line)

        if findings:
            result = f"{date_str}:\n" + '\n'.join(findings)
            all_renal_results.append(result)

    # ======================================================================
    # Pattern 3: "Left kidney tumor" or "Left kidney margin" summaries
    # These appear in impression or as standalone pathology summaries
    # ======================================================================
    kidney_specimen_pattern = r'((?:Left|Right)\s+kidney)\s+((?:final\s+)?margin|tumor)[:\s]+[-–]?\s*([^\n]+)'

    for match in re.finditer(kidney_specimen_pattern, clinical_document, re.IGNORECASE):
        kidney_side = match.group(1)
        specimen_type = match.group(2)
        finding = match.group(3).strip()

        # Expand abbreviations
        finding = re.sub(r'\bccRcc\b', 'clear cell renal cell carcinoma', finding, flags=re.IGNORECASE)
        finding = re.sub(r'\bRCC\b', 'renal cell carcinoma', finding, flags=re.IGNORECASE)

        result = f"{kidney_side} {specimen_type} - {finding}"

        # Don't add if we already have this from another pattern
        if not any(result.lower() in existing.lower() for existing in all_renal_results):
            all_renal_results.append(result)

    # ======================================================================
    # Pattern 4: "s/p resection" with pathology finding
    # "Clear-cell renal cell carcinoma of left kidney s/p resection"
    # ======================================================================
    resection_pattern = r'((?:Clear[- ]?cell\s+)?renal\s+cell\s+(?:carcinoma|neoplasm))\s+of\s+((?:left|right)\s+kidney)\s+s/p\s+(?:resection|partial\s+nephrectomy|nephrectomy)'

    for match in re.finditer(resection_pattern, clinical_document, re.IGNORECASE):
        tumor_type = match.group(1).strip()
        kidney_side = match.group(2).strip()

        # Format as pathology result
        result = f"{kidney_side.title()} - {tumor_type.lower()}"

        # Don't add duplicates
        if not any(result.lower() in existing.lower() for existing in all_renal_results):
            all_renal_results.append(result)

    # ======================================================================
    # Pattern 5: Look for Comments about immunohistochemistry/differential diagnosis
    # Only capture comments that are specifically about renal/kidney pathology
    # ======================================================================
    comment_pattern = r'Comment:\s*((?:The\s+)?(?:malignant|tumor|neoplastic)[^\n]+(?:\n\s{2,}[^\n]+)*)'

    for match in re.finditer(comment_pattern, clinical_document, re.IGNORECASE):
        comment = match.group(1).strip()
        # Only include if it's about renal pathology
        if re.search(r'renal|kidney', comment, re.IGNORECASE):
            # Clean up multi-line comments
            comment = re.sub(r'\n\s+', ' ', comment)
            comment = re.sub(r'\s+', ' ', comment)

            # Add as a separate comment line if not already included
            comment_line = f"Comment: {comment}"
            if not any('comment' in existing.lower() for existing in all_renal_results):
                all_renal_results.append(comment_line)

    return '\n\n'.join(all_renal_results)


def extract_addendum_pathology(clinical_document: str) -> str:
    """
    Extract pathology from note addenda (non-standard format).

    Handles formats like:
    1. Addendum with "Pathology No:" header:
       Pathology No: HP-25-04300
       PROSTATE BIOPSY: 9/11/2025
       DIAGNOSIS:
       A. PROSTATE, RIGHT BASE, BIOPSY;
          ACINAR ADENOCARCINOMA, GRADE GROUP 1 (GLEASON SCORE 3+3=6)

    2. "MICROSCOPIC EVALUATION AND DIAGNOSIS:" format:
       MICROSCOPIC EVALUATION AND DIAGNOSIS:
       A-N. Prostate core biopsies from specified sites:

    3. Addendum biopsy with specimen descriptions:
       A. Kidney, right lower pole, core needle biopsy of mass:
        -Clear cell renal cell carcinoma

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted addendum pathology, or "" if not found
    """
    all_results = []

    # ======================================================================
    # Pattern 1: "Pathology No:" followed by biopsy type and DIAGNOSIS
    # ======================================================================
    pathno_pattern = r'Pathology\s+No(?:\.)?:\s*([A-Z]{2}-\d{2}-\d+)\s*\n\s*((?:PROSTATE|BLADDER|KIDNEY|RENAL)\s+BIOPSY)[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})?\s*\n\s*DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*/es/|\nFacility:|\n={10,})'
    for match in re.finditer(pathno_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        path_num = match.group(1)
        biopsy_type = match.group(2).strip()
        biopsy_date = match.group(3) or ""
        diagnosis_block = match.group(4).strip()

        # Parse individual specimens from diagnosis block
        specimens = _parse_specimen_block(diagnosis_block)
        if specimens:
            header = f"{biopsy_type}"
            if biopsy_date:
                header += f" ({biopsy_date})"
            header += f" [Pathology No: {path_num}]"
            result = header + ":\n" + '\n'.join(specimens)
            all_results.append(result)

    # ======================================================================
    # Pattern 2: "MICROSCOPIC EVALUATION AND DIAGNOSIS:" format
    # (Note: "EVALUATION" vs standard "EXAM")
    # ======================================================================
    eval_pattern = r'MICROSCOPIC\s+EVALUATION\s+AND\s+DIAGNOSIS[:\s]*\n(.*?)(?=\n\s*(?:Based on immunoprofile|Comment:|/es/|Facility:|={10,}|\n\n\n))'
    for match in re.finditer(eval_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        diagnosis_block = match.group(1).strip()

        # Also check for "Based on immunoprofile" continuation
        continuation_match = re.search(
            r'Based on immunoprofile[,\s]*the following is the final diagnosis\s*\n(.*?)(?=\n\s*(?:/es/|Facility:|={10,}|-{3,}\s*(?:TUMOR|SURGICAL)|ROS:|Medical\s+Problems|Medication\s+List|Active\s+Outpatient))',
            clinical_document[match.end():],
            re.IGNORECASE | re.DOTALL
        )

        if continuation_match:
            # The immunoprofile section has the definitive results
            final_block = continuation_match.group(1).strip()
            specimens = _parse_specimen_block(final_block)
        else:
            specimens = _parse_specimen_block(diagnosis_block)

        if specimens:
            result = "Prostate core biopsies:\n" + '\n'.join(specimens)
            all_results.append(result)

    # ======================================================================
    # Pattern 3: Addendum kidney/renal biopsy with immunohistochemistry
    # ======================================================================
    kidney_addendum_pattern = r'\s*[A-L]\.\s*(Kidney[,\s]+[^:]+?(?:biopsy|mass)[^:]*)[:\s]*\n\s*[-•]?\s*(.*?)(?=\n\s*Comment:|\n\s*[A-L]\.\s|\n\s*/es/|\n={10,})'
    for match in re.finditer(kidney_addendum_pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        specimen = match.group(1).strip()
        finding = match.group(2).strip()
        finding = re.sub(r'\n\s+[-•]?\s*', ' ', finding)
        finding = re.sub(r'\s+', ' ', finding)

        # Look for immunohistochemistry comment after this specimen
        comment_pattern = r'Comment:\s*(.*?)(?=\n\s*(?:[A-L]\.|/es/|Facility:|={10,}|\n\n))'
        comment_match = re.search(comment_pattern, clinical_document[match.end():], re.IGNORECASE | re.DOTALL)
        comment = ""
        if comment_match:
            comment_text = comment_match.group(1).strip()
            comment_text = re.sub(r'\n\s+', ' ', comment_text)
            comment_text = re.sub(r'\s+', ' ', comment_text)
            if re.search(r'positive|negative|stain|immunohistochem', comment_text, re.IGNORECASE):
                comment = f"\n  Comment: {comment_text}"

        result = f"{specimen}: {finding}{comment}"
        if not any(result.lower()[:40] in existing.lower() for existing in all_results):
            all_results.append(result)

    return '\n\n'.join(all_results)


def _parse_specimen_block(block: str) -> list:
    """
    Parse a block of specimen results with letter labels (A., B., C., etc.).

    Handles formats:
    - "A. PROSTATE, RIGHT BASE, BIOPSY;\n   ACINAR ADENOCARCINOMA..."
    - "B.. Left mid prostate, needle core biopsy:\n   -Tiny focus..."
    - "A, C, D,E-J,L,M,N. Prostate core biopsies from specified sites:\n   -Negative..."
    - "D-F. PROSTATE, LEFT BASE/MID/APEX, BIOPSY:\n     NO TUMOR PRESENT."

    Args:
        block: Text block containing lettered specimen results

    Returns:
        List of formatted specimen result strings
    """
    specimens = []

    # Split on specimen labels: single (A.), multi (D-F.), grouped (A, C, D.)
    # Using a regex that matches the start of each specimen entry
    parts = re.split(r'\n\s*(?=[A-P](?:[-,\s]+[A-P])*\.)', block)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Match the label and content
        label_match = re.match(r'([A-P](?:[-,\s]+[A-P])*)\.\s*(.*)', part, re.DOTALL)
        if not label_match:
            continue

        label = label_match.group(1).strip()
        content = label_match.group(2).strip()

        # Clean content - collapse multi-line into readable format
        # Preserve the specimen name and finding on separate logical lines
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•'):
                line = line[1:].strip()
            if line and line != ',':
                cleaned_lines.append(line)

        if cleaned_lines:
            # First line is typically the specimen description, rest are findings
            specimen_desc = cleaned_lines[0].rstrip(';:')
            findings = ' '.join(cleaned_lines[1:]) if len(cleaned_lines) > 1 else ""

            if findings:
                specimens.append(f"{label}. {specimen_desc}: {findings}")
            else:
                specimens.append(f"{label}. {specimen_desc}")

    return specimens


def extract_pathology(clinical_document: str) -> str:
    """
    Extract pathology reports from all formats in VA clinical documents.

    Handles:
    1. SURGICAL PATHOLOGY sections (standard format)
    2. MICROSCOPIC EXAM/DIAGNOSIS format (prostate biopsy, TURBT)
    3. Note addenda with pathology results
    4. MICROSCOPIC EVALUATION AND DIAGNOSIS format
    5. Renal pathology and nephrectomy reports
    6. External/non-VA pathology reports

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted pathology reports (date + diagnosis), or "" if not found
    """
    pathology_reports = []

    # First, try to extract prostate biopsy specifically (critical for prostate cancer diagnosis)
    prostate_biopsy = extract_prostate_biopsy(clinical_document)
    if prostate_biopsy:
        pathology_reports.append(prostate_biopsy)

    # Extract renal pathology (kidney cancer, nephrectomy margins)
    renal_pathology = extract_renal_pathology(clinical_document)
    if renal_pathology:
        pathology_reports.append(renal_pathology)

    # Also try to extract TURBT pathology (critical for bladder cancer diagnosis)
    turbt_pathology = extract_turbt_pathology(clinical_document)
    if turbt_pathology:
        pathology_reports.append(turbt_pathology)

    # Extract addendum pathology (non-standard formats in note addenda)
    addendum_pathology = extract_addendum_pathology(clinical_document)
    if addendum_pathology:
        pathology_reports.append(addendum_pathology)

    # Split by SURGICAL PATHOLOGY sections
    # Handle both consecutive dashes (----) and spaced dashes (- - - -)
    # Also handle "MEDICAL RECORD | SURGICAL PATHOLOGY" format
    split_patterns = [
        r'-{4,}\s*SURGICAL PATHOLOGY\s*-{4,}',  # ----SURGICAL PATHOLOGY----
        r'(?:- ){4,}.*?SURGICAL PATHOLOGY',      # - - - - SURGICAL PATHOLOGY
        r'MEDICAL\s+RECORD\s*\|\s*SURGICAL\s+PATHOLOGY',  # MEDICAL RECORD | SURGICAL PATHOLOGY
    ]

    sections = [clinical_document]
    for pattern in split_patterns:
        new_sections = []
        for section in sections:
            parts = re.split(pattern, section, flags=re.IGNORECASE)
            new_sections.extend(parts)
        sections = new_sections

    for i, section in enumerate(sections):
        if i == 0:
            # First section is before any SURGICAL PATHOLOGY marker
            continue

        # Extract date
        date_match = re.search(r'Date obtained:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', section, re.IGNORECASE)
        date = date_match.group(1) if date_match else ""

        # Extract specimen type - but skip lab specimens (not surgical pathology)
        # Lab specimens are not surgical pathology tissue and should be excluded
        lab_specimen_types = ['SERUM', 'BLOOD', 'PLASMA', 'URINE', 'CSF', 'FLUID',
                              'FECES', 'STOOL', 'SPUTUM', 'SWAB', 'CULTURE',
                              'RECTAL', 'NASAL', 'THROAT', 'ORAL']
        specimen = ""
        for spec_match in re.finditer(r'Specimen:\s*([^\n]+)', section, re.IGNORECASE):
            candidate = spec_match.group(1).strip()
            # Skip if this is a lab specimen type
            if not any(lab_type in candidate.upper() for lab_type in lab_specimen_types):
                specimen = candidate
                break

        # Extract diagnosis
        # Look for common diagnosis headers: "DIAGNOSIS:", "FLOW CYTOMETRY DIAGNOSIS:", "FINAL DIAGNOSIS:", etc.
        # CRITICAL: Exclude "PREOPERATIVE DIAGNOSIS", "OPERATIVE DIAGNOSIS", "POSTOPERATIVE DIAGNOSIS"
        diagnosis_match = re.search(
            r'(?:FINAL\s+|FLOW\s+CYTOMETRY\s+|FISH\s+)?DIAGNOSIS(?!\s*:\s*$)[:\s;]*([^\n]+(?:\n(?!\s*(?:Comment|Note|Clinical|Reporting))[^\n]+)*)',
            section,
            re.IGNORECASE | re.MULTILINE
        )

        # Skip if it's a surgical diagnosis (preoperative, operative, postoperative)
        if diagnosis_match:
            # Check if this is preceded by PREOPERATIVE, OPERATIVE, or POSTOPERATIVE
            match_pos = diagnosis_match.start()
            preceding_text = section[max(0, match_pos-30):match_pos]
            if any(term in preceding_text.upper() for term in ['PREOPERATIVE', 'POSTOPERATIVE', 'OPERATIVE FINDINGS']):
                continue

        if diagnosis_match:
            diagnosis = diagnosis_match.group(1).strip()

            # Skip if diagnosis is empty, too short, or only contains punctuation/metadata
            if not diagnosis or len(diagnosis) < 5:
                continue

            # Skip if diagnosis is just punctuation or whitespace
            if re.match(r'^[\s\.\,\;\:\-\*]+$', diagnosis):
                continue

            # Skip if diagnosis starts with metadata patterns
            if any(diagnosis.upper().startswith(p) for p in ['CASE REVIEWED', 'THIS IHC TEST', 'NP ', 'MD ']):
                continue

            # Filter out VA metadata lines from diagnosis
            diagnosis_lines = []
            for line in diagnosis.split('\n'):
                line = line.strip()
                # Skip metadata lines
                if any([
                    line.startswith('-' * 5),  # Dash separators
                    line.startswith('=' * 5),  # Equals separators
                    not line,  # Empty lines
                    re.match(r'^[\.\,\;\:\-\*\s]+$', line),  # Lines with only punctuation
                    'OPERATIVE FINDINGS' in line.upper(),
                    'POSTOPERATIVE DIAGNOSIS' in line.upper(),
                    'PREOPERATIVE DIAGNOSIS' in line.upper(),
                    'Surgeon/physician' in line,
                    'Accession No' in line,
                    'Case reviewed' in line,
                    'was notified' in line,
                    'This IHC test' in line,
                    'NP ' in line and 'notified' in line.lower(),  # NP name in notification context
                    line.startswith('*This'),
                ]):
                    continue
                diagnosis_lines.append(line)

            if not diagnosis_lines:
                continue

            diagnosis = '\n'.join(diagnosis_lines)

            # Clean up: remove excessive whitespace
            diagnosis = re.sub(r' +', ' ', diagnosis)
            diagnosis = re.sub(r'\n{3,}', '\n', diagnosis)

            # Format: Date | Specimen | Diagnosis
            if date and diagnosis:
                report = f"{date} - {specimen}: {diagnosis}" if specimen else f"{date}: {diagnosis}"
                pathology_reports.append(report)
            elif diagnosis:
                report = f"{specimen}: {diagnosis}" if specimen else diagnosis
                pathology_reports.append(report)

    # Also extract colonoscopy findings
    colonoscopy_results = extract_colonoscopy_findings(clinical_document)
    if colonoscopy_results:
        pathology_reports.append(colonoscopy_results)

    # Extract external/non-VA pathology (BAMC, SAMC, civilian hospitals)
    external_prostate = extract_external_prostate_pathology(clinical_document)
    if external_prostate and external_prostate not in pathology_reports:
        pathology_reports.append(external_prostate)

    if not pathology_reports:
        return ""

    return '\n\n'.join(pathology_reports)


def extract_pathology_from_note(note_content: str) -> str:
    """
    Extract pathology section from a clinical note (alternative format).

    Some notes may have embedded pathology results in a "Pathology:" section.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted pathology text, or "" if not found
    """
    # Pattern: "Pathology:" followed by content
    pattern = r'(?:Pathology|PATHOLOGY|Path):\s*(.*?)(?=\n\s*(?:MEDICATIONS:|ALLERGIES:|ASSESSMENT:|PLAN:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        path_text = match.group(1).strip()

        # Filter out VA metadata and empty surgical report sections
        va_metadata_patterns = [
            r'^\s*-{10,}\s*$',  # Lines with just dashes
            r'^\s*={10,}\s*$',  # Lines with just equals signs
            r'^\s*PREOPERATIVE DIAGNOSIS:\s*$',  # Empty preop diagnosis
            r'^\s*OPERATIVE FINDINGS:\s*$',  # Empty operative findings
            r'^\s*POSTOPERATIVE DIAGNOSIS:\s*$',  # Empty postop diagnosis
            r'^\s*Surgeon/physician:.*$',  # Surgeon info
            r'^\s*Accession No\..*$',  # Accession numbers
            r'^\s*PATHOLOGY REPORT\s+Accession.*$',  # Pathology report header with accession
            r'^\s*Specimen ID:.*$',  # Specimen IDs
            r'^\s*Body Site:.*$',  # Body site lines when standalone
        ]

        lines = path_text.split('\n')
        filtered_lines = []

        for line in lines:
            # Check if line matches any metadata pattern
            is_metadata = False
            for pattern_str in va_metadata_patterns:
                if re.match(pattern_str, line, re.IGNORECASE):
                    is_metadata = True
                    break

            if not is_metadata and line.strip():
                filtered_lines.append(line)

        path_text = '\n'.join(filtered_lines)

        # Remove ** markdown formatting
        path_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', path_text)
        # Clean up whitespace
        path_text = re.sub(r' +', ' ', path_text)
        path_text = re.sub(r'\n{3,}', '\n\n', path_text)
        return path_text.strip()

    return ""


def extract_external_prostate_pathology(clinical_document: str) -> str:
    """
    Extract prostate pathology from external/non-VA facilities (BAMC, SAMC, civilian hospitals).

    These reports have a simpler format:
    Prostate Cancer Biopsy at BAMC
    Right base      negative
    Right mid       Negative
    Right apex      3+4     20%     1/2
    Left Base       negative
    Left Mid        negative
    Left Apex       3+3             1/2

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted prostate pathology results, or "" if not found
    """
    results = []

    # Pattern 1: "Prostate Cancer Biopsy at [FACILITY]" or "Pathology: Prostate Cancer Biopsy at [FACILITY]"
    biopsy_pattern = r'(?:Pathology:\s*)?Prostate\s+Cancer\s+Biopsy\s+at\s+([A-Z]+)\s*\n((?:(?:Right|Left)\s+(?:base|mid|apex)[^\n]+\n?)+)'

    for match in re.finditer(biopsy_pattern, clinical_document, re.IGNORECASE):
        facility = match.group(1).strip()
        biopsy_data = match.group(2).strip()

        if not biopsy_data:
            continue

        # Parse individual core results
        cores_positive = []
        cores_negative = []
        gleason_score = ""
        max_percentage = ""

        for line in biopsy_data.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Pattern for core results: "Right apex  3+4  20%  1/2"
            core_match = re.match(r'((?:Right|Left)\s+(?:base|mid|apex))\s+(.+)', line, re.IGNORECASE)
            if core_match:
                location = core_match.group(1).strip()
                finding = core_match.group(2).strip()

                if 'negative' in finding.lower() or finding.lower() == 'neg':
                    cores_negative.append(location.lower())
                else:
                    # Parse Gleason pattern: "3+4 20% 1/2" or "3+3 1/2"
                    gleason_match = re.search(r'(\d\+\d)', finding)
                    percent_match = re.search(r'(\d+%)', finding)
                    cores_match = re.search(r'(\d/\d)', finding)

                    if gleason_match:
                        core_gleason = gleason_match.group(1)
                        if not gleason_score:
                            gleason_score = core_gleason

                        core_info = location.lower()
                        if percent_match:
                            core_info += f": Gleason {core_gleason}, {percent_match.group(1)}"
                            if not max_percentage or int(percent_match.group(1).replace('%', '')) > int(max_percentage.replace('%', '')):
                                max_percentage = percent_match.group(1)
                        else:
                            core_info += f": Gleason {core_gleason}"
                        if cores_match:
                            core_info += f" ({cores_match.group(1)} cores)"
                        cores_positive.append(core_info)

        if not cores_positive and not cores_negative:
            continue

        # Build summary
        summary_parts = [f"Prostate Cancer Biopsy ({facility}):"]

        if cores_positive:
            # Calculate total Gleason score
            if gleason_score:
                parts = gleason_score.split('+')
                if len(parts) == 2:
                    total = int(parts[0]) + int(parts[1])
                    summary_parts.append(f"Prostatic adenocarcinoma, Gleason score {gleason_score}={total}")

            for core in cores_positive:
                summary_parts.append(f"- {core}")

        if cores_negative:
            summary_parts.append(f"Negative: {', '.join(cores_negative)}")

        results.append('\n'.join(summary_parts))

    return '\n\n'.join(results) if results else ""


def extract_colonoscopy_findings(clinical_document: str) -> str:
    """
    Extract colonoscopy pathology findings from Provider Narrative sections.

    Pattern: Look for "History of colonoscopy" Provider Narratives with Note Narrative containing pathology findings.

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted colonoscopy findings, or "" if not found
    """
    colonoscopy_findings = []

    # Pattern 1: Provider Narrative sections with colonoscopy history
    pattern = r'Provider Narrative\s+History of colonoscopy.*?Note Narrative\s+(.*?)(?=Exposures|Facility:|Provider Narrative|={30,}|$)'

    for match in re.finditer(pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        narrative = match.group(1).strip()
        narrative = re.sub(r'\s+', ' ', narrative)
        if len(narrative) < 10:
            continue

        date_match = re.search(r'(?:Last done in|done in|in)\s+(\d{4})', narrative, re.IGNORECASE)
        date = date_match.group(1) if date_match else ""

        if date:
            colonoscopy_findings.append(f"Colonoscopy ({date}): {narrative}")
        else:
            colonoscopy_findings.append(f"Colonoscopy: {narrative}")

    # Pattern 2: Inline MICROSCOPIC EXAM/DIAGNOSIS with colon specimens
    # Handles flattened format from GI pathology notification letters:
    # "** MICROSCOPIC EXAM/DIAGNOSIS:  DIAGNOSIS:  A. COLON, CECUM, BIOPSY: - TUBULAR ADENOMA."
    inline_micro = re.finditer(
        r'\*{0,2}\s*MICROSCOPIC\s+EXAM/DIAGNOSIS[:\s]*(?:DIAGNOSIS[:\s]*)?(.*?)(?=\n\s*Recommendations|\n\s*Colonoscopy\s+reminder|\n\s*If\s+you\s+have|\n\s*Facility:|\n={10,}|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    for match in inline_micro:
        content = match.group(1).strip()
        if not re.search(r'COLON|CECUM|ASCENDING|DESCENDING|TRANSVERSE|SIGMOID|RECTUM|ADENOMA', content, re.IGNORECASE):
            continue

        # Parse specimens from the flattened or multi-line format
        # Split on specimen labels: "A. COLON, ..." "B. COLON, ..."
        specimen_parts = re.split(r'(?=[A-L]\.\s*(?:COLON|CECUM|SIGMOID|RECTUM))', content)
        specimen_results = []

        for part in specimen_parts:
            part = part.strip()
            if not part:
                continue

            # Match: "A. COLON, CECUM, BIOPSY: - EARLY ADENOMATOUS CHANGE. - COLONIC MUCOSA..."
            spec_match = re.match(
                r'([A-L])\.\s*(?:COLON|CECUM|SIGMOID|RECTUM)[,\s]+([^:]+?)(?:BIOPSY|POLYPECTOMY|RESECTION)[;\s:]*\s*(.*)',
                part, re.IGNORECASE | re.DOTALL
            )
            if spec_match:
                letter = spec_match.group(1)
                location = spec_match.group(2).strip().rstrip(',').title()
                findings_raw = spec_match.group(3).strip()

                # Collapse embedded newlines/whitespace from flattened format
                findings_raw = re.sub(r'\s+', ' ', findings_raw)

                # Parse individual findings (split on "- " bullet points)
                findings = []
                for finding in re.split(r'\s*-\s+', findings_raw):
                    finding = finding.strip().rstrip('.')
                    if finding and len(finding) > 2:
                        # Normalize case
                        finding = finding[0].upper() + finding[1:].lower()
                        findings.append(finding)

                if findings:
                    specimen_results.append(f"{letter}. {location}: {'; '.join(findings)}")

        if specimen_results:
            # Try to find date from surrounding context
            date = ""
            date_match = re.search(
                r'(?:performed\s+on|procedure.+?on|DATE OF NOTE:)\s*([A-Za-z]{3}\s+\d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
                clinical_document[max(0, match.start()-500):match.start()],
                re.IGNORECASE
            )
            if date_match:
                date = date_match.group(1).strip()

            header = f"Colonoscopy pathology ({date}):" if date else "Colonoscopy pathology:"
            colonoscopy_findings.append(header + '\n' + '\n'.join(specimen_results))

    if not colonoscopy_findings:
        return ""

    return '\n\n'.join(colonoscopy_findings)
