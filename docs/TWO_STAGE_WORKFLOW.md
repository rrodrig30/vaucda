# Two-Stage Clinical Note Generation Workflow

## Overview

VAUCDA implements an **improved two-stage workflow** for clinical note generation that addresses a critical flaw in traditional single-stage approaches: **selecting calculators before seeing organized clinical data**.

### The Problem with Single-Stage Workflows

**Old Workflow (Backwards):**
```
User → Select Calculators (blindly) → Paste Clinical Data → Generate Note
Problem: How do you know which calculators are relevant before seeing the data?
Result: Missed calculators, inappropriate selections, cognitive burden
```

### The Solution: Two-Stage Workflow

**New Workflow (Clinically Sound):**
```
Stage 1: Clinical Data → Organize → Extract Entities → Suggest Calculators
         ↓
Stage 2: Review Note → Select Calculators → Provide Missing Inputs → Generate Final Note with A&P
```

---

## Architecture

### Stage 1: Preliminary Note Generation

**Purpose:** Organize clinical data and suggest relevant calculators

**Process:**
1. **Ambient Listening** (optional): Captures audio from clinical encounter
   - Real-time transcription using Whisper (medium.en model)
   - Immediate entity extraction from speech
   - HIPAA-compliant: audio deleted immediately after transcription

2. **Clinical Input**: Manual paste + ambient transcription combined

3. **LLM Processing**:
   - Organizes data into structured preliminary note
   - Includes: CC, HPI, PMH, Medications, Exam, Labs, Imaging
   - **EXCLUDES Assessment & Plan** (pending calculator analysis)

4. **Entity Extraction**:
   - **Regex-based extraction** (20+ patterns, 0.9 confidence)
     - PSA, Gleason scores, age, clinical stage, etc.
   - **LLM-based extraction** (catches complex patterns, 0.7 confidence)
   - Deduplication with confidence prioritization

5. **Calculator Suggestion**:
   - Evaluates 30+ calculators against extracted entities
   - **Confidence scoring**:
     - **High**: All required inputs detected → Auto-selected
     - **Medium**: 50%+ inputs detected → Suggested
     - **Low**: <50% inputs detected → Listed for reference
   - Identifies missing inputs for user to provide

**API Endpoint:**
```http
POST /api/v1/notes/generate-initial
Content-Type: application/json

{
  "clinical_input": "72 yo M with PSA 8.5, Gleason 3+4...",
  "note_type": "clinic_note",
  "llm_provider": "ollama",
  "llm_model": "llama3.1:8b",
  "temperature": 0.3
}
```

**Response:**
```json
{
  "preliminary_note": "CHIEF COMPLAINT: Elevated PSA\n\nHPI: 72-year-old male...",
  "extracted_entities": [
    {
      "field": "psa",
      "value": 8.5,
      "confidence": 0.9,
      "source_text": "PSA 8.5",
      "extraction_method": "regex"
    }
  ],
  "suggested_calculators": [
    {
      "calculator_id": "capra_score",
      "calculator_name": "CAPRA Score",
      "category": "prostate",
      "confidence": "high",
      "auto_selected": true,
      "reason": "All required inputs detected",
      "required_inputs": ["psa", "age", "gleason_primary", ...],
      "available_inputs": ["psa", "age", "gleason_primary", ...],
      "missing_inputs": [],
      "detected_entities": {"psa": 8.5, "age": 72}
    }
  ],
  "metadata": {
    "generation_time_seconds": 3.2,
    "entities_extracted": 6,
    "calculators_suggested": 2
  }
}
```

---

### Stage 2: Final Note Generation

**Purpose:** Generate comprehensive Assessment & Plan with calculator results and evidence

**Process:**
1. **Clinician Review**:
   - Reviews preliminary note for accuracy
   - Checks extracted entities
   - Modifies calculator selection if needed
   - Provides missing calculator inputs

2. **Calculator Execution**:
   - Runs selected calculators with extracted + user-provided inputs
   - Generates interpretations and recommendations
   - Validates input ranges and constraints

3. **RAG Evidence Retrieval** (if enabled):
   - Generates embedding from clinical input
   - Searches Neo4j vector index for relevant guidelines
   - Retrieves NCCN, AUA, EAU guidelines

4. **LLM Final Generation**:
   - Integrates preliminary note + calculator results + RAG evidence
   - Generates comprehensive **Assessment & Plan**:
     - Clinical reasoning and differential diagnosis
     - Calculator results with clinical interpretation
     - Evidence-based treatment recommendations
     - Shared decision-making documentation
     - Counseling time and discussion points
     - Follow-up plan

**API Endpoint:**
```http
POST /api/v1/notes/generate-final
Content-Type: application/json

{
  "preliminary_note": "CHIEF COMPLAINT: Elevated PSA...",
  "clinical_input": "72 yo M with PSA 8.5...",
  "selected_calculators": ["capra_score", "nccn_risk"],
  "additional_inputs": {
    "clinical_stage": "T1c",
    "family_history": false
  },
  "use_rag": true,
  "llm_provider": "ollama",
  "llm_model": "llama3.1:8b",
  "temperature": 0.3
}
```

**Response:**
```json
{
  "final_note": "CLINIC NOTE - Urology\n\n[Full note with A&P]...",
  "calculator_results": [
    {
      "calculator_id": "capra_score",
      "calculator_name": "CAPRA Score",
      "result": {"score": 4, "risk_level": "Intermediate"},
      "interpretation": "CAPRA Score 4/10: Intermediate risk",
      "recommendations": [
        "Consider radical prostatectomy or radiation",
        "Discuss active surveillance vs definitive treatment"
      ],
      "formatted_output": "CAPRA Score: 4/10 (Intermediate Risk)"
    }
  ],
  "rag_sources": [
    {
      "title": "NCCN Prostate Cancer Guidelines 2024",
      "source": "NCCN",
      "category": "prostate"
    }
  ],
  "metadata": {
    "generation_time_seconds": 8.4,
    "calculators_executed": 2,
    "rag_enabled": true,
    "rag_sources_count": 3
  }
}
```

---

## Components

### Backend

#### 1. **Entity Extractor** (`backend/app/services/entity_extractor.py`)

Hybrid approach for maximum accuracy:

```python
class ClinicalEntityExtractor:
    """Extract clinical entities from unstructured text."""

    ENTITY_PATTERNS = {
        'psa': [r'PSA\s*[:=]?\s*(\d+\.?\d*)'],
        'gleason_primary': [r'Gleason\s+(\d)\s*\+\s*\d'],
        'age': [r'(\d{1,3})\s*y\.?o\.?'],
        # ... 20+ more patterns
    }

    def extract_entities(self, clinical_text: str):
        # Regex extraction (high confidence)
        regex_entities = self._extract_with_regex(text)

        # LLM extraction (medium confidence, catches complex patterns)
        llm_entities = self._extract_with_llm(text, regex_entities)

        # Deduplicate (keep highest confidence)
        return self._deduplicate_entities(regex_entities + llm_entities)
```

**Supported Entities:**
- PSA (total, free, PHI)
- Gleason scores (primary, secondary, Grade Group)
- Age
- Clinical stage (TNM)
- Biopsy results (cores, percentage)
- Tumor characteristics (size, location, necrosis)
- Lab values (creatinine, calcium, hemoglobin)
- Symptom scores (IPSS, ICIQ)
- Prostate volume

#### 2. **Calculator Suggester** (`backend/app/services/calculator_suggester.py`)

Maps 30+ calculators to required inputs and evaluates applicability:

```python
class CalculatorSuggester:
    CALCULATOR_REQUIREMENTS = {
        'capra_score': {
            'category': 'prostate',
            'name': 'CAPRA Score',
            'required': ['psa', 'age', 'gleason_primary', 'gleason_secondary',
                        'clinical_stage', 'percent_positive_cores'],
            'description': 'Predicts recurrence-free survival after prostatectomy'
        },
        # ... 30+ more
    }

    def suggest_calculators(self, extracted_entities):
        for calc_id, requirements in self.CALCULATOR_REQUIREMENTS.items():
            available = [inp for inp in required if inp in entities]
            missing = [inp for inp in required if inp not in entities]

            if not missing:
                confidence = 'high'
                auto_selected = True
            elif len(available) >= 0.5 * len(required):
                confidence = 'medium'
                auto_selected = False
            else:
                confidence = 'low'
                auto_selected = False
```

**Supported Calculator Categories:**
- **Prostate Cancer**: CAPRA, PCPT, NCCN, PSA Kinetics, PHI, Free PSA Ratio
- **Kidney Cancer**: SSIGN, IMDC, RENAL Nephrometry, Leibovich
- **Bladder Cancer**: EORTC Recurrence/Progression, Cueto BCG
- **Voiding Dysfunction**: IPSS, ICIQ
- **Surgical Risk**: RCRI, Clavien-Dindo, Charlson Comorbidity Index

#### 3. **Ambient Listening WebSocket** (`backend/app/api/v1/ambient.py`)

Real-time audio transcription with entity extraction:

```python
@router.websocket("/stream")
async def ambient_listening_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time audio transcription."""

    await websocket.accept()
    model = get_whisper_model()  # Lazy-load Whisper medium.en

    while True:
        message = await websocket.receive_json()

        if message['type'] == 'audio':
            # Decode base64 audio
            audio_chunk = base64.b64decode(message['data'])

            # Transcribe with Whisper
            result = await transcribe_audio_chunk(model, audio_chunk)

            # Send transcription
            await websocket.send_json({
                "type": "transcription",
                "text": result['text'],
                "confidence": result['confidence']
            })

            # Extract entities
            entities = extractor.extract_entities(result['text'])
            await websocket.send_json({
                "type": "entities",
                "entities": entities
            })

            # HIPAA: Delete audio immediately
            del audio_chunk
```

**HIPAA Compliance:**
- Audio chunks processed in 2-second intervals
- Immediate deletion after transcription
- No persistence to disk or database
- All processing in-memory only
- TLS 1.3 encryption for WebSocket

---

### Frontend

#### 1. **AmbientListening Component** (`frontend/src/components/notes/AmbientListening.tsx`)

Audio capture with MediaRecorder API:

```typescript
const startRecording = async () => {
  // Request microphone access
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      sampleRate: 16000
    }
  })

  // Set up audio visualization
  const audioContext = new AudioContext({ sampleRate: 16000 })
  const analyser = audioContext.createAnalyser()

  // Connect WebSocket
  const ws = new WebSocket(`${wsURL}/api/v1/ambient/stream?token=${token}`)

  // Set up MediaRecorder
  const mediaRecorder = new MediaRecorder(stream, {
    mimeType: 'audio/webm',
    audioBitsPerSecond: 16000
  })

  mediaRecorder.ondataavailable = (event) => {
    // Convert to base64 and send
    const reader = new FileReader()
    reader.onloadend = () => {
      const base64Audio = (reader.result as string).split(',')[1]
      ws.send(JSON.stringify({
        type: 'audio',
        data: base64Audio
      }))
    }
    reader.readAsDataURL(event.data)
  }

  // Record in 2-second chunks
  mediaRecorder.start(2000)
}
```

**Features:**
- Real-time audio level visualization
- Transcription history display
- Extracted entities preview
- Start/stop controls
- Error handling and reconnection

#### 2. **CalculatorSuggestionPanel Component**

Displays suggested calculators with confidence indicators:

```typescript
<CalculatorSuggestionPanel
  suggestions={suggestedCalculators}
  extractedEntities={extractedEntities}
  selectedCalculators={selectedCalculators}
  onCalculatorToggle={handleCalculatorToggle}
  onAdditionalInputChange={handleAdditionalInputChange}
  additionalInputs={additionalInputs}
/>
```

**Features:**
- Confidence badges (high/medium/low)
- Auto-selection for high-confidence calculators
- Expandable details showing detected vs. missing inputs
- Input fields for missing data
- Category-based color coding
- Summary statistics

#### 3. **NoteGeneration Page** (Redesigned)

Complete two-stage workflow UI:

**Stage 1: Clinical Data Collection**
- Ambient listening component
- Clinical input textarea
- "Generate Preliminary Note" button

**Stage 2: Preliminary Note & Calculator Suggestions**
- Preliminary note display (markdown)
- Extracted entities grid
- Calculator suggestion panel with selection
- "Generate Final Note" button

**Stage 3: Final Note with A&P**
- Final note display (markdown)
- Calculator results cards
- RAG sources references
- Copy/Download/Save actions

---

## Clinical Workflow Example

### Case: 72-Year-Old Male with Elevated PSA

**Step 1: Clinical Encounter**

Clinician uses ambient listening during patient visit:

> "Seventy-two year old male presenting for elevated PSA. PSA is eight point five ng/mL, up from six point two one year ago. DRE shows firm right lobe. MRI demonstrates PI-RADS four lesion in right peripheral zone. Biopsy revealed Gleason three plus four equals seven adenocarcinoma. Four of twelve cores positive. Clinical stage T one C. Discussed treatment options including active surveillance, prostatectomy, and radiation. Patient prefers surgery. Counseled regarding surgical risks including incontinence and erectile dysfunction. Reviewed CAPRA score showing intermediate risk. Patient wishes to proceed with robotic-assisted laparoscopic prostatectomy."

**Ambient Listening Captures:**
- Real-time transcription appears
- Entities extracted in real-time:
  - Age: 72 (0.95 confidence)
  - PSA: 8.5 (0.95 confidence)
  - Gleason primary: 3 (0.90 confidence)
  - Gleason secondary: 4 (0.90 confidence)
  - Percent positive cores: 33.3% (0.85 confidence)
  - Clinical stage: T1c (0.90 confidence)

**Step 2: Generate Preliminary Note**

Clinician clicks "Generate Preliminary Note"

**LLM Output:**
```
CLINIC NOTE - Urology

CHIEF COMPLAINT: Elevated PSA

HISTORY OF PRESENT ILLNESS:
72-year-old male presents for discussion of elevated PSA. Current PSA 8.5 ng/mL,
increased from 6.2 ng/mL one year ago. DRE notable for firm right lobe.
Multiparametric MRI demonstrated PI-RADS 4 lesion in right peripheral zone.
Subsequent 12-core biopsy revealed Gleason 3+4=7 (Grade Group 2) adenocarcinoma
in 4 of 12 cores (33% positive).

PHYSICAL EXAMINATION:
DRE: Firm right lobe, no nodules

DIAGNOSTIC STUDIES:
- PSA: 8.5 ng/mL (prior 6.2 ng/mL)
- MRI: PI-RADS 4 lesion, right peripheral zone
- Biopsy: Gleason 3+4=7, 4/12 cores positive

CLINICAL STAGE: T1c

[Assessment & Plan pending calculator analysis and treatment discussion...]
```

**Calculator Suggestions:**
- **CAPRA Score** (HIGH confidence, auto-selected)
  - All inputs detected: PSA, age, Gleason, clinical stage, % cores
- **NCCN Risk Stratification** (HIGH confidence, auto-selected)
  - All inputs detected
- **PCPT Risk Calculator** (MEDIUM confidence)
  - Missing: DRE status, family history, prior biopsy
  - User can provide: DRE=abnormal, family_history=no, prior_biopsy=no

**Step 3: Review and Select**

Clinician reviews:
- ✓ Preliminary note accurate
- ✓ Entities correctly extracted
- ✓ CAPRA and NCCN auto-selected (appropriate)
- Adds PCPT with missing inputs
- Clicks "Generate Final Note"

**Step 4: Final Note Generated**

**LLM Output (with Calculator Results and Evidence):**
```
CLINIC NOTE - Urology
[Date/Time/Provider]

CHIEF COMPLAINT: Elevated PSA

HISTORY OF PRESENT ILLNESS:
72-year-old male presents for discussion of elevated PSA...
[Same as preliminary note]

ASSESSMENT & PLAN:

1. PROSTATE ADENOCARCINOMA, CLINICAL STAGE T1c

   Risk Stratification:
   - CAPRA Score: 4/10 (Intermediate Risk)
     - Components: PSA 8.5, age 72, Gleason 3+4, cT1c, 33% positive cores
     - 5-year biochemical recurrence-free probability: 75%

   - NCCN Risk Category: Favorable Intermediate Risk
     - Basis: Gleason 3+4, PSA 8.5, cT1c, <50% cores positive

   - PCPT Risk Calculator: 23% probability of prostate cancer on biopsy
     (Note: Already diagnosed; included for reference)

   Treatment Discussion:
   Discussed treatment options at length including active surveillance,
   radical prostatectomy, and radiation therapy (EBRT vs. brachytherapy).

   Per NCCN Guidelines for favorable intermediate risk prostate cancer,
   definitive treatment options include radical prostatectomy or radiation
   therapy with androgen deprivation therapy consideration.

   Patient preferences: Prefers definitive surgical management

   Shared Decision-Making:
   Counseled extensively regarding:
   - Surgical approach: Robotic-assisted laparoscopic prostatectomy
   - Oncologic outcomes: >95% cure rate at 10 years for favorable intermediate risk
   - Complications:
     * Urinary incontinence: 5-10% persistent, 80-90% continent at 1 year
     * Erectile dysfunction: 30-70% depending on nerve-sparing approach
     * Bleeding, infection (<2% each)
     * Need for blood transfusion (<5%)

   Patient demonstrates excellent understanding of risks, benefits, and
   alternatives. Questions answered. Patient wishes to proceed with surgery.

   Plan:
   - Schedule robotic-assisted laparoscopic prostatectomy
   - Preoperative clearance (cardiology if indicated)
   - Discuss nerve-sparing approach (bilateral vs. unilateral)
   - Order baseline erectile function assessment

   Counseling time: 35 minutes (>50% of 60-minute visit)

Evidence Sources Referenced:
- NCCN Clinical Practice Guidelines in Oncology: Prostate Cancer, Version 2.2024
- AUA/ASTRO/SUO Guideline: Clinically Localized Prostate Cancer (2022)

[Signature]
```

---

## Technical Details

### Entity Extraction Patterns

**Regex Patterns** (20+ fields):
```python
'psa': [
    r'PSA\s*[:=]?\s*(\d+\.?\d*)',
    r'prostate[-\s]specific antigen\s*[:=]?\s*(\d+\.?\d*)',
]
'gleason_primary': [
    r'Gleason\s+(\d)\s*\+\s*\d',
    r'Grade\s+Group\s+(\d)',
]
'clinical_stage': [
    r'[cC]linical\s+stage\s*[:=]?\s*([T][0-9][a-c]?)',
    r'\b([T][0-9][a-c])\b',
]
```

**LLM Prompt** (for complex extractions):
```
Extract structured clinical data from this text. Return ONLY a JSON object.

Clinical Text: {text}

Extract these fields if present:
- psa (ng/mL)
- age (years)
- gleason_primary (3-5)
- gleason_secondary (3-5)
- clinical_stage (T1, T1c, T2a, etc.)
- percent_positive_cores (percentage)
- tumor_size_cm

Return JSON format:
{
  "psa": 8.5,
  "age": 72,
  ...
}

If a value is not mentioned or unclear, do not include it.
Return ONLY the JSON object, no additional text.
```

### Calculator Suggestion Algorithm

```python
def _evaluate_calculator(calc_id, requirements, entity_dict):
    required_inputs = requirements['required']
    available = [inp for inp in required_inputs if inp in entity_dict]
    missing = [inp for inp in required_inputs if inp not in entity_dict]

    # Determine confidence
    if not missing:
        confidence = 'high'
        auto_selected = True
        reason = 'All required inputs detected'
    elif len(available) >= len(required_inputs) * 0.5:
        confidence = 'medium'
        auto_selected = False
        reason = f'Missing {len(missing)} required input(s)'
    else:
        confidence = 'low'
        auto_selected = False
        reason = f'Insufficient data detected'

    return {
        'calculator_id': calc_id,
        'confidence': confidence,
        'auto_selected': auto_selected,
        'missing_inputs': missing,
        'detected_entities': {k: entity_dict[k] for k in available}
    }
```

---

## HIPAA Compliance

### Audio Handling
- **Capture**: MediaRecorder API with 2-second chunks
- **Transmission**: Base64-encoded via TLS 1.3 WebSocket
- **Processing**: Whisper transcription in-memory
- **Deletion**: Immediate (`del audio_chunk`) after transcription
- **Storage**: NONE - audio never persists to disk

### PHI Protection
- **Session-only processing**: No notes stored in database
- **Local-first**: Draft notes saved to browser localStorage only
- **No logging of PHI**: Audit logs contain metadata only (timestamps, user IDs, no clinical content)
- **Encryption**: All communication via HTTPS/WSS (TLS 1.3)

### Compliance Checklist
- ✅ Minimum necessary PHI principle (entities extracted, raw data discarded)
- ✅ Access controls (JWT authentication required)
- ✅ Audit logging (metadata only)
- ✅ Encryption in transit (TLS 1.3)
- ✅ Encryption at rest (not applicable - no storage)
- ✅ Data retention policy (session-only, explicit deletion)
- ✅ BAA with Anthropic/OpenAI if using cloud LLMs
- ✅ Local-first option (Ollama) for zero cloud exposure

---

## Testing

### End-to-End Test Scenario

**Test Case**: Prostate Cancer Patient with Complete Data

1. **Start ambient listening**
   - Verify WebSocket connection established
   - Verify audio capture starts (visualizer shows levels)

2. **Speak clinical data**:
   > "Seventy-two year old male with PSA eight point five, Gleason three plus four, clinical stage T one C, four out of twelve cores positive"

3. **Verify real-time processing**:
   - Check transcription appears in history
   - Verify entities extracted (age=72, psa=8.5, etc.)
   - Check confidence scores

4. **Generate preliminary note**:
   - Click "Generate Preliminary Note"
   - Verify preliminary note contains organized data
   - Verify NO Assessment & Plan section
   - Check extracted entities displayed (6 entities)
   - Verify calculator suggestions appear

5. **Review calculator suggestions**:
   - Verify CAPRA Score: HIGH confidence, auto-selected
   - Verify NCCN Risk: HIGH confidence, auto-selected
   - Verify PCPT: MEDIUM confidence, not auto-selected
   - Check detected values shown for CAPRA
   - Check missing inputs identified for PCPT

6. **Provide missing inputs**:
   - Enter clinical_stage="T1c" for PCPT
   - Verify input fields work

7. **Generate final note**:
   - Click "Generate Final Note"
   - Verify final note includes full Assessment & Plan
   - Check calculator results displayed (2 cards)
   - Verify RAG sources shown (if Neo4j available)
   - Check metadata: time, calculator count, RAG sources

8. **Verify actions**:
   - Test Copy button
   - Test Download button
   - Test Save Draft button
   - Verify "Start New Note" clears state

---

## Performance Considerations

### Latency Breakdown (Typical Case)

**Stage 1: Preliminary Note**
- Entity extraction (regex): <100ms
- Entity extraction (LLM): 1-3s
- Calculator suggestion: <100ms
- Preliminary note generation (LLM): 3-10s
- **Total: ~5-15 seconds**

**Stage 2: Final Note**
- Calculator execution: 100-500ms per calculator
- RAG vector search (Neo4j): 200-800ms
- Final note generation (LLM): 5-15s
- **Total: ~8-20 seconds**

**Ambient Listening**
- Audio chunk (2s): Buffered
- Whisper transcription: 500-1500ms
- Entity extraction: <100ms
- **Real-time latency: <2 seconds**

### Optimization Strategies

1. **Use Ollama for local inference** (no API latency)
2. **Cache extracted entities** (avoid re-extraction)
3. **Parallel calculator execution** (ThreadPoolExecutor)
4. **Pre-warm Whisper model** (lazy-loaded on first use)
5. **Stream LLM responses** (use WebSocket for real-time chunks)

---

## Future Enhancements

### Planned Features

1. **Voice Commands**:
   - "Start recording"
   - "Generate note"
   - "Add calculator: CAPRA"

2. **Smart Entity Correction**:
   - Clinician can click to edit extracted entities
   - Re-suggestion of calculators based on corrections

3. **Template Customization**:
   - Custom preliminary note sections
   - Institution-specific formatting

4. **Collaborative Review**:
   - Share preliminary note with team
   - Real-time calculator selection collaboration

5. **Historical Data Integration**:
   - Auto-populate PSA kinetics from prior visits
   - Trend visualization

---

## Troubleshooting

### Ambient Listening Not Working

**Symptom**: "Failed to start recording" error

**Solutions**:
1. Check microphone permissions in browser
2. Verify HTTPS/WSS (required for MediaRecorder API)
3. Check Whisper model installed: `pip list | grep openai-whisper`
4. Verify WebSocket endpoint accessible: `ws://localhost:8000/api/v1/ambient/stream`
5. Check browser console for detailed errors

### Calculators Not Suggested

**Symptom**: "No Calculator Suggestions" message

**Solutions**:
1. Verify clinical data contains recognizable patterns
2. Check entity extraction results (expand entities section)
3. Ensure calculator requirements file up to date
4. Review entity extraction confidence scores
5. Try LLM-based extraction if regex failing

### Stage 2 Generation Fails

**Symptom**: "Error generating final note"

**Solutions**:
1. Check calculator inputs valid (ranges, types)
2. Verify Neo4j available if RAG enabled
3. Check LLM provider status
4. Review backend logs for detailed error
5. Try with RAG disabled to isolate issue

---

## References

- **NCCN Guidelines**: Clinical Practice Guidelines in Oncology
- **AUA Guidelines**: American Urological Association Clinical Guidelines
- **EAU Guidelines**: European Association of Urology Clinical Guidelines
- **Whisper Documentation**: https://github.com/openai/whisper
- **FastAPI WebSockets**: https://fastapi.tiangolo.com/advanced/websockets/
- **MediaRecorder API**: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder
