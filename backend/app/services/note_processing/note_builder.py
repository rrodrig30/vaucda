"""
Note Builder

Orchestrates the entire note processing pipeline:
1. Identify notes (GU and non-GU)
2. Extract data from notes
3. Extract document-level data
4. Synthesize all sections (PARALLEL execution for performance)
5. Assemble final urology clinic note

Supports task-specific LLM configuration via LLMTaskConfig.
Stage 1 primarily uses regex extraction with minimal LLM use.

Performance optimizations:
- Independent synthesis agents run in parallel using ThreadPoolExecutor
- Reduces total processing time from sequential sum to max single agent time
"""

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig

from .note_identifier import identify_notes
from .agents.gu_agent import process_gu_notes
from .agents.non_gu_agent import process_non_gu_notes
from .extractors import extract_pmh, extract_medications, extract_pathology, extract_imaging, extract_allergies_from_document, extract_sexual
from .extractors.psh_extractor import extract_psh
from .extractors.consult_request_extractor import (
    extract_consult_request,
    is_urology_consult,
    get_providers_to_scan
)
from .extractors.provider_note_scanner import scan_provider_notes_for_urologic_content
from .extractors.psa_extractor import extract_psa
from .extractors.lab_extractor import extract_labs, extract_calcium_series
from .extractors.stone_extractor import extract_stone_labs
from .extractors.endocrine_extractor import extract_endocrine_labs
from .extractors.social_extractor import extract_social, extract_social_with_change_detection
from .extractors.family_extractor import extract_family
from .extractors.diet_extractor import extract_diet
from .document_classifier import DocumentClassifier, extract_document_type
from .extractors.pcp_note_extractor import PCPNoteExtractor
from .extractors.specialty_urologic_scanner import (
    scan_non_gu_notes_for_urologic_content,
    format_cross_specialty_context
)
from .visit_progression_analyzer import analyze_visit_progression
from .patient_status_facts import (
    extract_patient_status_facts,
    format_facts_for_prompt,
    sanitize_context_against_facts,
)
from .llm_helper import (
    set_current_task_config,
    get_current_task_config,
    run_with_task_config,
)

# Import synthesis agents
from .agents.cc_agent import synthesize_cc
from .agents.hpi_agent import synthesize_hpi, synthesize_consult_hpi
from .agents.prior_ap_agent import (
    synthesize_prior_ap_context,
    format_prior_ap_for_hpi
)
from .extractors import extract_assessment, extract_plan
from .agents.ipss_agent import synthesize_ipss
from .agents.diet_agent import synthesize_diet
from .agents.pmh_agent import synthesize_pmh
from .agents.psh_agent import synthesize_psh
from .agents.social_agent import synthesize_social
from .agents.family_agent import synthesize_family
from .agents.sexual_agent import synthesize_sexual
from .agents.psa_agent import synthesize_psa
from .agents.pathology_agent import synthesize_pathology
from .agents.medications_agent import synthesize_medications
from .agents.allergies_agent import synthesize_allergies
from .agents.lab_agents import (
    synthesize_endocrine_labs,
    synthesize_stone_labs,
    synthesize_general_labs,
    synthesize_testosterone
)
from .agents.imaging_agent import synthesize_imaging
from .agents.ros_agent import synthesize_ros
from .agents.pe_agent import synthesize_pe
# Note: Assessment and Plan are Stage 2 only (completed after patient visit)


def get_time_suffix(is_consult: bool = False) -> str:
    """
    Get the appropriate time billing suffix template.

    Args:
        is_consult: If True, returns 45-minute template; otherwise 40-minute template

    Returns:
        Time suffix template string
    """
    # Path to time suffix template file
    # __file__ is in backend/app/services/note_processing/, need to go up 5 levels to project root
    time_suffix_path = Path(__file__).parent.parent.parent.parent.parent / 'time suffix.txt'

    try:
        with open(time_suffix_path, 'r') as f:
            content = f.read()

        # Split by the separator line
        templates = content.split('++++++++++++++++++++++++++++++++++++++')

        if is_consult:
            # 45-minute version is the second template (index 1)
            if len(templates) >= 2:
                # Strip whitespace and any remaining plus signs
                template = templates[1].strip().lstrip('+').strip()
                return template
            else:
                # Fallback: try to find 45-minute section
                lines = content.split('\n')
                # Find where "Total: 45" appears and extract that section
                for i, line in enumerate(lines):
                    if 'Total:' in line and '45' in line:
                        # Go backwards to find start
                        start_idx = max(0, i - 35)  # Approximately 35 lines before
                        end_idx = min(len(lines), i + 5)  # A few lines after
                        return '\n'.join(lines[start_idx:end_idx])
        else:
            # 40-minute version is the first template (index 0)
            if len(templates) >= 1:
                # Strip whitespace and any remaining plus signs
                template = templates[0].strip().lstrip('+').strip()
                return template
            else:
                # Fallback: return first 40 lines
                lines = content.split('\n')
                return '\n'.join(lines[:40])

    except FileNotFoundError:
        # Return a basic template if file not found
        total_time = 45 if is_consult else 40
        return f"""
Time of Start:
Time End:
Time Spent in Chart prep, review, interpretation, & documentation: See Below
Total Time Spent: {total_time} minutes

Please note that I have spent >{total_time} total minutes in this visit including counseling,
coordination of care, chart review, lab interpretation, discussion of findings with the patient,
independent interpretation of data, communicating or referring to providers, formation of a
treatment plan with shared decision making, placing orders, coordinating follow-up and
documenting the encounter.
"""


def build_urology_note(
    clinical_text: str,
    task_config: Optional["LLMTaskConfig"] = None,
    source_format: str = "cprs",
) -> str:
    """
    Build a comprehensive urology clinic note from a clinical document.

    This is the main entry point for the new agent-based architecture.

    Args:
        clinical_text: Full clinical document text (aliased from clinical_document)
        task_config: Optional LLMTaskConfig for Stage 1 LLM settings
        source_format: "cprs" (default) or "vista". When "vista", the
            clinical_text is run through the VistA -> CPRS normalizer
            BEFORE extractors / agents see it. The downstream pipeline
            is identical regardless of source.

    Returns:
        Formatted urology clinic note

    Note:
        Stage 1 primarily uses regex-based extraction for speed.
        LLM is used sparingly for synthesis where needed.
        The task_config is set globally for all agent LLM calls.
    """
    # Set the task config for all agents to use via thread-local storage
    # This ensures all synthesize_with_llm calls use the user's configured model
    set_current_task_config(task_config)

    # Source-format normalization. Applied at the very top so every
    # extractor / agent downstream sees CPRS-canonical section layout.
    # Pass-through for "cprs"; rewrites VistA section headers / tables
    # for "vista". Failures fall back to the original text so the
    # pipeline never blocks on a normalizer bug.
    try:
        from .source_normalizers import normalize_to_cprs
        normalized = normalize_to_cprs(clinical_text, source_format)
        if normalized and normalized != clinical_text:
            print(
                f"  Source-format normalization applied: "
                f"{source_format} -> cprs ({len(clinical_text)} -> "
                f"{len(normalized)} chars)"
            )
            clinical_text = normalized
    except Exception as _e:
        logger.warning(f"Source normalization skipped: {_e}")

    clinical_document = clinical_text  # Alias for backward compatibility

    # Extract visit date if prepended to document (from batch processing)
    import re as _re
    _visit_date_match = _re.match(r'^VISIT DATE:\s*(\S+)\s*\n', clinical_document)
    _visit_date = _visit_date_match.group(1) if _visit_date_match else ""

    print("\n" + "="*80)
    print("BUILDING UROLOGY NOTE - New Agent-Based Architecture")
    if _visit_date:
        print(f"VISIT DATE: {_visit_date}")
    print("="*80)

    # Step 1: Identify notes
    print("\n[1/5] Identifying notes...")
    notes_dict = identify_notes(clinical_document)
    gu_count = len(notes_dict["gu_notes"])
    non_gu_count = len(notes_dict["non_gu_notes"])
    consult_count = len(notes_dict.get("consult_requests", []))
    print(f"      Found {gu_count} GU notes, {non_gu_count} non-GU notes, and {consult_count} consult requests")

    # Determine if this is a consult
    is_consult = consult_count > 0

    # Step 2: Extract data from notes
    print("\n[2/5] Extracting data from notes...")
    gu_notes = process_gu_notes(notes_dict["gu_notes"], visit_date=_visit_date)
    non_gu_notes = process_non_gu_notes(notes_dict["non_gu_notes"])
    print(f"      Processed {len(gu_notes)} GU note dictionaries")
    print(f"      Processed {len(non_gu_notes)} non-GU note dictionaries")

    # Step 2b: Scan non-GU notes for urologically-relevant cross-specialty content
    print("\n[2b/5] Scanning non-GU notes for urologic content...")
    cross_specialty_results = scan_non_gu_notes_for_urologic_content(notes_dict["non_gu_notes"])
    cross_specialty_context = format_cross_specialty_context(cross_specialty_results)
    if cross_specialty_results:
        specialties_found = set(r.get("specialty", "Unknown") for r in cross_specialty_results)
        print(f"      Found urologic content in {len(cross_specialty_results)} non-GU notes")
        print(f"      Specialties: {', '.join(specialties_found)}")
    else:
        print(f"      No urologic content found in non-GU notes")

    # Step 3: Extract document-level data
    print("\n[3/5] Extracting document-level data...")

    # Initialize PCP note variables
    pcp_note_content = None
    pcp_data = None

    # NEW: For consult requests, use document classifier to extract from PCP notes
    if is_consult:
        print("      Using document classifier for consult request...")
        classifier = DocumentClassifier()
        classification = classifier.classify_document(clinical_document)

        # Extract PCP note content if present
        pcp_note_content = classifier.extract_document_segment(clinical_document, "PRIMARY_CARE_NOTE")

        if pcp_note_content:
            print(f"      Found PCP note ({len(pcp_note_content)} chars) - extracting data...")
            pcp_extractor = PCPNoteExtractor()
            pcp_data = pcp_extractor.extract_all(pcp_note_content)
            # Note: surgical history and dietary will be synthesized later

        # For consults, always extract social and family from full document
        # (they're in the consult request body, not PCP note)
        # Use change detection to flag differences from prior A&P statements
        document_social = extract_social_with_change_detection(clinical_document, clinical_document)
        document_family = extract_family(clinical_document)
    else:
        # For regular clinic notes, use standard extraction with change detection
        # Pass full document for A&P comparison to flag social history changes
        document_social = extract_social_with_change_detection(clinical_document, clinical_document)
        document_family = extract_family(clinical_document)

    document_pmh = extract_pmh(clinical_document)
    document_psh = extract_psh(clinical_document)
    document_medications = extract_medications(clinical_document)
    document_pathology = extract_pathology(clinical_document)
    document_imaging = extract_imaging(clinical_document)
    document_psa = extract_psa(clinical_document)
    document_labs = extract_labs(clinical_document, visit_date=_visit_date)
    document_stone_labs = extract_stone_labs(clinical_document)
    document_calcium = extract_calcium_series(clinical_document)
    document_endocrine = extract_endocrine_labs(clinical_document)
    document_dietary = extract_diet(clinical_document)
    document_allergies = extract_allergies_from_document(clinical_document)
    document_sexual = extract_sexual(clinical_document)

    print(f"      PMH: {len(document_pmh.split(chr(10)) if document_pmh else [])} diagnoses")
    print(f"      Medications: {len(document_medications.split(chr(10)) if document_medications else [])} meds")
    print(f"      Pathology: {'Found' if document_pathology else 'None'}")
    print(f"      Imaging: {'Found' if document_imaging else 'None'}")
    print(f"      PSA: {'Found' if document_psa else 'None'}")
    print(f"      Labs: {'Found' if document_labs else 'None'}")
    print(f"      Stone Labs: {'Found' if document_stone_labs else 'None'}")
    print(f"      Calcium Series: {'Found' if document_calcium else 'None'}")
    print(f"      Endocrine: {'Found' if document_endocrine else 'None'}")
    print(f"      Social: {'Found' if document_social else 'None'}")
    print(f"      Family: {'Found' if document_family else 'None'}")
    print(f"      Dietary: {'Found' if document_dietary else 'None'}")
    print(f"      Allergies: {'Found' if document_allergies else 'None'}")
    print(f"      Sexual: {'Found' if document_sexual else 'None'}")

    # Pre-LLM defense layer for the HPI agent.
    # Compose a deterministic-only Stage 1 stub from the just-extracted
    # PMH + PSH + pathology and run the fact extractor on it. The HPI
    # agent receives the rendered ground-truth block at the top of its
    # context plus an ABSOLUTE-RULES directive in its instructions, and
    # the prior-context artifacts that get fed into the HPI prompt
    # (visit_progression / prior_ap_context_for_hpi / cross_specialty)
    # are sanitized against the verdict to break the feedback loop where
    # last visit's hallucinated A&P resurfaces as this visit's HPI.
    _deterministic_stub_for_hpi = (
        "PAST MEDICAL HISTORY:\n" + (document_pmh or "") + "\n\n"
        "PAST SURGICAL HISTORY:\n" + (document_psh or "") + "\n\n"
        "PATHOLOGY RESULTS:\n" + (document_pathology or "") + "\n"
    )
    # Pass the raw clinical_document too. This catches treatments that are
    # documented only in narrative HPI / prior-Assessment / problem-list
    # text — the most common shape for radiation and ADT histories. The
    # raw scanner is gated by strict prostate-cancer co-occurrence rules
    # so dermatology cryotherapy etc. cannot trip it.
    _hpi_patient_facts = extract_patient_status_facts(
        _deterministic_stub_for_hpi,
        raw_clinical_text=clinical_document,
    )
    _hpi_authoritative_facts = format_facts_for_prompt(_hpi_patient_facts)
    print(f"      Patient facts (for HPI): cancer={_hpi_patient_facts.cancer_status}, "
          f"naive={_hpi_patient_facts.treatment_naive}, "
          f"phoenix={_hpi_patient_facts.phoenix_applicable}")

    # Step 4: Synthesize all sections
    print("\n[4/5] Synthesizing sections...")

    # Extract CC and HPI from consult if present
    is_gu_consult = False
    consult_cc = None
    consult_hpi = None
    consult_data = None
    provider_urologic_context = None
    patient_name = None
    patient_ssn = None
    patient_age = None
    patient_sex = None
    patient_race = None

    # ======================================================================
    # EXTRACT PATIENT DEMOGRAPHICS (for BOTH consult AND clinic notes)
    # Primary sources: AUTOMATED RESULTS LETTER, TELEPHONE NOTE
    # These contain reliable patient name, SSN, age, sex, and race
    # ======================================================================
    from .extractors.consult_request_extractor import ConsultRequestExtractor
    demographics_extractor = ConsultRequestExtractor()
    demographics = demographics_extractor.extract_patient_demographics(clinical_document)

    if demographics:
        patient_name = demographics.get('patient_name_formatted')
        patient_ssn = demographics.get('ssn')
        patient_age = demographics.get('age')
        patient_sex = demographics.get('sex')
        patient_race = demographics.get('race')

    # Calculate accurate age from DOB and Date of Service. Computed age
    # ALWAYS wins over chart-text age when DOB is available — the
    # chart-text age comes from "most common Age:" markers across the
    # source notes, which may be stale (from prior visits where the
    # patient was younger). When visit_date is missing, today's date is
    # the date of service (this is what's being documented right now).
    from datetime import datetime
    # Try multiple DOB formats commonly seen in VA charts:
    #   "DOB: 03/09/1950", "Date of Birth: 03-09-1950", "DOB:1950-03-09",
    #   "DOB MMM DD,YYYY".
    dob = None
    dob_str_found = None
    dob_match = _re.search(
        r'(?:DOB|Date\s+of\s+[Bb]irth)\s*[:=]\s*'
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        r'|\d{4}[/-]\d{1,2}[/-]\d{1,2}'
        r'|[A-Za-z]{3}\s+\d{1,2}\s*,?\s*\d{4})',
        clinical_document,
    )
    if dob_match:
        dob_str_found = dob_match.group(1).strip()
        for fmt in (
            '%m/%d/%Y', '%m/%d/%y',
            '%m-%d-%Y', '%m-%d-%y',
            '%Y-%m-%d', '%Y/%m/%d',
            '%b %d, %Y', '%b %d %Y', '%B %d, %Y',
        ):
            try:
                dob = datetime.strptime(dob_str_found.replace('-', '/').replace(',', ''),
                                        fmt.replace('-', '/').replace(',', ''))
                break
            except ValueError:
                continue

    visit_dt = None
    if _visit_date:
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
            try:
                visit_dt = datetime.strptime(_visit_date, fmt)
                break
            except ValueError:
                continue
    if visit_dt is None:
        # Fall back to today as the date of service. The note we're
        # generating reflects TODAY's visit, so today is the correct
        # default when no explicit visit_date was provided.
        visit_dt = datetime.now()

    if dob:
        age_at_visit = visit_dt.year - dob.year
        if (visit_dt.month, visit_dt.day) < (dob.month, dob.day):
            age_at_visit -= 1
        # MEDICAL DOB CENTURY PIVOT. Python's %y parses 2-digit years
        # with a POSIX pivot at 69 (00-68 → 2000s, 69-99 → 1900s). This
        # is wrong for medical DOBs: a patient with "DOB: 1/29/43" was
        # born in 1943, not 2043. When the naive parse produces an
        # impossible age (negative, > 130), shift the year back by 100.
        # We also catch the symmetric case where a young patient's DOB
        # would be parsed as the 1900s but the year > current 2-digit
        # year (e.g. "DOB: 01/15/05" in 2026 should be 2005, not 1905
        # — Python's pivot already handles that, but the guard below
        # is the same loop pattern for safety).
        while age_at_visit < 0 or age_at_visit > 130:
            if age_at_visit < 0:
                # Shift DOB back a century.
                from datetime import datetime as _dt
                try:
                    dob = dob.replace(year=dob.year - 100)
                except ValueError:
                    break
                age_at_visit = visit_dt.year - dob.year
                if (visit_dt.month, visit_dt.day) < (dob.month, dob.day):
                    age_at_visit -= 1
            else:  # > 130 — shift forward a century
                try:
                    dob = dob.replace(year=dob.year + 100)
                except ValueError:
                    break
                age_at_visit = visit_dt.year - dob.year
                if (visit_dt.month, visit_dt.day) < (dob.month, dob.day):
                    age_at_visit -= 1
        if age_at_visit != patient_age:
            print(
                f"      Age corrected: chart-text age={patient_age!r} -> "
                f"computed age={age_at_visit} from DOB {dob_str_found} + "
                f"DOS {visit_dt.strftime('%Y-%m-%d')}"
            )
        patient_age = str(age_at_visit)
    elif patient_age:
        print(
            f"      WARNING: Age {patient_age!r} taken from chart text "
            f"(no DOB found). May be stale if the source contains old "
            f"notes; verify against patient banner."
        )

    if patient_name or patient_ssn or patient_age:
        print(f"      Patient: {patient_name} (SSN: {patient_ssn}, Age: {patient_age}, Sex: {patient_sex}, Race: {patient_race})")
    else:
        print(f"      Patient demographics: Not found in document")

    # ======================================================================
    # CONSULT-SPECIFIC PROCESSING
    # ======================================================================
    if is_consult:
        consult_content = notes_dict["consult_requests"][0]["content"]

        # NEW: Use enhanced SURG-GU detection per instructions.txt
        # SURG-GU identifier ALWAYS starts with "SURG-GU" in To Service or Orderable Item
        is_gu_consult = is_urology_consult(consult_content)
        print(f"      Detected {'SURG-GU (Urology)' if is_gu_consult else 'non-GU'} consult")

        # NEW: Extract all 9 consult tags per instructions.txt
        consult_data = extract_consult_request(consult_content)
        if consult_data:
            # CC = Provisional Diagnosis (per instructions.txt)
            consult_cc = consult_data.get("CC")  # Already maps to provisional_diagnosis
            consult_hpi = consult_data.get("HPI")  # Combined Reason for Request + Reason for Consult Request
            print(f"      Extracted CC from Provisional Diagnosis: {consult_cc[:50] if consult_cc else 'None'}...")

            # Log extracted consult tags
            print(f"      Current PC Provider: {consult_data.get('current_pc_provider', 'Not found')}")
            print(f"      Requesting Provider: {consult_data.get('requesting_provider', 'Not found')}")
            print(f"      To Service: {consult_data.get('to_service', 'Not found')}")
            print(f"      Orderable Item: {consult_data.get('orderable_item', 'Not found')}")

            # NEW: Scan provider notes for urologic content per instructions.txt
            # "scan for any notes from either the requesting physician or the Current PC Provider"
            providers_to_scan = consult_data.get('providers_to_scan', [])
            if providers_to_scan:
                print(f"      Scanning notes from providers: {', '.join(providers_to_scan)}")
                provider_urologic_context = scan_provider_notes_for_urologic_content(
                    clinical_document,
                    providers_to_scan
                )
                if provider_urologic_context:
                    print(f"      Found urologic context from provider notes: {len(provider_urologic_context)} chars")
                else:
                    print(f"      No urologic content found in provider notes")

            # Override demographics from consult data if available and not already found
            # (consult_data extraction might find additional info from consult-specific fields)
            if not patient_name and consult_data.get('patient_name'):
                patient_name = consult_data.get('patient_name')
            if not patient_ssn and consult_data.get('ssn'):
                patient_ssn = consult_data.get('ssn')
            if not patient_age and consult_data.get('age'):
                patient_age = consult_data.get('age')
            if not patient_sex and consult_data.get('sex'):
                patient_sex = consult_data.get('sex')
            if not patient_race and consult_data.get('race'):
                patient_race = consult_data.get('race')

    # CC + HPI synthesis is deferred into the parallel-synthesis block
    # below (see synthesis_tasks['cc']/['hpi']) so the LLM call(s) run
    # concurrently with the other ~18 agents instead of sequentially
    # before them. With cloud thinking models this saves 30-90s of wall
    # time on note generation. The fast-path values (consult_cc,
    # consult_hpi) are still used directly when present.

    # Analyze visit progression (what changed since last urology visit)
    # This is for followup visits - skip for consults (new patients)
    visit_progression = ""
    prior_ap_context_for_hpi = ""
    if not is_consult and gu_notes:
        print("      Analyzing visit progression...")
        visit_progression = analyze_visit_progression(
            prior_gu_notes=notes_dict["gu_notes"],
            current_clinical_data={
                "psa": document_psa,
                "pathology": document_pathology,
                "imaging": document_imaging,
                "labs": document_labs,
                "medications": document_medications,
            }
        )
        if visit_progression:
            print(f"      Visit progression: {len(visit_progression)} chars")
        else:
            print("      No prior plan found for progression analysis")

        # Extract prior Assessment & Plan context for HPI synthesis
        # This provides temporal continuity for followup visits
        print("      Extracting prior A&P context for HPI...")
        prior_assessments = []
        prior_plans = []
        # Recency filter: when any GU note from the last 18 months has
        # an A or P, drop A/P from older notes. Without this, a 2020
        # consult's A&P (e.g., "scrotal US, urology referral for
        # testicular pain") is fed to the Stage-2 synthesizer as a
        # peer of the most-recent followup A&P, biasing today's plan
        # toward stale concerns.
        from datetime import datetime as _dt2, timedelta as _td2
        _cutoff = _dt2.now() - _td2(days=548)
        def _gnote_dt(n):
            d = (n.get("_source_date") or n.get("date") or "").strip()
            if not d:
                return None
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return _dt2.strptime(d, fmt)
                except (ValueError, TypeError):
                    continue
            return None
        _notes_for_ap = notes_dict["gu_notes"]
        if any(_gnote_dt(n) and _gnote_dt(n) >= _cutoff
               for n in notes_dict["gu_notes"]):
            _notes_for_ap = [
                n for n in notes_dict["gu_notes"]
                if (_gnote_dt(n) is None) or (_gnote_dt(n) >= _cutoff)
            ]
        for note in _notes_for_ap:
            note_content = note.get("content", "")
            assessment = extract_assessment(note_content)
            plan = extract_plan(note_content)
            if assessment and assessment.strip():
                prior_assessments.append(assessment)
            if plan and plan.strip():
                prior_plans.append(plan)

        if prior_assessments or prior_plans:
            # use_llm=False for Stage 1 - faster regex-only extraction
            # Full LLM synthesis happens in Stage 2 for Assessment/Plan
            prior_ap_context = synthesize_prior_ap_context(
                prior_assessments=prior_assessments,
                prior_plans=prior_plans,
                patient_age=patient_age,
                patient_sex=patient_sex,
                use_llm=False  # Skip LLM call in Stage 1 for performance
            )
            prior_ap_context_for_hpi = format_prior_ap_for_hpi(prior_ap_context)
            if prior_ap_context_for_hpi:
                print(f"      Prior A&P context for HPI: {len(prior_ap_context_for_hpi)} chars")
            else:
                print("      No prior A&P context generated")
        else:
            print("      No prior assessments or plans found in GU notes")

    # HPI synthesis is also deferred into the parallel block — see
    # synthesis_tasks['hpi'] below. The branch logic (consult vs.
    # clinic) is captured inside the closure so the dispatch happens at
    # task-execution time.

    # =========================================================================
    # PARALLEL SYNTHESIS EXECUTION
    # All remaining synthesis agents are independent and can run concurrently
    # This reduces total time from sequential sum to ~max single agent time
    # =========================================================================
    print("      Running parallel synthesis agents...")
    parallel_start = time.time()

    # Define synthesis tasks as lambdas to capture current context
    # Each task returns (key, result) tuple for easy result collection
    synthesis_tasks: Dict[str, Callable] = {}

    # CC + HPI deferred to the parallel block (2026-05-06 perf change).
    # Both LLM calls were previously sequential before this block, adding
    # 30-90s of wall time on cloud thinking models. The branch logic
    # (consult vs. clinic) is captured inside the closures so dispatch
    # happens at task-execution time.
    _consult_cc_val = consult_cc
    _consult_hpi_val = consult_hpi
    _is_consult_val = is_consult
    _consult_data_val = consult_data
    _patient_name_val = patient_name
    _patient_age_val = patient_age
    _patient_sex_val = patient_sex
    _doc_pmh = document_pmh
    _doc_psa = document_psa
    _doc_path = document_pathology
    _doc_labs = document_labs
    _doc_imaging = document_imaging
    _doc_meds = document_medications
    _pcp_note_content = pcp_note_content
    _pcp_data = pcp_data
    _prov_uro_context = provider_urologic_context
    # Sanitize prior-derived contexts against the ground-truth facts BEFORE
    # they reach the HPI synthesis closure. This is the prior-LLM-hallucination
    # firewall: a previous run's "completed focal therapy" sentence sitting in
    # the visit_progression analysis or prior_ap_context cannot resurface as
    # this run's HPI claim if the ground-truth verdict contradicts it.
    def _sanitize_for_hpi(label: str, text: str) -> str:
        if not text or not text.strip():
            return text
        cleaned, stripped = sanitize_context_against_facts(text, _hpi_patient_facts)
        for s in stripped:
            print(f"      ✂ stripped from {label} (HPI input): {s[:140]}")
        return cleaned

    _cross_specialty_context = _sanitize_for_hpi("cross_specialty_context", cross_specialty_context)
    _visit_progression = _sanitize_for_hpi("visit_progression", visit_progression)
    _prior_ap_for_hpi = _sanitize_for_hpi("prior_ap_context_for_hpi", prior_ap_context_for_hpi)
    _hpi_auth_facts = _hpi_authoritative_facts
    _hpi_pf = _hpi_patient_facts

    # PHASE 2: build the deterministic HPI story skeleton and pass it to
    # the HPI agent as a structured rendering target. The agent's prompt
    # now treats the skeleton as authoritative — every event in the
    # skeleton must appear in the rendered HPI, and the agent may not
    # invent events not in the skeleton.
    try:
        from .hpi_skeleton import build_hpi_skeleton, format_skeleton_for_prompt
        _hpi_skeleton_obj = build_hpi_skeleton(
            facts=_hpi_pf,
            raw_clinical_text=clinical_document,
            patient_name=patient_name or "",
            age=str(patient_age or ""),
            sex=patient_sex or "",
            pathology_data=document_pathology or "",
            gu_notes=gu_notes,
        )
        _hpi_skeleton_text = format_skeleton_for_prompt(_hpi_skeleton_obj)
        print(
            f"      HPI skeleton built: phase={_hpi_skeleton_obj.phase}, "
            f"timeline events={len(_hpi_skeleton_obj.prior_treatment_events)}, "
            f"regimen items={len(_hpi_skeleton_obj.current_regimen)}, "
            f"procedure findings={len(_hpi_skeleton_obj.procedure_findings_text)}"
        )
    except Exception as _e:
        logger.warning(f"HPI skeleton build failed (non-fatal): {_e}")
        _hpi_skeleton_text = None

    _doc_psh_cc = document_psh
    _clinical_doc_cc = clinical_document

    def _build_cc():
        if _consult_cc_val:
            return _consult_cc_val
        # Pass urologic clinical context so synthesize_cc can:
        #   - derive a CC from PMH / pathology / PSA when no GU-note CC
        #     is available (or all extracted CCs are non-urologic), and
        #   - reframe stale "persistent / rising PSA / elevated PSA"
        #     CCs to "Follow-up after <treatment> for prostate cancer"
        #     when PSH or the raw document shows definitive treatment
        #     was completed AND the PSA trend confirms biochemical
        #     response. Without document_psh + clinical_document the
        #     reframe path can't see treatment history at all.
        return synthesize_cc(
            gu_notes,
            non_gu_notes,
            document_pmh=_doc_pmh,
            document_pathology=_doc_path,
            document_psa=_doc_psa,
            document_psh=_doc_psh_cc,
            clinical_document=_clinical_doc_cc,
            current_phase=_hpi_pf.current_phase if _hpi_pf else None,
            current_active_treatments=(
                _hpi_pf.current_active_treatments if _hpi_pf else None
            ),
            clinical_timeline=(
                _hpi_pf.clinical_timeline if _hpi_pf else None
            ),
        )

    def _build_hpi():
        if _is_consult_val and _consult_hpi_val:
            reason_for_request = (
                _consult_data_val.get('reason_for_request', '')
                if _consult_data_val else ''
            )
            return synthesize_consult_hpi(
                consult_reason=_consult_hpi_val,
                patient_name=_patient_name_val,
                patient_age=_patient_age_val,
                patient_sex=_patient_sex_val,
                pmh=_doc_pmh,
                psh=None,
                medications=_doc_meds,
                imaging=_doc_imaging,
                pcp_note_data=_pcp_data if _is_consult_val and _pcp_note_content else None,
                provider_urologic_context=_prov_uro_context,
                reason_for_request=reason_for_request,
                psa_data=_doc_psa,
                pathology_data=_doc_path,
                labs_data=_doc_labs,
            )
        v1_text = synthesize_hpi(
            gu_notes, non_gu_notes,
            psa_data=_doc_psa,
            pathology_data=_doc_path,
            labs_data=_doc_labs,
            imaging_data=_doc_imaging,
            cross_specialty_context=_cross_specialty_context,
            visit_progression=_visit_progression,
            prior_ap_context=_prior_ap_for_hpi,
            # New: feed PSH + raw document so HPI agent can build the
            # deterministic TREATMENT STATUS block. Forces the LLM to
            # narrate completed treatment instead of regurgitating an
            # older "awaiting treatment" snapshot.
            psh_data=document_psh,
            clinical_document=clinical_document,
            patient_name=_patient_name_val,
            patient_age=_patient_age_val,
            patient_sex=_patient_sex_val,
            authoritative_facts=_hpi_auth_facts,
            patient_facts=_hpi_pf,
            hpi_skeleton=_hpi_skeleton_text,
        )

        # ---- HPI v2 (constrained-JSON) path ----
        # Gated by VAUCDA_HPI_V2=1 env var. v2 has v1 text as its
        # fallback, so any v2 failure transparently degrades to v1.
        import os as _os
        if _os.environ.get("VAUCDA_HPI_V2", "0") != "1":
            return v1_text

        try:
            from .agents.hpi_agent_v2 import build_ground_truth, generate_hpi_v2
            from .llm_helper import synthesize_with_llm as _synth
            from dataclasses import replace as _dc_replace

            # JSON output is more verbose than v1 prose (schema overhead
            # plus structural braces). Default max_tokens often truncates
            # the trailing `}` of a 30+-line JSON object — give v2 headroom.
            _v2_task_config = (
                _dc_replace(task_config, max_tokens=max(task_config.max_tokens, 4096))
                if task_config is not None else None
            )

            def _llm_call(prompt: str) -> str:
                return _synth(prompt=prompt, temperature=0.0,
                              task_config=_v2_task_config)

            gt = build_ground_truth(
                patient_name=_patient_name_val or "",
                patient_age=int(_patient_age_val) if str(_patient_age_val or "").isdigit() else 0,
                patient_sex=_patient_sex_val or "",
                visit_date=_visit_date,
                psa_data=_doc_psa or "",
                psh_text=document_psh or "",
                pmh_text=_doc_pmh or "",
                pathology_text=_doc_path or "",
                medications_text=_doc_meds or "",
                imaging_text=_doc_imaging or "",
                procedure_findings=(_hpi_pf.procedure_findings if _hpi_pf else []),
                treatment_naive=(_hpi_pf.treatment_naive if _hpi_pf else True),
            )
            result = generate_hpi_v2(gt, _llm_call, max_retries=2,
                                     v1_fallback_text=v1_text)
            print(f"      HPI v2: {'fallback' if result.used_fallback else 'accepted'} "
                  f"after {len(result.attempts)} attempt(s)"
                  + (f" — {result.fallback_reason}" if result.used_fallback else ""))
            return result.hpi_text
        except Exception as _e:
            logger.warning(f"HPI v2 path failed (using v1): {_e}")
            return v1_text

    synthesis_tasks['cc'] = _build_cc
    synthesis_tasks['hpi'] = _build_hpi

    # IPSS synthesis
    # Capture _visit_date in closure
    _vd = _visit_date
    synthesis_tasks['ipss'] = lambda: synthesize_ipss(gu_notes, visit_date=_vd)

    # Dietary - prefer document-level extraction, then GU notes
    if document_dietary:
        synthesis_tasks['dhx'] = lambda: document_dietary
    else:
        synthesis_tasks['dhx'] = lambda: synthesize_diet(gu_notes)

    # PMH synthesis
    synthesis_tasks['pmh'] = lambda: synthesize_pmh(document_pmh, gu_notes, non_gu_notes)

    # PSH synthesis - consult vs clinic logic
    if is_consult and document_psh:
        synthesis_tasks['psh'] = lambda: synthesize_psh([{"PSH": document_psh}], [])
    else:
        synthesis_tasks['psh'] = lambda: synthesize_psh(gu_notes, non_gu_notes)

    # Social/Family - consult prefers document-level data
    if is_consult:
        if document_social:
            synthesis_tasks['social'] = lambda: document_social
        else:
            synthesis_tasks['social'] = lambda: synthesize_social(gu_notes, non_gu_notes)
        if document_family:
            synthesis_tasks['family'] = lambda: document_family
        else:
            synthesis_tasks['family'] = lambda: synthesize_family(gu_notes, non_gu_notes)
    else:
        synthesis_tasks['social'] = lambda: synthesize_social(gu_notes, non_gu_notes)
        synthesis_tasks['family'] = lambda: synthesize_family(gu_notes, non_gu_notes)

    # PSA synthesis - prefer document-level
    if document_psa:
        # Need to capture document_psa in closure properly
        _doc_psa = document_psa
        synthesis_tasks['psa'] = lambda: synthesize_psa([{"PSA": _doc_psa}])
    else:
        synthesis_tasks['psa'] = lambda: synthesize_psa(gu_notes)

    # Lab-related synthesis
    if is_consult:
        if document_endocrine:
            synthesis_tasks['endocrine'] = lambda: document_endocrine
        else:
            synthesis_tasks['endocrine'] = lambda: synthesize_endocrine_labs(gu_notes)
        if document_labs:
            synthesis_tasks['labs'] = lambda: document_labs
        else:
            synthesis_tasks['labs'] = lambda: synthesize_general_labs(gu_notes)
        if document_stone_labs:
            synthesis_tasks['stone'] = lambda: document_stone_labs
        else:
            synthesis_tasks['stone'] = lambda: synthesize_stone_labs(gu_notes)
    else:
        if document_endocrine:
            synthesis_tasks['endocrine'] = lambda: document_endocrine
        else:
            synthesis_tasks['endocrine'] = lambda: synthesize_endocrine_labs(gu_notes)
        if document_labs:
            synthesis_tasks['labs'] = lambda: document_labs
        else:
            synthesis_tasks['labs'] = lambda: synthesize_general_labs(gu_notes)
        if document_stone_labs:
            synthesis_tasks['stone'] = lambda: document_stone_labs
        else:
            synthesis_tasks['stone'] = lambda: synthesize_stone_labs(gu_notes)

    # Other independent synthesis agents
    _doc_sexual = document_sexual
    synthesis_tasks['sexual'] = lambda: synthesize_sexual(
        gu_notes, non_gu_notes, document_sexual=_doc_sexual
    )

    # Capture document_pathology in closure
    _doc_path = document_pathology
    synthesis_tasks['pathology'] = lambda: synthesize_pathology(_doc_path, gu_notes)

    synthesis_tasks['testosterone'] = lambda: synthesize_testosterone(gu_notes)

    # Capture document_medications in closure
    _doc_meds = document_medications
    synthesis_tasks['medications'] = lambda: synthesize_medications(_doc_meds, gu_notes)

    # Capture document_allergies in closure
    _doc_allergies = document_allergies
    synthesis_tasks['allergies'] = lambda: synthesize_allergies(gu_notes, non_gu_notes, document_allergies=_doc_allergies)

    # Capture document_imaging in closure
    _doc_imaging = document_imaging
    _proc_findings = _hpi_pf.procedure_findings if _hpi_pf else []
    synthesis_tasks['imaging'] = lambda: synthesize_imaging(
        _doc_imaging, gu_notes, procedure_findings=_proc_findings,
    )

    synthesis_tasks['ros'] = lambda: synthesize_ros(gu_notes, non_gu_notes)

    # Capture patient_sex in closure
    _pat_sex = patient_sex
    synthesis_tasks['pe'] = lambda: synthesize_pe(gu_notes, non_gu_notes, patient_sex=_pat_sex)

    # Execute all synthesis tasks in parallel using ThreadPoolExecutor
    # Max workers = number of tasks for full parallelization.
    #
    # CRITICAL: capture the parent thread's task_config (set by
    # set_current_task_config earlier in this function) and re-establish
    # it inside each worker via run_with_task_config. ThreadPoolExecutor
    # worker threads do NOT inherit threading.local state from the
    # parent, so without this wrapper every sub-agent call would fall
    # through synthesize_with_llm's legacy path to
    # settings.OLLAMA_DEFAULT_MODEL (historically llama3.1:8b),
    # bypassing the user's configured Stage 2 model — both clinically
    # wrong (different model than user requested) and dangerous (the
    # legacy 8B model loaded at its training-max context has wedged
    # the GPU multiple times in production).
    parent_task_config = get_current_task_config()
    results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=min(len(synthesis_tasks), 16)) as executor:
        # Submit each task wrapped so the worker thread re-establishes
        # parent_task_config before invoking the actual synthesis lambda.
        future_to_key = {
            executor.submit(run_with_task_config, parent_task_config, task): key
            for key, task in synthesis_tasks.items()
        }

        # Collect results as they complete
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:
                print(f"      WARNING: {key} synthesis failed: {e}")
                results[key] = ""

    # Extract results to named variables
    cc = results.get('cc', '')
    hpi = results.get('hpi', '')
    ipss = results.get('ipss', '')
    dhx = results.get('dhx', '')
    pmh = results.get('pmh', '')
    psh = results.get('psh', '')
    social = results.get('social', '')
    family = results.get('family', '')
    psa = results.get('psa', '')
    endocrine = results.get('endocrine', '')
    labs = results.get('labs', '')
    stone = results.get('stone', '')
    sexual = results.get('sexual', '')
    pathology = results.get('pathology', '')
    testosterone = results.get('testosterone', '')
    medications = results.get('medications', '')
    allergies = results.get('allergies', '')
    imaging = results.get('imaging', '')
    ros = results.get('ros', '')
    pe = results.get('pe', '')

    parallel_time = time.time() - parallel_start
    print(f"      CC: {len(cc) if cc else 0} chars")
    print(f"      HPI: {len(hpi) if hpi else 0} chars")
    print(f"      IPSS: {len(ipss) if ipss else 0} chars")
    # Note: Assessment and Plan are NOT generated in Stage 1 - they are completed during/after the visit

    print(f"      Parallel synthesis completed in {parallel_time:.2f}s ({len(synthesis_tasks)} agents)")

    # Step 5: Assemble final note
    print("\n[5/5] Assembling final note...")
    final_note = assemble_note(
        cc=cc,
        hpi=hpi,
        ipss=ipss,
        dhx=dhx,
        pmh=pmh,
        psh=psh,
        social=social,
        family=family,
        sexual=sexual,
        psa=psa,
        pathology=pathology,
        testosterone=testosterone,
        medications=medications,
        allergies=allergies,
        endocrine=endocrine,
        stone=stone,
        labs=labs,
        imaging=imaging,
        ros=ros,
        pe=pe,
        is_consult=is_consult,
        is_gu_consult=is_gu_consult,
        patient_name=patient_name,
        patient_ssn=patient_ssn,
        patient_age=patient_age,
        patient_sex=patient_sex,
        patient_race=patient_race
        # Note: Assessment and Plan are NOT included in Stage 1 preliminary note
    )

    print(f"      Final note: {len(final_note)} characters")

    # Step 5b: Second-pass consistency check
    # Reads the assembled note + authoritative facts, returns a JSON
    # list of inconsistencies, applies them deterministically.
    # Disabled by setting VAUCDA_CONSISTENCY_CHECK=0 in env.
    import os as _os
    if _os.environ.get("VAUCDA_CONSISTENCY_CHECK", "1") != "0":
        try:
            from .agents.consistency_checker import run_consistency_check
            print("\n[5b/5] Running consistency check...")
            _cc_result = run_consistency_check(
                stage1_note=final_note,
                authoritative_facts=_hpi_authoritative_facts,
                task_config=task_config,
            )
            if _cc_result.findings:
                print(
                    f"      Findings: {len(_cc_result.findings)} "
                    f"({_cc_result.applied_actions} applied, "
                    f"{_cc_result.flag_only_count} flag-only)"
                )
                for _f in _cc_result.findings:
                    print(f"        - [{_f.issue}] {_f.action}: {_f.evidence[:100]}")
                final_note = _cc_result.applied_note
            else:
                print("      No inconsistencies found")
        except Exception as _e:
            logger.warning(f"Consistency check skipped: {_e}")

    print("\n" + "="*80)
    print("NOTE BUILDING COMPLETE")
    print("="*80)

    # Clear the task config to prevent leaks between requests
    set_current_task_config(None)

    # ASCII-safety pass: convert Unicode look-alikes (en/em-dashes,
    # curly quotes, NBSP, ellipsis, ...) to ASCII equivalents so the
    # note pastes cleanly into VistA / CPRS. See text_normalizer.py.
    from .text_normalizer import to_vista_ascii
    return to_vista_ascii(final_note)


def _group_labs_by_date(labs_text: str) -> str:
    """
    Group lab results by collection date, separated by blank lines.

    Labs come in two formats:
    - "TEST (Mon DD, YYYY): value..." → date in parentheses
    - "TEST  value  units  range  [site] (Mon DD, YYYY)" → date at end

    Labs sharing the same date are grouped together. Groups are separated
    by a blank line, with the most recent group first.
    """
    import re
    from datetime import datetime

    if not labs_text or not labs_text.strip():
        return labs_text

    lines = labs_text.strip().split('\n')

    # Extract date from each line
    date_pattern_parens = re.compile(
        r'\(([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\)'
    )
    date_pattern_inline = re.compile(
        r'(\d{1,2}/\d{1,2}/\d{2,4})\s*:'
    )

    # Group lines by date
    groups = {}  # date_key -> (datetime_obj, [lines])
    no_date_lines = []

    for line in lines:
        if not line.strip():
            continue

        # Try parenthesized date: "(Sep 18, 2025)"
        m = date_pattern_parens.search(line)
        if m:
            date_str = m.group(1)
            # Parse for sorting
            try:
                dt = datetime.strptime(date_str, '%b %d, %Y')
            except ValueError:
                dt = None
            if date_str not in groups:
                groups[date_str] = (dt, [])
            groups[date_str][1].append(line)
            continue

        # Try inline date: "9/4/25: PSA 7.46"
        m = date_pattern_inline.search(line)
        if m:
            date_str = m.group(1)
            try:
                for fmt in ('%m/%d/%Y', '%m/%d/%y'):
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    dt = None
            except Exception:
                dt = None
            if date_str not in groups:
                groups[date_str] = (dt, [])
            groups[date_str][1].append(line)
            continue

        # No date found — keep at end
        no_date_lines.append(line)

    if not groups:
        return labs_text  # No dates found, return as-is

    # Sort groups by date (most recent first), None dates last
    sorted_groups = sorted(
        groups.values(),
        key=lambda x: x[0] or datetime.min,
        reverse=True
    )

    # Build output with blank lines between groups
    result_parts = []
    for _, group_lines in sorted_groups:
        result_parts.append('\n'.join(group_lines))

    if no_date_lines:
        result_parts.append('\n'.join(no_date_lines))

    return '\n\n'.join(result_parts)


def assemble_note(**sections) -> str:
    """
    Assemble the final note from all synthesized sections.

    Args:
        **sections: All note sections as keyword arguments
        is_consult: Boolean flag indicating if this is a consult note
        is_gu_consult: Boolean flag indicating if this is a GU consult (vs non-GU)
        patient_name: Patient name (optional)
        patient_ssn: Full SSN (optional)
        patient_age: Patient age (optional)
        patient_sex: Patient sex - MALE/FEMALE (optional)
        patient_race: Patient race (optional)

    Returns:
        Formatted note following urology_prompt.txt template or consult note template
    """
    note_parts = []
    is_consult = sections.get("is_consult", False)
    is_gu_consult = sections.get("is_gu_consult", True)  # Default to GU if not specified
    patient_name = sections.get("patient_name")
    patient_ssn = sections.get("patient_ssn")
    patient_age = sections.get("patient_age")
    patient_sex = sections.get("patient_sex")
    patient_race = sections.get("patient_race")

    # Patient Header (if available)
    # Format: "Patient: NAME (SSN: XXX-XX-XXXX) | Age: XX | Sex: MALE/FEMALE | Race: XXXX"
    if patient_name or patient_ssn or patient_age or patient_sex:
        header_parts = []
        if patient_name:
            header_parts.append(patient_name)
        if patient_ssn:
            # Show last 4 only for privacy
            ssn_last4 = patient_ssn.split('-')[-1] if patient_ssn and '-' in patient_ssn else patient_ssn
            header_parts.append(f"(SSN: XXX-XX-{ssn_last4})")

        demographics_parts = []
        if patient_age:
            demographics_parts.append(f"Age: {patient_age}")
        if patient_sex:
            demographics_parts.append(f"Sex: {patient_sex}")
        if patient_race:
            demographics_parts.append(f"Race: {patient_race}")

        patient_header = " ".join(header_parts)
        if demographics_parts:
            patient_header += " | " + " | ".join(demographics_parts)

        note_parts.append(f"Patient: {patient_header}\n")

    # CC (always required, always urologic). synthesize_cc never returns
    # empty — it derives a CC from PMH/pathology/PSA when no GU-note CC
    # is available, with "Urology follow-up" as the last-resort sentinel.
    # If for some reason sections["cc"] is still falsy here, render the
    # same sentinel rather than the old non-clinical "Unknown".
    cc_text = sections.get("cc") or "Urology follow-up"
    note_parts.append(f"CC: {cc_text}\n")

    # HPI (always required, always urologic). synthesize_hpi now falls
    # back to a context-only narrative when no GU-note HPI exists but
    # clinical context (PSA / pathology / imaging / etc.) is available.
    # The "Unknown" placeholder is reserved for the rare case where we
    # genuinely have no urologic data at all to write about.
    hpi_text = sections.get("hpi") or "No prior urologic history documented"
    note_parts.append(f"HPI: {hpi_text}\n")

    # Continue with all sections for both consults and clinic notes

    # Determine if patient is female for gender-specific section exclusions
    is_female = patient_sex and patient_sex.upper().strip() in ("FEMALE", "F")

    # IPSS - MALE ONLY (International Prostate Symptom Score is not applicable for female patients)
    # For female patients with voiding symptoms, use OAB-q or other female-specific tools
    if not is_female:
        if sections.get("ipss"):
            note_parts.append(f"IPSS:\n{sections['ipss']}\n")
        else:
            # No IPSS data found - use the empty template from ipss_agent
            from .agents.ipss_agent import get_empty_ipss_template
            note_parts.append(f"IPSS:\n{get_empty_ipss_template()}\n")

    # Dietary History - Only include if documented
    if sections.get("dhx"):
        note_parts.append(f"DIETARY HISTORY:\n{sections['dhx']}\n")
    else:
        # If no dietary history found, indicate not documented (per user feedback - no placeholders)
        note_parts.append("DIETARY HISTORY:\nNot documented\n")

    # Social History
    if sections.get("social"):
        note_parts.append(f"SOCIAL HISTORY:\n{sections['social']}\n")

    # Family History
    if sections.get("family"):
        note_parts.append(f"FAMILY HISTORY:\n{sections['family']}\n")

    # Sexual History — always emit the section header. If extraction
    # produced nothing, render "Not documented" so a silent extraction
    # failure is visible to the provider (mirrors DIETARY HISTORY's
    # behavior above). Previously the entire section was skipped when
    # synthesis returned empty, which made the gap impossible to spot
    # in the rendered note.
    if sections.get("sexual"):
        note_parts.append(f"SEXUAL HISTORY:\n{sections['sexual']}\n")
    else:
        note_parts.append("SEXUAL HISTORY:\nNot documented\n")

    # PMH
    if sections.get("pmh"):
        note_parts.append(f"PAST MEDICAL HISTORY:\n{sections['pmh']}\n")

    # PSH
    if sections.get("psh"):
        note_parts.append(f"PAST SURGICAL HISTORY:\n{sections['psh']}\n")

    # PSA Curve - MALE ONLY (females do not have prostate, no PSA screening)
    if not is_female and sections.get("psa"):
        note_parts.append(f"PSA CURVE:\n{sections['psa']}\n")

    # Medications
    if sections.get("medications"):
        note_parts.append(f"MEDICATIONS:\n{sections['medications']}\n")

    # Allergies
    if sections.get("allergies"):
        note_parts.append(f"\nALLERGIES: {sections['allergies']}\n")

    # Pathology — narrowed by 4 chars to fit CPRS line width
    if sections.get("pathology"):
        note_parts.append(f"\n{'='*74}\nPATHOLOGY RESULTS:\n{sections['pathology']}\n")
    else:
        # Always include pathology section for urology notes
        note_parts.append(f"\n{'='*74}\nPATHOLOGY RESULTS: None documented\n")

    # Testosterone — narrowed by 4 chars to fit CPRS line width
    if sections.get("testosterone"):
        note_parts.append(f"\n{'='*74}\nTESTOSTERONE:\n{sections['testosterone']}\n")

    # Endocrine Labs — narrowed by 4 (2 each side of title) for CPRS width
    if sections.get("endocrine"):
        note_parts.append(f"\n{'='*33}ENDOCRINE LABS {'='*27}\n{sections['endocrine']}\n")

    # Stone Labs - show if patient has stone history OR if stone-specific
    # data (24-hr urine, supersaturations, composition) was extracted
    if sections.get("stone"):
        pmh_text = sections.get("pmh", "").lower()
        has_stone_history = any(term in pmh_text for term in [
            "nephrolithiasis", "kidney stone", "renal calculi", "urolithiasis",
            "calculus", "stone disease", "kidney calculi", "renal stone"
        ])

        stone_text = sections["stone"]
        has_stone_specific_data = any(marker in stone_text for marker in [
            "24-Hour Urine", "Stone Risk", "Stone Composition",
            "Supersaturation", "Litholink", "CaOx", "CaPO4", "Brushite",
        ])

        if has_stone_history or has_stone_specific_data:
            # Narrowed by 4 (2 each side of title) for CPRS width
            note_parts.append(f"\n{'='*30}STONE RELATED LABS {'='*26}\n{sections['stone']}\n")

    # General Labs (moved to after Stone Labs) — narrowed by 4 for CPRS
    if sections.get("labs"):
        grouped_labs = _group_labs_by_date(sections['labs'])
        note_parts.append(f"\n{'='*36} LABS {'='*32}\n{grouped_labs}\n")

    # Imaging — narrowed by 4 (2 each side of title) for CPRS width
    if sections.get("imaging"):
        note_parts.append(f"\n{'='*36} IMAGING {'='*30}\n{sections['imaging']}\n")

    # ROS — narrowed by 4 chars for CPRS width
    if sections.get("ros"):
        note_parts.append(f"\n{'='*73}\n{sections['ros']}\n")

    # PE
    if sections.get("pe"):
        note_parts.append(f"{sections['pe']}\n")

    # Note: Assessment and Plan are NOT included in Stage 1 preliminary note
    # They will be added by the provider during/after the patient visit (Stage 2)

    # Note: Time billing suffix is NOT included in Stage 1 preliminary note
    # It will be added in Stage 2 after Assessment and Plan (via stage2_builder.py)

    # Assemble
    final_note = '\n'.join(note_parts)

    return final_note
