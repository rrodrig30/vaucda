"""Medical validation tests for RENAL Nephrometry Score.

References:
1. Kutikov A, Uzzo RG. The RENAL Nephrometry Score: a comprehensive standardized
   system for quantitating renal tumor complexity. J Urol. 2009;182(3):844-853.
2. Simmons MN, et al. Kidney tumor location measurement using the C index method.
   J Urol. 2010;183(5):1708-1713.
3. Ficarra V, et al. Preoperative aspects and dimensions used for an anatomical
   (PADUA) classification of renal tumours in patients who are candidates for
   nephron-sparing surgery. Eur Urol. 2009;56(5):786-793.
"""

import pytest
from calculators.kidney.renal_score import RENALScoreCalculator


class TestRENALScoreMedicalValidation:
    """Validate RENAL Score calculator against published clinical examples."""

    def setup_method(self):
        """Set up test calculator instance."""
        self.calc = RENALScoreCalculator()

    def test_kutikov_2009_example_low_complexity(self):
        """
        Published Example: Low Complexity Renal Mass

        Reference: Kutikov A, Uzzo RG. J Urol 2009;182:844-853, Figure 2A

        Renal mass characteristics:
        - Radius: 3 cm (≤4 cm) = 1 point
        - Exophytic: ≥50% exophytic = 1 point
        - Nearness: ≥7 mm from collecting system = 1 point
        - Location: Entirely below polar line = 1 point

        Expected RENAL Score: 4 points
        Expected Complexity: Low (4-6 points)
        Expected Surgical Consideration: Nephron-sparing surgery likely feasible
        """
        inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'anterior_posterior': 'posterior',
            'hilar': 'no'
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['total_score'] == 4, \
            f"Expected RENAL score 4, got {result.result['total_score']}"

        # Validate complexity classification
        assert result.result['complexity'] == "Low", \
            f"Expected 'Low' complexity, got '{result.result['complexity']}'"

        # Validate risk level
        assert result.risk_level == "Low", \
            f"Expected 'Low' risk level, got '{result.risk_level}'"

    def test_kutikov_2009_example_moderate_complexity(self):
        """
        Published Example: Moderate Complexity Renal Mass

        Reference: Kutikov A, Uzzo RG. J Urol 2009;182:844-853, Figure 2B

        Renal mass characteristics:
        - Radius: 5 cm (>4 to <7 cm) = 2 points
        - Exophytic: <50% exophytic = 2 points
        - Nearness: >4 to <7 mm = 2 points
        - Location: Crosses polar line = 2 points

        Expected RENAL Score: 8 points
        Expected Complexity: Moderate (7-9 points)
        Expected Surgical Consideration: Nephron-sparing surgery feasible
        """
        inputs = {
            'radius_points': 2,
            'exophytic_points': 2,
            'nearness_points': 2,
            'location_points': 2,
            'anterior_posterior': 'anterior',
            'hilar': 'no'
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['total_score'] == 8, \
            f"Expected RENAL score 8, got {result.result['total_score']}"

        # Validate complexity classification
        assert result.result['complexity'] == "Moderate", \
            f"Expected 'Moderate' complexity, got '{result.result['complexity']}'"

        # Validate risk level
        assert result.risk_level == "Intermediate", \
            f"Expected 'Intermediate' risk level, got '{result.risk_level}'"

    def test_kutikov_2009_example_high_complexity(self):
        """
        Published Example: High Complexity Renal Mass

        Reference: Kutikov A, Uzzo RG. J Urol 2009;182:844-853, Figure 2C

        Renal mass characteristics:
        - Radius: 8 cm (≥7 cm) = 3 points
        - Exophytic: Entirely endophytic = 3 points
        - Nearness: ≤4 mm from collecting system = 3 points
        - Location: >50% crosses midline = 3 points

        Expected RENAL Score: 12 points (maximum)
        Expected Complexity: High (10-12 points)
        Expected Surgical Consideration: Consider radical nephrectomy
        """
        inputs = {
            'radius_points': 3,
            'exophytic_points': 3,
            'nearness_points': 3,
            'location_points': 3,
            'anterior_posterior': 'indeterminate',
            'hilar': 'no'
        }

        result = self.calc.calculate(inputs)

        # Validate score
        assert result.result['total_score'] == 12, \
            f"Expected RENAL score 12, got {result.result['total_score']}"

        # Validate complexity classification
        assert result.result['complexity'] == "High", \
            f"Expected 'High' complexity, got '{result.result['complexity']}'"

        # Validate risk level
        assert result.risk_level == "High", \
            f"Expected 'High' risk level, got '{result.risk_level}'"

    def test_score_component_radius(self):
        """
        Validate radius scoring component.

        Radius Scoring (Kutikov et al. 2009):
        - ≤4 cm: 1 point
        - >4 to <7 cm: 2 points
        - ≥7 cm: 3 points
        """
        base_inputs = {
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'anterior_posterior': 'anterior',
            'hilar': 'no'
        }

        radius_test_cases = [
            (1, 4, "Low"),      # ≤4 cm → 4 total points
            (2, 5, "Low"),      # >4 to <7 cm → 5 total points
            (3, 6, "Low"),      # ≥7 cm → 6 total points (still low)
        ]

        for radius_pts, expected_total, expected_complexity in radius_test_cases:
            inputs = {**base_inputs, 'radius_points': radius_pts}
            result = self.calc.calculate(inputs)

            assert result.result['total_score'] == expected_total, \
                f"Radius {radius_pts}pts: Expected total {expected_total}, got {result.result['total_score']}"
            assert result.result['complexity'] == expected_complexity, \
                f"Radius {radius_pts}pts: Expected '{expected_complexity}', got '{result.result['complexity']}'"

    def test_score_component_exophytic(self):
        """
        Validate exophytic/endophytic scoring component.

        Exophytic Scoring (Kutikov et al. 2009):
        - ≥50% exophytic: 1 point
        - <50% exophytic: 2 points
        - Entirely endophytic: 3 points
        """
        base_inputs = {
            'radius_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'anterior_posterior': 'posterior',
            'hilar': 'no'
        }

        exo_test_cases = [
            (1, 4),  # ≥50% exophytic
            (2, 5),  # <50% exophytic
            (3, 6),  # Entirely endophytic
        ]

        for exo_pts, expected_total in exo_test_cases:
            inputs = {**base_inputs, 'exophytic_points': exo_pts}
            result = self.calc.calculate(inputs)

            assert result.result['total_score'] == expected_total, \
                f"Exophytic {exo_pts}pts: Expected {expected_total}, got {result.result['total_score']}"

    def test_score_component_nearness(self):
        """
        Validate nearness to collecting system scoring.

        Nearness Scoring (Kutikov et al. 2009):
        - ≥7 mm: 1 point
        - >4 to <7 mm: 2 points
        - ≤4 mm: 3 points
        """
        base_inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'location_points': 1,
            'hilar': 'no'
        }

        near_test_cases = [
            (1, 4),  # ≥7 mm
            (2, 5),  # >4 to <7 mm
            (3, 6),  # ≤4 mm
        ]

        for near_pts, expected_total in near_test_cases:
            inputs = {**base_inputs, 'nearness_points': near_pts}
            result = self.calc.calculate(inputs)

            assert result.result['total_score'] == expected_total, \
                f"Nearness {near_pts}pts: Expected {expected_total}, got {result.result['total_score']}"

    def test_score_component_location(self):
        """
        Validate location relative to polar lines scoring.

        Location Scoring (Kutikov et al. 2009):
        - Entirely above/below polar line: 1 point
        - Crosses polar line: 2 points
        - >50% crosses midline or between polar lines: 3 points
        """
        base_inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'hilar': 'no'
        }

        loc_test_cases = [
            (1, 4),  # Entirely above/below
            (2, 5),  # Crosses polar line
            (3, 6),  # >50% crosses midline
        ]

        for loc_pts, expected_total in loc_test_cases:
            inputs = {**base_inputs, 'location_points': loc_pts}
            result = self.calc.calculate(inputs)

            assert result.result['total_score'] == expected_total, \
                f"Location {loc_pts}pts: Expected {expected_total}, got {result.result['total_score']}"

    def test_complexity_stratification_boundaries(self):
        """
        Validate complexity classification boundaries.

        Complexity Classification (Kutikov et al. 2009):
        - Low: 4-6 points
        - Moderate: 7-9 points
        - High: 10-12 points
        """
        base_inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'hilar': 'no'
        }

        # Low complexity boundaries
        # Score 4 (minimum)
        result_4 = self.calc.calculate(base_inputs)
        assert result_4.result['complexity'] == "Low"

        # Score 6 (low-moderate boundary)
        inputs_6 = {**base_inputs, 'radius_points': 3}
        result_6 = self.calc.calculate(inputs_6)
        assert result_6.result['complexity'] == "Low"

        # Score 7 (moderate threshold)
        inputs_7 = {**base_inputs, 'radius_points': 2, 'exophytic_points': 2, 'nearness_points': 2}
        result_7 = self.calc.calculate(inputs_7)
        assert result_7.result['complexity'] == "Moderate"

        # Score 9 (moderate-high boundary)
        inputs_9 = {**base_inputs, 'radius_points': 3, 'exophytic_points': 2, 'nearness_points': 2}
        result_9 = self.calc.calculate(inputs_9)
        assert result_9.result['complexity'] == "Moderate"

        # Score 10 (high threshold)
        inputs_10 = {**base_inputs, 'radius_points': 3, 'exophytic_points': 3, 'nearness_points': 2, 'location_points': 2}
        result_10 = self.calc.calculate(inputs_10)
        assert result_10.result['complexity'] == "High"

        # Score 12 (maximum)
        inputs_12 = {**base_inputs, 'radius_points': 3, 'exophytic_points': 3, 'nearness_points': 3, 'location_points': 3}
        result_12 = self.calc.calculate(inputs_12)
        assert result_12.result['complexity'] == "High"

    def test_hilar_involvement_modifier(self):
        """
        Validate hilar involvement designation.

        Hilar Involvement (Kutikov et al. 2009):
        - Suffix 'h' indicates hilar involvement
        - Increases surgical complexity
        - Does not affect numerical score
        """
        base_inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1
        }

        # Without hilar involvement
        result_no_hilar = self.calc.calculate({**base_inputs, 'hilar': 'no'})
        score_no_hilar = result_no_hilar.result['total_score']

        # With hilar involvement
        result_with_hilar = self.calc.calculate({**base_inputs, 'hilar': 'yes'})
        score_with_hilar = result_with_hilar.result['total_score']

        # Score should be the same (hilar is a suffix, not scored)
        assert score_no_hilar == score_with_hilar == 4, \
            "Hilar involvement should not change numerical score"

        # But interpretation should note increased complexity
        assert "hilar" in result_with_hilar.interpretation.lower(), \
            "Interpretation should mention hilar involvement"

    def test_anterior_posterior_designation(self):
        """
        Validate anterior/posterior designation.

        A/P Designation (Kutikov et al. 2009):
        - Suffix 'a' (anterior) or 'p' (posterior)
        - Helps with surgical approach planning
        - Does not affect numerical score
        """
        base_inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'hilar': 'no'
        }

        for ap_location in ['anterior', 'posterior', 'indeterminate']:
            result = self.calc.calculate({**base_inputs, 'anterior_posterior': ap_location})

            assert result.result['total_score'] == 4, \
                f"A/P designation '{ap_location}' should not change score"
            assert result.result['anterior_posterior'] == ap_location, \
                f"A/P designation not recorded correctly"

    def test_clinical_scenario_nephron_sparing_candidate(self):
        """
        Clinical Scenario: Ideal Nephron-Sparing Surgery Candidate

        Patient: 58-year-old with 3.5 cm exophytic lower pole mass
        - Radius: 3.5 cm (≤4 cm) = 1 point
        - Exophytic: 60% exophytic (≥50%) = 1 point
        - Nearness: 8 mm from collecting system (≥7 mm) = 1 point
        - Location: Entirely below lower polar line = 1 point
        - A/P: Posterior
        - Hilar: No

        Expected RENAL Score: 4p
        Expected Complexity: Low
        Recommendation: Nephron-sparing surgery likely feasible
        """
        inputs = {
            'radius_points': 1,
            'exophytic_points': 1,
            'nearness_points': 1,
            'location_points': 1,
            'anterior_posterior': 'posterior',
            'hilar': 'no'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 4
        assert result.result['complexity'] == "Low"
        assert result.risk_level == "Low"
        assert any("nephron-sparing" in rec.lower() for rec in result.recommendations)

    def test_clinical_scenario_radical_nephrectomy_consideration(self):
        """
        Clinical Scenario: Complex Mass Warranting Radical Nephrectomy Consideration

        Patient: 72-year-old with 9 cm centrally located endophytic mass
        - Radius: 9 cm (≥7 cm) = 3 points
        - Exophytic: Entirely endophytic = 3 points
        - Nearness: 2 mm from collecting system (≤4 mm) = 3 points
        - Location: >50% crosses midline = 3 points
        - A/P: Indeterminate
        - Hilar: Yes

        Expected RENAL Score: 12xh (maximum complexity with hilar involvement)
        Expected Complexity: High
        Recommendation: Consider radical nephrectomy
        """
        inputs = {
            'radius_points': 3,
            'exophytic_points': 3,
            'nearness_points': 3,
            'location_points': 3,
            'anterior_posterior': 'indeterminate',
            'hilar': 'yes'
        }

        result = self.calc.calculate(inputs)

        assert result.result['total_score'] == 12
        assert result.result['complexity'] == "High"
        assert result.risk_level == "High"
        assert result.result['hilar_involvement'] == "yes"
        assert any("hilar" in rec.lower() or "radical" in rec.lower() for rec in result.recommendations)

    def test_accuracy_threshold_all_scenarios(self):
        """
        Verify calculator achieves >99% accuracy across all clinical scenarios.

        Medium-stakes calculator requirement: >99% accuracy
        """
        published_scenarios = [
            # (inputs, expected_score, expected_complexity)
            (
                {'radius_points': 1, 'exophytic_points': 1, 'nearness_points': 1, 'location_points': 1, 'hilar': 'no'},
                4, 'Low'
            ),
            (
                {'radius_points': 2, 'exophytic_points': 2, 'nearness_points': 2, 'location_points': 2, 'hilar': 'no'},
                8, 'Moderate'
            ),
            (
                {'radius_points': 3, 'exophytic_points': 3, 'nearness_points': 3, 'location_points': 3, 'hilar': 'no'},
                12, 'High'
            ),
        ]

        correct = 0
        total = len(published_scenarios)

        for inputs, expected_score, expected_complexity in published_scenarios:
            result = self.calc.calculate(inputs)

            if (result.result['total_score'] == expected_score and
                result.result['complexity'] == expected_complexity):
                correct += 1

        accuracy = (correct / total) * 100
        assert accuracy >= 99, \
            f"Accuracy {accuracy:.1f}% below required 99% threshold"
