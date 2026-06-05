"""
HPI Fact Verifier

Eliminates hallucinations in HPI synthesis by:
1. Extracting ground-truth PSA values, lab results, and clinical findings from source documents
2. Verifying synthesized HPI claims against these facts
3. Flagging or removing any claims not supported by source data

This is a CRITICAL SAFETY feature - incorrect clinical values can lead to wrong treatment decisions.

Author: VAUCDA Development Team
Date: February 2026
"""

import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class HPIFactType(Enum):
    """Types of HPI facts that can be extracted and verified."""
    PSA_VALUE = "psa_value"
    GLEASON_SCORE = "gleason_score"
    GRADE_GROUP = "grade_group"
    IPSS_SCORE = "ipss_score"
    CREATININE = "creatinine"
    EGFR = "egfr"
    HEMOGLOBIN = "hemoglobin"
    WBC = "wbc"
    TESTOSTERONE = "testosterone"
    IMAGING_FINDING = "imaging_finding"
    PROCEDURE = "procedure"
    DIAGNOSIS = "diagnosis"


@dataclass
class HPIFact:
    """A single verified HPI fact from source document."""
    fact_type: HPIFactType
    value: str
    normalized_value: str  # Standardized form for comparison
    date: Optional[str] = None
    source_text: str = ""
    confidence: float = 1.0  # 1.0 = deterministic extraction


@dataclass
class HPIVerificationResult:
    """Result of verifying synthesized HPI against source facts."""
    is_verified: bool
    confidence_score: float  # 0.0 - 1.0
    verified_claims: List[str] = field(default_factory=list)
    unverified_claims: List[str] = field(default_factory=list)
    potential_hallucinations: List[str] = field(default_factory=list)
    corrected_text: Optional[str] = None
    details: Dict = field(default_factory=dict)


class HPIFactVerifier:
    """
    Verifies HPI synthesis against deterministically extracted facts.

    Usage:
        verifier = HPIFactVerifier()

        # Extract facts from source document(s)
        verifier.extract_facts_from_source(clinical_document)
        verifier.extract_facts_from_psa_data(psa_curve)
        verifier.extract_facts_from_labs(labs_text)

        # Verify synthesized HPI
        result = verifier.verify_synthesis(synthesized_hpi)

        if not result.is_verified:
            print(f"Potential hallucinations: {result.potential_hallucinations}")
            # Use result.corrected_text if available
    """

    def __init__(self):
        self.ground_truth_facts: List[HPIFact] = []
        self._psa_values: Dict[str, str] = {}  # date -> value
        self._gleason_scores: Set[str] = set()
        self._grade_groups: Set[str] = set()
        self._ipss_scores: Set[str] = set()
        self._creatinine_values: Set[str] = set()
        self._egfr_values: Set[str] = set()
        self._hemoglobin_values: Set[str] = set()
        self._wbc_values: Set[str] = set()
        self._testosterone_values: Set[str] = set()
        self._imaging_findings: Set[str] = set()
        self._procedures: Set[str] = set()
        self._diagnoses: Set[str] = set()

    def reset(self):
        """Clear all extracted facts."""
        self.ground_truth_facts = []
        self._psa_values = {}
        self._gleason_scores = set()
        self._grade_groups = set()
        self._ipss_scores = set()
        self._creatinine_values = set()
        self._egfr_values = set()
        self._hemoglobin_values = set()
        self._wbc_values = set()
        self._testosterone_values = set()
        self._imaging_findings = set()
        self._procedures = set()
        self._diagnoses = set()

    def extract_facts_from_source(self, source_text: str) -> List[HPIFact]:
        """
        Extract all clinical facts deterministically from source document.

        Args:
            source_text: Raw source document text

        Returns:
            List of extracted HPIFact objects
        """
        if not source_text:
            return []

        facts = []

        # Extract PSA values
        facts.extend(self._extract_psa_values(source_text))

        # Extract Gleason scores
        facts.extend(self._extract_gleason_scores(source_text))

        # Extract Grade Groups
        facts.extend(self._extract_grade_groups(source_text))

        # Extract IPSS scores
        facts.extend(self._extract_ipss_scores(source_text))

        # Extract key lab values
        facts.extend(self._extract_creatinine(source_text))
        facts.extend(self._extract_egfr(source_text))
        facts.extend(self._extract_hemoglobin(source_text))
        facts.extend(self._extract_wbc(source_text))
        facts.extend(self._extract_testosterone(source_text))

        # Extract imaging findings
        facts.extend(self._extract_imaging_findings(source_text))

        # Extract procedures
        facts.extend(self._extract_procedures(source_text))

        # Extract diagnoses
        facts.extend(self._extract_diagnoses(source_text))

        self.ground_truth_facts.extend(facts)
        return facts

    def extract_facts_from_psa_data(self, psa_data: str) -> List[HPIFact]:
        """
        Extract PSA facts specifically from PSA curve/data.

        Args:
            psa_data: PSA curve text (e.g., "[r] Jan 15, 2025 08:00    4.52 H")

        Returns:
            List of extracted PSA facts
        """
        if not psa_data:
            return []

        facts = []

        # Pattern for PSA curve format: [r] DATE TIME VALUE [H]
        # Handles: [r] Jan 15, 2025 08:00    4.52 H
        patterns = [
            r'\[r\]\s*([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\s*(?:\d{2}:\d{2})?\s+(\d+\.?\d*)\s*H?',
            r'(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:\d{2}:\d{2})?\s+PSA[:\s]+(\d+\.?\d*)',
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?\s*[-–]\s*([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})',
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, psa_data, re.IGNORECASE):
                if len(match.groups()) >= 2:
                    date = match.group(1)
                    value = match.group(2)
                else:
                    date = None
                    value = match.group(1)

                # Normalize PSA value
                try:
                    normalized = f"{float(value):.2f}"
                except ValueError:
                    normalized = value

                # Skip impossible values
                try:
                    if float(value) > 10000:
                        continue
                except ValueError:
                    continue

                self._psa_values[date or 'unknown'] = normalized

                facts.append(HPIFact(
                    fact_type=HPIFactType.PSA_VALUE,
                    value=value,
                    normalized_value=normalized,
                    date=date,
                    source_text=match.group(0)
                ))

        self.ground_truth_facts.extend(facts)
        return facts

    def extract_facts_from_labs(self, labs_text: str) -> List[HPIFact]:
        """
        Extract lab value facts from labs section.

        Args:
            labs_text: Labs section text

        Returns:
            List of extracted lab facts
        """
        if not labs_text:
            return []

        facts = []

        # Extract creatinine, eGFR, hemoglobin, WBC, testosterone
        facts.extend(self._extract_creatinine(labs_text))
        facts.extend(self._extract_egfr(labs_text))
        facts.extend(self._extract_hemoglobin(labs_text))
        facts.extend(self._extract_wbc(labs_text))
        facts.extend(self._extract_testosterone(labs_text))

        self.ground_truth_facts.extend(facts)
        return facts

    def _extract_psa_values(self, text: str) -> List[HPIFact]:
        """Extract PSA values from text."""
        facts = []

        patterns = [
            # VA tabular format
            r'PSA(?:,?\s*(?:TOTAL|SERUM|SCREENING))?\s+(\d+\.?\d*)\s*(?:ng/mL)?',
            # Human readable
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?',
            # With date
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?\s*[-–\(]\s*([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})',
            r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL)?\s*[-–\(]\s*(\d{1,2}/\d{1,2}/\d{2,4})',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)

                # Skip impossible values
                try:
                    if float(value) > 10000:
                        continue
                except ValueError:
                    continue

                normalized = f"{float(value):.2f}"
                date = match.group(2) if len(match.groups()) > 1 else None

                self._psa_values[date or 'unknown'] = normalized

                facts.append(HPIFact(
                    fact_type=HPIFactType.PSA_VALUE,
                    value=value,
                    normalized_value=normalized,
                    date=date,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_gleason_scores(self, text: str) -> List[HPIFact]:
        """Extract Gleason scores."""
        facts = []

        patterns = [
            r'GLEASON[\'S]?\s+(?:SCORE\s+)?(\d)\s*\+\s*(\d)(?:\s*=\s*(\d+))?',
            r'GLEASON[\'S]?\s+GRADE\s+(\d)\s*\+\s*(\d)',
            r'(\d)\s*\+\s*(\d)\s*=\s*(\d+)/10',
            r'GRADE\s+GROUP\s+\d+\s*\((\d)\s*\+\s*(\d)\)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                primary = match.group(1)
                secondary = match.group(2)
                gleason = f"{primary}+{secondary}"
                self._gleason_scores.add(gleason)

                facts.append(HPIFact(
                    fact_type=HPIFactType.GLEASON_SCORE,
                    value=gleason,
                    normalized_value=gleason,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_grade_groups(self, text: str) -> List[HPIFact]:
        """Extract Grade Groups."""
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

                facts.append(HPIFact(
                    fact_type=HPIFactType.GRADE_GROUP,
                    value=grade_group,
                    normalized_value=grade_group,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_ipss_scores(self, text: str) -> List[HPIFact]:
        """Extract IPSS scores."""
        facts = []

        patterns = [
            r'IPSS[:\s]+(\d+)',
            r'I-PSS[:\s]+(\d+)',
            r'IPSS\s+(?:SCORE\s+)?(?:OF\s+)?(\d+)',
            r'IPSS\s*=\s*(\d+)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                score = match.group(1)
                # IPSS should be 0-35
                try:
                    if int(score) > 35:
                        continue
                except ValueError:
                    continue

                self._ipss_scores.add(score)

                facts.append(HPIFact(
                    fact_type=HPIFactType.IPSS_SCORE,
                    value=score,
                    normalized_value=score,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_creatinine(self, text: str) -> List[HPIFact]:
        """Extract creatinine values."""
        facts = []

        patterns = [
            r'CREATININE[:\s]+(\d+\.?\d*)\s*(?:mg/dL)?',
            r'CREAT[:\s]+(\d+\.?\d*)\s*(?:mg/dL)?',
            r'CR[:\s]+(\d+\.?\d*)\s*(?:mg/dL)?(?!\s*\d)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                # Creatinine sanity check: 0.1-20.0
                try:
                    if not (0.1 <= float(value) <= 20.0):
                        continue
                except ValueError:
                    continue

                self._creatinine_values.add(value)

                facts.append(HPIFact(
                    fact_type=HPIFactType.CREATININE,
                    value=value,
                    normalized_value=value,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_egfr(self, text: str) -> List[HPIFact]:
        """Extract eGFR values."""
        facts = []

        patterns = [
            r'(?:E?GFR|EGFR)[:\s]+[>]?(\d+)',
            r'(?:ESTIMATED\s+)?GFR[:\s]+[>]?(\d+)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                # eGFR sanity check: 1-200
                try:
                    if not (1 <= int(value) <= 200):
                        continue
                except ValueError:
                    continue

                self._egfr_values.add(value)

                facts.append(HPIFact(
                    fact_type=HPIFactType.EGFR,
                    value=value,
                    normalized_value=value,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_hemoglobin(self, text: str) -> List[HPIFact]:
        """Extract hemoglobin values."""
        facts = []

        patterns = [
            r'(?:HEMOGLOBIN|HGB|HB)[:\s]+(\d+\.?\d*)\s*(?:g/dL)?',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                # Hemoglobin sanity check: 3-25
                try:
                    if not (3.0 <= float(value) <= 25.0):
                        continue
                except ValueError:
                    continue

                self._hemoglobin_values.add(value)

                facts.append(HPIFact(
                    fact_type=HPIFactType.HEMOGLOBIN,
                    value=value,
                    normalized_value=value,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_wbc(self, text: str) -> List[HPIFact]:
        """Extract WBC values."""
        facts = []

        patterns = [
            r'WBC[:\s]+(\d+\.?\d*)\s*(?:K/uL|x10\^9)?',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                # WBC sanity check: 0.5-100
                try:
                    if not (0.5 <= float(value) <= 100.0):
                        continue
                except ValueError:
                    continue

                self._wbc_values.add(value)

                facts.append(HPIFact(
                    fact_type=HPIFactType.WBC,
                    value=value,
                    normalized_value=value,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_testosterone(self, text: str) -> List[HPIFact]:
        """Extract testosterone values."""
        facts = []

        patterns = [
            r'TESTOSTERONE[,\s]*(?:SERUM\s*)?(?:TOTAL)?[:\s]+(\d+)\s*(?:ng/dL)?',
            r'TOTAL\s+TESTOSTERONE[:\s]+(\d+)\s*(?:ng/dL)?',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                # Testosterone sanity check: 1-2000 ng/dL
                try:
                    if not (1 <= int(value) <= 2000):
                        continue
                except ValueError:
                    continue

                self._testosterone_values.add(value)

                facts.append(HPIFact(
                    fact_type=HPIFactType.TESTOSTERONE,
                    value=value,
                    normalized_value=value,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_imaging_findings(self, text: str) -> List[HPIFact]:
        """Extract key imaging findings."""
        facts = []

        # Key imaging findings to capture
        finding_patterns = [
            (r'PROSTATE\s+(?:VOLUME|SIZE)[:\s]+(\d+\.?\d*)\s*(?:cc|mL|cm3)?', 'prostate_volume'),
            (r'(?:KIDNEY|RENAL)\s+(?:CYST|MASS)[:\s]+(\d+\.?\d*)\s*(?:cm|mm)?', 'renal_finding'),
            (r'HYDRONEPHROSIS', 'hydronephrosis'),
            (r'(?:BLADDER\s+)?(?:STONE|CALCULUS|CALCULI)', 'stone'),
            (r'(?:METASTATIC|METASTASES|METS)', 'metastases'),
            (r'BONE\s+(?:LESION|METASTASES|METS)', 'bone_lesion'),
        ]

        for pattern, finding_type in finding_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                finding = match.group(0)
                self._imaging_findings.add(finding.lower())

                facts.append(HPIFact(
                    fact_type=HPIFactType.IMAGING_FINDING,
                    value=finding,
                    normalized_value=finding.lower(),
                    source_text=match.group(0)
                ))

        return facts

    def _extract_procedures(self, text: str) -> List[HPIFact]:
        """Extract procedures mentioned."""
        facts = []

        procedure_patterns = [
            r'PROSTATE\s+BIOPSY',
            r'TRANSRECTAL\s+(?:ULTRASOUND\s+)?BIOPSY',
            r'TRUS\s+BIOPSY',
            r'MRI[-\s]?FUSION\s+BIOPSY',
            r'CYSTOSCOPY',
            r'TURP',
            r'TURBT',
            r'RADICAL\s+PROSTATECTOMY',
            r'ROBOTIC\s+PROSTATECTOMY',
            r'NEPHRECTOMY',
            r'ORCHIECTOMY',
            r'VASECTOMY',
            r'(?:URS|URETEROSCOPY)',
            r'LITHOTRIPSY',
            r'ESWL',
        ]

        for pattern in procedure_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                match = re.search(pattern, text, re.IGNORECASE)
                procedure = match.group(0).lower()
                self._procedures.add(procedure)

                facts.append(HPIFact(
                    fact_type=HPIFactType.PROCEDURE,
                    value=procedure,
                    normalized_value=procedure,
                    source_text=match.group(0)
                ))

        return facts

    def _extract_diagnoses(self, text: str) -> List[HPIFact]:
        """Extract diagnoses mentioned."""
        facts = []

        diagnosis_patterns = [
            (r'PROSTATIC?\s+ADENOCARCINOMA', 'prostate cancer'),
            (r'PROSTATE\s+CANCER', 'prostate cancer'),
            (r'(?:BENIGN\s+PROSTATIC\s+)?(?:HYPERPLASIA|HYPERTROPHY)', 'BPH'),
            (r'BPH', 'BPH'),
            (r'LUTS', 'LUTS'),
            (r'OVERACTIVE\s+BLADDER', 'OAB'),
            (r'OAB', 'OAB'),
            (r'URINARY\s+(?:TRACT\s+)?INFECTION', 'UTI'),
            (r'UTI', 'UTI'),
            (r'HEMATURIA', 'hematuria'),
            (r'KIDNEY\s+STONE', 'nephrolithiasis'),
            (r'NEPHROLITHIASIS', 'nephrolithiasis'),
            (r'UROLITHIASIS', 'urolithiasis'),
            (r'ERECTILE\s+DYSFUNCTION', 'ED'),
            (r'HYPOGONADISM', 'hypogonadism'),
            (r'LOW\s+TESTOSTERONE', 'hypogonadism'),
        ]

        for pattern, normalized in diagnosis_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                match = re.search(pattern, text, re.IGNORECASE)
                self._diagnoses.add(normalized)

                facts.append(HPIFact(
                    fact_type=HPIFactType.DIAGNOSIS,
                    value=normalized,
                    normalized_value=normalized,
                    source_text=match.group(0)
                ))

        return facts

    def verify_synthesis(self, synthesized_text: str) -> HPIVerificationResult:
        """
        Verify synthesized HPI against ground truth facts.

        Args:
            synthesized_text: LLM-synthesized HPI text

        Returns:
            HPIVerificationResult with verification status and details
        """
        if not self.ground_truth_facts:
            return HPIVerificationResult(
                is_verified=False,
                confidence_score=0.0,
                details={"error": "No ground truth facts extracted"}
            )

        verified_claims = []
        unverified_claims = []
        potential_hallucinations = []

        # Check PSA values in synthesis
        synthesis_psa_values = set()
        for pattern in [r'PSA[:\s]+(\d+\.?\d*)', r'PSA\s+(?:of\s+)?(\d+\.?\d*)']:
            for match in re.finditer(pattern, synthesized_text, re.IGNORECASE):
                value = match.group(1)
                try:
                    normalized = f"{float(value):.2f}"
                    synthesis_psa_values.add(normalized)
                except ValueError:
                    continue

        # Get all ground truth PSA values
        ground_truth_psa = set(self._psa_values.values())

        for psa in synthesis_psa_values:
            # Check if this PSA value is close to any ground truth
            matched = False
            for gt_psa in ground_truth_psa:
                try:
                    if abs(float(psa) - float(gt_psa)) < 0.1:
                        matched = True
                        verified_claims.append(f"PSA {psa}")
                        break
                except ValueError:
                    continue

            if not matched and float(psa) > 0:
                potential_hallucinations.append(f"PSA {psa} (not in source)")

        # Check Gleason scores
        for match in re.finditer(r'GLEASON[\'S]?\s+(?:SCORE\s+)?(\d)\s*\+\s*(\d)', synthesized_text, re.IGNORECASE):
            gleason = f"{match.group(1)}+{match.group(2)}"
            if gleason in self._gleason_scores:
                verified_claims.append(f"Gleason {gleason}")
            else:
                potential_hallucinations.append(f"Gleason {gleason} (not in source)")

        # Check Grade Groups
        for match in re.finditer(r'GRADE\s+GROUP\s+(\d)', synthesized_text, re.IGNORECASE):
            gg = match.group(1)
            if gg in self._grade_groups:
                verified_claims.append(f"Grade Group {gg}")
            else:
                potential_hallucinations.append(f"Grade Group {gg} (not in source)")

        # Check IPSS scores
        for match in re.finditer(r'IPSS[:\s]+(\d+)', synthesized_text, re.IGNORECASE):
            score = match.group(1)
            if score in self._ipss_scores:
                verified_claims.append(f"IPSS {score}")
            else:
                potential_hallucinations.append(f"IPSS {score} (not in source)")

        # Check creatinine values
        for match in re.finditer(r'CREATININE[:\s]+(\d+\.?\d*)', synthesized_text, re.IGNORECASE):
            value = match.group(1)
            if value in self._creatinine_values:
                verified_claims.append(f"Creatinine {value}")
            else:
                # Check if close
                close = any(abs(float(value) - float(gt)) < 0.1 for gt in self._creatinine_values if gt)
                if not close:
                    potential_hallucinations.append(f"Creatinine {value} (not in source)")

        # Check testosterone values
        for match in re.finditer(r'TESTOSTERONE[:\s]+(\d+)', synthesized_text, re.IGNORECASE):
            value = match.group(1)
            if value in self._testosterone_values:
                verified_claims.append(f"Testosterone {value}")
            else:
                potential_hallucinations.append(f"Testosterone {value} (not in source)")

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

        return HPIVerificationResult(
            is_verified=is_verified,
            confidence_score=confidence_score,
            verified_claims=verified_claims,
            unverified_claims=unverified_claims,
            potential_hallucinations=potential_hallucinations,
            corrected_text=corrected_text,
            details={
                "source_psa_values": list(self._psa_values.values()),
                "source_gleason_scores": list(self._gleason_scores),
                "source_grade_groups": list(self._grade_groups),
                "source_ipss_scores": list(self._ipss_scores),
                "source_creatinine": list(self._creatinine_values),
                "source_testosterone": list(self._testosterone_values),
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
                claim = match.group(1)

                if claim.startswith('PSA '):
                    psa_val = claim.replace('PSA ', '')
                    # Handle both "12.50" and "12.5" formats. Dedupe so
                    # the for-loop doesn't run with the same pattern
                    # twice — when it did, the second iteration matched
                    # the already-wrapped "[UNVERIFIED PSA: X]" and
                    # produced "[UNVERIFIED [UNVERIFIED PSA: X]]".
                    psa_val_stripped = psa_val.rstrip('0').rstrip('.')
                    psa_patterns = [psa_val, psa_val_stripped]
                    if '.' not in psa_val_stripped:
                        psa_patterns.append(psa_val_stripped + '.0')
                    psa_patterns = list(dict.fromkeys(psa_patterns))

                    for pv in psa_patterns:
                        # Skip if this value is already wrapped by a
                        # prior iteration — negative lookbehind for
                        # "[UNVERIFIED PSA: " immediately before the
                        # match guards against re-wrapping.
                        corrected = re.sub(
                            rf'(?<!\[UNVERIFIED PSA: )PSA[:\s]+{re.escape(pv)}(?:\s*ng/mL)?',
                            f'[UNVERIFIED PSA: {pv}]',
                            corrected,
                            flags=re.IGNORECASE
                        )
                        # "PSA of X" format — same guard.
                        corrected = re.sub(
                            rf'(?<!\[UNVERIFIED PSA: )PSA\s+(?:of\s+)?{re.escape(pv)}',
                            f'[UNVERIFIED PSA: {pv}]',
                            corrected,
                            flags=re.IGNORECASE
                        )
                elif claim.startswith('Gleason '):
                    gleason_val = claim.replace('Gleason ', '')
                    corrected = re.sub(
                        rf'Gleason[\'s]?\s+(?:score\s+)?{re.escape(gleason_val)}',
                        f'[UNVERIFIED: Gleason {gleason_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif claim.startswith('Grade Group '):
                    gg_val = claim.replace('Grade Group ', '')
                    corrected = re.sub(
                        rf'Grade\s+Group\s+{re.escape(gg_val)}',
                        f'[UNVERIFIED: Grade Group {gg_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif claim.startswith('IPSS '):
                    ipss_val = claim.replace('IPSS ', '')
                    corrected = re.sub(
                        rf'IPSS[:\s]+{re.escape(ipss_val)}',
                        f'[UNVERIFIED: IPSS {ipss_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif claim.startswith('Creatinine '):
                    cr_val = claim.replace('Creatinine ', '')
                    corrected = re.sub(
                        rf'Creatinine[:\s]+{re.escape(cr_val)}',
                        f'[UNVERIFIED: Creatinine {cr_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )
                elif claim.startswith('Testosterone '):
                    t_val = claim.replace('Testosterone ', '')
                    corrected = re.sub(
                        rf'Testosterone[:\s]+{re.escape(t_val)}',
                        f'[UNVERIFIED: Testosterone {t_val}]',
                        corrected,
                        flags=re.IGNORECASE
                    )

        return corrected

    def get_verified_hpi(self, synthesized_text: str) -> Tuple[str, HPIVerificationResult]:
        """
        Get verified HPI text with hallucinations removed or flagged.

        Args:
            synthesized_text: LLM-synthesized HPI text

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
            "psa_values": list(self._psa_values.values()),
            "gleason_scores": list(self._gleason_scores),
            "grade_groups": list(self._grade_groups),
            "ipss_scores": list(self._ipss_scores),
            "creatinine_values": list(self._creatinine_values),
            "egfr_values": list(self._egfr_values),
            "hemoglobin_values": list(self._hemoglobin_values),
            "wbc_values": list(self._wbc_values),
            "testosterone_values": list(self._testosterone_values),
            "imaging_findings": list(self._imaging_findings),
            "procedures": list(self._procedures),
            "diagnoses": list(self._diagnoses),
            "total_facts": len(self.ground_truth_facts),
        }


def verify_hpi_against_source(
    source_documents: List[str],
    psa_data: Optional[str],
    labs_data: Optional[str],
    synthesized_hpi: str
) -> HPIVerificationResult:
    """
    Convenience function to verify synthesized HPI against source.

    Args:
        source_documents: List of raw source documents
        psa_data: PSA curve/data
        labs_data: Labs section text
        synthesized_hpi: LLM-synthesized HPI text

    Returns:
        HPIVerificationResult with verification status
    """
    verifier = HPIFactVerifier()

    for doc in source_documents:
        verifier.extract_facts_from_source(doc)

    if psa_data:
        verifier.extract_facts_from_psa_data(psa_data)

    if labs_data:
        verifier.extract_facts_from_labs(labs_data)

    return verifier.verify_synthesis(synthesized_hpi)
