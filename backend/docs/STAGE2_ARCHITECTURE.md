# Stage 2 Architecture Documentation

## Overview

Stage 2 completes the clinical note AFTER the patient visit by adding Assessment and Plan sections. This architecture leverages specialized agents that integrate multiple data sources to generate comprehensive, clinically-accurate documentation.

## Two-Stage Workflow

### Stage 1: Preliminary Note (BEFORE Visit)
**Purpose:** Organize historical clinical data into a structured note format

**Generated Sections:**
- Chief Complaint (CC)
- History of Present Illness (HPI)
- IPSS scoring
- Dietary/Social/Family/Sexual history
- Past Medical History (PMH)
- Past Surgical History (PSH)
- PSA Curve
- Pathology results
- Testosterone levels
- Medications
- Allergies
- Lab results (Endocrine, Stone, General)
- Imaging reports
- Review of Systems (ROS) - Static template
- Physical Examination (PE) - Static template

**NOT Included in Stage 1:**
- Assessment (clinical impression)
- Plan (treatment plan)

**Why Static Templates for ROS/PE:**
ROS and PE findings can only be documented during the actual patient examination. Stage 1 provides static templates that the provider fills in during the visit.

### Stage 2: Complete Note (AFTER Visit)
**Purpose:** Generate Assessment and Plan using all available clinical context

**Added Sections:**
- Assessment (4-8 sentence narrative clinical impression)
- Plan (comprehensive treatment plan)

**Data Sources Integrated:**
1. **Stage 1 Preliminary Note** - Historical data organized from prior visits
2. **Prior Assessments/Plans** - Extracted from historical GU notes only
3. **Ambient Listening Transcript** - Real-time provider-patient conversation (optional)
4. **Calculator Results** - 44 specialized urologic calculators (optional)
5. **RAG Content** - Evidence-based guidelines from Neo4j knowledge graph (optional)

## Stage 2 Agent Architecture

### assessment_agent.py

**Purpose:** Synthesize comprehensive clinical assessment

**Inputs:**
- `stage1_note` (str): Complete preliminary note from Stage 1
- `prior_assessments` (List[str]): Assessment sections from prior GU notes
- `ambient_transcript` (Optional[str]): Provider-patient conversation
- `calculator_results` (Optional[dict]): Results from clinical calculators
- `rag_content` (Optional[str]): Evidence-based guidelines

**Output:**
- 4-8 sentence narrative assessment focusing on current urologic status

**Key Features:**
1. **Context Integration:** Combines all available data sources into comprehensive context
2. **Structured Synthesis:** Uses LLM with detailed instructions for clinical accuracy
3. **Meta-commentary Cleaning:** Removes LLM artifacts and VA metadata
4. **Defense in Depth:** Multiple layers of filtering for clean output

**Example Flow:**
```python
# Build comprehensive context
context_parts = []
context_parts.append(f"=== STAGE 1 NOTE ===\n{stage1_note}")
context_parts.append(f"=== AMBIENT TRANSCRIPT ===\n{ambient_transcript}")
context_parts.append(f"=== CALCULATOR RESULTS ===\n{calculator_summary}")
context_parts.append(f"=== EVIDENCE GUIDELINES ===\n{rag_content}")
context_parts.append(f"=== PRIOR ASSESSMENTS ===\n{prior_assessments}")

# Generate assessment using LLM
assessment = synthesize_with_llm(
    section_name="Assessment",
    section_instances=[full_context],
    instructions=comprehensive_instructions
)

# Clean output
assessment = clean_llm_commentary(assessment)
return assessment
```

### plan_agent.py

**Purpose:** Synthesize comprehensive treatment plan

**Inputs:** (same as assessment_agent)
- `stage1_note` (str)
- `prior_plans` (List[str])
- `ambient_transcript` (Optional[str])
- `calculator_results` (Optional[dict])
- `rag_content` (Optional[str])

**Output:**
- Comprehensive, actionable treatment plan organized by problem

**Key Features:**
1. **Calculator Integration:** Incorporates calculator-based recommendations
2. **Evidence-Based:** Integrates AUA/NCCN/EAU guidelines from RAG
3. **Patient Preferences:** Incorporates patient concerns from ambient transcript
4. **Actionable Format:** Clear interventions, medications, procedures, follow-up

**Plan Organization:**
- Active treatments and interventions
- Medication management (new, adjustments, discontinuations)
- Procedures or referrals
- Patient education and counseling
- Follow-up schedule and monitoring
- Specific action items with timeframes

## Stage 2 Orchestration (stage2_builder.py)

### extract_prior_assessments_and_plans()

**Purpose:** Extract Assessment and Plan sections from historical GU notes

**Input:** List of GU note dictionaries from `identify_notes()`

**Output:** Tuple of (prior_assessments, prior_plans) as lists of strings

**Process:**
1. Iterate through GU notes
2. Extract Assessment using `extract_assessment()`
3. Extract Plan using `extract_plan()`
4. Filter empty/whitespace results
5. Return clean lists

### build_stage2_note()

**Purpose:** Complete the clinical note by adding Assessment and Plan

**Parameters:**
```python
def build_stage2_note(
    stage1_note: str,              # Preliminary note from Stage 1
    gu_notes: List[Dict],          # GU note dictionaries for historical context
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None
) -> str:
```

**Process:**
1. Extract prior assessments/plans from GU notes
2. Call `synthesize_assessment()` with all inputs
3. Call `synthesize_plan()` with all inputs
4. Assemble complete note: Stage 1 + Assessment + Plan
5. Return complete clinical note

**Output Format:**
```
[Stage 1 Preliminary Note]

=============================================================================
ASSESSMENT:
[Synthesized clinical impression]

=============================================================================
PLAN:
[Synthesized treatment plan]
```

## API Integration

### POST /api/v1/notes/generate-stage2-agent

**Purpose:** Execute Stage 2 using agent-based architecture

**Request Schema:** `FinalNoteRequest`
```json
{
  "preliminary_note": "...",      // Stage 1 note
  "clinical_input": "...",         // Original clinical data
  "selected_calculators": [...],   // Calculator IDs to run
  "additional_inputs": {...},      // Manual calculator inputs
  "use_rag": true,
  "llm_provider": "ollama",
  "llm_model": "llama3.1:8b",
  "temperature": 0.3
}
```

**Response Schema:** `FinalNoteResponse`
```json
{
  "final_note": "...",             // Complete note with A&P
  "calculator_results": [...],      // Executed calculator results
  "rag_sources": [...],            // Evidence citations
  "metadata": {
    "generation_time_seconds": 8.4,
    "calculators_executed": 2,
    "rag_enabled": true,
    "rag_sources_count": 5,
    "gu_notes_found": 3,
    "workflow": "stage2_agent_based"
  }
}
```

**Endpoint Flow:**
1. Identify GU notes from clinical input
2. Extract entities for calculator execution
3. Execute selected calculators
4. Retrieve RAG content (if enabled)
5. Call `build_stage2_note()` with all inputs
6. Return complete note with metadata

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         STAGE 1                                 │
│  (Preliminary Note - BEFORE Visit)                              │
│                                                                 │
│  Input: Historical clinical documents                          │
│  Output: Organized note WITHOUT Assessment/Plan                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PATIENT VISIT                                │
│  Provider fills in ROS/PE templates during examination         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         STAGE 2                                 │
│  (Complete Note - AFTER Visit)                                  │
│                                                                 │
│  Inputs:                                                        │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ 1. Stage 1 Preliminary Note                          │      │
│  │ 2. Prior Assessments/Plans (from GU notes)          │      │
│  │ 3. Ambient Transcript (optional)                     │      │
│  │ 4. Calculator Results (optional)                     │      │
│  │ 5. RAG Content (optional)                            │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │      extract_prior_assessments_and_plans()           │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                  │
│              ┌───────────────┴───────────────┐                 │
│              ▼                               ▼                 │
│  ┌─────────────────────┐       ┌─────────────────────┐        │
│  │ assessment_agent    │       │    plan_agent       │        │
│  │ synthesize_assessment│       │ synthesize_plan     │        │
│  └─────────────────────┘       └─────────────────────┘        │
│              │                               │                 │
│              └───────────────┬───────────────┘                 │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │       assemble_complete_note()                       │      │
│  │  Stage 1 + Assessment + Plan                         │      │
│  └──────────────────────────────────────────────────────┘      │
│                              │                                  │
│                              ▼                                  │
│  Output: Complete clinical note ready for documentation        │
└─────────────────────────────────────────────────────────────────┘
```

## Clean API Separation

**Critical Design Decision:** Stage 2 agents have a CLEAN API surface that prevents data leakage:

### What Stage 2 Agents RECEIVE:
✅ Stage 1 preliminary note (complete)
✅ Prior assessments/plans (extracted lists)
✅ Ambient transcript (if available)
✅ Calculator results (if available)
✅ RAG content (if available)

### What Stage 2 Agents DO NOT RECEIVE:
❌ Full `gu_notes` dictionary
❌ Full `non_gu_notes` dictionary
❌ Raw extraction data from Stage 1

**Rationale:**
- Non-GU notes were already used to create the Stage 1 note
- Stage 2 agents work with the SYNTHESIZED Stage 1 output, not raw data
- This prevents duplication and ensures clean separation of concerns
- Prior assessments/plans come from GU notes ONLY (urologic context)

## Testing

### Unit Tests
**File:** `tests/test_stage2_integration.py`

**Test: Agent Isolation**
- Verifies assessment_agent works independently
- Verifies plan_agent works independently
- Tests with minimal inputs (no calculators, no RAG)

**Test: Full Integration**
- Stage 1 generation
- Stage 2 generation with simulated inputs
- Output file validation
- End-to-end pipeline verification

**Run Tests:**
```bash
cd /home/gulab/PythonProjects/VAUCDA/backend
python tests/test_stage2_integration.py
```

### Manual Testing via API

**Step 1: Generate Stage 1 Note**
```bash
curl -X POST http://localhost:8000/api/v1/notes/generate-initial \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clinical_input": "[VA clinical document]",
    "note_type": "clinic_note",
    "llm_provider": "ollama",
    "use_rag": true
  }'
```

**Step 2: Generate Stage 2 Complete Note**
```bash
curl -X POST http://localhost:8000/api/v1/notes/generate-stage2-agent \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "preliminary_note": "[Stage 1 output]",
    "clinical_input": "[Original VA document]",
    "selected_calculators": ["pcpt_risk", "capra_score"],
    "additional_inputs": {"clinical_stage": "T1c"},
    "use_rag": true,
    "llm_provider": "ollama",
    "temperature": 0.3
  }'
```

## Future Enhancements

### Ambient Listening Integration
**Status:** Architecture ready, implementation pending

**Future Flow:**
1. Real-time audio capture during patient visit
2. Speech-to-text transcription
3. Pass transcript to Stage 2 agents
4. Integrate conversational content with structured data

**API Schema Update Needed:**
Add `ambient_transcript` field to `FinalNoteRequest`:
```python
class FinalNoteRequest(BaseModel):
    # ... existing fields ...
    ambient_transcript: Optional[str] = Field(
        default=None,
        description="Real-time conversation transcript from ambient listening"
    )
```

### Calculator Auto-Suggestion
**Current:** Manual calculator selection
**Future:** AI-powered calculator suggestion based on clinical entities

### RAG Enhancement
**Current:** Graph-based RAG for Assessment & Plan
**Future:**
- Multi-modal RAG (text + images)
- Temporal RAG (time-aware guideline retrieval)
- Personalized RAG (patient-specific evidence)

## Performance Targets

Based on VAUCDA requirements:

| Metric | Target | Notes |
|--------|--------|-------|
| Stage 1 Generation | < 3 seconds | Standard cases |
| Stage 2 Generation | < 10 seconds | Complex cases with calculators + RAG |
| Calculator Execution | < 500ms each | Per calculator |
| RAG Retrieval | < 2 seconds | Graph search with 5 sources |
| Total Workflow | < 15 seconds | Stage 1 + Stage 2 + calculators + RAG |

## Security & Compliance

### HIPAA Compliance
- **Zero-persistence architecture:** No patient data stored permanently
- **Session-based processing:** All data ephemeral
- **Audit logging:** All API calls logged (no PHI in logs)
- **VA network compatible:** Supports VA firewall/security requirements

### Data Flow Security
- Stage 1 data: In-memory only, cleared after Stage 1 completion
- Stage 2 data: In-memory only, cleared after note generation
- Calculators: Stateless, no data retention
- RAG: Knowledge graph only (no PHI)
- LLM: All inference local (Ollama) or via HIPAA-compliant APIs (Anthropic/OpenAI BAA)

## Troubleshooting

### Issue: Assessment/Plan sections are empty

**Causes:**
1. No prior GU notes identified → No prior assessments/plans to synthesize
2. All inputs optional (ambient, calculators, RAG) → May have minimal context

**Solutions:**
- Verify input is properly formatted VA clinical document
- Check `identify_notes()` is finding GU notes
- Provide calculator results and RAG content for richer synthesis

### Issue: LLM meta-commentary in output

**Causes:**
- LLM adding preambles like "Based on the information provided..."
- VA metadata not fully filtered

**Solutions:**
- Already addressed via `clean_llm_commentary()` in `history_cleaners.py`
- Defense in depth: Filtering at extractor AND agent levels
- Verify filters are being applied in synthesis agents

### Issue: Duplicate information between Stage 1 and Assessment

**Causes:**
- Assessment agent repeating information from Stage 1 note

**Solutions:**
- LLM instructions emphasize SYNTHESIS not REPETITION
- Assessment should be NEW clinical impression, not restating HPI
- Temperature 0.2 reduces randomness and encourages concise output

## File Structure

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── notes.py                    # API endpoints (includes /generate-stage2-agent)
│   ├── services/
│   │   └── note_processing/
│   │       ├── stage2_builder.py           # Stage 2 orchestration
│   │       ├── note_builder.py             # Stage 1 orchestration
│   │       ├── note_identifier.py          # GU vs non-GU note identification
│   │       └── agents/
│   │           ├── assessment_agent.py     # Assessment synthesis
│   │           ├── plan_agent.py           # Plan synthesis
│   │           └── history_cleaners.py     # Meta-commentary removal
│   └── schemas/
│       └── notes.py                        # Pydantic schemas
├── tests/
│   └── test_stage2_integration.py          # Integration tests
└── docs/
    └── STAGE2_ARCHITECTURE.md              # This file
```

## Summary

Stage 2 represents a significant architectural enhancement that enables:

1. **Complete Clinical Documentation:** Assessment and Plan generated post-visit
2. **Multi-Source Integration:** Combines 5 different data sources intelligently
3. **Specialized Agents:** assessment_agent and plan_agent with focused responsibilities
4. **Clean API Surface:** Clear separation between Stage 1 and Stage 2
5. **Extensibility:** Ready for ambient listening, advanced RAG, and more calculators
6. **Clinical Accuracy:** Temperature 0.2, evidence-based synthesis, comprehensive context

The agent-based architecture provides superior integration of clinical data sources compared to simple LLM prompting, resulting in more accurate, context-aware, and clinically relevant Assessment and Plan sections.
