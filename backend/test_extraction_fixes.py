#!/usr/bin/env python3
"""
Test extraction fixes with user's real input data.

Verifies:
1. IPSS table is preserved (not embedded in HPI)
2. All 10 PMH diagnoses are extracted
3. All 4 PSH surgeries are extracted
4. No PSA hallucinations (no Dec 08, 2025)
5. Labs are clean (no VA metadata)
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.services.note_processing.note_builder import build_urology_note

def main():
    # Load user's input
    input_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/input.txt")
    with open(input_file, 'r') as f:
        clinical_input = f.read()

    print("="*80)
    print("TESTING EXTRACTION FIXES")
    print("="*80)

    # Build note
    note = build_urology_note(clinical_input)

    # Save output
    output_file = Path("/home/gulab/PythonProjects/VAUCDA/logs/note_fixed.log")
    with open(output_file, 'w') as f:
        f.write(note)

    print(f"\n✅ Note generated: {len(note)} characters")
    print(f"✅ Saved to: {output_file}")

    # Verification checks
    print("\n" + "="*80)
    print("VERIFICATION CHECKS")
    print("="*80)

    errors = []

    # Check 1: IPSS should be in its own section, not in HPI
    hpi_section = note.split("HPI:")[1].split("\n\n")[0] if "HPI:" in note else ""
    if "+---" in hpi_section or "IPSS" in hpi_section[:200]:
        errors.append("❌ IPSS table still embedded in HPI")
    else:
        print("✅ IPSS not embedded in HPI")

    # Check 2: IPSS section should exist with table format
    if "IPSS:" in note:
        ipss_section = note.split("IPSS:")[1].split("\n\n")[0]
        if "+---" in ipss_section or "+-" in ipss_section:
            print("✅ IPSS table preserved with ASCII borders")
        else:
            errors.append("❌ IPSS table format not preserved")
    else:
        errors.append("❌ IPSS section missing entirely")

    # Check 3: PMH should have 10 diagnoses
    if "PAST MEDICAL HISTORY:" in note:
        pmh_section = note.split("PAST MEDICAL HISTORY:")[1].split("\n\n")[0]
        pmh_lines = [line for line in pmh_section.split("\n") if line.strip() and line.strip()[0].isdigit()]
        pmh_count = len(pmh_lines)
        if pmh_count >= 10:
            print(f"✅ PMH has {pmh_count} diagnoses (expected 10)")
        else:
            errors.append(f"❌ PMH has only {pmh_count} diagnoses (expected 10)")
    else:
        errors.append("❌ PMH section missing")

    # Check 4: PSH should have 4 surgeries
    if "PAST SURGICAL HISTORY:" in note:
        psh_section = note.split("PAST SURGICAL HISTORY:")[1].split("\n\n")[0]
        psh_lines = [line for line in psh_section.split("\n") if line.strip() and line.strip()[0].isdigit()]
        psh_count = len(psh_lines)
        if psh_count >= 4:
            print(f"✅ PSH has {psh_count} surgeries (expected 4)")
        else:
            errors.append(f"❌ PSH has only {psh_count} surgeries (expected 4)")
    else:
        errors.append("❌ PSH section missing")

    # Check 5: PSA should NOT have Dec 08, 2025 (hallucination)
    if "PSA CURVE:" in note:
        psa_section = note.split("PSA CURVE:")[1].split("\n\n")[0]
        if "Dec 08, 2025" in psa_section or "Dec 08, 2025" in psa_section:
            errors.append("❌ PSA hallucination detected (Dec 08, 2025)")
        else:
            print("✅ No PSA hallucinations (Dec 08, 2025 not found)")

        # First PSA should be Jun 24, 2024
        if "Jun 24, 2024" in psa_section:
            print("✅ Correct first PSA date (Jun 24, 2024)")
        else:
            errors.append("❌ First PSA is not Jun 24, 2024")
    else:
        errors.append("❌ PSA section missing")

    # Check 6: Labs should NOT have VA metadata
    if "LABS" in note:
        labs_section = note.split("LABS")[1].split("IMAGING")[0] if "IMAGING" in note else note.split("LABS")[1]
        metadata_markers = [
            "Collection time:",
            "Reporting Lab:",
            "AUDIE L. MURPHY",
            "Test Name",
            "Result    Units",
            "Eval:"
        ]
        found_metadata = []
        for marker in metadata_markers:
            if marker in labs_section:
                found_metadata.append(marker)

        if found_metadata:
            errors.append(f"❌ Labs contain VA metadata: {', '.join(found_metadata)}")
        else:
            print("✅ Labs are clean (no VA metadata)")
    else:
        print("⚠️  No LABS section found")

    # Summary
    print("\n" + "="*80)
    if errors:
        print("FAILURES DETECTED:")
        for error in errors:
            print(f"  {error}")
        print("\n❌ Some fixes did not work correctly")
        return 1
    else:
        print("✅ ALL CHECKS PASSED")
        print("\nAll extraction issues have been fixed:")
        print("  • IPSS table preserved in separate section")
        print("  • PMH complete with all 10 diagnoses")
        print("  • PSH complete with all 4 surgeries")
        print("  • PSA curve has no hallucinations")
        print("  • Labs are clean without VA metadata")
        return 0


if __name__ == "__main__":
    sys.exit(main())
