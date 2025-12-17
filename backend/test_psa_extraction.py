#!/usr/bin/env python3
"""Test PSA extraction from actual consult data."""

from app.services.note_processing.extractors.psa_extractor import extract_psa

# Read the actual consult input
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    consult_input = f.read()

print("="*80)
print("TESTING PSA EXTRACTION")
print("="*80)

psa_data = extract_psa(consult_input)

if psa_data:
    print("\n✓ PSA data extracted:")
    print("-" * 80)
    print(psa_data)
    print("-" * 80)

    # Count entries
    entries = psa_data.strip().split('\n')
    print(f"\nNumber of PSA entries: {len(entries)}")

    print("\n✓ Expected format (from better_note.log):")
    print("-" * 80)
    print("[r] Mar 17, 2023 10:27    2.88")
    print("[r] Apr 22, 2013 09:25    2.38")
    print("[r] Jul 14, 2011 10:34    3.17")
    print("[r] Mar 16, 2009 10:01    1.90")
    print("[r] Apr 24, 2006 09:18    1.48")
    print("[r] Apr 08, 2005 09:41    1.39")
    print("-" * 80)
else:
    print("\n✗ NO PSA DATA EXTRACTED!")

print("="*80)
