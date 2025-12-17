"""
Comprehensive Validation Framework for Clinical Data Extraction

Validates extracted clinical data against:
- Data type and format requirements
- Clinical plausibility checks
- Completeness metrics
- Quality assurance standards
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    field: str
    value: Any
    error_message: Optional[str] = None
    severity: str = "error"  # "error", "warning", "info"


class ExtractionValidator:
    """Validates extracted clinical data."""

    def __init__(self):
        """Initialize the validator."""
        self.validation_rules = self._build_validation_rules()

    def _build_validation_rules(self) -> Dict[str, Dict]:
        """Build validation rules for clinical fields."""
        return {
            'psa': {
                'type': float,
                'min': 0,
                'max': 1000,  # Realistic PSA range
                'pattern': r'^\d+\.?\d*$'
            },
            'age': {
                'type': int,
                'min': 18,
                'max': 150,
                'pattern': r'^\d+$'
            },
            'creatinine': {
                'type': float,
                'min': 0.1,
                'max': 20,
                'pattern': r'^\d+\.?\d*$'
            },
            'hemoglobin': {
                'type': float,
                'min': 5,
                'max': 20,
                'pattern': r'^\d+\.?\d*$'
            },
            'wbc': {
                'type': float,
                'min': 0.5,
                'max': 50,
                'pattern': r'^\d+\.?\d*$'
            },
            'platelets': {
                'type': int,
                'min': 10,
                'max': 1000,
                'pattern': r'^\d+$'
            },
            'blood_pressure': {
                'type': str,
                'pattern': r'^\d{2,3}/\d{2,3}$'
            },
            'heart_rate': {
                'type': int,
                'min': 30,
                'max': 200,
                'pattern': r'^\d+$'
            },
            'temperature': {
                'type': float,
                'min': 35,
                'max': 42,
                'pattern': r'^\d+\.?\d*$'
            },
            'ipss_score': {
                'type': int,
                'min': 0,
                'max': 35,
                'pattern': r'^\d+$'
            }
        }

    def validate_field(
        self,
        field_name: str,
        value: Any,
        strict: bool = True
    ) -> ValidationResult:
        """
        Validate a single field.

        Args:
            field_name: Name of the field
            value: Value to validate
            strict: If True, raise on invalid; if False, return warning

        Returns:
            ValidationResult object
        """
        if not value and value != 0:  # Allow zero values
            return ValidationResult(
                is_valid=False,
                field=field_name,
                value=value,
                error_message=f"{field_name} is empty or None",
                severity="warning"
            )

        if field_name not in self.validation_rules:
            # No specific rules for this field - accept
            return ValidationResult(
                is_valid=True,
                field=field_name,
                value=value
            )

        rules = self.validation_rules[field_name]

        # Check pattern if defined
        if 'pattern' in rules:
            if not re.match(rules['pattern'], str(value)):
                return ValidationResult(
                    is_valid=False,
                    field=field_name,
                    value=value,
                    error_message=f"{field_name} format invalid: {value}",
                    severity="error" if strict else "warning"
                )

        # Try to convert to expected type
        try:
            if rules.get('type') == float:
                converted = float(value)
            elif rules.get('type') == int:
                converted = int(value)
            else:
                converted = value

            # Check numeric bounds
            if 'min' in rules and converted < rules['min']:
                return ValidationResult(
                    is_valid=False,
                    field=field_name,
                    value=value,
                    error_message=f"{field_name} below minimum ({rules['min']}): {value}",
                    severity="warning"
                )

            if 'max' in rules and converted > rules['max']:
                return ValidationResult(
                    is_valid=False,
                    field=field_name,
                    value=value,
                    error_message=f"{field_name} above maximum ({rules['max']}): {value}",
                    severity="warning"
                )

            return ValidationResult(
                is_valid=True,
                field=field_name,
                value=value
            )

        except (ValueError, TypeError) as e:
            return ValidationResult(
                is_valid=False,
                field=field_name,
                value=value,
                error_message=f"{field_name} type conversion failed: {str(e)}",
                severity="error"
            )

    def validate_extraction(
        self,
        extracted_data: Dict[str, Any],
        strict: bool = False
    ) -> Tuple[bool, List[ValidationResult]]:
        """
        Validate entire extraction.

        Args:
            extracted_data: Dictionary of extracted clinical data
            strict: If True, fail on any error; if False, collect warnings

        Returns:
            Tuple of (is_valid, list of validation results)
        """
        results = []
        has_errors = False

        for field_name, value in extracted_data.items():
            result = self.validate_field(field_name, value, strict=strict)
            results.append(result)

            if not result.is_valid and result.severity == "error":
                has_errors = True

        # Log results
        for result in results:
            if not result.is_valid:
                log_func = logger.error if result.severity == "error" else logger.warning
                log_func(f"Validation failed for {result.field}: {result.error_message}")

        return not has_errors, results

    def check_completeness(
        self,
        extracted_data: Dict[str, Any],
        required_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Check extraction completeness.

        Args:
            extracted_data: Dictionary of extracted data
            required_fields: Optional list of required fields

        Returns:
            Dict with completeness metrics
        """
        total_fields = len(extracted_data)
        present_fields = sum(1 for v in extracted_data.values() if v is not None and v != "")

        if required_fields:
            missing_required = [f for f in required_fields if not extracted_data.get(f)]
        else:
            missing_required = []

        completeness_percent = (present_fields / total_fields * 100) if total_fields > 0 else 0

        return {
            'total_fields': total_fields,
            'present_fields': present_fields,
            'completeness_percent': round(completeness_percent, 2),
            'missing_required': missing_required,
            'is_complete': missing_required == []
        }

    def validate_note_structure(self, note: str) -> Dict[str, Any]:
        """
        Validate note structure and required sections.

        Args:
            note: Generated clinical note

        Returns:
            Dict with structure validation results
        """
        required_sections = [
            'CC:',
            'HPI:',
            'PHYSICAL EXAM:',
            'MEDICATIONS:',
            'ALLERGIES:',
            'ASSESSMENT:'
        ]

        found_sections = []
        missing_sections = []

        for section in required_sections:
            if section in note:
                found_sections.append(section)
            else:
                missing_sections.append(section)

        # Check for placeholder text
        placeholder_patterns = [
            r'Not documented',
            r'Not documented in clinical data',
            r'\[ERROR:',
            r'PLACEHOLDER'
        ]

        placeholders_found = []
        for pattern in placeholder_patterns:
            matches = re.findall(pattern, note, re.IGNORECASE)
            if matches:
                placeholders_found.extend(matches)

        return {
            'total_sections': len(required_sections),
            'found_sections': len(found_sections),
            'missing_sections': missing_sections,
            'placeholders_found': len(set(placeholders_found)),
            'is_valid_structure': len(missing_sections) == 0,
            'has_placeholders': len(placeholders_found) > 0,
            'note_length': len(note)
        }

    def validate_calculator_inputs(
        self,
        calculator_name: str,
        inputs: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Validate inputs for a specific calculator.

        Args:
            calculator_name: Name of calculator
            inputs: Calculator input parameters

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic validation - real implementation would check per-calculator requirements
        if not inputs:
            return False, f"{calculator_name}: No inputs provided"

        # Check for required numeric fields
        numeric_fields = {k: v for k, v in inputs.items() if isinstance(v, (int, float))}
        if not numeric_fields:
            return False, f"{calculator_name}: No numeric inputs found"

        return True, ""


def get_extraction_validator() -> ExtractionValidator:
    """Get singleton validator instance."""
    return ExtractionValidator()
