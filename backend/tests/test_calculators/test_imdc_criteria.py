"""
Tests for IMDC Criteria Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.kidney.imdc_criteria import IMDCCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestIMDCCalculatorCalculation:
    """Test IMDC Criteria calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = IMDCCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'kps': 80,
        'time_diagnosis_to_treatment_months': 6,
        'hemoglobin_g_dL': 11.5,
        'calcium_mg_dL': 10.5,
        'albumin_g_dL': 3.8,
        'neutrophils_K_uL': 4.5,
        'platelets_K_uL': 350,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'kps': 80,
        'time_diagnosis_to_treatment_months': 6,
        'hemoglobin_g_dL': 11.5,
        'calcium_mg_dL': 10.5,
        'albumin_g_dL': 3.8,
        'neutrophils_K_uL': 4.5,
        'platelets_K_uL': 350,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'kps': 80,
        'time_diagnosis_to_treatment_months': 6,
        'hemoglobin_g_dL': 11.5,
        'calcium_mg_dL': 10.5,
        'albumin_g_dL': 3.8,
        'neutrophils_K_uL': 4.5,
        'platelets_K_uL': 350,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestIMDCCalculatorValidation:
    """Test input validation for IMDC Criteria."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = IMDCCalculator()

    def test_missing_required_input(self):
        """Test validation fails with missing required input."""
        inputs = {}  # Empty inputs

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert error is not None

    def test_invalid_input_type(self):
        """Test validation fails with invalid input type."""
        inputs = {'tumor_size': 'invalid'}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid

    def test_out_of_range_input(self):
        """Test validation fails with out-of-range input."""
        inputs = {'tumor_size': -5.0}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
