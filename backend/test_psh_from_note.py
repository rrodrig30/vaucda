#!/usr/bin/env python3
"""Test PSH extraction with real note content."""

import re
from pathlib import Path

# Load user's input
input_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/input.txt")
with open(input_file, 'r') as f:
    content = f.read()

# Get first note
first_note = content.split("STANDARD TITLE:")[1].split("STANDARD TITLE:")[0]

# Extract PSH section manually
if "PAST SURGICAL HISTORY:" in first_note:
    psh_start = first_note.index("PAST SURGICAL HISTORY:")
    psh_end = psh_start + 500  # Get more context
    psh_section = first_note[psh_start:psh_end]

    print("Raw PSH section (500 chars):")
    print("="*80)
    print(repr(psh_section))
    print("="*80)

    # Test pattern
    pattern = r'(?:PSH|PAST SURGICAL HISTORY):\s*(.*?)(?=\n\s*[A-Z][A-Z\s]+:|\n\s*={10,}|$)'
    match = re.search(pattern, psh_section, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        result = match.group(1).strip()
        print(f"\nMatched {len(result)} chars:")
        print("-"*80)
        print(result)
        print("-"*80)
        print(f"\nLines: {result.count(chr(10)) + 1}")
    else:
        print("NO MATCH!")
