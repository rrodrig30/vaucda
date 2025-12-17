"""
PSH (Past Surgical History) Agent

Combines surgical histories from all notes, including VA surgical data.
"""

from typing import List, Dict
import re
from ..llm_helper import combine_sections_with_llm


def synthesize_psh(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize Past Surgical History from all notes.

    Per instructions: Combine PSH from all notes, including any surgery data
    from VA clinical documents.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Synthesized, enumerated PSH list
    """
    # Collect all PSH entries
    all_psh = []

    for note in gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    for note in non_gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    if not all_psh:
        return ""

    # If only one instance, return it
    if len(all_psh) == 1:
        return all_psh[0]

    # Use LLM to combine and deduplicate PSH
    instructions = """
Combine these surgical histories into a single, deduplicated list.
- Remove duplicate surgeries
- Preserve dates (format: M/DD/YY or MM/DD/YYYY exactly as shown)
- Sort by date (most recent first) if dates are available
- Include ALL surgeries (ALL surgeries are relevant to urology - they impact patient positioning, flexibility, anesthesia tolerance, procedure complications, DVT/PE risk, etc.)
- Format as a simple list (one surgery per line)

CRITICAL: Provide ONLY the surgical history list. NO meta-commentary, NO explanations, NO preamble. Just the enumerated list.
"""

    synthesized_psh = combine_sections_with_llm(
        section_name="Past Surgical History",
        section_instances=all_psh,
        instructions=instructions
    )

    # Clean up LLM meta-commentary
    if synthesized_psh:
        # Remove common LLM meta-phrases
        synthesized_psh = re.sub(r'^(Here is|Here are|I have combined|Note:).*?\n', '', synthesized_psh, flags=re.MULTILINE | re.IGNORECASE)
        synthesized_psh = re.sub(r'\n(Note:|I removed|Since there).*$', '', synthesized_psh, flags=re.DOTALL | re.IGNORECASE)

        lines = [line.strip() for line in synthesized_psh.split('\n') if line.strip()]
        # Remove any numbering, bullets, or ** formatting that might already exist
        cleaned_lines = []
        for line in lines:
            # Remove leading numbers, bullets, asterisks
            line = re.sub(r'^[\d\.\-\*\)]+\s*', '', line)
            # Remove ** markdown
            line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
            if line:
                cleaned_lines.append(line)

        # Re-number
        enumerated_psh = '\n'.join([f"{i}. {line}" for i, line in enumerate(cleaned_lines, 1)])
        return enumerated_psh

    return synthesized_psh
