"""
Consult Request Extractor

Extracts metadata and patient information from VA CPRS consult requests.
Handles the structured header portion of consult documents.

Author: VAUCDA Development Team
Date: December 2025
"""

import re
from typing import Dict, Optional, Tuple


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

    # Consult metadata patterns
    ORDERING_PROVIDER_PATTERN = re.compile(
        r'(?:Requesting Provider|From Service):\s+([A-Z]+,[A-Z\s]+)',
        re.MULTILINE
    )

    PROVISIONAL_DIAGNOSIS_PATTERN = re.compile(
        r'Provisional Diagnosis:\s+(.+?)(?:\(ICD|$)',
        re.MULTILINE | re.DOTALL
    )

    REASON_FOR_CONSULT_PATTERN = re.compile(
        r'Reason for Consult Request:\s*\n(.+?)(?:\n\n|Inter-facility)',
        re.MULTILINE | re.DOTALL
    )

    CONSULT_SERVICE_PATTERN = re.compile(
        r'To Service:\s+(.+?)(?:\n|$)',
        re.MULTILINE
    )

    URGENCY_PATTERN = re.compile(
        r'Urgency:\s+(\w+)',
        re.MULTILINE
    )

    def __init__(self):
        """Initialize the ConsultRequestExtractor."""
        pass

    def extract_patient_demographics(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extract patient name, SSN, and age from consult request.

        Args:
            text: Full consult request text

        Returns:
            Dictionary with keys:
            - patient_name: Full name in "Last, First Middle" format
            - ssn: Full SSN (XXX-XX-XXXX)
            - ssn_last4: Last 4 digits of SSN
            - patient_name_formatted: Name in preferred format "FIRST MIDDLE Last"
            - age: Patient age as string
        """
        result = {
            'patient_name': None,
            'ssn': None,
            'ssn_last4': None,
            'patient_name_formatted': None,
            'age': None
        }

        # Try combined pattern first (most reliable)
        match = self.PATIENT_NAME_SSN_PATTERN.search(text)
        if match:
            name = match.group(1).strip()
            ssn = match.group(2).strip()

            result['patient_name'] = name
            result['ssn'] = ssn
            result['ssn_last4'] = ssn.split('-')[-1]
            result['patient_name_formatted'] = self._format_name(name)
        else:
            # Try separate patterns if combined didn't work
            name_match = self.PATIENT_NAME_ONLY_PATTERN.search(text)
            if name_match:
                name = name_match.group(1).strip()
                result['patient_name'] = name
                result['patient_name_formatted'] = self._format_name(name)

            # Look for SSN separately
            ssn_match = self.SSN_PATTERN.search(text)
            if ssn_match:
                ssn = ssn_match.group(1).strip()
                result['ssn'] = ssn
                result['ssn_last4'] = ssn.split('-')[-1]

        # Extract age (format: "Age: 74" or "Age:74")
        age_pattern = re.compile(r'Age:\s*(\d+)', re.IGNORECASE)
        age_match = age_pattern.search(text)
        if age_match:
            result['age'] = age_match.group(1).strip()

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
        Extract consult request metadata.

        Args:
            text: Full consult request text

        Returns:
            Dictionary with consult metadata:
            - ordering_provider: Requesting provider name
            - provisional_diagnosis: Chief complaint/diagnosis
            - reason_for_consult: Detailed reason text
            - service: Consulting service (e.g., "SURG GU OUTPATIENT")
            - urgency: Routine, Urgent, Stat
        """
        result = {}

        # Ordering provider
        match = self.ORDERING_PROVIDER_PATTERN.search(text)
        result['ordering_provider'] = match.group(1).strip() if match else None

        # Provisional diagnosis
        match = self.PROVISIONAL_DIAGNOSIS_PATTERN.search(text)
        result['provisional_diagnosis'] = match.group(1).strip() if match else None

        # Reason for consult
        match = self.REASON_FOR_CONSULT_PATTERN.search(text)
        result['reason_for_consult'] = match.group(1).strip() if match else None

        # Service
        match = self.CONSULT_SERVICE_PATTERN.search(text)
        result['service'] = match.group(1).strip() if match else None

        # Urgency
        match = self.URGENCY_PATTERN.search(text)
        result['urgency'] = match.group(1).strip() if match else None

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
            'Provisional Diagnosis:',
            'Requesting Provider:',
            'To Service:',
            'Urgency:',
            'CPRS RELEASED ORDER'
        ]

        # Require at least 3 indicators
        matches = sum(1 for indicator in indicators if indicator in text)
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
    Extract complete consult request data including CC and HPI.

    This is the main entry point called by note_builder.py.

    Args:
        text: Full consult request text

    Returns:
        Dictionary with:
        - CC: Chief complaint from provisional diagnosis/reason for consult
        - HPI: History of present illness (brief version from reason for consult)
        - patient_name: Patient name
        - ssn_last4: Last 4 of SSN
        - ordering_provider: Requesting provider
        - service: Consulting service
    """
    extractor = ConsultRequestExtractor()
    demographics = extractor.extract_patient_demographics(text)
    metadata = extractor.extract_consult_metadata(text)

    # Extract CC from provisional diagnosis
    cc = metadata.get('provisional_diagnosis', '')
    if not cc:
        cc = "Consult request"

    # Extract HPI from reason for consult
    hpi = metadata.get('reason_for_consult', '')
    if not hpi:
        hpi = ""

    return {
        'CC': cc,
        'HPI': hpi,
        'patient_name': demographics.get('patient_name_formatted', ''),
        'ssn': demographics.get('ssn', ''),
        'ssn_last4': demographics.get('ssn_last4', ''),
        'ordering_provider': metadata.get('ordering_provider', ''),
        'service': metadata.get('service', ''),
        'urgency': metadata.get('urgency', '')
    }
