#!/usr/bin/env python3
"""Test imaging extraction with real consult input."""

import sys
sys.path.insert(0, '/home/gulab/PythonProjects/VAUCDA/backend')

from app.services.note_processing.extractors.imaging_extractor import extract_imaging

# Read the input file
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    clinical_document = f.read()

# Extract imaging
imaging_result = extract_imaging(clinical_document)

print("=" * 80)
print("IMAGING EXTRACTION TEST")
print("=" * 80)
print(f"\nImaging found: {bool(imaging_result)}")
print(f"Length: {len(imaging_result)} characters")
print("\n" + "=" * 80)
print("EXTRACTED IMAGING:")
print("=" * 80)
print(imaging_result if imaging_result else "None")
print("\n" + "=" * 80)
