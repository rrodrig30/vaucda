"""
Synthesis Agents

Each agent takes extracted data (from GU and non-GU dictionaries) and
synthesizes a final section using LLM-based combination (temperature 0.2).

Note: PE and ROS agents return static templates (not extracted from notes)
because these sections document findings from the actual patient visit and
must be filled in by the provider during the encounter.
"""

from .gu_agent import process_gu_notes
from .non_gu_agent import process_non_gu_notes

__all__ = [
    'process_gu_notes',
    'process_non_gu_agent',
]
