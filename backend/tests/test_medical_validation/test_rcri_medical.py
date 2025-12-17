"""Medical validation tests for RCRI (Revised Cardiac Risk Index).

References:
1. Lee TH, et al. Derivation and prospective validation of a simple index for
   prediction of cardiac risk of major noncardiac surgery.
   Circulation. 1999;100(10):1043-1049.
2. Ford MK, et al. Systematic review: prediction of perioperative cardiac
   complications and mortality by the revised cardiac risk index.
   Ann Intern Med. 2010;152(1):26-35.
"""

import pytest
from calculators.surgical.rcri import RCRICalculator


class TestRCRIMedicalValidation:
    """Validate RCRI calculator against published clinical examples."""

    def setup_method(self):
        """Set up test calculator instance."""
        self.calc = RCRICalculator()

    def test_lee_1999_class_i_low_risk(self):
        """
        Published Example: Class I - Low Risk Patient

        Reference: Lee TH, et al. Circulation 1999;100:1043-1049, Table 3

        Patient characteristics:
        - No RCRI risk factors present

        RCRI Risk Factors (6 total):
        1. High-risk surgery: No
        2. Ischemic heart disease: No
        3. Congestive heart failure: No
        4. Cerebrovascular disease: No
        5. Diabetes on insulin: No
        6. Creatinine >2.0 mg/dL: No

        Expected RCRI Score: 0 points
        Expected Risk Class: Class I (Low Risk)
        Expected MACE Rate: 0.4%
        """
        inputs = {
            'risk_factors_count': 0
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['rcri_score'] == 0, \
            f"Expected RCRI score 0, got {result.result['rcri_score']}"

        # Validate risk level
        assert result.risk_level == "Low", \
            f"Expected 'Low' risk, got '{result.risk_level}'"

        # Validate MACE rate
        assert result.result['mace_risk'] == "0.4%", \
            f"Expected MACE rate 0.4%, got {result.result['mace_risk']}"

    def test_lee_1999_class_ii_moderate_risk(self):
        """
        Published Example: Class II - Moderate Risk Patient

        Reference: Lee TH, et al. Circulation 1999;100:1043-1049, Table 3

        Patient characteristics:
        - 1 RCRI risk factor present (e.g., diabetes on insulin)

        Expected RCRI Score: 1 point
        Expected Risk Class: Class II (Moderate Risk)
        Expected MACE Rate: 0.9%
        """
        inputs = {
            'risk_factors_count': 1
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['rcri_score'] == 1, \
            f"Expected RCRI score 1, got {result.result['rcri_score']}"

        # Validate risk level
        assert result.risk_level == "Moderate", \
            f"Expected 'Moderate' risk, got '{result.risk_level}'"

        # Validate MACE rate
        assert result.result['mace_risk'] == "0.9%", \
            f"Expected MACE rate 0.9%, got {result.result['mace_risk']}"

    def test_lee_1999_class_iii_high_risk(self):
        """
        Published Example: Class III - High Risk Patient

        Reference: Lee TH, et al. Circulation 1999;100:1043-1049, Table 3

        Patient characteristics:
        - 2 RCRI risk factors present
        - Example: High-risk surgery + history of ischemic heart disease

        Expected RCRI Score: 2 points
        Expected Risk Class: Class III (High Risk)
        Expected MACE Rate: 6.6%
        """
        inputs = {
            'risk_factors_count': 2
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['rcri_score'] == 2, \
            f"Expected RCRI score 2, got {result.result['rcri_score']}"

        # Validate risk level
        assert result.risk_level == "High", \
            f"Expected 'High' risk, got '{result.risk_level}'"

        # Validate MACE rate
        assert result.result['mace_risk'] == "6.6%", \
            f"Expected MACE rate 6.6%, got {result.result['mace_risk']}"

    def test_lee_1999_class_iv_very_high_risk(self):
        """
        Published Example: Class IV - Very High Risk Patient

        Reference: Lee TH, et al. Circulation 1999;100:1043-1049, Table 3

        Patient characteristics:
        - 3+ RCRI risk factors present
        - Example: High-risk surgery + ischemic heart disease + diabetes on insulin

        Expected RCRI Score: 3+ points
        Expected Risk Class: Class IV (High Risk)
        Expected MACE Rate: 11%
        """
        inputs = {
            'risk_factors_count': 3
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['rcri_score'] == 3, \
            f"Expected RCRI score 3, got {result.result['rcri_score']}"

        # Validate risk level
        assert result.risk_level == "High", \
            f"Expected 'High' risk, got '{result.risk_level}'"

        # Validate MACE rate
        assert result.result['mace_risk'] == "11%", \
            f"Expected MACE rate 11%, got {result.result['mace_risk']}"

    def test_score_range_validation(self):
        """
        Validate all possible RCRI scores (0-6).

        RCRI Scoring:
        - Score = number of risk factors present (0-6)
        - Each risk factor contributes 1 point
        """
        test_cases = [
            (0, "Low", "0.4%"),
            (1, "Moderate", "0.9%"),
            (2, "High", "6.6%"),
            (3, "High", "11%"),
            (4, "High", "11%"),
            (5, "High", "11%"),
            (6, "High", "11%"),
        ]

        for score, expected_risk_level, expected_mace in test_cases:
            inputs = {'risk_factors_count': score}
            result = self.calc.calculate(inputs)

            assert result.result['rcri_score'] == score, \
                f"Score {score}: Expected score {score}, got {result.result['rcri_score']}"
            assert result.risk_level == expected_risk_level, \
                f"Score {score}: Expected '{expected_risk_level}', got '{result.risk_level}'"
            assert result.result['mace_risk'] == expected_mace, \
                f"Score {score}: Expected MACE {expected_mace}, got {result.result['mace_risk']}"

    def test_risk_stratification_thresholds(self):
        """
        Validate risk stratification thresholds.

        Risk Classification (Lee et al. 1999):
        - Class I (Low): 0 risk factors
        - Class II (Moderate): 1 risk factor
        - Class III (High): 2 risk factors
        - Class IV (High): ≥3 risk factors
        """
        # Low risk boundary
        result_0 = self.calc.calculate({'risk_factors_count': 0})
        assert result_0.risk_level == "Low"

        # Moderate risk
        result_1 = self.calc.calculate({'risk_factors_count': 1})
        assert result_1.risk_level == "Moderate"

        # High risk threshold
        result_2 = self.calc.calculate({'risk_factors_count': 2})
        assert result_2.risk_level == "High"

        # Very high risk
        result_3 = self.calc.calculate({'risk_factors_count': 3})
        assert result_3.risk_level == "High"

    def test_mace_rate_escalation(self):
        """
        Validate MACE rate escalation with increasing risk factors.

        MACE Rate Progression (Lee et al. 1999):
        - 0 factors: 0.4%
        - 1 factor: 0.9% (2.25x increase)
        - 2 factors: 6.6% (7.3x increase from 1 factor)
        - ≥3 factors: 11% (1.67x increase from 2 factors)
        """
        mace_rates = []
        for count in range(4):
            result = self.calc.calculate({'risk_factors_count': count})
            mace_rates.append(result.result['mace_risk'])

        # Verify escalation pattern
        assert mace_rates == ["0.4%", "0.9%", "6.6%", "11%"], \
            f"MACE rate escalation incorrect: {mace_rates}"

    def test_ford_2010_systematic_review_validation(self):
        """
        External Validation: Ford et al. Systematic Review

        Reference: Ford MK, et al. Ann Intern Med 2010;152:26-35

        Systematic review confirmed RCRI accuracy across multiple studies:
        - Low risk (0 factors): <1% MACE
        - Moderate risk (1 factor): ~1% MACE
        - High risk (≥2 factors): >5% MACE
        """
        # Low risk validation
        result_low = self.calc.calculate({'risk_factors_count': 0})
        assert result_low.result['mace_risk'] == "0.4%"
        assert result_low.risk_level == "Low"

        # Moderate risk validation
        result_mod = self.calc.calculate({'risk_factors_count': 1})
        assert result_mod.result['mace_risk'] == "0.9%"
        assert result_mod.risk_level == "Moderate"

        # High risk validation
        result_high = self.calc.calculate({'risk_factors_count': 2})
        assert result_high.result['mace_risk'] == "6.6%"
        assert result_high.risk_level == "High"

    def test_clinical_scenario_vascular_surgery(self):
        """
        Clinical Scenario: High-Risk Vascular Surgery

        Patient: 72-year-old undergoing AAA repair
        - High-risk surgery (vascular): YES (1 point)
        - History of MI 2 years ago: YES (1 point)
        - CHF with EF 35%: YES (1 point)
        - CVA 5 years ago: YES (1 point)
        - Diabetes on insulin: YES (1 point)
        - Creatinine 2.3 mg/dL: YES (1 point)

        Total Risk Factors: 6
        Expected RCRI: 6 points
        Expected MACE Risk: 11% (Lee et al. 1999 reported 11% for ≥3 risk factors)
        """
        inputs = {
            'risk_factors_count': 6
        }

        result = self.calc.calculate(inputs)

        assert result.result['rcri_score'] == 6
        assert result.risk_level == "High"
        assert result.result['mace_risk'] == "11%"

    def test_clinical_scenario_low_risk_orthopedic(self):
        """
        Clinical Scenario: Low-Risk Orthopedic Surgery

        Patient: 45-year-old undergoing total knee replacement
        - High-risk surgery: NO (orthopedic is not high-risk)
        - No cardiac history
        - No diabetes
        - Normal renal function

        Total Risk Factors: 0
        Expected RCRI: 0 points
        Expected MACE Risk: 0.4%
        """
        inputs = {
            'risk_factors_count': 0
        }

        result = self.calc.calculate(inputs)

        assert result.result['rcri_score'] == 0
        assert result.risk_level == "Low"
        assert result.result['mace_risk'] == "0.4%"

    def test_accuracy_threshold_all_scenarios(self):
        """
        Verify calculator achieves >99.5% accuracy across all clinical scenarios.

        High-stakes calculator requirement: >99.5% accuracy
        """
        published_scenarios = [
            # (risk_factors_count, expected_score, expected_risk_level, expected_mace)
            (0, 0, 'Low', '0.4%'),
            (1, 1, 'Moderate', '0.9%'),
            (2, 2, 'High', '6.6%'),
            (3, 3, 'High', '11%'),
        ]

        correct = 0
        total = len(published_scenarios)

        for count, expected_score, expected_risk, expected_mace in published_scenarios:
            result = self.calc.calculate({'risk_factors_count': count})

            if (result.result['rcri_score'] == expected_score and
                result.risk_level == expected_risk and
                result.result['mace_risk'] == expected_mace):
                correct += 1

        accuracy = (correct / total) * 100
        assert accuracy >= 99.5, \
            f"Accuracy {accuracy:.1f}% below required 99.5% threshold"
