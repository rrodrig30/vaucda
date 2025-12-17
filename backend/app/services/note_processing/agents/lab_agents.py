"""
Lab-Related Agents

Simple agents that format lab data (endocrine, stone, general labs).
These agents primarily organize and format data without complex LLM synthesis.
"""

from typing import List, Dict


def synthesize_endocrine_labs(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize endocrine lab results from GU notes.

    Collects: Total Testosterone, % Free Testosterone, Total Estrogens, LH, FSH, A1C, AFP, HCG, LDH

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Formatted endocrine labs in reverse chronological order
    """
    all_endocrine = []

    for note in gu_notes:
        if note.get("Endocrine"):
            all_endocrine.append(note["Endocrine"])

    if not all_endocrine:
        return ""

    # Simple combination - just concatenate unique entries
    combined = '\n'.join(all_endocrine)

    return combined


def synthesize_stone_labs(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize stone-related lab results from GU notes.

    Collects: 24-hour urine, CMP, PTH

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Formatted stone labs in reverse chronological order
    """
    all_stone = []

    for note in gu_notes:
        if note.get("Stone"):
            all_stone.append(note["Stone"])

    if not all_stone:
        return ""

    # Simple combination
    combined = '\n\n'.join(all_stone)

    return combined


def synthesize_general_labs(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize general lab results from GU notes.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Formatted general labs in reverse chronological order
    """
    all_labs = []

    for note in gu_notes:
        if note.get("Labs"):
            all_labs.append(note["Labs"])

    if not all_labs:
        return ""

    # Simple combination
    combined = '\n\n'.join(all_labs)

    return combined


def synthesize_testosterone(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize testosterone curve from GU notes.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Combined testosterone curve in reverse chronological order
    """
    all_testosterone = []

    for note in gu_notes:
        if note.get("Testosterone"):
            all_testosterone.append(note["Testosterone"])

    if not all_testosterone:
        return ""

    # Simple combination
    combined = '\n'.join(all_testosterone)

    return combined
