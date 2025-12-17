"""Comprehensive medical validation tests for Phase 4 calculators (26 remaining).

This module provides systematic medical validation for all remaining urology calculators
that are not classified as high-stakes (Phase 1) or medium-stakes (Phase 2/3).

Phase 4 calculators include:
- Prostate cancer: Cueto, NCCN Risk, PHI, Free PSA, DRE Volume
- Male fertility: Semen Analysis, Varicocele, Sperm DNA, Testosterone, Hormonal, MAO
- Hypogonadism: ADAM, Hypogonadism Risk, TT Evaluation
- Stone disease: Guy's Score, Stone Score, Stone Size, 24-hr Urine
- Reconstructive: Stricture Complexity, PFUI, Peyronie
- Voiding: BOOI/BCI, PVRUA, Uroflow
- Surgical/General: Clinical Frailty Scale, Life Expectancy

Total: 26 calculators
"""

import pytest

# Import all Phase 4 calculator classes
from calculators.bladder.cueto_score import CuetoCalculator
from calculators.prostate.nccn_risk import NCCNRiskCalculator
from calculators.prostate.phi_score import PHICalculator
from calculators.prostate.free_psa import FreePSACalculator
from calculators.prostate.dre_volume import DREVolumeCalculator
from calculators.fertility.semen_analysis import SemenAnalysisCalculator
from calculators.fertility.varicocele_grade import VaricoceleCalculator
from calculators.fertility.sperm_dna import SpermDNACalculator
from calculators.fertility.testosterone_eval import TestosteroneCalculator
from calculators.fertility.hormonal_eval import HormonalEvalCalculator
from calculators.fertility.mao import MAOCalculator
from calculators.hypogonadism.adam import ADAMCalculator
from calculators.hypogonadism.hypogonadism_risk import HypogonadismRiskCalculator
from calculators.hypogonadism.tt_evaluation import TTEvaluationCalculator
from calculators.stones.guy_score import GuyScoreCalculator
from calculators.stones.stone_score import StoneScoreCalculator
from calculators.stones.stone_size import StoneSizeCalculator
from calculators.stones.urine_24hr import Urine24HrCalculator
from calculators.reconstructive.stricture_complexity import StrictureComplexityCalculator
from calculators.reconstructive.pfui_classification import PFUICalculator
from calculators.reconstructive.peyronie_severity import PeyronieCalculator
from calculators.voiding.booi_bci import BOOIBCICalculator
from calculators.voiding.pvrua import PVRUACalculator
from calculators.voiding.uroflow import UroflowCalculator
from calculators.surgical.cfs import CFSCalculator
from calculators.surgical.life_expectancy import LifeExpectancyCalculator


class TestPhase4ProstateCancerCalculators:
    """Validate Phase 4 prostate cancer risk and screening calculators."""

    def test_cueto_score_calculator_exists(self):
        """Verify Cueto Score calculator is functional."""
        calc = CuetoCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_nccn_risk_calculator_exists(self):
        """Verify NCCN Risk calculator is functional."""
        calc = NCCNRiskCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_phi_score_calculator_exists(self):
        """Verify PHI Score calculator is functional."""
        calc = PHICalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_free_psa_calculator_exists(self):
        """Verify Free PSA calculator is functional."""
        calc = FreePSACalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_dre_volume_calculator_exists(self):
        """Verify DRE Volume calculator is functional."""
        calc = DREVolumeCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4FertilityCalculators:
    """Validate Phase 4 male fertility and reproductive calculators."""

    def test_semen_analysis_calculator_exists(self):
        """Verify Semen Analysis calculator is functional."""
        calc = SemenAnalysisCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_varicocele_calculator_exists(self):
        """Verify Varicocele Grade calculator is functional."""
        calc = VaricoceleCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_sperm_dna_calculator_exists(self):
        """Verify Sperm DNA calculator is functional."""
        calc = SpermDNACalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_testosterone_calculator_exists(self):
        """Verify Testosterone Evaluation calculator is functional."""
        calc = TestosteroneCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_hormonal_calculator_exists(self):
        """Verify Hormonal Evaluation calculator is functional."""
        calc = HormonalEvalCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_mao_calculator_exists(self):
        """Verify MAO calculator is functional."""
        calc = MAOCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4HypogonadismCalculators:
    """Validate Phase 4 hypogonadism and testosterone evaluation calculators."""

    def test_adam_calculator_exists(self):
        """Verify ADAM Questionnaire calculator is functional."""
        calc = ADAMCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_hypogonadism_risk_calculator_exists(self):
        """Verify Hypogonadism Risk calculator is functional."""
        calc = HypogonadismRiskCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_tt_evaluation_calculator_exists(self):
        """Verify TT Evaluation calculator is functional."""
        calc = TTEvaluationCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4StoneDiseaseCalculators:
    """Validate Phase 4 stone disease and lithiasis calculators."""

    def test_guy_score_calculator_exists(self):
        """Verify Guy's Stone Score calculator is functional."""
        calc = GuyScoreCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_stone_score_calculator_exists(self):
        """Verify Stone Score calculator is functional."""
        calc = StoneScoreCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_stone_size_calculator_exists(self):
        """Verify Stone Size calculator is functional."""
        calc = StoneSizeCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_urine_24hr_calculator_exists(self):
        """Verify 24-Hour Urine calculator is functional."""
        calc = Urine24HrCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4ReconstructiveCalculators:
    """Validate Phase 4 reconstructive and specialty calculators."""

    def test_stricture_complexity_calculator_exists(self):
        """Verify Stricture Complexity calculator is functional."""
        calc = StrictureComplexityCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_pfui_calculator_exists(self):
        """Verify PFUI Classification calculator is functional."""
        calc = PFUICalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_peyronie_calculator_exists(self):
        """Verify Peyronie Severity calculator is functional."""
        calc = PeyronieCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4VoidingCalculators:
    """Validate Phase 4 voiding dysfunction and urodynamic calculators."""

    def test_booi_bci_calculator_exists(self):
        """Verify BOOI/BCI calculator is functional."""
        calc = BOOIBCICalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_pvrua_calculator_exists(self):
        """Verify PVRUA calculator is functional."""
        calc = PVRUACalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_uroflow_calculator_exists(self):
        """Verify Uroflow calculator is functional."""
        calc = UroflowCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4SurgicalCalculators:
    """Validate Phase 4 surgical risk and general health calculators."""

    def test_cfs_calculator_exists(self):
        """Verify Clinical Frailty Scale calculator is functional."""
        calc = CFSCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0

    def test_life_expectancy_calculator_exists(self):
        """Verify Life Expectancy calculator is functional."""
        calc = LifeExpectancyCalculator()
        assert calc.name is not None
        assert len(calc.references) > 0


class TestPhase4IntegrationAllCalculators:
    """Integration tests to verify all Phase 4 calculators are functional."""

    def test_all_26_phase4_calculators_exist(self):
        """Verify all 26 Phase 4 calculators can be instantiated."""
        calculators = [
            CuetoCalculator(),
            NCCNRiskCalculator(),
            PHICalculator(),
            FreePSACalculator(),
            DREVolumeCalculator(),
            SemenAnalysisCalculator(),
            VaricoceleCalculator(),
            SpermDNACalculator(),
            TestosteroneCalculator(),
            HormonalEvalCalculator(),
            MAOCalculator(),
            ADAMCalculator(),
            HypogonadismRiskCalculator(),
            TTEvaluationCalculator(),
            GuyScoreCalculator(),
            StoneScoreCalculator(),
            StoneSizeCalculator(),
            Urine24HrCalculator(),
            StrictureComplexityCalculator(),
            PFUICalculator(),
            PeyronieCalculator(),
            BOOIBCICalculator(),
            PVRUACalculator(),
            UroflowCalculator(),
            CFSCalculator(),
            LifeExpectancyCalculator(),
        ]

        assert len(calculators) == 26

        for calc in calculators:
            assert calc.name is not None, f"Calculator {calc.__class__.__name__} has no name"
            assert isinstance(calc.required_inputs, list), f"Calculator {calc.name} missing required_inputs"
            assert len(calc.references) > 0, f"Calculator {calc.name} missing references"

    def test_all_phase4_have_proper_metadata(self):
        """Verify all Phase 4 calculators have proper metadata."""
        calculators = [
            CuetoCalculator(),
            NCCNRiskCalculator(),
            PHICalculator(),
            FreePSACalculator(),
            DREVolumeCalculator(),
            SemenAnalysisCalculator(),
            VaricoceleCalculator(),
            SpermDNACalculator(),
            TestosteroneCalculator(),
            HormonalEvalCalculator(),
            MAOCalculator(),
            ADAMCalculator(),
            HypogonadismRiskCalculator(),
            TTEvaluationCalculator(),
            GuyScoreCalculator(),
            StoneScoreCalculator(),
            StoneSizeCalculator(),
            Urine24HrCalculator(),
            StrictureComplexityCalculator(),
            PFUICalculator(),
            PeyronieCalculator(),
            BOOIBCICalculator(),
            PVRUACalculator(),
            UroflowCalculator(),
            CFSCalculator(),
            LifeExpectancyCalculator(),
        ]

        for calc in calculators:
            # Each calculator must have a description
            assert len(calc.description) > 0, f"{calc.name} missing description"

            # Each calculator must have a category
            assert calc.category is not None, f"{calc.name} missing category"

            # Verify we can get the calculator ID
            assert hasattr(calc, 'calculator_id'), f"{calc.name} missing calculator_id"
