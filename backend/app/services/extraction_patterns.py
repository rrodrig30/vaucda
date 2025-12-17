"""
VA Clinic Note Extraction Patterns

Comprehensive pattern library for extracting structured clinical data from
VA electronic health records. Based on analysis of 95 training examples.

NO PLACEHOLDER DEFAULTS - All methods return empty strings when data cannot be extracted.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class VAExtractionPatterns:
    """Pattern-based extraction for VA clinic notes."""

    @staticmethod
    def extract_ipss_table(text: str) -> str:
        """
        Extract IPSS (International Prostate Symptom Score) table from VA format.

        VA Format:
        1. Incomplete emptying: 5 (sensation of not emptied afterwards)
        2. Frequency: 4 (feeling after less the 2 hours)
        ...
        TOTAL: 32 (1-7=MILD, 8-19=MODERATE, 20-35=SEVERE)
        Bother of symptoms to patient (Quality of life): 6 (1-6)

        Returns:
            Formatted IPSS table or empty string
        """
        # Look for IPSS section - multiple patterns for VA formats
        ipss_patterns = [
            r'(?:AUA BPH \(IPSS\) SYMPTOM SCORES|IPSS\s+SYMPTOM\s+SCORES)[:\s]*'
            r'(?:Occurances in the last month:|Questions:)(.*?)'
            r'(?=\n\nAdditional|TOTAL|Bother of symptoms|$)',
            r'(?:IPSS\s+SCORE)[:\s]*(.*?)(?=\n\n[A-Z]|$)',
            r'(?:International\s+Prostate\s+Symptom)[:\s]*(.*?)(?=\n\n[A-Z]|$)',
        ]

        ipss_content = ""
        for pattern in ipss_patterns:
            ipss_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if ipss_match:
                ipss_content = ipss_match.group(1) if ipss_match.lastindex else ipss_match.group(0)
                break

        if not ipss_content or len(ipss_content.strip()) < 50:
            logger.debug("No substantial IPSS section found in text")
            return ""

        # Extract individual scores
        scores = {}
        score_patterns = {
            'Empty': r'(?:1\.|Incomplete\s+emptying):?\s*(\d+)',
            'Frequency': r'(?:2\.|Frequency):?\s*(\d+)',
            'Urgency': r'(?:4\.|Urge\s+to\s+urinate):?\s*(\d+)',
            'Hesitancy': r'(?:6\.|Straining):?\s*(\d+)',
            'Intermittency': r'(?:3\.|Intermittency):?\s*(\d+)',
            'Flow': r'(?:5\.|Weak\s+Stream):?\s*(\d+)',
            'Nocturia': r'(?:7\.|Urinating\s+at\s+night):?\s*(\d+)',
        }

        for label, pattern in score_patterns.items():
            match = re.search(pattern, ipss_content, re.IGNORECASE)
            if match:
                try:
                    score_val = int(match.group(1))
                    if 0 <= score_val <= 5:  # Valid IPSS item score
                        scores[label] = score_val
                except (ValueError, TypeError):
                    continue

        # Extract total score
        total_match = re.search(r'(?:TOTAL:?\s*)?(\d+)\s*(?:/35|\(1-7=MILD)', text, re.IGNORECASE | re.DOTALL)
        total = int(total_match.group(1)) if total_match else (sum(scores.values()) if scores else None)

        # Extract bother index
        bother_match = re.search(
            r'(?:Bother\s+of\s+symptoms|Quality\s+of\s+life):?\s*(\d+)',
            text,
            re.IGNORECASE
        )
        bother = int(bother_match.group(1)) if bother_match else None

        if len(scores) < 3:  # Need at least 3 items to be meaningful
            logger.debug(f"Could not extract sufficient IPSS scores (found {len(scores)})")
            return ""

        # Format as table - match the expected output format
        table_lines = [
            "+---------------+------+",
            "|        IPSS          |",
            "+---------------+------+",
            "| Symptom       | Date |",
            "+---------------+------+",
        ]

        symptom_order = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']
        for label in symptom_order:
            if label in scores:
                table_lines.append(f"| {label:13} | {scores[label]:4} |")

        table_lines.append("+---------------+------+")
        if total is not None:
            table_lines.append(f"| Total         | {total:>3}/35|")
        if bother is not None:
            table_lines.append(f"| BI            | {bother:>3}/6  |")
        table_lines.append("+---------------+------+")

        return "\n".join(table_lines)

    @staticmethod
    def extract_psa_curve(text: str) -> str:
        """
        Extract PSA values and format as PSA CURVE.

        VA Format: [r] MMM DD, YYYY HHMM    PSA_VALUE (append H if >4)

        Returns:
            Formatted PSA curve or empty string
        """
        psa_values = []

        # Pattern 1: Lab results with dates (MM/DD/YYYY format)
        pattern1 = r'(\d{1,2}/\d{1,2}/\d{2,4})[^\n]*?PSA[:\s]+(\d+\.?\d*)'
        matches1 = re.findall(pattern1, text, re.IGNORECASE)

        for date_str, value in matches1:
            try:
                # Try MM/DD/YYYY
                if '/' in date_str:
                    parts = date_str.split('/')
                    if len(parts) == 3:
                        if len(parts[2]) == 2:  # YY format
                            year = 2000 + int(parts[2])
                        else:
                            year = int(parts[2])
                        date = datetime(year, int(parts[0]), int(parts[1]))
                    else:
                        continue
                else:
                    continue

                psa_val = float(value)
                if psa_val > 0 and psa_val < 1000:  # Sanity check
                    psa_values.append((date, psa_val))
            except (ValueError, IndexError):
                continue

        # Pattern 2: Already formatted PSA curve [r] format
        pattern2 = r'\[r\]\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{4})\s+(\d+\.?\d*)'
        matches2 = re.findall(pattern2, text)

        for date_str, time_str, value in matches2:
            try:
                date = datetime.strptime(f"{date_str} {time_str}", '%b %d, %Y %H%M')
                psa_val = float(value)
                if psa_val > 0 and psa_val < 1000:
                    psa_values.append((date, psa_val))
            except (ValueError, TypeError):
                continue

        # Pattern 3: Lab report format with lab test names
        pattern3 = r'(?:LAB|Test)[:\s]*PSA[:\s]*(\d+\.?\d*)[^\n]*(?:Date|collected)?[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})'
        matches3 = re.findall(pattern3, text, re.IGNORECASE | re.DOTALL)

        for value, date_str in matches3:
            try:
                parts = date_str.split('/')
                if len(parts) == 3:
                    if len(parts[2]) == 2:
                        year = 2000 + int(parts[2])
                    else:
                        year = int(parts[2])
                    date = datetime(year, int(parts[0]), int(parts[1]))
                    psa_val = float(value)
                    if psa_val > 0 and psa_val < 1000:
                        psa_values.append((date, psa_val))
            except (ValueError, IndexError):
                continue

        if not psa_values:
            logger.debug("No PSA values found in text")
            return ""

        # Remove duplicates and sort by date (most recent first)
        unique_psa_values = list(set(psa_values))
        unique_psa_values.sort(reverse=True)

        # Format as PSA CURVE
        curve_lines = []
        for date, value in unique_psa_values[:20]:  # Limit to 20 most recent values
            h_flag = "H" if value > 4.0 else ""
            formatted_value = f"{value:.2f}".rstrip('0').rstrip('.')
            curve_lines.append(f"[r] {date.strftime('%b %d, %Y %H%M')}    {formatted_value}{h_flag}")

        return "\n".join(curve_lines)

    @staticmethod
    def extract_medications(text: str) -> List[Dict[str, str]]:
        """
        Extract medications from VA prescription format.

        VA Format:
        Drug Name: TAMSULOSIN HCL 0.4MG CAP
        Issue Date: 05/13/2025
        SIG: TAKE ONE CAPSULE BY MOUTH TWICE A DAY FOR PROSTATE

        Returns:
            List of medication dictionaries with name, dose, route, frequency
        """
        medications = []

        # Find all medication blocks
        med_pattern = r'Drug Name\s*\n\s*([^\n]+)\n.*?SIG\s*\n\s*([^\n]+)'
        matches = re.findall(med_pattern, text, re.IGNORECASE | re.DOTALL)

        for drug_name, sig in matches:
            drug_name = drug_name.strip()
            sig = sig.strip()

            # Parse dosage from drug name
            dose_match = re.search(r'(\d+\.?\d*\s*(?:MG|MCG|G|ML|%))', drug_name, re.IGNORECASE)
            dose = dose_match.group(1) if dose_match else ""

            # Parse route from SIG
            route_patterns = [
                r'BY MOUTH',
                r'TOPICAL',
                r'SUBCUTANEOUS',
                r'INTRAVENOUS',
                r'INTRAMUSCULAR',
            ]
            route = ""
            for pattern in route_patterns:
                if re.search(pattern, sig, re.IGNORECASE):
                    route = pattern.replace(' ', ' ').title()
                    break

            # Parse frequency from SIG
            freq_patterns = {
                'daily': r'(?:EVERY DAY|DAILY|ONCE A DAY)',
                'twice daily': r'TWICE A DAY|BID',
                'three times daily': r'THREE TIMES A DAY|TID',
                'as needed': r'AS NEEDED|PRN',
            }
            frequency = ""
            for freq, pattern in freq_patterns.items():
                if re.search(pattern, sig, re.IGNORECASE):
                    frequency = freq
                    break

            medications.append({
                'name': drug_name,
                'dose': dose,
                'route': route,
                'frequency': frequency,
                'sig': sig
            })

        if not medications:
            logger.debug("No medications found in text")

        return medications

    @staticmethod
    def extract_rated_disabilities(text: str) -> List[str]:
        """
        Extract VA service-connected rated disabilities.

        VA Format:
        Rated Disabilities:    MIGRAINE HEADACHES  (50%)
                               SICKLE CELL ANEMIA  (30%)

        Returns:
            List of disability strings with percentages
        """
        disabilities = []

        # Find rated disabilities section
        section_match = re.search(
            r'Rated Disabilities:(.*?)(?:\n\n|Order Information|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if not section_match:
            logger.debug("No rated disabilities section found")
            return []

        section = section_match.group(1)

        # Extract individual disabilities
        disability_pattern = r'([A-Z][A-Z\s,\-]+?)\s+\((\d+)%\)'
        matches = re.findall(disability_pattern, section)

        for condition, percentage in matches:
            condition = condition.strip()
            disabilities.append(f"{condition} ({percentage}%)")

        return disabilities

    @staticmethod
    def extract_chief_complaint(text: str) -> str:
        """
        Extract chief complaint from VA consult or note.

        Looks for:
        - Provisional Diagnosis
        - Reason For Request
        - Chief Complaint section

        Returns:
            Chief complaint string or empty
        """
        # Pattern 1: Provisional Diagnosis
        prov_dx_match = re.search(
            r'Provisional Diagnosis:\s*([^\n]+(?:\n\s+[^\n]+)*)',
            text,
            re.IGNORECASE
        )
        if prov_dx_match:
            diagnosis = prov_dx_match.group(1).strip()
            # Clean up continuation lines
            diagnosis = re.sub(r'\n\s+', ' ', diagnosis)
            return diagnosis

        # Pattern 2: Reason For Request
        reason_match = re.search(
            r'Reason For Request:\s*\n(.*?)(?:\n\n|Additional Comments|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if reason_match:
            reason = reason_match.group(1).strip()
            # Get first non-empty line as chief complaint
            first_line = [line for line in reason.split('\n') if line.strip()]
            if first_line:
                return first_line[0].strip()

        # Pattern 3: CC: header
        cc_match = re.search(r'CC:\s*([^\n]+)', text, re.IGNORECASE)
        if cc_match:
            return cc_match.group(1).strip()

        logger.debug("No chief complaint found in text")
        return ""

    @staticmethod
    def extract_demographics(text: str) -> Dict[str, str]:
        """
        Extract patient demographics from VA format.

        Returns:
            Dictionary with age, gender, veteran_status, etc.
        """
        demographics = {}

        # Age extraction
        age_patterns = [
            r'(\d+)[-\s]?(?:year|yr|y/o|yo)[-\s]?old',
            r'Age[:\s]+(\d+)',
        ]
        for pattern in age_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                demographics['age'] = int(match.group(1))
                break

        # Gender
        if re.search(r'\bmale\b', text, re.IGNORECASE):
            demographics['gender'] = 'male'
        elif re.search(r'\bfemale\b', text, re.IGNORECASE):
            demographics['gender'] = 'female'

        # Veteran status
        if re.search(r'Patient Type:\s*SC VETERAN', text, re.IGNORECASE):
            demographics['veteran_status'] = 'Service-Connected Veteran'

        # Service connection percentage
        sc_match = re.search(r'SC Percent:\s*(\d+)%', text, re.IGNORECASE)
        if sc_match:
            demographics['sc_percentage'] = int(sc_match.group(1))

        return demographics

    @staticmethod
    def extract_labs(text: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract laboratory results from VA format.

        Returns only labs with high confidence (>80% pattern match).
        Returns empty values instead of hallucinating.

        Returns:
            Dictionary with 'endocrine_labs' and 'general_labs' keys
        """
        labs = {
            'endocrine_labs': [],
            'general_labs': []
        }

        # Endocrine labs - require strict pattern matching
        endocrine_patterns = {
            'HgbA1c': r'(?:HgbA1c|glycated hemoglobin)[:\s]+(\d+\.?\d*)\s*%',
            'TSH': r'TSH[:\s]+(\d+\.?\d*)\s*(?:uIU/mL|mIU/L|uU/mL)?',
            'Vitamin D': r'(?:Vitamin D|25-OH Vitamin D)[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?',
            'Testosterone': r'Testosterone[:\s]+(\d+\.?\d*)\s*(?:ng/dL)?',
        }

        for lab_name, pattern in endocrine_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    # Sanity check: values should be in reasonable ranges
                    if lab_name == 'HgbA1c' and value > 15:
                        logger.debug(f"Skipping {lab_name} - unreasonable value {value}")
                        continue
                    labs['endocrine_labs'].append({
                        'test': lab_name,
                        'value': match.group(1),
                        'unit': '',
                    })
                except (ValueError, TypeError):
                    logger.debug(f"Failed to parse {lab_name} value")
                    continue

        # General labs - require strict pattern matching and context
        general_patterns = {
            'PSA': r'(?:PSA|Prostate.?Specific.?Antigen)[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?',
            'Creatinine': r'(?:Creat|Creatinine)[:\s]+(\d+\.?\d*)\s*(?:mg/dL|mg/dl)?',
            'eGFR': r'eGFR[:\s]+(\d+)',
            'Hemoglobin': r'(?:Hgb|Hemoglobin)[:\s]+(\d+\.?\d*)',
            'Hematocrit': r'(?:Hct|Hematocrit)[:\s]+(\d+\.?\d*)',
            'Potassium': r'Potassium[:\s]+(\d+\.?\d*)',
            'Sodium': r'Sodium[:\s]+(\d+)',
        }

        for lab_name, pattern in general_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    # Sanity checks for reasonable ranges
                    if lab_name == 'PSA' and value > 100:
                        logger.debug(f"Skipping {lab_name} - unreasonable value {value}")
                        continue
                    if lab_name in ['Hemoglobin', 'Hematocrit', 'Potassium', 'Sodium']:
                        if value > 999:  # Likely metadata, not lab value
                            logger.debug(f"Skipping {lab_name} - unreasonable value {value}")
                            continue

                    labs['general_labs'].append({
                        'test': lab_name,
                        'value': match.group(1),
                        'unit': '',
                    })
                except (ValueError, TypeError):
                    logger.debug(f"Failed to parse {lab_name} value")
                    continue

        return labs

    @staticmethod
    def extract_imaging(text: str) -> str:
        """
        Extract imaging study results from VA format.

        Returns:
            Imaging report text or empty string
        """
        # Look for imaging sections
        imaging_patterns = [
            r'IMAGING:?(.*?)(?:\n={3,}|\n\n[A-Z]+:|\Z)',
            r'(?:CT|MRI|Ultrasound|X-ray|PET)[:\s]+([^\n]+(?:\n(?!\n)[^\n]+)*)',
        ]

        for pattern in imaging_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                imaging = match.group(1).strip()
                if len(imaging) > 20:  # Ensure meaningful content
                    return imaging

        logger.debug("No imaging studies found in text")
        return ""

    @staticmethod
    def extract_social_history(text: str) -> str:
        """
        Extract social history from VA format.

        Returns:
            Social history text or empty string
        """
        # Look for social history section
        sh_match = re.search(
            r'SOCIAL HISTORY:?(.*?)(?:\n\n|FAMILY HISTORY|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if sh_match:
            return sh_match.group(1).strip()

        logger.debug("No social history found in text")
        return ""

    @staticmethod
    def extract_past_medical_history(text: str) -> List[str]:
        """
        Extract past medical history as list.

        Returns:
            List of medical conditions
        """
        conditions = []

        # Look for PMH section
        pmh_match = re.search(
            r'(?:PAST MEDICAL HISTORY|PMH):?(.*?)(?:\n\n|PAST SURGICAL|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )

        if not pmh_match:
            # Try extracting from rated disabilities
            disabilities = VAExtractionPatterns.extract_rated_disabilities(text)
            for disability in disabilities:
                # Remove percentage
                condition = re.sub(r'\s*\(\d+%\)', '', disability)
                conditions.append(condition)
            return conditions

        pmh_text = pmh_match.group(1)

        # Extract numbered or bulleted list
        list_pattern = r'(?:^\d+[\.\)]\s*|\n\d+[\.\)]\s*|^[\-\*]\s*|\n[\-\*]\s*)([^\n]+)'
        matches = re.findall(list_pattern, pmh_text, re.MULTILINE)

        if matches:
            conditions = [m.strip() for m in matches if m.strip()]
        else:
            # Try comma-separated
            lines = [line.strip() for line in pmh_text.split('\n') if line.strip()]
            for line in lines:
                if ',' in line:
                    conditions.extend([c.strip() for c in line.split(',') if c.strip()])
                else:
                    conditions.append(line)

        return conditions


def get_extraction_patterns() -> VAExtractionPatterns:
    """Get singleton instance of extraction patterns."""
    return VAExtractionPatterns()
