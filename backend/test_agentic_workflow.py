#!/usr/bin/env python3
"""
Test the complete agentic extraction workflow for large clinical inputs.

This demonstrates the two-stage process:
1. Stage 1 (Agentic PEFT Extraction): Large input → Section extraction → PEFT processing → Preliminary note
2. Stage 2 (GraphRAG A&P): Preliminary note → GraphRAG retrieval → Assessment & Plan generation

This handles inputs like note.log (680KB+) that exceed the model's context window.
"""

import os
import sys
import requests
import json
from pathlib import Path
from datetime import datetime

print("=" * 80)
print("AGENTIC EXTRACTION WORKFLOW TEST")
print("=" * 80)

# Configuration
NOTE_LOG_PATH = Path("../logs/note.log")
BACKEND_URL = "http://localhost:8002"
OUTPUT_DIR = Path("logs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Read clinical content from note.log
if not NOTE_LOG_PATH.exists():
    print(f"\n✗ File not found: {NOTE_LOG_PATH}")
    print("Please ensure note.log exists with clinical test data")
    sys.exit(1)

print(f"\n1. Reading clinical content from {NOTE_LOG_PATH}")
print(f"   File size: {NOTE_LOG_PATH.stat().st_size / 1024:.1f} KB")

with open(NOTE_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
    clinical_content = f.read()

print(f"   Content length: {len(clinical_content)} characters (~{len(clinical_content) // 4} tokens)")

# Get HuggingFace token from .env
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
    print("\n⚠ HUGGINGFACE_TOKEN not found in .env (will use fallback)")

# Test 1: Login to get auth token
print("\n" + "=" * 80)
print("TEST 1: AUTHENTICATION")
print("=" * 80)

login_url = f"{BACKEND_URL}/api/v1/auth/token"
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

# Test 2: Stage 1 - Preliminary note generation with agentic extraction
print("\n" + "=" * 80)
print("TEST 2: STAGE 1 - AGENTIC EXTRACTION & PRELIMINARY NOTE")
print("=" * 80)

note_url = f"{BACKEND_URL}/api/v1/notes/generate-initial"
headers = {
    "Authorization": f"Bearer {auth_token}",
    "Content-Type": "application/json"
}

# Request with large clinical input
# Backend will detect size and automatically use agentic extraction if needed
note_data = {
    "clinical_input": clinical_content,
    "note_type": "clinic_note",
    "llm_provider": "ollama",  # Backend tries PEFT first, then falls back
    "temperature": 0.3,
    "use_rag": False  # Stage 1 doesn't need RAG
}

print(f"\nSending request to {note_url}")
print(f"Input length: {len(clinical_content)} chars (~{len(clinical_content) // 4} tokens)")
print(f"\nProcessing may take 2-5 minutes for large inputs with agentic extraction...")
print("Progress:")
print("  → Section extraction agent: Identifying clinical sections")
print("  → Processing agent: PEFT model processing each section")
print("  → Synthesis agent: Combining into preliminary note")

try:
    response = requests.post(note_url, headers=headers, json=note_data, timeout=1800)
    response.raise_for_status()
    result = response.json()

    print("\n✓ Stage 1 complete!")

    # Extract preliminary note
    preliminary_note = result.get('preliminary_note', '')
    metadata = result.get('metadata', {})

    print(f"\n   Input size: {len(clinical_content)} chars")
    print(f"   Output size: {len(preliminary_note)} chars")
    print(f"   Compression ratio: {len(clinical_content) / len(preliminary_note):.2f}x")
    print(f"   Generation time: {metadata.get('generation_time_seconds', 'N/A')} seconds")

    # Save preliminary note
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stage1_output = OUTPUT_DIR / f"stage1_preliminary_{timestamp}.txt"

    with open(stage1_output, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("STAGE 1: PRELIMINARY NOTE (AGENTIC EXTRACTION)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Input size: {len(clinical_content)} chars\n")
        f.write(f"Output size: {len(preliminary_note)} chars\n")
        f.write(f"Compression: {len(clinical_content) / len(preliminary_note):.2f}x\n")
        f.write(f"Generation time: {metadata.get('generation_time_seconds', 'N/A')}s\n")
        f.write("=" * 80 + "\n\n")
        f.write(preliminary_note)

    print(f"\n✓ Preliminary note saved to: {stage1_output}")

    # Display section preview
    print("\n" + "=" * 80)
    print("PRELIMINARY NOTE SECTIONS (first 300 chars)")
    print("=" * 80)
    sections_preview = preliminary_note[:300]
    print(sections_preview)
    if len(preliminary_note) > 300:
        print("\n... (truncated, see full output in file)")

except requests.exceptions.Timeout:
    print(f"\n✗ Request timed out after 1800 seconds")
    print("   The processing may be taking longer than expected")
    print("   Check backend logs for progress: tail -f logs/backend.log")
    sys.exit(1)

except Exception as e:
    print(f"\n✗ Stage 1 failed: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"\n   Status code: {e.response.status_code}")
        print(f"   Response: {e.response.text[:1000]}...")
    sys.exit(1)

# Test 3: Stage 2 - Assessment & Plan with GraphRAG
print("\n" + "=" * 80)
print("TEST 3: STAGE 2 - ASSESSMENT & PLAN WITH GRAPHRAG")
print("=" * 80)

final_note_url = f"{BACKEND_URL}/api/v1/notes/generate-final"

# For Stage 2, we pass the preliminary note and request GraphRAG
final_note_data = {
    "preliminary_note": preliminary_note,
    "clinical_input": clinical_content,  # REQUIRED: Original clinical data for calculator execution
    "clinical_entities": result.get('extracted_entities', []),
    "selected_calculators": [],  # Can add calculator IDs if needed
    "llm_provider": "ollama",
    "use_rag": True,  # Enable GraphRAG for evidence-based A&P
    "temperature": 0.3
}

print(f"\nSending request to {final_note_url}")
print("Processing:")
print("  → GraphRAG retrieval: Finding relevant clinical evidence")
print("  → LLM generation: Creating Assessment & Plan")

try:
    response = requests.post(final_note_url, headers=headers, json=final_note_data, timeout=300)
    response.raise_for_status()
    final_result = response.json()

    print("\n✓ Stage 2 complete!")

    # Extract final note
    final_note = final_result.get('final_note', '')
    rag_sources = final_result.get('rag_sources', [])

    print(f"\n   Preliminary note size: {len(preliminary_note)} chars")
    print(f"   Final note size: {len(final_note)} chars")
    print(f"   RAG sources used: {len(rag_sources)}")

    # Save final note
    stage2_output = OUTPUT_DIR / f"stage2_final_{timestamp}.txt"

    with open(stage2_output, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("STAGE 2: FINAL NOTE WITH ASSESSMENT & PLAN\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Preliminary note: {len(preliminary_note)} chars\n")
        f.write(f"Final note: {len(final_note)} chars\n")
        f.write(f"RAG sources: {len(rag_sources)}\n")
        f.write("=" * 80 + "\n\n")
        f.write(final_note)

        if rag_sources:
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("RAG SOURCES CONSULTED\n")
            f.write("=" * 80 + "\n")
            for i, source in enumerate(rag_sources, 1):
                f.write(f"\n{i}. {source.get('title', 'Unknown')}\n")
                f.write(f"   Type: {source.get('type', 'N/A')}\n")
                f.write(f"   Relevance: {source.get('score', 'N/A')}\n")

    print(f"\n✓ Final note saved to: {stage2_output}")

    # Display A&P preview
    print("\n" + "=" * 80)
    print("ASSESSMENT & PLAN PREVIEW (last 500 chars of final note)")
    print("=" * 80)
    ap_preview = final_note[-500:]
    print("..." + ap_preview if len(final_note) > 500 else final_note)

    print("\n" + "=" * 80)
    print("✓✓✓ TWO-STAGE WORKFLOW COMPLETED SUCCESSFULLY ✓✓✓")
    print("=" * 80)
    print(f"\nStage 1 (Preliminary): {stage1_output}")
    print(f"Stage 2 (Final with A&P): {stage2_output}")
    print("\nWorkflow summary:")
    print(f"  1. Input: {len(clinical_content)} chars (large unstructured data)")
    print(f"  2. Agentic extraction → Preliminary note: {len(preliminary_note)} chars")
    print(f"  3. GraphRAG + LLM → Final note with A&P: {len(final_note)} chars")
    print(f"  4. Total compression: {len(clinical_content) / len(final_note):.2f}x")

    sys.exit(0)

except requests.exceptions.Timeout:
    print(f"\n✗ Stage 2 timed out after 300 seconds")
    print("   Check backend logs: tail -f logs/backend.log")
    sys.exit(1)

except Exception as e:
    print(f"\n✗ Stage 2 failed: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"\n   Status code: {e.response.status_code}")
        print(f"   Response: {e.response.text[:1000]}...")

    print("\n⚠ Stage 1 completed successfully but Stage 2 failed")
    print(f"Preliminary note saved to: {stage1_output}")
    sys.exit(1)
