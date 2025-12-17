"""
Note Processing Module

This module implements the agent-based clinical note processing architecture.
It splits clinical documents into GU and non-GU notes, extracts structured data,
and synthesizes comprehensive urology clinic notes.

Architecture:
1. Note Identification: Split document by STANDARD TITLE markers
2. Extraction Phase: Extract data from identified notes into dictionaries
3. Synthesis Phase: Combine data using LLM-based agents
4. Assembly: Build final formatted note
"""

from .note_identifier import identify_notes

__all__ = ['identify_notes']
