# VAUCDA - Complete System Architecture
**VA Urology Clinical Documentation Assistant**

Version: 1.0
Date: November 28, 2025
Classification: Production-Ready Architecture

---

## Executive Summary

This document provides the complete technical architecture for VAUCDA, a production-ready Python web application that uses LLMs and RAG to transform unstructured clinical data into structured urology notes with 44 specialized clinical calculators.

**CRITICAL REQUIREMENTS:**
- NO fallbacks, placeholders, simulations, mock code, or demo code
- 100% functionality - all UI elements generate REAL data from actual system operations
- Environment-driven - Complete .env configuration system
- Zero-persistence PHI architecture (HIPAA compliance)
- Chain of Thought (COT) and Tree of Thought (TOT) reasoning throughout

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Complete Directory Structure](#complete-directory-structure)
3. [Technology Stack](#technology-stack)
4. [Database Architecture](#database-architecture)
5. [API Specification](#api-specification)
6. [Frontend Architecture](#frontend-architecture)
7. [LLM Integration Layer](#llm-integration-layer)
8. [Clinical Calculator Framework](#clinical-calculator-framework)
9. [Security Architecture](#security-architecture)
10. [Deployment Strategy](#deployment-strategy)
11. [Environment Configuration](#environment-configuration)
12. [Testing Strategy](#testing-strategy)
13. [Implementation Roadmap](#implementation-roadmap)
14. [Dependency Graph](#dependency-graph)

---

## 1. System Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │    React 18+ Frontend with Tailwind CSS 3.4+                  │  │
│  │    - Note Generation Interface                                 │  │
│  │    - Module Selection Panel (44 calculators)                  │  │
│  │    - Settings Management                                       │  │
│  │    - Evidence Search Interface                                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↕ HTTPS/TLS 1.3
┌─────────────────────────────────────────────────────────────────────┐
│                       APPLICATION LAYER                             │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐   │
│  │  FastAPI    │  │  Note       │  │  Clinical Module Engine   │   │
│  │  0.109+     │  │  Generator  │  │  (44 Calculators)         │   │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐   │
│  │  Template   │  │  Settings   │  │  Document Processor       │   │
│  │  Manager    │  │  Manager    │  │  (PDF/DOCX)               │   │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Celery 5.3+ Workers (Background LLM Processing)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────────┐
│                      CLINICAL MODULE LAYER                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐  │
│  │ Prostate (7) │ │ Kidney (4)   │ │ Bladder (3)  │ │ Male     │  │
│  │ Cancer       │ │ Cancer       │ │ Cancer       │ │ Void (5) │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐  │
│  │ Female (5)   │ │ Reconstr.(4) │ │ Fertility(5) │ │ Stones(4)│  │
│  │ Urology      │ │ Urology      │ │              │ │          │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────┘  │
│  ┌──────────────┐ ┌──────────────┐                                 │
│  │ Hypogon. (3) │ │ Surgical (4) │                                 │
│  │              │ │ Planning     │                                 │
│  └──────────────┘ └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────────┐
│                         LLM LAYER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐  │
│  │  Ollama     │  │  Anthropic  │  │  OpenAI                   │  │
│  │  (Primary)  │  │  (Optional) │  │  (Optional)               │  │
│  │  Local LLM  │  │  Claude API │  │  GPT-4o API               │  │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │         LangChain 0.1+ RAG Pipeline                          │  │
│  │         - Vector Search (Neo4j)                              │  │
│  │         - Context Assembly                                   │  │
│  │         - Augmented Generation                               │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐  │
│  │  Neo4j 5.x  │  │  SQLite     │  │  File Storage             │  │
│  │  Vector+KG  │  │  Settings   │  │  (Docs, Templates)        │  │
│  │  768-dim    │  │  Audit Logs │  │                           │  │
│  │  APOC, GDS  │  │  Sessions   │  │  NO PHI STORAGE           │  │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Redis 7.2+ (Message Broker, Caching)                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Capabilities

1. **Note Generation**: Transform unstructured clinical data into structured urology notes
2. **Clinical Decision Support**: 44 specialized calculators across 10 urologic subspecialties
3. **Evidence-Based Guidance**: RAG-powered knowledge retrieval from urologic literature
4. **Multi-Provider LLM Support**: Ollama (primary), Anthropic Claude, OpenAI GPT
5. **Zero-Persistence PHI**: HIPAA-compliant architecture with no PHI storage

### 1.3 Performance Targets

- Note generation: < 3 seconds (standard), < 10 seconds (complex)
- Calculator results: < 500ms
- System availability: 99.5%
- Support 500 concurrent users
- Zero PHI persistence (all clinical data deleted after response)

---

## 2. Complete Directory Structure

```
/home/gulab/PythonProjects/VAUCDA/
├── .env                              # Environment configuration (NOT in git)
├── .env.example                      # Template for environment variables
├── .gitignore                        # Git ignore configuration
├── docker-compose.yml                # Multi-container orchestration
├── Dockerfile                        # API container definition
├── README.md                         # Project documentation
├── LICENSE                           # License file
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Python project configuration
├── pytest.ini                        # Pytest configuration
├── logo.svg                          # VA logo (exists)
├── urology_prompt.txt                # System prompt (exists)
├── rules.txt                         # Development rules (exists)
│
├── docs/                             # Documentation
│   ├── VAUCDA.md                     # Calculator algorithms (exists)
│   ├── VAUCDA Colors.md              # Color palette (exists)
│   ├── VAUCDA_PDD.md                 # Program Design Doc (exists)
│   ├── VAUCDA_SDD.md                 # Software Design Doc (exists)
│   ├── API_REFERENCE.md              # API documentation
│   ├── CALCULATOR_REFERENCE.md       # Calculator documentation
│   ├── DEPLOYMENT_GUIDE.md           # Deployment instructions
│   └── USER_GUIDE.md                 # End-user documentation
│
├── backend/                          # FastAPI backend application
│   ├── __init__.py
│   ├── main.py                       # FastAPI application entry point
│   ├── config.py                     # Configuration management
│   ├── dependencies.py               # Dependency injection
│   │
│   ├── api/                          # API routes
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── notes.py              # Note generation endpoints
│   │   │   ├── calculators.py        # Calculator endpoints
│   │   │   ├── templates.py          # Template management endpoints
│   │   │   ├── settings.py           # Settings endpoints
│   │   │   ├── llm.py                # LLM management endpoints
│   │   │   ├── evidence.py           # Evidence search endpoints
│   │   │   └── health.py             # Health check endpoints
│   │   └── websockets/
│   │       ├── __init__.py
│   │       └── streaming.py          # WebSocket streaming endpoints
│   │
│   ├── core/                         # Core business logic
│   │   ├── __init__.py
│   │   ├── note_generator.py         # Note generation orchestration
│   │   ├── template_manager.py       # Template management
│   │   ├── settings_manager.py       # Settings management
│   │   ├── document_processor.py     # PDF/DOCX processing
│   │   └── session_manager.py        # Session handling
│   │
│   ├── calculators/                  # Clinical calculator modules
│   │   ├── __init__.py
│   │   ├── base.py                   # Base calculator class
│   │   ├── registry.py               # Calculator registry
│   │   ├── validators.py             # Input validation
│   │   │
│   │   ├── prostate/                 # Prostate cancer calculators (7)
│   │   │   ├── __init__.py
│   │   │   ├── psa_kinetics.py
│   │   │   ├── pcpt.py
│   │   │   ├── capra.py
│   │   │   ├── nccn_risk.py
│   │   │   ├── nccn_diagnostic.py
│   │   │   ├── nccn_surveillance.py
│   │   │   └── psa_tracking.py
│   │   │
│   │   ├── kidney/                   # Kidney cancer calculators (4)
│   │   │   ├── __init__.py
│   │   │   ├── renal_score.py
│   │   │   ├── ssign_score.py
│   │   │   ├── imdc_criteria.py
│   │   │   └── survival_estimate.py
│   │   │
│   │   ├── bladder/                  # Bladder cancer calculators (3)
│   │   │   ├── __init__.py
│   │   │   ├── eortc_recurrence.py
│   │   │   ├── eortc_progression.py
│   │   │   └── survival_estimate.py
│   │   │
│   │   ├── voiding/                  # Male voiding calculators (5)
│   │   │   ├── __init__.py
│   │   │   ├── ipss.py
│   │   │   ├── aua_subscore.py
│   │   │   ├── booi_bci.py
│   │   │   ├── uroflow.py
│   │   │   └── pvr_assessment.py
│   │   │
│   │   ├── female/                   # Female urology calculators (5)
│   │   │   ├── __init__.py
│   │   │   ├── udi_iiq.py
│   │   │   ├── oab_q.py
│   │   │   ├── pop_q.py
│   │   │   ├── sui_severity.py
│   │   │   └── bladder_diary.py
│   │   │
│   │   ├── reconstructive/           # Reconstructive urology (4)
│   │   │   ├── __init__.py
│   │   │   ├── stricture_complexity.py
│   │   │   ├── pfui_classification.py
│   │   │   ├── fistula_classification.py
│   │   │   └── peyronies_assessment.py
│   │   │
│   │   ├── fertility/                # Male fertility calculators (5)
│   │   │   ├── __init__.py
│   │   │   ├── semen_analysis.py
│   │   │   ├── hormonal_panel.py
│   │   │   ├── varicocele_grading.py
│   │   │   ├── azoospermia_workup.py
│   │   │   └── dfi_interpretation.py
│   │   │
│   │   ├── hypogonadism/             # Hypogonadism calculators (3)
│   │   │   ├── __init__.py
│   │   │   ├── testosterone_eval.py
│   │   │   ├── adam_questionnaire.py
│   │   │   └── treatment_monitoring.py
│   │   │
│   │   ├── stones/                   # Urolithiasis calculators (4)
│   │   │   ├── __init__.py
│   │   │   ├── stone_score.py
│   │   │   ├── passage_probability.py
│   │   │   ├── urine_24hr.py
│   │   │   └── prevention_plan.py
│   │   │
│   │   └── surgical/                 # Surgical planning calculators (4)
│   │       ├── __init__.py
│   │       ├── frailty_scale.py
│   │       ├── rcri.py
│   │       ├── nsqip.py
│   │       └── life_expectancy.py
│   │
│   ├── llm/                          # LLM integration layer
│   │   ├── __init__.py
│   │   ├── base.py                   # Base LLM provider interface
│   │   ├── orchestrator.py           # Multi-provider orchestration
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── ollama.py             # Ollama client (primary)
│   │   │   ├── anthropic.py          # Anthropic Claude client
│   │   │   └── openai.py             # OpenAI GPT client
│   │   ├── model_selector.py         # Task-based model selection
│   │   └── prompts.py                # System prompts (loads urology_prompt.txt)
│   │
│   ├── rag/                          # RAG pipeline
│   │   ├── __init__.py
│   │   ├── pipeline.py               # RAG pipeline orchestration
│   │   ├── embeddings.py             # Embedding generation
│   │   ├── retriever.py              # Document retrieval
│   │   ├── context_builder.py        # Context assembly
│   │   └── ingestion.py              # Document ingestion to Neo4j
│   │
│   ├── db/                           # Database layer
│   │   ├── __init__.py
│   │   ├── neo4j_client.py           # Neo4j connection and operations
│   │   ├── sqlite_client.py          # SQLite connection and operations
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── neo4j_models.py       # Neo4j node/relationship models
│   │   │   └── sqlite_models.py      # SQLite table models
│   │   └── migrations/
│   │       ├── neo4j/
│   │       │   └── init_schema.cypher
│   │       └── sqlite/
│   │           └── init_schema.sql
│   │
│   ├── security/                     # Security layer
│   │   ├── __init__.py
│   │   ├── ephemeral_data.py         # PHI ephemeral data handling
│   │   ├── auth.py                   # Authentication (JWT)
│   │   ├── encryption.py             # Encryption utilities
│   │   ├── audit.py                  # Audit logging (PHI-free)
│   │   └── middleware.py             # Security middleware
│   │
│   ├── models/                       # Pydantic models
│   │   ├── __init__.py
│   │   ├── notes.py                  # Note generation models
│   │   ├── calculators.py            # Calculator input/output models
│   │   ├── templates.py              # Template models
│   │   ├── settings.py               # Settings models
│   │   └── common.py                 # Common/shared models
│   │
│   ├── schemas/                      # Request/Response schemas
│   │   ├── __init__.py
│   │   ├── note_schemas.py
│   │   ├── calculator_schemas.py
│   │   ├── template_schemas.py
│   │   └── settings_schemas.py
│   │
│   ├── tasks/                        # Celery tasks
│   │   ├── __init__.py
│   │   ├── celery_app.py             # Celery application
│   │   ├── note_tasks.py             # Async note generation
│   │   └── ingestion_tasks.py        # Document ingestion tasks
│   │
│   ├── utils/                        # Utility functions
│   │   ├── __init__.py
│   │   ├── logging.py                # Logging configuration
│   │   ├── validators.py             # Custom validators
│   │   ├── formatters.py             # Output formatters
│   │   └── helpers.py                # Helper functions
│   │
│   └── tests/                        # Backend tests
│       ├── __init__.py
│       ├── conftest.py               # Pytest fixtures
│       ├── unit/                     # Unit tests
│       │   ├── test_calculators/
│       │   ├── test_llm/
│       │   ├── test_rag/
│       │   └── test_security/
│       ├── integration/              # Integration tests
│       │   ├── test_api/
│       │   ├── test_db/
│       │   └── test_e2e/
│       └── fixtures/                 # Test data
│           ├── clinical_data/
│           └── expected_outputs/
│
├── frontend/                         # React frontend application
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── vite.config.ts               # Vite build configuration
│   ├── .env.local                    # Frontend environment vars
│   ├── index.html
│   │
│   ├── public/                       # Static assets
│   │   ├── logo.svg                  # Symlink to /logo.svg
│   │   └── favicon.ico
│   │
│   └── src/
│       ├── main.tsx                  # Application entry point
│       ├── App.tsx                   # Root component
│       ├── index.css                 # Global styles (Tailwind)
│       │
│       ├── components/               # React components
│       │   ├── layout/
│       │   │   ├── MainLayout.tsx
│       │   │   ├── Header.tsx
│       │   │   ├── Navigation.tsx
│       │   │   └── TabContainer.tsx
│       │   │
│       │   ├── note/
│       │   │   ├── NoteGenerator.tsx
│       │   │   ├── NoteTypeSelector.tsx
│       │   │   ├── ClinicalInputArea.tsx
│       │   │   ├── GeneratedNoteDisplay.tsx
│       │   │   └── NoteExporter.tsx
│       │   │
│       │   ├── modules/
│       │   │   ├── ModuleSelector.tsx
│       │   │   ├── CategoryAccordion.tsx
│       │   │   ├── CalculatorPanel.tsx
│       │   │   ├── CalculatorInputForm.tsx
│       │   │   └── CalculatorResults.tsx
│       │   │
│       │   ├── settings/
│       │   │   ├── SettingsPanel.tsx
│       │   │   ├── TemplateSettings.tsx
│       │   │   ├── LLMSettings.tsx
│       │   │   └── ModuleDefaults.tsx
│       │   │
│       │   ├── evidence/
│       │   │   ├── EvidenceSearch.tsx
│       │   │   ├── SearchResults.tsx
│       │   │   └── DocumentViewer.tsx
│       │   │
│       │   └── common/
│       │       ├── Button.tsx
│       │       ├── Card.tsx
│       │       ├── Modal.tsx
│       │       ├── StatusIndicator.tsx
│       │       ├── LoadingSpinner.tsx
│       │       └── ErrorBoundary.tsx
│       │
│       ├── hooks/                    # Custom React hooks
│       │   ├── useNoteGeneration.ts
│       │   ├── useCalculator.ts
│       │   ├── useSettings.ts
│       │   └── useWebSocket.ts
│       │
│       ├── services/                 # API client services
│       │   ├── api.ts                # Axios instance
│       │   ├── noteService.ts
│       │   ├── calculatorService.ts
│       │   ├── templateService.ts
│       │   └── settingsService.ts
│       │
│       ├── store/                    # State management
│       │   ├── index.ts
│       │   ├── noteSlice.ts
│       │   ├── settingsSlice.ts
│       │   └── uiSlice.ts
│       │
│       ├── types/                    # TypeScript types
│       │   ├── note.types.ts
│       │   ├── calculator.types.ts
│       │   ├── template.types.ts
│       │   └── common.types.ts
│       │
│       ├── utils/                    # Utility functions
│       │   ├── formatters.ts
│       │   ├── validators.ts
│       │   └── constants.ts
│       │
│       └── __tests__/                # Frontend tests
│           ├── components/
│           ├── hooks/
│           └── utils/
│
├── data/                             # Application data (NOT in git if contains PHI)
│   ├── documents/                    # Clinical knowledge documents
│   │   ├── guidelines/
│   │   │   ├── nccn/                 # NCCN guidelines
│   │   │   ├── aua/                  # AUA guidelines
│   │   │   └── eau/                  # EAU guidelines
│   │   ├── references/               # Peer-reviewed literature
│   │   └── calculators/              # Calculator documentation
│   │
│   ├── templates/                    # Note templates
│   │   ├── clinic_notes/
│   │   ├── consult_notes/
│   │   ├── preop_notes/
│   │   └── postop_notes/
│   │
│   ├── settings/                     # SQLite databases
│   │   └── vaucda.db
│   │
│   └── exports/                      # User-generated exports (ephemeral)
│
├── logs/                             # Application logs (NO PHI)
│   ├── api.log
│   ├── celery.log
│   ├── audit.log                     # PHI-free audit logs
│   └── error.log
│
├── scripts/                          # Utility scripts
│   ├── setup_ollama_models.sh        # Pull required Ollama models
│   ├── init_neo4j.sh                 # Initialize Neo4j schema
│   ├── ingest_documents.py           # Ingest clinical documents to Neo4j
│   ├── create_admin_user.py          # Create admin user
│   └── backup_settings.sh            # Backup settings database
│
└── deployment/                       # Deployment configurations
    ├── nginx/
    │   └── vaucda.conf               # Nginx reverse proxy config
    ├── systemd/
    │   ├── vaucda-api.service
    │   └── vaucda-celery.service
    └── ssl/
        └── README.md                 # SSL certificate instructions
```

---

## 3. Technology Stack

### 3.1 Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Web Framework | FastAPI | 0.109+ | Async REST API, WebSocket support |
| Python Runtime | Python | 3.11+ | Core application logic |
| Task Queue | Celery | 5.3+ | Background processing for LLM calls |
| Message Broker | Redis | 7.2+ | Celery backend, caching |
| ASGI Server | Uvicorn | 0.27+ | Production async server |

**Key Dependencies:**
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
celery[redis]==5.3.4
redis==5.0.1
python-dotenv==1.0.0
pydantic==2.5.0
pydantic-settings==2.1.0
```

### 3.2 LLM Integration Stack

| Provider | Integration Method | Models Supported |
|----------|-------------------|------------------|
| Ollama (Primary) | REST API via `ollama-python` | Llama 3.1 (8B/70B), Mistral 7B, Phi-3 |
| Anthropic | `anthropic` SDK | Claude 3.5 Sonnet, Claude 3 Opus |
| OpenAI | `openai` SDK | GPT-4o, GPT-4 Turbo |

**Dependencies:**
```
ollama-python==0.1.0
anthropic==0.18.0
openai==1.10.0
langchain==0.1.0
langchain-community==0.0.10
sentence-transformers==2.2.2
```

### 3.3 Database Technologies

| Database | Purpose | Configuration |
|----------|---------|---------------|
| Neo4j 5.x | Vector storage (768-dim), knowledge graph | APOC, GDS plugins enabled |
| SQLite | User settings, session metadata, audit logs | Local file-based, no PHI |
| File System | Document storage, templates | Structured directory hierarchy |

**Dependencies:**
```
neo4j==5.15.0
neo4j-graphdatabase==5.15.0
langchain-neo4j==0.1.0
aiosqlite==0.19.0
```

### 3.4 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18+ | Component-based UI framework |
| TypeScript | 5+ | Type safety |
| Vite | 5+ | Build tool and dev server |
| Tailwind CSS | 3.4+ | Utility-first styling |
| Axios | 1.6+ | HTTP client |
| Redux Toolkit | 2.0+ | State management |

**package.json dependencies:**
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "@reduxjs/toolkit": "^2.0.0",
    "react-redux": "^9.0.0",
    "axios": "^1.6.0",
    "tailwindcss": "^3.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

### 3.5 Document Processing

| Component | Technology | Purpose |
|-----------|------------|---------|
| PDF Parsing | PyMuPDF | PDF extraction |
| DOCX Parsing | python-docx | DOCX extraction |
| Text Processing | unstructured | Document chunking |

**Dependencies:**
```
pymupdf==1.23.8
python-docx==1.1.0
unstructured==0.11.0
```

### 3.6 Security & Authentication

| Component | Technology | Purpose |
|-----------|------------|---------|
| Authentication | python-jose, passlib | JWT token generation |
| Password Hashing | bcrypt | Secure password storage |
| TLS/SSL | cryptography | Certificate management |

**Dependencies:**
```
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==41.0.7
```

---

## 4. Database Architecture

### 4.1 Neo4j Graph Schema

#### 4.1.1 Node Types

**Document Nodes** (Clinical Knowledge)
```cypher
(:Document {
    id: STRING (UUID),
    title: STRING,
    source: STRING,
    content: STRING (full text),
    embedding: LIST<FLOAT> (768 dimensions),
    created_at: DATETIME,
    document_type: STRING  // 'guideline', 'reference', 'calculator'
})
```

**ClinicalConcept Nodes**
```cypher
(:ClinicalConcept {
    id: STRING (UUID),
    name: STRING,
    category: STRING,  // 'prostate', 'kidney', 'bladder', etc.
    description: STRING,
    icd10_codes: LIST<STRING>,
    snomed_codes: LIST<STRING>,
    embedding: LIST<FLOAT> (768 dimensions)
})
```

**Calculator Nodes**
```cypher
(:Calculator {
    id: STRING (UUID),
    name: STRING,
    category: STRING,
    formula: STRING,
    inputs: LIST<STRING>,
    interpretation: STRING,
    references: LIST<STRING>,
    version: STRING
})
```

**Template Nodes**
```cypher
(:Template {
    id: STRING (UUID),
    name: STRING,
    type: STRING,  // 'clinic_note', 'consult', 'preop', 'postop'
    content: STRING,
    sections: LIST<STRING>,
    active: BOOLEAN,
    created_at: DATETIME
})
```

**User Nodes**
```cypher
(:User {
    id: STRING (UUID),
    username: STRING UNIQUE,
    email: STRING UNIQUE,
    role: STRING,  // 'user', 'admin'
    preferences: MAP,
    created_at: DATETIME,
    last_login: DATETIME
})
```

#### 4.1.2 Relationship Types

```cypher
// Knowledge Graph Relationships
(:Document)-[:REFERENCES]->(:ClinicalConcept)
(:Document)-[:CITES]->(:Document)
(:ClinicalConcept)-[:RELATED_TO {weight: FLOAT}]->(:ClinicalConcept)
(:Calculator)-[:APPLIES_TO]->(:ClinicalConcept)
(:Calculator)-[:DERIVED_FROM]->(:Document)

// User Relationships
(:User)-[:PREFERS {priority: INT}]->(:Template)
(:User)-[:USES {count: INT, last_used: DATETIME}]->(:Calculator)
```

#### 4.1.3 Vector Indexes

```cypher
// Document embeddings index for RAG
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
FOR (d:Document) ON EACH [d.content, d.title]

CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description]
```

#### 4.1.4 Constraints

```cypher
// Uniqueness constraints
CREATE CONSTRAINT document_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE

CREATE CONSTRAINT calculator_id IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.id IS UNIQUE

CREATE CONSTRAINT template_id IF NOT EXISTS
FOR (t:Template) REQUIRE t.id IS UNIQUE

CREATE CONSTRAINT user_id IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE

CREATE CONSTRAINT user_username IF NOT EXISTS
FOR (u:User) REQUIRE u.username IS UNIQUE
```

### 4.2 SQLite Schema

```sql
-- User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    default_llm TEXT DEFAULT 'ollama',
    default_model TEXT DEFAULT 'llama3.1:8b',
    default_template TEXT DEFAULT 'urology_clinic',
    module_defaults JSON,
    display_preferences JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session Audit Log (Metadata Only - NO PHI)
CREATE TABLE IF NOT EXISTS session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- 'note_generation', 'calculator_use', etc.
    module_used TEXT,
    input_hash TEXT,       -- SHA256 hash only, not actual content
    output_hash TEXT,      -- SHA256 hash only, not actual content
    llm_provider TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    duration_ms INTEGER,
    success BOOLEAN,
    error_code TEXT,       -- Non-descriptive error code
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for performance
    INDEX idx_session_id (session_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Template Versions
CREATE TABLE IF NOT EXISTS template_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(template_id, version)
);

-- LLM Model Cache Metadata
CREATE TABLE IF NOT EXISTS llm_model_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL,
    last_pulled TIMESTAMP,
    size_mb INTEGER,
    status TEXT,  -- 'available', 'pulling', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Calculator Usage Statistics (Aggregated, No PHI)
CREATE TABLE IF NOT EXISTS calculator_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calculator_id TEXT NOT NULL,
    usage_date DATE NOT NULL,
    usage_count INTEGER DEFAULT 0,
    avg_computation_time_ms REAL,

    UNIQUE(calculator_id, usage_date)
);
```

### 4.3 Redis Data Structures

**Celery Task Queue:**
```
celery:task:{task_id}  // Task metadata
celery:result:{task_id}  // Task results
```

**Session Cache:**
```
session:{session_id}  // TTL: 30 minutes
{
    "user_id": "uuid",
    "llm_provider": "ollama",
    "model": "llama3.1:8b"
}
```

**LLM Response Cache (Optional):**
```
llm_cache:{input_hash}  // TTL: 1 hour
{
    "response": "...",
    "model": "llama3.1:8b",
    "timestamp": "ISO8601"
}
```

---

This is the first part of the comprehensive architecture document. Would you like me to continue with the remaining sections (API Specification, Frontend Architecture, LLM Integration, Clinical Calculators, Security, Deployment, Environment Configuration, Testing, Implementation Roadmap, and Dependency Graph)?

