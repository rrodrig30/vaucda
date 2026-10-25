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
import re
from typing import Literal

from .vista_to_cprs import normalize_vista_to_cprs

logger = logging.getLogger(__name__)

SourceFormat = Literal["cprs", "vista"]


_VISTA_BAR_RE = re.compile(r"^-{5,}\s*[A-Z]{2,5}\s+-\s+[A-Za-z][^\n]{2,60}-{5,}\s*$", re.M)
_VISTA_BANNER_RE = re.compile(r"^\s*(?:CLINIC\s*:[^\n]*\bDATE:|EXTRACTED:\s*\d{4}-\d{2}-\d{2})", re.M)


def looks_like_vista(raw_text: str) -> bool:
    """True when the text carries the VistA prep-extract signature: at least two
    '---- XX - Section ----' bars, or one bar plus the CLINIC/EXTRACTED banner."""
    if not raw_text:
        return False
    head = raw_text[:200000]
    bars = len(_VISTA_BAR_RE.findall(head))
    return bars >= 2 or (bars >= 1 and bool(_VISTA_BANNER_RE.search(head[:3000])))


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
    # The source format is a per-user PREFERENCE, and it was silently flipped to
    # 'cprs' by a settings save on 2026-10-07 while every chart was still a VistA
    # prep extract. With the normalizer skipped, every document-level extractor
    # (PMH / PSH / meds / labs / imaging / pathology) returned empty and the notes
    # lost those sections. The CONTENT decides: a VistA extract is unmistakable
    # (the 'CLINIC : ... DATE:' / 'EXTRACTED:' banner and the '---- DEM -
    # Demographics ----' section bars), so normalize it whatever the preference.
    if fmt != "vista" and looks_like_vista(raw_text):
        logger.info("source_format=%r but the text is a VistA extract — normalizing", fmt)
        fmt = "vista"
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
