#!/usr/bin/env python3
"""
Test the improved section extraction in Ollama fallback.
"""

import asyncio
import requests
import os
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8002/api/v1"
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpass"

# Get HuggingFace token
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "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")

async def main():
    print("=" * 80)
    print("SECTION EXTRACTION FIX TEST")
    print("=" * 80)
    print()

    # Read clinical content
    print("1. Reading clinical content from ../logs/note.log")
    with open("../logs/note.log", "r") as f:
        clinical_content = f.read()

    file_size_kb = len(clinical_content) / 1024
    print(f"   File size: {file_size_kb:.1f} KB")
    print(f"   Content length: {len(clinical_content)} characters (~{len(clinical_content)//4} tokens)")
    print()

    print(f"2. HuggingFace token: {HUGGINGFACE_TOKEN[:12]}...{HUGGINGFACE_TOKEN[-4:]}")
    print()

    # Test 1: Authentication
    print("=" * 80)
    print("TEST 1: AUTHENTICATION")
    print("=" * 80)
    print()

    print(f"Logging in to {BASE_URL}/auth/token...")
    auth_response = requests.post(
        f"{BASE_URL}/auth/token",
        data={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        }
    )

    if auth_response.status_code != 200:
        print(f"✗ Login failed: {auth_response.status_code}")
        print(f"   Response: {auth_response.text}")
        return

    token_data = auth_response.json()
    access_token = token_data["access_token"]
    print("✓ Login successful")
    print()

    # Test 2: Generate preliminary note with section extraction
    print("=" * 80)
    print("TEST 2: STAGE 1 - SECTION EXTRACTION + PRELIMINARY NOTE")
    print("=" * 80)
    print()

    print(f"Sending request to {BASE_URL}/notes/generate-initial")
    print(f"Input length: {len(clinical_content)} chars (~{len(clinical_content)//4} tokens)")
    print()

    print("This will test the improved SectionExtractionAgent fallback...")
    print("Expected behavior:")
    print("  → SectionExtractionAgent: Extract sections from raw input")
    print("  → Template builder: Map extracted sections to template")
    print("  → Result: Preliminary note with actual clinical data")
    print()

    stage1_response = requests.post(
        f"{BASE_URL}/notes/generate-initial",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "clinical_input": clinical_content,
            "huggingface_token": HUGGINGFACE_TOKEN
        },
        timeout=300  # 5 minute timeout
    )

    if stage1_response.status_code != 200:
        print(f"✗ Stage 1 failed: {stage1_response.status_code} {stage1_response.reason}")
        print(f"   Status code: {stage1_response.status_code}")
        print(f"   Response: {stage1_response.text[:500]}...")
        return

    print("✓ Stage 1 complete!")
    print()

    stage1_data = stage1_response.json()
    preliminary_note = stage1_data["preliminary_note"]
    generation_time = stage1_data.get("generation_time", 0)

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save preliminary note
    prelim_filename = f"logs/stage1_section_extraction_fix_{timestamp}.txt"
    with open(prelim_filename, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("STAGE 1: PRELIMINARY NOTE (SECTION EXTRACTION FIX)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Input size: {len(clinical_content)} chars\n")
        f.write(f"Output size: {len(preliminary_note)} chars\n")
        f.write(f"Compression: {len(clinical_content)/len(preliminary_note):.2f}x\n")
        f.write(f"Generation time: {generation_time:.2f}s\n")
        f.write("=" * 80 + "\n")
        f.write("\n")
        f.write(preliminary_note)

    print(f"   Input size: {len(clinical_content)} chars")
    print(f"   Output size: {len(preliminary_note)} chars")
    print(f"   Compression ratio: {len(clinical_content)/len(preliminary_note):.2f}x")
    print(f"   Generation time: {generation_time:.2f} seconds")
    print()
    print(f"✓ Preliminary note saved to: {prelim_filename}")
    print()

    # Check for improvements
    print("=" * 80)
    print("VERIFICATION: CHECKING FOR ACTUAL DATA")
    print("=" * 80)
    print()

    # Count "Not documented" occurrences
    not_documented_count = preliminary_note.count("Not documented")
    print(f"'Not documented' occurrences: {not_documented_count}")

    # Check for specific sections
    has_hpi = "HPI:" in preliminary_note and len(preliminary_note.split("HPI:")[1].split("\n\n")[0].strip()) > 50
    has_medications = "MEDICATIONS:" in preliminary_note
    has_labs = "PSA:" in preliminary_note or "Creatinine:" in preliminary_note

    print(f"Has substantial HPI: {has_hpi}")
    print(f"Has medications section: {has_medications}")
    print(f"Has lab results: {has_labs}")
    print()

    # Show first 500 chars of note
    print("=" * 80)
    print("PRELIMINARY NOTE PREVIEW (first 500 chars)")
    print("=" * 80)
    print(preliminary_note[:500])
    print("...")
    print()

    print("=" * 80)
    print("✓ SECTION EXTRACTION FIX TEST COMPLETED")
    print("=" * 80)
    print()
    print(f"Full output saved to: {prelim_filename}")
    print()

    if not_documented_count > 5:
        print("⚠ WARNING: Still many 'Not documented' sections. May need further investigation.")
    elif has_hpi and has_medications and has_labs:
        print("✓ SUCCESS: Clinical data is being extracted properly!")
    else:
        print("⚠ PARTIAL SUCCESS: Some sections extracted, but may need more work.")

if __name__ == "__main__":
    asyncio.run(main())
