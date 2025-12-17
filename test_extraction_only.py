#!/usr/bin/env python3
"""
Test Extraction Components Directly

Tests individual extractors without full LLM synthesis.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.note_processing.document_classifier import DocumentClassifier
from app.services.note_processing.extractors.pcp_note_extractor import PCPNoteExtractor
from app.services.note_processing.extractors.consult_request_extractor import extract_consult_request
from app.services.note_processing.extractors.psa_extractor import extract_psa
from app.services.note_processing.extractors.lab_extractor import extract_stone_labs, extract_calcium_series
from app.services.note_processing.extractors.endocrine_extractor import extract_endocrine_labs
from app.services.note_processing.extractors.imaging_extractor import extract_imaging


def main():
    # Read input file
    input_path = '/home/gulab/PythonProjects/VAUCDA/logs/input.txt'

    print("="*80)
    print("DIRECT EXTRACTION COMPONENT TEST")
    print("="*80)

    with open(input_path, 'r') as f:
        input_text = f.read()

    print(f"\nInput size: {len(input_text)} characters\n")

    # Test 1: Document Classifier
    print("="*80)
    print("TEST 1: Document Classifier")
    print("="*80)
    classifier = DocumentClassifier()
    classification = classifier.classify_document(input_text)
    print(f"Document Type: {classification['document_type']}")
    print(f"Is Composite: {classification['is_composite']}")
    print(f"Number of segments: {len(classification['segments'])}")
    for i, seg in enumerate(classification['segments'][:5]):
        print(f"  Segment {i+1}: {seg.doc_type} ({len(seg.content)} chars)")

    # Test 2: PCP Note Extraction
    print("\n" + "="*80)
    print("TEST 2: PCP Note Extraction")
    print("="*80)
    pcp_content = classifier.extract_document_segment(input_text, "PRIMARY_CARE_NOTE")
    if pcp_content:
        print(f"PCP Note found: {len(pcp_content)} characters")
        pcp_extractor = PCPNoteExtractor()
        pcp_data = pcp_extractor.extract_all(pcp_content)

        print("\nSocial History:")
        print("-" * 40)
        print(pcp_data.get('social_history', 'NOT FOUND'))

        print("\nFamily History:")
        print("-" * 40)
        print(pcp_data.get('family_history', 'NOT FOUND'))

        print("\nSurgical History:")
        print("-" * 40)
        print(pcp_data.get('surgical_history', 'NOT FOUND')[:300])  # First 300 chars
    else:
        print("PCP Note NOT FOUND")

    # Test 3: PSA Extraction
    print("\n" + "="*80)
    print("TEST 3: PSA Extraction")
    print("="*80)
    psa_data = extract_psa(input_text)
    if psa_data:
        print("PSA Data found:")
        print("-" * 40)
        print(psa_data)
    else:
        print("PSA Data NOT FOUND")

    # Test 4: Stone Labs
    print("\n" + "="*80)
    print("TEST 4: Stone Labs Extraction")
    print("="*80)
    stone_labs = extract_stone_labs(input_text)
    if stone_labs:
        print("Stone Labs found:")
        print("-" * 40)
        print(stone_labs)
    else:
        print("Stone Labs NOT FOUND")

    # Test 5: Calcium Series
    print("\n" + "="*80)
    print("TEST 5: Calcium Series Extraction")
    print("="*80)
    calcium_data = extract_calcium_series(input_text)
    if calcium_data:
        print("Calcium Series found:")
        print("-" * 40)
        print(calcium_data[:500])  # First 500 chars
    else:
        print("Calcium Series NOT FOUND")

    # Test 6: Endocrine Labs
    print("\n" + "="*80)
    print("TEST 6: Endocrine Labs Extraction")
    print("="*80)
    endocrine_data = extract_endocrine_labs(input_text)
    if endocrine_data:
        print("Endocrine Labs found:")
        print("-" * 40)
        print(endocrine_data)
    else:
        print("Endocrine Labs NOT FOUND")

    # Test 7: Imaging
    print("\n" + "="*80)
    print("TEST 7: Imaging Extraction")
    print("="*80)
    imaging_data = extract_imaging(input_text)
    if imaging_data:
        print("Imaging found:")
        print("-" * 40)
        print(imaging_data[:800])  # First 800 chars
    else:
        print("Imaging NOT FOUND")

    # Test 8: Consult Request
    print("\n" + "="*80)
    print("TEST 8: Consult Request Extraction")
    print("="*80)
    consult_data = extract_consult_request(input_text)
    if consult_data:
        print("Consult Request found:")
        print("-" * 40)
        for key, value in consult_data.items():
            if value:
                print(f"{key}: {value[:100] if isinstance(value, str) and len(value) > 100 else value}")
    else:
        print("Consult Request NOT FOUND")

    # Summary
    print("\n" + "="*80)
    print("EXTRACTION SUMMARY")
    print("="*80)
    results = {
        'PCP Note': bool(pcp_content),
        'Social History': bool(pcp_data.get('social_history')) if pcp_content else False,
        'Family History': bool(pcp_data.get('family_history')) if pcp_content else False,
        'Surgical History': bool(pcp_data.get('surgical_history')) if pcp_content else False,
        'PSA Data': bool(psa_data),
        'Stone Labs': bool(stone_labs),
        'Calcium Series': bool(calcium_data),
        'Endocrine Labs': bool(endocrine_data),
        'Imaging': bool(imaging_data),
        'Consult Request': bool(consult_data)
    }

    success_count = sum(results.values())
    total_count = len(results)

    for item, found in results.items():
        status = "✓" if found else "✗"
        print(f"{status} {item}")

    print(f"\n{success_count}/{total_count} components extracted successfully ({success_count/total_count*100:.1f}%)")
    print("="*80)


if __name__ == '__main__':
    main()
