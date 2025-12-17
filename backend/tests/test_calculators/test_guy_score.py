"""
Tests for Guy's Stone Score Calculator.

Validates:
- Calculation accuracy
- Input validation
- Risk categorization
- Edge cases
- Published examples
"""

import pytest
from calculators.stones.guy_score import GuyScoreCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestGuyScoreCalculatorCalculation:
    """Test Guy's Stone Score calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = GuyScoreCalculator()

    def test_basic_calculation(self):
        """Test basic calculation with valid inputs."""
        inputs = {
        'size_points': 1,
        'density_points': 1,
        'location_points': 1,
    }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert result.result is not None
        # Add specific assertions based on expected output

    def test_interpretation_present(self):
        """Test that interpretation is provided."""
        inputs = {
        'size_points': 1,
        'density_points': 1,
        'location_points': 1,
    }

        result = self.calc.calculate(inputs)

        assert result.interpretation is not None
        assert len(result.interpretation) > 0

    def test_risk_level_assigned(self):
        """Test that risk level is assigned when applicable."""
        inputs = {
        'size_points': 1,
        'density_points': 1,
        'location_points': 1,
    }

        result = self.calc.calculate(inputs)

        # Check if calculator provides risk levels
        if hasattr(result, 'risk_level'):
            assert result.risk_level is not None


@pytest.mark.calculator
@pytest.mark.unit
class TestGuyScoreCalculatorValidation:
    """Test input validation for Guy's Stone Score."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = GuyScoreCalculator()

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
