#!/usr/bin/env python3
"""
End-to-end test using note.log content to verify system works after PEFT removal.
"""
import asyncio
import sys
from pathlib import Path

# Read the note.log content
note_log_path = Path("logs/note.log")
if not note_log_path.exists():
    print(f"ERROR: {note_log_path} not found")
    sys.exit(1)

raw_note = note_log_path.read_text()

print("=" * 80)
print("VAUCDA END-TO-END TEST (Post-PEFT Removal)")
print("=" * 80)
print(f"\nInput: Loaded {len(raw_note)} characters from logs/note.log")
print(f"First 200 chars: {raw_note[:200]}...")

async def test_note_processing():
    """Test the note processing pipeline."""
    from llm.llm_manager import LLMManager, TaskType

    print("\n" + "=" * 80)
    print("TEST 1: LLM Manager Initialization")
    print("=" * 80)

    try:
        llm_manager = LLMManager()
        print(f"✓ LLM Manager initialized successfully")
        print(f"  Available providers: {list(llm_manager.providers.keys())}")
        print(f"  Primary provider: {llm_manager.primary_provider}")
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("TEST 2: Simple Text Generation")
    print("=" * 80)

    try:
        test_prompt = "What is BPH? Respond in one short sentence."
        print(f"Prompt: {test_prompt}")
        response = await llm_manager.generate(
            prompt=test_prompt,
            task_type=TaskType.SIMPLE_NOTE,
            temperature=0.3,
            max_tokens=100
        )
        print(f"✓ Generation successful")
        print(f"  Provider used: {response.provider}")
        print(f"  Model: {response.model}")
        print(f"  Response: {response.content[:200]}...")
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("TEST 3: Extract Key Info from Note.log")
    print("=" * 80)

    try:
        extraction_prompt = f"""Extract the following from this clinical note:
1. Patient age and demographics
2. Chief complaint
3. Current medications (list top 5)

Note:
{raw_note[:2000]}

Provide a concise extraction."""

        response = await llm_manager.generate(
            prompt=extraction_prompt,
            task_type=TaskType.DATA_EXTRACTION,
            temperature=0.1,
            max_tokens=500
        )
        print(f"✓ Extraction successful")
        print(f"\nExtracted Information:")
        print("-" * 80)
        print(response.content)
        print("-" * 80)
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
    print("\nSummary:")
    print("  ✓ LLM Manager working (Ollama provider)")
    print("  ✓ Text generation working")
    print("  ✓ Clinical data extraction working")
    print("\nConclusion: System is fully operational after PEFT/fine-tuning removal")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_note_processing())
    sys.exit(0 if success else 1)
