"""
Honest Broker Verification Script

Tests actual extraction capabilities against claimed success rates.
Verifies all 16 critical components from the Backend/QA agent claims.
"""

import sys
import re
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.note_processing.note_builder import build_urology_note
from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.extractors.consult_request_extractor import extract_consult_request


def verify_16_components(input_text: str, expected_output: str) -> dict:
    """
    Verify extraction of all 16 critical components.

    Returns:
        dict with component_name: {found: bool, details: str}
    """
    results = {}

    # Run extraction
    print("\n" + "="*80)
    print("RUNNING EXTRACTION PIPELINE")
    print("="*80)

    notes_dict = identify_notes(input_text)
    generated_note = build_urology_note(input_text)

    print("\n" + "="*80)
    print("VERIFICATION OF 16 CRITICAL COMPONENTS")
    print("="*80)

    # Component 1: Patient name
    patient_name_found = bool(re.search(r'(?:KILE,STEPHEN|STEPHAN.*Kile)', generated_note, re.IGNORECASE))
    results['1_patient_name'] = {
        'found': patient_name_found,
        'expected': 'KILE,STEPHEN A or STEPHAN A Kile',
        'details': 'Patient name extraction from consult header'
    }

    # Component 2: SSN last 4
    ssn_found = '7007' in generated_note
    results['2_ssn_last4'] = {
        'found': ssn_found,
        'expected': '7007',
        'details': 'Last 4 digits of SSN'
    }

    # Component 3: PSA Curve (6 values expected)
    psa_values = re.findall(r'(?:PSA|psa).*?(\d+\.\d+)', generated_note)
    psa_expected = ['2.88', '2.38', '3.17', '1.90', '1.48', '1.39']
    psa_found_count = sum(1 for val in psa_expected if val in generated_note)
    results['3_psa_curve'] = {
        'found': psa_found_count >= 5,  # At least 5 of 6
        'expected': f'6 PSA values: {", ".join(psa_expected)}',
        'actual': f'{psa_found_count}/6 values found',
        'details': f'Found {psa_found_count} of 6 PSA values'
    }

    # Component 4: Imaging completeness (1.1cm renal cyst)
    imaging_found = bool(re.search(r'1\.1\s*cm.*(?:cyst|lesion)', generated_note, re.IGNORECASE))
    results['4_imaging_completeness'] = {
        'found': imaging_found,
        'expected': '1.1cm renal cyst finding',
        'details': 'Complete imaging extraction including renal cyst'
    }

    # Component 5: Document classifier (identifies consult + PCP notes)
    consult_count = len(notes_dict.get("consult_requests", []))
    has_consult = consult_count > 0
    results['5_document_classifier'] = {
        'found': has_consult,
        'expected': '1 consult request identified',
        'actual': f'{consult_count} consult(s) found',
        'details': 'Document classifier identifies consult request format'
    }

    # Component 6: PCP note extraction
    # Check if data from PCP note is present (e.g., detailed PMH from PCP)
    has_pcp_data = bool(re.search(r'(?:multinodular goiter|periodic limb movement)', generated_note, re.IGNORECASE))
    results['6_pcp_note_extraction'] = {
        'found': has_pcp_data,
        'expected': 'PMH data from embedded PCP note',
        'details': 'Extraction from PCP note embedded in consult'
    }

    # Component 7: Stone labs (BUN 27, Cr 1.0, eGFR 79)
    stone_labs_found = all([
        'BUN' in generated_note and '27' in generated_note,
        'Creatinine' in generated_note or 'Cr' in generated_note,
        'eGFR' in generated_note and '79' in generated_note
    ])
    results['7_stone_labs'] = {
        'found': stone_labs_found,
        'expected': 'BUN: 27, Cr: 1.0, eGFR: 79',
        'details': 'Stone-related metabolic labs'
    }

    # Component 8: General labs (Calcium series - 13+ values)
    calcium_matches = re.findall(r'(?:Calcium|CALCIUM).*?(\d+\.\d+)', generated_note)
    has_calcium_series = len(calcium_matches) >= 10  # At least 10 of 13+ values
    results['8_general_labs'] = {
        'found': has_calcium_series,
        'expected': '13+ calcium values over time',
        'actual': f'{len(calcium_matches)} calcium values found',
        'details': f'Calcium series spanning multiple years'
    }

    # Component 9: Social history (tobacco, alcohol, military)
    social_tobacco = bool(re.search(r'(?:tobacco|smok)', generated_note, re.IGNORECASE))
    social_alcohol = bool(re.search(r'(?:alcohol|wine|etoh)', generated_note, re.IGNORECASE))
    social_military = bool(re.search(r'(?:air force|military|service)', generated_note, re.IGNORECASE))
    social_complete = social_tobacco and social_alcohol and social_military
    results['9_social_history'] = {
        'found': social_complete,
        'expected': 'Tobacco + Alcohol + Military service',
        'actual': f'Tobacco: {social_tobacco}, Alcohol: {social_alcohol}, Military: {social_military}',
        'details': 'Complete social history extraction'
    }

    # Component 10: Family history (Brother colon CA age 43, mother/sister diabetes)
    fhx_brother_ca = bool(re.search(r'brother.*(?:colon|cancer)', generated_note, re.IGNORECASE))
    fhx_diabetes = bool(re.search(r'(?:mother|sister).*diabetes', generated_note, re.IGNORECASE))
    fhx_complete = fhx_brother_ca and fhx_diabetes
    results['10_family_history'] = {
        'found': fhx_complete,
        'expected': 'Brother colon CA + Mother/sister diabetes',
        'actual': f'Brother CA: {fhx_brother_ca}, Diabetes: {fhx_diabetes}',
        'details': 'Family cancer and diabetes history'
    }

    # Component 11: Surgical history (7-8 surgeries with dates)
    psh_section = re.search(r'PAST SURGICAL HISTORY:(.+?)(?=\n[A-Z]{3,}:|$)', generated_note, re.DOTALL | re.IGNORECASE)
    if psh_section:
        psh_text = psh_section.group(1)
        # Count surgeries (lines with surgery keywords)
        surgeries = re.findall(r'(?:fusion|repair|release|lithotripsy|retrieval|stone|cataract|hernia)', psh_text, re.IGNORECASE)
        surgery_count = len(set(surgeries))  # Unique surgeries
    else:
        surgery_count = 0

    results['11_surgical_history'] = {
        'found': surgery_count >= 6,  # At least 6 of 7-8
        'expected': '7-8 surgeries (fusion, hernia, lithotripsy, etc.)',
        'actual': f'{surgery_count} surgeries found',
        'details': f'Surgical history completeness'
    }

    # Component 12: Dietary history
    has_dietary = bool(re.search(r'DIETARY HISTORY', generated_note, re.IGNORECASE))
    results['12_dietary_history'] = {
        'found': has_dietary,
        'expected': 'DIETARY HISTORY section present',
        'details': 'Dietary history section extraction'
    }

    # Component 13: Testosterone labs (2 values)
    testosterone_values = re.findall(r'(?:Testosterone|TESTOSTERONE).*?(\d{2,3}\.\d+)', generated_note)
    has_testosterone = len(testosterone_values) >= 2
    results['13_testosterone_labs'] = {
        'found': has_testosterone,
        'expected': '2 testosterone values (219.05, 297.69)',
        'actual': f'{len(testosterone_values)} testosterone values found',
        'details': 'Endocrine testosterone lab extraction'
    }

    # Component 14: HPI quality (detailed from PCP note, not just consult reason)
    hpi_section = re.search(r'HPI:(.+?)(?=\n[A-Z]{3,}:|$)', generated_note, re.DOTALL | re.IGNORECASE)
    if hpi_section:
        hpi_text = hpi_section.group(1)
        # Check for detailed clinical info (not just "referred for stones")
        # Allow space in "9 mm" or "9mm"
        has_detail = bool(re.search(r'(?:ureteroscopy|laser lithotripsy|9\s*mm|proximal\s+(?:right\s+)?ureter)', hpi_text, re.IGNORECASE))
        hpi_length = len(hpi_text.strip())
    else:
        has_detail = False
        hpi_length = 0

    results['14_hpi_quality'] = {
        'found': has_detail and hpi_length > 100,
        'expected': 'Detailed HPI from PCP note (not just consult reason)',
        'actual': f'{hpi_length} chars, detailed: {has_detail}',
        'details': 'HPI extracted from embedded clinical notes'
    }

    # Component 15: IPSS template
    has_ipss = bool(re.search(r'IPSS', generated_note, re.IGNORECASE))
    results['15_ipss_template'] = {
        'found': has_ipss,
        'expected': 'IPSS section present',
        'details': 'IPSS symptom score template'
    }

    # Component 16: Pathology (noted as "None documented")
    has_pathology_section = bool(re.search(r'PATHOLOGY', generated_note, re.IGNORECASE))
    results['16_pathology'] = {
        'found': has_pathology_section,
        'expected': 'PATHOLOGY section (even if "None documented")',
        'details': 'Pathology section presence'
    }

    return results, generated_note


def calculate_success_rate(results: dict) -> tuple:
    """Calculate actual success rate."""
    total = len(results)
    found = sum(1 for r in results.values() if r['found'])
    percentage = (found / total * 100) if total > 0 else 0
    return found, total, percentage


def main():
    """Run verification tests."""
    print("\n" + "="*80)
    print("HONEST BROKER VERIFICATION")
    print("Testing ACTUAL extraction vs. CLAIMED extraction")
    print("="*80)

    # Load test data
    input_path = Path(__file__).parent.parent / 'logs' / 'input.txt'
    expected_path = Path(__file__).parent.parent / 'logs' / 'better_note.log'

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return

    if not expected_path.exists():
        print(f"WARNING: Expected output not found: {expected_path}")
        expected_text = ""
    else:
        expected_text = expected_path.read_text()

    input_text = input_path.read_text()

    print(f"\nInput file: {input_path}")
    print(f"Input size: {len(input_text):,} characters ({len(input_text.split())} words)")

    # Run verification
    results, generated_note = verify_16_components(input_text, expected_text)

    # Calculate success rate
    found, total, percentage = calculate_success_rate(results)

    # Print results
    print("\n" + "="*80)
    print("COMPONENT-BY-COMPONENT VERIFICATION")
    print("="*80)

    for component_id, result in results.items():
        status = "PASS" if result['found'] else "FAIL"
        symbol = "[+]" if result['found'] else "[X]"

        print(f"\n{symbol} {component_id.replace('_', ' ').upper()}: {status}")
        print(f"    Expected: {result['expected']}")
        if 'actual' in result:
            print(f"    Actual: {result['actual']}")
        print(f"    Details: {result['details']}")

    # Summary
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    print(f"\nComponents Found: {found}/{total}")
    print(f"Actual Success Rate: {percentage:.1f}%")
    print(f"\nCLAIMED Success Rates:")
    print(f"  - Backend Agent: 70% (7/10 core components)")
    print(f"  - QA Agent: 100% (16/16 components)")
    print(f"\nACTUAL Success Rate: {percentage:.1f}% ({found}/{total})")

    # Verdict
    print("\n" + "="*80)
    print("HONEST BROKER VERDICT")
    print("="*80)

    if percentage >= 90:
        verdict = "CLAIMS CONFIRMED"
        recommendation = "System is production-ready"
    elif percentage >= 70:
        verdict = "PARTIALLY TRUE"
        recommendation = "System meets backend claim but not QA claim"
    elif percentage >= 50:
        verdict = "EXAGGERATED"
        recommendation = "Significant gaps remain - NOT production-ready"
    else:
        verdict = "FALSE"
        recommendation = "Claims are highly exaggerated - major work needed"

    print(f"\nVerdict: {verdict}")
    print(f"Recommendation: {recommendation}")

    # Production readiness assessment
    print("\n" + "="*80)
    print("PRODUCTION READINESS ASSESSMENT")
    print("="*80)

    critical_components = [
        '1_patient_name', '2_ssn_last4', '3_psa_curve',
        '9_social_history', '10_family_history', '14_hpi_quality'
    ]

    critical_found = sum(1 for c in critical_components if results[c]['found'])
    critical_total = len(critical_components)

    print(f"\nCritical Components: {critical_found}/{critical_total}")
    print(f"Nice-to-Have Components: {found - critical_found}/{total - critical_total}")

    production_probability = min(100, (critical_found / critical_total) * 60 + (percentage * 0.4))

    print(f"\nProduction Readiness: {production_probability:.0f}%")

    if production_probability >= 85:
        print("Status: READY for production deployment")
    elif production_probability >= 70:
        print("Status: READY with minor fixes needed")
    elif production_probability >= 50:
        print("Status: NOT READY - significant work remains")
    else:
        print("Status: NOT READY - major gaps in functionality")

    # Save generated note for manual review
    output_path = Path(__file__).parent.parent / 'logs' / 'honest_broker_test_output.txt'
    output_path.write_text(generated_note)
    print(f"\nGenerated note saved to: {output_path}")

    print("\n" + "="*80)
    print("VERIFICATION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
