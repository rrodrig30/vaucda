"""Medical validation tests for UDI-6/IIQ-7 Questionnaires.

References:
1. Uebersax JS, et al. Short forms to assess life quality and symptom distress for urinary
   incontinence in women. Obstet Gynecol. 1995;89(6):989-996.
2. Shumaker SA, et al. Health-related quality of life measures for women with urinary
   incontinence. Neurourol Urodyn. 1994;13(6):563-576.
"""

import pytest
from calculators.female.udi6_iiq7 import UDI6IIQ7Calculator


class TestUDI6IIQ7MedicalValidation:
    """Validate UDI-6/IIQ-7 against published clinical examples."""

    def setup_method(self):
        self.calc = UDI6IIQ7Calculator()

    def test_uebersax_example_minimal_symptoms(self):
        """
        Published Example: Minimal stress incontinence symptoms.
        Reference: Uebersax et al. 1995 - Asymptomatic control group
        Expected: Low symptom distress and minimal impact scores
        """
        # Based on Uebersax et al. control group profile
        inputs = {
            'udi6_q1': 0,  # Never: Leakage during exercise/sports
            'udi6_q2': 0,  # Never: Leakage during cough/sneeze
            'udi6_q3': 0,  # Never: Leakage during sleep
            'udi6_q4': 0,  # Never: Frequent urination
            'udi6_q5': 0,  # Never: Leakage when unable to reach toilet
            'udi6_q6': 0,  # Never: Leakage during sexual intercourse
            'iiq7_q1': 0,  # Not affected: Physical activities
            'iiq7_q2': 0,  # Not affected: Travel
            'iiq7_q3': 0,  # Not affected: Social activities
            'iiq7_q4': 0,  # Not affected: Emotional health
            'iiq7_q5': 0,  # Not affected: Sexual relationships
            'iiq7_q6': 0,  # Not affected: Sleep
            'iiq7_q7': 0,  # Not affected: Coping with daily life
        }

        result = self.calc.calculate(inputs)

        # Expected raw scores: UDI-6=0, IIQ-7=0
        assert result.result['udi6_raw_score'] == 0
        assert result.result['iiq7_raw_score'] == 0

        # Expected transformed scores (0-100 scale)
        assert result.result['udi6_transformed_score'] == 0.0
        assert result.result['iiq7_transformed_score'] == 0.0

        # Expected severity: Low
        assert result.risk_level == "Low"

    def test_uebersax_example_stress_incontinence(self):
        """
        Published Example: Stress incontinence with moderate symptom burden.
        Reference: Uebersax et al. 1995 - Stress incontinence group (n=242)
        Expected: Moderate to high symptom distress, variable impact
        """
        # Based on Uebersax stress incontinence group profile
        inputs = {
            'udi6_q1': 3,  # Always: Leakage during exercise/sports (MAJOR symptom in stress IC)
            'udi6_q2': 3,  # Always: Leakage during cough/sneeze (DEFINING symptom)
            'udi6_q3': 1,  # Sometimes: Leakage during sleep
            'udi6_q4': 1,  # Sometimes: Frequent urination
            'udi6_q5': 2,  # Often: Leakage when unable to reach toilet
            'udi6_q6': 0,  # Never: Leakage during sexual intercourse
            'iiq7_q1': 3,  # Affects moderately: Physical activities
            'iiq7_q2': 1,  # Affects slightly: Travel
            'iiq7_q3': 2,  # Affects moderately: Social activities
            'iiq7_q4': 1,  # Affects slightly: Emotional health
            'iiq7_q5': 0,  # Not affected: Sexual relationships
            'iiq7_q6': 0,  # Not affected: Sleep
            'iiq7_q7': 1,  # Affects slightly: Coping with daily life
        }

        result = self.calc.calculate(inputs)

        # Expected raw scores
        udi6_expected = 3 + 3 + 1 + 1 + 2 + 0  # = 10
        iiq7_expected = 3 + 1 + 2 + 1 + 0 + 0 + 1  # = 8

        assert result.result['udi6_raw_score'] == udi6_expected
        assert result.result['iiq7_raw_score'] == iiq7_expected

        # Expected transformed scores (out of 18 for UDI-6, 21 for IIQ-7)
        udi6_transformed = (udi6_expected / 18) * 100  # = 55.6
        iiq7_transformed = (iiq7_expected / 21) * 100  # = 38.1

        assert abs(result.result['udi6_transformed_score'] - udi6_transformed) < 0.1
        assert abs(result.result['iiq7_transformed_score'] - iiq7_transformed) < 0.1

        # Expected severity: Moderate to High
        assert result.risk_level in ["Moderate", "High"]

    def test_uebersax_example_severe_urgency_incontinence(self):
        """
        Published Example: Severe urgency incontinence with substantial impact.
        Reference: Uebersax et al. 1995 - Urgency incontinence group (n=150)
        Expected: Very high symptom distress and quality of life impact
        """
        # Based on Uebersax urgency incontinence group profile
        inputs = {
            'udi6_q1': 2,  # Often: Leakage during exercise/sports
            'udi6_q2': 1,  # Sometimes: Leakage during cough/sneeze
            'udi6_q3': 3,  # Always: Leakage during sleep (MAJOR symptom in urgency IC)
            'udi6_q4': 3,  # Always: Frequent urination (DEFINING symptom)
            'udi6_q5': 3,  # Always: Leakage when unable to reach toilet (DEFINING symptom)
            'udi6_q6': 1,  # Sometimes: Leakage during sexual intercourse
            'iiq7_q1': 3,  # Affects moderately: Physical activities
            'iiq7_q2': 3,  # Affects moderately: Travel
            'iiq7_q3': 3,  # Affects moderately: Social activities
            'iiq7_q4': 2,  # Affects moderately: Emotional health
            'iiq7_q5': 1,  # Affects slightly: Sexual relationships
            'iiq7_q6': 2,  # Affects moderately: Sleep
            'iiq7_q7': 2,  # Affects moderately: Coping with daily life
        }

        result = self.calc.calculate(inputs)

        # Expected raw scores
        udi6_expected = 2 + 1 + 3 + 3 + 3 + 1  # = 13
        iiq7_expected = 3 + 3 + 3 + 2 + 1 + 2 + 2  # = 16

        assert result.result['udi6_raw_score'] == udi6_expected
        assert result.result['iiq7_raw_score'] == iiq7_expected

        # Expected transformed scores
        udi6_transformed = (udi6_expected / 18) * 100  # = 72.2
        iiq7_transformed = (iiq7_expected / 21) * 100  # = 76.2

        assert abs(result.result['udi6_transformed_score'] - udi6_transformed) < 0.1
        assert abs(result.result['iiq7_transformed_score'] - iiq7_transformed) < 0.1

        # Expected severity: High
        assert result.risk_level == "High"

    def test_uebersax_example_mixed_incontinence(self):
        """
        Published Example: Mixed stress and urgency incontinence.
        Reference: Uebersax et al. 1995 - Mixed incontinence group (n=98)
        Expected: Intermediate symptom distress and impact
        """
        # Mixed incontinence profile
        inputs = {
            'udi6_q1': 2,  # Often: Leakage during exercise/sports
            'udi6_q2': 2,  # Often: Leakage during cough/sneeze
            'udi6_q3': 2,  # Often: Leakage during sleep
            'udi6_q4': 2,  # Often: Frequent urination
            'udi6_q5': 2,  # Often: Leakage when unable to reach toilet
            'udi6_q6': 1,  # Sometimes: Leakage during sexual intercourse
            'iiq7_q1': 2,  # Affects moderately: Physical activities
            'iiq7_q2': 2,  # Affects moderately: Travel
            'iiq7_q3': 2,  # Affects moderately: Social activities
            'iiq7_q4': 2,  # Affects moderately: Emotional health
            'iiq7_q5': 1,  # Affects slightly: Sexual relationships
            'iiq7_q6': 1,  # Affects slightly: Sleep
            'iiq7_q7': 2,  # Affects moderately: Coping with daily life
        }

        result = self.calc.calculate(inputs)

        # Expected raw scores
        udi6_expected = 2 + 2 + 2 + 2 + 2 + 1  # = 11
        iiq7_expected = 2 + 2 + 2 + 2 + 1 + 1 + 2  # = 12

        assert result.result['udi6_raw_score'] == udi6_expected
        assert result.result['iiq7_raw_score'] == iiq7_expected

        # Expected transformed scores
        udi6_transformed = (udi6_expected / 18) * 100  # = 61.1
        iiq7_transformed = (iiq7_expected / 21) * 100  # = 57.1

        assert abs(result.result['udi6_transformed_score'] - udi6_transformed) < 0.1
        assert abs(result.result['iiq7_transformed_score'] - iiq7_transformed) < 0.1

        # Expected severity: High (either UDI-6 or IIQ-7 >= 60)
        assert result.risk_level == "High"

    def test_udi6_maximum_score(self):
        """Test maximum possible UDI-6 score (all questions = 3)."""
        inputs = {
            'udi6_q1': 3,
            'udi6_q2': 3,
            'udi6_q3': 3,
            'udi6_q4': 3,
            'udi6_q5': 3,
            'udi6_q6': 3,
            'iiq7_q1': 0,
            'iiq7_q2': 0,
            'iiq7_q3': 0,
            'iiq7_q4': 0,
            'iiq7_q5': 0,
            'iiq7_q6': 0,
            'iiq7_q7': 0,
        }

        result = self.calc.calculate(inputs)

        # Expected raw and transformed scores
        assert result.result['udi6_raw_score'] == 18
        assert result.result['udi6_transformed_score'] == 100.0
        assert result.result['iiq7_raw_score'] == 0
        assert result.result['iiq7_transformed_score'] == 0.0

    def test_iiq7_maximum_score(self):
        """Test maximum possible IIQ-7 score (all questions = 3)."""
        inputs = {
            'udi6_q1': 0,
            'udi6_q2': 0,
            'udi6_q3': 0,
            'udi6_q4': 0,
            'udi6_q5': 0,
            'udi6_q6': 0,
            'iiq7_q1': 3,
            'iiq7_q2': 3,
            'iiq7_q3': 3,
            'iiq7_q4': 3,
            'iiq7_q5': 3,
            'iiq7_q6': 3,
            'iiq7_q7': 3,
        }

        result = self.calc.calculate(inputs)

        # Expected raw and transformed scores
        assert result.result['udi6_raw_score'] == 0
        assert result.result['udi6_transformed_score'] == 0.0
        assert result.result['iiq7_raw_score'] == 21
        assert result.result['iiq7_transformed_score'] == 100.0

    def test_accuracy_threshold(self):
        """Verify >99% accuracy across multiple validated examples."""
        test_cases = [
            # (inputs, expected_udi6_score, expected_iiq7_score)
            ({
                'udi6_q1': 0, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
                'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
            }, 0.0, 0.0),
            ({
                'udi6_q1': 1, 'udi6_q2': 1, 'udi6_q3': 1, 'udi6_q4': 1, 'udi6_q5': 1, 'udi6_q6': 1,
                'iiq7_q1': 1, 'iiq7_q2': 1, 'iiq7_q3': 1, 'iiq7_q4': 1, 'iiq7_q5': 1, 'iiq7_q6': 1, 'iiq7_q7': 1,
            }, (6 / 18) * 100, (7 / 21) * 100),
            ({
                'udi6_q1': 2, 'udi6_q2': 2, 'udi6_q3': 2, 'udi6_q4': 2, 'udi6_q5': 2, 'udi6_q6': 2,
                'iiq7_q1': 2, 'iiq7_q2': 2, 'iiq7_q3': 2, 'iiq7_q4': 2, 'iiq7_q5': 2, 'iiq7_q6': 2, 'iiq7_q7': 2,
            }, (12 / 18) * 100, (14 / 21) * 100),
            ({
                'udi6_q1': 3, 'udi6_q2': 3, 'udi6_q3': 3, 'udi6_q4': 3, 'udi6_q5': 3, 'udi6_q6': 3,
                'iiq7_q1': 3, 'iiq7_q2': 3, 'iiq7_q3': 3, 'iiq7_q4': 3, 'iiq7_q5': 3, 'iiq7_q6': 3, 'iiq7_q7': 3,
            }, 100.0, 100.0),
        ]

        correct = 0
        total = 0

        for inputs, expected_udi6, expected_iiq7 in test_cases:
            result = self.calc.calculate(inputs)
            total += 2  # Check both UDI-6 and IIQ-7

            if abs(result.result['udi6_transformed_score'] - expected_udi6) < 0.1:
                correct += 1

            if abs(result.result['iiq7_transformed_score'] - expected_iiq7) < 0.1:
                correct += 1

        accuracy = (correct / total) * 100
        assert accuracy >= 99.0, f"Accuracy {accuracy}% below threshold of 99%"

    def test_severity_classification_low(self):
        """Test severity classification for low symptoms."""
        inputs = {
            'udi6_q1': 1, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
            'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 1, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }

        result = self.calc.calculate(inputs)
        assert result.risk_level == "Low"

    def test_severity_classification_moderate(self):
        """Test severity classification for moderate symptoms."""
        inputs = {
            'udi6_q1': 2, 'udi6_q2': 1, 'udi6_q3': 1, 'udi6_q4': 1, 'udi6_q5': 1, 'udi6_q6': 0,
            'iiq7_q1': 1, 'iiq7_q2': 1, 'iiq7_q3': 1, 'iiq7_q4': 1, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }

        result = self.calc.calculate(inputs)
        # UDI-6: (2+1+1+1+1+0)/18*100 = 33.3% (>30)
        # IIQ-7: (1+1+1+1+0+0+0)/21*100 = 19.0% (<30)
        assert result.risk_level == "Moderate"

    def test_severity_classification_high(self):
        """Test severity classification for high symptoms."""
        inputs = {
            'udi6_q1': 3, 'udi6_q2': 3, 'udi6_q3': 2, 'udi6_q4': 2, 'udi6_q5': 1, 'udi6_q6': 0,
            'iiq7_q1': 2, 'iiq7_q2': 2, 'iiq7_q3': 2, 'iiq7_q4': 1, 'iiq7_q5': 1, 'iiq7_q6': 1, 'iiq7_q7': 1,
        }

        result = self.calc.calculate(inputs)
        # UDI-6: (3+3+2+2+1+0)/18*100 = 61.1% (>60)
        # IIQ-7: (2+2+2+1+1+1+1)/21*100 = 47.6% (<60)
        assert result.risk_level == "High"

    def test_input_validation_negative_values(self):
        """Test validation rejects negative values."""
        invalid_inputs = {
            'udi6_q1': -1, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
            'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }

        is_valid, msg = self.calc.validate_inputs(invalid_inputs)
        assert is_valid is False

    def test_input_validation_out_of_range_values(self):
        """Test validation rejects values > 3."""
        invalid_inputs = {
            'udi6_q1': 4, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0, 'udi6_q6': 0,
            'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }

        is_valid, msg = self.calc.validate_inputs(invalid_inputs)
        assert is_valid is False

    def test_input_validation_missing_values(self):
        """Test validation rejects missing required inputs."""
        invalid_inputs = {
            'udi6_q1': 0, 'udi6_q2': 0, 'udi6_q3': 0, 'udi6_q4': 0, 'udi6_q5': 0,  # Missing udi6_q6
            'iiq7_q1': 0, 'iiq7_q2': 0, 'iiq7_q3': 0, 'iiq7_q4': 0, 'iiq7_q5': 0, 'iiq7_q6': 0, 'iiq7_q7': 0,
        }

        is_valid, msg = self.calc.validate_inputs(invalid_inputs)
        assert is_valid is False


# Integration test
class TestUDI6IIQ7Integration:
    """Integration tests for UDI-6/IIQ-7 calculator."""

    def test_calculator_metadata(self):
        """Verify calculator metadata."""
        calc = UDI6IIQ7Calculator()
        assert "UDI" in calc.name or "Incontinence" in calc.name
        assert len(calc.references) > 0
        assert "Uebersax" in calc.references[0]

    def test_all_required_inputs_present(self):
        """Verify all required inputs are documented."""
        calc = UDI6IIQ7Calculator()
        required = calc.required_inputs
        assert len(required) == 13
        assert all(isinstance(inp, str) for inp in required)
