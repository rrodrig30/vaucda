"""
Allergies Agent

Combines allergy information from all notes.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm


def synthesize_allergies(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize allergies from all notes.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Synthesized, enumerated allergies list
    """
    # Collect all allergy entries
    all_allergies = []

    for note in gu_notes:
        if note.get("Allergies"):
            all_allergies.append(note["Allergies"])

    for note in non_gu_notes:
        if note.get("Allergies"):
            all_allergies.append(note["Allergies"])

    if not all_allergies:
        return "No known drug allergies (NKDA)"

    # If only one instance, return it
    if len(all_allergies) == 1:
        return all_allergies[0]

    # Use LLM to combine and deduplicate allergies
    instructions = """
Combine these allergy lists into a single, deduplicated list.
- Remove duplicate allergies
- Include the allergen name and reaction type
- Format as a simple list (one allergy per line)
- If all entries say "no allergies" or "NKDA", return "No known drug allergies (NKDA)"
"""

    synthesized_allergies = combine_sections_with_llm(
        section_name="Allergies",
        section_instances=all_allergies,
        instructions=instructions
    )

    # Clean up LLM meta-commentary and enumerate
    if synthesized_allergies and not synthesized_allergies.lower().startswith("no known"):
        # Remove LLM meta-commentary
        import re
        synthesized_allergies = re.sub(r'^(After reviewing|Here is|Here are|I have|I removed|Note:).*?\n', '', synthesized_allergies, flags=re.MULTILINE | re.IGNORECASE)
        synthesized_allergies = re.sub(r'\n(Note:|I corrected|The entry).*$', '', synthesized_allergies, flags=re.DOTALL | re.IGNORECASE)

        lines = [line.strip() for line in synthesized_allergies.split('\n') if line.strip()]
        # Remove any numbering, bullets, or * formatting
        cleaned_lines = []
        for line in lines:
            # Remove leading markers
            line = re.sub(r'^[\d\.\-\*\)]+\s*', '', line)
            # Remove * bullets
            line = line.lstrip('* ')
            if line and not line.lower().startswith(('after', 'here', 'note', 'i have', 'i removed')):
                cleaned_lines.append(line)

        if cleaned_lines:
            # Re-number
            enumerated_allergies = '\n'.join([f"{i}. {line}" for i, line in enumerate(cleaned_lines, 1)])
            return enumerated_allergies

    return synthesized_allergies
