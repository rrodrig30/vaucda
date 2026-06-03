# VAUCDA Extraction Fixes - Technical Specifications

**Status**: RESEARCH COMPLETE - Detailed Fix Specifications
**Date**: December 26, 2025
**Scope**: Technical details for implementing 4 extraction fixes

---

## Fix 1: Age Extraction - Context-Aware Differentiation

### Current Implementation
**File**: `/home/exx/PycharmProjects/vaucda/backend/app/services/entity_extractor.py`

```python
# Lines 49-54 (CURRENT - PROBLEMATIC)
'age': [
    r'(\d{1,3})[-\s]*y\.?o\.?',                          # 74yo, 74-y.o., 74 y.o.
    r'(\d{1,3})[-\s]+years?[-\s]+old',                   # 74-year-old, 74 years old
    r'age\s*[:=]?\s*(\d{1,3})\b',                        # age: 74 or age 74
],

# Lines 222-266 (_extract_with_regex - CURRENT)
for field, patterns in self.ENTITY_PATTERNS.items():
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            # ... extract and validate
            entities.append({
                'field': field,
                'value': value,
                'confidence': 0.9,
                'source_text': match.group(0),
                'extraction_method': 'regex'
            })

# Lines 471-486 (_deduplicate_entities - CURRENT AGE LOGIC)
elif field == 'age':
    try:
        new_age = int(value)
        old_age = int(existing['value'])
        new_in_range = 50 <= new_age <= 90
        old_in_range = 50 <= old_age <= 90
        if new_in_range and not old_in_range:
            seen_fields[field] = entity
        elif new_in_range and old_in_range:
            if entity['confidence'] > existing['confidence'] or new_age > old_age:
                seen_fields[field] = entity
```

### Root Cause Analysis

**Problem 1: No Context Awareness**
- Pattern `r'(\d{1,3})[-\s]*y\.?o\.?'` matches "17yo" from "17 yo w/ Down's"
- Pattern `r'age\s*[:=]?\s*(\d{1,3})\b'` matches both "age: 66" (patient) and "age: 17" (family member)
- No mechanism to distinguish between patient demographics section and family history section

**Problem 2: Deduplication Insufficient**
- Collects all matches first: [entity(age=17, conf=0.9), entity(age=66, conf=0.9)]
- Deduplication logic prefers age in 50-90 range, BUT:
  - Only when one is in range and one is not
  - When both are in range (both 50-90), uses confidence (equal at 0.9) or highest value (66 > 17, so picks 66)
  - **BUT**: Dictionary iteration order may pick 17 first, then doesn't update if 66 comes later at same confidence

**Problem 3: No Proximity Analysis**
- Doesn't analyze HOW CLOSE age is to patient identifiers ("PATIENT:", "Age:", "DOB:")
- Doesn't check section headers to determine if age is in demographics vs. family section

---

### Proposed Solution

**Approach 1: Section-Bounded Extraction (Recommended)**

```python
# PHASE 1: Extract demographics section first
def _extract_patient_demographics_section(self, text: str) -> str:
    """
    Extract the patient demographics section from clinical document.

    Common patterns:
    - "PATIENT: Last, First Middle Age: 66..."
    - "Demographics:" or "PATIENT DEMOGRAPHICS:"
    - Consult request header with patient info

    Returns bounded section containing ONLY patient info.
    """
    # Pattern 1: Explicit "PATIENT:" line and following lines until next section
    pattern1 = r'PATIENT\s*[:=]?\s*([^\n]+(?:\n(?!(?:VISIT|CHIEF|HPI|PMH|PSH|SOCIAL|FAMILY|MEDICATIONS|PHYSICAL|ASSESSMENT))[^\n]+)*)'

    # Pattern 2: Consult header with patient name and SSN
    pattern2 = r'([A-Z]+,[A-Z]+(?:\s+[A-Z])?),?\s+(\d{3}-\d{2}-\d{4})'

    # Look for patient name and age in close proximity
    for pattern in [pattern1, pattern2]:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(0)[:500]  # Return first 500 chars of demographics

    return ""

# PHASE 2: Extract age only from demographics section
def _extract_age_from_demographics(self, text: str) -> Optional[int]:
    """Extract age from patient demographics section only."""
    # Only search in demographics section
    demo_section = self._extract_patient_demographics_section(text)

    if not demo_section:
        # Fallback: try age pattern with context requiring "Age:" prefix
        pattern = r'Age\s*[:=]?\s*(\d{1,3})\b'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            age = int(match.group(1))
            if 18 <= age <= 120:  # Adult range
                return age
        return None

    # Try age patterns within demographics section
    age_patterns = [
        r'Age\s*[:=]?\s*(\d{1,3})\b',
        r'(\d{1,3})[-\s]*y\.?o\.?(?:\s|,|$)',  # Only match if followed by space/comma/EOL
    ]

    for pattern in age_patterns:
        match = re.search(pattern, demo_section, re.IGNORECASE)
        if match:
            age = int(match.group(1))
            if 18 <= age <= 120:
                return age

    return None
```

**Approach 2: Proximity-Based Ranking (Fallback)**

```python
def _calculate_proximity_score(self, age_text: str, age_position: int,
                               full_text: str) -> float:
    """
    Score extracted age based on proximity to patient identifiers.

    Higher score = closer to patient info, lower score = likely family member.
    """
    # Find distances to key patient identifiers
    patient_keywords = ['PATIENT:', 'Age:', 'DOB:', 'MRN:', 'CPRS']

    min_distance = len(full_text)
    for keyword in patient_keywords:
        pos = full_text.rfind(keyword, 0, age_position + 20)  # Within ~20 chars
        if pos != -1:
            min_distance = min(min_distance, abs(age_position - pos))

    # Find distance to section headers indicating family/social
    family_keywords = ['FAMILY HISTORY:', 'SOCIAL HISTORY:', 'FAMILY:', 'SOCIAL:',
                      'Brother', 'Sister', 'Father', 'Mother', 'Daughter', 'Son',
                      'w/ Down', 'with Down', 'family member']

    family_distance = len(full_text)
    for keyword in family_keywords:
        pos = full_text.rfind(keyword, 0, age_position + 30)
        if pos != -1:
            family_distance = min(family_distance, abs(age_position - pos))

    # Calculate proximity score (0.0 - 1.0)
    # Closer to patient keywords = higher score
    # Closer to family keywords = lower score
    patient_proximity = 1.0 / (1.0 + min_distance / 100.0)
    family_proximity = 1.0 / (1.0 + family_distance / 100.0)

    proximity_score = patient_proximity - family_proximity
    return max(0.0, min(1.0, proximity_score))

def _extract_age_with_proximity_ranking(self, text: str) -> Optional[int]:
    """Extract age using proximity-based ranking for disambiguation."""
    # Find all age matches with their positions
    age_candidates = []

    age_patterns = [
        r'(\d{1,3})[-\s]*y\.?o\.?',
        r'(\d{1,3})[-\s]+years?[-\s]+old',
        r'age\s*[:=]?\s*(\d{1,3})\b',
    ]

    for pattern in age_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            age = int(match.group(1))
            if 18 <= age <= 120:
                position = match.start()
                proximity_score = self._calculate_proximity_score(
                    match.group(0), position, text
                )
                age_candidates.append({
                    'value': age,
                    'confidence': 0.9 + (proximity_score * 0.1),  # Boost by proximity
                    'position': position,
                    'source_text': match.group(0),
                    'proximity_score': proximity_score
                })

    if not age_candidates:
        return None

    # Return highest confidence candidate
    best = max(age_candidates, key=lambda x: x['confidence'])
    return best['value']
```

**Approach 3: Enhanced Deduplication (Easiest to Implement)**

```python
def _deduplicate_entities_improved(self, entities: List[Dict]) -> List[Dict]:
    """Improved deduplication with better age handling."""
    seen_fields = {}

    for entity in entities:
        field = entity['field']
        value = entity['value']

        if field not in seen_fields:
            seen_fields[field] = [entity]  # Keep list of candidates
        else:
            seen_fields[field].append(entity)

    # Process deduplicated fields
    result = {}
    for field, candidates in seen_fields.items():
        if field == 'age' and len(candidates) > 1:
            # Sort by proximity to patient info (via confidence + semantic score)
            # Prefer ages in typical urology patient range (40-90)
            # Then by confidence
            def age_score(entity):
                age = int(entity['value'])
                in_typical_range = 40 <= age <= 90
                conf = entity['confidence']
                proximity = entity.get('proximity_score', 0.5)

                # Score: (is in range ? +1 : -1) + confidence + proximity
                return (1 if in_typical_range else -1) + conf + proximity

            best = max(candidates, key=age_score)
            result[field] = best
        else:
            # Default: keep highest confidence
            best = max(candidates, key=lambda e: e['confidence'])
            result[field] = best

    return list(result.values())
```

### Recommended Implementation

**Use Approach 1 + Approach 3 (Combination)**:
1. Extract patient demographics section first (Approach 1)
2. Extract age from bounded section
3. If not found, fallback to full document with Approach 3 deduplication
4. Reject ages that include family member markers

---

## Fix 2: PSA Curve - Complete VA Lab Format Support

### Current Implementation
**File**: `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/extractors/psa_extractor.py`

```python
# Lines 63-73 (CURRENT - PROBLEMATIC)
va_lab_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})(?:(?!Specimen Collection Date|={10,})[\s\S])*?PSA\s+TOTAL\s+(\d+\.?\d*)\s+n[gG]/mL'
for match in re.finditer(va_lab_pattern, note_content, re.IGNORECASE):
    date = match.group(1).strip()
    time = match.group(2).strip()
    value = match.group(3).strip()
    psa_entries.append(f"{date} {time}: {value}")
```

### Root Cause Analysis

**Problem 1: Restrictive Lookahead**
```regex
(?:(?!Specimen Collection Date|={10,})[\s\S])*?
```
This means: "Match any character EXCEPT when you see 'Specimen Collection Date' or 10+ equals signs"

**Why it fails**:
- VA EMR outputs have section dividers like `================== CHEMISTRY PANEL ==================`
- The lookahead `={10,}` matches these dividers and terminates the pattern early
- Pattern never reaches "PSA TOTAL" on the other side of the divider

**Example VA Format**:
```
Specimen Collection Date: Apr 11, 2025@12:17
================== CHEMISTRY PANEL ==================
PSA TOTAL                      6.88     ng/mL
```
Pattern fails because it sees "================" and stops

---

### Proposed Solution

**Approach 1: Extend Lookahead to Allow Common Dividers**

```python
# IMPROVED Pattern - Allow dividers and section headers between date and PSA
va_lab_pattern_v2 = r'''
    Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})
    (?:(?!Specimen Collection Date)[\s\S])*?  # Non-greedy, stop at next specimen only
    PSA\s+TOTAL\s+(\d+\.?\d*)\s+(?:n[gG]/mL|ng/mL)
'''
```

**Approach 2: Separate Patterns for Different VA Lab Variations**

```python
def extract_psa(note_content: str) -> str:
    """
    Extract PSA curve data from a clinical note.
    Supports multiple format variations including VA EMR output.
    """
    psa_entries = []

    # Pattern 0: VA Lab Result Format v1 (standard)
    # Specimen Collection Date: Apr 11, 2025@12:17
    # PSA TOTAL                      6.88     ng/mL
    pattern_va_lab_v1 = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})\s+(?:[\s\S])*?PSA\s+TOTAL\s+(\d+\.?\d*)'

    # Pattern 0b: VA Lab Result Format v2 (with dividers/headers)
    # Handles section headers between date and PSA TOTAL
    pattern_va_lab_v2 = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})(?:(?!Specimen Collection Date)[\s\S]){0,500}?PSA\s+TOTAL\s+(\d+\.?\d*)'

    # Pattern 0c: Standalone PSA TOTAL with preceding date
    # For lab results where PSA TOTAL is isolated
    # Looks for any date pattern followed by PSA TOTAL within 300 chars
    pattern_psa_standalone = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4}).*?PSA\s+TOTAL\s+(\d+\.?\d*)(?:\s+n[gG]/mL)?'

    # Pattern 1: "PSA:" or "PSA Curve:" section
    section_pattern = r'(?:PSA(?:\s+Curve)?|Prostate-Specific Antigen):\s*\n((?:.*\n)*?)(?=\n{2,}|\n(?:MEDICATIONS|ALLERGIES|PATHOLOGY|...):|$)'

    match = re.search(section_pattern, note_content, re.IGNORECASE | re.MULTILINE)
    if match:
        psa_section = match.group(1).strip()
        # Extract from PSA section (existing code)
        # ...

    # Pattern 2a: VA Lab Format v1 (standard)
    for match in re.finditer(pattern_va_lab_v1, note_content, re.IGNORECASE | re.DOTALL):
        date = match.group(1).strip()
        time = match.group(2).strip()
        value = match.group(3).strip()
        psa_entries.append(f"{date} {time}: {value}")

    # Pattern 2b: VA Lab Format v2 (with headers/dividers)
    for match in re.finditer(pattern_va_lab_v2, note_content, re.IGNORECASE | re.DOTALL):
        date = match.group(1).strip()
        time = match.group(2).strip()
        value = match.group(3).strip()
        # Check if this entry already extracted to avoid duplicates
        entry = f"{date} {time}: {value}"
        if entry not in psa_entries:
            psa_entries.append(entry)

    # Pattern 2c: Standalone PSA TOTAL (fallback)
    if not psa_entries:
        for match in re.finditer(pattern_psa_standalone, note_content, re.IGNORECASE | re.DOTALL):
            date = match.group(1).strip()
            value = match.group(2).strip()
            entry = f"{date}: {value}"
            if entry not in psa_entries:
                psa_entries.append(entry)

    # Pattern 3: Narrative mentions (existing code)
    # ...

    return '\n'.join(psa_entries)
```

**Approach 3: Context Window Limiting**

```python
# Instead of "match anything until next specimen date":
# Use fixed window to prevent runaway matching

va_lab_pattern_v3 = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})((?:(?!Specimen Collection Date).){0,800}?)PSA\s+TOTAL\s+(\d+\.?\d*)'

# Explanation:
# {0,800}? = match up to 800 chars (typical lab result block)
# (?!Specimen Collection Date) = negative lookahead for next specimen
# Prevents matching across multiple lab results
```

### Recommended Implementation

**Use Approach 2** (Multiple patterns for format variations):
1. Try Pattern 2a (standard VA lab format)
2. Try Pattern 2b (VA lab with dividers/headers)
3. Try Pattern 2c (standalone PSA TOTAL)
4. Keep Pattern 1 (explicit PSA: sections)
5. Keep Pattern 3 (narrative fallback)

---

## Fix 3: HPI Generation - Synthesis Fallback

### Current Implementation
**File**: `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/agents/hpi_agent.py`

```python
# Lines 106-277 (synthesize_consult_hpi)
def synthesize_consult_hpi(
    consult_reason: str,        # May be empty!
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None
) -> str:
    """Synthesize HPI for consult requests."""

    # ... builds context_sections ...
    full_context = '\n\n'.join(context_sections)  # May be empty!

    # If full_context is empty, LLM gets empty prompt
    # Returns deterministic "Unknown" at zero temperature
```

### Root Cause Analysis

**Problem 1: No Input Validation**
- Function accepts empty `consult_reason`
- No check to verify consult_reason has content before building prompt
- No fallback if consult_reason is empty

**Problem 2: Weak Context Building**
- Only uses parameters passed; doesn't try alternative sources
- If `consult_reason=""` and `pcp_note_data` is empty dict, context is minimal
- No validation of `context_sections` list before building prompt

**Problem 3: Zero Temperature + Empty Context = Placeholder**
- Line 274: `temperature=0.0` (deterministic)
- With empty context, LLM returns empty or "Unknown"
- No error recovery or fallback

**Problem 4: No Source Prioritization**
- Doesn't check which parameter has best data
- Treats all parameters equally
- No logic like "try consult_reason first, then PCP note, then chief complaint"

---

### Proposed Solution

**Approach 1: Input Validation + Data Source Prioritization**

```python
def synthesize_consult_hpi(
    consult_reason: str = "",
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None,
    chief_complaint: Optional[str] = None  # ADD NEW PARAMETER
) -> str:
    """
    Synthesize comprehensive HPI for consult requests with fallback handling.
    """

    # PHASE 1: Validate and gather primary HPI source
    primary_hpi_source = None
    primary_hpi_text = None

    # Priority 1: Consult reason (most direct)
    if consult_reason and consult_reason.strip():
        primary_hpi_source = "consult_reason"
        primary_hpi_text = consult_reason.strip()
    # Priority 2: PCP note HPI (clinical detail)
    elif pcp_note_data and pcp_note_data.get('hpi') and pcp_note_data['hpi'].strip():
        primary_hpi_source = "pcp_note_hpi"
        primary_hpi_text = pcp_note_data['hpi'].strip()
    # Priority 3: Chief complaint (minimal fallback)
    elif chief_complaint and chief_complaint.strip():
        primary_hpi_source = "chief_complaint"
        primary_hpi_text = chief_complaint.strip()

    # PHASE 2: If no primary source, return empty (will be flagged upstream)
    if not primary_hpi_text:
        return ""

    # PHASE 3: Build context sections with validated data
    context_sections = []

    # Always include primary HPI source
    if primary_hpi_source == "consult_reason":
        context_sections.append(f"PRIMARY SOURCE - REASON FOR CONSULT:\n{primary_hpi_text}")
    elif primary_hpi_source == "pcp_note_hpi":
        context_sections.append(f"PRIMARY SOURCE - PCP NOTE HPI:\n{primary_hpi_text}")
    else:
        context_sections.append(f"PRIMARY SOURCE - CHIEF COMPLAINT:\n{primary_hpi_text}")

    # Add supplemental data (PMH, PSH, meds, imaging, etc.)
    # ... existing code ...

    # PHASE 4: Build prompt with context validation
    full_context = '\n\n'.join(context_sections)

    # Verify context is not empty
    if not full_context.strip():
        logger.warning("HPI synthesis: No context available after validation")
        return ""

    # Build prompt
    prompt = f"""..."""

    # PHASE 5: Call LLM with appropriate temperature
    temperature = 0.0 if primary_hpi_source == "consult_reason" else 0.3

    synthesized_hpi = synthesize_with_llm(
        prompt=prompt,
        temperature=temperature
    )

    return clean_llm_commentary(synthesized_hpi)
```

**Approach 2: Fallback Synthesis Chain**

```python
def synthesize_hpi_with_fallbacks(
    primary_hpi: str = "",
    fallback_hpi_1: str = "",  # Secondary source
    fallback_hpi_2: str = "",  # Tertiary source
    patient_context: Dict[str, str] = None,
    temperature: float = 0.0
) -> str:
    """
    Synthesize HPI with fallback chain.

    Tries primary; if empty, uses fallback 1; if empty, uses fallback 2.
    If all empty, returns empty (error handled upstream).
    """
    # Select best available source
    hpi_text = primary_hpi or fallback_hpi_1 or fallback_hpi_2

    if not hpi_text:
        return ""

    # If only fallback available, increase temperature for creativity
    if not primary_hpi and fallback_hpi_1:
        temperature = 0.3
    elif not primary_hpi and not fallback_hpi_1:
        temperature = 0.5

    # Build prompt with available context
    prompt = f"""
Create a clinical HPI based on available information:

{hpi_text}

{f"Patient demographics: {patient_context['name']} age {patient_context['age']}" if patient_context else ""}

Provide only the clinical narrative, no meta-commentary.
"""

    return synthesize_with_llm(prompt, temperature=temperature)
```

**Approach 3: Upstream Validation in note_builder.py**

```python
# In note_builder.py, when calling synthesize_consult_hpi:

# BEFORE: Direct call (may receive empty consult_reason)
# synthesized_hpi = synthesize_consult_hpi(
#     consult_reason=metadata.get('reason_for_consult', '')
# )

# AFTER: Validate before calling
def synthesize_hpi_with_validation(metadata: Dict, pcp_data: Dict) -> str:
    """Synthesize HPI with input validation."""

    consult_reason = metadata.get('reason_for_consult', '').strip() or \
                    metadata.get('provisional_diagnosis', '').strip() or ""

    pcp_hpi = pcp_data.get('hpi', '').strip() if pcp_data else ""

    # Call synthesis with validated inputs
    hpi = synthesize_consult_hpi(
        consult_reason=consult_reason,
        pcp_note_data={'hpi': pcp_hpi} if pcp_hpi else None,
        # ... other parameters ...
    )

    # Validate output
    if not hpi or hpi.lower() in ['unknown', 'no information', '']:
        # Log warning and return empty
        logger.warning(f"HPI synthesis failed: returned {hpi}")
        return ""

    return hpi
```

### Recommended Implementation

**Use Approach 1 + Approach 3** (Function improvement + upstream validation):
1. Add input validation in `synthesize_consult_hpi()`
2. Add data source prioritization (consult_reason > pcp_hpi > chief_complaint)
3. Add validation in `note_builder.py` before calling synthesis
4. Check output for placeholder values ("Unknown", etc.) and log as errors
5. Return empty string if no valid HPI can be synthesized (will be handled downstream)

---

## Fix 4: Social History - Section Boundary Enforcement

### Current Implementation
**File**: `/home/exx/PycharmProjects/vaucda/backend/app/services/note_processing/extractors/social_extractor.py`

```python
# Lines 11-63 (CURRENT - PROBLEMATIC)
def extract_social(note_content: str) -> str:
    social_parts = []

    # Pattern 1: Explicit "Social History:" section
    pattern = r'(?:Social History|SOCIAL|Social Hx):\s*(.*?)(?=\n\s*(?:Family History|FAMILY:|...))'
    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        social_text = match.group(1).strip()
        # ... process ...
        social_parts.append(social_text)

    # Pattern 2: Narrative extraction (RECEIVES FULL DOCUMENT!)
    narrative_social = _extract_social_narrative(note_content)  # <- PROBLEM

    # Pattern 3: PCP extraction (RECEIVES FULL DOCUMENT!)
    pcp_social = _extract_social_from_pcp_format(note_content)  # <- PROBLEM

    # Combine all parts (may mix data from different sections!)
    combined = '\n'.join(social_parts)

# Lines 77-139 (_extract_social_narrative - CURRENT)
def _extract_social_narrative(text: str) -> str:
    """Extract social history from narrative mentions."""
    # Patterns applied to FULL document
    alcohol_patterns = [
        r'Alcohol\s*[:-]\s*([^\n]+)'  # <- MATCHES IN ANY SECTION!
    ]

    for pattern in alcohol_patterns:
        match = re.search(pattern, text, re.IGNORECASE)  # Searches FULL text
        if match:
            # May match in FAMILY HISTORY section!
            alcohol_text = match.group(1).strip()
            if alcohol_text.lower() not in ['none', 'no', 'denies']:
                social_elements.append(f"Alcohol: {alcohol_text}")
                break
```

### Root Cause Analysis

**Problem 1: Boundary Violation**
- `_extract_social_narrative()` receives FULL document
- Patterns like `r'Alcohol\s*[:-]\s*([^\n]+)'` match in ANY section
- First match wins, regardless of section
- Family history section comes AFTER social history in document
- But if family section has "Alcohol: ; 17 yo w/ Down's", it gets extracted first

**Problem 2: No Semantic Validation**
- Accepts ";" as valid alcohol history
- No check for family member descriptors ("yo w/", "with Down's", "sister", etc.)
- No filtering of malformed data

**Problem 3: Multi-source Contamination**
- Pattern 1 correctly extracts bounded "SOCIAL HISTORY:" section
- Pattern 2 narrative extraction ignores boundaries and searches full doc
- Pattern 3 PCP extraction also searches full doc
- Combining all sources mixes correct + incorrect data

---

### Proposed Solution

**Approach 1: Section-Bounded Extraction with Isolation**

```python
def extract_social(note_content: str) -> str:
    """
    Extract Social History from a clinical note with proper section boundaries.

    STRATEGY:
    1. Extract SOCIAL HISTORY section with boundaries
    2. Pass ONLY bounded section to narrative extraction
    3. Keep PCP extraction on full doc (it's designed for that)
    4. Combine with deduplication
    """
    social_parts = []

    # PHASE 1: Extract bounded "Social History:" section
    social_section_pattern = r'(?:Social History|SOCIAL|Social Hx):\s*(.*?)(?=\n\s*(?:Family History|FAMILY:|Sexual History|SEXUAL:|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    social_section = None
    match = re.search(social_section_pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        social_section = match.group(1).strip()
        if social_section.lower() not in ['noncontributory', 'none', 'not available', 'no social history']:
            social_text = re.sub(r' +', ' ', social_section)
            social_text = re.sub(r'\n{3,}', '\n\n', social_text)
            social_text = _filter_healthcare_maintenance(social_text)
            if social_text:
                social_parts.append(('explicit_section', social_text))

    # PHASE 2: Extract narrative from BOUNDED section only
    # Don't pass full document!
    if social_section:
        narrative_social = _extract_social_narrative(social_section)  # <- BOUNDED!
        if narrative_social:
            filtered = _filter_healthcare_maintenance(narrative_social)
            if filtered:
                social_parts.append(('narrative', filtered))

    # PHASE 3: Try PCP extraction on full document (it's designed for it)
    pcp_social = _extract_social_from_pcp_format(note_content)
    if pcp_social:
        filtered = _filter_healthcare_maintenance(pcp_social)
        if filtered:
            social_parts.append(('pcp', filtered))

    # PHASE 4: Combine and deduplicate
    if not social_parts:
        return ""

    # Priority: explicit_section > narrative > pcp
    # Deduplicate by content, keeping first occurrence
    seen = set()
    combined_parts = []
    for source, text in social_parts:
        normalized = ' '.join(text.lower().split())
        if normalized not in seen:
            seen.add(normalized)
            combined_parts.append(text)

    combined = '\n'.join(combined_parts)
    return _deduplicate_social_text(combined)


def _extract_social_narrative(bounded_section: str) -> str:
    """
    Extract social history from narrative format.

    NOW RECEIVES BOUNDED SECTION ONLY!
    """
    social_elements = []

    # Tobacco patterns
    tobacco_patterns = [
        r'(?:The patient has|Patient has)\s+never used\s+(?:other types of\s+)?tobacco',
        r'Tobacco\s*[:-]\s*(?:No|None)',
        r'(?:Former|Ex)\s+tobacco\s+user,?\s*quit\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
        r'(?:Never|Non[- ]?)smoker',
        r'Current\s+smoker,?\s*([^\n.]+)',
        r'Quit\s+(?:smoking|tobacco)\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
        r'Tob(?:acco)?:\s*([^\n]+)'
    ]

    for pattern in tobacco_patterns:
        match = re.search(pattern, bounded_section, re.IGNORECASE)
        if match:
            # ... extract tobacco ...
            break

    # Alcohol patterns - NOW WITH VALIDATION
    alcohol_patterns = [
        r'(?:An )?alcohol screening test \(AUDIT-C\) was\s+(\w+)\s*\(score[^\)]*\)',
        r'Alcohol Screen[:\s]*([^\n]+)',
        r'AUDIT-C[:\s]*([^\n]+)',
        r'ETOH\s*[:-]?\s*([^\n]+)',
        r'(?:Reports|States)\s+consuming\s+(?:approximately\s+)?([^.]+(?:glass|drink|beer|wine)[^.]*)',
        r'Alcohol\s*[:-]\s*([^\n]+)'
    ]

    for pattern in alcohol_patterns:
        match = re.search(pattern, bounded_section, re.IGNORECASE)
        if match:
            alcohol_text = match.group(1).strip()
            # NEW: Validate extracted text
            if _is_valid_social_value(alcohol_text, 'alcohol'):
                social_elements.append(f"Alcohol: {alcohol_text}")
                break

    # ... other patterns ...

    return '. '.join(social_elements) + '.' if social_elements else ""


def _is_valid_social_value(value: str, field_type: str) -> bool:
    """
    Validate extracted social history values.

    Rejects:
    - Garbage characters (lone semicolon)
    - Family member descriptions
    - Age markers with family descriptors
    """
    if not value or not value.strip():
        return False

    # Reject garbage characters
    if value.strip() in [';', ',', ':', '-.', '-']:
        return False

    # Reject values containing family member + age markers
    family_age_pattern = r'\b(yo|y\.?o\.?)\s+w/(?>Down|autism|mental|intellectual)'
    if re.search(family_age_pattern, value, re.IGNORECASE):
        return False

    # For all fields, reject if contains family member names at start
    family_names = ['sister', 'brother', 'father', 'mother', 'grandfather',
                   'grandmother', 'son', 'daughter', 'aunt', 'uncle', 'cousin']
    lower_value = value.lower()
    for name in family_names:
        if lower_value.startswith(name):
            return False

    # Field-specific validation
    if field_type == 'alcohol':
        # Additional alcohol validation
        if lower_value in ['none', 'no', 'denies', 'negative']:
            return False  # These are handled separately

    return True
```

**Approach 2: Add Semantic Validation**

```python
def _filter_healthcare_maintenance(text: str) -> str:
    """
    Filter out healthcare maintenance content and validate remaining text.
    """
    # Stop at healthcare maintenance markers
    healthcare_markers = [
        'Healthcare-', 'Healthcare:', 'Health maintenance:',
        'Living will', 'Advance directive',
        'Shingles-', 'Flu shot', 'Covid', 'Pvx 20', 'RSV vaccine',
        'HIV-declines', 'Hepatitis C', 'Colonoscopy',
        'Ultrasound', 'Sleep study', "Alzheimer's work-up",
        'Mammogram', 'Pap smear'
    ]

    lines = text.split('\n')
    filtered_lines = []

    for line in lines:
        # Check healthcare maintenance
        is_healthcare = any(marker.lower() in line.lower() for marker in healthcare_markers)
        if is_healthcare:
            break

        # Check for structural artifacts
        if line.strip() in ['Behavior - Cooperative', 'Psychological Social:']:
            continue

        # NEW: Check for family member contamination
        # If line contains age marker + family descriptor, skip it
        if re.search(r'\b(\d+)\s+(?:yo|y\.?o\.?)\s+w/(?>Down|autism)', line, re.IGNORECASE):
            continue

        if line.strip():
            filtered_lines.append(line)

    return '\n'.join(filtered_lines).strip()


def _deduplicate_social_text_improved(text: str) -> str:
    """
    Remove duplicate phrases and validate content.
    """
    if not text:
        return ""

    sentences = []
    for part in text.split('.'):
        part = part.strip()
        if part:
            # Validate sentence before adding
            if _is_valid_social_value(part, 'general'):
                sentences.append(part)

    # Remove exact duplicates
    seen = set()
    unique_sentences = []
    for sentence in sentences:
        normalized = ' '.join(sentence.lower().split())
        if normalized not in seen:
            seen.add(normalized)
            unique_sentences.append(sentence)

    return '. '.join(unique_sentences) + '.' if unique_sentences else ""
```

### Recommended Implementation

**Use Approach 1 + Approach 2** (Section boundaries + semantic validation):
1. Extract bounded "SOCIAL HISTORY:" section
2. Pass ONLY bounded section to `_extract_social_narrative()`
3. Keep PCP extraction on full document
4. Add `_is_valid_social_value()` function for semantic validation
5. Enhance `_filter_healthcare_maintenance()` with family member filtering
6. Deduplicate with improved logic

---

## Summary of Implementation Files

| Issue | Primary Files | Secondary Files | Priority |
|-------|---------------|-----------------|----------|
| Age Extraction | entity_extractor.py | consult_request_extractor.py | CRITICAL |
| PSA Curve | psa_extractor.py | - | CRITICAL |
| HPI Synthesis | hpi_agent.py | note_builder.py | HIGH |
| Social History | social_extractor.py | entity_extractor.py | HIGH |

---

**End of Specifications Document**
**Status**: Ready for Implementation
**Last Updated**: December 26, 2025
