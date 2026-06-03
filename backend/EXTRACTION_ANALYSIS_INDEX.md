# VAUCDA Clinical Data Extraction Failures - Complete Analysis Index

**Status**: RESEARCH PHASE COMPLETE
**Date**: December 26, 2025
**Task**: Analyze 4 critical extraction failures in VAUCDA clinical note generator

---

## Overview

This directory contains comprehensive analysis of 4 clinical data extraction failures affecting the VAUCDA system:

1. **Age Extraction Error**: Extracting child's age (17) instead of patient's age (66)
2. **PSA Curve Incompleteness**: Missing recent elevated PSA values from VA lab format (2024-2025)
3. **HPI Missing**: Shows "Unknown" instead of synthesizing from available data
4. **Social History Garbled**: Includes child description ("17 yo w/ Down's") instead of patient data

All failures stem from **insufficient context awareness** and **missing fallback mechanisms**.

---

## Analysis Documents

### 1. EXTRACTION_FAILURE_ANALYSIS.md (22KB)
**Comprehensive deep-dive analysis of all 4 failures**

**Contains**:
- Executive summary
- Detailed root cause analysis for each issue
- Code location identification
- Why current approaches fail
- Evidence of gaps with examples
- Summary table of root causes
- High-level recommended fixes
- Code files requiring modification
- Conclusion synthesizing all issues

**Read this for**: Understanding WHY the failures occur and what mechanisms cause them

**Key sections**:
- Issue 1: Age Extraction - Context Ambiguity Problem
- Issue 2: PSA Extraction - Format Coverage Gap
- Issue 3: HPI Generation - Synthesis Fallback Missing
- Issue 4: Social History - Section Boundary Violation

---

### 2. EXTRACTION_FAILURE_QUICK_REFERENCE.md (8.7KB)
**Visual, matrix-based quick reference guide**

**Contains**:
- Issue comparison matrix (one-page overview)
- Code snippets showing CURRENT vs. EXPECTED behavior
- Problem code locations with line numbers
- "FIX APPROACH" sections for each issue
- Testing requirements with example inputs/outputs
- Implementation checklist
- Priority order
- Related files to review

**Read this for**: Quick understanding of each issue and what needs fixing

**Best for**: Planning implementation order, test case design, developer reference

---

### 3. EXTRACTION_FIXES_SPECIFICATIONS.md (33KB)
**Detailed technical specifications for implementing fixes**

**Contains**:
- For each of the 4 issues:
  - Current implementation code (with line numbers)
  - Root cause analysis (what's wrong and why)
  - 3 proposed solution approaches for each issue
  - Recommended approach with implementation examples
  - Pseudocode/actual code snippets ready for implementation

**Specific implementations provided**:
- Fix 1: Age Extraction
  - Approach 1: Section-bounded extraction (RECOMMENDED)
  - Approach 2: Proximity-based ranking (fallback)
  - Approach 3: Enhanced deduplication (easiest)

- Fix 2: PSA Extraction
  - Approach 1: Extended lookahead
  - Approach 2: Multiple patterns for format variations (RECOMMENDED)
  - Approach 3: Context window limiting

- Fix 3: HPI Synthesis
  - Approach 1: Input validation + prioritization (RECOMMENDED)
  - Approach 2: Fallback synthesis chain
  - Approach 3: Upstream validation in note_builder

- Fix 4: Social History Boundaries
  - Approach 1: Section-bounded extraction with isolation (RECOMMENDED)
  - Approach 2: Semantic validation enhancement

**Read this for**: Implementation details, code patterns, exact changes needed

**Best for**: Developers doing the actual code modifications

---

## Quick Navigation

### I want to understand the problems
→ Start with **EXTRACTION_FAILURE_QUICK_REFERENCE.md**

### I need comprehensive analysis of root causes
→ Read **EXTRACTION_FAILURE_ANALYSIS.md** sections on each issue

### I'm implementing the fixes
→ Use **EXTRACTION_FIXES_SPECIFICATIONS.md** for code examples

### I need a one-page overview
→ See EXTRACTION_FAILURE_QUICK_REFERENCE.md Issue Comparison Matrix

### I'm planning test cases
→ See EXTRACTION_FAILURE_QUICK_REFERENCE.md Testing Requirements section

---

## Issue Summary Table

| Issue | Severity | Root Cause | Fix Complexity | Files Affected |
|-------|----------|-----------|-----------------|-----------------|
| Age Extraction | CRITICAL | No context differentiation between patient/family | Medium | entity_extractor.py |
| PSA Curve | CRITICAL | VA lab format gaps; restrictive regex lookahead | Medium | psa_extractor.py |
| HPI Synthesis | HIGH | No fallback when extraction empty | Low | hpi_agent.py, note_builder.py |
| Social History | HIGH | Section boundaries not enforced | Medium | social_extractor.py, entity_extractor.py |

---

## Implementation Priority

### Phase 1: CRITICAL (Demographics & Clinical Accuracy)
1. **Age Extraction Fix** (2 hours)
   - Impact: Correct patient demographics
   - Complexity: Medium
   - Files: entity_extractor.py

2. **PSA Curve Fix** (1.5 hours)
   - Impact: Complete prostate cancer risk assessment
   - Complexity: Medium
   - Files: psa_extractor.py

### Phase 2: HIGH (Documentation Quality)
3. **HPI Synthesis Fix** (1.5 hours)
   - Impact: No more "Unknown" HPI sections
   - Complexity: Low
   - Files: hpi_agent.py, note_builder.py

4. **Social History Fix** (2 hours)
   - Impact: Clean, accurate social history
   - Complexity: Medium
   - Files: social_extractor.py, entity_extractor.py

**Total estimated implementation time**: 7 hours

---

## Code Files to Modify

### Primary Files
1. `/home/exx/PycharmProjects/vaucda/backend/app/services/entity_extractor.py`
   - Lines 49-54: Age patterns
   - Lines 471-486: Age deduplication logic
   - Lines 268-316: Validation rules

2. `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/extractors/psa_extractor.py`
   - Lines 63-73: VA lab pattern

3. `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/agents/hpi_agent.py`
   - Lines 106-277: synthesize_consult_hpi() function
   - Lines 13-103: synthesize_hpi() function

4. `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/extractors/social_extractor.py`
   - Lines 11-63: extract_social() function
   - Lines 77-139: _extract_social_narrative() function
   - Lines 142-190: _filter_healthcare_maintenance() function

### Secondary Files
5. `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/extractors/hpi_extractor.py`
   - Lines 10-43: extract_hpi() function

6. `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/note_builder.py`
   - Validation layer for HPI synthesis calls

---

## Test Coverage Plan

### Test Case 1: Age Disambiguation
**File**: entity_extractor.py (test_extract_with_regex for age field)
```
Input: Document with "66YO MALE" and "17 yo w/ Down's"
Expected: age=66
Status: Currently FAILS (returns 17)
```

### Test Case 2: PSA Recent Values
**File**: psa_extractor.py (test_extract_psa)
```
Input: VA lab format with 2024-2025 dates
Expected: All PSA values from 2024-2025 extracted
Status: Currently FAILS (missing recent values)
```

### Test Case 3: HPI Synthesis
**File**: hpi_agent.py (test_synthesize_consult_hpi)
```
Input: Consult request with reason for consult
Expected: Synthesized narrative HPI
Status: Currently FAILS (returns "Unknown")
```

### Test Case 4: Social History Boundaries
**File**: social_extractor.py (test_extract_social)
```
Input: Document with patient social history + family history
Expected: Patient alcohol history only
Status: Currently FAILS (returns family member data)
```

---

## Key Insights

### Root Cause Pattern
All four failures share a common pattern:
1. **Extraction patterns lack context awareness**
   - Match anywhere in document without understanding section/role
   - No distinction between patient vs. family member vs. system data

2. **Missing fallback mechanisms**
   - When primary extraction fails, no secondary attempt
   - No synthesis from alternative data sources
   - No placeholder value detection/replacement

3. **Weak validation**
   - Accepts any match that passes basic range validation
   - No semantic validation (garbage characters, inconsistent context)
   - No deduplication logic sophisticated enough to rank by context

### Recommended Fix Strategy
1. **Enforce section boundaries** (where data comes from matters)
2. **Add context awareness** (patient demographics ≠ family history ≠ clinical findings)
3. **Implement smart fallbacks** (alternative sources and synthesis)
4. **Enhance validation** (semantic checks beyond range validation)

---

## Document Relationships

```
EXTRACTION_FAILURE_QUICK_REFERENCE.md
  ├─> High-level overview
  ├─> Problem identification
  └─> Implementation checklist

         ↓ (Details needed?)

EXTRACTION_FAILURE_ANALYSIS.md
  ├─> Deep root cause analysis
  ├─> Code location references
  ├─> Evidence of gaps
  └─> High-level fix approaches

         ↓ (Ready to implement?)

EXTRACTION_FIXES_SPECIFICATIONS.md
  ├─> Current implementation code
  ├─> Multiple solution approaches
  ├─> Recommended implementation
  ├─> Code snippets/patterns
  └─> Integration points
```

---

## Next Steps

### For Research/Planning
1. Read EXTRACTION_FAILURE_QUICK_REFERENCE.md (10 min)
2. Read EXTRACTION_FAILURE_ANALYSIS.md (30 min)
3. Review EXTRACTION_FIXES_SPECIFICATIONS.md table of contents (5 min)

### For Implementation
1. Select issue to fix (recommend: Age first)
2. Open EXTRACTION_FIXES_SPECIFICATIONS.md to specific issue section
3. Choose recommended approach
4. Use provided code snippets as template
5. Create test case from QUICK_REFERENCE.md Testing Requirements
6. Implement and test
7. Move to next issue

### For Code Review
1. Compare implementation against recommended approach in SPECIFICATIONS
2. Verify test cases from QUICK_REFERENCE.md pass
3. Check for regressions in related extractors
4. Validate deduplication logic handles edge cases

---

## Document Statistics

| Document | Size | Sections | Content Type |
|----------|------|----------|--------------|
| EXTRACTION_FAILURE_ANALYSIS.md | 22KB | 9 main | Analysis |
| EXTRACTION_FAILURE_QUICK_REFERENCE.md | 8.7KB | 8 main | Reference |
| EXTRACTION_FIXES_SPECIFICATIONS.md | 33KB | 4 main (+ 3 approaches each) | Implementation |
| **Total** | **63.7KB** | **21+** | **Complete Analysis** |

---

## Contact & Questions

For clarifications on:
- **Root causes**: See EXTRACTION_FAILURE_ANALYSIS.md
- **Quick overview**: See EXTRACTION_FAILURE_QUICK_REFERENCE.md
- **Implementation details**: See EXTRACTION_FIXES_SPECIFICATIONS.md

All analysis is self-contained; no external references required.

---

**Analysis Status**: COMPLETE - RESEARCH PHASE FINISHED
**Next Phase**: IMPLEMENTATION (not started)
**Recommendation**: Begin with Age Extraction fix (highest impact, clear solution)

---

**Generated**: December 26, 2025
**For**: VAUCDA Development Team
**Task Status**: Research Complete - Ready for Implementation Planning
