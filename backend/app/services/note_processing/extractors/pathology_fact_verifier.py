"""
Pathology Fact Verifier

Eliminates hallucinations in pathology synthesis by:
1. Extracting ground-truth pathology facts deterministically from source documents
2. Verifying synthesized pathology against these facts
3. Flagging or removing any claims not supported by source data

This is a CRITICAL SAFETY feature - incorrect pathology can lead to wrong treatment decisions.

Author: VAUCDA Development Team
Date: February 2026
"""

import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class PathologyFactType(Enum):
    """Types of pathology facts that can be extracted and verified."""
    GLEASON_SCORE = "gleason_score"
    GRADE_GROUP = "grade_group"
    CORE_COUNT = "core_count"
    LOCATION = "location"
    DATE = "date"
    DIAGNOSIS = "diagnosis"
    PERCENTAGE = "percentage"
    PERINEURAL_INVASION = "perineural_invasion"
    MARGIN_STATUS = "margin_status"
    STAGE = "stage"
    TUMOR_SIZE = "tumor_size"


@dataclass
class PathologyFact:
    """A single verified pathology fact from source document."""
    fact_type: PathologyFactType
    value: str
    normalized_value: str  # Standardized form for comparison
    source_text: str  # Original text where fact was found
    confidence: float = 1.0  # 1.0 = deterministic extraction


@dataclass
class VerificationResult:
    """Result of verifying synthesized pathology against source facts."""
    is_verified: bool
    confidence_score: float  # 0.0 - 1.0
    verified_claims: List[str] = field(default_factory=list)
    unverified_claims: List[str] = field(default_factory=list)
    potential_hallucinations: List[str] = field(default_factory=list)
    corrected_text: Optional[str] = None
    details: Dict = field(default_factory=dict)


class PathologyFactVerifier:
    """
    Verifies pathology synthesis against deterministically extracted facts.

    Usage:
        verifier = PathologyFactVerifier()

        # Extract facts from source document(s)
        verifier.extract_facts_from_source(source_document)

        # Verify synthesized pathology
        result = verifier.verify_synthesis(synthesized_pathology)

        if not result.is_verified:
            print(f"Potential hallucinations: {result.potential_hallucinations}")
            # Use result.corrected_text if available
    """

    def __init__(self):
        self.ground_truth_facts: List[PathologyFact] = []
        self._gleason_scores: Set[str] = set()
        self._grade_groups: Set[str] = set()
        self._core_counts: Set[str] = set()
        self._locations: Set[str] = set()
        self._dates: Set[str] = set()
        self._diagnoses: Set[str] = set()
        self._percentages: Set[str] = set()
        self._has_pni: Optional[bool] = None
        self._margin_status: Optional[str] = None
        self._stages: Set[str] = set()
        self._tumor_sizes: Set[str] = set()

    def reset(self):
        """Clear all extracted facts."""
        self.ground_truth_facts = []
        self._gleason_scores = set()
        self._grade_groups = set()
        self._core_counts = set()
        self._locations = set()
        self._dates = set()
        self._diagnoses = set()
        self._percentages = set()
        self._has_pni = None
        self._margin_status = None
        self._stages = set()
        self._tumor_sizes = set()

    def extract_facts_from_source(self, source_text: str) -> List[PathologyFact]:
        """
        Extract all pathology facts deterministically from source document.

        This uses regex patterns ONLY - no LLM involved - to ensure
        ground truth cannot be hallucinated.

        Args:
            source_text: Raw source document text

        Returns:
            List of extracted PathologyFact objects
        """
        facts = []

        # Extract Gleason scores
        facts.extend(self._extract_gleason_scores(source_text))

        # Extract Grade Groups
        facts.extend(self._extract_grade_groups(source_text))

        # Extract core counts
        facts.extend(self._extract_core_counts(source_text))

        # Extract anatomical locations
        facts.extend(self._extract_locations(source_text))

        # Extract dates
        facts.extend(self._extract_dates(source_text))

        # Extract diagnoses
        facts.extend(self._extract_diagnoses(source_text))

        # Extract percentages
        facts.extend(self._extract_percentages(source_text))

        # Extract perineural invasion status
        facts.extend(self._extract_perineural_invasion(source_text))

        # Extract margin status
        facts.extend(self._extract_margin_status(source_text))

        # Extract staging information
        facts.extend(self._extract_staging(source_text))

        # Extract tumor sizes
        facts.extend(self._extract_tumor_sizes(source_text))

        self.ground_truth_facts.extend(facts)
        return facts

    def _extract_gleason_scores(self, text: str) -> List[PathologyFact]:
        """Extract all Gleason scores from text."""
        facts = []

        # Pattern 1: "Gleason score 3+4=7" or "Gleason 3+4"
        patterns = [
            r'GLEASON[\'S]?\s+(?:SCORE\s+)?(\d)\s*\+\s*(\d)(?:\s*=\s*(\d+))?',
            r'GLEASON[\'S]?\s+GRADE\s+(\d)\s*\+\s*(\d)',
            r'(\d)\s*\+\s*(\d)\s*=\s*(\d+)/10',  # 3+3=6/10
            r'GRADE\s+GROUP\s+\d+\s*\((\d)\s*\+\s*(\d)\)',  # Grade Group 2 (3+4)
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                primary = match.group(1)
                secondary = match.group(2)
                gleason = f"{primary}+{secondary}"
                normalized = gleason

                # Store normalized form
                self._gleason_scores.add(normalized)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.GLEASON_SCORE,
                    value=gleason,
                    normalized_value=normalized,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_grade_groups(self, text: str) -> List[PathologyFact]:
        """Extract all Grade Groups from text."""
        facts = []

        patterns = [
            r'GRADE\s+GROUP\s+(\d)',
            r'GG\s*(\d)',
            r'ISUP\s+(?:GRADE\s+)?(\d)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                grade_group = match.group(1)
                self._grade_groups.add(grade_group)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.GRADE_GROUP,
                    value=grade_group,
                    normalized_value=grade_group,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_core_counts(self, text: str) -> List[PathologyFact]:
        """Extract core counts (e.g., '3 of 12 cores positive')."""
        facts = []
        seen_positions = set()  # Track positions to avoid duplicates

        patterns = [
            r'INVOLVING\s+(\d+)\s*(?:of|/)\s*(\d+)\s*CORES?',
            r'(\d+)\s*(?:of|/)\s*(\d+)\s*cores?\s*(?:positive|involved|with)',
            r'(\d+)\s*(?:of|/)\s*(\d+)\s*cores?',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Skip if we already found a core count at this position
                start_pos = match.start()
                if any(abs(start_pos - pos) < 5 for pos in seen_positions):
                    continue

                positive = match.group(1)
                total = match.group(2)
                core_count = f"{positive}/{total}"
                self._core_counts.add(core_count)
                seen_positions.add(start_pos)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.CORE_COUNT,
                    value=core_count,
                    normalized_value=core_count,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_locations(self, text: str) -> List[PathologyFact]:
        """Extract anatomical locations."""
        facts = []

        # Prostate locations
        prostate_locations = [
            r'((?:RIGHT|LEFT|BILATERAL)\s+(?:MEDIAL\s+|LATERAL\s+)?(?:BASE|MID|APEX))',
            r'((?:RIGHT|LEFT)\s+(?:ANTERIOR|POSTERIOR)\s+(?:BASE|MID|APEX))',
            r'PROSTATE[,\s]+([A-Z]+\s+(?:BASE|MID|APEX))',
        ]

        for pattern in prostate_locations:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                location = match.group(1).strip().lower()
                # Normalize
                location = re.sub(r'\s+', ' ', location)
                self._locations.add(location)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.LOCATION,
                    value=location,
                    normalized_value=location,
                    source_text=match.group(0)
                ))

        # Kidney/bladder locations
        other_locations = [
            r'((?:LEFT|RIGHT)\s+(?:KIDNEY|RENAL)\s+(?:MASS|TUMOR|LOWER POLE|UPPER POLE))',
            r'((?:LEFT|RIGHT)\s+(?:URETER|URETERAL))',
            r'(BLADDER[,\s]+[A-Z]+\s+(?:WALL|DOME|TRIGONE))',
        ]

        for pattern in other_locations:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                location = match.group(1).strip().lower()
                location = re.sub(r'\s+', ' ', location)
                self._locations.add(location)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.LOCATION,
                    value=location,
                    normalized_value=location,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_dates(self, text: str) -> List[PathologyFact]:
        """Extract procedure/pathology dates."""
        facts = []

        patterns = [
            r'(\d{1,2}/\d{1,2}/\d{2,4})',  # MM/DD/YY or MM/DD/YYYY
            r'([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})',  # Jan 15, 2025
            r'(\d{1,2}/\d{4})',  # M/YYYY
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                date = match.group(1).strip()
                self._dates.add(date)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.DATE,
                    value=date,
                    normalized_value=date,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_diagnoses(self, text: str) -> List[PathologyFact]:
        """Extract diagnosis types (adenocarcinoma, negative, etc.)."""
        facts = []

        diagnosis_patterns = [
            (r'PROSTATIC\s+ADENOCARCINOMA', 'prostatic adenocarcinoma'),
            (r'ACINAR\s+ADENOCARCINOMA', 'acinar adenocarcinoma'),
            (r'ADENOCARCINOMA', 'adenocarcinoma'),
            (r'NEGATIVE\s+FOR\s+MALIGNANCY', 'negative for malignancy'),
            (r'NO\s+(?:EVIDENCE\s+OF\s+)?MALIGNANCY', 'negative for malignancy'),
            (r'ATYPICAL\s+SMALL\s+ACINAR\s+PROLIFERATION', 'ASAP'),
            (r'ASAP', 'ASAP'),
            (r'HIGH[- ]?GRADE\s+(?:PROSTATIC\s+)?INTRAEPITHELIAL\s+NEOPLASIA', 'HGPIN'),
            (r'HGPIN', 'HGPIN'),
            (r'UROTHELIAL\s+CARCINOMA', 'urothelial carcinoma'),
            (r'TRANSITIONAL\s+CELL\s+CARCINOMA', 'transitional cell carcinoma'),
            (r'RENAL\s+CELL\s+CARCINOMA', 'renal cell carcinoma'),
            (r'CLEAR\s+CELL\s+RENAL\s+CELL\s+CARCINOMA', 'clear cell RCC'),
            (r'PAPILLARY\s+RENAL\s+CELL\s+CARCINOMA', 'papillary RCC'),
            (r'CHROMOPHOBE\s+RENAL\s+CELL\s+CARCINOMA', 'chromophobe RCC'),
            (r'TUBULAR\s+ADENOMA', 'tubular adenoma'),
        ]

        for pattern, normalized in diagnosis_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                self._diagnoses.add(normalized)

                match = re.search(pattern, text, re.IGNORECASE)
                facts.append(PathologyFact(
                    fact_type=PathologyFactType.DIAGNOSIS,
                    value=normalized,
                    normalized_value=normalized,
                    source_text=match.group(0) if match else pattern
                ))

        return facts

    def _extract_percentages(self, text: str) -> List[PathologyFact]:
        """Extract percentage involvement."""
        facts = []
        seen_pcts = set()  # Avoid duplicate extraction

        patterns = [
            r'INVOLVING\s+(?:LESS\s+THAN\s+)?(\d+)\s*%',
            r'(\d+)\s*%\s*(?:OF\s+)?(?:TISSUE|INVOLVEMENT|INVOLVED)',
            r'(\d+)\s*%\s*TUMOR',
            r'\((\d+)\s*%\)',  # (35%) format
            r',\s*(\d+)\s*%',  # comma-separated percentage
            r'CORES?\s*\((\d+)\s*%\)',  # cores (35%)
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                pct = match.group(1)
                if pct in seen_pcts:
                    continue
                seen_pcts.add(pct)
                self._percentages.add(pct)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.PERCENTAGE,
                    value=pct,
                    normalized_value=pct,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_perineural_invasion(self, text: str) -> List[PathologyFact]:
        """Extract perineural invasion status."""
        facts = []

        pni_positive = [
            r'PERINEURAL\s+INVASION\s+(?:IS\s+)?(?:PRESENT|IDENTIFIED|SEEN)',
            r'(?:WITH|SHOWS?)\s+PERINEURAL\s+INVASION',
            r'PNI\s+(?:IS\s+)?PRESENT',
        ]

        pni_negative = [
            r'NO\s+PERINEURAL\s+INVASION',
            r'PERINEURAL\s+INVASION\s+(?:IS\s+)?(?:NOT\s+)?(?:ABSENT|NOT\s+IDENTIFIED|NOT\s+SEEN)',
            r'PNI\s+(?:IS\s+)?(?:ABSENT|NEGATIVE)',
        ]

        for pattern in pni_positive:
            if re.search(pattern, text, re.IGNORECASE):
                self._has_pni = True
                match = re.search(pattern, text, re.IGNORECASE)
                facts.append(PathologyFact(
                    fact_type=PathologyFactType.PERINEURAL_INVASION,
                    value="present",
                    normalized_value="present",
                    source_text=match.group(0) if match else pattern
                ))
                break

        for pattern in pni_negative:
            if re.search(pattern, text, re.IGNORECASE):
                self._has_pni = False
                match = re.search(pattern, text, re.IGNORECASE)
                facts.append(PathologyFact(
                    fact_type=PathologyFactType.PERINEURAL_INVASION,
                    value="absent",
                    normalized_value="absent",
                    source_text=match.group(0) if match else pattern
                ))
                break

        return facts

    def _extract_margin_status(self, text: str) -> List[PathologyFact]:
        """Extract surgical margin status."""
        facts = []

        positive_patterns = [
            r'MARGIN[S]?\s+(?:ARE\s+)?POSITIVE',
            r'POSITIVE\s+(?:SURGICAL\s+)?MARGIN[S]?',
            r'MARGIN[S]?\s+INVOLVED',
        ]

        negative_patterns = [
            r'MARGIN[S]?\s+(?:ARE\s+)?NEGATIVE',
            r'NEGATIVE\s+(?:SURGICAL\s+)?MARGIN[S]?',
            r'MARGIN[S]?\s+(?:ARE\s+)?(?:FREE|CLEAR|UNINVOLVED)',
        ]

        for pattern in positive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                self._margin_status = "positive"
                match = re.search(pattern, text, re.IGNORECASE)
                facts.append(PathologyFact(
                    fact_type=PathologyFactType.MARGIN_STATUS,
                    value="positive",
                    normalized_value="positive",
                    source_text=match.group(0) if match else pattern
                ))
                break

        for pattern in negative_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                self._margin_status = "negative"
                match = re.search(pattern, text, re.IGNORECASE)
                facts.append(PathologyFact(
                    fact_type=PathologyFactType.MARGIN_STATUS,
                    value="negative",
                    normalized_value="negative",
                    source_text=match.group(0) if match else pattern
                ))
                break

        return facts

    def _extract_staging(self, text: str) -> List[PathologyFact]:
        """Extract pathologic staging (pT, pN, etc.)."""
        facts = []

        patterns = [
            r'(pT\d[abc]?)',  # pT2a, pT3b
            r'(pN\d)',  # pN0, pN1
            r'(pM\d)',  # pM0, pM1
            r'STAGE\s+([IVX]+[ABC]?)',  # Stage IIIA
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                stage = match.group(1).upper()
                self._stages.add(stage)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.STAGE,
                    value=stage,
                    normalized_value=stage,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_tumor_sizes(self, text: str) -> List[PathologyFact]:
        """Extract tumor sizes."""
        facts = []

        patterns = [
            r'(\d+\.?\d*)\s*(?:CM|MM)\s*(?:TUMOR|MASS|LESION)',
            r'TUMOR[,\s]+(\d+\.?\d*)\s*(?:CM|MM)',
            r'(?:MEASURING|SIZE[:\s]+)(\d+\.?\d*)\s*(?:X\s*\d+\.?\d*\s*)?(?:CM|MM)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                size = match.group(1)
                self._tumor_sizes.add(size)

                facts.append(PathologyFact(
                    fact_type=PathologyFactType.TUMOR_SIZE,
                    value=size,
                    normalized_value=size,
                    source_text=match.group(0)
                ))

        return facts

    def verify_synthesis(self, synthesized_text: str) -> VerificationResult:
        """
        Verify synthesized pathology against ground truth facts.

        Args:
            synthesized_text: LLM-synthesized pathology text

        Returns:
            VerificationResult with verification status and details
        """
        if not self.ground_truth_facts:
            return VerificationResult(
                is_verified=False,
                confidence_score=0.0,
                details={"error": "No ground truth facts extracted"}
            )

        verified_claims = []
        unverified_claims = []
        potential_hallucinations = []

        # Check Gleason scores in synthesis
        synthesis_gleasons = set()
        for pattern in [r'GLEASON[\'S]?\s+(?:SCORE\s+)?(\d)\s*\+\s*(\d)',
                        r'(\d)\s*\+\s*(\d)\s*=\s*\d+']:
            for match in re.finditer(pattern, synthesized_text, re.IGNORECASE):
                gleason = f"{match.group(1)}+{match.group(2)}"
                synthesis_gleasons.add(gleason)

        for gleason in synthesis_gleasons:
            if gleason in self._gleason_scores:
                verified_claims.append(f"Gleason {gleason}")
            else:
                potential_hallucinations.append(f"Gleason {gleason} (not in source)")

        # Check Grade Groups in synthesis
        synthesis_grades = set()
        for match in re.finditer(r'GRADE\s+GROUP\s+(\d)', synthesized_text, re.IGNORECASE):
            synthesis_grades.add(match.group(1))

        for grade in synthesis_grades:
            if grade in self._grade_groups:
                verified_claims.append(f"Grade Group {grade}")
            else:
                potential_hallucinations.append(f"Grade Group {grade} (not in source)")

        # Check percentages in synthesis
        synthesis_pcts = set()
        for match in re.finditer(r'(\d+)\s*%', synthesized_text):
            synthesis_pcts.add(match.group(1))

        for pct in synthesis_pcts:
            if pct in self._percentages:
                verified_claims.append(f"{pct}%")
            elif int(pct) not in [100, 0]:  # 100% and 0% are often generic
                # Check if it's close to any source percentage
                close_match = False
                for source_pct in self._percentages:
                    if abs(int(pct) - int(source_pct)) <= 1:
                        close_match = True
                        break
                if not close_match:
                    potential_hallucinations.append(f"{pct}% (not in source)")

        # Check core counts in synthesis
        for match in re.finditer(r'(\d+)\s*(?:of|/)\s*(\d+)\s*cores?', synthesized_text, re.IGNORECASE):
            core_count = f"{match.group(1)}/{match.group(2)}"
            if core_count in self._core_counts:
                verified_claims.append(f"{core_count} cores")
            else:
                potential_hallucinations.append(f"{core_count} cores (not in source)")

        # Check diagnoses in synthesis
        for diagnosis in ['adenocarcinoma', 'negative for malignancy', 'ASAP', 'HGPIN',
                          'urothelial carcinoma', 'renal cell carcinoma']:
            if diagnosis.lower() in synthesized_text.lower():
                if diagnosis.lower() in [d.lower() for d in self._diagnoses]:
                    verified_claims.append(diagnosis)
                else:
                    # More lenient for diagnosis types - check partial matches
                    partial_match = False
                    for source_diag in self._diagnoses:
                        if diagnosis.lower() in source_diag.lower() or source_diag.lower() in diagnosis.lower():
                            partial_match = True
                            break
                    if not partial_match:
                        potential_hallucinations.append(f"{diagnosis} (not in source)")

        # Calculate confidence score
        total_claims = len(verified_claims) + len(potential_hallucinations)
        if total_claims > 0:
            confidence_score = len(verified_claims) / total_claims
        else:
            confidence_score = 1.0  # No specific claims to verify

        # Generate corrected text if hallucinations found
        corrected_text = None
        if potential_hallucinations:
            corrected_text = self._generate_corrected_text(
                synthesized_text,
                potential_hallucinations
            )

        is_verified = len(potential_hallucinations) == 0 and confidence_score >= 0.8

        return VerificationResult(
            is_verified=is_verified,
            confidence_score=confidence_score,
            verified_claims=verified_claims,
            unverified_claims=unverified_claims,
            potential_hallucinations=potential_hallucinations,
            corrected_text=corrected_text,
            details={
                "source_gleason_scores": list(self._gleason_scores),
                "source_grade_groups": list(self._grade_groups),
                "source_percentages": list(self._percentages),
                "source_core_counts": list(self._core_counts),
                "source_diagnoses": list(self._diagnoses),
            }
        )

    def _generate_corrected_text(
        self,
        original_text: str,
        hallucinations: List[str]
    ) -> str:
        """
        Generate corrected text by removing/flagging hallucinated content.

        Args:
            original_text: Original synthesized text
            hallucinations: List of hallucinated claims

        Returns:
            Corrected text with hallucinations marked
        """
        corrected = original_text

        for hallucination in hallucinations:
            # Extract the specific value
            match = re.search(r'^(.*?)\s*\(not in source\)$', hallucination)
            if match:
                value = match.group(1)
                # Mark the hallucination in the text
                # Pattern to find and mark
                if 'Gleason' in value:
                    gleason_val = value.replace('Gleason ', '')
                    corrected = re.sub(
                        rf'Gleason[\'s]?\s+(?:score\s+)?{re.escape(gleason_val)}',
                        f'[UNVERIFIED: Gleason {gleason_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif 'Grade Group' in value:
                    gg_val = value.replace('Grade Group ', '')
                    corrected = re.sub(
                        rf'Grade\s+Group\s+{re.escape(gg_val)}',
                        f'[UNVERIFIED: Grade Group {gg_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif '%' in value:
                    pct_val = value.replace('%', '')
                    corrected = re.sub(
                        rf'\b{re.escape(pct_val)}\s*%',
                        f'[UNVERIFIED: {pct_val}%]',
                        corrected
                    )
                elif 'cores' in value:
                    cores_val = value.replace(' cores', '')
                    corrected = re.sub(
                        rf'\b{re.escape(cores_val)}\s*(?:of|/)',
                        f'[UNVERIFIED: {cores_val}] of',
                        corrected,
                        flags=re.IGNORECASE
                    )

        return corrected

    def get_verified_pathology(self, synthesized_text: str) -> Tuple[str, VerificationResult]:
        """
        Get verified pathology text with hallucinations removed or flagged.

        Args:
            synthesized_text: LLM-synthesized pathology text

        Returns:
            Tuple of (verified_text, verification_result)
        """
        result = self.verify_synthesis(synthesized_text)

        if result.is_verified:
            return synthesized_text, result
        elif result.corrected_text:
            return result.corrected_text, result
        else:
            return synthesized_text, result

    def get_fact_summary(self) -> Dict:
        """
        Get a summary of all extracted ground truth facts.

        Returns:
            Dictionary summarizing extracted facts
        """
        return {
            "gleason_scores": list(self._gleason_scores),
            "grade_groups": list(self._grade_groups),
            "core_counts": list(self._core_counts),
            "locations": list(self._locations),
            "dates": list(self._dates),
            "diagnoses": list(self._diagnoses),
            "percentages": list(self._percentages),
            "perineural_invasion": self._has_pni,
            "margin_status": self._margin_status,
            "stages": list(self._stages),
            "tumor_sizes": list(self._tumor_sizes),
            "total_facts": len(self.ground_truth_facts),
        }


def verify_pathology_against_source(
    source_document: str,
    synthesized_pathology: str
) -> VerificationResult:
    """
    Convenience function to verify synthesized pathology against source.

    Args:
        source_document: Raw source document
        synthesized_pathology: LLM-synthesized pathology text

    Returns:
        VerificationResult with verification status
    """
    verifier = PathologyFactVerifier()
    verifier.extract_facts_from_source(source_document)
    return verifier.verify_synthesis(synthesized_pathology)
