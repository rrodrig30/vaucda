"""Merge grounded L1 facts into the deterministic ``PatientStatusFacts``.

Additive + monotonic by construction: every L1 record must ground to a verbatim
source quote (the hallucination net) before it can contribute, and the merge
only ADDS missed facts / UPGRADES status away from UNCERTAIN. It never removes
or overrides a deterministic fact. Grade, procedures, and imaging are NOT taken
from L1 (the gold eval showed regex >= L1 there).
"""
import calendar
import re
from typing import List, Optional, Tuple

import os

# Importing runtime first runs its sys.path setup so the L1 scripts resolve.
from .runtime import extract_batch
from router import route_extract  # noqa: E402  (scripts/l1/router.py)

from ..clinical_timeline import TimelineEvent
from ..gu_diagnoses import GUDiagnosis

# Map an L1 diagnosis site/name to an organ bucket for routing.
_ORGAN_KW = [
    ("prostate", r"prostat"),
    ("renal", r"renal|kidney|nephr"),
    ("bladder", r"bladder|urotheli|vesical"),
    ("upper_tract", r"ureter|renal pelvis|upper[\s-]tract"),
    ("testicular", r"testic|testis|scrotal|germ[\s-]cell"),
    ("penile", r"penile|penis"),
    ("adrenal", r"adrenal"),
]


# GU organs whose diagnoses belong in a urology note. Non-GU cancers (liver,
# lung, colon, ...) often appear in tumor-board notes but must NOT enter the
# urologic ground truth / CC.
_GU_ORGANS = {"renal", "bladder", "upper_tract", "testicular", "penile", "adrenal"}


def _organ_of(site: str, name: str) -> str:
    s = f"{site} {name}".lower()
    for organ, pat in _ORGAN_KW:
        if re.search(pat, s):
            return organ
    return "other"

# Treatment statuses that mean the therapy was actually administered (vs merely
# planned/declined) — only these flip treatment_naive / add a timeline event.
_ADMINISTERED = {"started", "ongoing", "completed", "discontinued"}
# Modalities that are MONITORING, not treatment. An active-surveillance /
# watchful-waiting patient is treatment-naive by definition, so these must never
# flip treatment_naive or count as a confirmed treatment (the AS over-call bug).
_NON_TREATMENT_MODALITIES = {"active-surveillance", "watchful-waiting", "observation"}
_RADIATION_MODALITIES = {"radiation", "brachytherapy"}
# L1 modality -> treatment_active_status category (only the ones that layer tracks)
_STATUS_CATEGORY = {
    "ADT": "adt", "radiation": "radiation", "brachytherapy": "radiation",
    "prostatectomy": "prostatectomy", "focal": "focal",
}


def _grounded(quote: Optional[str], haystacks: List[str]) -> bool:
    """True if ``quote`` appears (whitespace-flexible) in any source haystack."""
    if not quote or not quote.split():
        return False
    pat = re.compile(r"\s+".join(re.escape(t) for t in quote.split()), re.S)
    return any(h and pat.search(h) for h in haystacks)


def _iso_to_event_date(s: Optional[str]) -> Optional[Tuple[str, str]]:
    """('2023-05-12'|'2023-05'|'2023') -> (date_key, display) or None."""
    if not s:
        return None
    m = re.match(r"\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", s)
    if not m:
        return None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if mo and d:
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", \
                f"{calendar.month_abbr[int(mo)]} {int(d)}, {y}"
        except (ValueError, IndexError):
            return None
    if mo:
        try:
            return f"{int(y):04d}-{int(mo):02d}", f"{calendar.month_abbr[int(mo)]} {y}"
        except (ValueError, IndexError):
            return None
    return y, y


def _add_timeline(facts, ev: TimelineEvent) -> None:
    """Append a timeline event unless an equivalent one (same date / type /
    modality) is already present — keeps repeats across multiple consult notes
    from duplicating, and makes a re-run idempotent."""
    for e in facts.clinical_timeline:
        if (e.date_key == ev.date_key and e.event_type == ev.event_type
                and (e.modality or "").lower() == (ev.modality or "").lower()):
            return
    facts.clinical_timeline.append(ev)


def _dedup_add(lst: List[str], value: str) -> bool:
    """Append ``value`` to ``lst`` if not already present (case-insensitive,
    substring-aware). Returns True if added."""
    v = value.strip()
    if not v:
        return False
    low = v.lower()
    for existing in lst:
        e = existing.lower()
        if low in e or e in low:
            return False
    lst.append(v)
    return True


def enrich(facts, source_text: str):
    """Run L1 over the narrative segments of ``source_text`` and merge the
    grounded results into ``facts`` (mutated in place; also returned).

    ``source_text`` must be the RAW VistA extract (the same format the L1 corpus
    was segmented from). The router keys on VistA section codes (SPN narrative);
    on CPRS-native input it finds no narrative segments and this is a no-op.
    """
    route = route_extract(source_text or "")
    pathology = route.pathology or ""
    if not route.narrative_segments:
        return facts

    # Only urologic-context segments feed the urologic facts object. By default
    # restrict to fact-bearing notes (treatment narrative or a rich diagnostic
    # title) — routine follow-ups carry none of the promoted fields and only
    # cost inference time. VAUCDA_L1_ALL_SEGMENTS=1 processes every segment.
    all_segs = os.getenv("VAUCDA_L1_ALL_SEGMENTS", "0").strip() in ("1", "true", "True", "on")
    candidates = [
        seg for seg, ctx in route.narrative_segments
        if ctx == "urologic" and (all_segs or seg.has_treatment_narrative or seg.rich_title)
    ]
    if not candidates:
        return facts

    drafts = extract_batch([seg.text for seg in candidates], pathology)

    found_cancer = False
    n_dx = n_tx = 0
    for seg, draft in zip(candidates, drafts):
        if not draft:
            continue
        haystacks = [seg.text, pathology, source_text]

        for d in (draft.get("diagnoses") or []):
            cat = (d.get("category") or "").lower()
            if cat not in ("cancer", "indeterminate", "benign"):
                continue
            q = d.get("source_quote")
            if not _grounded(q, haystacks):
                continue
            name = d.get("name") or ""
            site = d.get("site") or ""
            organ = _organ_of(site, name)
            # Non-urologic cancers (liver / lung / colon / ...) can appear in
            # tumor-board notes but do NOT belong in a urology note's GU ground
            # truth or CC — skip anything that isn't a GU organ.
            if organ != "prostate" and organ not in _GU_ORGANS:
                continue

            tl_name = name[:60]  # name used in the timeline DIAGNOSIS event
            if organ == "prostate":
                # Prostate cancer feeds the prostate-specific status; a merely
                # indeterminate/benign prostate note does not.
                if cat != "cancer":
                    continue
                found_cancer = True
                if _dedup_add(facts.cancer_evidence, q):
                    n_dx += 1
            else:
                # Non-prostate GU diagnosis -> the multi-cancer field, so a renal
                # or bladder cancer never flips PROSTATE_CANCER_STATUS. The
                # deterministic detector is authoritative on category (its
                # confirmation gate is conservative); L1 only ADDS organs it
                # missed, and fills a missing grade.
                grade = d.get("grade")
                if isinstance(grade, dict):
                    grade = " ".join(str(v) for v in grade.values() if v)
                grade = (str(grade) if grade else "")[:30]
                existing = next((x for x in facts.other_gu_diagnoses if x.organ == organ), None)
                if existing is None:
                    facts.other_gu_diagnoses.append(GUDiagnosis(
                        organ=organ, category=cat, name=(name or q)[:80],
                        grade=grade, evidence=q))
                    n_dx += 1
                else:
                    if grade and not existing.grade:
                        existing.grade = grade
                    # If the deterministic gate judged this organ indeterminate,
                    # do NOT let L1's diagnosis name assert cancer downstream
                    # (timeline -> HPI "bladder cancer" over-call). Use the
                    # conservative deterministic name in the timeline event.
                    if existing.category == "indeterminate":
                        tl_name = existing.name[:60]
            dd = _iso_to_event_date(d.get("diagnosis_date"))
            if dd:
                _add_timeline(facts, TimelineEvent(
                    date_key=dd[0], date_display=dd[1], event_type="DIAGNOSIS",
                    modality=tl_name, detail=site, source_quote=q))

        for t in (draft.get("treatment_events") or []):
            status = (t.get("status") or "").lower()
            if status not in _ADMINISTERED:
                continue
            modality = t.get("modality") or "treatment"
            # Active surveillance / watchful waiting is monitoring, not therapy:
            # never flip naive or record it as a confirmed treatment.
            if modality.lower() in _NON_TREATMENT_MODALITIES:
                continue
            q = t.get("source_quote")
            if not _grounded(q, haystacks):
                continue
            agent = t.get("agent")
            label = modality + (f" ({agent})" if agent else "") + f" — {status}"
            if _dedup_add(facts.confirmed_urologic_treatments, q):
                n_tx += 1
            facts.treatment_naive = False
            if modality.lower() in _RADIATION_MODALITIES:
                facts.phoenix_applicable = True

            # L1 contributes HISTORY, not currency. The deterministic layer
            # (RXOP active-outpatient list + recency) is the sole authority on
            # "what is active NOW". So L1 only ever records a COMPLETED /
            # DISCONTINUED course (which actively helps the Plan avoid
            # over-continuing a finite course) and NEVER asserts ACTIVE — an L1
            # history fact must not be able to push the Plan toward
            # 'continue <drug>'. started/ongoing are left to the deterministic
            # currency logic.
            cat = _STATUS_CATEGORY.get(t.get("modality"))
            if (cat and cat not in facts.treatment_active_status
                    and status in ("completed", "discontinued")):
                facts.treatment_active_status[cat] = (
                    "DISCONTINUED" if cat == "adt" else "COMPLETED")

            ev_type = ("TREATMENT_STARTED" if status in ("started", "ongoing")
                       else "TREATMENT_DECLINED" if status == "declined"
                       else "TREATMENT_COMPLETED")
            dd = _iso_to_event_date(t.get("end_date") or t.get("start_date"))
            if dd:
                _add_timeline(facts, TimelineEvent(
                    date_key=dd[0], date_display=dd[1], event_type=ev_type,
                    modality=modality, detail=label, source_quote=q))

    # Upgrade cancer_status only away from uncertainty — never downgrade a
    # deterministic PRESENT/TREATED verdict.
    if found_cancer and facts.cancer_status in ("UNCERTAIN", "ABSENT"):
        facts.cancer_status = ("TREATED" if facts.confirmed_urologic_treatments
                               else "PRESENT")

    # Keep the timeline chronological after additions.
    facts.clinical_timeline.sort(key=lambda e: e.date_key)

    print(f"[L1] merged {n_dx} cancer-evidence + {n_tx} treatment fact(s) "
          f"from {len(candidates)} fact-bearing segment(s); "
          f"cancer={facts.cancer_status} naive={facts.treatment_naive}")
    return facts
