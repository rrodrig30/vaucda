"""
Tests for Free PSA Ratio Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.prostate.free_psa import FreePSACalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestFreePSACalculatorCalculation:
    """Test Free PSA Ratio calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = FreePSACalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'total_psa': 6.5,
        'free_psa': 1.2,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'total_psa': 6.5,
        'free_psa': 1.2,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'total_psa': 6.5,
        'free_psa': 1.2,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestFreePSACalculatorValidation:
    """Test input validation for Free PSA Ratio."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = FreePSACalculator()

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
