#!/usr/bin/env python3
"""
Test script to verify note generation fixes
"""

import sys
import os
from pathlib import Path

# Set up paths
sys.path.insert(0, '/home/gulab/PythonProjects/VAUCDA/backend')

# Load environment variables from .env
from dotenv import load_dotenv
env_path = Path('/home/gulab/PythonProjects/VAUCDA/.env')
if env_path.exists():
    load_dotenv(env_path)

# Set defaults if not in .env
if not os.getenv('OLLAMA_BASE_URL'):
    os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
if not os.getenv('OLLAMA_NOTE_GENERATION_MODEL'):
    os.environ['OLLAMA_NOTE_GENERATION_MODEL'] = 'llama3.1:70b'
if not os.getenv('OLLAMA_CLINICAL_EXTRACTION_MODEL'):
    os.environ['OLLAMA_CLINICAL_EXTRACTION_MODEL'] = 'llama3.1:8b'

from app.services.note_processing.note_builder import build_urology_note


def test_note_generation():
    """Test note generation with the input.txt file"""

    # Read input document
    with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
        clinical_document = f.read()

    print("Starting note generation test...")
    print("=" * 80)

    # Generate note
    generated_note = build_urology_note(clinical_document)

    # Save to file
    output_path = '/home/gulab/PythonProjects/VAUCDA/logs/note_test_output.log'
    with open(output_path, 'w') as f:
        f.write(generated_note)

    print("\n" + "=" * 80)
    print(f"Note generation complete!")
    print(f"Output saved to: {output_path}")
    print("=" * 80)

    # Verify fixes
    print("\nVerifying fixes:")
    print("-" * 80)

    # Check 1: Labs section should have dates
    if "9/4/25:" in generated_note or "Lipid panel" in generated_note:
        print("✓ PASS: General Labs extraction includes dates and panels")
    else:
        print("✗ FAIL: General Labs missing dates")

    # Check 2: HPI should not say "no information available"
    if "no further information" not in generated_note.lower() and "HPI:" in generated_note:
        hpi_section = generated_note.split("HPI:")[1].split("\n\n")[0]
        if len(hpi_section) > 100:  # HPI should have substantial content
            print("✓ PASS: HPI contains extracted content")
        else:
            print("✗ FAIL: HPI is too short")
    else:
        print("✗ FAIL: HPI says 'no information available'")

    # Check 3: IPSS at Visit section should exist
    if "IPSS AT VISIT:" in generated_note:
        print("✓ PASS: IPSS AT VISIT section present")
    else:
        print("✗ FAIL: IPSS AT VISIT section missing")

    # Check 4: Imaging section should have content
    if "MRI PROSTATE" in generated_note and "PI-RADS" in generated_note:
        print("✓ PASS: Imaging extraction includes MRI findings")
    else:
        print("✗ FAIL: Imaging missing or incomplete")

    print("-" * 80)
    print("\nTest complete! Check output file for full note.")


if __name__ == "__main__":
    test_note_generation()
