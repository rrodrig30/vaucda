"""LLM-forward composition with deterministic VERIFICATION (rebuild, 10/2026).

Principle (user decision 2026-10-21): the LLM reads the WHOLE chart and writes
the Assessment and Plan as the attending would — using the clinician's most
recent HPI/Assessment/Plan as the backbone, the deterministic tables (PSA
curve, PSADT, ADT schedule, pathology, labs, imaging, medications, functional
status, life expectancy) as authoritative DATA, and GraphRAG guideline passages
for recommendations. Deterministic checks never overwrite the draft: they raise
DISCREPANCIES which a second, quote-grounded LLM call adjudicates; a correction
is applied only when the adjudicator's supporting quote exists verbatim in the
chart, otherwise the item is surfaced to the provider in VERIFICATION NOTES.

Gate: VAUCDA_COMPOSE_V3=1 (default 0 until the eval beats the current
pipeline).
"""
import os


def compose_v3_enabled() -> bool:
    return os.environ.get("VAUCDA_COMPOSE_V3", "0").strip() in ("1", "true", "True", "on")
