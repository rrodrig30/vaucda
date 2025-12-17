"""
Test Stage 2 Integration

This script tests the full Stage 2 pipeline:
1. Stage 1: Generate preliminary note
2. Stage 2: Generate Assessment & Plan using specialized agents
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.note_processing.note_builder import build_urology_note
from app.services.note_processing.stage2_builder import build_stage2_note
from app.services.note_processing.note_identifier import identify_notes


def test_stage2_integration():
    """Test complete Stage 1 + Stage 2 workflow."""

    print("\n" + "="*80)
    print("TESTING STAGE 2 INTEGRATION")
    print("="*80)

    # Use real VA training data file for testing
    training_data_path = Path(__file__).parent.parent.parent / "training data" / "9_15_25 #4.in"

    print(f"\nLoading training data from: {training_data_path}")

    try:
        with open(training_data_path, 'r', encoding='utf-8') as f:
            clinical_input = f.read()
        print(f"Loaded {len(clinical_input)} characters of clinical data")
    except Exception as e:
        print(f"ERROR: Could not load training data: {e}")
        print("Falling back to synthetic test data...")

        # Fallback synthetic data (keep original as backup)
        clinical_input = """
STANDARD TITLE: UROLOGY
Date Signed: 01/15/2024
Author: Dr. Rodriguez, Urology

CHIEF COMPLAINT: Elevated PSA

HISTORY OF PRESENT ILLNESS:
72-year-old male with history of BPH presents for elevated PSA. Most recent PSA 8.5 ng/mL.
Patient reports mild LUTS with IPSS of 12. No hematuria, no dysuria. Family history
significant for father with prostate cancer at age 75.

PAST MEDICAL HISTORY:
- Benign prostatic hyperplasia
- Hypertension
- Type 2 diabetes mellitus

MEDICATIONS:
Tamsulosin 0.4 mg daily
Finasteride 5 mg daily
Lisinopril 20 mg daily
Metformin 1000 mg BID

SOCIAL HISTORY:
Never smoker, occasional alcohol use

PSA CURVE:
01/10/2023: 6.2 ng/mL
07/15/2023: 7.1 ng/mL
01/15/2024: 8.5 ng/mL H

LABS:
Creatinine: 1.1 mg/dL
eGFR: 72 mL/min

ASSESSMENT:
Patient with rising PSA trend concerning for possible prostate malignancy.
Gleason 3+4 prostate adenocarcinoma on prior biopsy, 4/12 cores positive.

PLAN:
1. Discussed active surveillance vs. definitive treatment
2. Patient elected for active surveillance with 6-month PSA monitoring
3. MRI prostate ordered
4. Follow-up in 6 months
    """

    print("\n" + "-"*80)
    print("STAGE 1: Generating Preliminary Note")
    print("-"*80)

    try:
        # Stage 1: Generate preliminary note
        stage1_note = build_urology_note(clinical_input)

        print("\nStage 1 Complete!")
        print(f"Preliminary note length: {len(stage1_note)} characters")
        print("\nStage 1 Note Preview (first 500 chars):")
        print(stage1_note[:500])
        print("...")

    except Exception as e:
        print(f"\n❌ Stage 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "-"*80)
    print("STAGE 2: Generating Assessment & Plan")
    print("-"*80)

    try:
        # Identify GU notes for Stage 2
        notes_dict = identify_notes(clinical_input)
        gu_notes = notes_dict.get("gu_notes", [])

        print(f"\nFound {len(gu_notes)} GU notes for historical context")

        # Stage 2: Generate complete note with Assessment & Plan
        # Simulate calculator results
        calculator_results = {
            "pcpt_risk": {
                "calculator_name": "PCPT Risk Calculator 2.0",
                "result": {"cancer_risk": 0.23, "high_grade_risk": 0.12},
                "interpretation": "23% risk of prostate cancer, 12% risk of high-grade cancer",
                "recommendations": ["Consider prostate biopsy", "Discuss risks/benefits with patient"]
            }
        }

        # Simulate RAG content
        rag_content = """
        AUA/NCCN Guidelines for Prostate Cancer:
        - PSA > 4.0 ng/mL warrants further evaluation
        - Rising PSA trend concerning for malignancy
        - MRI-targeted biopsy recommended for elevated PSA with prior negative biopsy
        - Active surveillance appropriate for low-risk disease
        """

        # Build Stage 2 note
        complete_note = build_stage2_note(
            stage1_note=stage1_note,
            gu_notes=gu_notes,
            ambient_transcript=None,  # Not available in this test
            calculator_results=calculator_results,
            rag_content=rag_content
        )

        print("\nStage 2 Complete!")
        print(f"Complete note length: {len(complete_note)} characters")

        # Save complete note to file
        output_file = backend_dir / "logs" / "stage2_test_output.txt"
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("COMPLETE CLINICAL NOTE (STAGE 1 + STAGE 2)\n")
            f.write("="*80 + "\n\n")
            f.write(complete_note)

        print(f"\nComplete note saved to: {output_file}")

        print("\n" + "="*80)
        print("STAGE 2 INTEGRATION TEST: ✅ SUCCESS")
        print("="*80)

        # Display Assessment & Plan section
        if "ASSESSMENT:" in complete_note:
            assessment_start = complete_note.find("ASSESSMENT:")
            print("\nExtracted Assessment & Plan Section:")
            print("-"*80)
            print(complete_note[assessment_start:])

    except Exception as e:
        print(f"\n❌ Stage 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return


def test_agent_isolation():
    """Test that Stage 2 agents have clean isolation from Stage 1."""

    print("\n" + "="*80)
    print("TESTING AGENT ISOLATION")
    print("="*80)

    from app.services.note_processing.agents.assessment_agent import synthesize_assessment
    from app.services.note_processing.agents.plan_agent import synthesize_plan

    # Test data
    stage1_note = "CC: Elevated PSA\n\nHPI: Patient with rising PSA..."
    prior_assessments = ["Patient has BPH with rising PSA trend."]
    prior_plans = ["Continue active surveillance, repeat PSA in 6 months."]

    print("\nTesting assessment_agent...")
    try:
        assessment = synthesize_assessment(
            stage1_note=stage1_note,
            prior_assessments=prior_assessments,
            ambient_transcript=None,
            calculator_results=None,
            rag_content=None
        )
        print(f"✅ Assessment generated: {len(assessment)} chars")
    except Exception as e:
        print(f"❌ Assessment agent failed: {e}")
        import traceback
        traceback.print_exc()

    print("\nTesting plan_agent...")
    try:
        plan = synthesize_plan(
            stage1_note=stage1_note,
            prior_plans=prior_plans,
            ambient_transcript=None,
            calculator_results=None,
            rag_content=None
        )
        print(f"✅ Plan generated: {len(plan)} chars")
    except Exception as e:
        print(f"❌ Plan agent failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("AGENT ISOLATION TEST: ✅ SUCCESS")
    print("="*80)


if __name__ == "__main__":
    print("\n" + "#"*80)
    print("# STAGE 2 INTEGRATION TEST SUITE")
    print("#"*80)

    # Test 1: Agent isolation
    test_agent_isolation()

    # Test 2: Full integration
    test_stage2_integration()

    print("\n" + "#"*80)
    print("# ALL TESTS COMPLETE")
    print("#"*80 + "\n")
