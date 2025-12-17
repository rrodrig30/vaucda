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
        'psa': [
            r'\bPSA\s+TOTAL\s*[:=]?\s*(\d+\.?\d*)',  # PSA TOTAL (lab format)
            r'\bPSA\s*[:=]\s*(\d+\.?\d*)\s*(?:ng/ml|ng/mL)',  # PSA: X ng/mL
            r'\bPSA\s+(?:level|value)\s*[:=]?\s*(\d+\.?\d*)',  # PSA level/value
            r'prostate[-\s]specific antigen\s*[:=]\s*(\d+\.?\d*)',
            # PSA CURVE format: [r] Jun 24, 2024 09:36    0.52
            r'\[r\]\s+\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)',
        ],
        'free_psa': [
            r'free\s+PSA\s*[:=]\s*(\d+\.?\d*)',
            r'fPSA\s*[:=]\s*(\d+\.?\d*)',
        ],
        'phi': [
            r'\bPHI\s*[:=]\s*(\d+\.?\d*)',
            r'prostate health index\s*[:=]\s*(\d+\.?\d*)',
        ],

        # Gleason score
        'gleason_primary': [
            r'Gleason\s+(\d)\s*\+\s*\d',
            r'Grade\s+Group\s+(\d)',
        ],
        'gleason_secondary': [
            r'Gleason\s+\d\s*\+\s*(\d)',
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
            r'SSN.*?(\d{3}-\d{2}-\d{4})',  # Full SSN: 123-45-6789
            r'Social\s+Security.*?(\d{3}-\d{2}-\d{4})',  # Social Security Number: 123-45-6789
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
    }

    def __init__(self, llm_manager: Optional[LLMManager] = None):
        """Initialize entity extractor."""
        self.llm_manager = llm_manager or LLMManager()

    async def extract_entities(self, clinical_text: str) -> List[Dict[str, Any]]:
        """
        Extract clinical entities from text using both regex and LLM.

        Args:
            clinical_text: Unstructured clinical text

        Returns:
            List of extracted entities with field, value, confidence, source
        """
        entities = []

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

                        # Convert to appropriate type
                        if field in ['psa', 'free_psa', 'phi', 'creatinine', 'calcium',
                                    'hemoglobin', 'tumor_size_cm', 'prostate_volume_cc',
                                    'percent_positive_cores', 'temperature']:
                            value = float(value)
                        elif field in ['age', 'gleason_primary', 'gleason_secondary',
                                      'ipss_score', 'total_cores', 'heart_rate', 'respiratory_rate',
                                      'oxygen_saturation']:
                            value = int(value)
                        elif field in ['blood_pressure', 'gender', 'clinical_stage']:
                            # Keep as string for blood pressure, gender, clinical stage
                            value = str(value).lower() if field == 'gender' else str(value)

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

    def _validate_entity_value(self, field: str, value: Any) -> bool:
        """
        Validate extracted entity values for clinical plausibility.
        Returns True if value is plausible, False otherwise.
        """
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

    async def _extract_with_llm(self, text: str, existing_entities: List[Dict]) -> List[Dict[str, Any]]:
        """Use LLM to extract entities that regex might miss."""

        # Build list of already extracted fields
        extracted_fields = {e['field'] for e in existing_entities}

        # LLM prompt for entity extraction
        prompt = f"""Extract structured clinical data from this text. Return ONLY a JSON object with the extracted values.

Clinical Text:
{text}

Extract these fields if present:
- psa (ng/mL)
- age (years)
- gender (male or female)
- gleason_primary (primary Gleason pattern, 3-5)
- gleason_secondary (secondary Gleason pattern, 3-5)
- clinical_stage (T stage: T1, T1c, T2a, T2b, T2c, T3a, etc.)
- percent_positive_cores (percentage)
- total_cores (number)
- creatinine (mg/dL)
- calcium (mg/dL)
- hemoglobin (g/dL)
- tumor_size_cm (centimeters)
- prostate_volume_cc (cc)
- ipss_score (0-35)
- comorbidities (array of condition codes from PMH: MI, CHF, PVD, CVA, dementia, COPD, CTD, PUD, diabetes, CKD, hemiplegia, cancer, liver_mild, liver_severe, metastatic_cancer, AIDS)
- health_status (excellent, good, fair, or poor)

Return JSON format:
{{
  "psa": 8.5,
  "age": 72,
  "gender": "male",
  "comorbidities": ["diabetes", "CHF", "COPD"],
  "health_status": "fair",
  ...
}}

For comorbidities, look in the PAST MEDICAL HISTORY section and map diagnoses to codes:
- Myocardial infarction → MI
- Heart failure, CHF → CHF
- Peripheral vascular disease → PVD
- Stroke, CVA → CVA
- Dementia → dementia
- COPD, emphysema, chronic bronchitis → COPD
- Connective tissue disease, lupus, RA → CTD
- Peptic ulcer → PUD
- Diabetes → diabetes
- Kidney disease, CKD, renal failure → CKD
- Hemiplegia, paralysis → hemiplegia
- Cancer (not metastatic) → cancer
- Liver disease (mild) → liver_mild
- Liver cirrhosis (severe) → liver_severe
- Metastatic cancer → metastatic_cancer
- AIDS → AIDS

If a value is not mentioned or unclear, do not include it in the JSON.
Return ONLY the JSON object, no additional text."""

        try:
            # Use fast model for extraction
            response = await self.llm_manager.generate(
                prompt=prompt,
                provider="ollama",
                model="llama3.1:8b",
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

                return entities

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return []

        return []

    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Remove duplicate entities, keeping highest confidence."""
        seen_fields = {}

        for entity in entities:
            field = entity['field']
            if field not in seen_fields or entity['confidence'] > seen_fields[field]['confidence']:
                seen_fields[field] = entity

        return list(seen_fields.values())
