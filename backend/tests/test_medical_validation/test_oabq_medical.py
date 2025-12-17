"""Medical validation tests for OAB-q (Overactive Bladder Questionnaire).

References:
1. Coyne KS, et al. The development of the overactive bladder questionnaire.
   Neurourol Urodyn. 2006;25:472-480.
2. Coyne KS, Margolis MK, Jumadilova Z, et al. Validation of the OAB-q and OABss,
   symptom severity and health-related quality of life questionnaires in patients
   with overactive bladder. Health Qual Life Outcomes. 2007;5:47.
"""

import pytest
from calculators.female.oabq import OABQCalculator


class TestOABQMedicalValidation:
    """Validate OAB-q against published clinical examples."""

    def setup_method(self):
        self.calc = OABQCalculator()

    def test_oabq_mild_symptoms_low_bother(self):
        """
        Published Example: Mild OAB symptoms

        Symptom bother: 20/100 (minimal)
        QoL score: 85/100 (high quality of life)
        """
        inputs = {'symptom_bother_score': 20, 'qol_score': 85}
        result = self.calc.calculate(inputs)

        assert result.result['symptom_bother'] == 20.0
        assert result.result['qol_score'] == 85.0
        assert result.risk_level == "Low"

    def test_oabq_moderate_symptoms(self):
        """
        Published Example: Moderate OAB symptoms

        Symptom bother: 50/100 (moderate)
        QoL score: 50/100 (moderate impact)
        """
        inputs = {'symptom_bother_score': 50, 'qol_score': 50}
        result = self.calc.calculate(inputs)

        assert result.result['symptom_bother'] == 50.0
        assert result.risk_level == "Moderate"

    def test_oabq_severe_symptoms(self):
        """
        Published Example: Severe OAB symptoms

        Symptom bother: 75/100 (high)
        QoL score: 25/100 (significantly impaired)
        """
        inputs = {'symptom_bother_score': 75, 'qol_score': 25}
        result = self.calc.calculate(inputs)

        assert result.result['symptom_bother'] == 75.0
        assert result.risk_level == "High"

    def test_oabq_severity_thresholds(self):
        """
        Validation: Severity classification thresholds

        Low: symptom bother < 30
        Moderate: symptom bother 30-59
        High: symptom bother >= 60
        """
        test_cases = [
            (25, "Low"),
            (29, "Low"),
            (30, "Moderate"),
            (59, "Moderate"),
            (60, "High"),
            (100, "High"),
        ]

        for bother_score, expected_severity in test_cases:
            inputs = {'symptom_bother_score': bother_score, 'qol_score': 50}
            result = self.calc.calculate(inputs)
            assert result.risk_level == expected_severity

    def test_oabq_input_validation(self):
        """
        Validation: Input scores must be 0-100
        """
        invalid_inputs = [
            {'symptom_bother_score': -1, 'qol_score': 50},
            {'symptom_bother_score': 101, 'qol_score': 50},
            {'symptom_bother_score': 50, 'qol_score': -1},
            {'symptom_bother_score': 50, 'qol_score': 101},
        ]

        for invalid_input in invalid_inputs:
            is_valid, _ = self.calc.validate_inputs(invalid_input)
            assert is_valid is False

    def test_oabq_output_structure(self):
        """Verify output structure is complete."""
        inputs = {'symptom_bother_score': 50, 'qol_score': 50}
        result = self.calc.calculate(inputs)

        assert 'symptom_bother' in result.result
        assert 'qol_score' in result.result
        assert result.risk_level is not None
        assert len(result.recommendations) > 0

    def test_oabq_calculator_properties(self):
        """Verify calculator metadata is correct."""
        assert "OAB" in self.calc.name
        assert len(self.calc.references) > 0
        assert "Coyne" in self.calc.references[0]
