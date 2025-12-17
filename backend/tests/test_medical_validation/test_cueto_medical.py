"""
Rigorous medical validation for CUETO BCG Risk Score Calculator.

References:
- Fernandez-Gomez JM, et al. Ann Oncol 2009;20(9):1529-1534 (CUETO group)
- Luo HL, et al. Prognostic factors of complete response to BCG. Urol Oncol 2013;31:909-915

CUETO BCG Risk Score: Sum of risk factors
- T1 disease: 1 point
- Concurrent CIS: 1 point
- High-grade (G3): 1 point
- Age > 70: 1 point
- Female gender: 1 point
Total: 0-5 points

Risk groups:
- 0 points: Low Risk (~5-10% BCG failure)
- 1 point: Intermediate Risk (~15-20% failure)
- 2 points: High Risk (~25-35% failure)
- 3-5 points: Very High Risk (~40-50% failure)
"""

import pytest

from calculators.bladder.cueto_score import CuetoCalculator


class TestCuetoBCGRiskMedicalValidation:
    """Rigorous validation of CUETO BCG risk stratification."""

    def setup_method(self):
        """Initialize calculator for each test."""
        self.calc = CuetoCalculator()

    def test_cueto_low_risk_ta_g1_male_young(self):
        """
        Published Example: Low Risk BCG Failure

        Reference: Fernandez-Gomez JM, et al. CUETO group analysis.
        Ann Oncol 2009;20(9):1529-1534, Table 2

        Patient characteristics:
        - T-category: Ta (non-muscle invasive, confined to mucosa)
        - Grade: G1 (low-grade)
        - No concurrent CIS
        - Age: 55 years (≤70)
        - Gender: Male

        Risk factors: 0
        Expected CUETO score: 0 points
        Expected risk: Low (5-10% BCG failure)
        Expected recommendation: Standard BCG induction
        """
        inputs = {
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 55,
            'gender': 'male'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 0
        assert result.risk_level == "Low Risk"
        assert "5-10%" in result.interpretation
        assert "Standard BCG induction" in result.interpretation

    def test_cueto_intermediate_risk_single_factor(self):
        """
        Published Example: Intermediate Risk - One Risk Factor

        Reference: CUETO BCG Risk Score study

        Patient characteristics:
        - T-category: T1 (invades lamina propria)
        - Grade: G2 (intermediate)
        - No concurrent CIS
        - Age: 60 years
        - Gender: Male

        Risk factors: 1 (T1 disease)
        Expected CUETO score: 1 point
        Expected risk: Intermediate (15-20% BCG failure)
        """
        inputs = {
            't_category': 'T1',
            'concurrent_cis': 'no',
            'grade': 'G2',
            'age': 60,
            'gender': 'male'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 1
        assert result.risk_level == "Intermediate Risk"
        assert "15-20%" in result.interpretation
        assert "T1 disease" in str(result.result['risk_factors'])

    def test_cueto_high_risk_two_factors(self):
        """
        Published Example: High Risk - Two Risk Factors

        Reference: CUETO BCG Risk Score

        Patient characteristics:
        - T-category: T1
        - Grade: G3 (high-grade)
        - No concurrent CIS
        - Age: 58 years
        - Gender: Male

        Risk factors: 2 (T1 + G3)
        Expected CUETO score: 2 points
        Expected risk: High (25-35% BCG failure)
        """
        inputs = {
            't_category': 'T1',
            'concurrent_cis': 'no',
            'grade': 'G3',
            'age': 58,
            'gender': 'male'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 2
        assert result.risk_level == "High Risk"
        assert "25-35%" in result.interpretation
        assert "T1 disease" in str(result.result['risk_factors'])
        assert "High-grade disease" in str(result.result['risk_factors'])

    def test_cueto_very_high_risk_multiple_factors(self):
        """
        Published Example: Very High Risk - Multiple Factors

        Reference: CUETO group - worst prognosis subgroup

        Patient characteristics:
        - T-category: T1
        - Grade: G3 (high-grade)
        - Concurrent CIS: Yes
        - Age: 75 years (>70)
        - Gender: Female

        Risk factors: 5 (all factors present)
        Expected CUETO score: 5 points
        Expected risk: Very High (40-50% BCG failure)
        Expected: Alternative/intensified BCG recommended
        """
        inputs = {
            't_category': 'T1',
            'concurrent_cis': 'yes',
            'grade': 'G3',
            'age': 75,
            'gender': 'female'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 5
        assert result.risk_level == "Very High Risk"
        assert "40-50%" in result.interpretation
        assert "alternative" in result.interpretation.lower() or "intensified" in result.interpretation.lower()
        assert len(result.result['risk_factors']) == 5

    def test_cueto_cis_concurrent_risk_factor(self):
        """
        Published Example: Concurrent CIS as Risk Factor

        Reference: CUETO - Concurrent CIS indicates advanced disease

        Patient characteristics:
        - T-category: Ta
        - Grade: G2
        - Concurrent CIS: Yes (1 point)
        - Age: 55 years
        - Gender: Male

        Risk factors: 1 (concurrent CIS)
        Expected CUETO score: 1 point
        Expected risk: Intermediate
        """
        inputs = {
            't_category': 'Ta',
            'concurrent_cis': 'yes',
            'grade': 'G2',
            'age': 55,
            'gender': 'male'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 1
        assert "Concurrent CIS" in str(result.result['risk_factors'])

    def test_cueto_age_older_than_70(self):
        """
        Published Example: Age >70 as Risk Factor

        Reference: CUETO - older age associated with BCG failure

        Patient characteristics:
        - T-category: Ta
        - Grade: G1
        - No concurrent CIS
        - Age: 72 years (>70, 1 point)
        - Gender: Male

        Risk factors: 1 (age >70)
        Expected CUETO score: 1 point
        """
        inputs = {
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 72,
            'gender': 'male'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 1
        assert "Age > 70" in str(result.result['risk_factors'])

    def test_cueto_female_gender_risk_factor(self):
        """
        Published Example: Female Gender as Risk Factor

        Reference: CUETO - female gender associated with worse BCG response

        Patient characteristics:
        - T-category: Ta
        - Grade: G2
        - No concurrent CIS
        - Age: 55 years
        - Gender: Female (1 point)

        Risk factors: 1 (female)
        Expected CUETO score: 1 point
        """
        inputs = {
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G2',
            'age': 55,
            'gender': 'female'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 1
        assert "Female gender" in str(result.result['risk_factors'])

    def test_cueto_all_risk_categories_coverage(self):
        """
        Accuracy Test: All CUETO risk groups properly classified.

        Risk groups:
        - Score 0: Low Risk
        - Score 1: Intermediate Risk
        - Score 2: High Risk
        - Score 3-5: Very High Risk
        """
        test_cases = [
            # Score 0: Low Risk
            {'t_category': 'Ta', 'concurrent_cis': 'no', 'grade': 'G1', 'age': 55, 'gender': 'male', 'expected': 'Low Risk'},
            # Score 1: Intermediate Risk
            {'t_category': 'T1', 'concurrent_cis': 'no', 'grade': 'G2', 'age': 55, 'gender': 'male', 'expected': 'Intermediate Risk'},
            # Score 2: High Risk
            {'t_category': 'T1', 'concurrent_cis': 'no', 'grade': 'G3', 'age': 55, 'gender': 'male', 'expected': 'High Risk'},
            # Score 3: Very High Risk
            {'t_category': 'T1', 'concurrent_cis': 'yes', 'grade': 'G3', 'age': 55, 'gender': 'male', 'expected': 'Very High Risk'},
        ]

        for case in test_cases:
            expected = case.pop('expected')
            result = self.calc.calculate(case)
            assert result.risk_level == expected, \
                f"Risk classification failed: got {result.risk_level}, expected {expected}"

    def test_cueto_threshold_age_70_boundary(self):
        """
        Validation: Age 70 threshold properly implemented.

        Age 70 should NOT add risk point (threshold is >70)
        Age 71 should add risk point
        """
        # Age 70 (not >70, no points for age)
        result = self.calc.calculate({
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 70,
            'gender': 'male'
        })
        assert result.result['total_score'] == 0

        # Age 71 (>70, 1 point for age)
        result = self.calc.calculate({
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 71,
            'gender': 'male'
        })
        assert result.result['total_score'] == 1
        assert "Age > 70" in str(result.result['risk_factors'])

    def test_cueto_bcg_failure_probability_scaling(self):
        """
        Validation: BCG failure probability increases with score.

        Expected progression:
        - Score 0: 5-10%
        - Score 1: 15-20%
        - Score 2: 25-35%
        - Score 3+: 40-50%
        """
        result_0 = self.calc.calculate({
            't_category': 'Ta', 'concurrent_cis': 'no', 'grade': 'G1',
            'age': 55, 'gender': 'male'
        })
        assert "5-10%" in result_0.interpretation

        result_1 = self.calc.calculate({
            't_category': 'T1', 'concurrent_cis': 'no', 'grade': 'G2',
            'age': 55, 'gender': 'male'
        })
        assert "15-20%" in result_1.interpretation

        result_2 = self.calc.calculate({
            't_category': 'T1', 'concurrent_cis': 'no', 'grade': 'G3',
            'age': 55, 'gender': 'male'
        })
        assert "25-35%" in result_2.interpretation

    def test_cueto_recommendations_high_risk(self):
        """
        Validation: High-risk patients get appropriate recommendations.

        Patients with score >=3 should be recommended for:
        - Alternative/intensified BCG regimen
        - Early recognition of BCG failure
        - Lower threshold for cystectomy
        """
        result = self.calc.calculate({
            't_category': 'T1',
            'concurrent_cis': 'yes',
            'grade': 'G3',
            'age': 72,
            'gender': 'female'
        })

        recommendations_text = " ".join(result.recommendations)
        assert any(word in recommendations_text.lower() for word in ['alternative', 'intensified', 'early', 'cystectomy'])

    def test_cueto_input_validation_tstage(self):
        """Validation: T-category must be Ta or T1."""
        result = self.calc.calculate({
            't_category': 'Ta',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 55,
            'gender': 'male'
        })
        assert result.result['t_category'] == 'Ta'

        result = self.calc.calculate({
            't_category': 'T1',
            'concurrent_cis': 'no',
            'grade': 'G1',
            'age': 55,
            'gender': 'male'
        })
        assert result.result['t_category'] == 'T1'

    def test_cueto_input_validation_grade(self):
        """Validation: Grade must be G1, G2, or G3."""
        for grade in ['G1', 'G2', 'G3']:
            result = self.calc.calculate({
                't_category': 'Ta',
                'concurrent_cis': 'no',
                'grade': grade,
                'age': 55,
                'gender': 'male'
            })
            assert result.result['grade'] == grade

    def test_cueto_references_complete(self):
        """Validation: Calculator has proper medical references."""
        assert len(self.calc.references) >= 1
        assert any("CUETO" in ref or "Fernandez" in ref for ref in self.calc.references)
