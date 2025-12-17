"""
Document Classifier

Identifies and segments different document types within a composite clinical document.
Particularly important for consult requests which often contain multiple embedded notes.

Author: VAUCDA Development Team
Date: December 2025
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DocumentSegment:
    """Represents a segment of a document identified by the classifier."""
    doc_type: str
    content: str
    start_pos: int
    end_pos: int
    metadata: Dict[str, any]


class DocumentClassifier:
    """
    Classifies and segments clinical documents into constituent parts.

    Handles:
    - Consult request headers
    - Primary care notes (embedded in consults)
    - GU clinic notes
    - Emergency department notes
    - Radiology reports
    - Lab results
    - Medication lists
    - Problem lists
    """

    # Document type markers
    CONSULT_REQUEST_MARKERS = [
        'Reason for Consult Request:',
        'Provisional Diagnosis:',
        'Requesting Provider:',
        'To Service:',
        'CPRS RELEASED ORDER'
    ]

    PRIMARY_CARE_MARKERS = [
        'PRIMARY CARE',
        'ANNUAL NOTE',
        'ANNUAL EXAM',
        'NCFC PHYSICIAN NOTE'
    ]

    ED_MARKERS = [
        'ED PROVIDER NOTE',
        'EMERGENCY DEPT',
        'PHYSICIAN EMERGENCY DEPT NOTE'
    ]

    GU_CLINIC_MARKERS = [
        'SURG GU',
        'UROLOGY CLINIC',
        'GU OUTPATIENT',
        'UROLOGY NOTE'
    ]

    RADIOLOGY_MARKERS = [
        'IMPRESSION:',
        'CT CHEST',
        'CT ABD',
        'CT RENAL',
        'MRI ',
        'ULTRASOUND',
        'X-RAY',
        'RADIOGRAPH'
    ]

    def __init__(self):
        """Initialize the document classifier."""
        pass

    def classify_document(self, text: str) -> Dict[str, any]:
        """
        Classify a clinical document and identify its constituent parts.

        Args:
            text: Full document text

        Returns:
            Dictionary with:
            - document_type: Primary document type
            - segments: List of DocumentSegment objects
            - is_composite: Whether document contains multiple embedded notes
        """
        segments = []

        # Identify consult request header
        consult_segment = self._identify_consult_request(text)
        if consult_segment:
            segments.append(consult_segment)

        # Identify embedded primary care notes
        pcp_segments = self._identify_primary_care_notes(text)
        segments.extend(pcp_segments)

        # Identify emergency department notes
        ed_segments = self._identify_ed_notes(text)
        segments.extend(ed_segments)

        # Identify GU clinic notes
        gu_segments = self._identify_gu_notes(text)
        segments.extend(gu_segments)

        # Identify radiology reports
        rad_segments = self._identify_radiology_reports(text)
        segments.extend(rad_segments)

        # Identify lab results sections
        lab_segments = self._identify_lab_results(text)
        segments.extend(lab_segments)

        # Determine primary document type
        if consult_segment:
            doc_type = "CONSULT_REQUEST"
        elif pcp_segments:
            doc_type = "PRIMARY_CARE_NOTE"
        elif gu_segments:
            doc_type = "GU_CLINIC_NOTE"
        elif ed_segments:
            doc_type = "ED_NOTE"
        else:
            doc_type = "UNKNOWN"

        return {
            'document_type': doc_type,
            'segments': segments,
            'is_composite': len(segments) > 1
        }

    def _identify_consult_request(self, text: str) -> Optional[DocumentSegment]:
        """Identify VA consult request header."""
        # Look for consult request markers
        marker_count = sum(1 for marker in self.CONSULT_REQUEST_MARKERS if marker in text)

        if marker_count >= 3:
            # Find the end of consult request header
            end_markers = [
                '==================================== END',
                'No local TIU results',
                'Drug Name',
                'Provider Narrative'
            ]

            end_pos = len(text)
            for marker in end_markers:
                pos = text.find(marker)
                if pos != -1 and pos < end_pos:
                    end_pos = pos

            return DocumentSegment(
                doc_type="CONSULT_REQUEST_HEADER",
                content=text[:end_pos],
                start_pos=0,
                end_pos=end_pos,
                metadata={'marker_count': marker_count}
            )

        return None

    def _identify_primary_care_notes(self, text: str) -> List[DocumentSegment]:
        """Identify embedded primary care notes."""
        segments = []

        # Pattern: Look for PRIMARY CARE note headers
        # Format: "LOCAL TITLE: NCFC PHYSICIAN NOTE" or "PRIMARY CARE NURSE NEW PATIENT/ANNUAL/FLWUP NOTE"
        pcp_pattern = r'(LOCAL TITLE:\s+(?:NCFC PHYSICIAN NOTE|PRIMARY CARE.*?NOTE).*?)(?=LOCAL TITLE:|Facility:|Note Text|={70,}|$)'

        for match in re.finditer(pcp_pattern, text, re.DOTALL | re.IGNORECASE):
            content = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Extract date if present
            date_match = re.search(r'DATE OF NOTE:\s+([A-Z]{3}\s+\d{1,2},\s+\d{4})', content)
            date = date_match.group(1) if date_match else None

            # Extract author if present
            author_match = re.search(r'AUTHOR:\s+([A-Z]+,[A-Z\s]+)', content)
            author = author_match.group(1) if author_match else None

            segments.append(DocumentSegment(
                doc_type="PRIMARY_CARE_NOTE",
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={'date': date, 'author': author}
            ))

        return segments

    def _identify_ed_notes(self, text: str) -> List[DocumentSegment]:
        """Identify emergency department notes."""
        segments = []

        # Pattern: ED PROVIDER NOTE
        ed_pattern = r'(LOCAL TITLE:\s+ED PROVIDER NOTE.*?)(?=LOCAL TITLE:|Facility:|={70,}|$)'

        for match in re.finditer(ed_pattern, text, re.DOTALL | re.IGNORECASE):
            content = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Extract chief complaint
            cc_match = re.search(r'CC:\s+([^\n]+)', content)
            cc = cc_match.group(1).strip() if cc_match else None

            segments.append(DocumentSegment(
                doc_type="ED_NOTE",
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={'chief_complaint': cc}
            ))

        return segments

    def _identify_gu_notes(self, text: str) -> List[DocumentSegment]:
        """Identify GU/Urology clinic notes."""
        segments = []

        # Pattern: Look for GU-related note titles (NOTE or CONSULT)
        gu_pattern = r'(LOCAL TITLE:.*?(?:SURG GU|UROLOGY|URO\s).*?(?:NOTE|CONSULT).*?)(?=LOCAL TITLE:|Facility:|={70,}|$)'

        for match in re.finditer(gu_pattern, text, re.DOTALL | re.IGNORECASE):
            content = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            segments.append(DocumentSegment(
                doc_type="GU_CLINIC_NOTE",
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={}
            ))

        return segments

    def _identify_radiology_reports(self, text: str) -> List[DocumentSegment]:
        """Identify radiology/imaging reports."""
        segments = []

        # Pattern 1: Detailed Report format
        detailed_report_pattern = r'(Detailed Report\s+.*?(?:CT|MRI|ULTRASOUND|X-RAY).*?)(?=Detailed Report|Facility:|Performing Lab|={30,}|$)'

        for match in re.finditer(detailed_report_pattern, text, re.DOTALL | re.IGNORECASE):
            content = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Extract exam date
            date_match = re.search(r'Exm Date:\s*([A-Z]{3}\s+\d{1,2},\s+\d{4})', content)
            date = date_match.group(1) if date_match else None

            # Extract study name
            study_lines = content.split('\n')
            study_name = "Imaging Study"
            for line in study_lines[:5]:
                if re.search(r'(?:CT|MRI|ULTRASOUND|X-RAY)', line, re.IGNORECASE):
                    if not re.search(r'(?:Exm Date:|Req Phys:)', line, re.IGNORECASE):
                        study_name = line.strip()
                        break

            segments.append(DocumentSegment(
                doc_type="RADIOLOGY_REPORT",
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={'date': date, 'study_name': study_name}
            ))

        return segments

    def _identify_lab_results(self, text: str) -> List[DocumentSegment]:
        """Identify laboratory results sections."""
        segments = []

        # Pattern: VA lab format with specimen collection dates
        lab_pattern = r'(Specimen:\s+(?:SERUM|BLOOD|URINE|PLASMA).*?Specimen Collection Date:.*?)(?=Specimen:|Performing Lab Sites|Facility:|={70,}|$)'

        for match in re.finditer(lab_pattern, text, re.DOTALL | re.IGNORECASE):
            content = match.group(1)
            start_pos = match.start()
            end_pos = match.end()

            # Extract collection date
            date_match = re.search(r'Specimen Collection Date:\s+([A-Z]{3}\s+\d{1,2},\s+\d{4})', content)
            date = date_match.group(1) if date_match else None

            # Extract specimen type
            spec_match = re.search(r'Specimen:\s+([A-Z]+)', content)
            specimen_type = spec_match.group(1) if spec_match else None

            segments.append(DocumentSegment(
                doc_type="LAB_RESULTS",
                content=content,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={'date': date, 'specimen_type': specimen_type}
            ))

        return segments

    def extract_document_segment(self, text: str, doc_type: str) -> str:
        """
        Extract all content for a specific document type.

        Args:
            text: Full document text
            doc_type: Type of document to extract

        Returns:
            Combined content of all matching segments
        """
        classification = self.classify_document(text)
        matching_segments = [seg for seg in classification['segments'] if seg.doc_type == doc_type]

        if not matching_segments:
            return ""

        # Combine content from all matching segments
        combined_content = '\n\n'.join(seg.content for seg in matching_segments)
        return combined_content


# Convenience functions
def classify_document(text: str) -> Dict[str, any]:
    """Classify a clinical document."""
    classifier = DocumentClassifier()
    return classifier.classify_document(text)


def extract_document_type(text: str, doc_type: str) -> str:
    """Extract all content for a specific document type."""
    classifier = DocumentClassifier()
    return classifier.extract_document_segment(text, doc_type)
