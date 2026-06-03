"""
Clinical Entity Extraction Service

Extracts structured clinical data from unstructured text using LLM.
"""

import logging
import re
import json
from typing import Dict, List, Any, Optional
from llm.llm_manager import LLMManager

logger = logging.getLogger(__name__)


class ClinicalEntityExtractor:
    """Extract clinical entities from unstructured text."""

    # Define clinical entity patterns and types
    ENTITY_PATTERNS = {
        # PSA and prostate markers
        # More specific patterns to avoid matching specimen IDs like "SPSA24"
        # CRITICAL: Patterns must extract the ACTUAL PSA value, NOT the timestamp
        'psa': [
            r'\bPSA\s+TOTAL\s*[:=]?\s*(\d+\.?\d*)',  # PSA TOTAL (lab format)
            r'\bPSA\s*[:=]\s*(\d+\.?\d*)\s*(?:ng/ml|ng/mL)',  # PSA: X ng/mL
            r'\bPSA\s+(?:level|value)\s*[:=]?\s*(\d+\.?\d*)',  # PSA level/value
            r'prostate[-\s]specific antigen\s*[:=]\s*(\d+\.?\d*)',
            # PSA CURVE format with [r] prefix and HH:MM time: [r] Jun 24, 2024 09:36    0.52
            r'\[r\]\s+\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)',
            # PSA CURVE format with [r] prefix and HHMM time (legacy): [r] Jun 24, 2024 0936    0.52
            # CRITICAL: Must match 4-digit time then 2+ spaces then decimal value
            r'\[r\]\s+\w+\s+\d{1,2},\s+\d{4}\s+\d{4}\s{2,}(\d+\.?\d*)',
            # PSA CURVE format without [r] prefix: Apr 02, 2025 08:13: 1.82
            # Pattern matches: MMM DD, YYYY HH:MM: VALUE (colon separator before value)
            r'^[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\s*(\d+\.?\d*)$',
            # Narrative PSA value: "PSA was 4.2" or "most recent PSA 1.82"
            r'(?:most recent\s+)?PSA\s+(?:was\s+|of\s+|is\s+)?(\d+\.?\d*)',
        ],
        'free_psa': [
            r'free\s+PSA\s*[:=]\s*(\d+\.?\d*)',
            r'fPSA\s*[:=]\s*(\d+\.?\d*)',
        ],
        'phi': [
            r'\bPHI\s*[:=]\s*(\d+\.?\d*)',
            r'prostate health index\s*[:=]\s*(\d+\.?\d*)',
        ],

        # Gleason score - multiple formats
        'gleason_primary': [
            r'Gleason\s+(?:score\s+)?(\d)\s*\+\s*\d',  # Gleason 3+4 or Gleason score 3+4
            r'Grade\s+Group\s+(\d)',
            r'adenocarcinoma[,\s]+Gleason\s+(?:score\s+)?(\d)\s*\+',  # adenocarcinoma, Gleason 3+4
            r'(?:Right|Left)\s+(?:base|mid|apex)\s+(\d)\s*\+\s*\d',  # External biopsy: Right apex 3+4
            r'(\d)\s*\+\s*\d\s*[=]\s*\d',  # 3+4=7 format
        ],
        'gleason_secondary': [
            r'Gleason\s+(?:score\s+)?\d\s*\+\s*(\d)',
            r'adenocarcinoma[,\s]+Gleason\s+(?:score\s+)?\d\s*\+\s*(\d)',
            r'(?:Right|Left)\s+(?:base|mid|apex)\s+\d\s*\+\s*(\d)',  # External biopsy: Right apex 3+4
            r'\d\s*\+\s*(\d)\s*[=]\s*\d',  # 3+4=7 format
        ],

        # Age
        'age': [
            r'(\d{1,3})[-\s]*y\.?o\.?',  # Handle hyphens: 74yo, 74-y.o., 74 y.o.
            r'(\d{1,3})[-\s]+years?[-\s]+old',  # Handle hyphens: 74-year-old, 74 years old
            r'age\s*[:=]?\s*(\d{1,3})\b',  # age: 74 or age 74 (word boundary to avoid "age 3 months")
        ],

        # Clinical stage
        'clinical_stage': [
            r'[cC]linical\s+stage\s*[:=]?\s*([T][0-9][a-c]?)',
            r'[sS]tage\s*[:=]?\s*([T][0-9][a-c]?)',
            r'\b([T][0-9][a-c])\b',
        ],

        # Biopsy results
        'percent_positive_cores': [
            r'(\d+)\s*/\s*\d+\s+cores?\s+positive',
            r'(\d+\.?\d*)%\s+positive cores',
        ],
        'total_cores': [
            r'\d+\s*/\s*(\d+)\s+cores',
        ],

        # Kidney cancer markers
        'creatinine': [
            r'creatinine\s*[:=]?\s*(\d+\.?\d*)',
            r'Cr\s*[:=]?\s*(\d+\.?\d*)',
        ],
        'calcium': [
            r'calcium\s*[:=]?\s*(\d+\.?\d*)',
            r'Ca\s*[:=]?\s*(\d+\.?\d*)',
        ],
        'hemoglobin': [
            r'hemoglobin\s*[:=]?\s*(\d+\.?\d*)',
            r'Hgb?\s*[:=]?\s*(\d+\.?\d*)',
        ],

        # Tumor characteristics
        'tumor_size_cm': [
            r'tumor\s+size\s*[:=]\s*(\d+\.?\d*)\s*cm',  # Require colon/equals
            r'(?:mass|tumor|lesion).*?(\d+\.?\d*)\s*cm',  # mass/tumor/lesion X cm
        ],

        # IPSS score
        'ipss_score': [
            r'IPSS\s*(?:score|total)?\s*[:=]\s*(\d+)',  # IPSS score: X or IPSS: X
            r'(?:total\s+)?(?:symptom\s+)?score\s*[:=]\s*(\d+)',  # Total score: X
        ],

        # Patient demographics
        'patient_name': [
            r'(?:Patient|Name|Pt\.?)\s*[:=]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?)',  # Patient: Last, First Middle
            r'^\s*([A-Z][a-z]+,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # Last, First Middle at start of line
        ],
        'ssn': [
            r'SSN\s*(?:\(Last\s+4\))?\s*[:=]?\s*(\d{4})',  # SSN (Last 4): 1234 or SSN: 1234
            r'SSN.*?(\d{3}-\d{2}-\d{4})',  # Full SSN: XXX-XX-XXXX
            r'Social\s+Security.*?(\d{3}-\d{2}-\d{4})',  # Social Security Number: XXX-XX-XXXX
        ],
        'dob': [
            r'DOB\s*[:=]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # DOB: MM/DD/YYYY or MM-DD-YYYY
            r'Date\s+of\s+[Bb]irth\s*[:=]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # Date of Birth: MM/DD/YYYY
            r'[Bb]orn\s+on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # Born on MM/DD/YYYY
        ],

        # Prostate volume
        'prostate_volume_cc': [
            r'prostate\s+volume\s*[:=]?\s*(\d+\.?\d*)\s*(?:cc|ml)',
            r'(\d+\.?\d*)\s*(?:cc|ml)\s+prostate',
        ],

        # Vital signs
        'blood_pressure': [
            r'[Bb][Pp]\s*[:=]?\s*(\d{2,3}/\d{2,3})',
            r'Blood\s+[Pp]ressure\s*[:=]?\s*(\d{2,3}/\d{2,3})',
        ],
        'heart_rate': [
            r'[Hh][Rr]\s*[:=]?\s*(\d+)',
            r'Heart\s+[Rr]ate\s*[:=]?\s*(\d+)',
            r'Pulse\s*[:=]?\s*(\d+)',
        ],
        'temperature': [
            r'[Tt]emp\s*[:=]?\s*(\d+\.?\d*)',
            r'[Tt]emperature\s*[:=]?\s*(\d+\.?\d*)',
        ],
        'respiratory_rate': [
            r'[Rr][Rr]\s*[:=]?\s*(\d+)',
            r'Resp\s+[Rr]ate\s*[:=]?\s*(\d+)',
        ],
        'oxygen_saturation': [
            r'[Oo]2\s*[Ss]at\s*[:=]\s*(\d+)%?',  # O2 Sat: 95%
            r'[Oo]xygen\s*[Ss]aturation\s*[:=]\s*(\d+)%?',  # Oxygen Saturation: 95%
            r'[Ss][Pp][Oo]2\s*[:=]\s*(\d+)%?',  # SpO2: 95%
            r'\b[Oo]2\s*[:=]\s*(\d+)%',  # O2: 95% (require % to avoid ambiguity)
        ],

        # Gender (note: first pattern needs special handling to get group 2)
        'gender': [
            r'\b(male|female)\b',  # Simple male/female match
            r'\bgender\s*[:=]?\s*(male|female)\b',
            r'\bsex\s*[:=]?\s*(male|female)\b',
        ],

        # Race/ethnicity for PCPT calculator (african_american boolean)
        'race': [
            # VA demographics format: "Race:  BLACK OR AFRICAN AMERICAN"
            r'Race:\s*(BLACK\s+OR\s+AFRICAN\s+AMERICAN|WHITE|HISPANIC|ASIAN|NATIVE AMERICAN|BLACK|AFRICAN AMERICAN)',
            # General patterns
            r'\b(african[- ]?american|black|caucasian|white|hispanic|asian|native american)\b',
            r'race\s*[:=]?\s*(african[- ]?american|black|caucasian|white|hispanic|asian)',
            r'ethnicity\s*[:=]?\s*(african[- ]?american|black|caucasian|white|hispanic|asian)',
        ],

        # DRE (Digital Rectal Exam) findings for PCPT calculator
        # Matches prostate exam findings: symmetric/asymmetric, firm/hard/nodular
        'dre_findings': [
            # PROSTATE: Approximately 60 grams, moderately enlarged, symmetric, firm
            r'PROSTATE:\s*(?:Approximately\s+)?(?:\d+\s*(?:grams?|g|cc))?,?\s*([^\n]+)',
            # DRE: normal, abnormal, nodular
            r'(?:DRE|digital rectal exam(?:ination)?)\s*[:=]?\s*(normal|abnormal|[^\n,\.]{10,50})',
            # Prostate exam: findings
            r'prostate\s+exam(?:ination)?[:=]?\s*([^\n\.]+)',
            # Prostate on exam was...
            r'prostate\s+(?:was|is|appears?)\s+([^\n\.]+)',
        ],

        # Family history patterns - prostate cancer specific
        'family_history_prostate_cancer': [
            r'family history[:\s]+(?:significant\s+for\s+|positive\s+for\s+|includes?\s+)?.*?(prostate cancer)',
            r'(?:father|brother|grandfather|uncle)\s+(?:has\s+)?(?:history\s+of\s+)?(prostate cancer)',
            r'(prostate cancer)\s+in\s+(?:father|brother|grandfather|uncle|family)',
            r'FH[:\s]+.*?(prostate cancer)',
        ],

        # Prior biopsy patterns
        'prior_biopsy': [
            r'(?:prior|previous|past)\s+(?:prostate\s+)?biopsy\s*[:=]?\s*([^\n\.]+)',
            r'(?:prior|previous)\s+negative\s+biopsy',
            r'biopsy\s+(?:in\s+)?\d{4}[:\s]+([^\n\.]+)',
            r'no\s+prior\s+biopsy',
            r'never\s+(?:had\s+)?(?:a\s+)?biopsy',
        ],
    }

    def __init__(self, llm_manager: Optional[LLMManager] = None, provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize entity extractor.

        Args:
            llm_manager: Optional LLM manager instance
            provider: Optional provider override for LLM extraction (e.g., 'ollama')
            model: Optional model override for LLM extraction (e.g., 'gemini-3-flash-preview:cloud')
        """
        self.llm_manager = llm_manager or LLMManager()
        self._provider = provider
        self._model = model

    def _extract_psa_from_curve(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract PSA value from PSA CURVE section.

        The PSA CURVE section is created by the PSA agent and contains
        validated PSA values. We should use this as the source of truth.

        Returns:
            Dict with PSA entity if found, None otherwise
        """
        # Look for PSA CURVE section
        psa_section_match = re.search(
            r'PSA\s+CURVE:\s*\n((?:.*\n)*?)(?=\n(?:PATHOLOGY|MEDICATIONS|ALLERGIES|LABS|===)|$)',
            text,
            re.IGNORECASE | re.MULTILINE
        )

        if not psa_section_match:
            return None

        psa_section = psa_section_match.group(1)

        # Parse PSA values from the section
        # Format 1: Apr 02, 2025 08:13: 1.82 (colon separator)
        # Format 2: [r] Apr 02, 2025 08:13    1.82 (space separator, HH:MM time)
        # Format 3: [r] Apr 02, 2025 0813    1.82 (space separator, HHMM time - legacy)
        # CRITICAL: Time pattern must handle both HH:MM and HHMM to avoid
        # capturing 4-digit time as PSA value (e.g., 0808 -> 808)
        psa_patterns = [
            # Format: Apr 02, 2025 08:13: 1.82 (colon separator after time)
            r'[A-Za-z]{3}\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2})?:\s*(\d+\.?\d*)H?',
            # Format: [r] Apr 02, 2025 08:13    1.82H (HH:MM time with colon)
            r'\[r\]\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)(?:\s*H)?',
            # Format: [r] Apr 02, 2025 0813    1.82H (HHMM time without colon - legacy)
            # Must match 4-digit time then spaces then decimal PSA value
            r'\[r\]\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{4}\s{2,}(\d+\.?\d*)(?:\s*H)?',
            # Format: [r] Apr 02, 2025         1.82H (no time, padded spaces)
            r'\[r\]\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s{5,}(\d+\.?\d*)(?:\s*H)?',
        ]

        for pattern in psa_patterns:
            match = re.search(pattern, psa_section)
            if match:
                try:
                    psa_value = float(match.group(1))
                    # Validate: PSA should be between 0 and 1000
                    if 0 <= psa_value <= 1000:
                        logger.info(f"Extracted PSA {psa_value} from PSA CURVE section")
                        return {
                            'field': 'psa',
                            'value': psa_value,
                            'confidence': 0.95,  # High confidence - from dedicated PSA section
                            'source_text': f'PSA CURVE: {match.group(0)}',
                            'extraction_method': 'psa_curve_section'
                        }
                except ValueError:
                    continue

        return None

    async def extract_entities(self, clinical_text: str) -> List[Dict[str, Any]]:
        """
        Extract clinical entities from text using both regex and LLM.

        Args:
            clinical_text: Unstructured clinical text

        Returns:
            List of extracted entities with field, value, confidence, source
        """
        entities = []

        # PRIORITY EXTRACTION: Extract PSA from PSA CURVE section first
        # This is the most reliable source as it was already validated by the PSA agent
        psa_from_curve = self._extract_psa_from_curve(clinical_text)
        if psa_from_curve:
            entities.append(psa_from_curve)
            logger.info(f"PSA extracted from PSA CURVE section: {psa_from_curve['value']}")

        # First pass: Regex-based extraction (high confidence)
        regex_entities = self._extract_with_regex(clinical_text)
        entities.extend(regex_entities)

        # Second pass: LLM-based extraction (catches complex patterns)
        try:
            llm_entities = await self._extract_with_llm(clinical_text, regex_entities)
            entities.extend(llm_entities)
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")

        # Deduplicate and prioritize by confidence
        # PSA from curve section will have priority due to higher confidence (0.95)
        entities = self._deduplicate_entities(entities)

        return entities

    def _extract_with_regex(self, text: str) -> List[Dict[str, Any]]:
        """Extract entities using regex patterns."""
        entities = []

        for field, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    try:
                        value = match.group(1)

                        # CRITICAL: Context-aware filtering for age
                        # Skip ages that refer to family members (children, relatives)
                        if field == 'age':
                            if self._is_family_member_age(text, match):
                                logger.debug(
                                    f"Skipping age={value}: appears to be family member age "
                                    f"(context: {match.group(0)})"
                                )
                                continue

                        # Convert to appropriate type
                        if field in ['psa', 'free_psa', 'phi', 'creatinine', 'calcium',
                                    'hemoglobin', 'tumor_size_cm', 'prostate_volume_cc',
                                    'percent_positive_cores', 'temperature']:
                            value = float(value)
                        elif field in ['age', 'gleason_primary', 'gleason_secondary',
                                      'ipss_score', 'total_cores', 'heart_rate', 'respiratory_rate',
                                      'oxygen_saturation']:
                            value = int(value)
                        elif field in ['blood_pressure', 'gender', 'clinical_stage', 'race',
                                      'dre_findings', 'family_history_prostate_cancer', 'prior_biopsy']:
                            # Keep as string for these fields
                            value = str(value).lower() if field in ['gender', 'race'] else str(value)

                        # Validate the extracted value before adding
                        if not self._validate_entity_value(field, value):
                            logger.debug(
                                f"Skipping regex extraction for {field}={value}: "
                                f"failed validation (source: {match.group(0)})"
                            )
                            continue

                        entities.append({
                            'field': field,
                            'value': value,
                            'confidence': 0.9,  # High confidence for regex matches
                            'source_text': match.group(0),
                            'extraction_method': 'regex'
                        })
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Failed to extract {field}: {e}")
                        continue

        return entities

    def _is_family_member_age(self, text: str, match: re.Match) -> bool:
        """
        Determine if an age match refers to a family member rather than the patient.

        Checks surrounding context for indicators like:
        - Child/family descriptors (son, daughter, child, w/, with Down's)
        - Family history sections
        - Family relationship words before the age
        """
        match_start = match.start()
        match_end = match.end()

        # Get context: 100 chars before and 50 chars after the match
        context_start = max(0, match_start - 100)
        context_end = min(len(text), match_end + 50)
        context_before = text[context_start:match_start].lower()
        context_after = text[match_end:context_end].lower()
        full_context = context_before + text[match_start:match_end].lower() + context_after

        # Family member indicators BEFORE the age
        family_indicators_before = [
            'child', 'son', 'daughter', 'wife', 'husband', 'mother', 'father',
            'brother', 'sister', 'aunt', 'uncle', 'niece', 'nephew',
            'grandson', 'granddaughter', 'grandchild'
        ]

        # Family member indicators AFTER the age (within same phrase)
        family_indicators_after = [
            "w/", "w/ down", "with down", "down's", "downs",
            "piano", "cheer", "cheerleader", "church greeter",
            "special needs", "autistic", "autism"
        ]

        # Check if in SOCIAL HISTORY or FAMILY HISTORY section
        # Look back for section headers
        section_context = text[max(0, match_start - 500):match_start].lower()
        in_family_section = any(header in section_context for header in
                                ['family history', 'social history', 'social and personal'])

        # Check for family relationship immediately before the age
        words_before = context_before.split()[-5:] if context_before else []
        has_family_before = any(
            any(ind in word for ind in family_indicators_before)
            for word in words_before
        )

        # Check for child descriptors immediately after the age
        has_family_after = any(ind in context_after for ind in family_indicators_after)

        # If this looks like "17 yo w/ Down's" pattern - definitely family member
        if has_family_after and 'w/' in context_after[:15]:
            return True

        # If in family/social section AND age is young (< 30), likely a dependent
        age_value = int(match.group(1))
        if in_family_section and age_value < 30:
            return True

        # If preceded by family relationship word
        if has_family_before:
            return True

        return False

    def _validate_entity_value(self, field: str, value: Any) -> bool:
        """
        Validate extracted entity values for clinical plausibility.
        Returns True if value is plausible, False otherwise.
        """
        # CRITICAL: Reject values that look like reference ranges or comparison operators
        # This prevents extraction of ">8", "<4.0", ">=0.2", etc.
        if isinstance(value, str):
            value_str = str(value).strip()
            # Reject values starting with comparison operators
            if value_str and value_str[0] in '><~':
                logger.warning(
                    f"Entity validation failed: {field}={value} looks like a reference range "
                    f"(starts with comparison operator)"
                )
                return False
            # Reject values containing comparison operators
            if any(op in value_str for op in ['>=', '<=', '>', '<']):
                logger.warning(
                    f"Entity validation failed: {field}={value} contains comparison operator"
                )
                return False

        # Define clinical value ranges
        validation_rules = {
            'psa': (0.0, 1000.0),  # PSA rarely > 1000 ng/mL
            'age': (10, 120),       # Adult/adolescent urology (reject spurious matches like "3" from "3 months")
            'oxygen_saturation': (70, 100),  # O2 sat 70-100% (below 70% is critical)
            'heart_rate': (20, 250),         # HR 20-250 bpm
            'temperature': (90.0, 108.0),    # Temp 90-108°F
            'respiratory_rate': (4, 60),     # RR 4-60 breaths/min
            'creatinine': (0.0, 30.0),       # Creatinine 0-30 mg/dL
            'hemoglobin': (2.0, 25.0),       # Hemoglobin 2-25 g/dL
            'calcium': (2.0, 20.0),          # Calcium 2-20 mg/dL
            'tumor_size_cm': (0.0, 50.0),    # Tumor size 0-50 cm
            'prostate_volume_cc': (10.0, 500.0),  # Prostate volume 10-500 cc
            'ipss_score': (0, 35),           # IPSS 0-35
            'gleason_primary': (3, 5),       # Gleason pattern 3-5
            'gleason_secondary': (3, 5),     # Gleason pattern 3-5
            'percent_positive_cores': (0.0, 100.0),  # Percentage 0-100
            'total_cores': (1, 50),          # Biopsy cores 1-50
            'free_psa': (0.0, 100.0),        # Free PSA 0-100 ng/mL
            'phi': (0.0, 200.0),             # PHI 0-200
        }

        if field not in validation_rules:
            return True  # No validation rule = accept value

        min_val, max_val = validation_rules[field]

        try:
            # Convert to float for comparison
            numeric_value = float(value)

            if numeric_value < min_val or numeric_value > max_val:
                logger.warning(
                    f"Entity validation failed: {field}={value} is outside "
                    f"plausible range [{min_val}, {max_val}]"
                )
                return False

            return True

        except (ValueError, TypeError):
            # Non-numeric values for fields that should be numeric
            logger.warning(f"Entity validation failed: {field}={value} is not numeric")
            return False

    def _extract_comorbidities_from_pmh(self, text: str) -> List[str]:
        """
        Extract CCI comorbidities from ACTUAL PMH section using rule-based matching.

        This is a GROUNDED extraction - only returns comorbidities that are
        VERIFIED to exist in the patient's actual diagnoses. NO LLM hallucination.

        CRITICAL: Only searches within PMH section, NOT the entire document.
        This prevents false matches from ROS (e.g., "No claudication" triggering PVD).

        Returns:
            List of CCI comorbidity codes found in the actual PMH
        """
        comorbidities = []

        # CRITICAL FIX: Extract ONLY the PMH section from the document
        # This prevents matching negative findings in ROS like "No claudication"
        pmh_section = ""
        pmh_match = re.search(
            r'(?:PAST MEDICAL HISTORY|PMH)[:\s]*\n(.*?)(?=\n\s*(?:PAST SURGICAL|PSH|MEDICATIONS|ALLERGIES|PSA CURVE|PATHOLOGY|===|SOCIAL|FAMILY|SEXUAL)|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if pmh_match:
            pmh_section = pmh_match.group(1)
        else:
            # Fallback: look for numbered diagnosis list
            pmh_section = text

        text_lower = pmh_section.lower()

        # CCI comorbidity mappings - MUST match actual diagnosis text
        cci_mappings = {
            'MI': [
                'myocardial infarction', 'mi ', 'stemi', 'nstemi',
                'st segment elevation myocardial infarction',
                'acute myocardial infarction', 'heart attack'
            ],
            'CHF': [
                'congestive heart failure', 'chf', 'heart failure',
                'left ventricular failure', 'right heart failure',
                'cardiomyopathy with failure', 'systolic dysfunction'
            ],
            'PVD': [
                'peripheral vascular disease', 'pvd', 'peripheral arterial disease',
                'pad', 'claudication', 'arterial insufficiency'
            ],
            'CVA': [
                'cerebrovascular accident', 'cva', 'stroke', 'cerebral infarction',
                'transient ischemic attack', 'transient ischaemic attack',  # US + UK spelling
                'tia', 'cerebral hemorrhage'
            ],
            'dementia': [
                'dementia', "alzheimer", 'cognitive impairment',
                'memory loss', 'vascular dementia'
            ],
            'COPD': [
                'chronic obstructive pulmonary disease', 'copd',
                'emphysema', 'chronic bronchitis', 'chronic airway obstruction'
            ],
            'CTD': [
                'connective tissue disease', 'lupus', 'sle',
                'rheumatoid arthritis', 'scleroderma', 'polymyositis',
                'mixed connective tissue', 'dermatomyositis'
            ],
            'PUD': [
                'peptic ulcer', 'gastric ulcer', 'duodenal ulcer',
                'stomach ulcer', 'gi ulcer'
            ],
            'diabetes': [
                'diabetes mellitus', 'diabetic', 'dm type', 'type 1 diabetes',
                'type 2 diabetes', 'iddm', 'niddm', 'dm2', 'dm1'
            ],
            'CKD': [
                'chronic kidney disease', 'ckd', 'renal failure',
                'chronic renal', 'end stage renal', 'esrd', 'dialysis',
                'renal insufficiency'
            ],
            'hemiplegia': [
                'hemiplegia', 'hemiparesis', 'paralysis', 'paraplegia',
                'quadriplegia', 'tetraplegia'
            ],
            'cancer': [
                'malignant neoplasm', 'carcinoma', 'adenocarcinoma',
                'cancer', 'lymphoma', 'leukemia', 'myeloma'
            ],
            'liver_mild': [
                'chronic hepatitis', 'hepatitis b', 'hepatitis c',
                'nash', 'nafld'
                # NOTE: 'fatty liver' and 'steatosis' REMOVED - simple hepatic steatosis
                # is NOT a CCI condition. CCI liver_mild = chronic liver disease only.
            ],
            'liver_severe': [
                'cirrhosis', 'liver cirrhosis', 'hepatic cirrhosis',
                'liver failure', 'portal hypertension', 'esophageal varices'
            ],
            'metastatic_cancer': [
                'metastatic', 'metastasis', 'stage iv cancer',
                'disseminated cancer', 'advanced cancer with mets'
            ],
            'AIDS': [
                'aids', 'hiv/aids', 'acquired immunodeficiency'
            ]
        }

        # Check each CCI condition against actual PMH text
        for cci_code, keywords in cci_mappings.items():
            for keyword in keywords:
                if keyword in text_lower:
                    # IMPORTANT: Exclude metastatic_cancer if just "cancer" found
                    # and no metastatic indicators
                    if cci_code == 'cancer':
                        # Check if it's actually metastatic
                        if any(m in text_lower for m in ['metastatic', 'metastasis', 'stage iv']):
                            if 'metastatic_cancer' not in comorbidities:
                                comorbidities.append('metastatic_cancer')
                        else:
                            if cci_code not in comorbidities:
                                comorbidities.append(cci_code)
                    elif cci_code not in comorbidities:
                        comorbidities.append(cci_code)
                    break  # Found this condition, move to next

        logger.debug(f"Extracted comorbidities from PMH (grounded): {comorbidities}")
        return comorbidities

    async def _extract_with_llm(self, text: str, existing_entities: List[Dict]) -> List[Dict[str, Any]]:
        """Use LLM to extract entities that regex might miss."""

        # Build list of already extracted fields
        extracted_fields = {e['field'] for e in existing_entities}

        # CRITICAL FIX: Extract comorbidities using GROUNDED rule-based method
        # NOT LLM hallucination. This prevents the LLM from inventing conditions.
        grounded_comorbidities = self._extract_comorbidities_from_pmh(text)

        # LLM prompt for entity extraction - COMORBIDITIES REMOVED to prevent hallucination
        prompt = f"""Extract structured clinical data from this text. Return ONLY a JSON object with the extracted values.

Clinical Text:
{text}

Extract these fields if present:
- psa (ng/mL) - most recent PSA value. MUST be a pure numeric value (e.g., 4.5). Do NOT extract reference ranges like ">4.0", "<0.2", or "0.2-4.0". Only extract the actual measured PSA value.
- age (years) - pure numeric value
- gender (male or female)
- race (african american, black, caucasian, white, hispanic, asian)
- gleason_primary (primary Gleason pattern, 3-5)
- gleason_secondary (secondary Gleason pattern, 3-5)
- clinical_stage (T stage: T1, T1c, T2a, T2b, T2c, T3a, etc.)
- percent_positive_cores (percentage)
- total_cores (number)
- creatinine (mg/dL) - actual measured value, NOT reference ranges
- calcium (mg/dL) - actual measured value, NOT reference ranges
- hemoglobin (g/dL) - actual measured value, NOT reference ranges
- tumor_size_cm (centimeters)
- prostate_volume_cc (cc)
- ipss_score (0-35)
- dre_abnormal (true/false - was digital rectal exam abnormal? Look for nodule, induration, asymmetry, hardness)
- family_history_prostate_cancer (true/false - does patient have family history of prostate cancer in father, brother, grandfather?)
- prior_negative_biopsy (true/false - has patient had a prior prostate biopsy that was negative/benign?)
- health_status (excellent, good, fair, or poor)

CRITICAL: For all numeric values (psa, age, creatinine, hemoglobin, etc.), return ONLY the actual measured value as a plain number. Do NOT include:
- Reference ranges (e.g., "0.2-4.0", ">4", "<10")
- Comparison operators (>, <, >=, <=)
- Units (ng/mL, mg/dL)
- Flags (H, L, HIGH, LOW)

Return JSON format:
{{
  "psa": 8.5,
  "age": 72,
  "gender": "male",
  "race": "caucasian",
  "dre_abnormal": false,
  "family_history_prostate_cancer": true,
  "prior_negative_biopsy": false,
  "health_status": "fair"
}}

For DRE findings, look in PHYSICAL EXAM section for PROSTATE or RECTAL findings.
For family history, look in FAMILY HISTORY section for prostate cancer in relatives.
For prior biopsy, look in HPI or PATHOLOGY for mention of previous biopsies.

If a value is not mentioned or unclear, do not include it in the JSON.
Return ONLY the JSON object, no additional text."""

        try:
            # Use the configured extraction model
            # Default uses LLM Manager's primary provider. Can be overridden
            # by passing provider/model to the constructor or via task_config.
            response = await self.llm_manager.generate(
                prompt=prompt,
                provider=getattr(self, '_provider', None),
                model=getattr(self, '_model', None),
                temperature=0.0,  # Deterministic
                max_tokens=500
            )

            # Parse JSON response - extract content from LLMResponse object
            response_text = response.content if hasattr(response, 'content') else str(response)
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                extracted_data = json.loads(json_match.group(0))

                entities = []
                for field, value in extracted_data.items():
                    # Skip if already extracted with regex
                    if field in extracted_fields:
                        continue

                    # CRITICAL FIX: Filter out None/null/empty values
                    # Only add entities that have actual, valid values
                    if value is None or value == "" or value == "null":
                        logger.debug(f"Skipping LLM extraction for {field}: value is None/empty")
                        continue

                    # For lists (like comorbidities), skip if empty
                    if isinstance(value, list) and len(value) == 0:
                        logger.debug(f"Skipping LLM extraction for {field}: empty list")
                        continue

                    # Validate numeric values (skip validation for lists like comorbidities)
                    if not isinstance(value, list) and not self._validate_entity_value(field, value):
                        logger.debug(f"Skipping LLM extraction for {field}={value}: failed validation")
                        continue

                    entities.append({
                        'field': field,
                        'value': value,
                        'confidence': 0.7,  # Medium confidence for LLM extraction
                        'source_text': text[:100],  # First 100 chars as context
                        'extraction_method': 'llm'
                    })

                # CRITICAL: Add grounded comorbidities (rule-based, not LLM)
                # This prevents hallucination of conditions like CHF, COPD, diabetes, CKD
                if grounded_comorbidities and 'comorbidities' not in extracted_fields:
                    entities.append({
                        'field': 'comorbidities',
                        'value': grounded_comorbidities,
                        'confidence': 0.95,  # High confidence - rule-based extraction
                        'source_text': 'Extracted from PAST MEDICAL HISTORY',
                        'extraction_method': 'grounded_rules'
                    })
                    logger.info(f"Added grounded comorbidities: {grounded_comorbidities}")

                return entities

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            # Even if LLM fails, return grounded comorbidities
            if grounded_comorbidities and 'comorbidities' not in extracted_fields:
                return [{
                    'field': 'comorbidities',
                    'value': grounded_comorbidities,
                    'confidence': 0.95,
                    'source_text': 'Extracted from PAST MEDICAL HISTORY',
                    'extraction_method': 'grounded_rules'
                }]
            return []

        # Even if no JSON match, return grounded comorbidities
        if grounded_comorbidities and 'comorbidities' not in extracted_fields:
            return [{
                'field': 'comorbidities',
                'value': grounded_comorbidities,
                'confidence': 0.95,
                'source_text': 'Extracted from PAST MEDICAL HISTORY',
                'extraction_method': 'grounded_rules'
            }]
        return []

    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """
        Remove duplicate entities, keeping best value.

        For PSA: Keep the FIRST value found (most recent from PSA CURVE which is reverse chronological)
        For age: Keep value closest to typical adult age range (55-85 for urology)
        For others: Keep highest confidence
        """
        seen_fields = {}

        for entity in entities:
            field = entity['field']
            value = entity['value']

            if field not in seen_fields:
                seen_fields[field] = entity
            else:
                existing = seen_fields[field]

                # FIX: For PSA, keep HIGHEST CONFIDENCE value (PSA CURVE section has 0.95)
                # PSA from curve section is most reliable as it's validated by PSA agent
                if field == 'psa':
                    # Keep the higher confidence value
                    # PSA from curve section (0.95) > regex (0.9) > LLM (0.7)
                    if entity['confidence'] > existing['confidence']:
                        seen_fields[field] = entity
                    # If same confidence, keep first (most recent from reverse-chronological curve)
                    # else keep existing

                # Special handling for age: prefer value in typical adult range
                elif field == 'age':
                    try:
                        new_age = int(value)
                        old_age = int(existing['value'])
                        # Prefer age in 50-90 range for urology patients
                        new_in_range = 50 <= new_age <= 90
                        old_in_range = 50 <= old_age <= 90
                        if new_in_range and not old_in_range:
                            seen_fields[field] = entity
                        elif new_in_range and old_in_range:
                            # If both in range, keep higher confidence or higher age
                            if entity['confidence'] > existing['confidence'] or new_age > old_age:
                                seen_fields[field] = entity
                    except (ValueError, TypeError):
                        pass

                # Default: keep highest confidence
                elif entity['confidence'] > existing['confidence']:
                    seen_fields[field] = entity

        return list(seen_fields.values())

    def derive_calculator_inputs(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Derive calculator-specific boolean inputs from extracted entities.

        Converts raw extractions like 'dre_findings' text to boolean 'dre_abnormal',
        'race' to 'african_american' boolean, etc.

        Returns:
            Dictionary with calculator input fields and their derived values
        """
        calculator_inputs = {}
        entity_dict = {e['field']: e for e in entities}

        # 1. Derive african_american from race
        if 'race' in entity_dict:
            race_value = str(entity_dict['race']['value']).lower()
            is_african_american = any(term in race_value for term in
                                      ['african', 'black', 'african-american', 'african american'])
            calculator_inputs['african_american'] = is_african_american
            logger.debug(f"Derived african_american={is_african_american} from race='{race_value}'")

        # 2. Derive dre_abnormal from dre_findings
        if 'dre_findings' in entity_dict:
            dre_text = str(entity_dict['dre_findings']['value']).lower()

            # Strong abnormal DRE indicators (definitely abnormal)
            abnormal_indicators = ['nodule', 'nodular', 'indurat', 'hard',
                                   'asymmetr', 'irregular', 'suspicious', 'abnormal',
                                   'mass', 'lesion', 'palpable tumor', 'cancer']

            # Normal DRE indicators
            normal_indicators = ['normal', 'benign', 'smooth', 'non-tender', 'nontender',
                                 'symmetric', 'soft', 'no nodule', 'unremarkable', 'wnl',
                                 'within normal', 'deferred', 'no abnormal', 'negative',
                                 'moderately enlarged']  # BPH is not abnormal DRE

            # "firm" is normal when with "symmetric" (BPH), abnormal when isolated or with "hard"
            firm_is_abnormal = 'firm' in dre_text and 'symmetric' not in dre_text

            has_abnormal = any(ind in dre_text for ind in abnormal_indicators) or firm_is_abnormal
            has_normal = any(ind in dre_text for ind in normal_indicators)

            # Determine DRE abnormality
            if has_abnormal and not has_normal:
                calculator_inputs['dre_abnormal'] = True
            elif has_normal:
                calculator_inputs['dre_abnormal'] = False
            elif 'deferred' in dre_text or 'not performed' in dre_text:
                # Exam deferred - don't set (user will need to enter)
                pass
            else:
                # Default to False if findings are ambiguous but not clearly abnormal
                calculator_inputs['dre_abnormal'] = False

            logger.debug(f"Derived dre_abnormal={calculator_inputs.get('dre_abnormal')} from dre='{dre_text}'")

        # 3. Derive family_history (prostate cancer) from family_history_prostate_cancer
        if 'family_history_prostate_cancer' in entity_dict:
            # If we found a match, family history is positive
            calculator_inputs['family_history'] = True
            logger.debug("Derived family_history=True from family history prostate cancer match")

        # 4. Derive prior_negative_biopsy from prior_biopsy
        if 'prior_biopsy' in entity_dict:
            biopsy_text = str(entity_dict['prior_biopsy']['value']).lower()
            # Check for negative/benign indicators
            negative_indicators = ['negative', 'benign', 'no cancer', 'no malignancy',
                                   'bph', 'atypical', 'atypia', 'asap']
            positive_indicators = ['cancer', 'adenocarcinoma', 'malignant', 'gleason']
            no_biopsy_indicators = ['no prior', 'never', 'first', 'initial']

            has_negative = any(ind in biopsy_text for ind in negative_indicators)
            has_positive = any(ind in biopsy_text for ind in positive_indicators)
            has_no_biopsy = any(ind in biopsy_text for ind in no_biopsy_indicators)

            if has_no_biopsy:
                calculator_inputs['prior_negative_biopsy'] = False
            elif has_negative and not has_positive:
                calculator_inputs['prior_negative_biopsy'] = True
            elif has_positive:
                calculator_inputs['prior_negative_biopsy'] = False  # Has cancer, not a "negative" biopsy

            logger.debug(f"Derived prior_negative_biopsy={calculator_inputs.get('prior_negative_biopsy')} from biopsy='{biopsy_text}'")
        else:
            # No prior biopsy information found - default to False (no prior negative biopsy)
            # This is a reasonable default for PCPT calculator when biopsy status is unknown
            calculator_inputs['prior_negative_biopsy'] = False
            logger.debug("No prior biopsy information found, defaulting prior_negative_biopsy=False")

        # 5. Pass through standard numeric fields
        standard_fields = ['age', 'psa', 'gleason_primary', 'gleason_secondary',
                          'ipss_score', 'prostate_volume_cc', 'tumor_size_cm',
                          'creatinine', 'hemoglobin', 'calcium']
        for field in standard_fields:
            if field in entity_dict:
                calculator_inputs[field] = entity_dict[field]['value']

        return calculator_inputs
