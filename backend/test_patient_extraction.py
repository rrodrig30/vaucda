#!/usr/bin/env python3
"""Quick test to verify patient demographics extraction from actual consult data."""

import re
from app.services.note_processing.extractors.consult_request_extractor import (
    ConsultRequestExtractor,
    extract_patient_demographics
)

# Sample text from actual consult (logs/input.txt line 665)
sample_text = """
DATE:  OCT 17, 2025

KILE,STEPHEN A, 495-60-7007
Age: 74 Sex: MALE Race: WHITE

Weight: 187 lb [84.82 kg] (10/17/2025 10:30)  Height:  70 in [177.8 cm]
"""

print("=" * 80)
print("TESTING PATIENT DEMOGRAPHICS EXTRACTION")
print("=" * 80)

# Test the current pattern
extractor = ConsultRequestExtractor()

print("\n1. Testing PATIENT_NAME_SSN_PATTERN:")
print(f"   Pattern: {extractor.PATIENT_NAME_SSN_PATTERN.pattern}")

match = extractor.PATIENT_NAME_SSN_PATTERN.search(sample_text)
if match:
    print(f"   ✓ MATCHED!")
    print(f"   - Full match: {match.group(0)}")
    print(f"   - Name (group 1): {match.group(1)}")
    print(f"   - SSN (group 2): {match.group(2)}")
else:
    print(f"   ✗ NO MATCH")

print("\n2. Testing extract_patient_demographics function:")
result = extract_patient_demographics(sample_text)
print(f"   Result: {result}")

if result['patient_name']:
    print(f"   ✓ Extracted patient_name: {result['patient_name']}")
else:
    print(f"   ✗ Failed to extract patient_name")

if result['ssn']:
    print(f"   ✓ Extracted SSN: {result['ssn']}")
else:
    print(f"   ✗ Failed to extract SSN")

if result['ssn_last4']:
    print(f"   ✓ Extracted SSN last 4: {result['ssn_last4']}")
else:
    print(f"   ✗ Failed to extract SSN last 4")

if result['patient_name_formatted']:
    print(f"   ✓ Formatted name: {result['patient_name_formatted']}")
else:
    print(f"   ✗ Failed to format name")

print("\n3. Expected values:")
print("   - patient_name: KILE,STEPHEN A")
print("   - ssn: 495-60-7007")
print("   - ssn_last4: 7007")
print("   - patient_name_formatted: STEPHEN A Kile")

print("\n4. Testing with real consult input:")
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    full_text = f.read()

result_full = extract_patient_demographics(full_text)
print(f"   Result from full consult: {result_full}")

print("\n" + "=" * 80)
