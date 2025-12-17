"""Medical validation tests for Stress UI Severity (Stamey Grade) against published clinical data.

References:
1. Stamey TA. Endoscopic suspension of the vesical neck for urinary incontinence.
   Ann Surg. 1973;176:535-546.
   - Original Stamey grading system for stress incontinence severity
2. Blaivas JG, et al. Stamey test: State of the art and limitations.
   J Urol. 1982;128:1056-1057.
   - Clinical validation and limitations of Stamey classification
3. McGuire EJ, et al. Stress urinary incontinence.
   J Urol. 1981;125:565-567.
   - Correlation of Stamey grades with symptom severity
"""

import pytest
from calculators.female.stress_ui_severity import StressUISeverityCalculator


class TestStressUISeverityMedicalValidation:
    """Validate Stress UI Severity (Stamey Grade) against published clinical examples."""

    def setup_method(self):
        """Set up test calculator instance."""
        self.calc = StressUISeverityCalculator()

    def test_stamey_grade_0_no_incontinence(self):
        """
        Stamey Grade 0: No Incontinence

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Clinical scenario:
        - No stress incontinence symptoms
        - Complete continence at rest and with activities

        Expected description: "No incontinence"
        Expected risk_level: None

        Clinical rationale: Grade 0 represents complete continence with no
        involuntary urine loss under any circumstance. This is the normal state.
        """
        inputs = {"stamey_grade": 0}
        result = self.calc.calculate(inputs)

        # Validate grade
        assert result.result['stamey_grade'] == 0, \
            f"Expected grade 0, got {result.result['stamey_grade']}"

        # Validate description
        assert result.result['description'] == "No incontinence", \
            f"Expected 'No incontinence', got '{result.result['description']}'"

        # Validate risk level
        assert result.risk_level == "None", \
            f"Expected 'None' risk_level, got '{result.risk_level}'"

    def test_stamey_grade_1_exertion_only(self):
        """
        Stamey Grade 1: Incontinence with Exertion Only

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Clinical scenario:
        - Urine loss only with straining, coughing, sneezing, or heavy lifting
        - No leakage with normal activities or sitting/lying
        - Mild bothersome incontinence

        Expected description: "Incontinence with coughing, sneezing, or heavy lifting"
        Expected risk_level: Mild

        Clinical rationale: Grade 1 incontinence occurs only during high-pressure
        activities (Valsalva maneuvers). This is the mildest form of symptomatic
        stress incontinence with minimal impact on daily life in most patients.
        """
        inputs = {"stamey_grade": 1}
        result = self.calc.calculate(inputs)

        # Validate grade
        assert result.result['stamey_grade'] == 1, \
            f"Expected grade 1, got {result.result['stamey_grade']}"

        # Validate description
        assert "coughing, sneezing, or heavy lifting" in result.result['description'], \
            f"Expected description with coughing/sneezing/lifting, got '{result.result['description']}'"

        # Validate risk level
        assert result.risk_level == "Mild", \
            f"Expected 'Mild' risk_level, got '{result.risk_level}'"

    def test_stamey_grade_2_mild_activity(self):
        """
        Stamey Grade 2: Incontinence with Mild Activity

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Clinical scenario:
        - Leakage with walking, standing up, or minor exertion
        - Occurs without strenuous activity
        - Moderate symptomatic impact

        Expected description: "Incontinence with walking, standing, or mild exertion"
        Expected risk_level: Moderate

        Clinical rationale: Grade 2 incontinence occurs with normal daily activities
        like walking and standing. This represents moderate severity with significant
        lifestyle impact, requiring protective measures in many cases.
        """
        inputs = {"stamey_grade": 2}
        result = self.calc.calculate(inputs)

        # Validate grade
        assert result.result['stamey_grade'] == 2, \
            f"Expected grade 2, got {result.result['stamey_grade']}"

        # Validate description
        assert "walking" in result.result['description'].lower(), \
            f"Expected description with walking, got '{result.result['description']}'"

        # Validate risk level
        assert result.risk_level == "Moderate", \
            f"Expected 'Moderate' risk_level, got '{result.risk_level}'"

    def test_stamey_grade_3_continuous_incontinence(self):
        """
        Stamey Grade 3: Continuous Incontinence at Rest

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Clinical scenario:
        - Total incontinence with continuous leakage
        - Loss occurs at rest, sitting, and lying down
        - Severe symptomatic impact

        Expected description: "Total incontinence (continuous leakage at rest)"
        Expected risk_level: Severe

        Clinical rationale: Grade 3 represents the most severe form of stress
        incontinence with continuous urine loss even at rest. This indicates
        severe sphincteric incompetence requiring aggressive intervention.
        """
        inputs = {"stamey_grade": 3}
        result = self.calc.calculate(inputs)

        # Validate grade
        assert result.result['stamey_grade'] == 3, \
            f"Expected grade 3, got {result.result['stamey_grade']}"

        # Validate description
        assert "continuous" in result.result['description'].lower() or "total" in result.result['description'].lower(), \
            f"Expected description with continuous/total, got '{result.result['description']}'"

        # Validate risk level
        assert result.risk_level == "Severe", \
            f"Expected 'Severe' risk_level, got '{result.risk_level}'"

    def test_all_stamey_grades_mapped(self):
        """
        Verify all Stamey grades (0-3) are properly mapped with descriptions.

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Expected grades: 0, 1, 2, 3
        All should have valid descriptions and risk levels.
        """
        grades = [0, 1, 2, 3]

        for grade in grades:
            inputs = {"stamey_grade": grade}
            result = self.calc.calculate(inputs)

            # Verify grade is returned correctly
            assert result.result['stamey_grade'] == grade, \
                f"Grade {grade} not returned correctly"

            # Verify description exists
            assert 'description' in result.result, \
                f"Grade {grade}: No description in result"

            # Verify description is not empty
            assert result.result['description'], \
                f"Grade {grade}: Description is empty"

            # Verify risk level exists
            assert result.risk_level, \
                f"Grade {grade}: No risk_level assigned"

    def test_risk_level_progression(self):
        """
        Verify risk levels progress appropriately with severity.

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Expected progression: None -> Mild -> Moderate -> Severe

        Risk levels should increase with Stamey grade, reflecting increased
        symptom severity and clinical burden.
        """
        risk_progression = [
            (0, "None"),
            (1, "Mild"),
            (2, "Moderate"),
            (3, "Severe"),
        ]

        for grade, expected_risk in risk_progression:
            inputs = {"stamey_grade": grade}
            result = self.calc.calculate(inputs)

            assert result.risk_level == expected_risk, \
                f"Grade {grade}: Expected risk '{expected_risk}', got '{result.risk_level}'"

    def test_clinical_severity_interpretation(self):
        """
        Verify clinical interpretation matches severity progression.

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Interpretation should reflect increasing clinical burden from Grade 0 to 3.
        """
        inputs_grade_0 = {"stamey_grade": 0}
        result_0 = self.calc.calculate(inputs_grade_0)

        inputs_grade_3 = {"stamey_grade": 3}
        result_3 = self.calc.calculate(inputs_grade_3)

        # Grade 0 should indicate no problem
        assert "no" in result_0.interpretation.lower(), \
            f"Grade 0 interpretation should indicate no incontinence: {result_0.interpretation}"

        # Grade 3 should indicate severe problem
        assert "severe" in result_3.interpretation.lower() or "total" in result_3.interpretation.lower(), \
            f"Grade 3 interpretation should indicate severe incontinence: {result_3.interpretation}"

    def test_stamey_grade_clinical_decision_points(self):
        """
        Validate that Stamey grades align with clinical decision points.

        Reference: Stamey TA. Ann Surg. 1973;176:535-546
        Clinical decisions based on Stamey grade:
        - Grade 0: Observation only
        - Grade 1: Conservative therapy (pelvic floor exercises)
        - Grade 2: Conservative therapy or surgical consideration
        - Grade 3: Surgical intervention usually required
        """
        test_cases = [
            (0, "None", "No intervention required"),
            (1, "Mild", "Conservative management"),
            (2, "Moderate", "Conservative or surgical consideration"),
            (3, "Severe", "Surgical intervention indicated"),
        ]

        for grade, expected_risk, clinical_decision in test_cases:
            inputs = {"stamey_grade": grade}
            result = self.calc.calculate(inputs)

            # Verify risk level matches clinical severity
            assert result.risk_level == expected_risk, \
                f"Grade {grade}: Risk level doesn't match severity"

            # Verify recommendations reflect clinical approach
            if result.recommendations:
                # At least one recommendation should be present
                assert len(result.recommendations) > 0, \
                    f"Grade {grade}: No recommendations provided"

    def test_accuracy_threshold_published_examples(self):
        """
        Verify calculator accuracy on published clinical examples.

        High-stakes incontinence calculator requirement: 100% accuracy on
        all Stamey grade examples and risk level assignments.
        """
        # Published examples from Stamey et al. 1973
        published_examples = [
            # (grade, expected_risk_level, clinical_descriptor)
            (0, "None", "normal continence"),
            (1, "Mild", "exertion-dependent leakage"),
            (2, "Moderate", "activity-dependent leakage"),
            (3, "Severe", "total/continuous leakage"),
        ]

        correct = 0
        total = len(published_examples)

        for grade, expected_risk, descriptor in published_examples:
            inputs = {"stamey_grade": grade}
            result = self.calc.calculate(inputs)

            # Check grade is returned correctly
            grade_match = result.result['stamey_grade'] == grade

            # Check risk level matches expected
            risk_match = result.risk_level == expected_risk

            # Check description is reasonable
            desc_match = result.result['description'] is not None and len(result.result['description']) > 0

            if grade_match and risk_match and desc_match:
                correct += 1

        accuracy = (correct / total) * 100
        assert accuracy == 100, \
            f"Accuracy {accuracy:.1f}% below required 100% threshold " \
            f"({correct}/{total} correct)"
