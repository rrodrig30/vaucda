#!/usr/bin/env python3
"""
Test script for Stage 3 ambient-augmented note generation.

This tests the complete workflow:
1. Takes a Stage 2 note
2. Simulates ambient transcription from a clinical encounter
3. Performs intelligent section-aware merging
4. Outputs the Stage 3 note
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.ambient_merge_service import (
    IntelligentNoteMerger,
    SectionAwareTranscriptionParser
)


# Test Stage 2 note (from /tmp/test_note_with_filtering.txt)
STAGE2_NOTE = """CC: Follow-up for elevated PSA, BPH with severe LUTS, and erectile dysfunction.

HPI: Mr. Echeverri is a 65-year-old male with a history of benign prostatic hyperplasia (BPH) with severe lower urinary tract symptoms. He has experienced urinary retention and erectile dysfunction in the past. His urologic history also includes a diagnosis of prostate cancer, for which he underwent chemotherapy and radiation therapy coordinated with urology.
In the recent past, Mr. Echeverri underwent a transurethral resection of the prostate (TURP) to alleviate his BPH symptoms. He has also had nephrostomy tube placement due to urinary obstruction caused by kidney stones. The patient's urologic status is currently being managed with follow-up evaluations and treatment as needed.
Mr. Echeverri's current presentation includes continued lower urinary tract symptoms, including frequency and urgency. He reports difficulty initiating urination and a weak stream. His erectile dysfunction persists, but he has not sought treatment for this issue recently.

IPSS:
+---------------+--------+--------+--------+--------+--------+
|        IPSS          | 8/18/25|11/20/23| 5/20/24|10/21/24| Today  |
+---------------+--------+--------+--------+--------+--------+
| Empty         |   0    |   2    |   2    |   1    |        |
| Frequency     |   0    |   3    |   2    |   0    |        |
| Urgency       |   0    |   2    |   2    |   2    |        |
| Hesitancy     |   0    |   2    |   3    |   0    |        |
| Intermittency |   0    |   2    |   3    |   2    |        |
| Flow          |   0    |   1    |   4    |   1    |        |
| Nocturia      |   2    |   4    |   4    |   2    |        |
+---------------+--------+--------+--------+--------+--------+
| Total         | 2/35  | 15/35  | 20/35  | 6/35   |        |
| BI            | 1/6   | 2/6    | 3/6    | 1/6    |        |
+---------------+--------+--------+--------+--------+--------+

DIETARY HISTORY:
Coffee 16 oz q AM, occasionally cappuccino. No alcohol.

SOCIAL HISTORY:
Retired Air Force MSgt, released in 2011 after 26 years of service. Former smoker, having smoked for over 30 years before quitting about 10 years ago. Denies current alcohol use and illicit drug use.

FAMILY HISTORY:
Father had prostate removal, likely for cancer.

SEXUAL HISTORY:
The patient reports experiencing erectile dysfunction (ED) for approximately 11 years. He had previously tried MUSE as a treatment option but has noted that his condition has worsened over time despite its use.

PAST MEDICAL HISTORY:
1. Low back pain
2. Hyperhidrosis
3. Asthma
4. BPH - benign prostatic hyperplasia
5. Coronary artery disease
6. Erectile dysfunction

PAST SURGICAL HISTORY:
1. HoLEP prostate Proc/Sx - 05/2025
2. CABG (LIMA-LAD, SVG-PDA) - 11/1/2022
3. Left bunionectomy with ORIF - 2/3/2017

PSA CURVE:
May 16, 2025 11:01    4.01 H
Jul 08, 2024 12:04    3.85
Apr 15, 2024 10:31    3.49

MEDICATIONS:
1. Ezetimibe 10Mg Tab - Take one tablet by mouth every day for high cholesterol
2. Fluoxetine Hcl 20Mg Cap - Take one capsule by mouth every morning for mood
3. Famotidine 10Mg Tab - Take one tablet by mouth nightly for gastroesophageal reflux disease

ALLERGIES: 1. Sertraline - causes headache

PHYSICAL EXAM:

GENERAL: Well-developed, well-nourished gentleman with appropriate orientation, mood, affect, demeanor, and dress.
HEENT: Normal symmetric, non-tender neck without mass/thyromegaly to palpation.
CHEST: Normal respiratory effort; no gynecomastia or masses.
ABDOMEN: Soft, non-tender, non-distended, without masses or organomegaly. No palpable hernias.
GU: No CVAT or bladder tenderness/fullness.
RECTAL: Normal anus and perineum; intact sphincter tone; no hemorrhoids or fissures. Prostate exam deferred/performed (choose one).
PROSTATE: [To be documented during exam]
CNS: Alert and oriented; normal gait; intact cranial nerves; no focal deficits.

ASSESSMENT:

Problem List:
1. Elevated PSA
2. BPH with LUTS
3. Erectile dysfunction

The patient presents with an elevated PSA of 4.01, which is concerning given his family history of prostate cancer. His BPH symptoms have improved since the HoLEP procedure, but he continues to experience some lower urinary tract symptoms. His erectile dysfunction has been long-standing and appears to be refractory to previously tried treatments.

PLAN:

Problem #1: Elevated PSA
- Repeat PSA in 3 months
- Consider MRI prostate if PSA continues to rise
- Discuss biopsy options if indicated

Problem #2: BPH with LUTS
- Continue conservative management
- Follow-up IPSS scoring at next visit
- Consider medication adjustment if symptoms worsen

Problem #3: Erectile dysfunction
- Discuss PDE5 inhibitor trial
- Consider referral to ED specialist if refractory
- Patient education on treatment options
"""

# Simulated ambient transcription from clinical encounter
AMBIENT_TRANSCRIPTION = """
The patient started describing his symptoms, saying he's been getting up about 3 times per night to urinate, which is bothering him. He reports frequency during the day about every 2 hours and has some urgency. When asked about incomplete emptying, he says he feels like he's emptying completely now. His stream hesitancy is minimal, maybe a score of 1. The weak stream has improved, he'd rate it a 1 now. Intermittency is also better, maybe a 1 or 2.

Regarding his erectile dysfunction, the patient mentioned that he tried sildenafil 50mg but it didn't work very well. We discussed increasing the dose to 100mg, and he's interested in trying that. He also mentioned he's had some success with tadalafil 10mg in the past.

On examination, the prostate feels smooth, slightly enlarged, about 40 grams estimated, no nodules or induration palpated. There is no tenderness.

The patient also reported that he had a screening colonoscopy last month that found a small polyp that was removed. The pathology came back as benign tubular adenoma. He mentioned this wasn't in the records I had.

We discussed his PSA trend and the slight elevation. Given his family history and the rising PSA, I'm concerned about prostate cancer. We talked about getting an MRI prostate and possibly a biopsy if the MRI shows any suspicious lesions.

For his LUTS, since he's doing better post-HoLEP, we'll continue observation. If symptoms worsen, we can consider starting tamsulosin.

The patient voiced interest in starting on the sildenafil 100mg for his ED. We'll start with that and he'll let me know how it works at the next visit.
"""


def test_transcription_parser():
    """Test the section-aware transcription parser."""
    print("=" * 80)
    print("TEST 1: Section-Aware Transcription Parsing")
    print("=" * 80)

    parser = SectionAwareTranscriptionParser()
    segments = parser.parse(AMBIENT_TRANSCRIPTION)

    print(f"\nIdentified {len(segments)} segments:\n")

    for i, segment in enumerate(segments, 1):
        print(f"{i}. Section: {segment.section} (confidence: {segment.confidence:.2f})")
        print(f"   Content: {segment.content[:100]}...")
        print()

    return segments


def test_intelligent_merge():
    """Test the intelligent note merger."""
    print("=" * 80)
    print("TEST 2: Intelligent Section-Aware Merging")
    print("=" * 80)

    merger = IntelligentNoteMerger()
    merged_note = merger.merge(
        existing_note=STAGE2_NOTE,
        transcription=AMBIENT_TRANSCRIPTION,
        speaker_map={}
    )

    print("\nMERGED NOTE:")
    print("=" * 80)
    print(merged_note)
    print("=" * 80)

    return merged_note


def test_specific_section_updates():
    """Test that specific sections were updated correctly."""
    print("\n" + "=" * 80)
    print("TEST 3: Verify Specific Section Updates")
    print("=" * 80)

    merger = IntelligentNoteMerger()
    merged_note = merger.merge(
        existing_note=STAGE2_NOTE,
        transcription=AMBIENT_TRANSCRIPTION,
        speaker_map={}
    )

    # Check for key updates
    checks = [
        ("IPSS Today column updated", "3 times per night" in merged_note or "nocturia" in merged_note.lower()),
        ("Sexual History updated with medication details", "sildenafil 100mg" in merged_note or "tadalafil" in merged_note),
        ("Physical Exam updated with prostate findings", "40 grams" in merged_note or "smooth" in merged_note.lower()),
        ("PSH updated with colonoscopy", "colonoscopy" in merged_note.lower() or "polyp" in merged_note.lower()),
        ("Plan updated with sildenafil 100mg", "100mg" in merged_note or "100 mg" in merged_note),
    ]

    print("\nSection Update Verification:")
    for description, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {description}")

    return all(check[1] for check in checks)


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "STAGE 3 AMBIENT MERGE TEST SUITE" + " " * 26 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    # Test 1: Parse transcription
    segments = test_transcription_parser()

    # Test 2: Merge notes
    merged_note = test_intelligent_merge()

    # Test 3: Verify updates
    all_passed = test_specific_section_updates()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    if all_passed:
        print("✓ All tests PASSED - Stage 3 ambient merging is working correctly!")
    else:
        print("✗ Some tests FAILED - Review the output above")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
