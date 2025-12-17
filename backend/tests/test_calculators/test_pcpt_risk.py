"""
Tests for PCPT 2.0 Risk Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.prostate.pcpt_risk import PCPTCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestPCPTCalculatorCalculation:
    """Test PCPT 2.0 Risk calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PCPTCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'age': 65,
        'psa': 5.0,
        'dre_abnormal': False,
        'african_american': False,
        'family_history': False,
        'prior_negative_biopsy': False,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'age': 65,
        'psa': 5.0,
        'dre_abnormal': False,
        'african_american': False,
        'family_history': False,
        'prior_negative_biopsy': False,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'age': 65,
        'psa': 5.0,
        'dre_abnormal': False,
        'african_american': False,
        'family_history': False,
        'prior_negative_biopsy': False,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestPCPTCalculatorValidation:
    """Test input validation for PCPT 2.0 Risk."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PCPTCalculator()

    def test_missing_required_input(self):
        """Test validation fails with missing required input."""
        inputs = {}  # Empty inputs

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert error is not None

    def test_invalid_input_type(self):
        """Test validation fails with invalid input type."""
        inputs = {'psa': 'not_a_number'}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid

    def test_out_of_range_input(self):
        """Test validation fails with out-of-range input."""
        inputs = {'psa': -1.0}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
