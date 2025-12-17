#!/usr/bin/env python3
"""Test complete note generation with real consult input."""

import sys
sys.path.insert(0, '/home/gulab/PythonProjects/VAUCDA/backend')

from app.services.note_processing.note_builder import build_urology_note

# Read the input file
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    clinical_document = f.read()

print("\n" + "=" * 80)
print("GENERATING COMPLETE CONSULT NOTE")
print("=" * 80)

# Build the note
final_note = build_urology_note(clinical_document)

# Save to note.log
with open('/home/gulab/PythonProjects/VAUCDA/logs/note.log', 'w') as f:
    f.write(final_note)

print("\n" + "=" * 80)
print("NOTE GENERATION COMPLETE")
print("=" * 80)
print(f"Final note: {len(final_note)} characters")
print(f"Final note: {len(final_note.split(chr(10)))} lines")
print(f"\nNote saved to: /home/gulab/PythonProjects/VAUCDA/logs/note.log")
print("\n" + "=" * 80)
print("PREVIEW (first 100 lines):")
print("=" * 80)
print('\n'.join(final_note.split('\n')[:100]))
