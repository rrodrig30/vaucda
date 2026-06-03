"""
Provider Note Scanner for Consult HPI Synthesis

Scans clinical notes from specified providers (Current PC Provider, Requesting Provider)
to extract urologic-related content that should be combined with consult request HPI.

Per instructions.txt:
"Once the initial HPI has been created (synthesis from the information in the consult request),
the Requesting physician's notes need to be reviewed to see if they have additional information
about the patient relating to his request. Hence the program needs to scan for any notes from
either the requesting physician or the Current PC Provider, to see if there is mention of their
urologic issues. If so, then that information must be combined with the HPI information from
the Consult Request, and then a new HPI synthesized."

Author: VAUCDA Development Team
Date: December 2025
"""

import re
from typing import Dict, List, Optional, Tuple


# Urologic keywords and conditions to scan for
UROLOGIC_KEYWORDS = [
    # Symptoms
    'hematuria', 'gross hematuria', 'microscopic hematuria',
    'dysuria', 'frequency', 'urgency', 'nocturia', 'hesitancy',
    'weak stream', 'urinary retention', 'incontinence',
    'flank pain', 'colicky pain', 'testicular pain',
    'erectile dysfunction', 'ed', 'impotence',

    # Conditions
    'prostate', 'psa', 'bph', 'benign prostatic',
    'prostate cancer', 'prostatitis',
    'kidney stone', 'renal stone', 'nephrolithiasis', 'urolithiasis',
    'hydronephrosis', 'hydroureter',
    'bladder cancer', 'bladder tumor', 'bladder mass',
    'renal mass', 'kidney mass', 'renal cell',
    'testicular mass', 'scrotal mass', 'varicocele', 'hydrocele',
    'uti', 'urinary tract infection', 'pyelonephritis',
    'hematospermia', 'blood in semen',
    'cryptorchidism', 'undescended testicle',
    'phimosis', 'paraphimosis',

    # Tests/Procedures
    'cystoscopy', 'ureteroscopy', 'lithotripsy',
    'turp', 'transurethral', 'prostatectomy',
    'nephrectomy', 'orchiectomy',
    'ct urogram', 'renal ultrasound', 'bladder ultrasound',
    'psa level', 'psa screening', 'psa velocity',
    'urinalysis', 'urine culture',

    # GU-specific
    'surg-gu', 'urology', 'urologist', 'gu consult',
    'genitourinary', 'voiding', 'ipss',
]

# Patterns for identifying notes by specific providers
PROVIDER_NOTE_PATTERNS = [
    # Pattern 1: "Signed by: PROVIDER,NAME"
    r'Signed\s+by:\s*([A-Z]+,\s*[A-Z][A-Za-z]+)',
    # Pattern 2: "PROVIDER,NAME MD" at note start
    r'^([A-Z]+,\s*[A-Z][A-Za-z]+)\s*(?:MD|DO|PA|NP|RN)',
    # Pattern 3: "Author: PROVIDER,NAME"
    r'AUTHOR:\s*([A-Z]+,\s*[A-Z][A-Za-z]+)',
    # Pattern 4: "Provider: PROVIDER,NAME"
    r'Provider:\s*([A-Z]+,\s*[A-Z][A-Za-z]+)',
    # Pattern 5: "Addendum by: PROVIDER,NAME"
    r'Addendum\s+by:\s*([A-Z]+,\s*[A-Z][A-Za-z]+)',
]


class ProviderNoteScanner:
    """
    Scans clinical notes for urologic content from specified providers.
    """

    def __init__(self):
        """Initialize the provider note scanner."""
        # Compile urologic keyword pattern (case-insensitive)
        self.urologic_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(kw) for kw in UROLOGIC_KEYWORDS) + r')\b',
            re.IGNORECASE
        )

    def scan_for_urologic_content(
        self,
        clinical_document: str,
        providers_to_scan: List[str]
    ) -> Dict[str, str]:
        """
        Scan clinical document for urologic content from specified providers.

        Args:
            clinical_document: Full clinical document (may contain multiple notes)
            providers_to_scan: List of provider names to search for

        Returns:
            Dictionary with:
            - urologic_content: Extracted urologic-related text
            - matched_providers: List of providers whose notes were found
            - keyword_matches: Keywords that were found
        """
        if not clinical_document or not providers_to_scan:
            return {
                'urologic_content': '',
                'matched_providers': [],
                'keyword_matches': []
            }

        # Normalize provider names for matching
        normalized_providers = self._normalize_provider_names(providers_to_scan)

        # Find all notes in the document
        notes = self._segment_notes(clinical_document)

        # Scan each note for provider match and urologic content
        urologic_content_parts = []
        matched_providers = set()
        all_keyword_matches = set()

        for note in notes:
            note_author = self._extract_note_author(note)
            if not note_author:
                continue

            # Check if this note is from one of our target providers
            if self._is_provider_match(note_author, normalized_providers):
                # Extract urologic content from this note
                urologic_text, keywords = self._extract_urologic_content(note)
                if urologic_text:
                    urologic_content_parts.append(urologic_text)
                    matched_providers.add(note_author)
                    all_keyword_matches.update(keywords)

        return {
            'urologic_content': '\n\n'.join(urologic_content_parts),
            'matched_providers': list(matched_providers),
            'keyword_matches': list(all_keyword_matches)
        }

    def _normalize_provider_names(self, providers: List[str]) -> List[str]:
        """
        Normalize provider names for flexible matching.

        Args:
            providers: List of provider names

        Returns:
            List of normalized names (uppercase, trimmed)
        """
        normalized = []
        for provider in providers:
            if provider:
                # Remove titles and normalize
                name = provider.strip().upper()
                # Remove common titles
                name = re.sub(r'\s*(?:MD|DO|PA|NP|RN|PHD|FACP|FACS)\s*$', '', name, flags=re.IGNORECASE)
                name = name.strip()
                if name:
                    normalized.append(name)
        return normalized

    def _segment_notes(self, clinical_document: str) -> List[str]:
        """
        Segment a clinical document into individual notes.

        VA documents often contain multiple notes separated by
        delimiters or date headers.

        Args:
            clinical_document: Full clinical document

        Returns:
            List of individual note texts
        """
        # Pattern for note separators
        separators = [
            r'={10,}',  # Long equals lines
            r'-{10,}',  # Long dash lines
            r'\n\s*LOCAL TITLE:',  # VA note header
            r'\n\s*DATE OF NOTE:',  # Date of note header
            r'\n\s*Signed\s+by:.*?\n\s*Signed:',  # Signature blocks
        ]

        # Try to split by separators
        separator_pattern = '|'.join(f'({sep})' for sep in separators)
        parts = re.split(separator_pattern, clinical_document, flags=re.MULTILINE)

        # Filter out None values and empty strings, recombine
        notes = []
        current_note = []

        for part in parts:
            if part is None or not part.strip():
                continue
            # If this is a separator, end current note and start new one
            if re.match(separator_pattern, part.strip(), re.MULTILINE):
                if current_note:
                    notes.append('\n'.join(current_note))
                    current_note = []
            else:
                current_note.append(part)

        # Add final note
        if current_note:
            notes.append('\n'.join(current_note))

        # If no segmentation occurred, return whole document as single note
        if not notes:
            notes = [clinical_document]

        return notes

    def _extract_note_author(self, note: str) -> Optional[str]:
        """
        Extract the author/provider name from a note.

        Args:
            note: Individual note text

        Returns:
            Provider name or None if not found
        """
        for pattern in PROVIDER_NOTE_PATTERNS:
            match = re.search(pattern, note, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip().upper()
        return None

    def _is_provider_match(self, note_author: str, target_providers: List[str]) -> bool:
        """
        Check if note author matches any target provider.

        Uses flexible matching to handle variations in name formatting.

        Args:
            note_author: Author name from note
            target_providers: Normalized list of target provider names

        Returns:
            True if match found
        """
        note_author_upper = note_author.upper().strip()

        for target in target_providers:
            # Exact match
            if note_author_upper == target:
                return True

            # Last name match (handle "SMITH,JOHN" vs "SMITH, JOHN")
            note_last = note_author_upper.split(',')[0].strip()
            target_last = target.split(',')[0].strip()
            if note_last == target_last:
                return True

            # Partial match - target contained in author
            if target in note_author_upper or note_author_upper in target:
                return True

        return False

    def _extract_urologic_content(self, note: str) -> Tuple[str, List[str]]:
        """
        Extract urologic-related content from a note.

        Extracts paragraphs/sentences containing urologic keywords.

        Args:
            note: Individual note text

        Returns:
            Tuple of (extracted_content, list_of_keywords_found)
        """
        # Find all keyword matches
        keyword_matches = list(set(
            match.group(1).lower()
            for match in self.urologic_pattern.finditer(note)
        ))

        if not keyword_matches:
            return '', []

        # Extract sentences/paragraphs containing urologic content
        urologic_sentences = []

        # Split into paragraphs
        paragraphs = re.split(r'\n\s*\n', note)

        for para in paragraphs:
            if not para.strip():
                continue

            # Check if paragraph contains urologic keywords
            if self.urologic_pattern.search(para):
                # Clean the paragraph
                cleaned_para = self._clean_paragraph(para)
                if cleaned_para:
                    urologic_sentences.append(cleaned_para)

        # If no paragraph-level extraction, try sentence-level
        if not urologic_sentences:
            sentences = re.split(r'(?<=[.!?])\s+', note)
            for sentence in sentences:
                if self.urologic_pattern.search(sentence):
                    cleaned = sentence.strip()
                    if cleaned and len(cleaned) > 20:  # Skip very short fragments
                        urologic_sentences.append(cleaned)

        return '\n'.join(urologic_sentences), keyword_matches

    def _clean_paragraph(self, para: str) -> str:
        """
        Clean a paragraph of VA-specific formatting.

        Args:
            para: Paragraph text

        Returns:
            Cleaned paragraph
        """
        # Remove VA metadata
        cleaned = re.sub(r'Signed\s+by:.*', '', para, flags=re.IGNORECASE)
        cleaned = re.sub(r'AUTHOR:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'DATE OF NOTE:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'LOCAL TITLE:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}', '', cleaned)

        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()

        return cleaned


def scan_provider_notes_for_urologic_content(
    clinical_document: str,
    providers_to_scan: List[str]
) -> str:
    """
    Convenience function to scan clinical document for urologic content.

    Args:
        clinical_document: Full clinical document
        providers_to_scan: List of provider names (from consult request)

    Returns:
        Extracted urologic content text (or empty string if none found)
    """
    scanner = ProviderNoteScanner()
    result = scanner.scan_for_urologic_content(clinical_document, providers_to_scan)
    return result.get('urologic_content', '')


def extract_provider_urologic_context(
    clinical_document: str,
    providers_to_scan: List[str]
) -> Dict[str, any]:
    """
    Extract full urologic context from provider notes.

    Args:
        clinical_document: Full clinical document
        providers_to_scan: List of provider names (from consult request)

    Returns:
        Dictionary with urologic_content, matched_providers, keyword_matches
    """
    scanner = ProviderNoteScanner()
    return scanner.scan_for_urologic_content(clinical_document, providers_to_scan)
