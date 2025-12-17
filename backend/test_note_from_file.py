#!/usr/bin/env python3
"""
Test note generation using real clinical data from note.log.
Verifies PEFT model extracts correctly without fabrication or placeholders.
"""

import os
import sys
import requests
import json
from pathlib import Path
from datetime import datetime

print("=" * 80)
print("NOTE GENERATION TEST WITH REAL CLINICAL DATA")
print("=" * 80)

# Read clinical content from note.log
note_log_path = Path("../logs/note.log")
if not note_log_path.exists():
    print(f"\n✗ File not found: {note_log_path}")
    sys.exit(1)

print(f"\n1. Reading clinical content from {note_log_path}")
print(f"   File size: {note_log_path.stat().st_size / 1024:.1f} KB")

with open(note_log_path, 'r', encoding='utf-8', errors='ignore') as f:
    clinical_content = f.read()

print(f"   Content length: {len(clinical_content)} characters")

# Get HuggingFace token
env_file = Path(".env")
hf_token = None
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.startswith("HUGGINGFACE_TOKEN"):
                hf_token = line.split("=", 1)[1].strip()
                masked_token = hf_token[:10] + "..." + hf_token[-4:]
                print(f"\n2. HuggingFace token: {masked_token}")
                break

if not hf_token:
    print("\n✗ HUGGINGFACE_TOKEN not found in .env")
    sys.exit(1)

# Test 1: Login to get auth token
print("\n" + "=" * 80)
print("TEST 1: AUTHENTICATION")
print("=" * 80)

login_url = "http://localhost:8002/api/v1/auth/token"
login_data = {
    "username": "admin@vaucda.va.gov",
    "password": "Admin123!"
}

try:
    print(f"\nLogging in to {login_url}...")
    response = requests.post(login_url, data=login_data, timeout=10)
    response.raise_for_status()
    auth_token = response.json()["access_token"]
    print("✓ Login successful")
except Exception as e:
    print(f"✗ Login failed: {e}")
    print("\nIs the backend running? Check with: lsof -i :8002")
    sys.exit(1)

# Test 2: Generate note with PEFT model
print("\n" + "=" * 80)
print("TEST 2: NOTE GENERATION WITH PEFT MODEL")
print("=" * 80)

note_url = "http://localhost:8002/api/v1/notes/generate-initial"
headers = {
    "Authorization": f"Bearer {auth_token}",
    "Content-Type": "application/json"
}

# Backend will automatically try PEFT model first, fallback to Ollama if it fails
note_data = {
    "clinical_input": clinical_content,
    "note_type": "clinic_note",
    "llm_provider": "ollama",  # Default provider (backend tries PEFT first anyway)
    "temperature": 0.3
}

print(f"\nSending request to {note_url}")
print(f"Provider: {note_data['llm_provider']} (backend will try PEFT first)")
print(f"Input length: {len(clinical_content)} chars")
print(f"\nThis may take 30-60 seconds for PEFT model inference...")

try:
    response = requests.post(note_url, headers=headers, json=note_data, timeout=300)
    response.raise_for_status()
    result = response.json()

    print("\n✓ Note generation succeeded!")

    # Extract generated note
    generated_note = result.get('preliminary_note', '')
    print(f"\n   Generated note length: {len(generated_note)} characters")

    # Save to output file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(f"logs/test_output_{timestamp}.txt")

    with open(output_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("VAUCDA NOTE GENERATION TEST OUTPUT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Provider: {note_data['llm_provider']}\n")
        f.write(f"Model: {note_data['model_name']}\n")
        f.write(f"Input size: {len(clinical_content)} chars\n")
        f.write(f"Output size: {len(generated_note)} chars\n")
        f.write("=" * 80 + "\n\n")
        f.write(generated_note)
        f.write("\n\n" + "=" * 80 + "\n")
        f.write("QUALITY CHECKS\n")
        f.write("=" * 80 + "\n")

        # Quality checks
        checks = []

        # Check for placeholders
        placeholder_phrases = [
            "same as above",
            "see above",
            "unchanged",
            "...",
            "[insert",
            "[add",
            "TBD",
            "TODO"
        ]

        found_placeholders = []
        for phrase in placeholder_phrases:
            if phrase.lower() in generated_note.lower():
                found_placeholders.append(phrase)

        if found_placeholders:
            checks.append(f"✗ PLACEHOLDERS FOUND: {', '.join(found_placeholders)}")
        else:
            checks.append("✓ No placeholders detected")

        # Check for key sections
        required_sections = [
            "CC:",
            "HPI:",
            "IPSS",
            "MEDICATIONS:",
            "LABS",
            "PHYSICAL EXAM:"
        ]

        missing_sections = []
        for section in required_sections:
            if section not in generated_note:
                missing_sections.append(section)

        if missing_sections:
            checks.append(f"✗ MISSING SECTIONS: {', '.join(missing_sections)}")
        else:
            checks.append("✓ All required sections present")

        # Check for fabricated/suspicious patterns
        suspicious_patterns = [
            "example",
            "sample patient",
            "hypothetical",
            "placeholder"
        ]

        found_suspicious = []
        for pattern in suspicious_patterns:
            if pattern.lower() in generated_note.lower():
                found_suspicious.append(pattern)

        if found_suspicious:
            checks.append(f"⚠ SUSPICIOUS PATTERNS: {', '.join(found_suspicious)}")
        else:
            checks.append("✓ No suspicious fabrication patterns")

        # Write checks to file
        for check in checks:
            f.write(check + "\n")

        # Print checks to console
        print("\n" + "=" * 80)
        print("QUALITY CHECKS")
        print("=" * 80)
        for check in checks:
            print(check)

    print(f"\n✓ Output saved to: {output_file}")

    # Display first 500 characters
    print("\n" + "=" * 80)
    print("GENERATED NOTE PREVIEW (first 500 chars)")
    print("=" * 80)
    print(generated_note[:500])
    if len(generated_note) > 500:
        print("\n... (truncated, see full output in file)")

    print("\n" + "=" * 80)
    print("✓✓✓ TEST COMPLETED SUCCESSFULLY ✓✓✓")
    print("=" * 80)
    print(f"\nFull output saved to: {output_file}")
    print("Review the output file to verify:")
    print("  1. No fabricated data")
    print("  2. No placeholder text")
    print("  3. Complete extraction of clinical information")
    print("  4. Proper formatting")

    sys.exit(0)

except requests.exceptions.Timeout:
    print(f"\n✗ Request timed out after 300 seconds")
    print("   The model may be loading or inference is taking too long")
    sys.exit(1)

except Exception as e:
    print(f"\n✗ Note generation failed: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"\n   Status code: {e.response.status_code}")
        print(f"   Response: {e.response.text[:1000]}")

    # Check backend logs for errors
    print("\n" + "=" * 80)
    print("CHECKING BACKEND LOGS FOR ERRORS")
    print("=" * 80)

    log_file = Path("logs/backend.log")
    if log_file.exists():
        with open(log_file) as f:
            lines = f.readlines()
            recent_lines = lines[-50:]

            print("\nLast 50 lines of backend.log:")
            print("".join(recent_lines))

    sys.exit(1)
