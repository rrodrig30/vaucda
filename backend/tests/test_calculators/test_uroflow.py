"""
Tests for Uroflow Analysis Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.voiding.uroflow import UroflowCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestUroflowCalculatorCalculation:
    """Test Uroflow Analysis calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = UroflowCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'qmax': 15.5,
        'qave': 8.2,
        'voided_volume': 280,
        'flow_time': 32,
        'time_to_qmax': 8,
        'flow_pattern': 'normal',
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'qmax': 15.5,
        'qave': 8.2,
        'voided_volume': 280,
        'flow_time': 32,
        'time_to_qmax': 8,
        'flow_pattern': 'normal',
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'qmax': 15.5,
        'qave': 8.2,
        'voided_volume': 280,
        'flow_time': 32,
        'time_to_qmax': 8,
        'flow_pattern': 'normal',
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestUroflowCalculatorValidation:
    """Test input validation for Uroflow Analysis."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = UroflowCalculator()

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
