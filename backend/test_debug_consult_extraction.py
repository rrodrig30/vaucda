#!/usr/bin/env python3
"""Debug consult extraction to see what data is actually returned."""

from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.extractors.consult_request_extractor import extract_consult_request

# Read the actual consult input
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    consult_input = f.read()

print("="*80)
print("DEBUGGING CONSULT EXTRACTION")
print("="*80)

# Identify notes
notes_dict = identify_notes(consult_input)

if notes_dict.get("consult_requests"):
    consult_content = notes_dict["consult_requests"][0]["content"]

    print(f"\nConsult content length: {len(consult_content)} chars")
    print("\nFirst 500 chars of consult content:")
    print("-" * 80)
    print(consult_content[:500])
    print("-" * 80)

    # Extract consult data
    consult_data = extract_consult_request(consult_content)

    print("\nExtracted consult data:")
    print("-" * 80)
    for key, value in consult_data.items():
        if isinstance(value, str) and len(value) > 100:
            print(f"{key}: {value[:100]}... ({len(value)} chars total)")
        else:
            print(f"{key}: {value}")
    print("-" * 80)

    # Check specifically for patient info
    print("\nPatient demographics check:")
    print(f"  patient_name: '{consult_data.get('patient_name')}'")
    print(f"  ssn: '{consult_data.get('ssn')}'")
    print(f"  ssn_last4: '{consult_data.get('ssn_last4')}'")

else:
    print("\nNo consult requests found!")

print("\n" + "="*80)
