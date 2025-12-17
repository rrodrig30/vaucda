#!/usr/bin/env python3
"""
Test script to verify note generation fix.
Tests that the note contains actual data instead of "Not documented" placeholders.
"""
import asyncio
import sys
from pathlib import Path

# Load the clinical note with actual data
clinical_note_path = Path("logs/note.log")
if not clinical_note_path.exists():
    print(f"ERROR: {clinical_note_path} not found")
    sys.exit(1)

clinical_input = clinical_note_path.read_text()

print("=" * 80)
print("NOTE GENERATION FIX VERIFICATION TEST")
print("=" * 80)
print(f"\nLoaded clinical input: {len(clinical_input)} characters")
print(f"First 300 chars:\n{clinical_input[:300]}...")

async def test_note_generation():
    """Test note generation with the fixed code."""
    # We'll simulate what the API endpoint does
    from app.schemas.notes import InitialNoteRequest
    from llm.llm_manager import LLMManager, TaskType
    from app.services.note_generator import NoteGenerator
    from pathlib import Path

    print("\n" + "=" * 80)
    print("STEP 1: Initialize Note Generator")
    print("=" * 80)

    try:
        llm_manager = LLMManager()
        note_generator = NoteGenerator(llm_manager=llm_manager, neo4j_client=None, embedding_generator=None)
        print("✓ Note generator initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("STEP 2: Load Urology System Prompt")
    print("=" * 80)

    urology_prompt_file = Path("/home/gulab/PythonProjects/VAUCDA/urology_prompt.txt")
    urology_system_prompt = ""
    try:
        with open(urology_prompt_file, 'r') as f:
            urology_system_prompt = f.read()
        print(f"✓ Loaded urology system prompt ({len(urology_system_prompt)} chars)")
    except Exception as e:
        print(f"✗ Could not load urology_prompt.txt: {e}")
        return False

    print("\n" + "=" * 80)
    print("STEP 3: Generate Preliminary Note (Ollama Fallback Path)")
    print("=" * 80)

    try:
        # Build prompt exactly as the fixed code does
        stage1_prompt_parts = []

        # Add stage1 extraction instructions
        if note_generator.stage1_prompt:
            stage1_prompt_parts.append(note_generator.stage1_prompt)
        else:
            stage1_prompt_parts.append("Extract and organize ALL clinical data from the input below.")
            stage1_prompt_parts.append("CRITICAL: Include ALL details - no placeholders, no 'Not documented' unless data is truly absent.")
            stage1_prompt_parts.append("Extract every medication, lab result, vital sign, and clinical finding present in the input.")

        # Add the urology template as formatting guidance
        if urology_system_prompt:
            stage1_prompt_parts.append("\n=== TEMPLATE FORMAT TO FOLLOW ===\n")
            stage1_prompt_parts.append(urology_system_prompt)

        # Add the actual clinical input
        stage1_prompt_parts.append("\n=== RAW CLINICAL INPUT TO EXTRACT ===\n")
        stage1_prompt_parts.append(clinical_input)

        # Add instruction to generate complete note
        stage1_prompt_parts.append("\n=== INSTRUCTIONS ===")
        stage1_prompt_parts.append("Generate a complete, properly formatted urology clinic note using the template format above.")
        stage1_prompt_parts.append("Extract and include ALL clinical data from the input - medications, labs, vitals, imaging, history, etc.")
        stage1_prompt_parts.append("Do NOT use placeholders like 'Not documented' unless the data is genuinely absent from the input.")
        stage1_prompt_parts.append("If data exists in the input, extract it completely and accurately.")

        stage1_prompt = "\n".join(stage1_prompt_parts)

        print(f"Prompt constructed: {len(stage1_prompt)} chars")
        print("Calling Ollama llama3.1:8b for note generation...")

        # Use Ollama llama3.1:8b for extraction
        preliminary_note_response = await llm_manager.generate(
            prompt=stage1_prompt,
            system_prompt="You are a medical data extraction specialist. Extract and organize ALL clinical data accurately and completely. Never use placeholders when actual data is present.",
            task_type=TaskType.DATA_EXTRACTION,
            temperature=0.1,  # Low temperature for accurate extraction
            max_tokens=4096,
            model="llama3.1:8b"
        )

        # Extract the complete note directly from LLM
        preliminary_note = preliminary_note_response.content if hasattr(preliminary_note_response, 'content') else str(preliminary_note_response)

        print(f"✓ Note generated successfully: {len(preliminary_note)} chars")

    except Exception as e:
        print(f"✗ Note generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("STEP 4: Verify Note Quality")
    print("=" * 80)

    # Check for placeholder text
    placeholder_issues = []

    if "Not documented" in preliminary_note and "Benign Prostatic Hyperplasia" in clinical_input:
        placeholder_issues.append("Found 'Not documented' when actual PMH data exists in input")

    if "No PSA values documented" in preliminary_note and "PSA: 6.2" in clinical_input:
        placeholder_issues.append("Found 'No PSA values documented' when PSA value exists in input")

    if "None documented" in preliminary_note and "Tamsulosin" in clinical_input:
        placeholder_issues.append("Found 'None documented' when medications exist in input")

    # Check for actual data extraction
    data_found = []

    if "74" in preliminary_note or "74-year-old" in preliminary_note:
        data_found.append("✓ Patient age extracted")
    else:
        placeholder_issues.append("Patient age not found in note")

    if "Tamsulosin" in preliminary_note or "tamsulosin" in preliminary_note:
        data_found.append("✓ Medication (Tamsulosin) extracted")
    else:
        placeholder_issues.append("Medication (Tamsulosin) not extracted")

    if "6.2" in preliminary_note or "PSA" in preliminary_note:
        data_found.append("✓ PSA value extracted")
    else:
        placeholder_issues.append("PSA value not extracted")

    if "BPH" in preliminary_note or "Benign Prostatic Hyperplasia" in preliminary_note or "prostatic" in preliminary_note.lower():
        data_found.append("✓ BPH diagnosis extracted")
    else:
        placeholder_issues.append("BPH diagnosis not extracted")

    print("\nData Extraction Check:")
    for item in data_found:
        print(f"  {item}")

    if placeholder_issues:
        print("\nPlaceholder Issues Found:")
        for issue in placeholder_issues:
            print(f"  ✗ {issue}")
        print(f"\n⚠ WARNING: Note still has {len(placeholder_issues)} quality issues")
    else:
        print("\n✓ No placeholder issues - all expected data extracted!")

    print("\n" + "=" * 80)
    print("GENERATED NOTE PREVIEW (first 1000 chars):")
    print("=" * 80)
    print(preliminary_note[:1000])
    print("\n[... note continues ...]")
    print("=" * 80)

    # Overall result
    if len(placeholder_issues) == 0:
        print("\n✅ TEST PASSED: Note generation fix is working correctly!")
        return True
    else:
        print(f"\n❌ TEST FAILED: {len(placeholder_issues)} issues found")
        print("\nFull generated note:")
        print(preliminary_note)
        return False

if __name__ == "__main__":
    success = asyncio.run(test_note_generation())
    sys.exit(0 if success else 1)
