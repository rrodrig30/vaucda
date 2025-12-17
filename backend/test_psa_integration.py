#!/usr/bin/env python3
"""Integration test for PSA curve in final consult note."""

from app.services.note_processing.note_builder import build_urology_note

# Read the actual consult input
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    consult_input = f.read()

print("="*80)
print("TESTING PSA CURVE IN FINAL NOTE")
print("="*80)

# Build the note
note = build_urology_note(consult_input)

# Find PSA CURVE section
if "PSA CURVE:" in note:
    lines = note.split('\n')

    # Find the PSA CURVE section
    psa_start = -1
    for i, line in enumerate(lines):
        if "PSA CURVE:" in line:
            psa_start = i
            break

    if psa_start >= 0:
        # Extract PSA curve section (until next section or empty line)
        psa_lines = [lines[psa_start]]
        for i in range(psa_start + 1, len(lines)):
            if lines[i].strip() and not lines[i].startswith('[r]') and not lines[i].startswith('MEDICATIONS'):
                if lines[i].strip().isupper() or lines[i].startswith('='):
                    break
            if lines[i].strip():
                psa_lines.append(lines[i])

        print("\n✓ PSA CURVE FOUND:")
        print("-" * 80)
        for line in psa_lines[:10]:  # First 10 lines
            print(line)
        print("-" * 80)

        # Count PSA entries
        psa_count = sum(1 for line in psa_lines if line.startswith('[r]'))
        print(f"\nNumber of PSA entries: {psa_count}")

        print("\n✓ Expected format:")
        print("-" * 80)
        print("PSA CURVE:")
        print("[r] Mar 17, 2023 10:27    2.88")
        print("[r] Apr 22, 2013 09:25    2.38")
        print("[r] Jul 14, 2011 10:34    3.17")
        print("[r] Mar 16, 2009 10:01    1.90")
        print("[r] Apr 24, 2006 09:18    1.48")
        print("[r] Apr 08, 2005 09:41    1.39")
        print("-" * 80)

        if psa_count == 6:
            print("\n✓ SUCCESS: All 6 PSA values extracted!")
        else:
            print(f"\n✗ ISSUE: Expected 6 PSA values, got {psa_count}")
    else:
        print("\n✗ PSA CURVE header found but couldn't parse section")
else:
    print("\n✗ PSA CURVE section not found in note")

print("="*80)
