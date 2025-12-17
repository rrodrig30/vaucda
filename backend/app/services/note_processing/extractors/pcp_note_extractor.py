"""
Primary Care Note Extractor

Specialized extractor for VA Primary Care notes (Annual exams, follow-ups).
Handles narrative-style social/family/surgical history embedded in PCP notes.

Author: VAUCDA Development Team
Date: December 2025
"""

import re
from typing import Dict, List, Optional


class PCPNoteExtractor:
    """Extracts clinical data from VA Primary Care notes."""

    def __init__(self):
        """Initialize the PCP note extractor."""
        pass

    def extract_all(self, pcp_note: str) -> Dict[str, str]:
        """
        Extract all clinical data from a primary care note.

        Args:
            pcp_note: Full PCP note text

        Returns:
            Dictionary with extracted sections:
            - social_history
            - family_history
            - surgical_history (PSH)
            - dietary_history
            - hpi
        """
        return {
            'social_history': self.extract_social_history(pcp_note),
            'family_history': self.extract_family_history(pcp_note),
            'surgical_history': self.extract_surgical_history(pcp_note),
            'dietary_history': self.extract_dietary_history(pcp_note),
            'hpi': self.extract_hpi(pcp_note)
        }

    def extract_social_history(self, pcp_note: str) -> str:
        """
        Extract social history from PCP note.

        VA PCP notes often embed social history in narrative format within
        "CURRENT HEALTH STATUS:" or similar sections.

        Extracts:
        - Tobacco use
        - Alcohol use
        - Military service
        - Living situation
        - Occupation

        Args:
            pcp_note: Full PCP note text

        Returns:
            Synthesized social history text
        """
        social_elements = {}

        # Pattern 1: Tobacco history
        tobacco = self._extract_tobacco(pcp_note)
        if tobacco:
            social_elements['tobacco'] = tobacco

        # Pattern 2: Alcohol history
        alcohol = self._extract_alcohol(pcp_note)
        if alcohol:
            social_elements['alcohol'] = alcohol

        # Pattern 3: Military service
        military = self._extract_military_service(pcp_note)
        if military:
            social_elements['military'] = military

        # Pattern 4: Living situation
        living = self._extract_living_situation(pcp_note)
        if living:
            social_elements['living'] = living

        # Pattern 5: Occupation/employment
        occupation = self._extract_occupation(pcp_note)
        if occupation:
            social_elements['occupation'] = occupation

        if not social_elements:
            return ""

        # Synthesize into readable format
        return self._synthesize_social_history(social_elements)

    def _extract_tobacco(self, text: str) -> Optional[str]:
        """Extract tobacco use history."""
        # Pattern 1: "Tob: Quit age 20s" or similar
        pattern1 = r'Tob(?:acco)?:\s*([^\n]+)'
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 2: Narrative format
        patterns = [
            r'(?:Former|Ex)\s+tobacco\s+user,?\s*quit\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
            r'Quit\s+(?:smoking|tobacco)\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
            r'(?:Never|Non[- ]?)smoker',
            r'Current\s+smoker,?\s*([^\n.]+)',
            r'Tobacco:\s+([^\n]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if 'never' in match.group(0).lower() or 'non' in match.group(0).lower():
                    return "Never smoker"
                if match.groups():
                    return match.group(0).strip()
                return match.group(1).strip() if match.groups() else match.group(0).strip()

        # Pattern 3: Clinical reminder tobacco screening
        tobacco_screen_pattern = r'Tobacco Use Screening:.*?(?:has never smoked|never used|quit|current smoker)([^\n]*)'
        match = re.search(tobacco_screen_pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            full_match = match.group(0)
            if 'never smoked' in full_match.lower():
                return "Never smoker"
            elif 'quit' in full_match.lower():
                return "Former smoker (see clinical reminder for details)"

        return None

    def _extract_alcohol(self, text: str) -> Optional[str]:
        """Extract alcohol use history."""
        # Pattern 1: "ETOH -approximately 2 glasses of wine twice weekly"
        pattern1 = r'ETOH\s*[:-]?\s*([^\n]+)'
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            alcohol_text = match.group(1).strip()
            if alcohol_text.lower() not in ['none', 'no', 'denies']:
                return alcohol_text

        # Pattern 2: Narrative format
        patterns = [
            r'(?:Reports|States)\s+consuming\s+(?:approximately\s+)?([^.]+(?:glass|drink|beer|wine)[^.]*)',
            r'Alcohol\s*[:-]\s*([^\n]+)',
            r'(?:Drinks|Consumes)\s+([^.]+(?:glass|drink|beer|wine)[^.]*)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Pattern 3: AUDIT-C screening
        audit_pattern = r'Alcohol Use Screen.*?(?:negative|positive).*?score[=:]?\s*(\d+)'
        match = re.search(audit_pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            score = match.group(1)
            # Extract drink frequency from AUDIT-C if present
            freq_match = re.search(r'How often.*?alcohol.*?\n\s*(.+?)(?:\n\n|\n\d+\.)', text, re.DOTALL | re.IGNORECASE)
            if freq_match:
                frequency = freq_match.group(1).strip()
                return f"{frequency} (AUDIT-C score: {score})"

        return None

    def _extract_military_service(self, text: str) -> Optional[str]:
        """Extract military service history."""
        # Pattern: "Military Service -10.5 years Air Force. Worked in the band. Now retired"
        pattern = r'Military Service\s*[:-]\s*([^\n]+(?:\n(?!\s*$)[^\n]+)*)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Alternative pattern: OEF/OIF status or service-connected
        patterns = [
            r'(?:Served|Service)\s+in\s+(?:the\s+)?([A-Z][a-z]+\s+(?:Force|Navy|Army|Marines|Coast Guard))[^\n.]*',
            r'(?:Veteran|Vet)\s+of\s+([^\n.]+)',
            r'(\d+\.?\d*)\s+years\s+(?:in\s+)?(?:the\s+)?([A-Z][a-z]+\s+(?:Force|Navy|Army|Marines|Coast Guard))'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()

        return None

    def _extract_living_situation(self, text: str) -> Optional[str]:
        """Extract living situation."""
        patterns = [
            r'(?:Lives|Living)\s+(?:at\s+)?home',
            r'(?:Lives|Living)\s+(?:with|alone)',
            r'Living will[:-]?\s*([^\n]+)',
            r'(?:Stable|Unstable)\s+housing'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()

        return None

    def _extract_occupation(self, text: str) -> Optional[str]:
        """Extract occupation or employment status."""
        patterns = [
            r'(?:Works?|Worked|Employment|Occupation)[:\s]+as\s+([^\n.]+)',
            r'(?:Retired|Disability|Unemployed)',
            r'Now retired'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if match.groups():
                    return match.group(1).strip()
                return match.group(0).strip()

        return None

    def _synthesize_social_history(self, elements: Dict[str, str]) -> str:
        """Synthesize social history elements into readable format."""
        parts = []

        if 'tobacco' in elements:
            parts.append(elements['tobacco'])

        if 'alcohol' in elements:
            parts.append(f"Reports consuming {elements['alcohol']}" if not elements['alcohol'].startswith('Reports') else elements['alcohol'])

        if 'military' in elements:
            parts.append(elements['military'])

        if 'occupation' in elements:
            parts.append(elements['occupation'])

        if 'living' in elements:
            parts.append(elements['living'])

        return '. '.join(parts) + '.' if parts else ""

    def extract_family_history(self, pcp_note: str) -> str:
        """
        Extract family history from PCP note.

        Format: "Brother-colon cancer age 43-deceased; Mother and sister and grandmother-diabetes"

        Args:
            pcp_note: Full PCP note text

        Returns:
            Family history text
        """
        # Pattern 1: Explicit "FAMILY HISTORY:" section
        fh_section_pattern = r'FAMILY HISTORY:\s*\n([^\n]+(?:\n(?!\s*\n)[^\n]+)*)'
        match = re.search(fh_section_pattern, pcp_note, re.IGNORECASE)
        if match:
            fh_text = match.group(1).strip()
            # Clean up extra whitespace
            fh_text = re.sub(r'\s+', ' ', fh_text)
            return fh_text

        # Pattern 2: Family history in problem list
        # "Family history of cancer of colon"
        fh_problem_pattern = r'Family history of\s+([^\n(]+)'
        matches = re.findall(fh_problem_pattern, pcp_note, re.IGNORECASE)
        if matches:
            conditions = [m.strip() for m in matches]
            return f"Family history of {', '.join(conditions)}"

        # Pattern 3: Narrative format with relationships and conditions
        # "Brother-colon cancer age 43-deceased"
        fh_narrative_pattern = r'((?:Mother|Father|Brother|Sister|Son|Daughter|Grandmother|Grandfather)[-\s]+[^.\n]+(?:cancer|diabetes|heart disease|COPD|hypertension)[^.\n]*)'
        matches = re.findall(fh_narrative_pattern, pcp_note, re.IGNORECASE)
        if matches:
            return '. '.join(matches) + '.'

        return ""

    def extract_surgical_history(self, pcp_note: str) -> str:
        """
        Extract past surgical history from PCP note.

        Args:
            pcp_note: Full PCP note text

        Returns:
            Surgical history text
        """
        surgeries = []

        # Pattern 1: "PSH" section
        # Format: PSH\n procedure1\n procedure2\n...\nMEDICATIONS:
        psh_section_pattern = r'PSH\s*\n((?:\s+[^\n]+\n)+)'
        match = re.search(psh_section_pattern, pcp_note, re.IGNORECASE)
        if match:
            psh_text = match.group(1).strip()
            # Split by newlines and clean
            surgery_lines = [line.strip() for line in psh_text.split('\n') if line.strip()]
            surgeries.extend(surgery_lines)

        # Pattern 2: Narrative format with dates
        # "Cervical fusion C1- T2-2023 April"
        narrative_pattern = r'([A-Z][a-z]+(?:\s+[a-z]+)*(?:\s+[A-Z]\d+-?\s*[A-Z]?\d*)?)\s*[-–]\s*(\d{4}|\d{1,2}/\d{4}|[A-Z][a-z]+\s+\d{4})'
        matches = re.findall(narrative_pattern, pcp_note)
        for procedure, date in matches:
            # Filter to likely surgical procedures
            if any(keyword in procedure.lower() for keyword in ['fusion', 'repair', 'release', 'retrieval', 'surgery', 'ectomy', 'plasty', 'otomy']):
                surgeries.append(f"{procedure} ({date})")

        # Pattern 3: "s/p" or "status post" format
        sp_pattern = r'(?:s/p|status post)\s+([^(]+)\(([^)]+)\)'
        matches = re.findall(sp_pattern, pcp_note, re.IGNORECASE)
        for procedure, date in matches:
            surgeries.append(f"{procedure.strip()} ({date.strip()})")

        if not surgeries:
            return ""

        # Remove duplicates while preserving order
        seen = set()
        unique_surgeries = []
        for surgery in surgeries:
            surgery_lower = surgery.lower()
            if surgery_lower not in seen:
                seen.add(surgery_lower)
                unique_surgeries.append(surgery)

        return '\n'.join(f"- {s}" for s in unique_surgeries)

    def extract_dietary_history(self, pcp_note: str) -> str:
        """
        Extract dietary history from PCP note.

        Args:
            pcp_note: Full PCP note text

        Returns:
            Dietary history text
        """
        # Pattern 1: Nutrition section in nursing assessment
        nutrition_pattern = r'Nutrition:\s*\n\s*([^\n]+)'
        match = re.search(nutrition_pattern, pcp_note, re.IGNORECASE)
        if match:
            nutrition = match.group(1).strip()
            if nutrition.lower() not in ['no problem', 'wdl', 'wnl']:
                return nutrition

        # Pattern 2: Food insecurity screening
        food_pattern = r'food.*?(?:run out|didn.*?last|insecurity)([^\n.]+)'
        match = re.search(food_pattern, pcp_note, re.DOTALL | re.IGNORECASE)
        if match:
            return f"Food security screening: {match.group(0)}"

        return ""

    def extract_hpi(self, pcp_note: str) -> str:
        """
        Extract HPI or chief complaint from PCP note.

        Args:
            pcp_note: Full PCP note text

        Returns:
            HPI text
        """
        # Pattern 1: Chief complaint or problem/complaint section
        cc_pattern = r'(?:Chief complaint|Problem/Chief Complaint):\s*([^\n]+)'
        match = re.search(cc_pattern, pcp_note, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Pattern 2: Assessment section from walk-in visits
        assessment_pattern = r'Assessment:\s+([^/][^\n]+(?:\n(?!\s*\n)[^\n]+)*)'
        match = re.search(assessment_pattern, pcp_note, re.IGNORECASE)
        if match:
            assessment = match.group(1).strip()
            # Clean up: limit to first few sentences
            sentences = re.split(r'[.!?]\s+', assessment)
            return '. '.join(sentences[:3]) + '.'

        return ""


# Convenience functions
def extract_from_pcp_note(pcp_note: str) -> Dict[str, str]:
    """Extract all data from a primary care note."""
    extractor = PCPNoteExtractor()
    return extractor.extract_all(pcp_note)


def extract_social_from_pcp(pcp_note: str) -> str:
    """Extract social history from PCP note."""
    extractor = PCPNoteExtractor()
    return extractor.extract_social_history(pcp_note)


def extract_family_from_pcp(pcp_note: str) -> str:
    """Extract family history from PCP note."""
    extractor = PCPNoteExtractor()
    return extractor.extract_family_history(pcp_note)


def extract_surgical_from_pcp(pcp_note: str) -> str:
    """Extract surgical history from PCP note."""
    extractor = PCPNoteExtractor()
    return extractor.extract_surgical_history(pcp_note)
