#!/usr/bin/env python3
"""
Test Consult Note Extraction

Tests the enhanced extraction system against the input.txt consult request.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.note_processing.note_builder import build_urology_note


def main():
    # Read input file
    input_path = '/home/gulab/PythonProjects/VAUCDA/logs/input.txt'
    output_path = '/home/gulab/PythonProjects/VAUCDA/logs/test_output.txt'

    print("="*80)
    print("CONSULT NOTE EXTRACTION TEST")
    print("="*80)

    with open(input_path, 'r') as f:
        input_text = f.read()

    print(f"\nInput size: {len(input_text)} characters")

    # Build note
    print("\n" + "="*80)
    result = build_urology_note(input_text)

    # Write output
    with open(output_path, 'w') as f:
        f.write(result)

    print(f"\nOutput written to: {output_path}")
    print(f"Output size: {len(result)} characters")

    # Print summary
    print("\n" + "="*80)
    print("EXTRACTION SUMMARY")
    print("="*80)

    # Check for key sections
    sections_to_check = [
        ('PSA CURVE', 'PSA values extracted'),
        ('SOCIAL HISTORY', 'Social history extracted'),
        ('FAMILY HISTORY', 'Family history extracted'),
        ('PAST SURGICAL HISTORY', 'Surgical history extracted'),
        ('STONE LABS', 'Stone labs extracted'),
        ('CALCIUM', 'Calcium series extracted'),
        ('TESTOSTERONE', 'Testosterone labs extracted'),
        ('IMAGING', 'Imaging reports extracted'),
        ('BUN', 'Renal function (BUN) extracted'),
        ('eGFR', 'eGFR extracted'),
    ]

    found_count = 0
    for section, description in sections_to_check:
        if section in result:
            print(f"✓ {description}")
            found_count += 1
        else:
            print(f"✗ {description}")

    print(f"\n{found_count}/{len(sections_to_check)} key sections found ({found_count/len(sections_to_check)*100:.1f}%)")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()
