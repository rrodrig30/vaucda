#!/usr/bin/env python3
"""Debug pathology extraction with more detail."""

import re
from pathlib import Path

# Load user's input
input_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/input.txt")
with open(input_file, 'r') as f:
    content = f.read()

print("="*80)
print("DETAILED PATHOLOGY EXTRACTION DEBUG")
print("="*80)

# Split by SURGICAL PATHOLOGY sections
sections = re.split(r'-{4,}\s*SURGICAL PATHOLOGY\s*-{4,}', content, flags=re.IGNORECASE)

print(f"\nFound {len(sections)} sections (first is before any SURGICAL PATHOLOGY marker)\n")

for i, section in enumerate(sections[1:6], 1):  # Check first 5 surgical path sections
    print(f"\n{'='*80}")
    print(f"SECTION {i}")
    print(f"{'='*80}")

    # Show first 500 chars
    print(f"\nFirst 500 chars:")
    print(repr(section[:500]))

    # Extract date
    date_match = re.search(r'Date obtained:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', section, re.IGNORECASE)
    date = date_match.group(1) if date_match else "NO DATE"
    print(f"\nDate: {date}")

    # Look for DIAGNOSIS
    diagnosis_match = re.search(
        r'(?:FINAL\s+)?(?:FLOW\s+CYTOMETRY\s+)?DIAGNOSIS[:\s;]*([^\n]+(?:\n(?!\s*(?:Comment|Note|Clinical|Reporting))[^\n]+)*)',
        section,
        re.IGNORECASE | re.MULTILINE
    )

    if diagnosis_match:
        diagnosis = diagnosis_match.group(1).strip()
        print(f"\nDIAGNOSIS MATCHED ({len(diagnosis)} chars):")
        print(f"First 200 chars: {repr(diagnosis[:200])}")
    else:
        print("\nNO DIAGNOSIS FOUND")
