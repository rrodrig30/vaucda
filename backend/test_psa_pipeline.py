#!/usr/bin/env python3
"""Debug PSA data flow through the note building pipeline."""

from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.agents.gu_agent import process_gu_notes
from app.services.note_processing.extractors import extract_psa
from app.services.note_processing.agents.psa_agent import synthesize_psa

# Read the actual consult input
with open('/home/gulab/PythonProjects/VAUCDA/logs/input.txt', 'r') as f:
    clinical_document = f.read()

print("="*80)
print("TRACING PSA DATA FLOW")
print("="*80)

# Step 1: Document-level PSA extraction
print("\n[1] Document-level PSA extraction:")
document_psa = extract_psa(clinical_document)
if document_psa:
    print(f"✓ Found PSA data ({len(document_psa)} chars)")
    print(document_psa[:200])
else:
    print("✗ No PSA data found at document level")

# Step 2: Identify notes
print("\n[2] Identifying notes:")
notes_dict = identify_notes(clinical_document)
gu_count = len(notes_dict["gu_notes"])
print(f"Found {gu_count} GU notes")

# Step 3: Process GU notes
print("\n[3] Processing GU notes:")
gu_notes = process_gu_notes(notes_dict["gu_notes"])
print(f"Processed {len(gu_notes)} GU note dictionaries")

if gu_notes:
    print("\nGU note #1 keys:")
    print(list(gu_notes[0].keys()))

    if 'PSA' in gu_notes[0]:
        print(f"\n✓ GU note has PSA field:")
        print(gu_notes[0]['PSA'][:200] if gu_notes[0]['PSA'] else "(empty)")
    else:
        print("\n✗ GU note does NOT have PSA field")

# Step 4: Synthesize PSA from GU notes
print("\n[4] Synthesizing PSA from GU notes:")
psa_synthesized = synthesize_psa(gu_notes)
if psa_synthesized:
    print(f"✓ Synthesized PSA ({len(psa_synthesized)} chars):")
    print(psa_synthesized)
else:
    print("✗ No PSA synthesized from GU notes")

# Step 5: Check which path note_builder.py would take
print("\n[5] Note builder logic:")
is_consult = len(notes_dict.get("consult_requests", [])) > 0
print(f"is_consult: {is_consult}")
print(f"gu_notes count: {len(gu_notes)}")

if is_consult and not gu_notes:
    print("→ Would use document_psa directly")
else:
    print("→ Would use synthesize_psa(gu_notes)")
    print(f"   Result would be: {'PSA data' if psa_synthesized else 'empty'}")

print("\n" + "="*80)
