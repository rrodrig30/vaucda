# VAUCDA Extraction Failures - Quick Reference Guide

## Issue Comparison Matrix

| Aspect | Age | PSA | HPI | Social |
|--------|-----|-----|-----|--------|
| **Symptom** | Returns 17 instead of 66 | Missing 2024-25 values | Shows "Unknown" | Garbled with child data |
| **Root Cause** | No context differentiation | Format gaps in VA labs | No fallback synthesis | Boundary enforcement missing |
| **Error Type** | Pattern matching | Pattern matching | Logic/fallback | Pattern + validation |
| **Severity** | CRITICAL | CRITICAL | HIGH | HIGH |
| **Patient Impact** | Wrong demographics | Incomplete prostate cancer risk assessment | Incomplete documentation | Confusing/inaccurate history |

---

## Issue 1: Age Extraction Error

```
DOCUMENT CONTAINS:
  Patient: "66YO MALE"                      <- CORRECT
  Family: "17 yo w/ Down's"                 <- INCORRECT (child)

CURRENT BEHAVIOR:
  ✗ Extracts first match: 17
  ✗ Deduplication doesn't re-rank effectively
  ✗ Returns age 17 (WRONG)

PROBLEM CODE:
  entity_extractor.py, lines 49-54
  - Patterns: r'(\d{1,3})[-\s]*y\.?o\.?'
  - Matches ANY "##yo" in full document
  - No context awareness

FIX APPROACH:
  1. Extract age from patient demographics section only
  2. Use context: "PATIENT:", "Age:", "DOB:" keywords
  3. Improve deduplication to re-rank by proximity to patient info
  4. Validate final age against demographic location
```

---

## Issue 2: PSA Curve Missing Recent Values

```
DOCUMENT CONTAINS (VA Lab Format):
  Specimen Collection Date: Apr 11, 2025@12:17
  ================== CHEMISTRY PANEL ==================
  PSA TOTAL                      6.88     ng/mL   <- MISSING

CURRENT BEHAVIOR:
  ✓ Extracts old values (2012-2018)
  ✗ Misses recent values (2024-2025)
  ✗ Pattern fails on dividers/formatting

PROBLEM CODE:
  psa_extractor.py, lines 63-73
  - Pattern: va_lab_pattern with restrictive lookahead
  - r'(?:(?!Specimen Collection Date|={10,})[\s\S])*?'
  - Breaks when "========" section headers present
  - Format variation not covered

FIX APPROACH:
  1. Allow "=" dividers in lookahead
  2. Add standalone PSA TOTAL pattern with preceding date context
  3. Extend to cover all VA lab format variations
  4. Add test cases with actual VA EMR output
```

---

## Issue 3: HPI Shows "Unknown"

```
DOCUMENT CONTAINS:
  Consult Reason: "Evaluation for elevated PSA"  <- AVAILABLE
  PCP Note HPI: "Patient with BPH and recent PSA elevation"  <- AVAILABLE

CURRENT BEHAVIOR:
  ✗ HPI extractor returns "" (no "HPI:" section found)
  ✗ No fallback to synthesize from consult_reason
  ✗ Displays placeholder: "HPI: Unknown"

PROBLEM CODE:
  hpi_extractor.py, lines 10-43
    - Only looks for "HPI:" section
    - Returns "" if not found
    - No synthesis fallback

  hpi_agent.py, synthesize_consult_hpi()
    - Depends on parameters passed
    - No data source validation
    - May receive empty consult_reason

FIX APPROACH:
  1. Check extraction result; if empty, trigger fallback
  2. Priority: consult_reason > pcp_note_hpi > chief_complaint > empty
  3. Synthesize from available data even if HPI section missing
  4. Remove zero-temperature constraint when sparse data
```

---

## Issue 4: Social History Garbled Output

```
DOCUMENT CONTAINS:
  SOCIAL HISTORY:
    Alcohol: Denies              <- PATIENT DATA (correct)

  FAMILY HISTORY:
    Sister - 17 yo w/ Down's     <- FAMILY DATA
    Alcohol: ; 17 yo w/ Down's   <- MALFORMED FAMILY DATA

CURRENT BEHAVIOR:
  ✗ Returns: "Alcohol: ; 17 yo w/ Down's"  (from family section)
  ✗ Should return: "Alcohol: Denies"  (from social section)
  ✗ Section boundaries not enforced

PROBLEM CODE:
  social_extractor.py, lines 77-139
    - _extract_social_narrative() receives FULL document
    - Pattern: r'Alcohol\s*[:-]\s*([^\n]+)'
    - Matches in ANY section (not just social)
    - First match from family history section
    - No validation of captured content (";")

  social_extractor.py, lines 11-63
    - Multiple extraction sources: pattern1, narrative, PCP
    - Combines all without dedup
    - Garbled data gets included

FIX APPROACH:
  1. Extract "SOCIAL HISTORY:" section boundary FIRST
  2. Pass ONLY bounded section to _extract_social_narrative()
  3. Don't apply broad patterns to full document
  4. Add validation: reject "yo w/" + family names
  5. Reject garbage characters (lone semicolon)
  6. Deduplicate when combining multiple sources
```

---

## Code Location Quick Map

```
Backend Structure:
  backend/
    app/services/
      entity_extractor.py                    <- Issue 1 (Age)
        _extract_with_regex()                  [lines 222-266]
        _deduplicate_entities()                [lines 444-492]

      note_processing/
        extractors/
          psa_extractor.py                   <- Issue 2 (PSA)
            extract_psa()                      [lines 10-87]

          hpi_extractor.py                   <- Issue 3 (HPI)
            extract_hpi()                      [lines 10-43]

          social_extractor.py                <- Issue 4 (Social)
            extract_social()                   [lines 11-63]
            _extract_social_narrative()        [lines 77-139]

        agents/
          hpi_agent.py                       <- Issue 3 (HPI Synthesis)
            synthesize_consult_hpi()           [lines 106-277]
```

---

## Priority Implementation Order

### Phase 1: CRITICAL (Demographics & Clinical Data)
1. **Fix Age Extraction** (Entity Extractor)
   - Time: 2 hours
   - Impact: Correct patient demographics
   - Complexity: Medium (regex + logic)

2. **Fix PSA Curve Completeness** (PSA Extractor)
   - Time: 1.5 hours
   - Impact: Complete prostate cancer risk data
   - Complexity: Medium (regex patterns)

### Phase 2: HIGH (Documentation Completeness)
3. **Fix HPI Synthesis Fallback** (HPI Agent + Extractor)
   - Time: 1.5 hours
   - Impact: No more "Unknown" HPI sections
   - Complexity: Low (logic flow)

4. **Fix Social History Boundaries** (Social Extractor)
   - Time: 2 hours
   - Impact: Clean, accurate social history
   - Complexity: Medium (pattern scope + validation)

---

## Testing Requirements

### Test 1: Age Extraction
```python
document = """
Patient: 66YO MALE
Chief Complaint: Elevated PSA

Family History:
Sister: 17 yo w/ Down's syndrome
"""

CURRENT: age=17 (FAIL)
EXPECTED: age=66 (PASS)
```

### Test 2: PSA Recent Values
```python
document = """
Specimen Collection Date: Apr 11, 2025@12:17
================== CHEMISTRY PANEL ==================
PSA TOTAL                      6.88     ng/mL

Specimen Collection Date: May 15, 2025@10:22
================== CHEMISTRY PANEL ==================
PSA TOTAL                      7.28     ng/mL
"""

CURRENT: Returns only old values (FAIL)
EXPECTED: Returns [6.88, 7.28] (PASS)
```

### Test 3: HPI Synthesis
```python
consult_reason = "Evaluation for elevated PSA"
pcp_note_hpi = "Patient with history of prostate cancer screening"

CURRENT: Returns "Unknown" (FAIL)
EXPECTED: Returns synthesized narrative (PASS)
```

### Test 4: Social History
```python
document = """
SOCIAL HISTORY:
Alcohol: Denies

FAMILY HISTORY:
Sister - 17 yo w/ Down's
Alcohol: ; 17 yo w/ Down's
"""

CURRENT: Returns "Alcohol: ; 17 yo w/ Down's" (FAIL)
EXPECTED: Returns "Alcohol: Denies" (PASS)
```

---

## Implementation Checklist

### Age Fix
- [ ] Identify patient demographics section boundaries
- [ ] Modify entity_extractor to extract age from demographics only
- [ ] Enhance deduplication logic with semantic ranking
- [ ] Add test case: document with patient age + family ages
- [ ] Verify all extractors use bounded sections

### PSA Fix
- [ ] Document VA lab format variations
- [ ] Expand va_lab_pattern to handle dividers
- [ ] Add alternative PSA TOTAL patterns
- [ ] Test against 5+ VA EMR lab output samples
- [ ] Verify all 2024-2025 values extracted

### HPI Fix
- [ ] Add fallback logic in synthesize_consult_hpi()
- [ ] Implement data source prioritization
- [ ] Add synthesis trigger when extraction empty
- [ ] Test with consult requests lacking explicit HPI
- [ ] Verify no more "Unknown" placeholders

### Social Fix
- [ ] Extract and pass bounded SOCIAL HISTORY section
- [ ] Add semantic validation rules
- [ ] Filter family member descriptions
- [ ] Reject garbage characters
- [ ] Add deduplication for multi-source extraction
- [ ] Test with documents mixing social + family data

---

## Related Files to Review

- `note_builder.py` - Orchestrator calling all extractors
- `note_identifier.py` - Identifies document sections
- `entity_extractor.py` - Central entity extraction hub
- `llm_helper.py` - LLM synthesis functions
- Test files: `test_extraction_fixes.py`, `test_entity_extraction.py`

---

**Document Status**: Analysis Complete - Ready for Implementation
**Last Updated**: December 26, 2025
