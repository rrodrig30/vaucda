"""Source-EHR normalizers.

The note_processing pipeline (extractors, timeline, skeleton, agents) is
tuned for the CPRS-export section layout. When the user pastes a VistA
export — which carries the same clinical content but uses different
section headers and table formats — we run a preprocessing step that
rewrites the input into the CPRS section layout BEFORE the extractors
see it. Everything downstream stays unchanged.

Public API:
    normalize_to_cprs(raw_text, source_format) -> str
        Returns CPRS-formatted text. source_format is one of:
          "cprs"  - pass-through (default)
          "vista" - run VistA -> CPRS normalization
        Unknown values are treated as "cprs" pass-through so the
        pipeline never errors on a misconfigured setting.

    detect_source_format(raw_text) -> str
        Heuristic detection for auto-mode. Currently returns "cprs"
        unless strong VistA markers are present. Used only as a
        diagnostic / fallback hint; the authoritative selection is the
        user's setting from UserPreferences.source_format.
"""

from __future__ import annotations

import logging
from typing import Literal

from .vista_to_cprs import normalize_vista_to_cprs

logger = logging.getLogger(__name__)

SourceFormat = Literal["cprs", "vista"]


def normalize_to_cprs(raw_text: str, source_format: str) -> str:
    """Convert raw_text into CPRS section layout based on source_format.

    Args:
        raw_text: Raw clinician text as pasted / uploaded.
        source_format: "cprs" or "vista" (case-insensitive).

    Returns:
        CPRS-formatted text. On any failure the original raw_text is
        returned unchanged so the pipeline never blocks on a normalizer
        bug.
    """
    if not raw_text:
        return raw_text or ""
    fmt = (source_format or "cprs").strip().lower()
    if fmt == "cprs":
        return raw_text
    if fmt == "vista":
        try:
            normalized = normalize_vista_to_cprs(raw_text)
            if normalized and len(normalized) >= len(raw_text) * 0.5:
                return normalized
            # If the normalizer produced suspiciously short output, fall
            # back to the original rather than feed the pipeline a
            # truncated chart.
            logger.warning(
                "VistA normalizer produced suspiciously short output "
                "(%d chars from %d input); falling back to raw text",
                len(normalized or ""), len(raw_text),
            )
            return raw_text
        except Exception as e:  # noqa: BLE001
            logger.warning(f"VistA->CPRS normalization failed (fallback to raw): {e}")
            return raw_text
    # Unknown format: pass through and log
    logger.info(f"Unknown source_format {fmt!r}; treating as CPRS pass-through")
    return raw_text


def detect_source_format(raw_text: str) -> SourceFormat:
    """Heuristic detection. Not authoritative — the user setting wins."""
    if not raw_text:
        return "cprs"
    # VistA markers (high confidence). Extend as we learn more.
    vista_markers = (
        "Reporting Lab:",
        "MEDICAL RECORD |",
        "Submitted by: ALM",
        "Date obtained:",
    )
    hits = sum(1 for m in vista_markers if m in raw_text)
    if hits >= 2:
        return "vista"
    return "cprs"
