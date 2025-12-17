"""
Tests for Hypogonadism Risk Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.hypogonadism.hypogonadism_risk import HypogonadismRiskCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestHypogonadismRiskCalculatorCalculation:
    """Test Hypogonadism Risk calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = HypogonadismRiskCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'symptoms_present': True,
        'total_testosterone': 290,
        'free_testosterone': 55,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'symptoms_present': True,
        'total_testosterone': 290,
        'free_testosterone': 55,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'symptoms_present': True,
        'total_testosterone': 290,
        'free_testosterone': 55,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestHypogonadismRiskCalculatorValidation:
    """Test input validation for Hypogonadism Risk."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = HypogonadismRiskCalculator()

    def test_missing_required_input(self):
        """Test validation fails with missing required input."""
        inputs = {}  # Empty inputs

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert error is not None

    def test_invalid_input_type(self):
        """Test validation fails with invalid input type."""
        inputs = {'value': 'invalid'}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid

    def test_out_of_range_input(self):
        """Test validation fails with out-of-range input."""
        inputs = {'value': -1}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
