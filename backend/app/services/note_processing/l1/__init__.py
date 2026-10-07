"""L1 narrative-extractor integration (milestone 4).

The L1 model (fine-tuned medgemma-27b LoRA adapter) reads the NARRATIVE note
segments — tumor-board / consult prose, where the regex extractors have low
recall — and contributes diagnoses, treatment events, and diagnosis dates back
into the deterministic ``PatientStatusFacts``. Structured sections (RXOP meds,
SP pathology grade, CH/SLT/MIC labs, problem list, imaging) stay 100%
deterministic; nothing here touches them.

Gated entirely behind ``VAUCDA_L1=1`` (default off): when the flag is unset the
note pipeline is byte-for-byte the existing deterministic path. Heavy ML deps
(torch / transformers / peft) are imported lazily inside ``runtime`` only when
the flag is on AND enrichment is actually invoked, so importing this package is
cheap.

Per-field promotion policy (from the frozen-gold eval — promote only where the
fine-tuned L1 beats the regex baseline):
  - diagnoses (R 0.15 -> 0.67), treatment_events (R 0.07 -> 0.56),
    diagnosis_date (9% -> 90%): PROMOTED — merged in.
  - grade-by-system (regex 0.91 >= L1 0.87) and procedure/imaging split
    (L1 introduced 2-3 errors): NOT promoted — left to the deterministic
    pathology/structured extractors.

The merge is additive and monotonic: it only ADDS facts the deterministic layer
missed (grounded against the source by a verbatim-quote span resolver — the
hallucination net) and only UPGRADES status away from UNCERTAIN. It never
removes or overrides a deterministic fact.
"""
import os


def l1_enabled() -> bool:
    """True when the L1 narrative extractor is switched on via env."""
    return os.getenv("VAUCDA_L1", "0").strip() in ("1", "true", "True", "on")


def enrich_patient_facts_with_l1(facts, source_text):
    """Enrich a ``PatientStatusFacts`` in place using L1 over narrative segments.

    ``source_text`` is the RAW VistA extract (the router segments VistA SPN
    narrative; CPRS-native input is a no-op). No-op (returns ``facts``
    unchanged) when the flag is off. On any L1 runtime error the deterministic
    ``facts`` are returned unchanged unless ``VAUCDA_L1_STRICT=1``, so enabling
    L1 can never take down note generation. Heavy imports happen here, lazily.
    """
    if not l1_enabled():
        return facts
    try:
        from .enrich import enrich  # lazy: pulls torch/transformers only now
        return enrich(facts, source_text)
    except Exception as exc:  # pragma: no cover - defensive degrade-to-deterministic
        if os.getenv("VAUCDA_L1_STRICT", "0").strip() in ("1", "true", "True", "on"):
            raise
        print(f"[L1] enrichment skipped (deterministic facts kept): {exc!r}")
        return facts
