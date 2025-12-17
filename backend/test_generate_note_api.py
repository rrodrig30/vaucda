#!/usr/bin/env python3
"""
Test script to generate a clinical note via API and save the output
"""
import requests
import json
from pathlib import Path

# Read the clinical data file
data_file = Path(__file__).parent / "test_data" / "raw_clinical_data.txt"
with open(data_file, 'r') as f:
    clinical_data = f.read()

print(f"Clinical data loaded: {len(clinical_data)} characters")

# Step 1: Login to get auth token
print("\n1. Authenticating...")
login_url = "http://localhost:8002/api/v1/auth/token"
login_data = {
    "username": "admin@vaucda.va.gov",
    "password": "Admin123!"
}

login_response = requests.post(login_url, data=login_data, timeout=10)
if login_response.status_code != 200:
    print(f"✗ Login failed: {login_response.status_code}")
    print(login_response.text)
    exit(1)

auth_token = login_response.json()["access_token"]
print("✓ Login successful")

# Prepare API request
url = "http://localhost:8002/api/v1/notes/generate-initial"
headers = {
    "Authorization": f"Bearer {auth_token}",
    "Content-Type": "application/json"
}
payload = {
    "clinical_input": clinical_data,  # Use full clinical data
    "note_type": "clinic_note",
    "llm_provider": "ollama",  # Backend will use PEFT if available
    "temperature": 0.3,
    "use_rag": False
}

print(f"\n2. Sending request to {url}...")
print(f"   Payload size: {len(clinical_data)} chars")
print(f"   This will take approximately 15 minutes with multi-GPU processing...")

try:
    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=1800  # 30 minute timeout
    )

    print(f"\nResponse status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()

        print(f"\n{'='*80}")
        print(f"SUCCESS - Note Generated!")
        print(f"{'='*80}")

        # Print metadata
        if 'metadata' in result:
            metadata = result['metadata']
            print(f"\nMETADATA:")
            print(f"  Processing time: {metadata.get('processing_time_seconds', 'N/A')} seconds")
            print(f"  Sections processed: {metadata.get('sections_processed', 'N/A')}")
            print(f"  Input size: {metadata.get('input_chars', 'N/A')} chars")
            print(f"  Output size: {metadata.get('output_chars', 'N/A')} chars")
            print(f"  Compression ratio: {metadata.get('compression_ratio', 'N/A')}")

        # Print preliminary note
        if 'preliminary_note' in result:
            prelim = result['preliminary_note']
            print(f"\n{'='*80}")
            print(f"PRELIMINARY NOTE ({len(prelim)} characters):")
            print(f"{'='*80}")
            print(prelim)

        # Print final note
        if 'final_note' in result:
            final = result['final_note']
            print(f"\n{'='*80}")
            print(f"FINAL NOTE ({len(final)} characters):")
            print(f"{'='*80}")
            print(final)

        # Save to file
        output_file = Path(__file__).parent / "generated_note.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n✓ Full output saved to: {output_file}")

    else:
        print(f"\nError: {response.status_code}")
        print(response.text)

except requests.exceptions.Timeout:
    print("\n✗ Request timed out after 30 minutes")
except Exception as e:
    print(f"\n✗ Error: {e}")
