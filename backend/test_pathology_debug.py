#!/usr/bin/env python3
"""Debug pathology extraction."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.agents.gu_agent import process_gu_notes
from app.services.note_processing.extractors import extract_pathology

def main():
    # Load user's input
    input_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/input.txt")
    with open(input_file, 'r') as f:
        content = f.read()

    print("="*80)
    print("PATHOLOGY EXTRACTION DEBUG")
    print("="*80)

    # Identify notes
    notes_dict = identify_notes(content)
    gu_notes = notes_dict["gu_notes"]

    print(f"\nFound {len(gu_notes)} GU notes")

    # Process first note
    if gu_notes:
        processed = process_gu_notes(gu_notes[:1])
        pathology = processed[0].get("Pathology", "")

        print(f"\nFirst note pathology ({len(pathology)} chars):")
        print("-"*80)
        print(repr(pathology[:500]))
        print("-"*80)

        # Show what lines would be filtered
        print("\nLine-by-line analysis:")
        for i, line in enumerate(pathology.split('\n')[:20], 1):
            print(f"{i:3}. {repr(line[:80])}")

    # Also check document-level
    doc_path = extract_pathology(content)
    print(f"\n\nDocument-level pathology ({len(doc_path)} chars):")
    print("-"*80)
    print(doc_path[:500] if doc_path else "(empty)")
    print("-"*80)


if __name__ == "__main__":
    sys.exit(main())
