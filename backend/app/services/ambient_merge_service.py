"""
Ambient Listening Intelligent Merge Service

Performs section-aware parsing of clinical transcriptions and intelligently
merges new information into existing clinical notes.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """Represents a segment of transcription mapped to a clinical section."""
    section: str  # e.g., "HPI", "IPSS", "PSH", "PHYSICAL_EXAM", "ASSESSMENT", "PLAN"
    content: str
    confidence: float
    speaker: Optional[str] = None


class SectionAwareTranscriptionParser:
    """Parses transcription and identifies which clinical sections it relates to."""

    # Keywords that map to clinical note sections
    SECTION_KEYWORDS = {
        'HPI': [
            'history', 'presented with', 'complains of', 'started', 'began',
            'symptoms', 'reports', 'describes', 'experiencing', 'noticed'
        ],
        'IPSS': [
            'urinary symptoms', 'frequency', 'urgency', 'hesitancy', 'nocturia',
            'weak stream', 'incomplete emptying', 'straining', 'voiding'
        ],
        'SEXUAL_HISTORY': [
            'erectile', 'ED', 'sexual function', 'libido', 'viagra', 'cialis',
            'sildenafil', 'tadalafil', 'erection', 'intercourse', 'intimacy'
        ],
        'PSH': [
            'surgery', 'operation', 'procedure', 'had a', 'underwent',
            'prostatectomy', 'nephrectomy', 'cystectomy', 'TURP'
        ],
        'MEDICATIONS': [
            'taking', 'medication', 'prescribed', 'started on', 'dose',
            'mg', 'twice daily', 'once daily', 'stopped', 'discontinued'
        ],
        'PHYSICAL_EXAM': [
            'exam', 'examination', 'feels like', 'palpate', 'prostate',
            'tender', 'mass', 'enlarged', 'smooth', 'firm', 'nodule'
        ],
        'LABS': [
            'PSA', 'testosterone', 'creatinine', 'hemoglobin', 'lab results',
            'blood work', 'urine test'
        ],
        'ASSESSMENT': [
            'impression', 'diagnosis', 'concern', 'worried about', 'likely',
            'consistent with', 'suggests'
        ],
        'PLAN': [
            'plan', 'will', 'going to', 'schedule', 'order', 'refer',
            'follow up', 'continue', 'start', 'increase', 'decrease'
        ]
    }

    def parse(self, transcription: str, speaker_map: Optional[Dict[str, str]] = None) -> List[TranscriptionSegment]:
        """
        Parse transcription and map segments to clinical sections.

        Args:
            transcription: Full transcription text
            speaker_map: Optional mapping of speaker IDs to labels (Clinician, Patient, etc.)

        Returns:
            List of TranscriptionSegment objects
        """
        segments = []

        # Split transcription into sentences
        sentences = re.split(r'[.!?]+', transcription)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Identify which section this sentence relates to
            section, confidence = self._identify_section(sentence)

            if section:
                segments.append(TranscriptionSegment(
                    section=section,
                    content=sentence,
                    confidence=confidence
                ))

        return segments

    def _identify_section(self, text: str) -> Tuple[Optional[str], float]:
        """Identify which clinical section a piece of text relates to."""
        text_lower = text.lower()

        section_scores = {}

        for section, keywords in self.SECTION_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                section_scores[section] = score

        if not section_scores:
            return None, 0.0

        # Get section with highest score
        best_section = max(section_scores, key=section_scores.get)
        total_keywords = len(self.SECTION_KEYWORDS[best_section])
        confidence = min(section_scores[best_section] / total_keywords, 1.0)

        return best_section, confidence


class IntelligentNoteMerger:
    """Intelligently merges transcription segments into existing clinical note."""

    def __init__(self):
        self.parser = SectionAwareTranscriptionParser()

    def merge(self, existing_note: str, transcription: str,
              speaker_map: Optional[Dict[str, str]] = None) -> str:
        """
        Merge transcription into existing note with section-aware intelligence.

        Args:
            existing_note: The current Stage 2 note
            transcription: New transcription from ambient listening
            speaker_map: Optional speaker identification

        Returns:
            Updated note with merged information
        """
        # Parse transcription into segments
        segments = self.parser.parse(transcription, speaker_map)

        if not segments:
            logger.warning("No segments identified in transcription")
            return existing_note

        # Start with the original note
        merged_note = existing_note

        # Group segments by section for batch updates
        section_updates = {}
        for segment in segments:
            if segment.section not in section_updates:
                section_updates[segment.section] = []
            section_updates[segment.section].append(segment.content)

        # Apply updates to each section in-place
        for section_name, updates in section_updates.items():
            merged_note = self._merge_section_in_place(
                merged_note, section_name, updates
            )

        return merged_note

    def _merge_section_in_place(self, note: str, section_name: str,
                                updates: List[str]) -> str:
        """
        Merge updates into a specific section within the note without
        extracting all sections (preserves entire note structure).
        """
        # Map section names to regex patterns
        section_patterns = {
            'HPI': (r'(HPI:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'HPI:'),
            'IPSS': (r'(IPSS:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'IPSS:'),
            'SEXUAL_HISTORY': (r'(SEXUAL HISTORY:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'SEXUAL HISTORY:'),
            'PSH': (r'(PAST SURGICAL HISTORY:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'PAST SURGICAL HISTORY:'),
            'MEDICATIONS': (r'(MEDICATIONS:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'MEDICATIONS:'),
            'PHYSICAL_EXAM': (r'(PHYSICAL EXAM:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'PHYSICAL EXAM:'),
            'LABS': (r'(LABS:.*?)(?=\n[A-Z]+ ?[A-Z]*:|\Z)', 'LABS:'),
            'ASSESSMENT': (r'(ASSESSMENT:.*?)(?=\nPLAN:|\Z)', 'ASSESSMENT:'),
            'PLAN': (r'(PLAN:.*?)(?=\nElectronically signed|\Z)', 'PLAN:'),
        }

        if section_name not in section_patterns:
            logger.warning(f"Unknown section for in-place merge: {section_name}")
            return note

        pattern, header = section_patterns[section_name]
        match = re.search(pattern, note, re.DOTALL | re.MULTILINE)

        if not match:
            logger.warning(f"Section {section_name} not found in note")
            return note

        # Get existing section content
        existing_content = match.group(1).strip()

        # Merge all updates for this section
        merged_content = existing_content
        for update in updates:
            merged_content = self._merge_segment(
                section_name=section_name,
                existing_content=merged_content,
                new_content=update
            )

        # Replace the section in the original note
        updated_note = note[:match.start()] + merged_content + note[match.end():]

        return updated_note

    def _extract_note_sections(self, note: str) -> Dict[str, str]:
        """Extract sections from existing clinical note."""
        sections = {}

        # Common section headers in urology notes
        section_patterns = [
            (r'(?:^|\n)(HPI:.*?)(?=\n[A-Z]+:|$)', 'HPI'),
            (r'(?:^|\n)(IPSS:.*?)(?=\n[A-Z]+:|$)', 'IPSS'),
            (r'(?:^|\n)(SEXUAL HISTORY:.*?)(?=\n[A-Z]+:|$)', 'SEXUAL_HISTORY'),
            (r'(?:^|\n)(PAST SURGICAL HISTORY:.*?)(?=\n[A-Z]+:|$)', 'PSH'),
            (r'(?:^|\n)(MEDICATIONS:.*?)(?=\n[A-Z]+:|$)', 'MEDICATIONS'),
            (r'(?:^|\n)(PHYSICAL EXAM:.*?)(?=\n[A-Z]+:|$)', 'PHYSICAL_EXAM'),
            (r'(?:^|\n)(LABS:.*?)(?=\n[A-Z]+:|$)', 'LABS'),
            (r'(?:^|\n)(ASSESSMENT:.*?)(?=\n(?:PLAN:|Electronically signed)|$)', 'ASSESSMENT'),
            (r'(?:^|\n)(PLAN:.*?)(?=\nElectronically signed|$)', 'PLAN'),
        ]

        for pattern, section_name in section_patterns:
            match = re.search(pattern, note, re.DOTALL | re.MULTILINE)
            if match:
                sections[section_name] = match.group(1).strip()

        return sections

    def _merge_segment(self, section_name: str, existing_content: str,
                      new_content: str) -> str:
        """Merge new content into a specific section."""

        if section_name == 'HPI':
            return self._merge_hpi(existing_content, new_content)
        elif section_name == 'IPSS':
            return self._merge_ipss(existing_content, new_content)
        elif section_name == 'SEXUAL_HISTORY':
            return self._merge_sexual_history(existing_content, new_content)
        elif section_name == 'PSH':
            return self._merge_psh(existing_content, new_content)
        elif section_name == 'MEDICATIONS':
            return self._merge_medications(existing_content, new_content)
        elif section_name == 'PHYSICAL_EXAM':
            return self._merge_physical_exam(existing_content, new_content)
        elif section_name == 'LABS':
            return self._merge_labs(existing_content, new_content)
        elif section_name == 'ASSESSMENT':
            return self._merge_assessment(existing_content, new_content)
        elif section_name == 'PLAN':
            return self._merge_plan(existing_content, new_content)
        else:
            # Default: append new content
            return f"{existing_content}\n\nDiscussion Update: {new_content}"

    def _merge_hpi(self, existing: str, new: str) -> str:
        """Merge new HPI information."""
        # Add as discussion update to HPI
        return f"{existing}\n\nDiscussion Update: {new}"

    def _merge_ipss(self, existing: str, new: str) -> str:
        """Merge IPSS updates from discussion."""
        # For now, add as note below IPSS table
        return f"{existing}\n\nDiscussion: {new}"

    def _merge_sexual_history(self, existing: str, new: str) -> str:
        """Merge sexual history updates (e.g., medication effectiveness)."""
        # Append as update
        return f"{existing}\n\nToday's Discussion: {new}"

    def _merge_psh(self, existing: str, new: str) -> str:
        """Merge new surgical history."""
        # Check if it's truly new information
        if new.lower() not in existing.lower():
            return f"{existing}\n- {new} (reported today)"
        return existing

    def _merge_medications(self, existing: str, new: str) -> str:
        """Merge medication updates."""
        return f"{existing}\n\nMedication Discussion: {new}"

    def _merge_physical_exam(self, existing: str, new: str) -> str:
        """Merge physical exam findings from discussion."""
        # Look for specific exam components - but exclude planning/discussion statements
        if 'prostate' in new.lower() and 'examination' in new.lower():
            # This is actual prostate exam findings (not just mentions of prostate)
            # Try to find and replace PROSTATE subsection
            prostate_pattern = r'PROSTATE:.*?(?=\nCNS:)'
            match = re.search(prostate_pattern, existing, re.DOTALL)

            if match:
                # Replace the entire PROSTATE subsection content
                replacement = f'PROSTATE: {new}'
                existing = existing[:match.start()] + replacement + existing[match.end():]
            else:
                # If PROSTATE: subsection doesn't exist, add it before CNS
                cns_pattern = r'(\nCNS:)'
                if re.search(cns_pattern, existing):
                    existing = re.sub(cns_pattern, f'\nPROSTATE: {new}\\1', existing)
                else:
                    # Add at end of physical exam section
                    existing = f"{existing}\nPROSTATE: {new}"
        elif 'prostate' in new.lower():
            # Mentions prostate but is not exam findings (planning/discussion)
            # Don't add to physical exam - let it go to appropriate section
            pass
        else:
            existing = f"{existing}\n\nAdditional Exam Findings: {new}"

        return existing

    def _merge_labs(self, existing: str, new: str) -> str:
        """Merge lab discussions."""
        return f"{existing}\n\nLab Discussion: {new}"

    def _merge_assessment(self, existing: str, new: str) -> str:
        """Merge assessment updates from discussion."""
        return f"{existing}\n\nClinical Discussion: {new}"

    def _merge_plan(self, existing: str, new: str) -> str:
        """Merge plan updates from discussion."""
        # Add as additional plan item
        return f"{existing}\n\n- Additional: {new}"

    def _reconstruct_note(self, sections: Dict[str, str]) -> str:
        """Reconstruct full note from merged sections."""
        # Order sections appropriately
        section_order = [
            'CC', 'HPI', 'IPSS', 'DIETARY HISTORY', 'SOCIAL HISTORY',
            'FAMILY HISTORY', 'SEXUAL_HISTORY', 'PMH', 'PSH', 'PSA CURVE',
            'PATHOLOGY RESULTS', 'MEDICATIONS', 'ALLERGIES', 'ENDOCRINE LABS',
            'LABS', 'IMAGING', 'GENERAL ROS', 'PHYSICAL_EXAM',
            'ASSESSMENT', 'PLAN'
        ]

        reconstructed = ""

        for section in section_order:
            if section in sections:
                reconstructed += f"{sections[section]}\n\n"

        return reconstructed.strip()
