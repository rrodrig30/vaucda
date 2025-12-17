"""
Test Clinical Entity Extraction from Stage 1 Preliminary Note

This test verifies that:
1. Entity extraction works from a Stage 1 preliminary note
2. All relevant clinical values are captured correctly
3. Calculator inputs can be properly extracted
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.entity_extractor import ClinicalEntityExtractor


# Sample Stage 1 preliminary note (what gets passed to calculator extraction)
SAMPLE_PRELIMINARY_NOTE = """
CHIEF COMPLAINT:
Elevated PSA

HISTORY OF PRESENT ILLNESS:
This is a 72 year old male with a history of elevated PSA who presents today for follow-up evaluation.
His most recent PSA was 8.5 ng/mL, which is elevated from his baseline of 4.2 ng/mL from 2 years ago.
Patient reports no urinary symptoms, no hematuria, no bone pain.

INTERNATIONAL PROSTATE SYMPTOM SCORE (IPSS):
Total Score: 14 (Moderate symptoms)

PAST MEDICAL HISTORY:
1. Hypertension
2. Type 2 Diabetes Mellitus
3. Chronic Heart Failure (CHF)
4. Chronic Obstructive Pulmonary Disease (COPD)

MEDICATIONS:
1. Lisinopril 10mg daily
2. Metformin 1000mg twice daily
3. Furosemide 40mg daily

ALLERGIES: NKDA

PSA CURVE (reverse chronological):
[r] Dec 05, 2024 10:30    8.5 H
[r] Jan 15, 2023 09:15    4.2
[r] Jun 20, 2021 11:00    3.8

PHYSICAL EXAMINATION:
Vital Signs:
  BP: 138/82
  HR: 76
  Temp: 98.6
  RR: 16
  O2 Sat: 96%

Digital Rectal Exam:
  Prostate: Firm, enlarged, approximately 45cc, no nodules

LABORATORY:
Creatinine: 1.2 mg/dL
Hemoglobin: 13.5 g/dL
Calcium: 9.4 mg/dL
"""


async def test_entity_extraction():
    """Test entity extraction from preliminary note."""
    print("=" * 80)
    print("TESTING ENTITY EXTRACTION FROM STAGE 1 PRELIMINARY NOTE")
    print("=" * 80)

    # Initialize extractor
    extractor = ClinicalEntityExtractor()

    # Extract entities
    print("\n[1/2] Extracting entities from preliminary note...")
    entities = await extractor.extract_entities(SAMPLE_PRELIMINARY_NOTE)

    print(f"\n[2/2] Found {len(entities)} entities:")
    print("-" * 80)

    # Display all extracted entities
    for entity in entities:
        print(f"Field: {entity['field']}")
        print(f"  Value: {entity['value']}")
        print(f"  Confidence: {entity['confidence']}")
        print(f"  Method: {entity['extraction_method']}")
        print(f"  Source: {entity.get('source_text', 'N/A')[:50]}...")
        print()

    # Create entity dictionary (how it's used in calculator execution)
    entity_dict = {e['field']: e['value'] for e in entities}

    print("-" * 80)
    print("\nENTITY DICTIONARY (for calculator inputs):")
    print("-" * 80)
    for field, value in sorted(entity_dict.items()):
        print(f"  {field}: {value}")

    # Verify expected values
    print("\n" + "=" * 80)
    print("VALIDATION:")
    print("=" * 80)

    expected_values = {
        'psa': 8.5,
        'age': 72,
        'gender': 'male',
        'ipss_score': 14,
        'blood_pressure': '138/82',
        'heart_rate': 76,
        'temperature': 98.6,
        'respiratory_rate': 16,
        'oxygen_saturation': 96,
        'creatinine': 1.2,
        'hemoglobin': 13.5,
        'calcium': 9.4,
        'prostate_volume_cc': 45.0
    }

    all_correct = True
    for field, expected_value in expected_values.items():
        actual_value = entity_dict.get(field)
        match = actual_value == expected_value
        status = "✓" if match else "✗"

        if not match:
            all_correct = False
            print(f"{status} {field}: Expected {expected_value}, Got {actual_value}")
        else:
            print(f"{status} {field}: {actual_value}")

    print("\n" + "=" * 80)
    if all_correct:
        print("SUCCESS: All entities extracted correctly!")
    else:
        print("WARNING: Some entities missing or incorrect")
    print("=" * 80)

    return entities, entity_dict


if __name__ == "__main__":
    asyncio.run(test_entity_extraction())
