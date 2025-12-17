# VA Urology Clinical Documentation Assistant (VAUCDA)
# Program Design Document

**Version:** 1.0  
**Date:** November 28, 2025  
**Status:** Draft  
**Document Type:** Program Design Document (PDD)  
**Classification:** Internal Technical Documentation

---

## Document Control

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | 2025-11-28 | VAUCDA Development Team | Initial program design document |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Program Overview](#2-program-overview)
3. [Stakeholder Analysis](#3-stakeholder-analysis)
4. [Functional Requirements](#4-functional-requirements)
5. [System Architecture](#5-system-architecture)
6. [Technology Platform](#6-technology-platform)
7. [Data Architecture](#7-data-architecture)
8. [LLM Integration Design](#8-llm-integration-design)
9. [Clinical Module Framework](#9-clinical-module-framework)
10. [Ambient Listening Extension](#10-ambient-listening-extension)
11. [User Interface Design](#11-user-interface-design)
12. [API Specification](#12-api-specification)
13. [Security Framework](#13-security-framework)
14. [Deployment Strategy](#14-deployment-strategy)
15. [Testing Strategy](#15-testing-strategy)
16. [Implementation Roadmap](#16-implementation-roadmap)
17. [Risk Assessment](#17-risk-assessment)
18. [Appendices](#appendices)

---

## 1. Introduction

### 1.1 Purpose

This Program Design Document (PDD) defines the comprehensive technical and programmatic specifications for the VA Urology Clinical Documentation Assistant (VAUCDA). The document serves as the authoritative reference for all development, integration, and deployment activities, providing detailed guidance for implementing a clinical documentation system that leverages large language models (LLMs) and retrieval-augmented generation (RAG) to transform unstructured clinical data into structured urology notes.

### 1.2 Scope

This document encompasses the complete program design including architecture, technology stack, data models, security framework, deployment specifications, and extensibility requirements. Notably, this design incorporates provisions for future ambient listening capabilities that will enable real-time capture and integration of provider-patient interactions into clinical documentation.

### 1.3 Intended Audience

This document is intended for software architects and engineers responsible for system implementation, clinical informaticists advising on workflow integration, security officers validating compliance requirements, project managers coordinating development activities, and VA technical leadership approving system deployment.

### 1.4 Document Conventions

Throughout this document, technical specifications are presented using standard notation for APIs (OpenAPI/YAML), database schemas (Cypher for Neo4j, SQL for SQLite), and code examples (Python, TypeScript). Architecture diagrams use ASCII representations for maximum compatibility.

### 1.5 References

This document references the VAUCDA Software Design Document v1.0 (November 2025), VA Technical Reference Model (TRM) standards, HIPAA Security Rule (45 CFR Part 164), NIST Cybersecurity Framework, and AUA/NCCN Clinical Guidelines for Urology.

---

## 2. Program Overview

### 2.1 Vision Statement

VAUCDA aims to become the standard clinical documentation platform for VA urology services, reducing documentation burden by 60% while improving note quality and consistency. The system will evolve to incorporate ambient listening capabilities, creating a seamless documentation experience where provider-patient conversations flow naturally into structured clinical notes.

### 2.2 Mission Statement

To provide VA urologists with an intelligent documentation assistant that transforms unstructured clinical data into high-quality, standardized notes while offering evidence-based clinical decision support through integrated calculators and RAG-powered knowledge retrieval.

### 2.3 Program Objectives

The primary objectives include delivering a functional note generation platform for urology clinic and consult documentation, integrating 44 specialized clinical calculators spanning 10 urologic subspecialties, implementing a RAG pipeline for evidence-based clinical guidance, establishing a zero-persistence PHI architecture ensuring HIPAA compliance, and designing an extensible framework for ambient listening integration.

### 2.4 Key Capabilities

#### 2.4.1 Core Documentation Functions

The note generation module accepts unstructured clinical data including lab results, imaging reports, prior notes, and patient history from VA clinical systems. The LLM processes this content and produces structured notes following urology-specific templates with consistent organization covering chief complaint, history of present illness, relevant urologic history, medications, genitourinary examination findings, diagnostic results, assessment, and plan.

#### 2.4.2 Clinical Decision Support

The system provides 44 specialized calculators organized across 10 clinical categories:

| Category | Modules | Representative Tools |
|----------|---------|---------------------|
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

#### 2.4.3 Evidence-Based Guidance

The RAG pipeline provides context-aware retrieval from AUA Guidelines, NCCN Clinical Practice Guidelines, EAU Guidelines, and peer-reviewed urologic literature stored in the Neo4j knowledge graph.

#### 2.4.4 Ambient Listening Extension (Planned)

Future capability to capture provider-patient audio interactions, transcribe in real-time, and merge conversational content with preliminary notes to produce comprehensive final documentation.

### 2.5 Success Metrics

Success will be measured by documentation time reduction of 50% or greater, note completion rate improvement to 95% same-day completion, user satisfaction scores of 4.0 or higher on a 5-point scale, system availability of 99.5% during operational hours, and response latency under 3 seconds for note generation.

---

## 3. Stakeholder Analysis

### 3.1 Primary Stakeholders

#### 3.1.1 VA Urologists (End Users)

These users are attending physicians, residents, and fellows in urology who require efficient documentation tools that integrate with clinical workflows, clinical decision support for complex cases, and evidence-based guidance accessible during patient encounters.

#### 3.1.2 VA Patients (Beneficiaries)

Veterans receiving urologic care benefit through improved documentation accuracy, reduced provider time spent on documentation (increasing face-time), and consistent application of evidence-based guidelines.

#### 3.1.3 VA Health Informatics

Technical stakeholders responsible for system integration and compliance have requirements for HIPAA-compliant architecture, integration with VA infrastructure, and audit capabilities.

#### 3.1.4 VA Leadership

Administrative stakeholders require operational efficiency improvements, cost-effectiveness metrics, and scalability to additional specialties.

### 3.2 Stakeholder Requirements Matrix

| Stakeholder | Primary Need | Key Requirement | Success Indicator |
|-------------|--------------|-----------------|-------------------|
| Urologists | Efficiency | Fast note generation | < 3 second response |
| Urologists | Accuracy | Reliable clinical calculators | 100% calculation accuracy |
| VA IT | Security | Zero PHI persistence | Clean audit reports |
| VA IT | Integration | VA network compatibility | Successful deployment |
| Patients | Quality | Accurate documentation | Reduced errors |
| Leadership | ROI | Measurable improvements | Productivity metrics |

---

## 4. Functional Requirements

### 4.1 Note Generation Requirements

#### FR-NG-001: Clinical Input Processing

The system shall accept unstructured clinical text up to 50,000 characters including laboratory results, imaging reports, prior clinical notes, and medication lists. Input shall be processed within 3 seconds for standard complexity cases and 10 seconds for complex multi-system cases.

#### FR-NG-002: Template-Based Output

The system shall generate notes conforming to configurable templates for urology clinic notes, urology consults, preoperative assessments, and postoperative notes. Each template shall include standard sections appropriate to note type with customizable section ordering and content depth.

#### FR-NG-003: LLM Provider Selection

Users shall be able to select from available LLM providers including Ollama (primary/local), Anthropic Claude, and OpenAI GPT models. The system shall support model switching without session interruption.

#### FR-NG-004: Module Integration

Generated notes shall automatically incorporate results from selected clinical calculators, displaying calculator outputs in a dedicated appendix section with proper formatting and citations.

### 4.2 Clinical Calculator Requirements

#### FR-CC-001: Calculator Accuracy

All calculators shall implement peer-reviewed algorithms with 100% mathematical accuracy. Each calculator shall include reference citations and version tracking.

#### FR-CC-002: Input Validation

Calculator inputs shall be validated against defined ranges with clear error messaging. Missing required inputs shall prevent calculation with guidance on required values.

#### FR-CC-003: Result Interpretation

Calculator results shall include numerical scores, risk category assignments, interpretive text, and evidence-based recommendations where applicable.

#### FR-CC-004: LLM-Assisted Input Extraction

The system shall offer optional LLM-assisted extraction of calculator inputs from clinical text, with user confirmation before calculation.

### 4.3 Evidence Search Requirements

#### FR-ES-001: RAG-Powered Search

The system shall provide semantic search across the clinical knowledge base using vector similarity in Neo4j. Search shall return relevant guideline excerpts, reference materials, and calculator documentation.

#### FR-ES-002: Source Attribution

All retrieved content shall include source attribution with document title, publication date, and direct links where available.

#### FR-ES-003: Category Filtering

Users shall be able to filter evidence searches by clinical category, guideline source, and publication date range.

### 4.4 Ambient Listening Requirements (Future Phase)

#### FR-AL-001: Audio Capture

The system shall capture provider-patient audio through approved recording devices with explicit consent mechanisms. Audio capture shall comply with all applicable recording consent laws.

#### FR-AL-002: Real-Time Transcription

Captured audio shall be transcribed in real-time with speaker diarization distinguishing provider and patient speech. Transcription latency shall not exceed 2 seconds from speech to text.

#### FR-AL-003: Note Integration

Transcribed content shall be intelligently merged with preliminary notes generated from structured clinical data. The system shall identify and appropriately position conversational content within note sections.

#### FR-AL-004: Review and Edit

Users shall have the ability to review, edit, and approve ambient-captured content before finalizing notes. The system shall highlight ambient-sourced content for easy identification.

### 4.5 Non-Functional Requirements

#### NFR-001: Performance

Response time shall be under 3 seconds for note generation, calculator results shall render within 500ms, and the system shall support 500 concurrent users.

#### NFR-002: Availability

System uptime shall be 99.5% during VA business hours (6 AM - 10 PM local time) with planned maintenance windows communicated 72 hours in advance.

#### NFR-003: Accessibility

The interface shall comply with WCAG 2.1 AA standards for all clinical interface elements, ensuring accessibility for users with disabilities.

#### NFR-004: Scalability

Architecture shall support horizontal scaling to accommodate growth across VA medical centers without degradation of performance metrics.

---

## 5. System Architecture

### 5.1 Architectural Principles

The system follows a layered architecture with clear separation of concerns. The presentation layer handles all user interactions through a responsive web interface. The application layer contains business logic for note generation, calculator orchestration, and RAG pipeline management. The LLM layer abstracts multiple AI providers behind a unified interface. The data layer manages persistent storage for configuration, knowledge graphs, and user preferences while ensuring zero persistence of PHI.

### 5.2 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    Web Interface (HTML/CSS/JS)                        │  │
│  │              React 18+ / Tailwind CSS / Alpine.js / HTMX              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              APPLICATION LAYER                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  FastAPI        │  │  Note           │  │  Clinical Module Engine   │   │
│  │  Backend        │  │  Generator      │  │  (44 Calculators)         │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Template       │  │  Settings       │  │  Document Processor       │   │
│  │  Manager        │  │  Manager        │  │  (PDF/DOCX Ingestion)     │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               Ambient Listening Service (Future Phase)               │   │
│  │         Audio Capture → Transcription → Note Integration             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           CLINICAL MODULE LAYER                             │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│  │  Prostate     │ │   Kidney      │ │   Bladder     │ │    Male       │   │
│  │  Cancer (7)   │ │   Cancer (4)  │ │   Cancer (3)  │ │   Voiding (5) │   │
│  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘   │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│  │   Female      │ │  Reconstr.    │ │    Male       │ │   Stones      │   │
│  │   Urology (5) │ │   Urology (4) │ │  Fertility(5) │ │         (4)   │   │
│  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘   │
│  ┌───────────────┐ ┌───────────────┐                                       │
│  │ Hypogonadism  │ │  Surgical     │                                       │
│  │         (3)   │ │  Planning (4) │                                       │
│  └───────────────┘ └───────────────┘                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                 LLM LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Ollama         │  │  Anthropic      │  │  OpenAI                   │   │
│  │  Client         │  │  Client         │  │  Client                   │   │
│  │  (Primary)      │  │  (Optional)     │  │  (Optional)               │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    RAG Pipeline (LangChain)                           │  │
│  │         Vector Search → Context Assembly → Augmented Generation       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                 DATA LAYER                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Neo4j 5.x      │  │  SQLite         │  │  File Storage             │   │
│  │  Vector + KG    │  │  Settings DB    │  │  (Documents, Templates)   │   │
│  │  (768-dim)      │  │                 │  │                           │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Component Interaction Flow

The standard note generation workflow proceeds as follows: The user enters clinical data in the web interface, which is transmitted via TLS 1.3 to the FastAPI backend. The Note Generator orchestrates processing, first retrieving relevant clinical guidance via the RAG Pipeline. The RAG Pipeline queries Neo4j for semantically similar documents using vector search. Context-augmented prompts are sent to the selected LLM (Ollama by default). If clinical modules are selected, the Calculator Engine processes inputs and generates appendix content. The completed note with appendices is returned to the user interface. Throughout this process, all clinical data remains in memory only and is securely deleted upon response delivery.

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌─────────────┐
│  User    │───▶│ FastAPI  │───▶│ Note         │───▶│ LLM Layer   │
│ Interface│    │ Backend  │    │ Generator    │    │ (Ollama)    │
└──────────┘    └──────────┘    └──────────────┘    └─────────────┘
                     │                 │                   │
                     │                 ▼                   │
                     │         ┌──────────────┐           │
                     │         │ RAG Pipeline │◀──────────┘
                     │         │ (LangChain)  │
                     │         └──────────────┘
                     │                 │
                     ▼                 ▼
              ┌──────────┐    ┌─────────────┐
              │ Clinical │    │ Neo4j       │
              │ Modules  │    │ Vector DB   │
              └──────────┘    └─────────────┘
```

### 5.4 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTAINER ORCHESTRATION                             │
│                            (Docker Compose)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ vaucda-api  │  │ vaucda-     │  │   neo4j     │  │   ollama    │        │
│  │   :8000     │  │ frontend    │  │ :7474/:7687 │  │   :11434    │        │
│  │             │  │   :3000     │  │             │  │   (GPU)     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐         │
│  │   redis     │  │   celery    │  │   ambient-listener          │         │
│  │   :6379     │  │   worker    │  │   (Future Phase)            │         │
│  │             │  │             │  │   Audio Processing Service   │         │
│  └─────────────┘  └─────────────┘  └─────────────────────────────┘         │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                          PERSISTENT VOLUMES                                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                    │
│  │ neo4j_data    │  │ ollama_models │  │ redis_data    │                    │
│  │ neo4j_logs    │  │               │  │               │                    │
│  └───────────────┘  └───────────────┘  └───────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Technology Platform

### 6.1 Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Web Framework | FastAPI | 0.109+ | Async REST API, WebSocket support |
| Python Runtime | Python | 3.11+ | Core application logic |
| Task Queue | Celery | 5.3+ | Background processing for LLM calls |
| Message Broker | Redis | 7.2+ | Task queue backend, caching |
| ASGI Server | Uvicorn | 0.27+ | Production async server |

### 6.2 LLM Integration Stack

| Provider | Integration Method | Supported Models | Primary Use Case |
|----------|-------------------|------------------|------------------|
| Ollama (Primary) | REST API via `ollama-python` | Llama 3.1 (8B/70B), Mistral 7B, Phi-3, CodeLlama | All clinical tasks |
| Anthropic | `anthropic` SDK | Claude 3.5 Sonnet, Claude 3 Opus | Complex reasoning (optional) |
| OpenAI | `openai` SDK | GPT-4o, GPT-4 Turbo | Fallback/comparison (optional) |

### 6.3 Database Technologies

| Database | Purpose | Configuration |
|----------|---------|---------------|
| Neo4j 5.x | Vector storage, knowledge graph, clinical relationships | APOC, GDS plugins enabled |
| SQLite | User settings, session metadata, audit logs | Local file-based, no PHI |
| File System | Document storage, templates, exports | Structured directory hierarchy |

### 6.4 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18+ | Component-based UI framework |
| Tailwind CSS | 3.4+ | Utility-first styling |
| Alpine.js | 3.x | Lightweight interactivity |
| HTMX | 1.9+ | Server-driven UI updates (alternative) |

### 6.5 RAG Pipeline Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangChain 0.1+ | RAG pipeline construction |
| Embeddings | sentence-transformers | Document vectorization (768-dim) |
| Vector Search | Neo4j Vector Index | Cosine similarity search |
| Document Processing | unstructured, PyMuPDF | PDF/DOCX parsing |

### 6.6 Ambient Listening Stack (Future Phase)

| Component | Technology | Purpose |
|-----------|------------|---------|
| Audio Capture | WebRTC / Native APIs | Browser/device audio streaming |
| Speech Recognition | Whisper (OpenAI) / Azure Speech | Real-time transcription |
| Speaker Diarization | pyannote-audio | Provider/patient identification |
| Audio Processing | librosa, soundfile | Audio preprocessing |
| Streaming | WebSocket | Real-time audio transmission |

---

## 7. Data Architecture

### 7.1 Neo4j Graph Schema

#### 7.1.1 Node Types

The knowledge graph contains five primary node types:

**Document nodes** store clinical knowledge resources with properties including id (STRING), title (STRING), source (STRING), content (STRING), embedding (LIST of FLOAT with 768 dimensions), created_at (DATETIME), and document_type (STRING: guideline, reference, or calculator).

**ClinicalConcept nodes** represent medical concepts with id (STRING), name (STRING), category (STRING for subspecialty), description (STRING), icd10_codes (LIST of STRING), and snomed_codes (LIST of STRING).

**Calculator nodes** define clinical calculators with id (STRING), name (STRING), category (STRING), formula (STRING), inputs (LIST of STRING), interpretation (STRING), and references (LIST of STRING).

**Template nodes** store note templates with id (STRING), name (STRING), type (STRING: clinic_note, consult, preop, or postop), content (STRING), sections (LIST of STRING), and active (BOOLEAN).

**User nodes** contain user information with id (STRING), username (STRING), preferences (MAP), and created_at (DATETIME).

#### 7.1.2 Relationship Types

The graph includes knowledge relationships where Documents REFERENCE ClinicalConcepts, Documents CITE other Documents, ClinicalConcepts are RELATED_TO other ClinicalConcepts, Calculators APPLY_TO ClinicalConcepts, and Calculators are DERIVED_FROM Documents. User relationships include Users PREFER Templates, Users USE Calculators, Sessions BELONG_TO Users, and Sessions GENERATE Notes.

#### 7.1.3 Vector Index Configuration

```cypher
// Document embeddings index
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

// Clinical concept embeddings index
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

// Full-text search indexes
CREATE FULLTEXT INDEX document_content IF NOT EXISTS
FOR (d:Document) ON EACH [d.content, d.title];

CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];
```

### 7.2 SQLite Schema (Settings Database)

```sql
-- User Preferences Table
CREATE TABLE user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    default_llm TEXT DEFAULT 'ollama',
    default_model TEXT DEFAULT 'llama3.1:8b',
    default_template TEXT DEFAULT 'urology_clinic',
    module_defaults JSON,
    display_preferences JSON,
    ambient_listening_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session Audit Log (Metadata Only - No PHI)
CREATE TABLE session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    module_used TEXT,
    input_hash TEXT,
    output_hash TEXT,
    llm_provider TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    duration_ms INTEGER,
    ambient_source BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Template Versions
CREATE TABLE template_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(template_id, version)
);

-- Ambient Session Metadata (Future Phase)
CREATE TABLE ambient_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    consent_obtained BOOLEAN NOT NULL,
    consent_timestamp TIMESTAMP,
    duration_seconds INTEGER,
    transcription_complete BOOLEAN DEFAULT FALSE,
    integration_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.3 File Storage Structure

```
/vaucda/
├── data/
│   ├── documents/
│   │   ├── guidelines/
│   │   │   ├── nccn/           # NCCN guidelines
│   │   │   ├── aua/            # AUA guidelines
│   │   │   └── eau/            # EAU guidelines
│   │   ├── references/         # Peer-reviewed literature
│   │   └── calculators/        # Calculator documentation
│   ├── templates/
│   │   ├── clinic_notes/
│   │   ├── consult_notes/
│   │   ├── preop_notes/
│   │   └── postop_notes/
│   └── exports/                # User-generated exports
├── models/
│   └── embeddings/             # Local embedding models
├── logs/                       # Application logs (no PHI)
└── audio/                      # Temporary audio processing (Future)
    └── temp/                   # Ephemeral, auto-purged
```

---

## 8. LLM Integration Design

### 8.1 Provider Abstraction Layer

The system implements a provider-agnostic abstraction allowing seamless switching between LLM backends. All providers implement a common interface supporting synchronous generation, streaming generation, and embedding generation.

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, List

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate completion with streaming."""
        pass
    
    @abstractmethod
    async def get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings."""
        pass
```

### 8.2 Ollama Integration (Primary Provider)

Ollama serves as the primary LLM provider, running locally to ensure PHI never leaves the VA network. Configuration includes the host address (default localhost:11434), timeout settings (120 seconds for generation), default model selection (llama3.1:8b), generation parameters (temperature 0.3, top_p 0.9), and maximum token limits (4096).

The model selection strategy maps task types to optimal models:

| Task Type | Primary Model | Fallback Model | Min Context |
|-----------|---------------|----------------|-------------|
| Note Generation | llama3.1:70b | llama3.1:8b | 8192 |
| Clinical Extraction | llama3.1:8b | mistral:7b | 4096 |
| Calculator Assist | phi3:medium | llama3.1:8b | 2048 |
| Evidence Search | llama3.1:8b | mistral:7b | 4096 |
| Summarization | llama3.1:8b | phi3:medium | 4096 |

### 8.3 RAG Pipeline Architecture

The Clinical RAG Pipeline retrieves relevant context from the Neo4j knowledge graph and augments prompts before generation. The pipeline uses HuggingFace embeddings (sentence-transformers/all-MiniLM-L6-v2) for query vectorization, performs similarity search with optional category filtering, assembles context from top-k relevant documents (default k=5), constructs augmented prompts with retrieved context, and generates responses via the selected LLM provider.

### 8.4 System Prompts

The clinical system prompt establishes the assistant's role:

```
You are a clinical documentation assistant specialized in urology. 
Your role is to help urologists create structured clinical notes from raw clinical data.

Guidelines:
1. Maintain medical accuracy and use appropriate terminology
2. Organize information according to standard note structure
3. Highlight critical findings that require immediate attention
4. Include relevant differential diagnoses when appropriate
5. Reference evidence-based guidelines when applicable
6. Never fabricate clinical information not present in the input
7. Flag any missing information that would typically be required

Output notes should follow this structure:
- Chief Complaint
- History of Present Illness
- Relevant Urologic History
- Medications
- Physical Examination (GU focus)
- Diagnostic Results
- Assessment
- Plan
```

The calculator assist prompt template extracts values for specific calculators:

```
You are a clinical calculator assistant. Help extract relevant values 
from clinical text to populate calculator inputs.

For the {calculator_name} calculator, identify these inputs:
{input_list}

Extract values from the clinical text and format as JSON.
If a value cannot be determined, mark it as null.
```

---

## 9. Clinical Module Framework

### 9.1 Calculator Base Architecture

All clinical calculators inherit from a common base class that provides input validation, standardized result formatting, and reference management. The framework supports multiple input types including float, integer, boolean, and choice selections with validation rules for ranges and required fields.

Calculator results include the computed score, interpretive text, risk level classification (very low through very high), clinical recommendations, calculation breakdown, and literature references.

### 9.2 Prostate Cancer Module Suite

#### 9.2.1 PSA Kinetics Calculator

Calculates PSA velocity (PSAV) and PSA doubling time (PSADT) from serial PSA measurements. Inputs include PSA values array and corresponding time points in months. The calculator uses log-linear regression for PSADT calculation.

Interpretation thresholds:
- PSAV > 2.0 ng/mL/year: Concerning for recurrence
- PSAV > 0.75 ng/mL/year: Increased cancer risk
- PSADT < 3 months: Aggressive disease, high metastatic risk
- PSADT 3-9 months: Intermediate risk
- PSADT 9-15 months: Lower risk
- PSADT > 15 months: Indolent behavior

#### 9.2.2 CAPRA Score Calculator

The Cancer of the Prostate Risk Assessment score integrates PSA level, Gleason pattern, clinical T stage, and percent positive cores to generate a 0-10 point score with associated recurrence-free survival estimates.

Risk categories:
- Score 0-2: Low risk (5-year RFS ~85%)
- Score 3-5: Intermediate risk (5-year RFS ~65%)
- Score 6-10: High risk (5-year RFS ~40%)

### 9.3 Module Registry Pattern

The system maintains a central registry of all clinical calculators, enabling dynamic discovery, category-based filtering, and runtime registration of new modules. The registry supports 44 calculators across 10 clinical categories with consistent access patterns.

---

## 10. Ambient Listening Extension

### 10.1 Overview and Rationale

The Ambient Listening Extension represents a planned capability to capture provider-patient audio interactions during clinical encounters and intelligently integrate transcribed content into preliminary clinic notes. This extension addresses the documentation burden by allowing providers to focus on patient interaction while the system captures relevant clinical details for subsequent note completion.

### 10.2 Architectural Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AMBIENT LISTENING ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ CONSENT MODULE  │  ← Patient/Provider consent capture                    │
│  │ - Explicit opt-in                                                        │
│  │ - Recording indicator                                                    │
│  │ - Pause/Stop controls                                                    │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐ │
│  │  AUDIO CAPTURE  │───▶│  TRANSCRIPTION  │───▶│  SPEAKER DIARIZATION   │ │
│  │  - WebRTC       │    │  - Whisper      │    │  - Provider ID          │ │
│  │  - Secure stream│    │  - Real-time    │    │  - Patient ID           │ │
│  │  - Ephemeral    │    │  - <2s latency  │    │  - Confidence scores    │ │
│  └─────────────────┘    └─────────────────┘    └───────────┬─────────────┘ │
│                                                            │                │
│                                                            ▼                │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                     CLINICAL CONTENT EXTRACTION                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │ │
│  │  │  Symptoms   │  │  History    │  │  Exam       │  │  Plan       │   │ │
│  │  │  Extraction │  │  Details    │  │  Findings   │  │  Discussion │   │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      NOTE INTEGRATION ENGINE                           │ │
│  │                                                                        │ │
│  │   ┌─────────────────┐         ┌─────────────────┐                     │ │
│  │   │  PRELIMINARY    │         │  AMBIENT        │                     │ │
│  │   │  NOTE           │    +    │  CONTENT        │                     │ │
│  │   │  (from clinical │         │  (transcribed)  │                     │ │
│  │   │   data input)   │         │                 │                     │ │
│  │   └────────┬────────┘         └────────┬────────┘                     │ │
│  │            │                           │                              │ │
│  │            └─────────────┬─────────────┘                              │ │
│  │                          │                                            │ │
│  │                          ▼                                            │ │
│  │              ┌─────────────────────┐                                  │ │
│  │              │  INTELLIGENT MERGE  │                                  │ │
│  │              │  - Section mapping  │                                  │ │
│  │              │  - Conflict resolve │                                  │ │
│  │              │  - Source tagging   │                                  │ │
│  │              └─────────────────────┘                                  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                       REVIEW INTERFACE                                 │ │
│  │  - Ambient content highlighted                                         │ │
│  │  - Edit/approve workflow                                               │ │
│  │  - Source attribution visible                                          │ │
│  │  - One-click finalization                                              │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 Consent and Privacy Framework

#### 10.3.1 Consent Requirements

The ambient listening feature requires explicit consent from both provider and patient before any audio capture. The consent module implements a dual-consent workflow where the provider enables ambient listening for their session and the patient provides informed consent via verbal acknowledgment (transcribed) or digital signature. Consent is recorded with timestamp in the audit log (metadata only, no PHI). A visible recording indicator remains active throughout the encounter.

#### 10.3.2 Privacy Safeguards

All audio processing follows the zero-persistence PHI architecture. Audio streams are processed in real-time with no persistent storage of raw audio. Transcribed text exists only in ephemeral memory during the session. Upon note finalization, all intermediate data is securely deleted. Only the final, provider-approved note content is available for integration with the EHR.

### 10.4 Audio Processing Pipeline

#### 10.4.1 Audio Capture

Audio capture utilizes WebRTC for browser-based capture with fallback to native device APIs for approved recording hardware. Audio streams are transmitted over secure WebSocket connections with TLS 1.3 encryption. The capture module supports configurable audio quality (16kHz minimum for medical transcription accuracy) and includes automatic noise reduction optimized for clinical environments.

#### 10.4.2 Real-Time Transcription

Transcription employs OpenAI Whisper (or Azure Speech as alternative) configured for medical vocabulary recognition. The target latency is under 2 seconds from speech to text. The system maintains a running transcript with timestamp alignment for subsequent speaker diarization.

#### 10.4.3 Speaker Diarization

The pyannote-audio pipeline identifies speaker segments and classifies them as provider or patient speech. Diarization confidence scores are maintained for quality assurance. Low-confidence segments are flagged for provider review.

### 10.5 Clinical Content Extraction

The LLM-powered extraction pipeline analyzes transcribed content to identify clinically relevant information organized by note section. Extraction categories include:

**Chief Complaint and HPI**: Patient-reported symptoms, duration, severity, associated factors
**Review of Systems**: Relevant positive and negative findings mentioned
**Physical Exam**: Any findings discussed during examination
**Assessment Discussion**: Diagnostic reasoning, differential considerations
**Plan Discussion**: Treatment options discussed, patient preferences, follow-up

### 10.6 Note Integration Logic

#### 10.6.1 Merge Strategy

The integration engine combines preliminary notes (generated from structured clinical data input) with ambient content (extracted from transcription) using an intelligent merge algorithm:

1. **Section Mapping**: Ambient content is classified by note section
2. **Content Alignment**: Extracted details are aligned with corresponding sections in the preliminary note
3. **Conflict Resolution**: When ambient content contradicts preliminary note content, both versions are preserved with source tagging for provider review
4. **Enhancement**: Ambient content adds detail to sparse preliminary sections
5. **Source Attribution**: All ambient-sourced content is tagged with `[AMBIENT]` markers

#### 10.6.2 Integration Confidence Scoring

Each integrated element receives a confidence score based on transcription confidence (from ASR), diarization confidence (speaker identification), extraction confidence (clinical relevance), and alignment confidence (section mapping accuracy). Low-confidence integrations are highlighted for mandatory provider review.

### 10.7 Review and Approval Workflow

The review interface presents the integrated note with visual distinction between content sources. Providers can accept ambient content as-is, edit ambient content before acceptance, reject ambient content (revert to preliminary only), or add additional content manually. Only after explicit provider approval is the note considered final and eligible for EHR integration.

### 10.8 Technical Requirements

| Requirement | Specification |
|-------------|---------------|
| Audio Quality | 16kHz minimum sample rate, mono channel |
| Transcription Latency | < 2 seconds speech-to-text |
| Diarization Accuracy | > 90% speaker identification |
| Integration Latency | < 5 seconds for merge completion |
| Consent Recording | Timestamped, tamper-evident audit trail |
| Data Retention | Zero retention of audio; text deleted post-approval |

---

## 11. User Interface Design

### 11.1 Design Principles

The interface prioritizes clinical efficiency with minimal cognitive load. Design principles include clarity (immediate understanding of system state and available actions), efficiency (minimum clicks to complete common workflows), accessibility (WCAG 2.1 AA compliance throughout), and professionalism (medical-appropriate aesthetics conveying trust and reliability).

### 11.2 Color System

#### 11.2.1 Primary Palette

| Color | Hex | CSS Variable | Usage |
|-------|-----|--------------|-------|
| Primary Blue | `#2c5282` | `--primary-blue` | Navigation, primary buttons, headings |
| Primary Light | `#3182ce` | `--primary-light-blue` | Hover states, interactive highlights |
| Secondary Blue | `#4299e1` | `--secondary-blue` | Secondary buttons, badges |
| Accent Blue | `#63b3ed` | `--accent-blue` | Links, subtle accents |
| Medical Teal | `#0d9488` | `--medical-teal` | Clinical actions, medical buttons |

#### 11.2.2 Status Colors

| Status | Hex | Usage |
|--------|-----|-------|
| Success | `#10b981` | Confirmations, active status |
| Warning | `#f59e0b` | Cautions, modified states |
| Error | `#ef4444` | Errors, alerts |
| Info | `#06b6d4` | Notifications, info messages |

#### 11.2.3 Neutral Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Body Text | `#374151` | Primary text |
| Secondary Text | `#707783` | Metadata, labels |
| Light BG | `#f9fafb` | Page backgrounds |
| Border | `#e5e7eb` | Dividers, borders |

### 11.3 Main Application Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  VA UROLOGY CLINICAL DOCUMENTATION ASSISTANT                    [User] [⚙]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ NOTE GENERATION │  │    SETTINGS     │  │  OPEN EVIDENCE  │             │
│  │     [ACTIVE]    │  │                 │  │                 │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Main Content Area - Tab Dependent]                                        │
│                                                                             │
│  ┌─────────────────────────────────────┬───────────────────────────────┐   │
│  │                                     │                               │   │
│  │  INPUT PANEL                        │  MODULE SELECTION PANEL       │   │
│  │                                     │                               │   │
│  │  Note Type: [Dropdown]              │  ▼ PROSTATE CANCER            │   │
│  │                                     │    □ PSA Kinetics             │   │
│  │  Clinical Input:                    │    □ PCPT 2.0                 │   │
│  │  ┌─────────────────────────────┐   │    □ CAPRA Score              │   │
│  │  │                             │   │                               │   │
│  │  │  [Text area for clinical    │   │  ▼ KIDNEY CANCER              │   │
│  │  │   data input]               │   │    □ RENAL Score              │   │
│  │  │                             │   │    □ SSIGN Score              │   │
│  │  │                             │   │                               │   │
│  │  └─────────────────────────────┘   │  [+ More Categories...]       │   │
│  │                                     │                               │   │
│  │  LLM Model: [llama3.1:8b ▼]        │                               │   │
│  │                                     │                               │   │
│  │  [🎤 Enable Ambient Listening]     │                               │   │
│  │                                     │                               │   │
│  │  [Generate Note]  [Clear]           │                               │   │
│  │                                     │                               │   │
│  └─────────────────────────────────────┴───────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 Ambient Listening Interface (Future Phase)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AMBIENT LISTENING ACTIVE                                    [🔴 Recording] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LIVE TRANSCRIPTION                                                  │   │
│  │                                                                       │   │
│  │  [Provider]: "So you mentioned the urgency has gotten worse over     │   │
│  │              the past two weeks?"                                    │   │
│  │                                                                       │   │
│  │  [Patient]:  "Yes, especially at night. I'm getting up four or      │   │
│  │              five times now."                                        │   │
│  │                                                                       │   │
│  │  [Provider]: "And the stream, has that changed at all?"              │   │
│  │                                                                       │   │
│  │  [Patient]:  "It's definitely weaker. Takes longer to get started   │   │
│  │              too."                                                   │   │
│  │  ▼                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌───────────────────────────┐  ┌───────────────────────────────────────┐  │
│  │  EXTRACTED ELEMENTS       │  │  PRELIMINARY NOTE PREVIEW             │  │
│  │                           │  │                                       │  │
│  │  ✓ Nocturia: 4-5x/night  │  │  CC: [awaiting generation]            │  │
│  │  ✓ Urgency: worsening    │  │                                       │  │
│  │  ✓ Weak stream           │  │  HPI: [will integrate ambient]        │  │
│  │  ✓ Hesitancy             │  │                                       │  │
│  │                           │  │                                       │  │
│  └───────────────────────────┘  └───────────────────────────────────────┘  │
│                                                                             │
│  [⏸ Pause]  [⏹ Stop Recording]  [Complete Encounter]                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.5 React Component Architecture

The frontend is organized into logical component groups:

**Layout Components**: MainLayout, Header, Navigation, TabContainer
**Note Components**: NoteGenerator, NoteTypeSelector, ClinicalInputArea, GeneratedNoteDisplay
**Module Components**: ModuleSelector, CategoryAccordion, CalculatorPanel, CalculatorInputForm
**Ambient Components** (Future): AmbientController, TranscriptionDisplay, ExtractedElementsList, ReviewInterface
**Common Components**: Button, Card, Modal, StatusIndicator, LoadingSpinner

---

## 12. API Specification

### 12.1 RESTful Endpoints

#### 12.1.1 Note Generation

**POST /api/v1/notes/generate**

Generates a clinical note from provided input.

Request body:
- `clinical_input` (string, required): Raw clinical text
- `note_type` (enum, required): clinic_note | consult | preop | postop
- `template_id` (string, optional): Specific template to use
- `selected_modules` (array of strings): Calculator modules to include
- `llm_config` (object, optional): Provider, model, temperature settings
- `ambient_session_id` (string, optional, future): Associated ambient session

Response:
- `note_id` (string): Unique identifier
- `generated_note` (string): Complete formatted note
- `sections` (array): Individual note sections
- `appendices` (array): Calculator results
- `metadata` (object): Model used, tokens, generation time

#### 12.1.2 Calculator Operations

**GET /api/v1/calculators**

Lists all available calculators organized by category.

**POST /api/v1/calculators/{calculator_id}/calculate**

Executes a specific calculator with provided inputs.

Request body:
- `inputs` (object): Calculator-specific input values

Response:
- `score` (number): Calculated result
- `interpretation` (string): Clinical interpretation
- `risk_level` (string): Risk category if applicable
- `recommendations` (array): Clinical recommendations
- `breakdown` (object): Score component details
- `references` (array): Literature citations

#### 12.1.3 Ambient Listening (Future Phase)

**POST /api/v1/ambient/sessions/start**

Initiates an ambient listening session.

Request body:
- `provider_consent` (boolean, required)
- `patient_consent_type` (enum): verbal | digital
- `associated_note_id` (string, optional)

Response:
- `session_id` (string): Unique session identifier
- `websocket_url` (string): Audio streaming endpoint

**POST /api/v1/ambient/sessions/{session_id}/stop**

Terminates an ambient session and triggers integration.

**GET /api/v1/ambient/sessions/{session_id}/transcript**

Retrieves the transcription for review (ephemeral, deleted after approval).

**POST /api/v1/ambient/sessions/{session_id}/integrate**

Merges ambient content with preliminary note.

### 12.2 WebSocket Endpoints

**WS /ws/generate**

Real-time streaming for note generation with progress updates.

**WS /ws/ambient/stream** (Future)

Real-time audio streaming for ambient listening with live transcription feedback.

Message types:
- Client → Server: `audio_chunk` (binary audio data)
- Server → Client: `transcription_update` (incremental transcript)
- Server → Client: `extraction_update` (identified clinical elements)
- Server → Client: `diarization_update` (speaker identification)

---

## 13. Security Framework

### 13.1 Zero-Persistence PHI Architecture

The fundamental security principle is that no patient clinical information is ever persisted to disk, database, or any permanent storage. The system operates on a stateless, transient processing model where clinical input is received encrypted over TLS, data is decrypted and held only in volatile memory, LLM processing occurs with in-memory data only, generated output is returned to client over TLS, and all clinical data is immediately purged from memory. No PHI exists on the server after response delivery.

### 13.2 Secure Transmission

All client-server communication uses TLS 1.3 with approved cipher suites (TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256). Security headers include Strict-Transport-Security, X-Content-Type-Options, X-Frame-Options, Content-Security-Policy, and Referrer-Policy.

### 13.3 Ephemeral Data Handling

Clinical data is managed through a context manager pattern that guarantees secure deletion:

```python
@contextmanager
def ephemeral_clinical_context(clinical_input: str):
    """Context manager ensuring clinical data is deleted after use."""
    container = EphemeralClinicalData()
    container.set_data(clinical_input)
    
    try:
        yield container.get_data()
    finally:
        # ALWAYS delete data, even on exception
        container.secure_delete()
        del container
        gc.collect()
```

Memory is overwritten with zeros before deallocation, and garbage collection is forced to ensure complete removal.

### 13.4 Data Classification

| Data Type | Stored? | Location | Retention |
|-----------|---------|----------|-----------|
| Clinical Input (PHI) | Never | Memory only | Deleted immediately |
| Generated Notes (PHI) | Never | Memory only | Deleted immediately |
| Audio Recordings (Future) | Never | Memory only | Deleted immediately |
| Transcriptions (Future) | Never | Memory only | Deleted post-approval |
| User ID | Yes | SQLite | Per policy |
| Session Timestamps | Yes | SQLite | 90 days |
| Module Usage Stats | Yes | SQLite | Aggregated only |
| Clinical Templates | Yes | File system | Permanent |
| Medical Guidelines | Yes | Neo4j | Permanent |

### 13.5 Authentication and Authorization

The system implements JWT-based authentication with 30-minute token expiration. Tokens are validated on each request with role-based access control for administrative functions. VA PIV/CAC integration is supported for production deployment.

### 13.6 HIPAA Compliance Matrix

| Requirement | Implementation | Verification |
|-------------|----------------|--------------|
| Access Controls §164.312(a) | JWT auth, role-based access | Automated testing |
| Audit Controls §164.312(b) | PHI-free audit logging | Log review |
| Integrity Controls §164.312(c) | TLS 1.3, message signing | Certificate validation |
| Transmission Security §164.312(e) | Mandatory TLS 1.3 | SSL Labs A+ rating |
| Encryption §164.312(a)(2)(iv) | AES-256 via TLS | Cipher audit |
| Data Minimization | Zero PHI persistence | Architecture review |
| Automatic Logoff §164.312(a)(2)(iii) | 30-minute timeout | Session management |

### 13.7 Ambient Listening Security (Future)

The ambient listening extension inherits and extends the zero-persistence model:

**Consent Verification**: Recording cannot begin without verified dual consent
**Audio Streaming**: Encrypted WebSocket (WSS) with session-specific keys
**No Audio Storage**: Raw audio is processed in streaming fashion with no disk writes
**Transcription Ephemeral**: Text exists only in memory until provider approval
**Audit Trail**: Consent timestamps and session metadata recorded (no PHI)
**Secure Deletion**: All intermediate data purged upon note finalization

---

## 14. Deployment Strategy

### 14.1 Container Configuration

The application deploys via Docker Compose with the following services:

**vaucda-api** (Port 8000): FastAPI backend with environment connections to Neo4j, Ollama, and Redis
**vaucda-frontend** (Port 3000): React application serving the user interface
**neo4j** (Ports 7474, 7687): Graph database with APOC and GDS plugins
**ollama** (Port 11434): Local LLM server with GPU acceleration
**redis** (Port 6379): Message broker and cache
**celery-worker**: Background task processor

### 14.2 Ollama Model Deployment

Required models are pulled during deployment initialization:
- llama3.1:8b (primary, fast response)
- llama3.1:70b (complex reasoning)
- mistral:7b (fallback)
- phi3:medium (calculator assistance)
- nomic-embed-text (embeddings)

### 14.3 Neo4j Initialization

Database initialization includes creating uniqueness constraints on Document, Calculator, Template, and User IDs, creating vector indexes for document and concept embeddings (768 dimensions, cosine similarity), and creating full-text indexes for content search.

### 14.4 Environment Configuration

Critical environment variables include JWT_SECRET_KEY (from secure vault), NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OLLAMA_HOST, REDIS_URL, and TLS certificate paths. All secrets are managed through VA-approved secret management infrastructure.

---

## 15. Testing Strategy

### 15.1 Testing Levels

**Unit Testing**: pytest for all Python modules with 80% minimum coverage. Calculator algorithms require 100% coverage with validation against published examples.

**Integration Testing**: API endpoint testing with pytest-asyncio. Database interaction testing with test containers. LLM integration testing with mocked responses.

**End-to-End Testing**: Playwright for browser automation. Full workflow testing from input to generated note. Accessibility testing with axe-core.

**Security Testing**: Penetration testing by VA security team. HIPAA compliance verification. PHI leak detection testing.

### 15.2 Calculator Validation

Each clinical calculator undergoes validation against published examples from source literature, edge case testing for boundary conditions, cross-validation with existing clinical tools where available, and clinical review by urology subject matter experts.

### 15.3 Ambient Listening Testing (Future)

Specialized testing for ambient features includes audio quality testing across device types, transcription accuracy measurement (Word Error Rate), diarization accuracy measurement, integration accuracy assessment, and consent workflow verification.

---

## 16. Implementation Roadmap

### 16.1 Phase 1: Core Platform (Months 1-4)

**Milestone 1.1** (Month 1): Project setup, development environment, CI/CD pipeline
**Milestone 1.2** (Month 2): FastAPI backend, Neo4j integration, basic authentication
**Milestone 1.3** (Month 3): Ollama integration, note generation workflow, template system
**Milestone 1.4** (Month 4): Frontend development, basic UI, initial testing

### 16.2 Phase 2: Clinical Modules (Months 5-7)

**Milestone 2.1** (Month 5): Calculator framework, prostate cancer modules
**Milestone 2.2** (Month 6): Remaining calculator modules (kidney, bladder, voiding)
**Milestone 2.3** (Month 7): Module integration, appendix generation, clinical validation

### 16.3 Phase 3: RAG and Evidence (Months 8-9)

**Milestone 3.1** (Month 8): RAG pipeline implementation, document ingestion
**Milestone 3.2** (Month 9): Evidence search interface, knowledge graph population

### 16.4 Phase 4: Security and Deployment (Months 10-11)

**Milestone 4.1** (Month 10): Security hardening, HIPAA compliance verification
**Milestone 4.2** (Month 11): VA infrastructure deployment, user acceptance testing

### 16.5 Phase 5: Ambient Listening Extension (Months 12-16)

**Milestone 5.1** (Month 12): Audio capture infrastructure, WebSocket implementation
**Milestone 5.2** (Month 13): Transcription integration, speaker diarization
**Milestone 5.3** (Month 14): Clinical extraction pipeline, LLM fine-tuning
**Milestone 5.4** (Month 15): Note integration engine, review interface
**Milestone 5.5** (Month 16): Ambient feature testing, pilot deployment

---

## 17. Risk Assessment

### 17.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM accuracy issues | Medium | High | Rigorous prompt engineering, human review workflow |
| Performance degradation | Medium | Medium | Horizontal scaling, caching strategies |
| Ollama availability | Low | High | Fallback providers, health monitoring |
| Integration complexity | Medium | Medium | Phased rollout, comprehensive testing |

### 17.2 Security Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| PHI exposure | Low | Critical | Zero-persistence architecture, memory isolation |
| Authentication bypass | Low | High | JWT validation, VA PIV integration |
| Data breach | Low | Critical | TLS 1.3, encryption at rest for non-PHI |

### 17.3 Ambient Listening Risks (Future)

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Consent compliance | Medium | High | Robust consent workflow, audit trail |
| Transcription errors | Medium | Medium | Provider review requirement, confidence scoring |
| Audio privacy | Medium | High | Zero storage, encrypted streaming |
| Integration inaccuracy | Medium | Medium | Human approval required, source tagging |

### 17.4 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| User adoption resistance | Medium | High | Training program, champion users |
| Workflow disruption | Medium | Medium | Gradual rollout, parallel operation period |
| Support burden | Medium | Medium | Comprehensive documentation, help system |

---

## Appendices

### Appendix A: Clinical Calculator Reference

#### A.1 Prostate Cancer Calculators

| Calculator | Inputs | Output | Risk Categories |
|------------|--------|--------|-----------------|
| PSA Kinetics | PSA values, time points | PSAV, PSADT | Based on thresholds |
| PCPT 2.0 | Age, race, family hx, PSA, DRE | Probability (0-100%) | Continuous |
| CAPRA Score | PSA, Gleason, stage, % cores | 0-10 points | Low/Intermediate/High |
| NCCN Risk | PSA, Gleason, stage, cores | Categorical | Very Low to Very High |

#### A.2 Kidney Cancer Calculators

| Calculator | Inputs | Output | Risk Categories |
|------------|--------|--------|-----------------|
| RENAL Score | R, E, N, A, L components | 4-12 points | Low/Moderate/High complexity |
| SSIGN Score | TNM, size, grade, necrosis | 0-17 points | 5 risk groups |
| IMDC Criteria | KPS, time, labs | 0-6 factors | Favorable/Intermediate/Poor |

### Appendix B: Error Codes

| Code | Category | Description |
|------|----------|-------------|
| VAUCDA-001 | LLM | Ollama connection failed |
| VAUCDA-002 | LLM | Model not available |
| VAUCDA-003 | LLM | Generation timeout |
| VAUCDA-010 | Database | Neo4j connection failed |
| VAUCDA-011 | Database | Vector search failed |
| VAUCDA-020 | Calculator | Invalid input parameters |
| VAUCDA-021 | Calculator | Calculator not found |
| VAUCDA-030 | Template | Template not found |
| VAUCDA-031 | Template | Template parsing error |
| VAUCDA-040 | Auth | Authentication failed |
| VAUCDA-041 | Auth | Authorization denied |
| VAUCDA-050 | Ambient | Consent not obtained |
| VAUCDA-051 | Ambient | Transcription service unavailable |
| VAUCDA-052 | Ambient | Integration failed |

### Appendix C: Glossary

| Term | Definition |
|------|------------|
| CAPRA | Cancer of the Prostate Risk Assessment |
| IMDC | International Metastatic RCC Database Consortium |
| LLM | Large Language Model |
| PHI | Protected Health Information |
| PSADT | PSA Doubling Time |
| PSAV | PSA Velocity |
| RAG | Retrieval-Augmented Generation |
| RENAL | Radius, Exophytic, Nearness, Anterior/posterior, Location |
| SSIGN | Stage, Size, Grade, Necrosis |
| TLS | Transport Layer Security |

### Appendix D: Document Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technical Lead | | | |
| Clinical Advisor | | | |
| Security Officer | | | |
| Project Manager | | | |
| Executive Sponsor | | | |

---

*This document is confidential and intended for internal technical use only.*

**Document Version:** 1.0  
**Last Updated:** November 28, 2025  
**Next Review:** February 28, 2026
