"""
Test script for consult request extraction
"""

from app.services.note_processing.extractors.consult_request_extractor import extract_consult_request
from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.note_builder import build_urology_note


def test_consult_request_extraction():
    """Test extraction of CC and HPI from consult request form"""
    print("="*80)
    print("TESTING CONSULT REQUEST EXTRACTION WITH input.txt")
    print("="*80)

    # Read the actual input file that's been failing
    with open('../logs/input.txt', 'r') as f:
        consult_doc = f.read()

    print("\n[1/3] Testing consult request identification...")
    notes_dict = identify_notes(consult_doc)
    consult_count = len(notes_dict.get("consult_requests", []))
    print(f"      Found {consult_count} consult request(s)")

    if consult_count > 0:
        print(f"      First consult request date: {notes_dict['consult_requests'][0]['date']}")

    print("\n[2/3] Testing CC and HPI extraction...")
    if consult_count > 0:
        consult_data = extract_consult_request(notes_dict["consult_requests"][0]["content"])
        if consult_data:
            print(f"\n      CC: {consult_data.get('CC', 'NOT FOUND')}")
            print(f"\n      HPI:\n{consult_data.get('HPI', 'NOT FOUND')}")
        else:
            print("      ERROR: Failed to extract consult data")
    else:
        print("      ERROR: No consult requests found")

    print("\n[3/3] Testing full note generation...")
    final_note = build_urology_note(consult_doc)

    print("\n" + "="*80)
    print("GENERATED CONSULT NOTE:")
    print("="*80)
    print(final_note)

    print("\n" + "="*80)
    print("TEST COMPLETE - Saving to ../logs/note.log")
    print("="*80)

    # Save to note.log for comparison
    with open('../logs/note.log', 'w') as f:
        f.write(final_note)


if __name__ == "__main__":
    test_consult_request_extraction()
