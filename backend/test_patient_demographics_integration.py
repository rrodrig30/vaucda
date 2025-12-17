#!/usr/bin/env python3
"""Integration test for patient demographics in consult notes."""

from app.services.note_processing.note_builder import build_urology_note

# Read the actual consult input
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    consult_input = f.read()

print("="*80)
print("TESTING PATIENT DEMOGRAPHICS IN CONSULT NOTE")
print("="*80)

# Build the note
note = build_urology_note(consult_input)

# Check if patient header is present
lines = note.split('\n')
first_10_lines = '\n'.join(lines[:10])

print("\nFirst 10 lines of generated note:")
print("-" * 80)
print(first_10_lines)
print("-" * 80)

# Check for patient header
if "Patient:" in note:
    # Find the patient line
    for line in lines:
        if line.startswith("Patient:"):
            print(f"\n✓ FOUND PATIENT HEADER: {line}")

            # Verify it contains expected data
            if "STEPHEN A Kile" in line or "KILE" in line:
                print("  ✓ Patient name extracted correctly")
            else:
                print("  ✗ Patient name missing or incorrect")

            if "495-60-7007" in line or "7007" in line:
                print("  ✓ SSN extracted correctly")
            else:
                print("  ✗ SSN missing or incorrect")
            break
else:
    print("\n✗ PATIENT HEADER NOT FOUND IN NOTE")

print("\nExpected format: Patient: STEPHEN A Kile 495-60-7007")
print("="*80)
