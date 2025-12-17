#!/usr/bin/env python3
"""
Script to update all calculator test files with complete, medically accurate input parameters.
"""

from pathlib import Path
import re

# Complete medical input parameters for all calculators
CALCULATOR_INPUTS = {
    # Prostate Calculators
    'capra': {
        'psa': 5.0,
        'gleason_primary': 3,
        'gleason_secondary': 4,
        't_stage': 'T1c',
        'percent_positive_cores': 25
    },
    'pcpt_risk': {
        'age': 65,
        'psa': 5.0,
        'dre_abnormal': False,
        'african_american': False,
        'family_history': False,
        'prior_negative_biopsy': False
    },
    'nccn_risk': {
        'psa': 8.5,
        'grade_group': 2,
        't_stage': 'T2a'
    },
    'psa_kinetics': {
        'psa_values': [
            {'psa': 3.0, 'date': '2023-01-01'},
            {'psa': 4.2, 'date': '2023-07-01'},
            {'psa': 5.5, 'date': '2024-01-01'}
        ],
        'current_psa': 5.5,
        'prostate_volume': 45
    },
    'free_psa': {
        'total_psa': 6.5,
        'free_psa': 1.2
    },
    'phi_score': {
        'total_psa': 6.0,
        'free_psa': 1.0,
        'proPSA_p2': 20.5
    },
    'dre_volume': {
        'length_cm': 4.0,
        'width_cm': 3.5,
        'depth_cm': 3.0
    },

    # Kidney Calculators
    'ssign_score': {
        'tnm_stage': 'T1a',
        'tumor_size': 3.5,
        'nuclear_grade': 2,
        'necrosis': False
    },
    'imdc_criteria': {
        'kps': 80,
        'time_diagnosis_to_treatment_months': 6,
        'hemoglobin_g_dL': 11.5,
        'calcium_mg_dL': 10.5,
        'albumin_g_dL': 3.8,
        'neutrophils_K_uL': 4.5,
        'platelets_K_uL': 350
    },
    'renal_score': {
        'radius_points': 1,
        'exophytic_points': 2,
        'nearness_points': 1,
        'location_points': 1
    },
    'leibovich_score': {
        'fuhrman_grade': 2,
        'ecog_ps': 0,
        'stage': 'pT1',
        'tumor_size_cm': 4.5
    },

    # Bladder Calculators
    'eortc_recurrence': {
        'number_of_tumors': 2,
        'tumor_diameter_cm': 2.5,
        'prior_recurrence_rate': 'primary',
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low'
    },
    'eortc_progression': {
        'number_of_tumors': 2,
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low'
    },
    'cueto_score': {
        't_category': 'Ta',
        'concurrent_cis': False,
        'grade': 'low',
        'age': 68,
        'gender': 'male'
    },

    # Voiding Calculators
    'ipss': {
        'incomplete_emptying': 2,
        'frequency': 3,
        'intermittency': 1,
        'urgency': 2,
        'weak_stream': 3,
        'straining': 1,
        'nocturia': 2,
        'qol': 3
    },
    'uroflow': {
        'qmax': 15.5,
        'qave': 8.2,
        'voided_volume': 280,
        'flow_time': 32,
        'time_to_qmax': 8,
        'flow_pattern': 'normal'
    },
    'pvrua': {
        'pvr_volume_mL': 75
    },
    'booi_bci': {
        'pdet_qmax': 55,
        'qmax': 12
    },
    'iciq': {
        'frequency': 3,
        'amount': 2,
        'impact': 4
    },

    # Female Calculators
    'popq': {
        'aa': -2,
        'ba': -2,
        'c': -6,
        'd': -7,
        'ap': -2,
        'bp': -2,
        'gh': 3,
        'pb': 2,
        'tvl': 9
    },
    'udi6_iiq7': {
        'udi6_q1': 1,
        'udi6_q2': 2,
        'udi6_q3': 1,
        'udi6_q4': 2,
        'udi6_q5': 1,
        'udi6_q6': 0,
        'iiq7_q1': 1,
        'iiq7_q2': 2,
        'iiq7_q3': 1,
        'iiq7_q4': 1,
        'iiq7_q5': 2,
        'iiq7_q6': 1,
        'iiq7_q7': 1
    },
    'oabq': {
        'symptom_bother_score': 45,
        'qol_score': 35
    },
    'pfdi': {
        'popdi_scores': [2, 1, 2, 3, 1, 2],
        'cradi_scores': [1, 2, 1, 3, 2, 1, 2, 1],
        'udi_scores': [2, 1, 2, 3, 1, 2, 1, 2]
    },
    'mesa': {
        'obstruction_type': 'vasal',
        'previous_attempts': 0,
        'testicular_volume': 18
    },

    # Reconstructive Calculators
    'clavien_dindo': {
        'grade': 3  # Integer required, not string like 'IIIa'
    },
    'stricture_complexity': {
        'location_points': 1,
        'length_points': 2,
        'etiology_points': 1,
        'prior_tx_points': 1
    },
    'pfui_classification': {
        'injury_type': 'partial',
        'gap_length': 1.5
    },
    'peyronie_severity': {
        'curvature_degrees': 45,
        'erectile_dysfunction_degree': 'mild'
    },

    # Fertility Calculators
    'semen_analysis': {
        'volume': 3.5,
        'concentration': 45,
        'motility_progressive': 55,
        'morphology_normal': 8
    },
    'sperm_dna': {
        'dfi_percent': 18.5
    },
    'varicocele_grade': {
        'grade': 2
    },
    'mao': {
        'decreased_libido': True,
        'decreased_energy': True,
        'decreased_strength': False,
        'lost_height': False,
        'decreased_enjoyment': True,
        'sad_grumpy': False,
        'erections_less_strong': True,
        'sports_ability_decline': True,
        'falling_asleep': False,
        'decreased_work_performance': False
    },
    'testosterone_eval': {
        'total_testosterone': 285,
        'age': 52
    },

    # Hypogonadism Calculators
    'adam': {
        'q1_libido': True,
        'q7_erections': True,
        'positive_questions': 3
    },
    'tt_evaluation': {
        'total_testosterone': 320,
        'lh': 4.5,
        'fsh': 5.2
    },
    'hypogonadism_risk': {
        'symptoms_present': True,
        'total_testosterone': 290,
        'free_testosterone': 55
    },

    # Stones Calculators
    'stone_score': {
        'size_points': 2,
        'tract_points': 1,
        'obstruction_points': 1,
        'number_points': 1,
        'hematuria_points': 0
    },
    'stone_size': {
        'hounsfield_units': 950
    },
    'guy_score': {
        'size_points': 1,
        'density_points': 1,
        'location_points': 1
    },
    'urine_24hr': {
        'volume': 2.2,
        'calcium': 285,
        'citrate': 420,
        'uric_acid': 650
    },

    # Surgical Calculators
    'rcri': {
        'risk_factors_count': 2
    },
    'nsqip': {
        'procedure_cpt': '55866'
    },
    'cfs': {
        'cfs_score': 4  # Clinical Frailty Scale: 1-9 (4 = Very Mild Frailty)
    },
    'cci': {
        'age': 72,
        'comorbidities': ['diabetes', 'copd']
    },

    # Additional calculators not in main list
    'hormonal_eval': {
        'testosterone': 350,
        'fsh': 5.5,
        'lh': 4.8
    },
    'life_expectancy': {
        'age': 70,
        'gender': 'male',
        'comorbidities_score': 3
    },
    'sandvik_severity': {
        'frequency': 'daily',
        'amount': 'moderate'
    },
    'stress_ui_severity': {
        'stamey_grade': 2
    },
    'testicular_volume': {
        'length': 4.5,
        'width': 3.0,
        'height': 2.5
    }
}


def update_test_file(test_file_path: Path):
    """Update a single test file with complete inputs."""

    # Extract calculator name from test file name
    calc_name = test_file_path.stem.replace('test_', '')

    if calc_name not in CALCULATOR_INPUTS:
        print(f"⚠️  No input mapping for {calc_name}")
        return False

    inputs_dict = CALCULATOR_INPUTS[calc_name]

    # Read the test file
    content = test_file_path.read_text()

    # Format the inputs dictionary as Python code
    inputs_str = format_inputs(inputs_dict, indent=8)

    # Pattern to match the inputs = {...} lines in test methods
    # We need to replace inputs in three methods: test_basic_calculation, test_interpretation_present, test_risk_level_assigned

    methods_to_update = [
        'test_basic_calculation',
        'test_interpretation_present',
        'test_risk_level_assigned'
    ]

    updated = False
    for method_name in methods_to_update:
        # Pattern to find the method and its inputs
        pattern = rf"(def {method_name}\(self\):.*?)(inputs = \{{[^}}]*\}})"

        def replace_inputs(match):
            nonlocal updated
            updated = True
            method_def = match.group(1)
            return f"{method_def}inputs = {inputs_str}"

        content = re.sub(pattern, replace_inputs, content, flags=re.DOTALL)

    if updated:
        test_file_path.write_text(content)
        print(f"✓ Updated {calc_name}")
        return True
    else:
        print(f"⚠️  Could not update {calc_name}")
        return False


def format_inputs(inputs_dict, indent=8):
    """Format inputs dictionary as properly indented Python code."""

    lines = ['{']
    indent_str = ' ' * indent

    for key, value in inputs_dict.items():
        if isinstance(value, str):
            lines.append(f"{indent_str}'{key}': '{value}',")
        elif isinstance(value, bool):
            lines.append(f"{indent_str}'{key}': {value},")
        elif isinstance(value, list):
            if key == 'psa_values':
                # Special formatting for PSA values
                lines.append(f"{indent_str}'{key}': [")
                for item in value:
                    lines.append(f"{indent_str}    {item},")
                lines.append(f"{indent_str}],")
            else:
                # Regular list
                lines.append(f"{indent_str}'{key}': {value},")
        else:
            lines.append(f"{indent_str}'{key}': {value},")

    lines.append(' ' * (indent - 4) + '}')

    return '\n'.join(lines)


def main():
    """Update all test files."""

    test_dir = Path('tests/test_calculators')

    if not test_dir.exists():
        print(f"Error: {test_dir} does not exist")
        return

    test_files = sorted(test_dir.glob('test_*.py'))

    print(f"Found {len(test_files)} test files\n")

    updated_count = 0
    for test_file in test_files:
        if update_test_file(test_file):
            updated_count += 1

    print(f"\n✓ Updated {updated_count} / {len(test_files)} test files")


if __name__ == '__main__':
    main()
