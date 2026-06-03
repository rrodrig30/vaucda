# EPIC-VAUCDA: EPIC FHIR Urology Clinical Documentation Assistant
# Software Design Document

**Version:** 1.0
**Date:** February 4, 2026
**Status:** Draft
**Document Type:** Software Design Document (SDD)
**Classification:** Internal Technical Documentation

---

## Document Control

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | 2026-02-04 | EPIC-VAUCDA Development Team | Initial software design document |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture Design](#3-architecture-design)
4. [Technology Stack](#4-technology-stack)
5. [Data Layer Design](#5-data-layer-design)
6. [EPIC FHIR Integration Layer](#6-epic-fhir-integration-layer)
7. [Note Processing Pipeline](#7-note-processing-pipeline)
8. [LLM Integration Layer](#8-llm-integration-layer)
9. [Clinical Calculator Engine](#9-clinical-calculator-engine)
10. [Word Document Generation](#10-word-document-generation)
11. [User Interface Specification](#11-user-interface-specification)
12. [API Design](#12-api-design)
13. [Authentication and Authorization](#13-authentication-and-authorization)
14. [Security and Compliance](#14-security-and-compliance)
15. [Deployment Architecture](#15-deployment-architecture)
16. [Appendices](#appendices)

---

## 1. Executive Summary

### 1.1 Purpose

This Software Design Document (SDD) defines the complete technical architecture, component design, data models, integration specifications, and implementation details for EPIC-VAUCDA (EPIC FHIR Urology Clinical Documentation Assistant). EPIC-VAUCDA extends the foundational VAUCDA system by replacing manual clinical data upload with automated extraction via the EPIC FHIR R4 API, producing structured urology clinic notes in Microsoft Word format through AI-powered component extraction using Anthropic Claude and Ollama LLM providers with dynamic model discovery.

### 1.2 Scope

This document encompasses the complete software design including EPIC FHIR R4 integration via SMART on FHIR OAuth 2.0 with PKCE, automated clinical data extraction from twelve FHIR resource types, a five-stage AI-powered note processing pipeline, dynamic LLM model discovery and selection across Anthropic and Ollama providers, Microsoft Word document generation via python-docx, 44 specialized urology clinical calculators with FHIR auto-population, Neo4j-powered RAG pipeline with PubMedBERT embeddings, React-based frontend with EPIC settings management, and zero-persistence PHI architecture for HIPAA compliance.

### 1.3 Key Technical Differentiators from VAUCDA

| Aspect | VAUCDA SDD | EPIC-VAUCDA SDD |
|--------|-----------|-----------------|
| Data Input | Manual text paste | EPIC FHIR R4 API with 12 resource types |
| Authentication | JWT-based | OAuth 2.0 SMART on FHIR with PKCE (RFC 7636) |
| Output Format | Browser HTML display | Microsoft Word (.docx) via python-docx |
| LLM Providers | Ollama, Anthropic, OpenAI | Ollama, Anthropic only (dynamic model loading) |
| Model Selection | Static configuration | Runtime discovery via API polling |
| Lab Retrieval | Manual paste | Dual-strategy: 6-month window + targeted LOINC |
| Calculator Inputs | Manual entry | FHIR auto-population from Observation resources |
| Settings | Basic preferences | EPIC credentials, LLM management, connection status |
| Embeddings | sentence-transformers general | PubMedBERT (NeuML/pubmedbert-base-embeddings) |
| Pipeline | 3-stage (paste → extract → display) | 5-stage (FHIR → extract → synthesize → build → Word) |

### 1.4 Compliance with Development Standards

This document and all implementations described herein comply with the EPIC-VAUCDA development standards (rules.txt):

- **Zero tolerance**: No fallbacks, placeholders, simulations, mock code, demo code, simplified versions, partially functioning code, nonfunctional code, emergency bypasses, or crippled implementations
- **Real implementation only**: All UI elements generate real data from actual system operations; no hardcoded elements; all configuration loaded from environment variables
- **Chain of Thought (COT) analysis**: Problem identification, solution design, implementation planning, testing strategy, and risk assessment applied to all design decisions
- **Tree of Thought (TOT) evaluation**: All solutions evaluated for reliability, efficiency, completeness, scalability, and compliance

---

## 2. System Overview

### 2.1 Functional Architecture

EPIC-VAUCDA provides three core functional areas:

**Clinical Note Generation**: Automated extraction of clinical data from EPIC FHIR R4 APIs, AI-powered transformation into structured urology clinic notes, and output as formatted Microsoft Word documents. The system supports four note types: clinic notes, consult notes, pre-operative notes, and post-operative notes.

**Clinical Decision Support**: 44 specialized calculators spanning 10 urologic subspecialties with automatic input population from FHIR-extracted laboratory data. Calculator results integrate directly into generated Word documents.

**Evidence-Based Guidance**: RAG-powered semantic search across clinical knowledge bases including AUA Guidelines, NCCN Clinical Practice Guidelines, and EAU Guidelines stored in Neo4j with PubMedBERT vector embeddings.

### 2.2 Clinical Module Categories

| Category | Module Count | Key Calculators/Assessments |
|----------|-------------|----------------------------|
| Prostate Cancer | 7 | PSA Kinetics, PCPT 2.0, CAPRA Score, NCCN Risk Stratification, D'Amico Classification, Memorial Nomogram, Partin Tables |
| Kidney Cancer | 4 | RENAL Nephrometry, SSIGN Score, IMDC Criteria, Leibovich Prognosis |
| Bladder Cancer | 3 | EORTC Recurrence Score, EORTC Progression Score, Cystectomy Nomogram |
| Male Voiding | 5 | IPSS, AUA Symptom Subscore, BOOI/BCI (Urodynamics), Uroflow Analysis, PVR Assessment |
| Female Urology | 5 | UDI-6/IIQ-7, OAB-q, POP-Q Staging, Blaivas-Groutz Classification, Valsalva Leak Point |
| Reconstructive | 4 | Stricture Complexity, PFUI Classification, Tissue Transfer Assessment, Fistula Classification |
| Male Fertility | 5 | Semen Analysis (WHO 2021), Varicocele Grading, Testosterone/FSH Ratio, Sperm Morphology (Kruger), DNA Fragmentation Index |
| Hypogonadism | 3 | Testosterone Evaluation, ADAM Questionnaire, qADAM Score |
| Urolithiasis | 4 | STONE Score, 24-hr Urine Interpretation, Hounsfield Density Analysis, Guy Stone Score |
| Surgical Planning | 4 | Clinical Frailty Scale (CFS), RCRI, NSQIP Risk Calculator, ASA Classification |

**Total: 44 Clinical Modules**

### 2.3 Non-Functional Requirements

| Requirement | Target | Verification |
|-------------|--------|-------------|
| FHIR data extraction | < 5 seconds (full patient) | Performance monitoring |
| Note generation (standard) | < 3 seconds | Load testing |
| Note generation (complex) | < 10 seconds | Load testing |
| Word document generation | < 2 seconds | Benchmark testing |
| Calculator results | < 500 milliseconds | Unit testing |
| Dynamic model discovery | < 2 seconds | Integration testing |
| System availability | 99.5% (6 AM - 10 PM) | Uptime monitoring |
| Concurrent users | 500 | Stress testing |
| EPIC connectivity uptime | 99.9% | Connection monitoring |
| Calculator accuracy | 100% mathematical | Validation testing |
| WCAG 2.1 AA compliance | Full compliance | Accessibility audit |

---

## 3. Architecture Design

### 3.1 High-Level Architecture

```
+-----------------------------------------------------------------------------+
|                              PRESENTATION LAYER                              |
|  +-----------------------------------------------------------------------+  |
|  |                    Web Interface (React 18+)                           |  |
|  |              Tailwind CSS 3.4+ / TypeScript 5.3+                      |  |
|  |  +-------------------+  +-------------------+  +-------------------+  |  |
|  |  | Note Generation   |  | EPIC Settings     |  | Evidence Search  |  |  |
|  |  | - Patient select  |  | - FHIR config     |  | - RAG search     |  |  |
|  |  | - LLM model pick  |  | - OAuth creds     |  | - Guideline view |  |  |
|  |  | - Module select   |  | - LLM management  |  | - Source attrib  |  |  |
|  |  | - Word download   |  | - Model discovery |  |                   |  |  |
|  |  +-------------------+  +-------------------+  +-------------------+  |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
|                              APPLICATION LAYER                               |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  FastAPI 0.109+ |  |  Note           |  |  Clinical Module Engine   |     |
|  |  Backend        |  |  Generator      |  |  (44 Calculators)         |     |
|  |  (Async)        |  |  (5-Stage)      |  |  (FHIR Auto-populate)    |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  EPIC FHIR      |  |  Word Document  |  |  Template Manager         |     |
|  |  Client          |  |  Generator      |  |  (Clinic, Consult,        |     |
|  |  (httpx async)  |  |  (python-docx)  |  |   PreOp, PostOp)          |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Settings        |  |  LLM Model      |  |  FHIR Resource           |     |
|  |  Manager          |  |  Discovery      |  |  Parser                   |     |
|  |  (Encrypted)     |  |  (Runtime)      |  |  (12 Resource Types)      |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                       EPIC FHIR INTEGRATION LAYER                            |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  OAuth 2.0      |  |  FHIR R4        |  |  Resource Extractors      |     |
|  |  SMART on FHIR  |  |  Client          |  |  - LabFetcher (LOINC)     |     |
|  |  with PKCE      |  |  (Async HTTP)   |  |  - NoteFetcher            |     |
|  |  (RFC 7636)     |  |                  |  |  - ImagingFetcher         |     |
|  +-----------------+  +-----------------+  |  - PathologyFetcher       |     |
|                                             |  - MedicationFetcher      |     |
|                                             |  - AllergyFetcher         |     |
|                                             |  - HistoryFetcher         |     |
|                                             +---------------------------+     |
+-----------------------------------------------------------------------------+
|                         AI PROCESSING LAYER                                  |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Extraction      |  |  Synthesis      |  |  RAG Pipeline             |     |
|  |  Agents          |  |  Agents          |  |  (LangChain + Neo4j)      |     |
|  |  - HPI Agent    |  |  - Assessment   |  |                           |     |
|  |  - Lab Agent    |  |  - Plan Agent   |  |  PubMedBERT Embeddings    |     |
|  |  - Imaging Agt  |  |  - PSA Agent    |  |  (768-dim vectors)        |     |
|  |  - Path Agent   |  |  - IPSS Agent   |  |  Cosine Similarity        |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                              LLM LAYER                                       |
|  +-----------------------------+  +---------------------------------------+  |
|  |  Ollama Client               |  |  Anthropic Client                     |  |
|  |  - Local GPU inference      |  |  - Claude 3.5 Sonnet, Claude 3 Opus  |  |
|  |  - /api/tags discovery      |  |  - API-based model discovery          |  |
|  |  - /api/generate endpoint   |  |  - /v1/messages endpoint              |  |
|  |  - /api/chat endpoint       |  |  - Streaming support                  |  |
|  +-----------------------------+  +---------------------------------------+  |
|  +---------------------------------------------------------------------+    |
|  |  Dynamic Model Discovery Registry                                     |    |
|  |  - Runtime model enumeration from all configured providers            |    |
|  |  - Model capability mapping (context window, token limits)            |    |
|  |  - Health check and availability monitoring                           |    |
|  |  - Task-to-model recommendation engine                                |    |
|  +---------------------------------------------------------------------+    |
+-----------------------------------------------------------------------------+
|                              DATA LAYER                                      |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Neo4j 5.x      |  |  SQLite          |  |  File Storage             |     |
|  |  Vector + KG    |  |  Settings DB    |  |  (Templates, Exports,     |     |
|  |  PubMedBERT     |  |  (Encrypted     |  |   Guidelines, Word docs)  |     |
|  |  768-dim cosine |  |   credentials)  |  |                           |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
```

### 3.2 Component Interaction Flow

```
+----------+    +----------+    +--------------+    +-------------+
|  User    |--->| FastAPI  |--->| EPIC FHIR    |--->| EPIC EHR    |
| Interface|    | Backend  |    | Client       |    | (FHIR R4)   |
+----------+    +----------+    +--------------+    +-------------+
                     |                 |
                     |                 v
                     |          +--------------+
                     |          | FHIR Resource|
                     |          | Extractors   |
                     |          +--------------+
                     |                 |
                     v                 v
              +----------+    +--------------+    +-------------+
              | Clinical |    | Note         |--->| LLM Layer   |
              | Modules  |    | Processing   |    | (Ollama /   |
              | (44 calc)|    | Pipeline     |    |  Anthropic) |
              +----------+    +--------------+    +-------------+
                                    |                    |
                                    v                    v
                             +--------------+    +-------------+
                             | Word Doc     |    | Neo4j       |
                             | Generator    |    | RAG + KG    |
                             | (python-docx)|    | (PubMedBERT)|
                             +--------------+    +-------------+
                                    |
                                    v
                             +--------------+
                             | .docx file   |
                             | (download)   |
                             +--------------+
```

### 3.3 Five-Stage Note Processing Pipeline

```
Stage 1: FHIR Data Extraction
+-------------------+     +-------------------+     +-------------------+
| OAuth 2.0 Auth    |---->| FHIR R4 Queries   |---->| Raw FHIR Bundles  |
| (SMART on FHIR)   |     | (12 resource types)|     | (JSON resources)  |
+-------------------+     +-------------------+     +-------------------+
                                                            |
                                                            v
Stage 2: Component Extraction (AI Agents)
+-------------------+     +-------------------+     +-------------------+
| HPI Agent         |     | Lab Agent         |     | Imaging Agent     |
| Pathology Agent   |     | Assessment Agent  |     | Plan Agent        |
| PSA Agent         |     | IPSS Agent        |     |                   |
+-------------------+     +-------------------+     +-------------------+
                                                            |
                                                            v
Stage 3: Document-Level Extraction
+-------------------+     +-------------------+     +-------------------+
| Allergy Extractor |     | Medication Ext    |     | PMH/PSH/Family    |
| Social Hx Extract |     | Diet Hx Extract   |     | Sexual Hx Extract |
+-------------------+     +-------------------+     +-------------------+
                                                            |
                                                            v
Stage 4: Section Synthesis (AI Agents)
+-------------------+     +-------------------+     +-------------------+
| Multi-source      |     | Conflict          |     | RAG-augmented     |
| section merging   |     | resolution        |     | evidence insert   |
+-------------------+     +-------------------+     +-------------------+
                                                            |
                                                            v
Stage 5: Word Document Assembly
+-------------------+     +-------------------+     +-------------------+
| python-docx       |     | Template          |     | .docx file        |
| rendering engine  |     | formatting        |     | (downloadable)    |
+-------------------+     +-------------------+     +-------------------+
```

---

## 4. Technology Stack

### 4.1 Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Web Framework | FastAPI | 0.109+ | REST API, async request handling, WebSocket |
| Python Runtime | Python | 3.11+ | Core application logic |
| ASGI Server | Uvicorn | 0.27+ | Production server with HTTP/2 |
| Task Queue | Celery | 5.3+ | Background FHIR fetching, LLM calls |
| Message Broker | Redis | 7.2+ | Celery backend, session caching |
| HTTP Client | httpx | 0.27+ | Async FHIR API calls, LLM API calls |
| Word Generation | python-docx | 1.1+ | Microsoft Word document creation |
| OAuth Library | authlib | 1.3+ | SMART on FHIR OAuth 2.0 with PKCE |
| Encryption | cryptography | 42.0+ | Credential encryption (Fernet) |
| Data Validation | Pydantic | 2.5+ | Request/response models, FHIR schemas |

### 4.2 LLM Integration

| Provider | Integration | Models Supported |
|----------|-------------|-----------------|
| **Ollama** (Primary) | REST API via `httpx` | All locally installed models (dynamic discovery via `/api/tags`) |
| **Anthropic** (Secondary) | `anthropic` SDK | Claude 3.5 Sonnet, Claude 3 Opus, Claude 3 Haiku (dynamic discovery) |

### 4.3 Database Technologies

| Database | Purpose | Configuration |
|----------|---------|---------------|
| **Neo4j 5.x** | Vector storage (PubMedBERT 768-dim), knowledge graph, clinical relationships | APOC + GDS plugins, cosine similarity |
| **SQLite** | User settings, EPIC credentials (encrypted), audit logs | AES-256 encrypted fields |
| **File System** | Word templates, generated documents, clinical guidelines | Structured directory hierarchy |

### 4.4 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18+ | Component-based UI framework |
| TypeScript | 5.3+ | Type-safe development |
| Tailwind CSS | 3.4+ | Utility-first styling |
| React Query | 5+ | Server state management, FHIR data caching |
| React Hook Form | 7+ | Calculator input forms |
| Zustand | 4+ | Client state management |
| Axios | 1.6+ | HTTP client for API calls |

### 4.5 RAG Pipeline

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangChain 0.1+ | RAG pipeline construction |
| Embeddings | PubMedBERT (`NeuML/pubmedbert-base-embeddings`) | Medical domain vectorization (768-dim) |
| Vector Search | Neo4j Vector Index | Cosine similarity search |
| Document Processing | `unstructured`, `PyMuPDF` | PDF/DOCX guideline parsing |
| Reranking | `sentence-transformers` CrossEncoder | Result relevance reranking |

### 4.6 Development and Testing

| Tool | Purpose |
|------|---------|
| pytest | Unit and integration testing |
| pytest-asyncio | Async test support |
| pytest-cov | Code coverage reporting |
| httpx (mock) | FHIR API mocking for tests |
| mypy | Static type checking |
| ruff | Python linting and formatting |
| Docker Compose | Local development environment |
| GitHub Actions | CI/CD pipeline |
