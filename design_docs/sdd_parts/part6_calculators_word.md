

---

## 9. Clinical Calculator Engine

### 9.1 Calculator Framework with FHIR Auto-Population

```python
# calculators/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

class RiskLevel(Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    INTERMEDIATE = "intermediate"
    HIGH = "high"
    VERY_HIGH = "very_high"

@dataclass
class CalculatorInput:
    """Input specification for a clinical calculator."""
    name: str
    type: str                           # "float", "int", "bool", "choice"
    required: bool = True
    default: Any = None
    choices: Optional[List[Any]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    loinc_code: Optional[str] = None    # LOINC code for FHIR auto-populate

@dataclass
class CalculatorResult:
    """Result from a clinical calculator."""
    score: float
    interpretation: str
    risk_level: Optional[RiskLevel] = None
    recommendations: Optional[List[str]] = None
    breakdown: Optional[Dict[str, Any]] = None
    references: Optional[List[str]] = None
    word_formatted: Optional[str] = None  # Pre-formatted for Word output

class ClinicalCalculator(ABC):
    """Base class for all 44 clinical calculators.

    Supports FHIR auto-population of inputs via LOINC code mapping.
    """

    name: str
    category: str
    description: str
    inputs: List[CalculatorInput]
    references: List[str]

    @abstractmethod
    def calculate(self, **kwargs) -> CalculatorResult:
        """Perform calculation and return result."""
        pass

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate and normalize calculator inputs."""
        validated = {}
        for input_spec in self.inputs:
            value = kwargs.get(input_spec.name)

            if value is None:
                if input_spec.required:
                    raise ValueError(f"Missing required input: {input_spec.name}")
                value = input_spec.default

            if value is not None:
                if input_spec.type == "float":
                    value = float(value)
                    if input_spec.min_value is not None and value < input_spec.min_value:
                        raise ValueError(
                            f"{input_spec.name} ({value}) below minimum ({input_spec.min_value})"
                        )
                    if input_spec.max_value is not None and value > input_spec.max_value:
                        raise ValueError(
                            f"{input_spec.name} ({value}) above maximum ({input_spec.max_value})"
                        )
                elif input_spec.type == "int":
                    value = int(value)
                elif input_spec.type == "bool":
                    value = bool(value)
                elif input_spec.type == "choice" and input_spec.choices:
                    if value not in input_spec.choices:
                        raise ValueError(
                            f"Invalid choice for {input_spec.name}: {value}. "
                            f"Valid: {input_spec.choices}"
                        )

            validated[input_spec.name] = value

        return validated

    def get_fhir_mappings(self) -> Dict[str, str]:
        """Get LOINC code mappings for FHIR auto-population.

        Returns:
            Dictionary of input_name -> LOINC code
        """
        return {
            inp.name: inp.loinc_code
            for inp in self.inputs
            if inp.loinc_code
        }

    def auto_populate_from_labs(
        self,
        lab_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Auto-populate calculator inputs from FHIR lab results.

        Args:
            lab_results: Dictionary of LOINC code -> most recent value

        Returns:
            Dictionary of auto-populated input values
        """
        populated = {}
        for inp in self.inputs:
            if inp.loinc_code and inp.loinc_code in lab_results:
                try:
                    value = lab_results[inp.loinc_code]
                    if inp.type == "float":
                        populated[inp.name] = float(value)
                    elif inp.type == "int":
                        populated[inp.name] = int(float(value))
                    else:
                        populated[inp.name] = value
                except (ValueError, TypeError):
                    continue
        return populated
```

### 9.2 PSA Kinetics Calculator

```python
# calculators/prostate/psa_kinetics.py
import math
from typing import List
from ..base import ClinicalCalculator, CalculatorInput, CalculatorResult, RiskLevel

class PSAKineticsCalculator(ClinicalCalculator):
    """Calculate PSA velocity (PSAV) and doubling time (PSADT)."""

    name = "PSA Kinetics Calculator"
    category = "prostate_cancer"
    description = "Calculate PSAV and PSADT from serial PSA measurements"

    inputs = [
        CalculatorInput("psa_values", "list",
                       description="Serial PSA values (ng/mL)",
                       loinc_code="2857-1"),
        CalculatorInput("time_points", "list",
                       description="Time points in months from first measurement"),
    ]

    references = [
        "D'Amico AV, et al. JAMA 2004;292:2237-2242",
        "Freedland SJ, et al. JAMA 2005;294:433-439",
        "Vickers AJ, et al. J Clin Oncol 2009;27:398-403"
    ]

    def calculate(self, **kwargs) -> CalculatorResult:
        validated = self.validate_inputs(**kwargs)
        psa_values = validated["psa_values"]
        time_points = validated["time_points"]

        if len(psa_values) < 2:
            raise ValueError("At least 2 PSA values required")
        if len(psa_values) != len(time_points):
            raise ValueError("PSA values and time points must have equal length")

        # Calculate PSAV (ng/mL/year)
        time_years = (time_points[-1] - time_points[0]) / 12
        psav = (psa_values[-1] - psa_values[0]) / time_years if time_years > 0 else 0

        # Calculate PSADT using log-linear regression (months)
        psadt = self._calculate_psadt(psa_values, time_points)

        # Build interpretation
        psav_interp = self._interpret_psav(psav)
        psadt_interp = self._interpret_psadt(psadt)

        word_text = (
            f"PSA Kinetics Analysis:\n"
            f"  PSAV: {psav:.2f} ng/mL/year - {psav_interp}\n"
            f"  PSADT: {psadt:.1f} months - {psadt_interp}\n"
            f"  Based on {len(psa_values)} measurements over "
            f"{time_years:.1f} years"
        )

        return CalculatorResult(
            score=psadt,
            interpretation=(
                f"PSAV: {psav:.2f} ng/mL/year ({psav_interp})\n"
                f"PSADT: {psadt:.1f} months ({psadt_interp})"
            ),
            risk_level=self._get_risk_level(psadt),
            breakdown={
                "psav": round(psav, 2),
                "psadt_months": round(psadt, 1) if psadt != float('inf') else None,
                "num_measurements": len(psa_values),
                "time_span_years": round(time_years, 1),
                "first_psa": psa_values[0],
                "last_psa": psa_values[-1],
            },
            references=self.references,
            word_formatted=word_text,
        )

    def _calculate_psadt(self, values: List[float], times: List[float]) -> float:
        """Calculate PSA doubling time via log-linear regression."""
        if not all(p > 0 for p in values):
            return float('inf')

        ln_psa = [math.log(p) for p in values]
        n = len(values)

        t_mean = sum(times) / n
        ln_mean = sum(ln_psa) / n

        numerator = sum(
            (t - t_mean) * (ln - ln_mean)
            for t, ln in zip(times, ln_psa)
        )
        denominator = sum((t - t_mean) ** 2 for t in times)

        if denominator == 0:
            return float('inf')

        slope = numerator / denominator
        if slope <= 0:
            return float('inf')

        return math.log(2) / slope

    def _interpret_psav(self, psav: float) -> str:
        if psav > 2.0:
            return "Concerning for recurrence"
        elif psav > 0.75:
            return "Increased cancer risk"
        elif psav > 0.35:
            return "Borderline"
        else:
            return "Within acceptable range"

    def _interpret_psadt(self, psadt: float) -> str:
        if psadt == float('inf'):
            return "Stable or decreasing PSA"
        elif psadt < 3:
            return "Aggressive disease, high metastatic risk"
        elif psadt < 9:
            return "Intermediate risk"
        elif psadt < 15:
            return "Lower risk"
        else:
            return "Indolent behavior"

    def _get_risk_level(self, psadt: float) -> RiskLevel:
        if psadt == float('inf'):
            return RiskLevel.VERY_LOW
        elif psadt < 3:
            return RiskLevel.VERY_HIGH
        elif psadt < 9:
            return RiskLevel.HIGH
        elif psadt < 15:
            return RiskLevel.INTERMEDIATE
        else:
            return RiskLevel.LOW
```

### 9.3 Module Registry with FHIR Integration

```python
# calculators/registry.py
from typing import Dict, List, Optional, Any
from .base import ClinicalCalculator, CalculatorResult
from ...epic_fhir.fetchers.lab_fetcher import LabResult

class ClinicalModuleRegistry:
    """Registry for all 44 clinical calculators with FHIR auto-population."""

    def __init__(self):
        self._calculators: Dict[str, ClinicalCalculator] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, calculator: ClinicalCalculator) -> None:
        """Register a calculator."""
        self._calculators[calculator.name] = calculator
        if calculator.category not in self._categories:
            self._categories[calculator.category] = []
        self._categories[calculator.category].append(calculator.name)

    def get_calculator(self, name: str) -> ClinicalCalculator:
        """Get calculator by name."""
        if name not in self._calculators:
            raise KeyError(f"Calculator not found: {name}")
        return self._calculators[name]

    def get_by_category(self, category: str) -> List[ClinicalCalculator]:
        """Get all calculators in a category."""
        names = self._categories.get(category, [])
        return [self._calculators[n] for n in names]

    def list_categories(self) -> List[str]:
        """List all calculator categories."""
        return list(self._categories.keys())

    def list_calculators(self, category: Optional[str] = None) -> List[str]:
        """List calculator names, optionally filtered by category."""
        if category:
            return self._categories.get(category, [])
        return list(self._calculators.keys())

    def auto_populate_calculator(
        self,
        calculator_name: str,
        lab_results: List[LabResult],
    ) -> Dict[str, Any]:
        """Auto-populate a calculator's inputs from FHIR lab results.

        Args:
            calculator_name: Name of the calculator
            lab_results: Lab results from FHIR

        Returns:
            Dictionary of auto-populated input values
        """
        calculator = self.get_calculator(calculator_name)

        # Build LOINC -> most recent value map
        loinc_values = {}
        for lab in sorted(lab_results, key=lambda x: x.effective_date, reverse=True):
            if lab.loinc_code not in loinc_values:
                loinc_values[lab.loinc_code] = lab.value

        return calculator.auto_populate_from_labs(loinc_values)

    def calculate_with_auto_populate(
        self,
        calculator_name: str,
        lab_results: List[LabResult],
        manual_overrides: Optional[Dict[str, Any]] = None,
    ) -> CalculatorResult:
        """Calculate with FHIR auto-populated + manual inputs.

        FHIR values are used as defaults; manual overrides take precedence.

        Args:
            calculator_name: Calculator to run
            lab_results: FHIR lab results for auto-population
            manual_overrides: Manual input values (override FHIR)

        Returns:
            CalculatorResult
        """
        calculator = self.get_calculator(calculator_name)

        # Auto-populate from FHIR
        auto_values = self.auto_populate_calculator(calculator_name, lab_results)

        # Apply manual overrides
        if manual_overrides:
            auto_values.update(manual_overrides)

        return calculator.calculate(**auto_values)
```

---

## 10. Word Document Generation

### 10.1 Document Style Configuration

```python
# word_generator/styles.py
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

@dataclass
class WordStyleConfig:
    """Configuration for Word document formatting."""

    # Page layout
    page_width: float = Inches(8.5)
    page_height: float = Inches(11)
    margin_top: float = Inches(0.75)
    margin_bottom: float = Inches(0.75)
    margin_left: float = Inches(1.0)
    margin_right: float = Inches(1.0)

    # Document title
    title_font: str = "Arial"
    title_size: int = Pt(16)
    title_color: Tuple[int, int, int] = (44, 82, 130)     # Primary Blue
    title_bold: bool = True

    # Section headers
    section_font: str = "Arial"
    section_size: int = Pt(12)
    section_color: Tuple[int, int, int] = (44, 82, 130)
    section_bold: bool = True
    section_underline: bool = True

    # Subsection headers
    subsection_font: str = "Arial"
    subsection_size: int = Pt(11)
    subsection_bold: bool = True

    # Body text
    body_font: str = "Times New Roman"
    body_size: int = Pt(11)
    body_color: Tuple[int, int, int] = (55, 65, 81)       # Body Text
    line_spacing: float = 1.15
    paragraph_spacing_after: int = Pt(6)

    # Table styles
    table_header_bg: Tuple[int, int, int] = (44, 82, 130)
    table_header_text: Tuple[int, int, int] = (255, 255, 255)
    table_border_color: Tuple[int, int, int] = (229, 231, 235)
    table_alt_row_bg: Tuple[int, int, int] = (249, 250, 251)
    table_font_size: int = Pt(10)

    # PSA Curve formatting
    psa_font: str = "Courier New"
    psa_size: int = Pt(10)
    psa_high_color: Tuple[int, int, int] = (239, 68, 68)  # Error Red

    # Status colors for lab values
    abnormal_high_color: Tuple[int, int, int] = (239, 68, 68)
    abnormal_low_color: Tuple[int, int, int] = (59, 130, 246)
    normal_color: Tuple[int, int, int] = (16, 185, 129)

    # Footer
    footer_font: str = "Arial"
    footer_size: int = Pt(8)
    footer_color: Tuple[int, int, int] = (156, 163, 175)
```

### 10.2 Word Document Generator

```python
# word_generator/generator.py
from io import BytesIO
from typing import Optional
from datetime import datetime
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

from .styles import WordStyleConfig
from ..note_processing.pipeline import NoteSections
from ..epic_fhir.fetchers.patient_fetcher import PatientDemographics


class WordDocumentGenerator:
    """Generate formatted Microsoft Word documents from note sections.

    Produces professional medical documents with proper formatting,
    tables (IPSS, PSA Curve), section headers, and clinical styling.
    """

    def __init__(self, config: Optional[WordStyleConfig] = None):
        self.config = config or WordStyleConfig()

    def generate(
        self,
        sections: NoteSections,
        demographics: Optional[PatientDemographics] = None,
        note_type: str = "clinic_note",
    ) -> bytes:
        """Generate a complete Word document.

        Args:
            sections: All note sections from the pipeline
            demographics: Patient demographics (optional)
            note_type: Type of note for template selection

        Returns:
            Bytes of the generated .docx file
        """
        doc = Document()
        self._setup_page_layout(doc)

        # Document header
        self._add_document_header(doc, note_type, demographics)

        # Chief Complaint
        if sections.chief_complaint:
            self._add_section(doc, "CHIEF COMPLAINT", sections.chief_complaint)

        # HPI
        if sections.hpi:
            self._add_section(doc, "HISTORY OF PRESENT ILLNESS", sections.hpi)

        # IPSS Table
        if sections.ipss:
            self._add_ipss_table(doc, sections.ipss)

        # History sections
        if sections.dietary_history:
            self._add_section(doc, "DIETARY HISTORY", sections.dietary_history)
        if sections.social_history:
            self._add_section(doc, "SOCIAL HISTORY", sections.social_history)
        if sections.family_history:
            self._add_section(doc, "FAMILY HISTORY", sections.family_history)
        if sections.sexual_history:
            self._add_section(doc, "SEXUAL HISTORY", sections.sexual_history)

        # PMH/PSH
        if sections.past_medical_history:
            self._add_section(doc, "PAST MEDICAL HISTORY",
                            sections.past_medical_history)
        if sections.past_surgical_history:
            self._add_section(doc, "PAST SURGICAL HISTORY",
                            sections.past_surgical_history)

        # PSA Curve
        if sections.psa_curve:
            self._add_psa_curve(doc, sections.psa_curve)

        # Testosterone Curve
        if sections.testosterone_curve:
            self._add_section(doc, "TESTOSTERONE CURVE",
                            sections.testosterone_curve)

        # Pathology
        if sections.pathology:
            self._add_section(doc, "PATHOLOGY RESULTS", sections.pathology)

        # Medications and Allergies
        if sections.medications:
            self._add_section(doc, "MEDICATIONS", sections.medications)
        if sections.allergies:
            self._add_section(doc, "ALLERGIES", sections.allergies)

        # Lab Sections
        if sections.endocrine_labs:
            self._add_lab_section(doc, "ENDOCRINE LABS", sections.endocrine_labs)
        if sections.stone_labs:
            self._add_lab_section(doc, "STONE LABS", sections.stone_labs)
        if sections.general_labs:
            self._add_lab_section(doc, "LABS", sections.general_labs)

        # Imaging
        if sections.imaging:
            self._add_section(doc, "IMAGING", sections.imaging)

        # ROS
        if sections.ros:
            self._add_section(doc, "REVIEW OF SYSTEMS", sections.ros)

        # Physical Exam
        if sections.physical_exam:
            self._add_section(doc, "PHYSICAL EXAMINATION", sections.physical_exam)

        # Assessment
        if sections.assessment:
            self._add_section(doc, "ASSESSMENT", sections.assessment)

        # Problem List
        if sections.problem_list:
            self._add_problem_list(doc, sections.problem_list)

        # Plan
        if sections.plan:
            self._add_section(doc, "PLAN", sections.plan)

        # Footer
        self._add_footer(doc)

        # Save to bytes
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def _setup_page_layout(self, doc: Document) -> None:
        """Configure page dimensions and margins."""
        section = doc.sections[0]
        section.page_width = self.config.page_width
        section.page_height = self.config.page_height
        section.top_margin = self.config.margin_top
        section.bottom_margin = self.config.margin_bottom
        section.left_margin = self.config.margin_left
        section.right_margin = self.config.margin_right

    def _add_document_header(
        self,
        doc: Document,
        note_type: str,
        demographics: Optional[PatientDemographics],
    ) -> None:
        """Add document title and patient header."""
        # Title
        type_names = {
            "clinic_note": "UROLOGY CLINIC NOTE",
            "consult": "UROLOGY CONSULT NOTE",
            "preop": "UROLOGY PRE-OPERATIVE NOTE",
            "postop": "UROLOGY POST-OPERATIVE NOTE",
        }
        title = type_names.get(note_type, "UROLOGY CLINIC NOTE")

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        run.font.name = self.config.title_font
        run.font.size = self.config.title_size
        run.font.bold = self.config.title_bold
        run.font.color.rgb = RGBColor(*self.config.title_color)

        # Date
        date_p = doc.add_paragraph()
        date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_run = date_p.add_run(
            f"Date: {datetime.now().strftime('%B %d, %Y')}"
        )
        date_run.font.name = self.config.body_font
        date_run.font.size = self.config.body_size

        # Patient demographics (if available)
        if demographics:
            demo_p = doc.add_paragraph()
            demo_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            demo_text = f"Patient: {demographics.name}"
            if demographics.age is not None:
                demo_text += f"  |  Age: {demographics.age}"
            if demographics.gender:
                demo_text += f"  |  Gender: {demographics.gender.title()}"
            demo_run = demo_p.add_run(demo_text)
            demo_run.font.name = self.config.body_font
            demo_run.font.size = self.config.body_size

        # Horizontal rule
        doc.add_paragraph("─" * 70)

    def _add_section(
        self,
        doc: Document,
        header: str,
        content: str,
    ) -> None:
        """Add a standard section with header and body text."""
        # Section header
        p = doc.add_paragraph()
        run = p.add_run(header + ":")
        run.font.name = self.config.section_font
        run.font.size = self.config.section_size
        run.font.bold = self.config.section_bold
        run.font.color.rgb = RGBColor(*self.config.section_color)

        # Body text
        for line in content.split('\n'):
            if line.strip():
                body_p = doc.add_paragraph()
                body_run = body_p.add_run(line)
                body_run.font.name = self.config.body_font
                body_run.font.size = self.config.body_size
                body_run.font.color.rgb = RGBColor(*self.config.body_color)
                body_p.paragraph_format.space_after = self.config.paragraph_spacing_after

    def _add_ipss_table(self, doc: Document, ipss_data: dict) -> None:
        """Add formatted IPSS score table."""
        self._add_section_header(doc, "IPSS")

        if not ipss_data or not ipss_data.get("total"):
            return

        # Create table
        symptoms = [
            "Incomplete Emptying", "Frequency", "Urgency",
            "Intermittency", "Weak Stream", "Straining", "Nocturia"
        ]

        table = doc.add_table(rows=len(symptoms) + 3, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Header row
        header_cells = table.rows[0].cells
        header_cells[0].text = "Symptom"
        header_cells[1].text = "Score"
        self._style_table_header(header_cells)

        # Symptom rows
        scores = ipss_data.get("scores", {})
        for i, symptom in enumerate(symptoms):
            row = table.rows[i + 1]
            row.cells[0].text = symptom
            score = scores.get(symptom, "—")
            row.cells[1].text = str(score)

        # Total row
        total_row = table.rows[len(symptoms) + 1]
        total_row.cells[0].text = "Total"
        total_row.cells[1].text = f"{ipss_data.get('total', '—')}/35"
        for cell in total_row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True

        # Bother Index row
        bi_row = table.rows[len(symptoms) + 2]
        bi_row.cells[0].text = "Bother Index (BI)"
        bi = ipss_data.get("bother_index")
        bi_row.cells[1].text = f"{bi}/6" if bi is not None else "—"

        # Severity interpretation
        severity = ipss_data.get("severity", "")
        if severity:
            p = doc.add_paragraph()
            run = p.add_run(f"Severity: {severity}")
            run.font.bold = True
            run.font.name = self.config.body_font
            run.font.size = self.config.body_size

    def _add_psa_curve(self, doc: Document, psa_text: str) -> None:
        """Add PSA curve with monospace formatting and color coding."""
        self._add_section_header(doc, "PSA CURVE")

        for line in psa_text.split('\n'):
            if not line.strip():
                continue

            p = doc.add_paragraph()
            if line.strip().endswith("H"):
                # High PSA value - red color
                run = p.add_run(line)
                run.font.name = self.config.psa_font
                run.font.size = self.config.psa_size
                run.font.color.rgb = RGBColor(*self.config.psa_high_color)
                run.font.bold = True
            else:
                run = p.add_run(line)
                run.font.name = self.config.psa_font
                run.font.size = self.config.psa_size
                run.font.color.rgb = RGBColor(*self.config.body_color)

            p.paragraph_format.space_after = Pt(2)

    def _add_lab_section(
        self,
        doc: Document,
        header: str,
        lab_text: str,
    ) -> None:
        """Add lab section with separator line styling."""
        # Add section separator
        separator = "=" * 25 + f" {header} " + "=" * 25
        sep_p = doc.add_paragraph()
        sep_run = sep_p.add_run(separator)
        sep_run.font.name = self.config.psa_font
        sep_run.font.size = Pt(10)
        sep_run.font.color.rgb = RGBColor(*self.config.section_color)

        # Lab values
        for line in lab_text.split('\n'):
            if not line.strip():
                continue
            p = doc.add_paragraph()
            # Color-code abnormal values
            if line.strip().endswith("*"):
                run = p.add_run(line)
                run.font.name = self.config.body_font
                run.font.size = self.config.body_size
                run.font.color.rgb = RGBColor(*self.config.abnormal_high_color)
            else:
                run = p.add_run(line)
                run.font.name = self.config.body_font
                run.font.size = self.config.body_size
            p.paragraph_format.space_after = Pt(2)

    def _add_problem_list(self, doc: Document, problems: list) -> None:
        """Add numbered problem list."""
        self._add_section_header(doc, "UROLOGY PROBLEM LIST")

        for i, problem in enumerate(problems, 1):
            p = doc.add_paragraph()
            run = p.add_run(f"Problem #{i}: {problem}")
            run.font.name = self.config.body_font
            run.font.size = self.config.body_size
            run.font.bold = True

    def _add_section_header(self, doc: Document, text: str) -> None:
        """Add a section header."""
        p = doc.add_paragraph()
        run = p.add_run(text + ":")
        run.font.name = self.config.section_font
        run.font.size = self.config.section_size
        run.font.bold = self.config.section_bold
        run.font.color.rgb = RGBColor(*self.config.section_color)

    def _style_table_header(self, cells) -> None:
        """Apply header styling to table cells."""
        for cell in cells:
            shading = cell._tc.get_or_add_tcPr()
            shading_elm = shading.makeelement(
                qn('w:shd'), {
                    qn('w:fill'): '{:02x}{:02x}{:02x}'.format(
                        *self.config.table_header_bg
                    ),
                    qn('w:val'): 'clear',
                }
            )
            shading.append(shading_elm)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.color.rgb = RGBColor(*self.config.table_header_text)
                    run.font.bold = True

    def _add_footer(self, doc: Document) -> None:
        """Add document footer with generation metadata."""
        doc.add_paragraph("─" * 70)

        footer_p = doc.add_paragraph()
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer_p.add_run(
            f"Generated by EPIC-VAUCDA | {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
            f"This document was generated using AI-assisted clinical documentation"
        )
        footer_run.font.name = self.config.footer_font
        footer_run.font.size = self.config.footer_size
        footer_run.font.color.rgb = RGBColor(*self.config.footer_color)
```
