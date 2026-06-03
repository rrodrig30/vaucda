

---

## 7. Note Processing Pipeline

### 7.1 Pipeline Orchestrator

```python
# note_processing/pipeline.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio

from ..epic_fhir.client import AsyncFHIRClient
from ..epic_fhir.fetchers.lab_fetcher import LabFetcher, LabResult
from ..epic_fhir.fetchers.note_fetcher import NoteFetcher, ClinicalNote
from ..epic_fhir.fetchers.imaging_fetcher import ImagingFetcher, ImagingReport
from ..epic_fhir.fetchers.pathology_fetcher import PathologyFetcher, PathologyReport
from ..epic_fhir.fetchers.patient_fetcher import PatientFetcher, PatientDemographics
from ..epic_fhir.fetchers.medication_fetcher import MedicationFetcher, Medication
from ..epic_fhir.fetchers.medication_fetcher import AllergyFetcher, AllergyEntry
from ..epic_fhir.fetchers.history_fetcher import (
    HistoryFetcher, ConditionEntry, ProcedureEntry, FamilyHistoryEntry
)
from ..llm.provider import LLMProvider
from .agents.hpi_agent import synthesize_hpi
from .agents.assessment_agent import synthesize_assessment
from .agents.plan_agent import synthesize_plan
from .agents.psa_agent import build_psa_curve
from .agents.ipss_agent import extract_ipss_scores
from .agents.pathology_agent import synthesize_pathology
from .extractors import (
    extract_allergies_from_fhir,
    extract_medications_from_fhir,
    extract_social_history,
    extract_dietary_history,
    extract_sexual_history,
    extract_ros,
    extract_physical_exam,
)
from ..word_generator.generator import WordDocumentGenerator


@dataclass
class FHIRPatientData:
    """All FHIR-extracted patient data for note generation."""
    demographics: Optional[PatientDemographics] = None
    labs: Dict[str, List[LabResult]] = field(default_factory=dict)
    clinical_notes: List[ClinicalNote] = field(default_factory=list)
    imaging_reports: List[ImagingReport] = field(default_factory=list)
    pathology_reports: List[PathologyReport] = field(default_factory=list)
    medications: List[Medication] = field(default_factory=list)
    allergies: List[AllergyEntry] = field(default_factory=list)
    conditions: List[ConditionEntry] = field(default_factory=list)
    procedures: List[ProcedureEntry] = field(default_factory=list)
    family_history: List[FamilyHistoryEntry] = field(default_factory=list)


@dataclass
class NoteSections:
    """All sections of a structured urology note."""
    chief_complaint: str = ""
    hpi: str = ""
    ipss: Dict[str, Any] = field(default_factory=dict)
    dietary_history: str = ""
    social_history: str = ""
    family_history: str = ""
    sexual_history: str = ""
    past_medical_history: str = ""
    past_surgical_history: str = ""
    psa_curve: str = ""
    testosterone_curve: str = ""
    pathology: str = ""
    medications: str = ""
    allergies: str = ""
    endocrine_labs: str = ""
    stone_labs: str = ""
    general_labs: str = ""
    imaging: str = ""
    ros: str = ""
    physical_exam: str = ""
    assessment: str = ""
    problem_list: List[str] = field(default_factory=list)
    plan: str = ""


@dataclass
class PipelineResult:
    """Result from the 5-stage note processing pipeline."""
    sections: NoteSections
    word_document_bytes: bytes
    metadata: Dict[str, Any]


class NoteProcessingPipeline:
    """Five-stage pipeline for generating urology clinic notes from FHIR data.

    Stage 1: FHIR Data Extraction - Fetch all patient data from EPIC
    Stage 2: Component Extraction - AI agents parse FHIR data into components
    Stage 3: Document-Level Extraction - Extract remaining note sections
    Stage 4: Section Synthesis - Merge multi-source data into unified sections
    Stage 5: Word Document Assembly - Generate formatted .docx output
    """

    def __init__(
        self,
        fhir_client: AsyncFHIRClient,
        llm_provider: LLMProvider,
        word_generator: WordDocumentGenerator,
    ):
        self.fhir_client = fhir_client
        self.llm = llm_provider
        self.word_gen = word_generator

        # Initialize fetchers
        self.lab_fetcher = LabFetcher(fhir_client)
        self.note_fetcher = NoteFetcher(fhir_client)
        self.imaging_fetcher = ImagingFetcher(fhir_client)
        self.pathology_fetcher = PathologyFetcher(fhir_client)
        self.patient_fetcher = PatientFetcher(fhir_client)
        self.med_fetcher = MedicationFetcher(fhir_client)
        self.allergy_fetcher = AllergyFetcher(fhir_client)
        self.history_fetcher = HistoryFetcher(fhir_client)

    async def generate_note(
        self,
        patient_id: str,
        note_type: str = "clinic_note",
        selected_modules: List[str] = None,
        model: Optional[str] = None,
    ) -> PipelineResult:
        """Execute the full 5-stage pipeline.

        Args:
            patient_id: FHIR Patient resource ID
            note_type: Type of note to generate
            selected_modules: Calculator modules to include
            model: LLM model override

        Returns:
            PipelineResult with sections, Word document bytes, and metadata
        """
        start_time = datetime.utcnow()
        metadata = {"patient_id_hash": hash(patient_id), "note_type": note_type}

        # ================================================================
        # STAGE 1: FHIR Data Extraction
        # ================================================================
        fhir_data = await self._stage1_fhir_extraction(patient_id)
        metadata["stage1_duration_ms"] = self._elapsed_ms(start_time)

        # ================================================================
        # STAGE 2: Component Extraction (AI Agents)
        # ================================================================
        stage2_start = datetime.utcnow()
        sections = await self._stage2_component_extraction(fhir_data, model)
        metadata["stage2_duration_ms"] = self._elapsed_ms(stage2_start)

        # ================================================================
        # STAGE 3: Document-Level Extraction
        # ================================================================
        stage3_start = datetime.utcnow()
        sections = await self._stage3_document_extraction(fhir_data, sections)
        metadata["stage3_duration_ms"] = self._elapsed_ms(stage3_start)

        # ================================================================
        # STAGE 4: Section Synthesis
        # ================================================================
        stage4_start = datetime.utcnow()
        sections = await self._stage4_section_synthesis(
            fhir_data, sections, model
        )
        metadata["stage4_duration_ms"] = self._elapsed_ms(stage4_start)

        # ================================================================
        # STAGE 5: Word Document Assembly
        # ================================================================
        stage5_start = datetime.utcnow()
        doc_bytes = self._stage5_word_assembly(
            sections, fhir_data.demographics, note_type
        )
        metadata["stage5_duration_ms"] = self._elapsed_ms(stage5_start)

        metadata["total_duration_ms"] = self._elapsed_ms(start_time)

        return PipelineResult(
            sections=sections,
            word_document_bytes=doc_bytes,
            metadata=metadata
        )

    # ==================================================================
    # STAGE 1: FHIR Data Extraction
    # ==================================================================

    async def _stage1_fhir_extraction(
        self,
        patient_id: str
    ) -> FHIRPatientData:
        """Fetch all patient data from EPIC FHIR concurrently."""
        data = FHIRPatientData()

        # Execute all FHIR queries concurrently for performance
        results = await asyncio.gather(
            self.patient_fetcher.fetch_patient(patient_id),
            self.lab_fetcher.fetch_all_labs(patient_id),
            self.note_fetcher.fetch_urology_notes(patient_id),
            self.imaging_fetcher.fetch_imaging_reports(patient_id),
            self.pathology_fetcher.fetch_pathology_reports(patient_id),
            self.med_fetcher.fetch_medications(patient_id),
            self.allergy_fetcher.fetch_allergies(patient_id),
            self.history_fetcher.fetch_conditions(patient_id),
            self.history_fetcher.fetch_procedures(patient_id),
            self.history_fetcher.fetch_family_history(patient_id),
            return_exceptions=True,
        )

        data.demographics = results[0] if not isinstance(results[0], Exception) else None
        data.labs = results[1] if not isinstance(results[1], Exception) else {}
        data.clinical_notes = results[2] if not isinstance(results[2], Exception) else []
        data.imaging_reports = results[3] if not isinstance(results[3], Exception) else []
        data.pathology_reports = results[4] if not isinstance(results[4], Exception) else []
        data.medications = results[5] if not isinstance(results[5], Exception) else []
        data.allergies = results[6] if not isinstance(results[6], Exception) else []
        data.conditions = results[7] if not isinstance(results[7], Exception) else []
        data.procedures = results[8] if not isinstance(results[8], Exception) else []
        data.family_history = results[9] if not isinstance(results[9], Exception) else []

        return data

    # ==================================================================
    # STAGE 2: Component Extraction (AI Agents)
    # ==================================================================

    async def _stage2_component_extraction(
        self,
        fhir_data: FHIRPatientData,
        model: Optional[str] = None,
    ) -> NoteSections:
        """AI agents extract structured components from FHIR data."""
        sections = NoteSections()

        # Prepare note content for AI agents
        note_texts = [n.content for n in fhir_data.clinical_notes]

        # Execute extraction agents concurrently
        hpi_task = asyncio.create_task(
            synthesize_hpi(
                note_texts,
                self.llm,
                model=model
            )
        )
        psa_task = asyncio.create_task(
            build_psa_curve(
                fhir_data.labs.get("psa_values", []),
                note_texts
            )
        )
        ipss_task = asyncio.create_task(
            extract_ipss_scores(
                fhir_data.labs,
                note_texts
            )
        )
        pathology_task = asyncio.create_task(
            synthesize_pathology(
                fhir_data.pathology_reports,
                note_texts,
                self.llm,
                model=model
            )
        )

        results = await asyncio.gather(
            hpi_task, psa_task, ipss_task, pathology_task,
            return_exceptions=True
        )

        sections.hpi = results[0] if not isinstance(results[0], Exception) else ""
        sections.psa_curve = results[1] if not isinstance(results[1], Exception) else ""
        sections.ipss = results[2] if not isinstance(results[2], Exception) else {}
        sections.pathology = results[3] if not isinstance(results[3], Exception) else ""

        return sections

    # ==================================================================
    # STAGE 3: Document-Level Extraction
    # ==================================================================

    async def _stage3_document_extraction(
        self,
        fhir_data: FHIRPatientData,
        sections: NoteSections,
    ) -> NoteSections:
        """Extract remaining sections from FHIR data and clinical notes."""

        # Direct FHIR-to-section mapping (no AI needed)
        sections.medications = extract_medications_from_fhir(
            fhir_data.medications
        )
        sections.allergies = extract_allergies_from_fhir(
            fhir_data.allergies
        )
        sections.past_medical_history = self._format_conditions(
            fhir_data.conditions
        )
        sections.past_surgical_history = self._format_procedures(
            fhir_data.procedures
        )
        sections.family_history = self._format_family_history(
            fhir_data.family_history
        )

        # Format lab sections from FHIR Observations
        sections.endocrine_labs = self._format_lab_section(
            fhir_data.labs.get("endocrine_labs", [])
        )
        sections.stone_labs = self._format_lab_section(
            fhir_data.labs.get("stone_labs", [])
        )
        sections.general_labs = self._format_lab_section(
            fhir_data.labs.get("general_labs", [])
        )

        # Format imaging from FHIR DiagnosticReports
        sections.imaging = self._format_imaging(
            fhir_data.imaging_reports
        )

        # Extract from clinical note text (needs AI for some)
        note_texts = [n.content for n in fhir_data.clinical_notes]
        combined_text = "\n\n".join(note_texts)

        sections.dietary_history = extract_dietary_history(combined_text)
        sections.social_history = extract_social_history(combined_text)
        sections.sexual_history = extract_sexual_history(combined_text)
        sections.ros = extract_ros(combined_text)
        sections.physical_exam = extract_physical_exam(combined_text)

        # Build testosterone curve from endocrine labs
        testosterone_labs = [
            lab for lab in fhir_data.labs.get("endocrine_labs", [])
            if lab.loinc_code in ("2986-8", "2991-8")
        ]
        sections.testosterone_curve = self._format_hormone_curve(
            testosterone_labs, "Testosterone"
        )

        return sections

    # ==================================================================
    # STAGE 4: Section Synthesis
    # ==================================================================

    async def _stage4_section_synthesis(
        self,
        fhir_data: FHIRPatientData,
        sections: NoteSections,
        model: Optional[str] = None,
    ) -> NoteSections:
        """Synthesize assessment and plan from all extracted data."""

        # Determine chief complaint from most recent encounter
        if fhir_data.conditions:
            uro_conditions = [
                c for c in fhir_data.conditions
                if self._is_urology_condition(c)
            ]
            if uro_conditions:
                sections.chief_complaint = (
                    f"Follow-up for {uro_conditions[0].name}"
                )
            else:
                sections.chief_complaint = "Urology consultation"

        # Build problem list from conditions
        sections.problem_list = [c.name for c in fhir_data.conditions
                                  if self._is_urology_condition(c)]

        # AI-synthesized assessment
        sections.assessment = await synthesize_assessment(
            sections=sections,
            demographics=fhir_data.demographics,
            llm_provider=self.llm,
            model=model,
        )

        # AI-synthesized plan
        sections.plan = await synthesize_plan(
            sections=sections,
            demographics=fhir_data.demographics,
            llm_provider=self.llm,
            model=model,
        )

        return sections

    # ==================================================================
    # STAGE 5: Word Document Assembly
    # ==================================================================

    def _stage5_word_assembly(
        self,
        sections: NoteSections,
        demographics: Optional[PatientDemographics],
        note_type: str,
    ) -> bytes:
        """Generate Microsoft Word document from synthesized sections."""
        return self.word_gen.generate(
            sections=sections,
            demographics=demographics,
            note_type=note_type,
        )

    # ==================================================================
    # Helper Methods
    # ==================================================================

    def _format_conditions(self, conditions: List[ConditionEntry]) -> str:
        """Format condition list for PMH section."""
        if not conditions:
            return ""
        lines = []
        for c in conditions:
            entry = c.name
            if c.icd10:
                entry += f" ({c.icd10})"
            lines.append(entry)
        return "\n".join(lines)

    def _format_procedures(self, procedures: List[ProcedureEntry]) -> str:
        """Format procedure list for PSH section."""
        if not procedures:
            return ""
        lines = []
        for p in procedures:
            entry = p.name
            if p.date:
                entry += f" ({p.date[:10]})"
            lines.append(entry)
        return "\n".join(lines)

    def _format_family_history(
        self,
        entries: List[FamilyHistoryEntry]
    ) -> str:
        """Format family history entries."""
        if not entries:
            return "No significant family history reported"
        lines = []
        for e in entries:
            entry = f"{e.relationship}: {e.condition}"
            if e.age_of_onset:
                entry += f" (age {e.age_of_onset})"
            if e.deceased:
                entry += " (deceased)"
            lines.append(entry)
        return "\n".join(lines)

    def _format_lab_section(self, labs: List[LabResult]) -> str:
        """Format lab results for note section."""
        if not labs:
            return ""
        lines = []
        for lab in labs:
            date_str = lab.effective_date.strftime("%b %d, %Y")
            value_str = f"{lab.value}"
            if lab.unit:
                value_str += f" {lab.unit}"
            if lab.is_abnormal:
                value_str += " *"
            ref_str = f" (Ref: {lab.reference_range})" if lab.reference_range else ""
            lines.append(f"{lab.display_name}: {value_str}{ref_str} [{date_str}]")
        return "\n".join(lines)

    def _format_imaging(self, reports: List[ImagingReport]) -> str:
        """Format imaging reports for note section.

        CRITICAL: Include EVERY imaging result without truncation.
        """
        if not reports:
            return ""
        sections = []
        for report in reports:
            date_str = report.date.strftime("%b %d, %Y")
            header = f"{report.modality}"
            if report.body_site:
                header += f" - {report.body_site}"
            header += f" ({date_str})"

            # Include full narrative - no truncation per rules.txt
            sections.append(f"{header}:\n{report.narrative}")

        return "\n\n".join(sections)

    def _format_hormone_curve(
        self,
        labs: List[LabResult],
        hormone_name: str
    ) -> str:
        """Format hormone lab values as a curve (reverse chronological)."""
        if not labs:
            return ""
        # Sort reverse chronological
        sorted_labs = sorted(labs, key=lambda x: x.effective_date, reverse=True)
        lines = []
        for lab in sorted_labs:
            date_str = lab.effective_date.strftime("%b %d, %Y %H:%M")
            value = lab.value
            flag = ""
            if lab.is_abnormal and lab.interpretation in ("L", "LL"):
                flag = " L"
            elif lab.is_abnormal and lab.interpretation in ("H", "HH"):
                flag = " H"
            lines.append(f"[r] {date_str}    {value}{flag}")
        return "\n".join(lines)

    def _is_urology_condition(self, condition: ConditionEntry) -> bool:
        """Check if a condition is urology-relevant."""
        uro_keywords = [
            "prostate", "bladder", "kidney", "renal", "ureter",
            "urethra", "testis", "testicular", "penis", "penile",
            "bph", "hematuria", "incontinence", "nephrolithiasis",
            "hydronephrosis", "varicocele", "epididymitis",
            "hypogonadism", "erectile", "overactive bladder",
            "urinary", "uti", "pyelonephritis"
        ]
        name_lower = condition.name.lower()
        return any(kw in name_lower for kw in uro_keywords)

    def _elapsed_ms(self, start: datetime) -> int:
        """Calculate elapsed milliseconds from start time."""
        return int((datetime.utcnow() - start).total_seconds() * 1000)
```

### 7.2 Extraction Agent: PSA Curve Builder (FHIR-Aware)

```python
# note_processing/agents/psa_agent.py
from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass
from ...epic_fhir.fetchers.lab_fetcher import LabResult

PSA_THRESHOLD = 4.0

async def build_psa_curve(
    psa_labs: List[LabResult],
    clinical_notes: List[str],
) -> str:
    """Build PSA curve from FHIR Observation data and clinical notes.

    Output format per urology_prompt.txt:
    [r] MMM DD, YYYY HH:MM    PSA_VALUE[H if >4]

    Args:
        psa_labs: PSA lab results from FHIR (LOINC 2857-1)
        clinical_notes: Clinical note texts for supplemental PSA data

    Returns:
        Formatted PSA curve string in reverse chronological order
    """
    # Collect PSA values from FHIR Observations
    psa_entries = []

    for lab in psa_labs:
        if lab.loinc_code == "2857-1":  # Total PSA only
            try:
                value = float(lab.value)
                psa_entries.append({
                    "date": lab.effective_date,
                    "value": value,
                    "source": "fhir"
                })
            except (ValueError, TypeError):
                continue

    # Also parse PSA values from clinical note text (catch any not in FHIR)
    import re
    psa_pattern = re.compile(
        r'\[r\]\s+(\w{3}\s+\d{1,2},\s+\d{4})\s+(\d{2}:\d{2})\s+([\d.]+)',
    )

    for note_text in clinical_notes:
        for match in psa_pattern.finditer(note_text):
            date_str = f"{match.group(1)} {match.group(2)}"
            try:
                date = datetime.strptime(date_str, "%b %d, %Y %H:%M")
                value = float(match.group(3))
                psa_entries.append({
                    "date": date,
                    "value": value,
                    "source": "note"
                })
            except (ValueError, TypeError):
                continue

    # Deduplicate by date (prefer FHIR source)
    seen_dates = {}
    for entry in psa_entries:
        date_key = entry["date"].strftime("%Y-%m-%d")
        if date_key not in seen_dates or entry["source"] == "fhir":
            seen_dates[date_key] = entry

    # Sort reverse chronological
    unique_entries = sorted(
        seen_dates.values(),
        key=lambda x: x["date"],
        reverse=True
    )

    # Format per urology_prompt.txt specification
    lines = []
    for entry in unique_entries:
        date_str = entry["date"].strftime("%b %d, %Y %H:%M")
        value = entry["value"]

        # Format value: remove trailing zeros
        if value == int(value):
            value_str = str(int(value))
        else:
            value_str = f"{value:.2f}".rstrip('0').rstrip('.')

        # Append H flag if PSA > 4.0
        flag = " H" if value > PSA_THRESHOLD else ""

        lines.append(f"[r] {date_str}    {value_str}{flag}")

    return "\n".join(lines)
```

### 7.3 Extraction Agent: IPSS Score Extractor (FHIR-Aware)

```python
# note_processing/agents/ipss_agent.py
from typing import List, Dict, Any, Optional
from ...epic_fhir.fetchers.lab_fetcher import LabResult

IPSS_SYMPTOMS = [
    "Incomplete Emptying",
    "Frequency",
    "Urgency",
    "Intermittency",
    "Weak Stream",
    "Straining",
    "Nocturia",
]

async def extract_ipss_scores(
    labs: Dict[str, List[LabResult]],
    clinical_notes: List[str],
) -> Dict[str, Any]:
    """Extract IPSS scores from FHIR and clinical notes.

    Checks FHIR Observations for LOINC 80976-4 (IPSS) first,
    then falls back to parsing clinical note text.

    Returns:
        Dictionary with IPSS scores and metadata:
        {
            "date": "YYYY-MM-DD",
            "scores": {"Incomplete Emptying": 3, "Frequency": 4, ...},
            "total": 22,
            "bother_index": 4,
            "severity": "Moderate"  # Mild (0-7), Moderate (8-19), Severe (20-35)
        }
    """
    import re

    # Strategy 1: Check FHIR Observations for IPSS questionnaire
    all_labs = []
    for category_labs in labs.values():
        all_labs.extend(category_labs)

    ipss_obs = [lab for lab in all_labs if lab.loinc_code == "80976-4"]

    if ipss_obs:
        # Use most recent IPSS from FHIR
        latest = max(ipss_obs, key=lambda x: x.effective_date)
        try:
            total = int(float(latest.value))
            return {
                "date": latest.effective_date.strftime("%Y-%m-%d"),
                "scores": {},  # Individual scores may not be in FHIR
                "total": total,
                "bother_index": None,
                "severity": _classify_ipss(total),
                "source": "fhir"
            }
        except (ValueError, TypeError):
            pass

    # Strategy 2: Parse from clinical note text
    for note_text in clinical_notes:
        ipss_data = _parse_ipss_from_text(note_text)
        if ipss_data:
            return ipss_data

    return {}


def _parse_ipss_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Parse IPSS table from clinical note text."""
    import re

    # Look for IPSS section
    ipss_section = re.search(
        r'IPSS.*?Total[:\s]*(\d+)\s*/\s*35.*?(?:BI|Bother)[:\s]*(\d+)\s*/\s*6',
        text,
        re.IGNORECASE | re.DOTALL
    )

    if not ipss_section:
        return None

    total = int(ipss_section.group(1))
    bother = int(ipss_section.group(2))

    # Try to extract individual scores
    scores = {}
    for symptom in IPSS_SYMPTOMS:
        pattern = re.compile(
            rf'{re.escape(symptom)}[:\s|]*(\d)',
            re.IGNORECASE
        )
        match = pattern.search(text)
        if match:
            scores[symptom] = int(match.group(1))

    return {
        "date": "",
        "scores": scores,
        "total": total,
        "bother_index": bother,
        "severity": _classify_ipss(total),
        "source": "note_text"
    }


def _classify_ipss(total: int) -> str:
    """Classify IPSS severity."""
    if total <= 7:
        return "Mild"
    elif total <= 19:
        return "Moderate"
    else:
        return "Severe"
```

### 7.4 LLM Helper for Section Combination

```python
# note_processing/llm_helper.py
from typing import List, Optional
from ..llm.provider import LLMProvider

async def combine_sections_with_llm(
    section_name: str,
    section_instances: List[str],
    instructions: str,
    llm_provider: LLMProvider,
    model: Optional[str] = None,
) -> str:
    """Combine multiple instances of a section using LLM.

    Args:
        section_name: Name of the clinical note section
        section_instances: Multiple versions/sources of the section content
        instructions: Specific combination instructions
        llm_provider: LLM provider for generation
        model: Optional model override

    Returns:
        Combined section text
    """
    if not section_instances:
        return ""

    if len(section_instances) == 1:
        return section_instances[0]

    # Build prompt for section combination
    numbered_sections = "\n\n".join(
        f"--- Source {i+1} ---\n{text}"
        for i, text in enumerate(section_instances)
    )

    prompt = f"""Combine these {len(section_instances)} versions of the {section_name} section into a single comprehensive version.

{instructions}

{numbered_sections}

Combined {section_name}:"""

    system_prompt = (
        "You are a clinical documentation assistant specialized in urology. "
        "Combine clinical information accurately. Never fabricate data. "
        "Return ONLY the combined clinical content with no meta-commentary."
    )

    result = await llm_provider.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=0.2,
    )

    return result.strip()
```
