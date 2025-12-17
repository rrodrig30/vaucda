"""
Pathology Agent

Combines and summarizes pathology reports.
"""

from typing import List, Dict
import re
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_pathology(document_pathology: str, gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize pathology results from document-level extraction and notes.

    Per instructions: Combine pathology from document sections and note extractions,
    then summarize.

    Args:
        document_pathology: Pathology from SURGICAL PATHOLOGY sections
        gu_notes: List of GU note dictionaries

    Returns:
        Summarized pathology results
    """
    # Collect all pathology entries
    all_pathology = []

    # Document-level pathology (from SURGICAL PATHOLOGY sections)
    if document_pathology:
        all_pathology.append(document_pathology)

    # Note-level pathology mentions
    for note in gu_notes:
        if note.get("Pathology"):
            all_pathology.append(note["Pathology"])

    if not all_pathology:
        return ""

    # If only one instance, return it
    if len(all_pathology) == 1:
        return all_pathology[0]

    # Use LLM to combine and summarize pathology
    instructions = """
Combine and summarize these pathology results.
- Keep each unique pathology report
- Include: Date, Specimen type, Diagnosis
- Remove duplicate reports
- Sort by date (most recent first)
- Keep summaries concise but clinically complete
- Include AJCC staging if present

CRITICAL: Provide ONLY the pathology results. NO meta-commentary, NO explanations, NO preamble like "Here are the results". Just the pathology data.
"""

    synthesized_pathology = combine_sections_with_llm(
        section_name="Pathology Results",
        section_instances=all_pathology,
        instructions=instructions
    )

    # Remove ** markdown formatting and VA metadata
    if synthesized_pathology:
        synthesized_pathology = re.sub(r'\*\*([^*]+)\*\*', r'\1', synthesized_pathology)

        # Filter out remaining VA metadata that LLM might have included
        va_metadata_patterns = [
            r'^\s*-{10,}\s*$',  # Lines with just dashes
            r'^\s*={10,}\s*$',  # Lines with just equals signs
            r'^\s*PREOPERATIVE DIAGNOSIS:\s*$',  # Empty preop diagnosis
            r'^\s*OPERATIVE FINDINGS:\s*$',  # Empty operative findings
            r'^\s*POSTOPERATIVE DIAGNOSIS:\s*$',  # Empty postop diagnosis
            r'^\s*Surgeon/physician:.*$',  # Surgeon info
            r'^\s*Accession No\..*$',  # Accession numbers
        ]

        lines = synthesized_pathology.split('\n')
        filtered_lines = []

        for line in lines:
            is_metadata = False
            for pattern_str in va_metadata_patterns:
                if re.match(pattern_str, line, re.IGNORECASE):
                    is_metadata = True
                    break

            if not is_metadata and line.strip():
                filtered_lines.append(line)

        synthesized_pathology = '\n'.join(filtered_lines)

        # Clean any LLM meta-commentary
        synthesized_pathology = clean_llm_commentary(synthesized_pathology)

    return synthesized_pathology
