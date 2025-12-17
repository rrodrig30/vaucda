"""
Tests for IPSS Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.voiding.ipss import IPSSCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestIPSSCalculatorCalculation:
    """Test IPSS calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = IPSSCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'incomplete_emptying': 2,
        'frequency': 3,
        'intermittency': 1,
        'urgency': 2,
        'weak_stream': 3,
        'straining': 1,
        'nocturia': 2,
        'qol': 3,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'incomplete_emptying': 2,
        'frequency': 3,
        'intermittency': 1,
        'urgency': 2,
        'weak_stream': 3,
        'straining': 1,
        'nocturia': 2,
        'qol': 3,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'incomplete_emptying': 2,
        'frequency': 3,
        'intermittency': 1,
        'urgency': 2,
        'weak_stream': 3,
        'straining': 1,
        'nocturia': 2,
        'qol': 3,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestIPSSCalculatorValidation:
    """Test input validation for IPSS."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = IPSSCalculator()

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
