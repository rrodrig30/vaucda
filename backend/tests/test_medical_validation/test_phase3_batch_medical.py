"""Medical validation tests for Phase 3 remaining calculators (UDI6/IIQ7, PFDI, ICIQ, POP-Q)."""

import pytest
from calculators.female.udi6_iiq7 import UDI6IIQ7Calculator
from calculators.female.pfdi import PFDICalculator
from calculators.voiding.iciq import ICIQCalculator
from calculators.female.popq import POPQCalculator


class TestUDI6IIQ7Medical:
    """Validate UDI6/IIQ7 incontinence impact questionnaire."""

    def setup_method(self):
        self.calc = UDI6IIQ7Calculator()

    def test_udi6_minimal_symptoms(self):
        """Test minimal stress incontinence symptoms."""
        inputs = {
            'udi6_q1': 0, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
            'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_udi6_moderate_symptoms(self):
        """Test moderate stress incontinence symptoms."""
        inputs = {
            'udi6_q1': 1, 'udi6_q2': 1, 'udi6_q3': 1, 'udi6_q4': 1, 'udi6_q5': 1, 'udi6_q6': 1,
            'iiq7_q1': 1, 'iiq7_q2': 1, 'iiq7_q3': 1, 'iiq7_q4': 1, 'iiq7_q5': 1, 'iiq7_q6': 1, 'iiq7_q7': 1,
        }
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_udi6_severe_symptoms(self):
        """Test severe stress incontinence symptoms."""
        inputs = {
            'udi6_q1': 3, 'udi6_q2': 3, 'udi6_q3': 3, 'udi6_q4': 3, 'udi6_q5': 3, 'udi6_q6': 3,
            'iiq7_q1': 3, 'iiq7_q2': 3, 'iiq7_q3': 3, 'iiq7_q4': 3, 'iiq7_q5': 3, 'iiq7_q6': 3, 'iiq7_q7': 3,
        }
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_udi6_input_validation(self):
        """Validate input ranges."""
        invalid_inputs = [
            {'udi6_q1': -1, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
             'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0},
        ]

        for invalid_input in invalid_inputs:
            is_valid, _ = self.calc.validate_inputs(invalid_input)
            assert is_valid is False


class TestPFDIMedical:
    """Validate PFDI pelvic floor dysfunction questionnaire."""

    def setup_method(self):
        self.calc = PFDICalculator()

    def test_pfdi_minimal_dysfunction(self):
        """Test minimal pelvic floor dysfunction."""
        inputs = {'popdi_scores': [0]*6, 'cradi_scores': [0]*8, 'udi_scores': [0]*6}
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_pfdi_moderate_dysfunction(self):
        """Test moderate pelvic floor dysfunction."""
        inputs = {'popdi_scores': [1]*6, 'cradi_scores': [1]*8, 'udi_scores': [1]*6}
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_pfdi_severe_dysfunction(self):
        """Test severe pelvic floor dysfunction."""
        inputs = {'popdi_scores': [3]*6, 'cradi_scores': [3]*8, 'udi_scores': [3]*6}
        result = self.calc.calculate(inputs)
        assert result is not None

    def test_pfdi_calculator_properties(self):
        """Verify calculator metadata."""
        assert "PFDI" in self.calc.name or "Pelvic" in self.calc.name


class TestICIQMedical:
    """Validate ICIQ incontinence impact questionnaire."""

    def setup_method(self):
        self.calc = ICIQCalculator()

    def test_iciq_minimal_symptoms(self):
        """Test minimal incontinence symptoms and impact."""
        inputs = {'frequency': 0, 'amount': 0, 'impact': 0}
        result = self.calc.calculate(inputs)
        assert result is not None
        assert result.result['total_score'] == 0
        assert result.result['severity'] == "No incontinence"

    def test_iciq_moderate_symptoms(self):
        """Test moderate incontinence symptoms."""
        inputs = {'frequency': 2, 'amount': 2, 'impact': 5}
        result = self.calc.calculate(inputs)
        assert result is not None
        assert result.result['total_score'] == 9
        assert result.result['severity'] == "Moderate"

    def test_iciq_severe_symptoms(self):
        """Test severe incontinence symptoms."""
        inputs = {'frequency': 4, 'amount': 4, 'impact': 10}
        result = self.calc.calculate(inputs)
        assert result is not None
        assert result.result['total_score'] == 18
        assert result.result['severity'] == "Severe"

    def test_iciq_calculator_properties(self):
        """Verify calculator metadata."""
        assert "ICIQ" in self.calc.name or "Incontinence" in self.calc.name


class TestPOPQMedical:
    """Validate POP-Q prolapse quantification staging."""

    def setup_method(self):
        self.calc = POPQCalculator()

    def test_popq_calculations_work(self):
        """Test that POP-Q calculations work across range of values."""
        test_inputs = [
            {'aa': -1, 'ba': -1, 'c': -5, 'ap': -2, 'bp': -2, 'd': -7, 'tvl': 9, 'gh': 4, 'pb': 3},
            {'aa': 0, 'ba': 0, 'c': -3, 'ap': -1, 'bp': -1, 'd': -6, 'tvl': 9, 'gh': 4, 'pb': 3},
            {'aa': 1, 'ba': 1, 'c': -2, 'ap': 0, 'bp': 0, 'd': -5, 'tvl': 9, 'gh': 4, 'pb': 3},
            {'aa': 2, 'ba': 2, 'c': 0, 'ap': 1, 'bp': 1, 'd': -4, 'tvl': 9, 'gh': 4, 'pb': 3},
        ]

        for inputs in test_inputs:
            result = self.calc.calculate(inputs)
            assert result is not None

    def test_popq_calculator_properties(self):
        """Verify calculator metadata."""
        assert "POP" in self.calc.name or "Prolapse" in self.calc.name


# Integration tests
class TestPhase3IntegrationBatch:
    """Integration tests for all Phase 3 remaining calculators."""

    def test_all_phase3_calculators_exist(self):
        """Verify all Phase 3 calculators can be instantiated."""
        calculators = [
            UDI6IIQ7Calculator(),
            PFDICalculator(),
            ICIQCalculator(),
            POPQCalculator(),
        ]

        assert len(calculators) == 4

        for calc in calculators:
            assert calc.name is not None
            assert len(calc.references) > 0
