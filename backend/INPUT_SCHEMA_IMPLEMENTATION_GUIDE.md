# Input Schema Implementation Guide

## Progress Summary

### Completed Categories (17 Calculators)
- ✅ Bladder (3/3): cueto_score, eortc_progression, eortc_recurrence
- ✅ Female (7/7): mesa, oabq, pfdi, popq, sandvik_severity, stress_ui_severity, udi6_iiq7
- ✅ Fertility (7/7): hormonal_eval, mao, semen_analysis, sperm_dna, testicular_volume, testosterone_eval, varicocele_grade
- ✅ Hypogonadism (3/3): adam, hypogonadism_risk, tt_evaluation

### Remaining Categories (31 Calculators)
- Kidney (4): imdc_criteria, leibovich_score, renal_score, ssign_score
- Prostate (6): dre_volume, free_psa, nccn_risk, pcpt_risk, phi_score, psa_kinetics
- Reconstructive (4): clavien_dindo, peyronie_severity, pfui_classification, stricture_complexity
- Stones (4): guy_score, stone_score, stone_size, urine_24hr
- Surgical (5): cci, cfs, life_expectancy, nsqip, rcri
- Voiding (5): booi_bci, iciq, ipss, pvrua, uroflow

## Implementation Template

Each calculator must:

1. **Import InputMetadata and InputType:**
```python
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)
```

2. **Implement get_input_schema() method:**
```python
def get_input_schema(self) -> List[InputMetadata]:
    """Get detailed metadata for [Calculator Name] inputs."""
    return [
        InputMetadata(
            field_name="field_name",
            display_name="Display Name",
            input_type=InputType.NUMERIC,  # ENUM, BOOLEAN, TEXT, DATE
            required=True,
            description="Clinical meaning",
            unit="unit",  # e.g., "ng/mL", "cm", "%"
            min_value=0,
            max_value=100,
            example="50",
            help_text="Clinical guidance for providers"
        ),
        # ... more fields
    ]
```

## Key Implementation Details

### InputType Options
- **NUMERIC**: Used for continuous values (PSA, age, scores)
- **ENUM**: Used for categorical choices (grades, stages, yes/no)
- **BOOLEAN**: Used for true/false answers
- **TEXT**: Used for free text (identifiers, notes)
- **DATE**: Used for calendar dates

### Numeric Fields
- Always include: min_value, max_value, unit, example
- Use realistic clinical ranges based on validate_inputs() method
- Include helpful min/max context in help_text

### Enum Fields
- Set allowed_values to match validation logic
- Can be strings ["low", "high"] or integers [1, 2, 3]
- Include description of what each option means in help_text

### Help Text Guidelines
- Keep concise (1-2 sentences)
- Include normal/abnormal ranges
- Mention clinical significance
- Reference scoring logic if applicable

## Remaining Implementation Order

### Priority 1: KIDNEY (4 calculators)
- imdc_criteria: 7 required inputs (KPS, time to treatment, labs)
- leibovich_score: 4 inputs (grade, ECOG, stage, size)
- renal_score: 4 required + 2 optional inputs (radius, exophytic, nearness, location points)
- ssign_score: 4 inputs (stage, size, grade, necrosis)

### Priority 2: PROSTATE (6 calculators)
- dre_volume: 3 inputs (width, height, depth in cm)
- free_psa: 2 inputs (total PSA, free PSA)
- nccn_risk: 3 inputs (PSA, Gleason, T-stage)
- pcpt_risk: 3 inputs (age, race, family history)
- phi_score: 3 inputs (total PSA, free PSA, p2PSA)
- psa_kinetics: 3 inputs (baseline PSA, current PSA, time interval)

### Priority 3: RECONSTRUCTIVE (4 calculators)
- clavien_dindo: 1 input (complication grade)
- peyronie_severity: Multiple clinical assessment inputs
- pfui_classification: Classification-based inputs
- stricture_complexity: Complexity scoring inputs

### Priority 4: STONES (4 calculators)
- guy_score: Stone scoring inputs
- stone_score: Stone size/type inputs
- stone_size: Measurement inputs
- urine_24hr: 24-hour urine parameters

### Priority 5: SURGICAL (5 calculators)
- cci: Comorbidity scoring
- cfs: Frailty assessment
- life_expectancy: Demographic inputs
- nsqip: Preoperative risk factors
- rcri: Cardiac risk indices

### Priority 6: VOIDING (5 calculators)
- booi_bci: Bladder/detrusor indices
- iciq: Incontinence severity questions
- ipss: Symptom score questionnaire (7 items)
- pvrua: Post-void residual measurement
- uroflow: Flow rate measurements

## Validation Reference

Extract validation logic from each calculator's validate_inputs() method:
- Note min/max ranges for NUMERIC inputs
- Extract enum/allowed values for ENUM inputs
- Check boolean (0/1, True/False) for BOOLEAN inputs

## Quality Checklist

For each calculator:
- [ ] All required_inputs have corresponding InputMetadata
- [ ] InputType matches validation method
- [ ] Min/max values align with validate_inputs()
- [ ] Allowed_values match validation enums
- [ ] help_text is clinically meaningful
- [ ] Example values are realistic
- [ ] Units are specified where applicable
- [ ] Display names are professional/user-friendly

## File Locations

All calculator files are in:
`/home/gulab/PythonProjects/VAUCDA/backend/calculators/[category]/[calculator].py`

Example:
- `/home/gulab/PythonProjects/VAUCDA/backend/calculators/kidney/ssign_score.py`
- `/home/gulab/PythonProjects/VAUCDA/backend/calculators/prostate/psa_kinetics.py`

## Testing

After implementation, verify with:
```bash
cd /home/gulab/PythonProjects/VAUCDA/backend
python3 -c "from calculators import get_all_calculators; c = get_all_calculators(); print(f'Total: {len(c)}'); [print(f'{calc.name}: {len(calc.get_input_schema())} inputs') for calc in c]"
```

## Next Steps

1. Implement remaining 31 calculators following this template
2. Run validation tests to ensure all input_schema methods work
3. Test API endpoints to confirm schemas are returned correctly
4. Use QA verification tool to check 100% coverage
5. Final honest-broker verification for production readiness
