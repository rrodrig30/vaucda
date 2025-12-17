"""
Tests for PSA Kinetics Calculator.

Validates:
- PSA velocity (PSAV) calculation
- PSA doubling time (PSADT) calculation
- Risk categorization
- Input validation
- Edge cases
"""

import math
import pytest

from calculators.prostate.psa_kinetics import PSAKineticsCalculator


@pytest.mark.calculator
@pytest.mark.unit
class TestPSAKineticsCalculation:
    """Test PSA kinetics calculations."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PSAKineticsCalculator()

    def test_psav_calculation_simple(self):
        """Test simple PSAV calculation."""
        inputs = {
            "psa_values": [2.0, 4.0],
            "time_points_months": [0, 12],
        }

        result = self.calc.calculate(inputs)

        assert result is not None
        assert "psav" in result.result
        # PSAV = (4.0 - 2.0) / 1 year = 2.0 ng/mL/year
        assert result.result["psav"] == pytest.approx(2.0, rel=0.01)

    def test_psav_calculation_multiple_points(self):
        """Test PSAV with multiple PSA measurements."""
        inputs = {
            "psa_values": [6.2, 7.1, 8.5],
            "time_points_months": [0, 6, 12],
        }

        result = self.calc.calculate(inputs)

        # PSAV = (8.5 - 6.2) / 1 year = 2.3 ng/mL/year
        assert result.result["psav"] == pytest.approx(2.3, rel=0.05)

    def test_psadt_calculation(self):
        """Test PSADT calculation using exponential model."""
        inputs = {
            "psa_values": [2.0, 4.0, 8.0],
            "time_points_months": [0, 10, 20],
        }

        result = self.calc.calculate(inputs)

        assert "psadt_months" in result.result
        # PSA doubles every ~10 months
        assert result.result["psadt_months"] == pytest.approx(10.0, rel=0.1)

    def test_psadt_very_short(self):
        """Test PSADT with rapid doubling (aggressive disease)."""
        inputs = {
            "psa_values": [1.0, 2.0, 4.0],
            "time_points_months": [0, 2, 4],
        }

        result = self.calc.calculate(inputs)

        # PSADT should be ~2 months
        assert result.result["psadt_months"] < 3
        assert result.risk_level == "very_high"
        assert "aggressive" in result.interpretation.lower()

    def test_psadt_long(self):
        """Test PSADT with slow progression."""
        inputs = {
            "psa_values": [4.0, 4.5, 5.0],
            "time_points_months": [0, 12, 24],
        }

        result = self.calc.calculate(inputs)

        # PSADT should be long (> 15 months)
        assert result.result["psadt_months"] > 15
        assert result.risk_level in ["low", "very_low"]

    def test_interpretation_high_psav(self):
        """Test interpretation when PSAV > 2.0."""
        inputs = {
            "psa_values": [4.0, 6.5],
            "time_points_months": [0, 12],
        }

        result = self.calc.calculate(inputs)

        assert result.result["psav"] > 2.0
        assert "concerning" in result.interpretation.lower() or "recurrence" in result.interpretation.lower()

    def test_interpretation_moderate_psav(self):
        """Test interpretation when PSAV 0.75-2.0."""
        inputs = {
            "psa_values": [4.0, 5.0],
            "time_points_months": [0, 12],
        }

        result = self.calc.calculate(inputs)

        assert 0.75 < result.result["psav"] < 2.0
        assert "increased" in result.interpretation.lower() or "risk" in result.interpretation.lower()


@pytest.mark.calculator
@pytest.mark.unit
class TestPSAKineticsValidation:
    """Test input validation for PSA kinetics calculator."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PSAKineticsCalculator()

    def test_validate_insufficient_datapoints(self):
        """Test validation fails with < 2 PSA values."""
        inputs = {
            "psa_values": [4.0],
            "time_points_months": [0],
        }

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert "at least 2" in error.lower()

    def test_validate_negative_psa(self):
        """Test validation fails with negative PSA."""
        inputs = {
            "psa_values": [-1.0, 4.0],
            "time_points_months": [0, 12],
        }

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert "negative" in error.lower() or "positive" in error.lower()

    def test_validate_mismatched_lengths(self):
        """Test validation fails when PSA and time arrays don't match."""
        inputs = {
            "psa_values": [4.0, 5.0, 6.0],
            "time_points_months": [0, 12],
        }

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert "match" in error.lower() or "length" in error.lower()

    def test_validate_non_monotonic_time(self):
        """Test validation fails when time points aren't increasing."""
        inputs = {
            "psa_values": [4.0, 5.0, 6.0],
            "time_points_months": [0, 12, 6],  # Not monotonic
        }

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid
        assert "increasing" in error.lower() or "chronological" in error.lower()

    def test_validate_zero_time_interval(self):
        """Test validation fails when time interval is zero."""
        inputs = {
            "psa_values": [4.0, 5.0],
            "time_points_months": [0, 0],
        }

        is_valid, error = self.calc.validate_inputs(inputs)

        assert not is_valid


@pytest.mark.calculator
@pytest.mark.unit
class TestPSAKineticsEdgeCases:
    """Test edge cases for PSA kinetics calculator."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PSAKineticsCalculator()

    def test_stable_psa(self):
        """Test calculation when PSA is stable."""
        inputs = {
            "psa_values": [4.0, 4.0, 4.0],
            "time_points_months": [0, 6, 12],
        }

        result = self.calc.calculate(inputs)

        assert result.result["psav"] == pytest.approx(0.0, abs=0.1)
        # PSADT should be infinity or very large
        assert result.result["psadt_months"] > 100

    def test_decreasing_psa(self):
        """Test calculation when PSA is decreasing."""
        inputs = {
            "psa_values": [8.0, 6.0, 4.0],
            "time_points_months": [0, 6, 12],
        }

        result = self.calc.calculate(inputs)

        # PSAV should be negative
        assert result.result["psav"] < 0
        # PSADT not applicable for decreasing PSA
        assert "declining" in result.interpretation.lower() or "decreasing" in result.interpretation.lower()

    def test_very_high_psa(self):
        """Test calculation with very high PSA values."""
        inputs = {
            "psa_values": [100.0, 150.0, 200.0],
            "time_points_months": [0, 6, 12],
        }

        result = self.calc.calculate(inputs)

        # Should still calculate correctly
        assert result.result["psav"] == pytest.approx(100.0, rel=0.1)

    def test_very_low_psa(self):
        """Test calculation with very low PSA values."""
        inputs = {
            "psa_values": [0.1, 0.15, 0.2],
            "time_points_months": [0, 6, 12],
        }

        result = self.calc.calculate(inputs)

        # Should still calculate correctly
        assert result.result["psav"] == pytest.approx(0.1, rel=0.1)


@pytest.mark.calculator
@pytest.mark.integration
class TestPSAKineticsPublishedExamples:
    """Test against published clinical examples."""

    def setup_method(self):
        """Set up calculator instance."""
        self.calc = PSAKineticsCalculator()

    def test_published_example_1(self):
        """Test Example 1 from D'Amico et al. JAMA 2004."""
        # Patient with biochemical recurrence
        inputs = {
            "psa_values": [0.2, 0.4, 0.8, 1.6],
            "time_points_months": [0, 3, 6, 9],
        }

        result = self.calc.calculate(inputs)

        # PSADT should be ~3 months (aggressive)
        assert 2.5 < result.result["psadt_months"] < 3.5
        assert result.risk_level == "very_high"

    def test_published_example_2(self):
        """Test Example 2 from Freedland et al. JAMA 2005."""
        # Patient with slow progression
        inputs = {
            "psa_values": [1.0, 1.5, 2.0, 2.5],
            "time_points_months": [0, 12, 24, 36],
        }

        result = self.calc.calculate(inputs)

        # PSADT should be ~27 months (indolent) using exponential regression
        assert 25 < result.result["psadt_months"] < 30
        assert result.risk_level in ["low", "intermediate"]
