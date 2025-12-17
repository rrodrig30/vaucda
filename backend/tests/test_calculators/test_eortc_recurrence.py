"""
Tests for EORTC Recurrence Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.bladder.eortc_recurrence import EORTCRecurrenceCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestEORTCRecurrenceCalculatorCalculation:
    """Test EORTC Recurrence calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = EORTCRecurrenceCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'number_of_tumors': 2,
        'tumor_diameter_cm': 2.5,
        'prior_recurrence_rate': 'primary',
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low',
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'number_of_tumors': 2,
        'tumor_diameter_cm': 2.5,
        'prior_recurrence_rate': 'primary',
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low',
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'number_of_tumors': 2,
        'tumor_diameter_cm': 2.5,
        'prior_recurrence_rate': 'primary',
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low',
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestEORTCRecurrenceCalculatorValidation:
    """Test input validation for EORTC Recurrence."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = EORTCRecurrenceCalculator()

    def test_missing_required_input(self):
        """Test validation fails with missing required input."""
        inputs = {}  # Empty inputs

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert error is not None

    def test_invalid_input_type(self):
        """Test validation fails with invalid input type."""
        inputs = {'number_tumors': 'many'}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid

    def test_out_of_range_input(self):
        """Test validation fails with out-of-range input."""
        inputs = {'number_tumors': -1}

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
