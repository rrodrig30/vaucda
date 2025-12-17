#!/usr/bin/env python3
"""Debug social history extraction"""

from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.extractors.social_extractor import extract_social

# Read the input file
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    clinical_document = f.read()

# Identify notes
notes_dict = identify_notes(clinical_document)

print("=" * 80)
print("SOCIAL HISTORY EXTRACTION DEBUG")
print("=" * 80)

print(f"\nFound {len(notes_dict.get('pcp_notes', []))} PCP notes")
print(f"Found {len(notes_dict.get('gu_notes', []))} GU notes")
print(f"Found {len(notes_dict.get('other_notes', []))} other notes")

# Extract from each PCP note
for i, note in enumerate(notes_dict.get('pcp_notes', [])):
    print(f"\n--- PCP Note {i+1} ---")
    social = extract_social(note)
    print(f"Length: {len(social)} chars")
    print(f"Content:\n{social}")
    print(f"\nFirst 500 chars: {social[:500]}")
    print(f"\nLast 500 chars: {social[-500:]}")

    # Check if it contains healthcare maintenance
    if 'Living will' in social:
        print("\n!!! CONTAINS 'Living will' !!!")
    if 'Ultrasound' in social:
        print("\n!!! CONTAINS 'Ultrasound' !!!")
