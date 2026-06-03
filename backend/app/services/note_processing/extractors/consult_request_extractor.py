"""
Consult Request Extractor

Extracts metadata and patient information from VA CPRS consult requests.
Handles the structured header portion of consult documents.

Enhanced per instructions.txt to extract 9 required consult tags:
1. Current PC Provider
2. Current PC Team
3. To Service
4. Requesting Provider
5. Orderable Item
6. Provisional Diagnosis
7. Reason For Request
8. Reason for Consult Request

Author: VAUCDA Development Team
Date: December 2025
"""

import re
from typing import Dict, List, Optional, Tuple


class ConsultRequestExtractor:
    """Extracts data from VA CPRS consult request headers."""

    # VA CPRS patient name format: LAST,FIRST MIDDLE, SSN
    PATIENT_NAME_SSN_PATTERN = re.compile(
        r'([A-Z]+,[A-Z]+(?:\s+[A-Z])?),?\s+(\d{3}-\d{2}-\d{4})',
        re.MULTILINE
    )

    # Alternative format without SSN
    PATIENT_NAME_ONLY_PATTERN = re.compile(
        r'^\s*([A-Z]+,[A-Z]+(?:\s+[A-Z])?)\s*$',
        re.MULTILINE
    )

    # SSN separate extraction
    SSN_PATTERN = re.compile(r'(\d{3}-\d{2}-\d{4})')

    # ======================================================================
    # RELIABLE PATIENT NAME SOURCES (per user feedback)
    # ======================================================================

    # 1. AUTOMATED RESULTS LETTER: "Dear Veteran: PATIENT NAME"
    # Example: "Dear Veteran: GERARDO GONZALES"
    # IMPORTANT: Only capture the name on the SAME LINE - stop at newline
    # The next line often contains "Thank you for choosing..." which should NOT be captured
    AUTOMATED_RESULTS_LETTER_PATTERN = re.compile(
        r'Dear\s+Veteran:\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*?)(?=\s*$|\s*\n)',
        re.MULTILINE
    )

    # 2. TELEPHONE NOTE: Patient info line after "LOCAL TITLE:" with "TELEPHONE NOTE"
    # Format: LAST,FIRST MIDDLE   SSN   (with possible extra spaces)
    # Example: "DOE,JOHN ANTHONY   XXX-XX-XXXX"
    TELEPHONE_NOTE_NAME_PATTERN = re.compile(
        r'([A-Z]+,[A-Z]+(?:\s+[A-Z]+)*)\s+(\d{3}-\d{2}-\d{4})',
        re.MULTILINE
    )

    # TELEPHONE NOTE demographics line: "Age:  66   Sex:  MALE    Race:  BLACK OR AFRICAN AMERICAN"
    TELEPHONE_NOTE_DEMOGRAPHICS_PATTERN = re.compile(
        r'Age:\s*(\d+)\s+Sex:\s*(MALE|FEMALE)\s+Race:\s*([A-Z\s]+?)(?:\n|Allergies:)',
        re.IGNORECASE | re.MULTILINE
    )

    # 3. STANDARD FORM 515: Patient info in pathology/lab reports
    # Format: NAME                                  STANDARD FORM 515
    #         ID:XXX-XX-XXXX  SEX:M DOB:MM/DD/YYYY  AGE: NN
    # Example: "DOE,JOHN CARLOS                    STANDARD FORM 515"
    #          "ID:XXX-XX-XXXX  SEX:M DOB:01/01/1970  AGE: 55"
    STANDARD_FORM_515_NAME_PATTERN = re.compile(
        r'([A-Z]+,[A-Z]+(?:\s+[A-Z]+)*)\s+STANDARD\s+FORM\s+515',
        re.MULTILINE
    )

    STANDARD_FORM_515_ID_PATTERN = re.compile(
        r'ID:(\d{3}-\d{2}-\d{4})\s+SEX:([MF])\s+DOB:(\d{2}/\d{2}/\d{4})\s+AGE:\s*(\d+)',
        re.MULTILINE
    )

    # ======================================================================
    # ENHANCED CONSULT METADATA PATTERNS (per instructions.txt)
    # ======================================================================

    # 1. Current PC Provider - Primary Care provider
    CURRENT_PC_PROVIDER_PATTERN = re.compile(
        r'Current\s+PC\s+Provider:\s*(.+?)(?:\n|$)',
        re.MULTILINE | re.IGNORECASE
    )

    # 2. Current PC Team - Team the provider works on
    CURRENT_PC_TEAM_PATTERN = re.compile(
        r'Current\s+PC\s+Team:\s*(.+?)(?:\n|$)',
        re.MULTILINE | re.IGNORECASE
    )

    # 3. To Service - Destination service (e.g., SURG-GU)
    CONSULT_SERVICE_PATTERN = re.compile(
        r'To\s+Service:\s*(.+?)(?:\n|$)',
        re.MULTILINE | re.IGNORECASE
    )

    # 4. Requesting Provider (may differ from PC Provider, e.g., ER doctor)
    REQUESTING_PROVIDER_PATTERN = re.compile(
        r'Requesting\s+Provider:\s*(.+?)(?:\n|$)',
        re.MULTILINE | re.IGNORECASE
    )

    # Legacy pattern for backward compatibility
    ORDERING_PROVIDER_PATTERN = re.compile(
        r'(?:Requesting Provider|From Service):\s+([A-Z]+,[A-Z\s]+)',
        re.MULTILINE
    )

    # 5. Orderable Item - Specific consult type (e.g., SURG-GU-PSA OUTPATIENT)
    ORDERABLE_ITEM_PATTERN = re.compile(
        r'Orderable\s+Item:\s*(.+?)(?:\n|$)',
        re.MULTILINE | re.IGNORECASE
    )

    # 6. Provisional Diagnosis - Becomes the Chief Complaint
    PROVISIONAL_DIAGNOSIS_PATTERN = re.compile(
        r'Provisional\s+Diagnosis:\s*(.+?)(?:\(ICD|$)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    # 7. Reason For Request (different from Reason for Consult Request)
    REASON_FOR_REQUEST_PATTERN = re.compile(
        r'Reason\s+For\s+Request:\s*\n?(.+?)(?=\n\s*(?:Reason\s+for\s+Consult|Provisional|To\s+Service|Orderable|Current|Requesting|\n\n|$))',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    # 8. Reason for Consult Request (may contain more detail)
    REASON_FOR_CONSULT_PATTERN = re.compile(
        r'Reason\s+for\s+Consult\s+Request:\s*\n?(.+?)(?=\n\n|Inter-facility|$)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    URGENCY_PATTERN = re.compile(
        r'Urgency:\s+(\w+)',
        re.MULTILINE
    )

    def __init__(self):
        """Initialize the ConsultRequestExtractor."""
        pass

    def is_urology_consult(self, text: str) -> bool:
        """
        Determine if this is a urology consult request.

        Per instructions.txt: Urology consults appear as "SURG-GU" in the
        To Service, Orderable Item, or both. The identifier ALWAYS starts
        with "SURG-GU" (e.g., "SURG-GU-PSA OUTPATIENT", "SURG-GU-BPH OUTPATIENT").

        Args:
            text: Full consult request text

        Returns:
            True if this is a urology (SURG-GU) consult
        """
        # Extract To Service
        to_service_match = self.CONSULT_SERVICE_PATTERN.search(text)
        to_service = to_service_match.group(1).strip().upper() if to_service_match else ""

        # Extract Orderable Item
        orderable_match = self.ORDERABLE_ITEM_PATTERN.search(text)
        orderable_item = orderable_match.group(1).strip().upper() if orderable_match else ""

        # Check if either starts with SURG-GU (per instructions.txt)
        return to_service.startswith('SURG-GU') or orderable_item.startswith('SURG-GU')

    def get_providers_to_scan(self, text: str) -> List[str]:
        """
        Get list of provider names whose notes should be scanned for urologic content.

        Per instructions.txt: Scan notes from both the Requesting Provider and
        the Current PC Provider for mentions of urologic issues to combine with
        the HPI from the consult request.

        Args:
            text: Full consult request text

        Returns:
            List of provider names to search for in clinical notes
        """
        providers = []

        # Current PC Provider
        pc_provider_match = self.CURRENT_PC_PROVIDER_PATTERN.search(text)
        if pc_provider_match:
            provider = pc_provider_match.group(1).strip()
            if provider and provider not in providers:
                providers.append(provider)

        # Requesting Provider (may be different, e.g., ER doctor)
        requesting_match = self.REQUESTING_PROVIDER_PATTERN.search(text)
        if requesting_match:
            provider = requesting_match.group(1).strip()
            if provider and provider not in providers:
                providers.append(provider)

        return providers

    def extract_patient_demographics(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract patient name, SSN, age, sex, and race from clinical document.

        PRIORITY ORDER (per user feedback - use reliable sources first):
        1. AUTOMATED RESULTS LETTER: "Dear Veteran: PATIENT NAME"
        2. TELEPHONE NOTE: Patient info line with Name, SSN, Age, Sex, Race
        3. Structured header lines: "PATIENT,NAME is a XX year old MALE"
        4. Clinical HPI format: "XX yo male" or "XX-year-old"

        These sources are ALWAYS present and ALWAYS have the patient's name,
        unlike other patterns that might match provider names.

        Args:
            text: Full clinical document text

        Returns:
            Dictionary with keys:
            - patient_name: Full name in "Last, First Middle" format
            - ssn: Full SSN (XXX-XX-XXXX)
            - ssn_last4: Last 4 digits of SSN
            - patient_name_formatted: Name in preferred format "FIRST MIDDLE Last"
            - age: Patient age as string
            - sex: Patient sex (MALE/FEMALE)
            - race: Patient race
        """
        result = {
            'patient_name': None,
            'ssn': None,
            'ssn_last4': None,
            'patient_name_formatted': None,
            'age': None,
            'sex': None,
            'race': None
        }

        # ======================================================================
        # PRIORITY 1: AUTOMATED RESULTS LETTER (most reliable for patient name)
        # Format: "Dear Veteran: DONOVAN ANTHONY THOMPSON"
        # ======================================================================
        results_letter_match = self.AUTOMATED_RESULTS_LETTER_PATTERN.search(text)
        if results_letter_match:
            # Name in FIRST MIDDLE LAST format (already formatted nicely)
            name_from_letter = results_letter_match.group(1).strip()
            result['patient_name_formatted'] = name_from_letter
            # Store original name (will be in FIRST MIDDLE LAST format)
            result['patient_name'] = name_from_letter

        # ======================================================================
        # PRIORITY 2: TELEPHONE NOTE (reliable source with full demographics)
        # Format after "LOCAL TITLE:" + "TELEPHONE NOTE":
        #   Date line
        #   Empty line
        #   "DOE,JOHN ANTHONY   XXX-XX-XXXX"
        #   "Age:  66   Sex:  MALE    Race:  BLACK OR AFRICAN AMERICAN"
        # ======================================================================

        # Look for TELEPHONE NOTE sections
        telephone_note_sections = re.findall(
            r'LOCAL\s+TITLE:\s*[^\n]*TELEPHONE\s+NOTE[^\n]*\n.*?(?=LOCAL\s+TITLE:|Note\s+Text|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        for section in telephone_note_sections:
            # Extract name and SSN from the patient info line
            name_ssn_match = self.TELEPHONE_NOTE_NAME_PATTERN.search(section)
            if name_ssn_match:
                name_va_format = name_ssn_match.group(1).strip()  # LAST,FIRST MIDDLE
                ssn = name_ssn_match.group(2).strip()

                # Only use this if we haven't found a name yet OR to get SSN
                if not result['patient_name']:
                    result['patient_name'] = name_va_format
                    result['patient_name_formatted'] = self._format_name(name_va_format)

                if not result['ssn']:
                    result['ssn'] = ssn
                    result['ssn_last4'] = ssn.split('-')[-1]

            # Extract demographics (Age, Sex, Race)
            demo_match = self.TELEPHONE_NOTE_DEMOGRAPHICS_PATTERN.search(section)
            if demo_match:
                if not result['age']:
                    result['age'] = demo_match.group(1).strip()
                if not result['sex']:
                    result['sex'] = demo_match.group(2).strip().upper()
                if not result['race']:
                    result['race'] = demo_match.group(3).strip()

        # ======================================================================
        # PRIORITY 2.5: STANDARD FORM 515 (pathology/lab reports)
        # Format: NAME                                  STANDARD FORM 515
        #         ID:XXX-XX-XXXX  SEX:M DOB:MM/DD/YYYY  AGE: NN
        # Example: "DOE,JOHN CARLOS                    STANDARD FORM 515"
        #          "ID:XXX-XX-XXXX  SEX:M DOB:01/01/1970  AGE: 55"
        # ======================================================================
        if not result['patient_name']:
            sf515_name_match = self.STANDARD_FORM_515_NAME_PATTERN.search(text)
            if sf515_name_match:
                name_va_format = sf515_name_match.group(1).strip()  # LAST,FIRST MIDDLE
                result['patient_name'] = name_va_format
                result['patient_name_formatted'] = self._format_name(name_va_format)

        # Extract SSN, Sex, and Age from Standard Form 515 ID line
        sf515_id_match = self.STANDARD_FORM_515_ID_PATTERN.search(text)
        if sf515_id_match:
            if not result['ssn']:
                ssn = sf515_id_match.group(1).strip()
                result['ssn'] = ssn
                result['ssn_last4'] = ssn.split('-')[-1]
            if not result['sex']:
                sex_char = sf515_id_match.group(2).strip().upper()
                result['sex'] = 'MALE' if sex_char == 'M' else 'FEMALE'
            if not result['age']:
                result['age'] = sf515_id_match.group(4).strip()

        # ======================================================================
        # PRIORITY 3: Cross-validate names from both sources
        # If both sources found names, use AUTOMATED RESULTS LETTER name (cleaner)
        # but verify with TELEPHONE NOTE
        # ======================================================================
        if results_letter_match and result['patient_name']:
            # Both sources found - use the AUTOMATED RESULTS LETTER format
            # (it's already in "FIRST MIDDLE LAST" format which is cleaner)
            result['patient_name_formatted'] = results_letter_match.group(1).strip()

        # ======================================================================
        # FALLBACK: Legacy patterns (only if no name found from reliable sources)
        # WARNING: These patterns may match provider names, so only use as fallback
        # ======================================================================
        if not result['patient_name']:
            # Try combined pattern (LAST,FIRST SSN)
            match = self.PATIENT_NAME_SSN_PATTERN.search(text)
            if match:
                # Validate this isn't a provider name by checking context
                # Providers appear after "Provider:", "AUTHOR:", "Requesting Provider:", etc.
                match_pos = match.start()
                preceding_text = text[max(0, match_pos - 50):match_pos].lower()

                # Skip if this is a provider reference
                provider_indicators = ['provider:', 'author:', 'cosigner:', 'signed by', 'dictated by']
                is_provider = any(indicator in preceding_text for indicator in provider_indicators)

                if not is_provider:
                    name = match.group(1).strip()
                    ssn = match.group(2).strip()

                    result['patient_name'] = name
                    result['ssn'] = ssn
                    result['ssn_last4'] = ssn.split('-')[-1]
                    result['patient_name_formatted'] = self._format_name(name)

        # ======================================================================
        # ENHANCED AGE EXTRACTION - Multiple patterns with validation
        # Priority order: structured header > Age: format > clinical format
        # ======================================================================
        if not result['age']:
            # Collect all age candidates with their context for validation
            age_candidates = []

            # Pattern 1: "PATIENT,NAME is a XX year old MALE/FEMALE" or "is a XX WHITE MALE"
            # This is the most reliable as it's in a structured header line
            structured_age_pattern = re.compile(
                r'[A-Z]+,[A-Z]+(?:\s+[A-Z])?\s+is\s+a\s+(\d+)\s+(?:year\s+old\s+)?(?:WHITE|BLACK|ASIAN|HISPANIC|[A-Z]+\s+)?(?:MALE|FEMALE)',
                re.IGNORECASE
            )
            for match in structured_age_pattern.finditer(text):
                age_val = int(match.group(1))
                # Validate age is reasonable (18-110 for veterans)
                if 18 <= age_val <= 110:
                    age_candidates.append((age_val, 'structured', match.start()))

            # Pattern 2: "Age: XX" format (from demographics sections)
            age_colon_pattern = re.compile(r'Age:\s*(\d+)', re.IGNORECASE)
            for match in age_colon_pattern.finditer(text):
                age_val = int(match.group(1))
                if 18 <= age_val <= 110:
                    age_candidates.append((age_val, 'age_colon', match.start()))

            # Pattern 3: "XX yo male/female" clinical format
            yo_pattern = re.compile(r'(\d+)\s*yo\s+(?:male|female|m|f|vet)', re.IGNORECASE)
            for match in yo_pattern.finditer(text):
                age_val = int(match.group(1))
                if 18 <= age_val <= 110:
                    age_candidates.append((age_val, 'yo_format', match.start()))

            # Pattern 4: "XX-year-old" clinical format
            year_old_pattern = re.compile(r'(\d+)[-\s]?year[-\s]?old', re.IGNORECASE)
            for match in year_old_pattern.finditer(text):
                age_val = int(match.group(1))
                if 18 <= age_val <= 110:
                    age_candidates.append((age_val, 'year_old', match.start()))

            # Select the most common age (mode) as multiple notes should agree
            if age_candidates:
                from collections import Counter
                age_values = [age for age, pattern_type, pos in age_candidates]
                age_counts = Counter(age_values)
                # Use the most common age value
                most_common_age = age_counts.most_common(1)[0][0]
                result['age'] = str(most_common_age)

        # ======================================================================
        # Extract sex if not already found
        # ======================================================================
        if not result['sex']:
            # Look for sex in structured header lines
            sex_pattern = re.compile(r'Sex:\s*(MALE|FEMALE)', re.IGNORECASE)
            sex_match = sex_pattern.search(text)
            if sex_match:
                result['sex'] = sex_match.group(1).strip().upper()
            else:
                # Try from structured name line
                if re.search(r'is\s+a\s+\d+\s+(?:\w+\s+)?MALE\b', text, re.IGNORECASE):
                    result['sex'] = 'MALE'
                elif re.search(r'is\s+a\s+\d+\s+(?:\w+\s+)?FEMALE\b', text, re.IGNORECASE):
                    result['sex'] = 'FEMALE'

        # ======================================================================
        # Extract race if not already found
        # ======================================================================
        if not result['race']:
            race_pattern = re.compile(r'Race:\s*([A-Z][A-Z\s]+?)(?:\n|Allergies:|Weight:|$)', re.IGNORECASE)
            race_match = race_pattern.search(text)
            if race_match:
                result['race'] = race_match.group(1).strip()
            else:
                # Try from structured name line: "is a 53 WHITE MALE"
                structured_race = re.search(
                    r'is\s+a\s+\d+\s+(WHITE|BLACK|ASIAN|HISPANIC|AFRICAN\s+AMERICAN|NATIVE\s+AMERICAN)\s+(?:MALE|FEMALE)',
                    text,
                    re.IGNORECASE
                )
                if structured_race:
                    result['race'] = structured_race.group(1).strip().upper()

        return result

    def _format_name(self, va_name: str) -> str:
        """
        Convert VA format name to preferred format.

        Args:
            va_name: Name in "LAST,FIRST MIDDLE" format

        Returns:
            Name in "FIRST MIDDLE Last" format (title case last name)
        """
        if ',' not in va_name:
            return va_name

        parts = va_name.split(',')
        if len(parts) != 2:
            return va_name

        last_name = parts[0].strip()
        first_middle = parts[1].strip()

        # Title case the last name, keep first/middle as is
        last_name_formatted = last_name.capitalize()

        return f"{first_middle} {last_name_formatted}"

    def extract_consult_metadata(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract all 9 consult request metadata fields per instructions.txt.

        Args:
            text: Full consult request text

        Returns:
            Dictionary with all consult metadata fields:
            - current_pc_provider: Primary Care provider
            - current_pc_team: PC team name
            - to_service: Destination service (e.g., "SURG-GU")
            - requesting_provider: Provider who ordered consult
            - orderable_item: Specific consult type
            - provisional_diagnosis: Chief complaint/diagnosis (becomes CC)
            - reason_for_request: Brief reason text
            - reason_for_consult: Detailed reason text (becomes HPI)
            - urgency: Routine, Urgent, Stat
            - ordering_provider: Legacy field (same as requesting_provider)
            - service: Legacy field (same as to_service)
            - is_urology_consult: Boolean if SURG-GU consult
        """
        result = {}

        # 1. Current PC Provider
        match = self.CURRENT_PC_PROVIDER_PATTERN.search(text)
        result['current_pc_provider'] = match.group(1).strip() if match else None

        # 2. Current PC Team
        match = self.CURRENT_PC_TEAM_PATTERN.search(text)
        result['current_pc_team'] = match.group(1).strip() if match else None

        # 3. To Service
        match = self.CONSULT_SERVICE_PATTERN.search(text)
        result['to_service'] = match.group(1).strip() if match else None
        result['service'] = result['to_service']  # Legacy compatibility

        # 4. Requesting Provider
        match = self.REQUESTING_PROVIDER_PATTERN.search(text)
        result['requesting_provider'] = match.group(1).strip() if match else None

        # Legacy ordering_provider - fall back to old pattern if new one doesn't match
        if not result['requesting_provider']:
            match = self.ORDERING_PROVIDER_PATTERN.search(text)
            result['requesting_provider'] = match.group(1).strip() if match else None
        result['ordering_provider'] = result['requesting_provider']  # Legacy compatibility

        # 5. Orderable Item
        match = self.ORDERABLE_ITEM_PATTERN.search(text)
        result['orderable_item'] = match.group(1).strip() if match else None

        # 6. Provisional Diagnosis (becomes CC per instructions.txt)
        match = self.PROVISIONAL_DIAGNOSIS_PATTERN.search(text)
        result['provisional_diagnosis'] = match.group(1).strip() if match else None

        # 7. Reason For Request
        match = self.REASON_FOR_REQUEST_PATTERN.search(text)
        result['reason_for_request'] = match.group(1).strip() if match else None

        # 8. Reason for Consult Request (becomes initial HPI per instructions.txt)
        match = self.REASON_FOR_CONSULT_PATTERN.search(text)
        result['reason_for_consult'] = match.group(1).strip() if match else None

        # 9. Urgency
        match = self.URGENCY_PATTERN.search(text)
        result['urgency'] = match.group(1).strip() if match else None

        # Flag for urology consult detection
        result['is_urology_consult'] = self.is_urology_consult(text)

        return result

    def is_consult_request(self, text: str) -> bool:
        """
        Determine if the input text is a VA consult request.

        Args:
            text: Input text to classify

        Returns:
            True if text appears to be a consult request
        """
        indicators = [
            'Reason for Consult Request:',
            'Reason For Request:',
            'Provisional Diagnosis:',
            'Requesting Provider:',
            'Current PC Provider:',
            'Current PC Team:',
            'To Service:',
            'Orderable Item:',
            'Urgency:',
            'CPRS RELEASED ORDER'
        ]

        # Require at least 3 indicators
        matches = sum(1 for indicator in indicators if indicator.lower() in text.lower())
        return matches >= 3

    def extract_consult_header_end_position(self, text: str) -> int:
        """
        Find where the consult request header ends and clinical notes begin.

        Args:
            text: Full consult request text

        Returns:
            Character position where header ends, or 0 if not found
        """
        # Common delimiters
        delimiters = [
            '==================================== END',
            'No local TIU results',
            'Provider Narrative',
            'Drug Name'
        ]

        for delimiter in delimiters:
            pos = text.find(delimiter)
            if pos != -1:
                return pos

        return 0

    def extract_all(self, text: str) -> Dict[str, any]:
        """
        Extract all consult request data.

        Args:
            text: Full consult request text

        Returns:
            Complete extraction results
        """
        demographics = self.extract_patient_demographics(text)
        metadata = self.extract_consult_metadata(text)

        return {
            'is_consult_request': self.is_consult_request(text),
            'demographics': demographics,
            'metadata': metadata,
            'header_end_position': self.extract_consult_header_end_position(text)
        }


# Convenience functions for backward compatibility
def extract_patient_demographics(text: str) -> Dict[str, Optional[str]]:
    """Extract patient demographics from consult request."""
    extractor = ConsultRequestExtractor()
    return extractor.extract_patient_demographics(text)


def extract_consult_metadata(text: str) -> Dict[str, Optional[str]]:
    """Extract consult metadata."""
    extractor = ConsultRequestExtractor()
    return extractor.extract_consult_metadata(text)


def is_consult_request(text: str) -> bool:
    """Check if text is a consult request."""
    extractor = ConsultRequestExtractor()
    return extractor.is_consult_request(text)


def extract_consult_request(text: str) -> Dict[str, any]:
    """
    Extract complete consult request data including all 9 tags, CC, and HPI.

    This is the main entry point called by note_builder.py.

    Per instructions.txt workflow:
    - CC (Chief Complaint) = Provisional Diagnosis
    - HPI = Synthesized from Reason for Request + Reason for Consult Request
    - Additional HPI content comes from provider note scanning (handled by note_builder)

    Args:
        text: Full consult request text

    Returns:
        Dictionary with all consult data:
        - CC: Chief complaint from provisional diagnosis
        - HPI: Initial HPI from reason for request/consult
        - is_urology_consult: Boolean if SURG-GU consult
        - current_pc_provider: Primary Care provider
        - current_pc_team: PC team name
        - to_service: Destination service
        - requesting_provider: Provider who ordered consult
        - orderable_item: Specific consult type
        - provisional_diagnosis: Original provisional diagnosis
        - reason_for_request: Brief reason text
        - reason_for_consult: Detailed reason text
        - providers_to_scan: List of providers for note scanning
        - patient_name: Patient name
        - ssn_last4: Last 4 of SSN
        - urgency: Routine, Urgent, Stat
        - Legacy fields: ordering_provider, service
    """
    extractor = ConsultRequestExtractor()
    demographics = extractor.extract_patient_demographics(text)
    metadata = extractor.extract_consult_metadata(text)

    # Per instructions.txt: CC = Provisional Diagnosis
    cc = metadata.get('provisional_diagnosis', '')
    if not cc:
        cc = "Consult request"

    # Per instructions.txt: HPI = Reason for Request + Reason for Consult Request
    # These are often sentence fragments that need synthesis
    reason_for_request = metadata.get('reason_for_request', '') or ''
    reason_for_consult = metadata.get('reason_for_consult', '') or ''

    # Combine both sources for initial HPI (will be further synthesized with provider notes)
    hpi_parts = []
    if reason_for_request.strip():
        hpi_parts.append(reason_for_request.strip())
    if reason_for_consult.strip():
        # Only add if different from reason_for_request
        if reason_for_consult.strip() != reason_for_request.strip():
            hpi_parts.append(reason_for_consult.strip())

    initial_hpi = ' '.join(hpi_parts) if hpi_parts else ""

    # Get providers to scan for additional HPI content
    providers_to_scan = extractor.get_providers_to_scan(text)

    return {
        # Primary fields
        'CC': cc,
        'HPI': initial_hpi,
        'is_urology_consult': metadata.get('is_urology_consult', False),

        # All 9 consult tags per instructions.txt
        'current_pc_provider': metadata.get('current_pc_provider', ''),
        'current_pc_team': metadata.get('current_pc_team', ''),
        'to_service': metadata.get('to_service', ''),
        'requesting_provider': metadata.get('requesting_provider', ''),
        'orderable_item': metadata.get('orderable_item', ''),
        'provisional_diagnosis': metadata.get('provisional_diagnosis', ''),
        'reason_for_request': reason_for_request,
        'reason_for_consult': reason_for_consult,

        # Provider note scanning
        'providers_to_scan': providers_to_scan,

        # Demographics
        'patient_name': demographics.get('patient_name_formatted', ''),
        'ssn': demographics.get('ssn', ''),
        'ssn_last4': demographics.get('ssn_last4', ''),
        'age': demographics.get('age', ''),
        'sex': demographics.get('sex', ''),
        'race': demographics.get('race', ''),

        # Urgency
        'urgency': metadata.get('urgency', ''),

        # Legacy compatibility
        'ordering_provider': metadata.get('ordering_provider', ''),
        'service': metadata.get('service', ''),
    }


def is_urology_consult(text: str) -> bool:
    """
    Check if text is a urology (SURG-GU) consult request.

    Per instructions.txt: SURG-GU always starts with "SURG-GU" in
    To Service or Orderable Item fields.
    """
    extractor = ConsultRequestExtractor()
    return extractor.is_urology_consult(text)


def get_providers_to_scan(text: str) -> List[str]:
    """Get list of provider names for note scanning."""
    extractor = ConsultRequestExtractor()
    return extractor.get_providers_to_scan(text)
