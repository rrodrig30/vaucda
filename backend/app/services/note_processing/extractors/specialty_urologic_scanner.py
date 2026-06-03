"""
Cross-Specialty Urologic Content Scanner

Scans ALL non-GU notes (Medical Oncology, Radiation Oncology, IR, Cardiology,
Infectious Disease, Hospital Medicine, etc.) for urologically-relevant content
that should be integrated into the urology clinic note.

This generalizes the consult-only provider_note_scanner.py pattern to work with
any specialty note type.

Author: VAUCDA Development Team
Date: February 2026
"""

import re
from typing import Dict, List, Optional, Set, Tuple

# Import base urologic keywords from provider_note_scanner (single source of truth)
from .provider_note_scanner import UROLOGIC_KEYWORDS


# Specialty-specific urologic keywords that extend the base set
# These capture urologically-relevant content from specific specialties
SPECIALTY_UROLOGIC_KEYWORDS = {
    # Medical Oncology - prostate/bladder/kidney cancer treatment
    'oncology': [
        'adt', 'androgen deprivation', 'androgen deprivation therapy',
        'enzalutamide', 'xtandi', 'abiraterone', 'zytiga',
        'docetaxel', 'cabazitaxel', 'pembrolizumab', 'keytruda',
        'avelumab', 'bavencio', 'nivolumab', 'opdivo',
        'psma pet', 'psma scan', 'ga-68 psma', 'lutetium',
        'bone scan', 'bone metastasis', 'bone metastases',
        'castration-resistant', 'crpc', 'mcrpc',
        'metastatic prostate', 'metastatic bladder', 'metastatic kidney',
        'gem/cis', 'gemcitabine', 'cisplatin', 'mvac',
        'checkpoint inhibitor', 'immunotherapy',
    ],

    # Radiation Oncology - prostate/bladder radiation, hormone therapy
    'radiation_oncology': [
        'brachytherapy', 'seed implant', 'hdr brachytherapy',
        'sbrt', 'stereotactic body', 'cyberknife',
        'ebrt', 'external beam', 'imrt', 'vmat', 'igrt',
        'radiation therapy', 'radiation treatment', 'radiotherapy',
        'hormone therapy', 'hormonal therapy',
        'lupron', 'leuprolide', 'eligard', 'firmagon', 'degarelix',
        'zoladex', 'goserelin', 'trelstar', 'triptorelin',
        'orchiectomy', 'bilateral orchiectomy',
        'pelvic radiation', 'prostate radiation', 'bladder radiation',
        'salvage radiation', 'adjuvant radiation',
        'radiation planning', 'simulation', 'ct simulation',
    ],

    # Interventional Radiology - GU procedures
    'interventional_radiology': [
        'nephrostomy', 'percutaneous nephrostomy', 'pcn',
        'nephrostomy tube', 'neph tube', 'pcn tube',
        'ureteral stent', 'stent placement', 'stent exchange',
        'embolization', 'renal embolization', 'prostate embolization',
        'ablation', 'renal ablation', 'cryoablation', 'rfa',
        'angiography', 'renal angiography',
        'biopsy', 'renal biopsy', 'prostate biopsy',
        'drainage', 'abscess drainage', 'perinephric',
    ],

    # Infectious Disease - GU infections
    'infectious_disease': [
        'urosepsis', 'urinary sepsis',
        'bacteremia', 'gram negative bacteremia',
        'sepsis', 'septic shock',  # Requires GU co-occurrence
        'pyelonephritis', 'pyonephrosis',
        'prostatitis', 'prostatic abscess',
        'epididymitis', 'orchitis', 'epididymo-orchitis',
        'fournier', 'fournier gangrene',
        'complicated uti', 'recurrent uti',
        'esbl', 'mrsa', 'vre', 'pseudomonas',
        'antibiotic', 'antimicrobial',  # Requires GU co-occurrence
    ],

    # Hospital Medicine / Inpatient - admissions for GU reasons
    'hospital_medicine': [
        'admission', 'admitted', 'hospitalization', 'hospitalized',
        'discharge', 'discharged',
        'inpatient', 'floor', 'icu',
        'acute kidney injury', 'aki', 'acute renal failure',
        'urinary obstruction', 'obstructive uropathy',
        'gross hematuria', 'clot retention',
        'urinary retention', 'acute urinary retention',
        'post-operative', 'postoperative', 'post-op',
    ],

    # Cardiology - clearance for urologic procedures
    'cardiology': [
        'anticoagulation', 'anticoagulant', 'blood thinner',
        'warfarin', 'coumadin', 'eliquis', 'apixaban',
        'xarelto', 'rivaroxaban', 'pradaxa', 'dabigatran',
        'antiplatelet', 'aspirin', 'plavix', 'clopidogrel',
        'bridging', 'bridge therapy', 'heparin bridge',
        'bleeding risk', 'surgical clearance', 'cardiac clearance',
        'pre-operative', 'preoperative', 'pre-op clearance',
        'hold anticoagulation', 'resume anticoagulation',
    ],
}

# Keywords that require co-occurrence with base urologic keywords
# (to avoid false positives from pure cardiology/ID notes)
REQUIRES_GU_COOCCURRENCE = {
    'sepsis', 'septic shock', 'antibiotic', 'antimicrobial',
    'admission', 'admitted', 'hospitalization', 'hospitalized',
    'discharge', 'discharged', 'inpatient', 'floor', 'icu',
    'anticoagulation', 'anticoagulant', 'blood thinner',
    'warfarin', 'coumadin', 'eliquis', 'apixaban',
    'xarelto', 'rivaroxaban', 'pradaxa', 'dabigatran',
    'antiplatelet', 'aspirin', 'plavix', 'clopidogrel',
    'bleeding risk',
    'surgical clearance', 'cardiac clearance', 'pre-operative',
    'preoperative', 'pre-op clearance', 'bridging', 'bridge therapy',
    'heparin bridge', 'hold anticoagulation', 'resume anticoagulation',
}


class SpecialtyUrologicScanner:
    """
    Scans non-GU specialty notes for urologically-relevant content.
    """

    def __init__(self):
        """Initialize scanner with compiled patterns."""
        # Combine base UROLOGIC_KEYWORDS with specialty-specific keywords
        all_keywords = set(UROLOGIC_KEYWORDS)
        for specialty_keywords in SPECIALTY_UROLOGIC_KEYWORDS.values():
            all_keywords.update(specialty_keywords)

        # Compile main urologic pattern (case-insensitive)
        self.urologic_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(kw) for kw in all_keywords) + r')\b',
            re.IGNORECASE
        )

        # Compile base urologic pattern for co-occurrence checking
        self.base_urologic_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(kw) for kw in UROLOGIC_KEYWORDS) + r')\b',
            re.IGNORECASE
        )

        # Compile co-occurrence keywords pattern
        self.cooccurrence_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(kw) for kw in REQUIRES_GU_COOCCURRENCE) + r')\b',
            re.IGNORECASE
        )

    def scan_notes(
        self,
        non_gu_notes: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Scan non-GU notes for urologically-relevant content.

        Args:
            non_gu_notes: List of non-GU note dictionaries from identify_notes()
                         Each dict has: {"title": "...", "date": "...", "content": "..."}

        Returns:
            List of dictionaries containing extracted urologic content:
            [
                {
                    "specialty": "MEDICAL ONCOLOGY",
                    "date": "Jan 15, 2026",
                    "content": "extracted urologic paragraphs...",
                    "keywords": ["PSMA PET", "ADT", "prostate cancer"]
                },
                ...
            ]
        """
        results = []

        for note in non_gu_notes:
            title = note.get("title", "")
            date = note.get("date", "")
            content = note.get("content", "")

            if not content:
                continue

            # Extract specialty from title
            specialty = self._extract_specialty(title)

            # Extract urologic content from note
            urologic_content, keywords = self._extract_urologic_content(content)

            if urologic_content:
                results.append({
                    "specialty": specialty,
                    "date": date,
                    "content": urologic_content,
                    "keywords": keywords
                })

        return results

    def _extract_specialty(self, title: str) -> str:
        """
        Extract specialty name from note title.

        Common VA title formats:
        - "MEDICAL ONCOLOGY NOTE"
        - "RADIATION ONCOLOGY CONSULT"
        - "INTERVENTIONAL RADIOLOGY PROCEDURE NOTE"
        - "INFECTIOUS DISEASE CONSULT"
        - "HOSPITAL MEDICINE PROGRESS NOTE"
        - "CARDIOLOGY CONSULT"

        Args:
            title: Note title string

        Returns:
            Specialty name in uppercase
        """
        if not title:
            return "UNKNOWN SPECIALTY"

        title_upper = title.upper()

        # Map common title patterns to specialty names
        specialty_patterns = [
            (r'MEDICAL\s+ONCOLOGY', 'MEDICAL ONCOLOGY'),
            (r'MED\s+ONC', 'MEDICAL ONCOLOGY'),
            (r'RADIATION\s+ONCOLOGY', 'RADIATION ONCOLOGY'),
            (r'RAD\s+ONC', 'RADIATION ONCOLOGY'),
            (r'INTERVENTIONAL\s+RADIOLOGY', 'INTERVENTIONAL RADIOLOGY'),
            (r'\bIR\b', 'INTERVENTIONAL RADIOLOGY'),
            (r'INFECTIOUS\s+DISEASE', 'INFECTIOUS DISEASE'),
            (r'\bID\b\s+(?:CONSULT|NOTE)', 'INFECTIOUS DISEASE'),
            (r'HOSPITAL\s+MEDICINE', 'HOSPITAL MEDICINE'),
            (r'HOSPITALIST', 'HOSPITAL MEDICINE'),
            (r'INTERNAL\s+MEDICINE', 'INTERNAL MEDICINE'),
            (r'CARDIOLOGY', 'CARDIOLOGY'),
            (r'PRIMARY\s+CARE', 'PRIMARY CARE'),
            (r'NEPHROLOGY', 'NEPHROLOGY'),
            (r'EMERGENCY', 'EMERGENCY MEDICINE'),
        ]

        for pattern, specialty in specialty_patterns:
            if re.search(pattern, title_upper):
                return specialty

        # Fallback: return first two words of title
        words = title_upper.split()
        if len(words) >= 2:
            return ' '.join(words[:2])
        return title_upper or "UNKNOWN SPECIALTY"

    def _extract_urologic_content(
        self,
        content: str
    ) -> Tuple[str, List[str]]:
        """
        Extract paragraphs containing urologic content from a note.

        Args:
            content: Full note text

        Returns:
            Tuple of (extracted_content, list_of_keywords_found)
        """
        # First pass: find all urologic keywords in the document
        all_keywords = set(
            match.group(1).lower()
            for match in self.urologic_pattern.finditer(content)
        )

        if not all_keywords:
            return '', []

        # Check if document has base urologic context (for co-occurrence filtering)
        has_base_gu_context = bool(self.base_urologic_pattern.search(content))

        # Extract paragraphs containing urologic content
        paragraphs = re.split(r'\n\s*\n', content)
        urologic_paragraphs = []
        final_keywords = set()

        for para in paragraphs:
            if not para.strip():
                continue

            # Find keywords in this paragraph
            para_keywords = set(
                match.group(1).lower()
                for match in self.urologic_pattern.finditer(para)
            )

            if not para_keywords:
                continue

            # Check co-occurrence requirements
            # A keyword requires co-occurrence if it OR any word in it is in REQUIRES_GU_COOCCURRENCE
            def requires_cooccurrence(kw: str) -> bool:
                kw_lower = kw.lower()
                if kw_lower in REQUIRES_GU_COOCCURRENCE:
                    return True
                # Check if any word in the keyword requires co-occurrence
                for word in kw_lower.split():
                    if word in REQUIRES_GU_COOCCURRENCE:
                        return True
                return False

            # Separate keywords that require GU context from direct urologic keywords
            cooccurrence_only = {kw for kw in para_keywords if requires_cooccurrence(kw)}
            direct_uro_keywords = para_keywords - cooccurrence_only

            # If paragraph only has co-occurrence keywords (no direct urologic),
            # it needs base GU context in the document
            if not direct_uro_keywords and cooccurrence_only:
                if not has_base_gu_context:
                    continue

            # Clean and add paragraph
            cleaned_para = self._clean_paragraph(para)
            if cleaned_para and len(cleaned_para) > 30:  # Skip very short fragments
                urologic_paragraphs.append(cleaned_para)
                final_keywords.update(para_keywords)

        return '\n\n'.join(urologic_paragraphs), list(final_keywords)

    def _clean_paragraph(self, para: str) -> str:
        """
        Clean paragraph of VA-specific metadata.

        Args:
            para: Paragraph text

        Returns:
            Cleaned paragraph
        """
        # Remove VA metadata patterns
        cleaned = re.sub(r'Signed\s+by:.*', '', para, flags=re.IGNORECASE)
        cleaned = re.sub(r'AUTHOR:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'DATE OF NOTE:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'LOCAL TITLE:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'STANDARD TITLE:.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}', '', cleaned)

        # Clean up whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = cleaned.strip()

        return cleaned


def scan_non_gu_notes_for_urologic_content(
    non_gu_notes: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    Scan non-GU notes for urologically-relevant content.

    This is the main entry point - call this from note_builder.py and stage2_builder.py.

    Args:
        non_gu_notes: List of non-GU note dicts from identify_notes()["non_gu_notes"]

    Returns:
        List of dicts with extracted urologic content per specialty note
    """
    scanner = SpecialtyUrologicScanner()
    return scanner.scan_notes(non_gu_notes)


def format_cross_specialty_context(
    scan_results: List[Dict[str, str]]
) -> str:
    """
    Format scan results for LLM consumption.

    Creates a structured context block that HPI/Assessment/Plan agents can use.

    Args:
        scan_results: Output from scan_non_gu_notes_for_urologic_content()

    Returns:
        Formatted string with specialty/date headers, or empty string if no results
    """
    if not scan_results:
        return ""

    context_parts = []

    for result in scan_results:
        specialty = result.get("specialty", "UNKNOWN")
        date = result.get("date", "Unknown date")
        content = result.get("content", "")
        keywords = result.get("keywords", [])

        if not content:
            continue

        # Format header with specialty and date
        header = f"[{specialty} - {date}]"

        # Add keywords for context (helps LLM understand relevance)
        if keywords:
            keyword_str = ", ".join(sorted(set(kw.upper() for kw in keywords[:5])))
            header += f" (Keywords: {keyword_str})"

        context_parts.append(f"{header}\n{content}")

    if not context_parts:
        return ""

    return "=== CROSS-SPECIALTY UROLOGIC FINDINGS ===\n\n" + "\n\n".join(context_parts)
