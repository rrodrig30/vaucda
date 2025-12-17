"""
Physical Exam Extractor

Extracts physical exam findings from clinical notes.
"""

import re


def extract_pe(note_content: str) -> str:
    """
    Extract physical exam section from a clinical note.

    Looks for "PHYSICAL EXAM:" or "PE:" section and extracts subsections:
    GENERAL, HEENT, CHEST, ABDOMEN, GU, RECTAL, PROSTATE, CNS

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PE text with subsections, or "" if not found
    """
    # Pattern: "PHYSICAL EXAM:" or "PE:" followed by content
    pattern = r'(?:PHYSICAL EXAM|PHYSICAL EXAMINATION|PE):\s*(.*?)(?=\n\s*(?:ASSESSMENT:|PLAN:|IMPRESSION:|PROBLEM LIST:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        pe_text = match.group(1).strip()

        # Filter out lab values that may have contaminated the PE section
        # Remove lines with common lab units
        lab_unit_patterns = [
            r'.*\d+\.?\d*\s*(?:mmol/L|mg/dL|ng/dL|ng/mL|g/dL|IU/L|mEq/L).*',
            r'.*(?:Hemoglobin|Creatinine|PSA|Glucose|BUN|Sodium|Potassium|Chloride|CO2|Specimen|Reporting Lab|Collection Date).*',
            r'.*URINE\s+[A-Z]+\s+(?:Negative|Positive|Trace|Small|Moderate|Large).*',
        ]

        lines = pe_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip lines matching lab patterns
            if any(re.match(pattern, line, re.IGNORECASE) for pattern in lab_unit_patterns):
                continue
            cleaned_lines.append(line)

        pe_text = '\n'.join(cleaned_lines).strip()

        # Clean up whitespace
        pe_text = re.sub(r' +', ' ', pe_text)
        pe_text = re.sub(r'\n{3,}', '\n\n', pe_text)

        return pe_text if len(pe_text) > 20 else ""

    return ""
