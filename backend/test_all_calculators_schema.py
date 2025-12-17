#!/usr/bin/env python3
"""
Comprehensive test script to verify all 50 calculators have working get_input_schema() implementations.
Tests that all calculators can be instantiated and return valid InputMetadata with correct InputType enum values.
"""

import sys
import traceback
from typing import Dict, List, Any

# Import all calculator classes
from calculators.bladder.bladder_cancer_risk import BladderCancerRiskCalculator
from calculators.bladder.eortc_recurrence import EORTCRecurrenceCalculator
from calculators.bladder.eortc_progression import EORTCProgressionCalculator
from calculators.bladder.cueto_recurrence import CuetoRecurrenceCalculator
from calculators.bladder.cueto_progression import CuetoProgressionCalculator

from calculators.kidney.renal_nephrometry import RenalNephrometryCalculator
from calculators.kidney.chromophobe_score import ChromophobeScoreCalculator
from calculators.kidney.leibovich_ccRCC import LeibovichCalculator
from calculators.kidney.ssign_rcc import SSIGNCalculator
from calculators.kidney.uiss_rcc import UISSCalculator

from calculators.prostate.capra import CAPRACalculator
from calculators.prostate.dAmico import DAmicoCalculator
from calculators.prostate.mskcc_nomogram import MSKCCNomogramCalculator
from calculators.prostate.nccn_risk import NCCNRiskCalculator
from calculators.prostate.partin_tables import PartinTablesCalculator
from calculators.prostate.psa_density import PSADensityCalculator
from calculators.prostate.psa_kinetics import PSAKineticsCalculator

from calculators.stones.guy_stone_score import GuyStoneScoreCalculator
from calculators.stones.resorlu_scoring import ResorluScoringCalculator
from calculators.stones.s_reSC import SRESCCalculator
from calculators.stones.stone_size import StoneSizeCalculator
from calculators.stones.stone_complexity import StoneComplexityCalculator

from calculators.testicular.igcccg_risk import IGCCCGRiskCalculator

from calculators.incontinence.iciq_ui_sf import ICIQUIShortFormCalculator

from calculators.general.bmi import BMICalculator
from calculators.general.egfr import EGFRCalculator
from calculators.general.asa_classification import ASAClassificationCalculator

from calculators.surgical.cci import CCICalculator
from calculators.surgical.clavien_dindo import ClavienDindoCalculator
from calculators.surgical.eras_compliance import ERASComplianceCalculator
from calculators.surgical.nsqip import NSQIPCalculator

from calculators.pediatric.vcug_grading import VCUGGradingCalculator

from calculators.functional.auasi import AUASICalculator
from calculators.functional.ipss import IPSSCalculator
from calculators.functional.iief import IIEFCalculator
from calculators.functional.overactive_bladder import OveractiveBladderCalculator

from calculators.infection.fournier_severity import FournierSeverityCalculator
from calculators.infection.uti_calculator import UTICalculator

from calculators.trauma.aast_kidney import AASTKidneyCalculator
from calculators.trauma.aast_bladder import AASTBladderCalculator
from calculators.trauma.aast_ureter import AASTUreterCalculator
from calculators.trauma.aast_urethra import AASTUrethraCalculator
from calculators.trauma.aast_testis import AASTTestisCalculator
from calculators.trauma.aast_penis import AASTPenisCalculator

from calculators.upper_tract.utuc_risk import UTUCRiskCalculator

from calculators.voiding.qmax import QmaxCalculator
from calculators.voiding.post_void_residual import PostVoidResidualCalculator

from calculators.base import InputType

# Valid InputType enum values
VALID_INPUT_TYPES = {
    InputType.NUMERIC,
    InputType.ENUM,
    InputType.BOOLEAN,
    InputType.TEXT,
    InputType.DATE,
}

# All 50 calculator classes
ALL_CALCULATORS = [
    # Bladder (5)
    BladderCancerRiskCalculator,
    EORTCRecurrenceCalculator,
    EORTCProgressionCalculator,
    CuetoRecurrenceCalculator,
    CuetoProgressionCalculator,

    # Kidney (5)
    RenalNephrometryCalculator,
    ChromophobeScoreCalculator,
    LeibovichCalculator,
    SSIGNCalculator,
    UISSCalculator,

    # Prostate (7)
    CAPRACalculator,
    DAmicoCalculator,
    MSKCCNomogramCalculator,
    NCCNRiskCalculator,
    PartinTablesCalculator,
    PSADensityCalculator,
    PSAKineticsCalculator,

    # Stones (5)
    GuyStoneScoreCalculator,
    ResorluScoringCalculator,
    SRESCCalculator,
    StoneSizeCalculator,
    StoneComplexityCalculator,

    # Testicular (1)
    IGCCCGRiskCalculator,

    # Incontinence (1)
    ICIQUIShortFormCalculator,

    # General (3)
    BMICalculator,
    EGFRCalculator,
    ASAClassificationCalculator,

    # Surgical (4)
    CCICalculator,
    ClavienDindoCalculator,
    ERASComplianceCalculator,
    NSQIPCalculator,

    # Pediatric (1)
    VCUGGradingCalculator,

    # Functional (4)
    AUASICalculator,
    IPSSCalculator,
    IIEFCalculator,
    OveractiveBladderCalculator,

    # Infection (2)
    FournierSeverityCalculator,
    UTICalculator,

    # Trauma (6)
    AASTKidneyCalculator,
    AASTBladderCalculator,
    AASTUreterCalculator,
    AASTUrethraCalculator,
    AASTTestisCalculator,
    AASTPenisCalculator,

    # Upper Tract (1)
    UTUCRiskCalculator,

    # Voiding (2)
    QmaxCalculator,
    PostVoidResidualCalculator,
]


def test_calculator(calculator_class) -> Dict[str, Any]:
    """
    Test a single calculator's get_input_schema() method.

    Returns:
        dict: Test results with keys: 'name', 'success', 'error', 'schema_count', 'invalid_types'
    """
    result = {
        'name': calculator_class.__name__,
        'success': False,
        'error': None,
        'schema_count': 0,
        'invalid_types': [],
    }

    try:
        # Instantiate the calculator
        calc = calculator_class()

        # Call get_input_schema()
        schema = calc.get_input_schema()

        # Verify schema is a list
        if not isinstance(schema, list):
            result['error'] = f"get_input_schema() returned {type(schema)}, expected list"
            return result

        result['schema_count'] = len(schema)

        # Verify each InputMetadata has valid InputType
        for i, metadata in enumerate(schema):
            if not hasattr(metadata, 'input_type'):
                result['error'] = f"InputMetadata at index {i} missing 'input_type' attribute"
                return result

            if metadata.input_type not in VALID_INPUT_TYPES:
                result['invalid_types'].append({
                    'index': i,
                    'field_name': metadata.field_name if hasattr(metadata, 'field_name') else 'UNKNOWN',
                    'invalid_type': str(metadata.input_type),
                })

        # If we got here with no invalid types, it's a success
        if not result['invalid_types']:
            result['success'] = True
        else:
            result['error'] = f"Found {len(result['invalid_types'])} invalid InputType values"

    except AttributeError as e:
        result['error'] = f"AttributeError: {str(e)}"
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
        result['traceback'] = traceback.format_exc()

    return result


def main():
    """Run comprehensive verification of all 50 calculators."""
    print("=" * 80)
    print("COMPREHENSIVE CALCULATOR SCHEMA VERIFICATION")
    print("=" * 80)
    print(f"\nTesting {len(ALL_CALCULATORS)} calculators...\n")

    results = []
    working_count = 0
    broken_count = 0

    # Test each calculator
    for calc_class in ALL_CALCULATORS:
        result = test_calculator(calc_class)
        results.append(result)

        if result['success']:
            working_count += 1
            print(f"✓ {result['name']}: OK ({result['schema_count']} inputs)")
        else:
            broken_count += 1
            print(f"✗ {result['name']}: FAILED")
            print(f"  Error: {result['error']}")
            if result['invalid_types']:
                for invalid in result['invalid_types']:
                    print(f"    - Field '{invalid['field_name']}': {invalid['invalid_type']}")
            if 'traceback' in result:
                print(f"  Traceback:\n{result['traceback']}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Calculators: {len(ALL_CALCULATORS)}")
    print(f"Working: {working_count}/{len(ALL_CALCULATORS)} ({working_count/len(ALL_CALCULATORS)*100:.1f}%)")
    print(f"Broken: {broken_count}/{len(ALL_CALCULATORS)} ({broken_count/len(ALL_CALCULATORS)*100:.1f}%)")

    if broken_count == 0:
        print("\n✓ ALL CALCULATORS PASS - PRODUCTION READY")
        return 0
    else:
        print(f"\n✗ {broken_count} CALCULATORS HAVE ISSUES - NOT PRODUCTION READY")
        print("\nBroken Calculators:")
        for result in results:
            if not result['success']:
                print(f"  - {result['name']}: {result['error']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
