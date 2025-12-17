"""
Template Manager for Clinical Notes
Manages note templates for different visit types and specialties
"""

import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class NoteType(Enum):
    """Types of clinical notes."""
    CLINIC = "clinic"
    CONSULT = "consult"
    PREOP = "preop"
    POSTOP = "postop"
    PROCEDURE = "procedure"
    TELEPHONE = "telephone"


class TemplateManager:
    """
    Manages clinical note templates.

    Provides templates for different note types and specialties.
    """

    def __init__(self, template_dir: str = "/home/gulab/PythonProjects/VAUCDA"):
        """
        Initialize template manager.

        Args:
            template_dir: Directory containing template files
        """
        self.template_dir = template_dir
        self.templates: Dict[str, str] = {}
        self._load_templates()

    def _load_templates(self):
        """Load all available templates."""
        # Load urology clinic template
        try:
            self.templates["clinic"] = self._load_clinic_template()
            logger.info("Loaded clinic template")
        except Exception as e:
            logger.error(f"Failed to load clinic template: {e}")
            self.templates["clinic"] = self._get_default_clinic_template()

        # Load or create other templates
        self.templates["consult"] = self._load_consult_template()
        self.templates["preop"] = self._load_preop_template()
        self.templates["postop"] = self._load_postop_template()
        self.templates["procedure"] = self._load_procedure_template()
        self.templates["telephone"] = self._load_telephone_template()

    def _load_clinic_template(self) -> str:
        """Load clinic template from urology_prompt.txt."""
        template_path = f"{self.template_dir}/urology_prompt.txt"
        with open(template_path, 'r') as f:
            return f.read()

    def _get_default_clinic_template(self) -> str:
        """Default clinic template fallback."""
        return """You are a urologist (Dr. Rodriguez) seeing patients at the VA Urology clinic.

Provide a comprehensive clinic note in narrative format, without bullet points.

Use the following template:

CC:

HPI:

IPSS (if applicable):
+---------------+--------+
|        IPSS            |
+---------------+--------+
| Symptom       | Score  |
+---------------+--------+
| Empty         |   #    |
| Frequency     |   #    |
| Urgency       |   #    |
| Hesitancy     |   #    |
| Intermittency |   #    |
| Flow          |   #    |
| Nocturia      |   #    |
+---------------+--------+
| Total         | ##/35  |
| BI            | #/6    |
+---------------+--------+

PAST MEDICAL HISTORY:

PAST SURGICAL HISTORY:

MEDICATIONS:

ALLERGIES:

LABS:

IMAGING:

PHYSICAL EXAM:

ASSESSMENT:

PLAN:
"""

    def _load_consult_template(self) -> str:
        """Load consult template."""
        return """You are a urologist providing a consultation.

Generate a comprehensive consultation note.

REASON FOR CONSULT:

HISTORY OF PRESENT ILLNESS:

RELEVANT PAST MEDICAL HISTORY:

RELEVANT PAST SURGICAL HISTORY:

MEDICATIONS:

ALLERGIES:

SOCIAL HISTORY:

REVIEW OF SYSTEMS:

LABS AND IMAGING:

PHYSICAL EXAMINATION:

ASSESSMENT AND RECOMMENDATIONS:

Thank you for this consultation. Please contact urology with any questions.
"""

    def _load_preop_template(self) -> str:
        """Load preoperative template."""
        return """You are a urologist performing a preoperative evaluation.

Generate a preoperative clinic note.

PLANNED PROCEDURE:

INDICATION:

HISTORY OF PRESENT ILLNESS:

PAST MEDICAL HISTORY:

PAST SURGICAL HISTORY:

MEDICATIONS:

ALLERGIES:

REVIEW OF SYSTEMS:

PREOPERATIVE LABS:

PREOPERATIVE IMAGING:

PHYSICAL EXAM:

CARDIAC RISK ASSESSMENT:

ANESTHESIA RISK ASSESSMENT:

ASSESSMENT:

PLAN:
- Cleared for surgery: [YES/NO]
- Anesthesia type: [General/Spinal/Local]
- Special considerations:
- Postoperative disposition:
"""

    def _load_postop_template(self) -> str:
        """Load postoperative template."""
        return """You are a urologist seeing a patient for postoperative follow-up.

Generate a postoperative clinic note.

PROCEDURE PERFORMED:
Date:

POSTOPERATIVE DAY:

CHIEF COMPLAINT:

HPI:

WOUND CHECK:
- Incision: [healing well/concerning]
- Drainage: [none/serous/purulent]
- Erythema: [none/present]

DRAIN OUTPUT (if applicable):

PAIN CONTROL:

MEDICATIONS:

PHYSICAL EXAM:

LABS (if obtained):

IMAGING (if obtained):

ASSESSMENT:

PLAN:
- Activity:
- Diet:
- Medications:
- Follow-up:
- Return precautions:
"""

    def _load_procedure_template(self) -> str:
        """Load procedure note template."""
        return """You are a urologist documenting a procedure.

Generate a procedure note.

PROCEDURE:

INDICATION:

CONSENT:
Informed consent obtained after discussion of risks, benefits, and alternatives.

ANESTHESIA:

POSITIONING:

PREP AND DRAPE:

PROCEDURE DETAILS:

FINDINGS:

ESTIMATED BLOOD LOSS:

COMPLICATIONS:

SPECIMENS:

DISPOSITION:
Patient tolerated procedure well and transferred to recovery in stable condition.
"""

    def _load_telephone_template(self) -> str:
        """Load telephone encounter template."""
        return """You are a urologist documenting a telephone encounter.

Generate a telephone encounter note.

REASON FOR CALL:

HISTORY:

REVIEW OF SYMPTOMS:

LABS/IMAGING REVIEW (if applicable):

ASSESSMENT:

RECOMMENDATIONS:

PLAN:

DISPOSITION:
- Patient understands and agrees with plan
- Advised to call/return if symptoms worsen
- Follow-up as outlined above
"""

    def get_template(self, note_type: str) -> str:
        """
        Get template by note type.

        Args:
            note_type: Type of note (clinic, consult, preop, etc.)

        Returns:
            Template string
        """
        template = self.templates.get(note_type)

        if template:
            logger.debug(f"Retrieved template for note type: {note_type}")
            return template
        else:
            logger.warning(f"Template not found for '{note_type}', using clinic template")
            return self.templates.get("clinic", self._get_default_clinic_template())

    def get_available_types(self) -> Dict[str, str]:
        """
        Get all available note types with descriptions.

        Returns:
            Dictionary mapping note types to descriptions
        """
        return {
            "clinic": "Standard outpatient clinic visit",
            "consult": "Consultation note",
            "preop": "Preoperative evaluation",
            "postop": "Postoperative follow-up",
            "procedure": "Procedure documentation",
            "telephone": "Telephone encounter"
        }

    def add_custom_template(self, note_type: str, template: str):
        """
        Add a custom template.

        Args:
            note_type: Template identifier
            template: Template content
        """
        self.templates[note_type] = template
        logger.info(f"Added custom template: {note_type}")

    def get_system_prompt(self, note_type: str) -> str:
        """
        Get system prompt appropriate for note type.

        Args:
            note_type: Type of note

        Returns:
            System prompt string
        """
        base_prompt = "You are an expert urologist generating clinical documentation. "

        type_specific = {
            "clinic": "Provide a comprehensive clinic note in narrative format.",
            "consult": "Provide a detailed consultation with specific recommendations.",
            "preop": "Perform a thorough preoperative risk assessment.",
            "postop": "Document postoperative course and provide clear instructions.",
            "procedure": "Document the procedure with precise technical details.",
            "telephone": "Document the telephone encounter concisely and clearly."
        }

        specific = type_specific.get(note_type, "Provide accurate clinical documentation.")

        return base_prompt + specific


# Global singleton instance
_template_manager = None


def get_template_manager() -> TemplateManager:
    """Get or create global template manager instance."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
