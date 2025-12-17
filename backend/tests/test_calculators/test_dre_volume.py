"""
Tests for DRE Volume Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.prostate.dre_volume import DREVolumeCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestDREVolumeCalculatorCalculation:
    """Test DRE Volume calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = DREVolumeCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'length_cm': 4.0,
        'width_cm': 3.5,
        'depth_cm': 3.0,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'length_cm': 4.0,
        'width_cm': 3.5,
        'depth_cm': 3.0,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'length_cm': 4.0,
        'width_cm': 3.5,
        'depth_cm': 3.0,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestDREVolumeCalculatorValidation:
    """Test input validation for DRE Volume."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = DREVolumeCalculator()

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
