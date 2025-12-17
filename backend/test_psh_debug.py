#!/usr/bin/env python3
"""Debug PSH extraction."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.services.note_processing.extractors.psh_extractor import extract_psh

def main():
    # Load user's input
    input_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/input.txt")
    with open(input_file, 'r') as f:
        content = f.read()

    # Get first note
    first_note = content.split("STANDARD TITLE:")[1].split("STANDARD TITLE:")[0]

    print("="*80)
    print("TESTING PSH EXTRACTOR ON FIRST NOTE")
    print("="*80)

    # Show PSH section in raw note
    if "PAST SURGICAL HISTORY:" in first_note:
        psh_start = first_note.index("PAST SURGICAL HISTORY:")
        psh_snippet = first_note[psh_start:psh_start+200]
        print("\nRaw PSH section in note:")
        print("-"*80)
        print(repr(psh_snippet))
        print("-"*80)

    # Extract PSH
    psh = extract_psh(first_note)

    print(f"\nExtracted PSH ({len(psh)} chars):")
    print("-"*80)
    print(psh)
    print("-"*80)

    # Count surgeries
    lines = [line for line in psh.split('\n') if line.strip()]
    print(f"\n✅ Extracted {len(lines)} surgeries:")
    for i, line in enumerate(lines, 1):
        print(f"  {i}. {line}")


if __name__ == "__main__":
    sys.exit(main())
