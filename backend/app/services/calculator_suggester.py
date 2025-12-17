"""
Calculator Suggestion Engine

Suggests relevant clinical calculators based on extracted entities.
"""

import logging
from typing import Dict, List, Any, Optional
from calculators.registry import CalculatorRegistry

logger = logging.getLogger(__name__)


class CalculatorSuggester:
    """Suggest calculators based on available clinical data."""

    # Map calculators to their required inputs
    CALCULATOR_REQUIREMENTS = {
        # Prostate Cancer Calculators
        'capra_score': {
            'category': 'prostate',
            'name': 'CAPRA Score',
            'required': ['psa', 'age', 'gleason_primary', 'gleason_secondary', 'clinical_stage', 'percent_positive_cores'],
            'optional': [],
            'description': 'Predicts recurrence-free survival after prostatectomy'
        },
        'pcptcalculator': {
            'category': 'prostate',
            'name': 'PCPT Risk Calculator',
            'required': ['age', 'psa', 'dre_abnormal', 'african_american', 'family_history', 'prior_negative_biopsy'],
            'optional': [],
            'description': 'Estimates risk of prostate cancer on biopsy'
        },
        'nccn_risk': {
            'category': 'prostate',
            'name': 'NCCN Risk Stratification',
            'required': ['psa', 'gleason_primary', 'gleason_secondary', 'clinical_stage'],
            'optional': ['percent_positive_cores'],
            'description': 'NCCN prostate cancer risk classification'
        },
        'psa_kinetics': {
            'category': 'prostate',
            'name': 'PSA Kinetics',
            'required': ['psa_values', 'time_points'],
            'optional': ['prostate_volume_cc'],
            'description': 'Calculate PSA velocity, doubling time, and density'
        },
        'phi_score': {
            'category': 'prostate',
            'name': 'Prostate Health Index (PHI)',
            'required': ['psa', 'free_psa', 'p2psa'],
            'optional': [],
            'description': 'Enhanced prostate cancer risk assessment'
        },
        'free_psa': {
            'category': 'prostate',
            'name': 'Free PSA Ratio',
            'required': ['psa', 'free_psa'],
            'optional': [],
            'description': 'Assess probability of prostate cancer'
        },

        # Kidney Cancer Calculators
        'ssign_score': {
            'category': 'kidney',
            'name': 'SSIGN Score',
            'required': ['tumor_size_cm', 'tnm_stage', 'nuclear_grade', 'tumor_necrosis'],
            'optional': [],
            'description': 'Predict cancer-specific survival for RCC'
        },
        'imdc_criteria': {
            'category': 'kidney',
            'name': 'IMDC Criteria',
            'required': ['karnofsky_score', 'hemoglobin', 'calcium', 'neutrophils', 'platelets', 'time_from_diagnosis'],
            'optional': [],
            'description': 'Prognostic model for metastatic RCC'
        },
        'renal_score': {
            'category': 'kidney',
            'name': 'RENAL Nephrometry Score',
            'required': ['tumor_size_cm', 'tumor_location', 'nearness_to_sinus'],
            'optional': [],
            'description': 'Assess renal mass complexity for partial nephrectomy'
        },
        'leibovich_score': {
            'category': 'kidney',
            'name': 'Leibovich Score',
            'required': ['tumor_size_cm', 'tnm_stage', 'nuclear_grade', 'tumor_necrosis'],
            'optional': [],
            'description': 'Predict metastatic progression after nephrectomy'
        },

        # Bladder Cancer Calculators
        'eortc_recurrence': {
            'category': 'bladder',
            'name': 'EORTC Recurrence Risk',
            'required': ['num_tumors', 'tumor_size_cm', 'prior_recurrence', 't_category', 'cis_present', 'tumor_grade'],
            'optional': [],
            'description': 'Predict bladder cancer recurrence risk'
        },
        'eortc_progression': {
            'category': 'bladder',
            'name': 'EORTC Progression Risk',
            'required': ['num_tumors', 'tumor_size_cm', 'prior_recurrence', 't_category', 'cis_present', 'tumor_grade'],
            'optional': [],
            'description': 'Predict bladder cancer progression risk'
        },
        'cueto_score': {
            'category': 'bladder',
            'name': 'Cueto BCG Score',
            'required': ['age', 'prior_recurrence', 'num_tumors', 'tumor_grade'],
            'optional': [],
            'description': 'Predict BCG failure in bladder cancer'
        },

        # Voiding Dysfunction
        'iciq': {
            'category': 'voiding',
            'name': 'ICIQ Score',
            'required': ['frequency', 'amount', 'impact'],
            'optional': [],
            'description': 'Incontinence impact assessment'
        },

        # Surgical Risk
        'rcri': {
            'category': 'surgical',
            'name': 'Revised Cardiac Risk Index',
            'required': ['risk_factors_count'],
            'optional': [],
            'description': 'Perioperative cardiac risk assessment'
        },
        'clavien_dindo': {
            'category': 'surgical',
            'name': 'Clavien-Dindo Classification',
            'required': ['complication_grade'],
            'optional': [],
            'description': 'Surgical complication severity grading'
        },
        'cci': {
            'category': 'surgical',
            'name': 'Charlson Comorbidity Index',
            'required': ['age', 'comorbidities'],
            'optional': [],
            'description': '10-year mortality prediction'
        },
        'lifeexpectancycalculator': {
            'category': 'surgical',
            'name': 'Actuarial 10-Year Survival Calculator',
            'required': ['age', 'gender', 'health_status', 'comorbidities'],
            'optional': [],
            'description': 'Estimate life expectancy using actuarial tables'
        },
    }

    def __init__(self):
        """Initialize calculator suggester."""
        self.registry = CalculatorRegistry()

    def suggest_calculators(self, extracted_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Suggest calculators based on extracted entities.

        Args:
            extracted_entities: List of extracted clinical entities

        Returns:
            List of calculator suggestions with confidence and missing inputs
        """
        # Build entity lookup dict
        entity_dict = {e['field']: e['value'] for e in extracted_entities}
        suggestions = []

        for calc_id, requirements in self.CALCULATOR_REQUIREMENTS.items():
            suggestion = self._evaluate_calculator(calc_id, requirements, entity_dict)
            if suggestion:
                suggestions.append(suggestion)

        # Sort by confidence (high -> medium -> low)
        confidence_order = {'high': 0, 'medium': 1, 'low': 2}
        suggestions.sort(key=lambda x: confidence_order.get(x['confidence'], 3))

        return suggestions

    def _evaluate_calculator(
        self,
        calc_id: str,
        requirements: Dict[str, Any],
        entity_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Evaluate if a calculator should be suggested."""

        required_inputs = requirements['required']
        optional_inputs = requirements.get('optional', [])
        all_inputs = required_inputs + optional_inputs

        # Check which inputs are available
        available_inputs = [inp for inp in all_inputs if inp in entity_dict]
        missing_required = [inp for inp in required_inputs if inp not in entity_dict]
        missing_optional = [inp for inp in optional_inputs if inp not in entity_dict]

        # Only suggest if at least some inputs are available
        if not available_inputs:
            return None

        # Determine confidence level
        if not missing_required:
            confidence = 'high'
            auto_selected = True
            reason = 'All required inputs detected'
        elif len(available_inputs) >= len(required_inputs) * 0.5:
            confidence = 'medium'
            auto_selected = False
            reason = f'Missing {len(missing_required)} required input(s)'
        else:
            confidence = 'low'
            auto_selected = False
            reason = f'Insufficient data detected ({len(available_inputs)}/{len(required_inputs)} required)'

        # Extract detected entity values
        detected_entities = {k: entity_dict[k] for k in available_inputs}

        return {
            'calculator_id': calc_id,
            'calculator_name': requirements['name'],
            'category': requirements['category'],
            'confidence': confidence,
            'auto_selected': auto_selected,
            'reason': reason,
            'required_inputs': required_inputs,
            'available_inputs': available_inputs,
            'missing_inputs': missing_required + missing_optional,
            'detected_entities': detected_entities
        }


# Singleton instance
_suggester = None

def get_calculator_suggester() -> CalculatorSuggester:
    """Get singleton calculator suggester instance."""
    global _suggester
    if _suggester is None:
        _suggester = CalculatorSuggester()
    return _suggester
