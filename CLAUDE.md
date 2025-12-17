# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VA Urology Clinical Documentation Assistant (VAUCDA) is a Python-based web application that leverages large language models and retrieval-augmented generation (RAG) to transform unstructured clinical data into structured urology clinic notes. The system provides evidence-based clinical decision support through 44 specialized calculators spanning 10 urologic subspecialties.

**Current Status:** Design phase - comprehensive Program Design Document (PDD) and Software Design Document (SDD) exist, but implementation has not yet begun.

## Architecture

### High-Level System Design

VAUCDA follows a layered architecture:

1. **Presentation Layer:** React 18+ with Tailwind CSS 3.4+ (or HTMX alternative)
2. **Application Layer:** FastAPI backend with async request handling
3. **Clinical Module Layer:** 44 specialized calculators organized into 10 categories
4. **LLM Layer:** Multi-provider support (Ollama primary, Anthropic Claude, OpenAI GPT)
5. **Data Layer:** Neo4j (vector + knowledge graph), SQLite (settings), file storage

### LLM Integration Strategy

- **Primary:** Ollama (local deployment) for privacy/compliance
- **Secondary:** Anthropic Claude 3.5 Sonnet, OpenAI GPT-4o
- **RAG Pipeline:** LangChain orchestration with sentence-transformers embeddings
- **Vector Search:** Neo4j vector indices for semantic similarity

### Clinical Module Categories (44 Total)

| Category | Count | Examples |
|----------|-------|----------|
| Prostate Cancer | 7 | PSA Kinetics, PCPT 2.0, CAPRA Score, NCCN Risk |
| Kidney Cancer | 4 | RENAL Nephrometry, SSIGN Score, IMDC Criteria |
| Bladder Cancer | 3 | EORTC Recurrence/Progression Scores |
| Male Voiding | 5 | IPSS, BOOI/BCI, Uroflow Analysis |
| Female Urology | 5 | UDI-6/IIQ-7, OAB-q, POP-Q Staging |
| Reconstructive | 4 | Stricture Complexity, PFUI Classification |
| Male Fertility | 5 | Semen Analysis (WHO 2021), Varicocele Grading |
| Hypogonadism | 3 | Testosterone Evaluation, ADAM Questionnaire |
| Urolithiasis | 4 | STONE Score, 24-hr Urine Interpretation |
| Surgical Planning | 4 | CFS, RCRI, NSQIP Risk Calculator |

## Technology Stack

### Backend (Python 3.11+)
- **Web Framework:** FastAPI 0.109+
- **ASGI Server:** Uvicorn 0.27+
- **Task Queue:** Celery 5.3+ with Redis 7.2+
- **LLM Clients:** `ollama-python`, `anthropic`, `openai`
- **RAG:** LangChain 0.1+, `sentence-transformers`, `unstructured`, PyMuPDF

### Databases
- **Neo4j 5.x:** Vector storage + knowledge graph (requires APOC, GDS plugins)
- **SQLite:** User settings, session data, audit logs
- **File System:** Document storage, templates

### Frontend
- **Primary:** React 18+, Tailwind CSS 3.4+, Alpine.js
- **Alternative:** HTMX for server-driven UI
- **Accessibility:** WCAG 2.1 AA compliance required

## Development Standards (rules.txt)

### Code Quality Requirements

1. **Zero Tolerance Policy:**
   - No fallbacks, placeholders, simulations, mock code, demo code
   - No partially functioning or nonfunctional code
   - No emergency bypasses or crippled implementations
   - No frontend/backend connection errors
   - No missing or outdated API endpoints
   - No duplicate API endpoints

2. **Real Implementation Only:**
   - All UI elements generate real data from actual system operations
   - No hardcoded elements - use .env configuration
   - No example forms/reports
   - All configuration loaded from environment variables

3. **Chain of Thought (COT) Analysis Required:**
   - Problem identification and root cause analysis
   - Solution design and architecture review
   - Implementation planning and dependency mapping
   - Testing strategy and validation approach
   - Risk assessment and mitigation planning

4. **Tree of Thought (TOT) Evaluation Criteria:**
   - Reliability: Solution stability and error handling
   - Efficiency: Performance impact and resource usage
   - Completeness: Full implementation with all interdependent relationships
   - Scalability: Ability to handle growth and load
   - Compliance: Follow all rules regarding real implementations

### Success Criteria
- All errors resolved without exception
- All user-reported issues addressed
- All mock/dummy code replaced with real implementations
- Comprehensive testing with 100% functionality
- Performance targets met (note generation < 3s, calculators < 500ms)
- Security requirements fully implemented
- WCAG 2.1 AA accessibility standards achieved

## Clinical Documentation Template

The system uses a standardized urology clinic note template (see `urology_prompt.txt`):

- Chief Complaint (CC)
- History of Present Illness (HPI)
- IPSS scoring table
- Dietary/Social/Family/Sexual history
- Past Medical/Surgical history
- PSA Curve (reverse chronological)
- Pathology Results
- Medications/Allergies
- Lab results (Endocrine, General, Imaging)
- Review of Systems (ROS)
- Physical Examination
- Assessment (4-8 sentence narrative summary)
- Problem list
- Plan

**Key Requirements:**
- Use clinical data only from uploaded documents
- No truncations - provide complete information
- Full summarizations of all imaging and pathology
- PSA Curve format: `[r] MMM DD, YYYY HH:MM    PSA_VALUE` (append H if >4)
- Chain of thought reasoning for clinical decision-making

## Security & Compliance

### HIPAA Compliance
- **Zero-persistence PHI architecture:** No patient data stored permanently
- Session-based processing only
- Audit logging for all clinical data access
- VA network compatibility requirements

### Performance Targets
- Note generation: < 3 seconds (standard), < 10 seconds (complex)
- Calculator results: < 500ms
- System availability: 99.5% during VA business hours (6 AM - 10 PM local)
- Support for 500 concurrent users

## Future Extensibility

### Ambient Listening Extension (Planned)
The architecture includes provisions for future real-time audio capture:
- Provider-patient conversation transcription
- Real-time merging of conversational content with preliminary notes
- Comprehensive final documentation generation

## Key Documentation Files

- `VAUCDA_PDD.md`: Program Design Document (comprehensive requirements, stakeholders, roadmap)
- `VAUCDA_SDD.md`: Software Design Document (technical architecture, APIs, deployment)
- `docs/VAUCDA.md`: Detailed calculator algorithms and clinical logic
- `docs/VAUCDA Colors.md`: UI color scheme and branding
- `rules.txt`: Development standards and quality requirements
- `urology_prompt.txt`: Clinical note template and formatting rules

## Implementation Notes

When implementing VAUCDA:

1. **Start with core infrastructure:** FastAPI backend, Neo4j connection, SQLite setup
2. **Implement LLM abstraction layer:** Support multi-provider switching (Ollama, Anthropic, OpenAI)
3. **Build clinical calculators systematically:** One category at a time with 100% accuracy validation
4. **RAG pipeline:** Document ingestion → chunking → embedding → Neo4j vector storage → retrieval
5. **Frontend integration:** Progressive enhancement - start with basic forms, add real-time features
6. **Environment-driven config:** All settings via .env (LLM API keys, Neo4j credentials, etc.)

### Critical Architectural Decisions

- **Neo4j Knowledge Graph:** Stores clinical relationships, guidelines (AUA, NCCN, EAU), calculator documentation
- **Vector Embeddings:** Enable semantic search for evidence-based guidance retrieval
- **Stateless Note Generation:** Each request is independent; no patient data persists
- **Template System:** Configurable note templates for clinic notes, consults, pre-op, post-op
- **Module Orchestration:** Clinical calculators integrate automatically into generated notes

## Non-Functional Requirements

- **Accessibility:** All UI components must meet WCAG 2.1 AA standards
- **Scalability:** Design for 500 concurrent users across VA medical centers
- **Maintainability:** Modular architecture - calculators are independent, pluggable components
- **Testability:** 100% accuracy validation for all clinical calculators required
