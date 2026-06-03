# EPIC-VAUCDA: EPIC FHIR Urology Clinical Documentation Assistant
# Program Design Document

**Version:** 1.0
**Date:** February 2, 2026
**Status:** Draft
**Document Type:** Program Design Document (PDD)
**Classification:** Internal Technical Documentation

---

## Document Control

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | 2026-02-02 | EPIC-VAUCDA Development Team | Initial program design document |

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Program Overview](#2-program-overview)
3. [Stakeholder Analysis](#3-stakeholder-analysis)
4. [Functional Requirements](#4-functional-requirements)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [System Architecture](#6-system-architecture)
7. [Technology Platform](#7-technology-platform)
8. [Data Architecture](#8-data-architecture)
9. [EPIC FHIR Integration Design](#9-epic-fhir-integration-design)
10. [LLM Integration Strategy](#10-llm-integration-strategy)
11. [Microsoft Word Output Design](#11-microsoft-word-output-design)
12. [Clinical Module Engine](#12-clinical-module-engine)
13. [User Interface Design](#13-user-interface-design)
14. [API Specification](#14-api-specification)
15. [Security and Compliance](#15-security-and-compliance)
16. [Deployment Architecture](#16-deployment-architecture)
17. [Testing Strategy](#17-testing-strategy)
18. [Risk Assessment](#18-risk-assessment)
19. [Appendices](#appendices)

---

## 1. Introduction

### 1.1 Purpose

This Program Design Document (PDD) defines the comprehensive technical and programmatic specifications for EPIC-VAUCDA (EPIC FHIR Urology Clinical Documentation Assistant). The document serves as the authoritative reference for all development, integration, and deployment activities. EPIC-VAUCDA extends the foundational VAUCDA architecture by replacing manual clinical data upload with automated data extraction via the EPIC FHIR R4 API, producing structured urology clinic notes in Microsoft Word format.

### 1.2 Scope

This document encompasses the complete program design including EPIC FHIR R4 integration via SMART on FHIR OAuth 2.0, automated clinical data extraction from EPIC EHR systems, AI-powered clinical note generation using Anthropic Claude and Ollama LLM providers with dynamic model discovery, 44 specialized urology clinical calculators, Microsoft Word document output via python-docx, zero-persistence PHI architecture for HIPAA compliance, and Neo4j-powered RAG pipeline for evidence-based clinical guidance.

### 1.3 Relationship to VAUCDA

EPIC-VAUCDA builds on the VAUCDA architecture with the following key modifications:

| Aspect | VAUCDA | EPIC-VAUCDA |
|--------|--------|-------------|
| Data Source | Manual file upload | EPIC FHIR R4 API |
| Authentication | JWT-based | OAuth 2.0 SMART on FHIR with PKCE |
| Output Format | Browser display | Microsoft Word (.docx) |
| LLM Providers | Ollama, Anthropic, OpenAI | Ollama, Anthropic (dynamic model loading) |
| Settings | Basic preferences | EPIC account credentials + LLM management |
| Lab Retrieval | Manual paste | Automated FHIR Observation queries |

### 1.4 Intended Audience

This document is intended for software architects and engineers responsible for EPIC FHIR integration and system implementation, clinical informaticists advising on EPIC EHR workflow integration, security officers validating OAuth 2.0 and HIPAA compliance requirements, project managers coordinating development activities, and VA/hospital technical leadership approving EPIC connectivity and system deployment.

### 1.5 Document Conventions

Technical specifications use standard notation: FHIR R4 resource schemas (JSON), OAuth 2.0 flows (RFC 6749/7636), API specifications (OpenAPI/YAML), database schemas (Cypher for Neo4j, SQL for SQLite), code examples (Python, TypeScript), and architecture diagrams (ASCII).

### 1.6 References

- VAUCDA Program Design Document v1.0 (November 2025)
- VAUCDA Software Design Document v1.0 (November 2025)
- HL7 FHIR R4 Specification (v4.0.1)
- SMART on FHIR Authorization Framework (v2.1)
- EPIC FHIR API Documentation (2025)
- OAuth 2.0 (RFC 6749) and PKCE Extension (RFC 7636)
- HIPAA Security Rule (45 CFR Part 164)
- AUA/NCCN Clinical Guidelines for Urology

---

## 2. Program Overview

### 2.1 Vision Statement

EPIC-VAUCDA aims to become the standard clinical documentation platform for urology services operating within EPIC EHR environments. By directly extracting clinical data from EPIC via FHIR R4 APIs, the system eliminates manual data entry, reduces documentation burden by 70%, and produces publication-quality Microsoft Word clinic notes. The system leverages dynamic LLM model loading from Anthropic and Ollama to provide optimal AI-assisted clinical reasoning.

### 2.2 Mission Statement

To provide urologists with an intelligent documentation assistant that automatically extracts clinical data from EPIC EHR systems via FHIR R4 APIs, transforms it into high-quality structured notes in Microsoft Word format, and offers evidence-based clinical decision support through integrated calculators and RAG-powered knowledge retrieval, while maintaining strict HIPAA compliance through zero-persistence PHI architecture.

### 2.3 Program Objectives

The primary objectives include:

1. **Automated EPIC Data Extraction**: Connect to EPIC FHIR R4 endpoints to retrieve all clinical data including labs, imaging, clinic notes, procedure notes, and pathology reports.
2. **Intelligent Lab Retrieval**: Retrieve all labs from the last 6 months plus targeted urology-specific labs (Litholink, Stone labs, PSA, testosterone, estrogen, LH, FSH, PTH, AFP, HCG, LDH, UA, Urine culture) regardless of date range.
3. **AI-Powered Note Generation**: Use Anthropic Claude and Ollama models with dynamic model discovery to extract clinical components and generate structured notes.
4. **Microsoft Word Output**: Generate formatted, downloadable clinic notes in .docx format using professional medical document templates.
5. **Clinical Decision Support**: Integrate 44 specialized urology calculators that automatically populate from FHIR-extracted data.
6. **Dynamic LLM Management**: Support runtime discovery and selection of available models from both Anthropic and Ollama providers.
7. **HIPAA-Compliant Architecture**: Maintain zero-persistence PHI with OAuth 2.0 SMART on FHIR authentication.

### 2.4 Key Capabilities

#### 2.4.1 EPIC FHIR Data Extraction

The system connects to EPIC FHIR R4 endpoints using OAuth 2.0 SMART on FHIR authorization. Data extraction includes:

| FHIR Resource | Clinical Data | Extraction Strategy |
|---------------|---------------|---------------------|
| Patient | Demographics, identifiers | Single query per encounter |
| Observation | Labs, vitals, IPSS scores | Date-filtered + LOINC-targeted |
| DiagnosticReport | Pathology, imaging reports | Category-filtered |
| DocumentReference | Clinic notes, procedure notes | Type-filtered for urology |
| Condition | Active diagnoses, problem list | Active status filter |
| MedicationStatement | Current medications | Active status filter |
| AllergyIntolerance | Drug/food allergies | All active entries |
| Procedure | Surgical history | Date-ordered |
| FamilyMemberHistory | Family cancer history | All entries |
| Encounter | Visit history | Date-range filtered |
| ServiceRequest | Pending orders, referrals | Active status filter |
| CarePlan | Treatment plans | Active status filter |

#### 2.4.2 Intelligent Lab Retrieval Strategy

The lab retrieval system operates on a dual-strategy approach:

**Strategy 1 - Temporal Window**: Retrieve ALL Observation resources with category `laboratory` from the last 6 months.

**Strategy 2 - Targeted Urology Labs**: Query specific LOINC codes regardless of date range to capture the complete urology lab history:

| Lab Panel | LOINC Codes | Clinical Significance |
|-----------|-------------|----------------------|
| PSA | 2857-1 (Total PSA), 10886-0 (Free PSA), 12841-3 (Free/Total %) | Prostate cancer screening/monitoring |
| Testosterone | 2986-8 (Total), 2991-8 (Free), 49041-6 (Bioavailable) | Hypogonadism evaluation |
| Estradiol | 2243-4 | Endocrine evaluation |
| LH | 10501-5 | Gonadotropin assessment |
| FSH | 15067-2 | Gonadotropin assessment |
| PTH | 2731-8 (Intact) | Stone disease evaluation |
| AFP | 1834-1 | Testicular cancer marker |
| HCG | 21198-7 (Beta-HCG) | Testicular cancer marker |
| LDH | 2532-0 | Testicular cancer marker |
| Urinalysis | 5794-3 (Microscopic), 24356-8 (Panel) | Hematuria/UTI evaluation |
| Urine Culture | 630-4 | Infection assessment |
| Litholink Panel | 57362-1 (24-hr Urine), 49054-9 (Oxalate), 2881-1 (Citrate), 21482-5 (Calcium 24h) | Stone metabolic evaluation |
| Stone Labs | 2777-1 (Uric acid), 2160-0 (Creatinine), 2075-0 (Chloride), 2947-0 (Sodium), 6298-4 (Potassium) | Metabolic stone evaluation |
| Vitamin D | 1989-3 (25-OH D2+D3) | Calcium metabolism |
| CBC | 58410-2 (CBC panel) | General screening |
| BMP/CMP | 51990-0 (BMP), 24323-8 (CMP) | Renal function, electrolytes |

#### 2.4.3 AI-Powered Clinical Note Generation

The note generation pipeline operates in five stages:

```
Stage 1: FHIR Data Extraction
  EPIC FHIR R4 API → Patient data, labs, notes, imaging, pathology

Stage 2: Component Extraction (AI Agents)
  Raw FHIR data → Structured clinical components
  - HPI Agent: History of present illness synthesis
  - Lab Agent: Lab result organization and trending
  - Imaging Agent: Imaging report summarization
  - Pathology Agent: Pathology report extraction
  - Assessment Agent: Clinical assessment generation
  - Plan Agent: Treatment plan formulation
  - PSA Agent: PSA curve construction
  - IPSS Agent: IPSS score extraction

Stage 3: Document-Level Extraction
  Full clinical document → Allergies, medications, PMH, PSH, social/family history

Stage 4: Section Synthesis (AI Agents)
  Multiple data sources → Unified section content per note section

Stage 5: Word Document Assembly
  Synthesized sections → Formatted Microsoft Word document (.docx)
```

#### 2.4.4 Clinical Decision Support

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

#### 2.4.5 Evidence-Based Guidance

The RAG pipeline provides context-aware retrieval from AUA Guidelines, NCCN Clinical Practice Guidelines, EAU Guidelines, and peer-reviewed urologic literature stored in the Neo4j knowledge graph.

### 2.5 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Documentation time reduction | 70% or greater | Time comparison study |
| Note completion rate | 95% same-day completion | Completion tracking |
| User satisfaction | 4.0+ on 5-point scale | Provider surveys |
| System availability | 99.5% during operational hours | Uptime monitoring |
| Note generation latency | < 3 seconds (standard) | Performance monitoring |
| FHIR data extraction latency | < 5 seconds (full patient) | Performance monitoring |
| Word document generation | < 2 seconds | Performance monitoring |
| Calculator accuracy | 100% mathematical accuracy | Validation testing |
| EPIC connectivity uptime | 99.9% | Connection monitoring |

---

## 3. Stakeholder Analysis

### 3.1 Primary Stakeholders

#### 3.1.1 Urologists (End Users)

Attending physicians, residents, and fellows in urology who require automated clinical data extraction from EPIC eliminating manual copy-paste workflows, structured note generation in Microsoft Word format compatible with institutional documentation standards, clinical decision support calculators pre-populated with FHIR-extracted data, and evidence-based guidance from AUA/NCCN guidelines.

#### 3.1.2 Patients (Beneficiaries)

Patients receiving urologic care benefit through improved documentation accuracy from automated data extraction, reduced provider time spent on documentation increasing face-time, consistent application of evidence-based guidelines in treatment planning, and comprehensive lab trending that catches clinically significant changes.

#### 3.1.3 Health IT Administration

Technical stakeholders responsible for EPIC EHR integration and system compliance require SMART on FHIR compliant OAuth 2.0 authentication, proper EPIC App Orchard registration and approval, HIPAA-compliant zero-persistence PHI architecture, and audit capabilities for all FHIR data access.

#### 3.1.4 Institutional Leadership

Administrative stakeholders require operational efficiency improvements and ROI metrics, EPIC integration compliance with institutional policies, scalability to additional specialties and facilities, and cost-effectiveness of AI-assisted documentation.

### 3.2 Stakeholder Requirements Matrix

| Stakeholder | Primary Need | Key Requirement | Success Indicator |
|-------------|--------------|-----------------|-------------------|
| Urologists | Efficiency | Automated EPIC data extraction | < 5 second data fetch |
| Urologists | Accuracy | Reliable clinical calculators | 100% calculation accuracy |
| Urologists | Output | Professional Word documents | DOCX download < 2 seconds |
| Health IT | Security | SMART on FHIR compliance | Clean EPIC audit reports |
| Health IT | Integration | EPIC App Orchard approval | Successful deployment |
| Patients | Quality | Accurate documentation | Reduced errors |
| Leadership | ROI | Measurable improvements | Productivity metrics |

---

## 4. Functional Requirements

### 4.1 EPIC FHIR Data Extraction Requirements

#### FR-FHIR-001: SMART on FHIR Authentication

The system shall implement OAuth 2.0 Authorization Code flow with PKCE (RFC 7636) for user-facing EPIC authentication. The system shall support the following SMART on FHIR scopes:

```
launch/patient
patient/Patient.read
patient/Observation.read
patient/Condition.read
patient/Procedure.read
patient/MedicationStatement.read
patient/AllergyIntolerance.read
patient/DiagnosticReport.read
patient/DocumentReference.read
patient/FamilyMemberHistory.read
patient/Encounter.read
patient/ServiceRequest.read
patient/CarePlan.read
```

#### FR-FHIR-002: Patient Context Launch

The system shall support EPIC EHR launch context where the patient context is provided by the EHR. The system shall also support standalone launch where the user searches for and selects a patient. Patient context shall be maintained for the duration of the session.

#### FR-FHIR-003: Lab Result Retrieval

The system shall retrieve all laboratory Observation resources from the last 6 months using the `date` search parameter. Additionally, the system shall retrieve all urology-specific labs (as defined in Section 2.4.2) using LOINC code queries regardless of date range. Lab results shall be organized by category (endocrine, stone, general) and presented in reverse chronological order.

#### FR-FHIR-004: Clinical Note Retrieval

The system shall retrieve DocumentReference resources filtered for urology clinic notes and urology procedure notes. The system shall extract the document content (either inline or via URL reference) and make it available for AI-powered component extraction.

#### FR-FHIR-005: Imaging Report Retrieval

The system shall retrieve DiagnosticReport resources with category `imaging` relevant to urologic conditions. Reports shall include the full narrative text for AI summarization.

#### FR-FHIR-006: Pathology Report Retrieval

The system shall retrieve DiagnosticReport resources with category `pathology` for urologic specimens. The system shall preserve specimen-level detail including anatomical locations, grades, Gleason scores, and percentages.

#### FR-FHIR-007: Medication and Allergy Retrieval

The system shall retrieve active MedicationStatement resources and all AllergyIntolerance resources for the patient. Medications shall be organized by category and allergies shall identify NKA (No Known Allergies) patterns.

#### FR-FHIR-008: Problem List and History

The system shall retrieve active Condition resources for the problem list, Procedure resources for surgical history, and FamilyMemberHistory resources for family history. These shall be integrated into the appropriate note sections.

### 4.2 Note Generation Requirements

#### FR-NG-001: AI-Powered Component Extraction

The system shall use LLM-powered extraction agents to parse FHIR-retrieved clinical data into structured note components. Agents include HPI extraction, lab organization, imaging summarization, pathology extraction, assessment generation, plan formulation, PSA curve construction, and IPSS score extraction. Each agent shall follow the same extraction patterns used in VAUCDA.

#### FR-NG-002: Template-Based Output

The system shall generate notes conforming to the standard urology clinic note template including: CC, HPI, IPSS table, Dietary History, Social History, Family History, Sexual History, PMH, PSH, PSA Curve, Testosterone Curve, Pathology Results, Medications, Allergies, Endocrine Labs, Stone Labs, General Labs, Imaging, ROS, PE, Assessment, Problem List, and Plan.

#### FR-NG-003: Microsoft Word Output

The system shall generate formatted Microsoft Word documents (.docx) using the python-docx library. Documents shall include proper medical document formatting with headers, tables (IPSS, PSA Curve), section breaks, and professional typography. The generated document shall be available for immediate download.

#### FR-NG-004: LLM Provider Selection with Dynamic Model Loading

Users shall be able to select from available LLM providers: Ollama (local) and Anthropic Claude. The system shall dynamically discover and present available models from each provider at runtime:

- **Ollama**: Query `/api/tags` endpoint to enumerate locally installed models
- **Anthropic**: Query available models via the Anthropic API

The system shall support model switching without session interruption.

#### FR-NG-005: Module Integration

Generated notes shall automatically incorporate results from selected clinical calculators, displaying calculator outputs in the appropriate note sections with proper formatting.

### 4.3 EPIC Settings and Account Management

#### FR-SET-001: EPIC Account Configuration

The system shall provide a dedicated settings page where users can configure EPIC FHIR connection parameters including:

- EPIC FHIR base URL (e.g., `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4`)
- Client ID (from EPIC App Orchard registration)
- Redirect URI for OAuth callback
- SMART on FHIR scopes

#### FR-SET-002: EPIC Credential Management

The system shall securely store EPIC OAuth 2.0 client credentials using encrypted storage. Access tokens and refresh tokens shall be managed in memory only and never persisted to disk. The settings page shall display connection status and last successful authentication time.

#### FR-SET-003: LLM Provider Configuration

The settings page shall allow users to configure:

- Ollama server host and port
- Anthropic API key (encrypted storage)
- Default model preferences per task type
- Temperature and generation parameters
- Model pull/download management for Ollama

#### FR-SET-004: Dynamic Model Discovery

The system shall periodically poll configured LLM providers to discover available models. The model selection dropdown shall reflect real-time availability, showing model name, size, and last modified timestamp for Ollama models, and model tier and capabilities for Anthropic models.

### 4.4 Clinical Calculator Requirements

#### FR-CC-001: Calculator Accuracy

All calculators shall implement peer-reviewed algorithms with 100% mathematical accuracy. Each calculator shall include reference citations and version tracking.

#### FR-CC-002: FHIR-Populated Inputs

The system shall offer automatic population of calculator inputs from FHIR-extracted data. When a patient's labs are retrieved via FHIR, relevant calculator inputs shall be pre-filled with the most recent values. Users shall confirm auto-populated values before calculation.

#### FR-CC-003: Result Interpretation

Calculator results shall include numerical scores, risk category assignments, interpretive text, and evidence-based recommendations where applicable. Results shall be formatted for inclusion in the generated Word document.

### 4.5 Evidence Search Requirements

#### FR-ES-001: RAG-Powered Search

The system shall provide semantic search across the clinical knowledge base using vector similarity in Neo4j. Search shall return relevant guideline excerpts, reference materials, and calculator documentation.

#### FR-ES-002: Source Attribution

All retrieved content shall include source attribution with document title, guideline organization, publication date, and direct links where available.

#### FR-ES-003: Category Filtering

Users shall be able to filter evidence searches by clinical category, guideline source (AUA, NCCN, EAU), and publication date range.

---

## 5. Non-Functional Requirements

### 5.1 Performance

| Operation | Target Latency | Notes |
|-----------|---------------|-------|
| EPIC FHIR patient data extraction | < 5 seconds | Full patient context |
| FHIR lab retrieval (6 months + targeted) | < 3 seconds | Parallel LOINC queries |
| Note generation (standard complexity) | < 3 seconds | Single-stage processing |
| Note generation (complex multi-system) | < 10 seconds | Multi-stage with RAG |
| Word document generation | < 2 seconds | Template rendering |
| Calculator results | < 500 milliseconds | Per calculation |
| Dynamic model discovery | < 2 seconds | Provider polling |
| Concurrent users | 500 | Across facilities |

### 5.2 Availability

System uptime shall be 99.5% during operational hours (6 AM - 10 PM local time). EPIC FHIR connectivity shall be monitored with automatic reconnection on failure. Planned maintenance windows shall be communicated 72 hours in advance.

### 5.3 Accessibility

The interface shall comply with WCAG 2.1 AA standards for all clinical interface elements, ensuring accessibility for users with disabilities. Generated Word documents shall include proper heading structure, alt text for tables, and accessible formatting.

### 5.4 Scalability

Architecture shall support horizontal scaling to accommodate growth across medical centers and facilities without degradation of performance metrics. FHIR connection pooling shall handle concurrent patient data requests.

### 5.5 Interoperability

The system shall comply with HL7 FHIR R4 specification for all EHR interactions. The system shall support EPIC FHIR R4 API endpoints and be adaptable to other FHIR-compliant EHR systems with minimal configuration changes.

---

## 6. System Architecture

### 6.1 Architectural Principles

The system follows a layered architecture with clear separation of concerns. The EPIC FHIR integration layer replaces manual file upload with automated data extraction. The AI processing layer transforms raw FHIR data into structured clinical components. The document generation layer produces formatted Microsoft Word output.

### 6.2 High-Level Architecture Diagram

```
+-----------------------------------------------------------------------------+
|                              PRESENTATION LAYER                              |
|  +-----------------------------------------------------------------------+  |
|  |                    Web Interface (React 18+)                           |  |
|  |              Tailwind CSS 3.4+ / TypeScript                            |  |
|  |  +-------------------+  +-------------------+  +-------------------+  |  |
|  |  | Note Generation   |  | EPIC Settings     |  | Evidence Search  |  |  |
|  |  | (Patient context, |  | (Credentials,     |  | (RAG-powered     |  |  |
|  |  |  LLM selection,   |  |  connection mgmt, |  |  clinical search) |  |  |
|  |  |  Word download)   |  |  model config)    |  |                   |  |  |
|  |  +-------------------+  +-------------------+  +-------------------+  |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
|                              APPLICATION LAYER                               |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  FastAPI        |  |  Note           |  |  Clinical Module Engine   |     |
|  |  Backend        |  |  Generator      |  |  (44 Calculators)         |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  EPIC FHIR      |  |  Word Document  |  |  Template Manager         |     |
|  |  Client          |  |  Generator      |  |  (Note templates)         |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Settings        |  |  LLM Model      |  |  Document Processor       |     |
|  |  Manager          |  |  Discovery      |  |  (FHIR Resource Parser)   |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                         EPIC FHIR INTEGRATION LAYER                          |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  OAuth 2.0      |  |  FHIR R4        |  |  Resource Extractors      |     |
|  |  SMART on FHIR  |  |  Client          |  |  (Labs, Notes, Imaging,   |     |
|  |  with PKCE      |  |  (httpx async)   |  |   Pathology, Meds, Hx)    |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                         AI PROCESSING LAYER                                  |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Extraction      |  |  Synthesis      |  |  RAG Pipeline             |     |
|  |  Agents          |  |  Agents          |  |  (LangChain + Neo4j)      |     |
|  |  (HPI, Labs,     |  |  (Assessment,   |  |                           |     |
|  |   Imaging,       |  |   Plan, PSA,    |  |  Vector Search + Context  |     |
|  |   Pathology)     |  |   IPSS)          |  |  Augmented Generation     |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                              LLM LAYER                                       |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Ollama          |  |  Anthropic      |  |  Dynamic Model            |     |
|  |  Client          |  |  Client          |  |  Discovery Registry       |     |
|  |  (Local, GPU)    |  |  (API)           |  |  (Runtime enumeration)    |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
|                              DATA LAYER                                      |
|  +-----------------+  +-----------------+  +---------------------------+     |
|  |  Neo4j 5.x      |  |  SQLite          |  |  File Storage             |     |
|  |  Vector + KG    |  |  Settings DB    |  |  (Templates, Exports)     |     |
|  |  (768-dim)      |  |  (Encrypted)    |  |                           |     |
|  +-----------------+  +-----------------+  +---------------------------+     |
+-----------------------------------------------------------------------------+
```

### 6.3 Component Interaction Flow

The standard note generation workflow:

```
1. User authenticates via EPIC OAuth 2.0 SMART on FHIR
                    |
2. Patient context established (EHR launch or standalone search)
                    |
3. FHIR Client retrieves patient data in parallel:
   +-- Labs (6-month window + LOINC-targeted urology labs)
   +-- Clinic notes (DocumentReference, urology-filtered)
   +-- Imaging reports (DiagnosticReport, imaging category)
   +-- Pathology reports (DiagnosticReport, pathology category)
   +-- Medications (MedicationStatement, active)
   +-- Allergies (AllergyIntolerance, all)
   +-- Conditions (active problem list)
   +-- Procedures (surgical history)
   +-- Family history (FamilyMemberHistory)
                    |
4. AI Extraction Agents process each data category:
   HPI Agent --> History of present illness
   Lab Agent --> Organized lab tables
   Imaging Agent --> Imaging summaries
   Pathology Agent --> Pathology results with specimen detail
   PSA Agent --> PSA curve (reverse chronological)
   IPSS Agent --> IPSS score table
                    |
5. Document-Level Extraction:
   Full document --> Allergies, medications, PMH, PSH, social/family history
                    |
6. Synthesis Agents combine multiple sources per section
                    |
7. RAG Pipeline provides evidence-based context for assessment/plan
                    |
8. Word Document Generator assembles all sections into .docx
                    |
9. User downloads formatted Microsoft Word document
```

### 6.4 FHIR Data Flow Architecture

```
+------------------+          +------------------+          +------------------+
|  EPIC EHR        |          |  EPIC-VAUCDA     |          |  LLM Providers   |
|  (FHIR R4 API)   |          |  Backend          |          |                  |
+------------------+          +------------------+          +------------------+
       |                              |                              |
       | 1. OAuth 2.0 PKCE            |                              |
       |<-----------------------------|                              |
       |                              |                              |
       | 2. Authorization Code        |                              |
       |----------------------------->|                              |
       |                              |                              |
       | 3. Access Token              |                              |
       |<-----------------------------|                              |
       |                              |                              |
       | 4. FHIR Resource Queries     |                              |
       |  GET /Patient/{id}           |                              |
       |  GET /Observation?patient=&  |                              |
       |      code=2857-1&            |                              |
       |      date=ge2025-08-02       |                              |
       |  GET /DiagnosticReport?      |                              |
       |      patient=&category=LAB   |                              |
       |  GET /DocumentReference?     |                              |
       |      patient=&type=urology   |                              |
       |<-----------------------------|                              |
       |                              |                              |
       | 5. FHIR Bundle Responses     |                              |
       |----------------------------->|                              |
       |                              |                              |
       |                              | 6. AI Extraction             |
       |                              |----------------------------->|
       |                              |                              |
       |                              | 7. Structured Components     |
       |                              |<-----------------------------|
       |                              |                              |
       |                              | 8. Generate Word Document    |
       |                              |                              |
       |                              | 9. Return .docx to User      |
       |                              |                              |
```

---

## 7. Technology Platform

### 7.1 Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Web Framework | FastAPI | 0.109+ | Async REST API, WebSocket support |
| Python Runtime | Python | 3.11+ | Core application logic |
| ASGI Server | Uvicorn | 0.27+ | Production async server |
| Task Queue | Celery | 5.3+ | Background FHIR extraction and LLM calls |
| Message Broker | Redis | 7.2+ | Task queue backend, token caching |
| HTTP Client | httpx | 0.27+ | Async FHIR API requests |
| Word Generation | python-docx | 1.1+ | Microsoft Word document creation |
| OAuth 2.0 | authlib | 1.3+ | SMART on FHIR authentication |

### 7.2 LLM Integration Stack

| Provider | Integration Method | Model Discovery | Primary Use Case |
|----------|-------------------|-----------------|------------------|
| **Ollama** (Local) | REST API via `ollama-python` | GET `/api/tags` for model enumeration | All clinical tasks (privacy-first) |
| **Anthropic** | `anthropic` SDK | API model listing | Complex reasoning, note synthesis |

**Dynamic Model Loading**: Both providers support runtime model discovery. The system polls provider endpoints on startup and periodically to maintain an up-to-date model registry. Users select from discovered models in the UI.

### 7.3 EPIC FHIR Integration

| Component | Technology | Purpose |
|-----------|------------|---------|
| FHIR Client | httpx + custom FHIR wrapper | Async FHIR R4 resource queries |
| OAuth 2.0 | authlib / custom PKCE | SMART on FHIR authorization |
| FHIR Parser | fhir.resources | FHIR R4 resource validation/parsing |
| LOINC Lookup | Local LOINC code registry | Lab identification and categorization |

### 7.4 Database Technologies

| Database | Purpose | Configuration |
|----------|---------|---------------|
| Neo4j 5.x | Vector storage, knowledge graph, clinical relationships | APOC, GDS plugins enabled |
| SQLite | User settings, EPIC credentials (encrypted), session metadata | Local file-based, AES-256 encryption for credentials |
| File System | Templates, exports, generated Word documents | Structured directory hierarchy |

### 7.5 Frontend Technologies

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18+ | Component-based UI framework |
| TypeScript | 5.0+ | Type-safe frontend development |
| Tailwind CSS | 3.4+ | Utility-first styling |
| React Query | 5+ | Server state management, FHIR data caching |

### 7.6 RAG Pipeline Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangChain 0.1+ | RAG pipeline construction |
| Embeddings | sentence-transformers (NeuML/pubmedbert-base-embeddings) | Medical document vectorization (768-dim) |
| Vector Search | Neo4j Vector Index | Cosine similarity search |
| Document Processing | unstructured, PyMuPDF | Guideline PDF parsing |

---

## 8. Data Architecture

### 8.1 Neo4j Graph Schema

#### 8.1.1 Node Types

The knowledge graph contains the same node types as VAUCDA:

**Document nodes** store clinical knowledge resources with properties: id (STRING), title (STRING), source (STRING), content (STRING), embedding (LIST of FLOAT, 768 dimensions), created_at (DATETIME), document_type (STRING: guideline, reference, calculator).

**ClinicalConcept nodes** represent medical concepts with properties: id (STRING), name (STRING), category (STRING), description (STRING), icd10_codes (LIST of STRING), snomed_codes (LIST of STRING).

**Calculator nodes** define clinical calculators with properties: id (STRING), name (STRING), category (STRING), formula (STRING), inputs (LIST of STRING), interpretation (STRING), references (LIST of STRING).

**Template nodes** store note templates with properties: id (STRING), name (STRING), type (STRING: clinic_note, consult, preop, postop), content (STRING), sections (LIST of STRING), active (BOOLEAN).

**User nodes** contain user information with properties: id (STRING), username (STRING), preferences (MAP), epic_config (MAP with encrypted values), created_at (DATETIME).

#### 8.1.2 LOINC Code Registry

A dedicated LOINC code registry maps laboratory tests to categories:

```cypher
(:LOINCCode {
    code: STRING,           // e.g., "2857-1"
    display: STRING,        // e.g., "Prostate specific Ag [Mass/volume] in Serum or Plasma"
    category: STRING,       // e.g., "endocrine", "stone", "general", "tumor_marker"
    urology_panel: STRING,  // e.g., "PSA", "Litholink", "Stone", "Testosterone"
    unit: STRING,           // e.g., "ng/mL"
    reference_range: STRING // e.g., "0.0-4.0"
})

(:LOINCCode)-[:BELONGS_TO_PANEL]->(:LabPanel {
    name: STRING,           // e.g., "Litholink Panel"
    description: STRING,
    clinical_use: STRING
})
```

#### 8.1.3 Vector Index Configuration

```cypher
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

CREATE FULLTEXT INDEX document_content IF NOT EXISTS
FOR (d:Document) ON EACH [d.content, d.title];

CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];

CREATE FULLTEXT INDEX loinc_search IF NOT EXISTS
FOR (l:LOINCCode) ON EACH [l.code, l.display];
```

### 8.2 SQLite Schema (Settings Database)

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- EPIC FHIR Configuration (Encrypted)
CREATE TABLE epic_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    fhir_base_url TEXT NOT NULL,
    client_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    scopes TEXT NOT NULL,
    -- Encrypted fields (AES-256-GCM)
    client_secret_encrypted BLOB,
    encryption_iv BLOB,
    encryption_tag BLOB,
    -- Connection status
    last_connected_at TIMESTAMP,
    connection_status TEXT DEFAULT 'disconnected',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_preferences(user_id)
);

-- LLM Provider Configuration
CREATE TABLE llm_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,            -- 'ollama' or 'anthropic'
    host TEXT,                         -- Ollama host URL
    api_key_encrypted BLOB,            -- Anthropic API key (encrypted)
    encryption_iv BLOB,
    encryption_tag BLOB,
    default_model TEXT,
    temperature REAL DEFAULT 0.3,
    max_tokens INTEGER DEFAULT 4096,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_preferences(user_id),
    UNIQUE(user_id, provider)
);

-- Session Audit Log (Metadata Only - No PHI)
CREATE TABLE session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    fhir_resources_accessed TEXT,       -- JSON list of resource types
    fhir_query_count INTEGER,
    module_used TEXT,
    llm_provider TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    duration_ms INTEGER,
    word_doc_generated BOOLEAN DEFAULT FALSE,
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

-- Discovered Models Cache
CREATE TABLE model_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_size TEXT,
    model_family TEXT,
    context_length INTEGER,
    capabilities JSON,
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, model_name)
);
```

### 8.3 File Storage Structure

```
/epic-vaucda/
+-- data/
|   +-- documents/
|   |   +-- guidelines/
|   |   |   +-- nccn/           # NCCN guidelines
|   |   |   +-- aua/            # AUA guidelines
|   |   |   +-- eau/            # EAU guidelines
|   |   +-- references/         # Peer-reviewed literature
|   |   +-- calculators/        # Calculator documentation
|   +-- templates/
|   |   +-- word/               # Word document templates (.docx)
|   |   +-- clinic_notes/       # Note section templates
|   |   +-- consult_notes/
|   |   +-- preop_notes/
|   |   +-- postop_notes/
|   +-- exports/                # Generated Word documents (ephemeral)
|   +-- loinc/                  # LOINC code registry data
+-- models/
|   +-- embeddings/             # Local embedding models
+-- logs/                       # Application logs (no PHI)
+-- config/                     # Configuration files
```

---

## 9. EPIC FHIR Integration Design

### 9.1 SMART on FHIR Authorization Flow

The system implements the SMART on FHIR Authorization Code flow with PKCE for secure EHR access:

```
+----------+          +----------+          +----------+          +----------+
|  Browser |          |  EPIC-   |          |  EPIC    |          |  EPIC    |
|  (User)  |          |  VAUCDA  |          |  Auth    |          |  FHIR    |
|          |          |  Backend |          |  Server  |          |  Server  |
+----------+          +----------+          +----------+          +----------+
     |                     |                     |                     |
     | 1. Click "Connect   |                     |                     |
     |    to EPIC"         |                     |                     |
     |------------------->|                     |                     |
     |                     |                     |                     |
     |                     | 2. Generate PKCE    |                     |
     |                     |    code_verifier    |                     |
     |                     |    + code_challenge  |                     |
     |                     |                     |                     |
     | 3. Redirect to EPIC |                     |                     |
     |    /authorize?       |                     |                     |
     |    response_type=    |                     |                     |
     |    code&client_id=   |                     |                     |
     |    &redirect_uri=    |                     |                     |
     |    &scope=launch/    |                     |                     |
     |    patient+patient/* |                     |                     |
     |    &code_challenge=  |                     |                     |
     |    &code_challenge_  |                     |                     |
     |    method=S256       |                     |                     |
     |-------------------------------------------------->|            |
     |                     |                     |                     |
     |                     |    4. User logs in  |                     |
     |                     |       and consents  |                     |
     |                     |                     |                     |
     | 5. Redirect back    |                     |                     |
     |    with auth code   |                     |                     |
     |<--------------------------------------------------|            |
     |                     |                     |                     |
     | 6. Forward code     |                     |                     |
     |------------------->|                     |                     |
     |                     |                     |                     |
     |                     | 7. POST /token       |                     |
     |                     |    grant_type=       |                     |
     |                     |    authorization_    |                     |
     |                     |    code&code=        |                     |
     |                     |    &code_verifier=   |                     |
     |                     |-------------------------->|              |
     |                     |                     |                     |
     |                     | 8. Access Token +    |                     |
     |                     |    Patient Context   |                     |
     |                     |<--------------------------|              |
     |                     |                     |                     |
     |                     | 9. FHIR Queries      |                     |
     |                     |    with Bearer token  |                     |
     |                     |----------------------------------------------->|
     |                     |                     |                     |
     |                     | 10. FHIR Bundles     |                     |
     |                     |<-----------------------------------------------|
     |                     |                     |                     |
```

### 9.2 FHIR Resource Query Design

#### 9.2.1 Lab Retrieval Queries

**All Labs (6-month window)**:
```
GET /Observation?patient={id}&category=laboratory&date=ge{6_months_ago}&_count=1000&_sort=-date
```

**Targeted Urology Labs (all time)**:
```
GET /Observation?patient={id}&code=2857-1,10886-0,12841-3&_sort=-date
GET /Observation?patient={id}&code=2986-8,2991-8,49041-6&_sort=-date
GET /Observation?patient={id}&code=2243-4,10501-5,15067-2&_sort=-date
GET /Observation?patient={id}&code=2731-8,1834-1,21198-7,2532-0&_sort=-date
GET /Observation?patient={id}&code=5794-3,24356-8,630-4&_sort=-date
GET /Observation?patient={id}&code=57362-1,49054-9,2881-1,21482-5&_sort=-date
GET /Observation?patient={id}&code=2777-1,2160-0,2075-0,2947-0,6298-4&_sort=-date
```

#### 9.2.2 Clinical Note Retrieval

```
GET /DocumentReference?patient={id}&type=http://loinc.org|11506-3&_sort=-date&_count=50
GET /DocumentReference?patient={id}&type=http://loinc.org|28570-0&_sort=-date&_count=50
```

(11506-3 = Progress note, 28570-0 = Procedure note, filtered by urology department/practitioner)

#### 9.2.3 Imaging and Pathology

```
GET /DiagnosticReport?patient={id}&category=imaging&_sort=-date&_count=100
GET /DiagnosticReport?patient={id}&category=pathology&_sort=-date&_count=50
```

#### 9.2.4 Medications, Allergies, Conditions

```
GET /MedicationStatement?patient={id}&status=active
GET /AllergyIntolerance?patient={id}
GET /Condition?patient={id}&clinical-status=active
GET /Procedure?patient={id}&_sort=-date
GET /FamilyMemberHistory?patient={id}
```

### 9.3 FHIR Resource to Note Section Mapping

| Note Section | FHIR Resources | Extraction Method |
|-------------|----------------|-------------------|
| CC | Encounter.reasonCode, Condition | AI extraction from visit reason |
| HPI | DocumentReference (clinic notes), Condition | AI synthesis from prior notes |
| IPSS | Observation (LOINC: 72149-5) | Direct value extraction |
| Dietary History | DocumentReference (social history) | AI extraction |
| Social History | DocumentReference, Observation (smoking) | AI extraction + structured data |
| Family History | FamilyMemberHistory | Direct resource parsing |
| Sexual History | DocumentReference | AI extraction from notes |
| PMH | Condition (all) | Direct resource parsing |
| PSH | Procedure | Direct resource parsing |
| PSA Curve | Observation (LOINC: 2857-1) | Date-sorted value extraction |
| Testosterone Curve | Observation (LOINC: 2986-8) | Date-sorted value extraction |
| Pathology | DiagnosticReport (pathology) | AI extraction preserving detail |
| Medications | MedicationStatement | Direct resource parsing |
| Allergies | AllergyIntolerance | Direct resource parsing |
| Endocrine Labs | Observation (endocrine LOINCs) | Categorized value extraction |
| Stone Labs | Observation (stone LOINCs) | Categorized value extraction |
| General Labs | Observation (general LOINCs) | Categorized value extraction |
| Imaging | DiagnosticReport (imaging) | AI summarization |
| ROS | DocumentReference | AI extraction + default template |
| PE | DocumentReference | AI extraction + default template |
| Assessment | All resources + RAG context | AI synthesis |
| Problem List | Condition (active) | Direct + AI synthesis |
| Plan | DocumentReference, CarePlan | AI synthesis |

### 9.4 EPIC App Orchard Registration

The system requires registration with EPIC App Orchard for production access:

| Registration Field | Value |
|--------------------|-------|
| Application Name | EPIC-VAUCDA Urology Documentation Assistant |
| Application Type | Patient-facing or Provider-facing Web Application |
| FHIR Version | R4 |
| Authorization | Authorization Code with PKCE |
| Requested Scopes | launch/patient, patient/*.read |
| Redirect URI | https://{deployment_host}/auth/callback |
| Privacy Policy | Required URL |
| Terms of Use | Required URL |

---

## 10. LLM Integration Strategy

### 10.1 Provider Abstraction Layer

The system implements a provider-agnostic abstraction supporting Ollama and Anthropic with dynamic model discovery:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, List, Dict

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

    @abstractmethod
    async def discover_models(self) -> List[Dict]:
        """Discover available models from the provider."""
        pass
```

### 10.2 Dynamic Model Discovery

#### 10.2.1 Ollama Model Discovery

The system queries Ollama's `/api/tags` endpoint to enumerate locally installed models:

```python
async def discover_ollama_models(host: str) -> List[Dict]:
    """Discover available Ollama models."""
    async with httpx.AsyncClient(base_url=host) as client:
        response = await client.get("/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        return [
            {
                "provider": "ollama",
                "name": m["name"],
                "size": m.get("size"),
                "modified_at": m.get("modified_at"),
                "family": m.get("details", {}).get("family"),
                "parameter_size": m.get("details", {}).get("parameter_size"),
                "quantization": m.get("details", {}).get("quantization_level"),
            }
            for m in models
        ]
```

#### 10.2.2 Anthropic Model Discovery

The system queries available Anthropic models:

```python
async def discover_anthropic_models(api_key: str) -> List[Dict]:
    """Discover available Anthropic models."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    models = await client.models.list()
    return [
        {
            "provider": "anthropic",
            "name": m.id,
            "display_name": m.display_name,
            "created_at": m.created_at,
        }
        for m in models.data
    ]
```

#### 10.2.3 Model Registry

The system maintains a unified model registry that is refreshed periodically:

```python
class ModelRegistry:
    """Unified registry of available models across all providers."""

    def __init__(self):
        self._models: Dict[str, List[Dict]] = {}
        self._last_refresh: Optional[datetime] = None
        self._refresh_interval = timedelta(minutes=5)

    async def refresh(self, providers: Dict[str, LLMProvider]):
        """Refresh model inventory from all providers."""
        for name, provider in providers.items():
            try:
                self._models[name] = await provider.discover_models()
            except Exception:
                # Provider unavailable, keep stale data
                pass
        self._last_refresh = datetime.utcnow()

    def get_all_models(self) -> List[Dict]:
        """Get all available models across providers."""
        all_models = []
        for provider_models in self._models.values():
            all_models.extend(provider_models)
        return all_models

    def get_models_by_provider(self, provider: str) -> List[Dict]:
        """Get models for a specific provider."""
        return self._models.get(provider, [])
```

### 10.3 Model Selection Strategy

| Task Type | Primary Model | Fallback Model | Min Context |
|-----------|---------------|----------------|-------------|
| Note Generation | claude-sonnet-4-20250514 | llama3.1:70b | 8192 |
| Clinical Extraction | llama3.1:8b | claude-haiku | 4096 |
| Calculator Assist | phi3:medium | llama3.1:8b | 2048 |
| Evidence Search | llama3.1:8b | mistral:7b | 4096 |
| Assessment Synthesis | claude-sonnet-4-20250514 | llama3.1:70b | 8192 |
| Pathology Extraction | llama3.1:8b | claude-haiku | 4096 |

### 10.4 RAG Pipeline Architecture

The Clinical RAG Pipeline retrieves relevant context from the Neo4j knowledge graph and augments prompts before generation. The pipeline uses PubMedBERT embeddings (NeuML/pubmedbert-base-embeddings) for medical domain-optimized query vectorization, performs similarity search with optional category filtering (AUA, NCCN, EAU guidelines), assembles context from top-k relevant documents (default k=5), constructs augmented prompts with retrieved context, and generates responses via the selected LLM provider.

---

## 11. Microsoft Word Output Design

### 11.1 Document Template Architecture

The system generates professional medical Word documents using python-docx with the following structure:

```
+-------------------------------------------------------------------+
|  [Hospital/Clinic Logo Area]                                       |
|  UROLOGY CLINIC NOTE                                               |
|  Date: [Visit Date]    Provider: [Provider Name]                   |
+-------------------------------------------------------------------+
|                                                                    |
|  CHIEF COMPLAINT:                                                  |
|  [CC text]                                                         |
|                                                                    |
|  HISTORY OF PRESENT ILLNESS:                                       |
|  [HPI narrative text]                                              |
|                                                                    |
|  +-------------------+--------+                                    |
|  |        IPSS                |                                    |
|  +-------------------+--------+                                    |
|  | Symptom           | Score  |                                    |
|  +-------------------+--------+                                    |
|  | Incomplete Empty  |   #    |                                    |
|  | Frequency         |   #    |                                    |
|  | ...               |   #    |                                    |
|  +-------------------+--------+                                    |
|  | Total             | ##/35  |                                    |
|  | Bother Index      | #/6    |                                    |
|  +-------------------+--------+                                    |
|                                                                    |
|  [... additional sections ...]                                     |
|                                                                    |
|  PSA CURVE:                                                        |
|  [r] MMM DD, YYYY HH:MM    PSA_VALUE[H]                          |
|  [r] MMM DD, YYYY HH:MM    PSA_VALUE                             |
|                                                                    |
|  [... remaining sections ...]                                      |
|                                                                    |
|  ASSESSMENT:                                                       |
|  [4-8 sentence narrative assessment]                               |
|                                                                    |
|  PROBLEM LIST:                                                     |
|  1. [Problem]                                                      |
|  2. [Problem]                                                      |
|                                                                    |
|  PLAN:                                                             |
|  [Treatment plan]                                                  |
+-------------------------------------------------------------------+
```

### 11.2 Word Document Formatting Specifications

| Element | Font | Size | Style |
|---------|------|------|-------|
| Document Title | Arial | 16pt | Bold |
| Section Headers | Arial | 12pt | Bold, Dark Blue (#2c5282) |
| Body Text | Times New Roman | 11pt | Normal |
| Table Headers | Arial | 10pt | Bold, White on Blue (#2c5282) |
| Table Body | Times New Roman | 10pt | Normal |
| PSA Curve | Courier New | 10pt | Monospace |
| Lab Values | Times New Roman | 10pt | Normal, abnormal values in Red |
| Footer | Arial | 8pt | Italic, Gray |

### 11.3 Document Generation Pipeline

1. **Template Loading**: Load base Word template with pre-defined styles
2. **Header Assembly**: Patient demographics, visit date, provider name
3. **Section Rendering**: Each note section rendered with appropriate formatting
4. **Table Generation**: IPSS table, lab tables with proper borders and shading
5. **PSA Curve Formatting**: Monospace font, reverse chronological, "H" flag for >4
6. **Pathology Detail Preservation**: Full specimen-level detail with proper formatting
7. **Assessment Narrative**: 4-8 sentences without bullet points
8. **Footer**: Generated timestamp, system version, disclaimers
9. **Final Assembly**: Combine all sections, apply page breaks, generate .docx

### 11.4 Download Mechanism

Generated Word documents are stored temporarily in memory and served via a download endpoint. The document is deleted from server memory immediately after the HTTP response completes, maintaining zero-persistence PHI architecture.

---

## 12. Clinical Module Engine

### 12.1 Calculator Base Architecture

All 44 clinical calculators inherit from a common base class that provides input validation, standardized result formatting, and reference management. The framework supports multiple input types including float, integer, boolean, and choice selections with validation rules for ranges and required fields.

Calculator results include the computed score, interpretive text, risk level classification (very low through very high), clinical recommendations, calculation breakdown, and literature references.

### 12.2 FHIR-Populated Calculator Inputs

A key enhancement over VAUCDA is automatic population of calculator inputs from FHIR-retrieved data:

| Calculator | Auto-Populated Inputs | FHIR Source |
|------------|----------------------|-------------|
| PSA Kinetics | PSA values, dates | Observation (LOINC: 2857-1) |
| CAPRA Score | PSA level | Observation (LOINC: 2857-1) |
| IPSS | Individual symptom scores | Observation (LOINC: 72149-5) |
| Testosterone Eval | Total T, Free T | Observation (LOINC: 2986-8, 2991-8) |
| 24-hr Urine | Calcium, oxalate, citrate, etc. | Observation (Litholink LOINCs) |
| IMDC Criteria | Labs (Hgb, calcium, neutrophils, platelets) | Observation (general LOINCs) |
| RCRI | Creatinine | Observation (LOINC: 2160-0) |

### 12.3 Module Categories

The 44 calculators are organized into 10 categories identical to VAUCDA:

**Prostate Cancer (7)**: PSA Kinetics, PCPT 2.0, CAPRA Score, NCCN Risk Stratification, Partin Tables, D'Amico Classification, Memorial Sloan Kettering Pre-Prostatectomy Nomogram

**Kidney Cancer (4)**: RENAL Nephrometry Score, SSIGN Score, IMDC Risk Criteria, UCLA Integrated Staging System (UISS)

**Bladder Cancer (3)**: EORTC Recurrence Score, EORTC Progression Score, Modified Charlson Comorbidity Index

**Male Voiding (5)**: IPSS Calculator, AUA Symptom Subscore, BOOI/BCI (Urodynamics), Uroflow Analysis, Post-Void Residual Assessment

**Female Urology (5)**: UDI-6/IIQ-7, OAB-q Short Form, POP-Q Staging, Blaivas-Groutz Nomogram, Valsalva Leak Point Pressure

**Reconstructive (4)**: Stricture Complexity Score, PFUI Classification, Urethral Plate Assessment, Lichen Sclerosus Severity Index

**Male Fertility (5)**: Semen Analysis (WHO 2021), Varicocele Grading (Dubin-Amelar), Y-Chromosome Microdeletion Risk, Sperm DNA Fragmentation Index, Hormonal Fertility Profile

**Hypogonadism (3)**: Testosterone Evaluation, ADAM Questionnaire, Endocrine Society Screening Criteria

**Urolithiasis (4)**: STONE Score, 24-hr Urine Interpretation, Guy's Stone Score, S.T.O.N.E. Nephrolithometry

**Surgical Planning (4)**: Clinical Frailty Scale (CFS), Revised Cardiac Risk Index (RCRI), ACS NSQIP Risk Calculator, Caprini VTE Risk Assessment

---

## 13. User Interface Design

### 13.1 Design Principles

The interface prioritizes clinical efficiency with minimal cognitive load. Design principles include clarity (immediate understanding of EPIC connection status and available actions), efficiency (automated data extraction eliminating manual entry), accessibility (WCAG 2.1 AA compliance throughout), and professionalism (medical-appropriate aesthetics conveying trust and reliability).

### 13.2 Color System

The color system follows the VAUCDA design specification:

| Color | Hex | CSS Variable | Usage |
|-------|-----|--------------|-------|
| Primary Blue | `#2c5282` | `--primary-blue` | Navigation, primary buttons, headings |
| Primary Light | `#3182ce` | `--primary-light-blue` | Hover states, interactive highlights |
| Secondary Blue | `#4299e1` | `--secondary-blue` | Secondary buttons, badges |
| Accent Blue | `#63b3ed` | `--accent-blue` | Links, subtle accents |
| Medical Teal | `#0d9488` | `--medical-teal` | Clinical actions, EPIC connection |
| Success | `#10b981` | `--success-green` | Connected status, confirmations |
| Warning | `#f59e0b` | `--warning-yellow` | Cautions, modified states |
| Error | `#ef4444` | `--error-red` | Errors, disconnected status |
| Info | `#06b6d4` | `--info-cyan` | Notifications, info messages |

### 13.3 Main Application Layout

```
+-----------------------------------------------------------------------------+
|  EPIC-VAUCDA UROLOGY DOCUMENTATION          [EPIC: Connected] [User] [Gear] |
+-----------------------------------------------------------------------------+
|                                                                              |
|  +-------------------+  +-------------------+  +-------------------+         |
|  | NOTE GENERATION   |  |  EPIC SETTINGS    |  |  EVIDENCE SEARCH  |         |
|  |     [ACTIVE]      |  |                   |  |                   |         |
|  +-------------------+  +-------------------+  +-------------------+         |
|                                                                              |
+-----------------------------------------------------------------------------+
|                                                                              |
|  [Main Content Area - Tab Dependent]                                         |
|                                                                              |
+-----------------------------------------------------------------------------+
```

### 13.4 Note Generation Screen

```
+-----------------------------------------------------------------------------+
|  NOTE GENERATION                         Patient: [Auto from EPIC Context]   |
+-----------------------------------------------------------------------------+
|                                   |  CLINICAL MODULES                        |
|  NOTE TYPE:                       |  +-------------------------------------+ |
|  +-------------------------------+|                                          |
|  | * Urology Clinic Note        ||  > PROSTATE CANCER                      |
|  | o Urology Consult            ||    [ ] PSA Kinetics                     |
|  | o Urology Preop Note         ||    [ ] PCPT 2.0                         |
|  | o Urology Postop Note        ||    [ ] CAPRA Score                      |
|  +-------------------------------+|    [ ] NCCN Risk Stratification         |
|                                   |                                          |
|  EPIC DATA STATUS:                |  > KIDNEY CANCER                         |
|  [*] Labs (127 results)          |    [ ] RENAL Nephrometry Score          |
|  [*] Clinic Notes (12 notes)     |    [ ] SSIGN Score                      |
|  [*] Imaging (8 reports)         |    [ ] IMDC Risk Criteria               |
|  [*] Pathology (3 reports)       |                                          |
|  [*] Medications (Active: 14)    |  > BLADDER CANCER                        |
|  [*] Allergies (3 allergies)     |    [ ] EORTC Recurrence Score           |
|                                   |    [ ] EORTC Progression Score          |
|  LLM MODEL:                       |                                          |
|  +-------------------------------+|  > MALE VOIDING DYSFUNCTION              |
|  | claude-sonnet-4-20250514  [v] ||    [ ] IPSS Calculator                  |
|  +-------------------------------+|    [ ] AUA Symptom Subscore              |
|  Provider: [Anthropic  v]        |                                          |
|                                   |  [+ More Categories...]                  |
|  [Generate Note]  [Refresh Data] |                                          |
+-----------------------------------+------------------------------------------+
```

### 13.5 EPIC Settings Screen

```
+-----------------------------------------------------------------------------+
|  EPIC SETTINGS                                                               |
+-----------------------------------------------------------------------------+
|                                                                              |
|  EPIC FHIR CONNECTION                               Status: [* Connected]   |
|  +-----------------------------------------------------------------------+  |
|  |  FHIR Base URL:                                                        |  |
|  |  +-------------------------------------------------------------------+|  |
|  |  | https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4         ||  |
|  |  +-------------------------------------------------------------------+|  |
|  |                                                                        |  |
|  |  Client ID:                                                            |  |
|  |  +-------------------------------------------------------------------+|  |
|  |  | xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx                              ||  |
|  |  +-------------------------------------------------------------------+|  |
|  |                                                                        |  |
|  |  Redirect URI:                                                         |  |
|  |  +-------------------------------------------------------------------+|  |
|  |  | https://epic-vaucda.va.gov/auth/callback                          ||  |
|  |  +-------------------------------------------------------------------+|  |
|  |                                                                        |  |
|  |  [Test Connection]  [Save]                                             |  |
|  +-----------------------------------------------------------------------+  |
|                                                                              |
|  LLM PROVIDER CONFIGURATION                                                 |
|  +-----------------------------------------------------------------------+  |
|  |                                                                        |  |
|  |  OLLAMA                                     Status: [* Online]         |  |
|  |  Host: [http://localhost:11434          ]                              |  |
|  |  Available Models:                                                     |  |
|  |    llama3.1:8b (4.7 GB)     [Default]                                 |  |
|  |    llama3.1:70b (40 GB)                                               |  |
|  |    mistral:7b (4.1 GB)                                                |  |
|  |    phi3:medium (7.9 GB)                                               |  |
|  |  [Pull New Model: _____________ ] [Pull]                              |  |
|  |                                                                        |  |
|  |  ANTHROPIC                                  Status: [* Active]         |  |
|  |  API Key: [****************************]                              |  |
|  |  Available Models:                                                     |  |
|  |    claude-sonnet-4-20250514                                           |  |
|  |    claude-haiku-4-20250514                                            |  |
|  |  [Refresh Models]                                                      |  |
|  |                                                                        |  |
|  +-----------------------------------------------------------------------+  |
|                                                                              |
+-----------------------------------------------------------------------------+
```

### 13.6 React Component Architecture

**Layout Components**: MainLayout, Header, Navigation, TabContainer, EPICStatusBadge
**Note Components**: NoteGenerator, NoteTypeSelector, EPICDataStatus, GeneratedNotePreview, WordDownloadButton
**EPIC Components**: EPICSettingsPanel, FHIRConnectionForm, PatientSelector, LabBrowser, NoteBrowser
**LLM Components**: LLMSettingsPanel, ModelSelector, ModelDiscoveryManager, OllamaModelPuller
**Module Components**: ModuleSelector, CategoryAccordion, CalculatorPanel, CalculatorInputForm, FHIRAutoPopulate
**Common Components**: Button, Card, Modal, StatusIndicator, LoadingSpinner, EncryptedInput

---

## 14. API Specification

### 14.1 Authentication Endpoints

**GET /auth/epic/authorize**

Initiates EPIC OAuth 2.0 SMART on FHIR authorization flow. Generates PKCE challenge and redirects to EPIC authorization endpoint.

**GET /auth/epic/callback**

Handles OAuth 2.0 callback with authorization code. Exchanges code for access token using PKCE verifier. Returns session token to client.

**POST /auth/epic/refresh**

Refreshes EPIC access token using refresh token. Returns new access token pair.

**GET /auth/epic/status**

Returns current EPIC connection status, token expiration, and patient context.

### 14.2 FHIR Data Endpoints

**GET /api/v1/fhir/patient**

Returns current patient context from EPIC FHIR.

**GET /api/v1/fhir/labs**

Retrieves all labs using the dual-strategy approach (6-month window + targeted urology LOINCs). Returns categorized lab results.

Query parameters:
- `window_months` (int, default 6): Temporal window for general labs
- `include_targeted` (bool, default true): Include targeted urology LOINC queries

**GET /api/v1/fhir/notes**

Retrieves urology clinic notes and procedure notes from DocumentReference resources.

**GET /api/v1/fhir/imaging**

Retrieves imaging DiagnosticReports relevant to urology.

**GET /api/v1/fhir/pathology**

Retrieves pathology DiagnosticReports for urologic specimens.

**GET /api/v1/fhir/medications**

Retrieves active medications from MedicationStatement resources.

**GET /api/v1/fhir/allergies**

Retrieves allergy information from AllergyIntolerance resources.

**GET /api/v1/fhir/conditions**

Retrieves active conditions/problem list from Condition resources.

**GET /api/v1/fhir/history**

Retrieves surgical history (Procedure) and family history (FamilyMemberHistory).

### 14.3 Note Generation Endpoints

**POST /api/v1/notes/generate**

Generates a clinical note from FHIR-extracted data.

Request body:
- `patient_id` (string, required): FHIR Patient resource ID
- `note_type` (enum, required): clinic_note | consult | preop | postop
- `template_id` (string, optional): Specific template to use
- `selected_modules` (array of strings): Calculator modules to include
- `llm_config` (object, optional): Provider, model, temperature settings
- `output_format` (enum, default "docx"): docx | json

Response:
- `note_id` (string): Unique identifier
- `download_url` (string): URL to download generated .docx
- `sections` (array): Individual note sections (for preview)
- `metadata` (object): Model used, tokens, generation time, FHIR queries executed

**GET /api/v1/notes/{note_id}/download**

Downloads the generated Microsoft Word document. The document is served and immediately purged from server memory.

### 14.4 Calculator Endpoints

**GET /api/v1/calculators**

Lists all available calculators organized by category.

**POST /api/v1/calculators/{calculator_id}/calculate**

Executes a specific calculator with provided inputs.

**GET /api/v1/calculators/{calculator_id}/auto-populate**

Returns auto-populated calculator inputs from FHIR data for the current patient.

### 14.5 LLM Management Endpoints

**GET /api/v1/llm/providers**

Returns all configured LLM providers with status and available models.

**GET /api/v1/llm/models**

Returns unified model list from all active providers.

**POST /api/v1/llm/ollama/pull**

Pulls a new model to the Ollama server.

**POST /api/v1/llm/refresh**

Forces a refresh of the model discovery cache.

### 14.6 Settings Endpoints

**GET /api/v1/settings/epic**

Returns current EPIC configuration (credentials masked).

**PUT /api/v1/settings/epic**

Updates EPIC FHIR configuration. Credentials are encrypted before storage.

**GET /api/v1/settings/llm**

Returns LLM provider configuration (API keys masked).

**PUT /api/v1/settings/llm/{provider}**

Updates LLM provider configuration. API keys are encrypted before storage.

### 14.7 WebSocket Endpoints

**WS /ws/generate**

Real-time streaming for note generation with progress updates.

Message types:
- Client to Server: `start_generation` (initiates note generation)
- Server to Client: `fhir_progress` (FHIR data extraction status)
- Server to Client: `extraction_progress` (AI extraction status by section)
- Server to Client: `generation_progress` (text generation chunks)
- Server to Client: `generation_complete` (includes download URL)

---

## 15. Security and Compliance

### 15.1 Zero-Persistence PHI Architecture

The fundamental security principle remains identical to VAUCDA: no patient clinical information is ever persisted to disk, database, or any permanent storage. The system operates on a stateless, transient processing model where:

1. EPIC FHIR data is received encrypted over TLS 1.3
2. FHIR resources are parsed and held only in volatile memory
3. AI processing occurs with in-memory data only
4. Generated Word document exists in memory only
5. Document is served to client over TLS 1.3
6. All clinical data is immediately purged from memory
7. No PHI exists on the server after response delivery

### 15.2 OAuth 2.0 Security

#### 15.2.1 PKCE Implementation

All OAuth 2.0 authorization code flows use PKCE (Proof Key for Code Exchange) per RFC 7636. The code_verifier is a cryptographically random 128-character string. The code_challenge uses S256 transformation. No client secrets are transmitted through the browser.

#### 15.2.2 Token Management

- Access tokens are stored in server-side encrypted session only (never in browser storage)
- Refresh tokens are stored in server-side encrypted session only
- Token expiration is strictly enforced with automatic refresh
- Session timeout after 30 minutes of inactivity
- All tokens are destroyed on logout

### 15.3 Credential Encryption

EPIC credentials and API keys stored in SQLite are encrypted using AES-256-GCM:

- Master encryption key derived from environment variable using PBKDF2
- Each credential uses a unique initialization vector (IV)
- Authentication tags verify data integrity
- Keys are never logged or included in error messages

### 15.4 FHIR Data Access Controls

- All FHIR requests include proper authorization headers
- Access scopes are limited to minimum required permissions
- Patient context is validated on every request
- FHIR audit events are logged (metadata only, no PHI)
- Session-scoped access prevents cross-patient data leaks

### 15.5 Data Classification

| Data Type | Stored? | Location | Retention |
|-----------|---------|----------|-----------|
| FHIR Patient Data (PHI) | Never | Memory only | Deleted immediately |
| Generated Notes (PHI) | Never | Memory only | Deleted immediately |
| Word Documents (PHI) | Never | Memory only | Deleted after download |
| EPIC Access Tokens | Never | Server session only | Destroyed on logout |
| Calculator Inputs (PHI) | Never | Memory only | Deleted immediately |
| EPIC Client ID | Yes | SQLite (encrypted) | Per user config |
| Anthropic API Key | Yes | SQLite (encrypted) | Per user config |
| User Preferences | Yes | SQLite | Per retention policy |
| Session Timestamps | Yes | SQLite | 90 days |
| FHIR Query Counts | Yes | SQLite | Aggregated metadata only |
| Clinical Templates | Yes | File system | Permanent |
| Medical Guidelines | Yes | Neo4j | Permanent |

### 15.6 HIPAA Compliance Matrix

| Requirement | Implementation | Verification |
|-------------|----------------|--------------|
| Access Controls (Section 164.312(a)) | OAuth 2.0 SMART on FHIR, RBAC | EPIC audit trail |
| Audit Controls (Section 164.312(b)) | PHI-free audit logging, FHIR access logging | Log review |
| Integrity Controls (Section 164.312(c)) | TLS 1.3, FHIR resource validation | Certificate validation |
| Transmission Security (Section 164.312(e)) | Mandatory TLS 1.3 (EPIC and client) | SSL Labs A+ rating |
| Encryption (Section 164.312(a)(2)(iv)) | AES-256-GCM (credentials), TLS 1.3 (transit) | Cipher audit |
| Data Minimization | Zero PHI persistence, minimum FHIR scopes | Architecture review |
| Automatic Logoff (Section 164.312(a)(2)(iii)) | 30-minute session timeout | Session management |
| Entity Authentication (Section 164.312(d)) | EPIC SSO via OAuth 2.0 | Authentication testing |

### 15.7 Secure Transmission

All client-server communication uses TLS 1.3 with approved cipher suites (TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256). All EPIC FHIR communication uses TLS 1.3 as required by EPIC. Security headers include Strict-Transport-Security, X-Content-Type-Options, X-Frame-Options, Content-Security-Policy, and Referrer-Policy.

---

## 16. Deployment Architecture

### 16.1 Container Configuration

```
+-----------------------------------------------------------------------------+
|                          CONTAINER ORCHESTRATION                              |
|                            (Docker Compose)                                   |
+-----------------------------------------------------------------------------+
|                                                                              |
|  +-------------+  +-------------+  +-------------+  +-------------+         |
|  | epic-vaucda |  | epic-vaucda |  |   neo4j     |  |   ollama    |         |
|  |  -api       |  |  -frontend  |  | :7474/:7687 |  |   :11434    |         |
|  |   :8000     |  |   :3000     |  |             |  |   (GPU)     |         |
|  +-------------+  +-------------+  +-------------+  +-------------+         |
|                                                                              |
|  +-------------+  +-------------+                                            |
|  |   redis     |  |   celery    |                                            |
|  |   :6379     |  |   worker    |                                            |
|  +-------------+  +-------------+                                            |
|                                                                              |
+-----------------------------------------------------------------------------+
|                          PERSISTENT VOLUMES                                   |
|  +---------------+  +---------------+  +---------------+                     |
|  | neo4j_data    |  | ollama_models |  | redis_data    |                     |
|  | neo4j_logs    |  |               |  |               |                     |
|  +---------------+  +---------------+  +---------------+                     |
+-----------------------------------------------------------------------------+
|                                                                              |
|                    EXTERNAL CONNECTIONS                                       |
|  +-----------------------------+  +-----------------------------+            |
|  | EPIC FHIR Server            |  | Anthropic API               |            |
|  | (via TLS 1.3)               |  | (via TLS 1.3)               |            |
|  +-----------------------------+  +-----------------------------+            |
|                                                                              |
+-----------------------------------------------------------------------------+
```

### 16.2 Environment Configuration

Critical environment variables:

```
# EPIC FHIR Configuration
EPIC_FHIR_BASE_URL=https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
EPIC_CLIENT_ID=<from EPIC App Orchard>
EPIC_REDIRECT_URI=https://epic-vaucda.va.gov/auth/callback

# LLM Providers
OLLAMA_HOST=http://ollama:11434
ANTHROPIC_API_KEY=<encrypted in vault>

# Database
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<from vault>

# Security
JWT_SECRET_KEY=<from vault>
MASTER_ENCRYPTION_KEY=<from vault>
TLS_CERT_FILE=/etc/ssl/certs/epic-vaucda.crt
TLS_KEY_FILE=/etc/ssl/private/epic-vaucda.key

# Redis
REDIS_URL=redis://redis:6379

# Embedding Model
EMBEDDING_MODEL=NeuML/pubmedbert-base-embeddings
```

### 16.3 EPIC Connectivity Requirements

- Network access to EPIC FHIR R4 endpoints
- TLS 1.3 certificates trusted by EPIC servers
- Registered application in EPIC App Orchard
- Approved SMART on FHIR scopes
- EPIC sandbox environment for development and testing
- EPIC production environment for deployment

### 16.4 Ollama Model Deployment

Required models are pulled during deployment initialization:
- llama3.1:8b (primary, fast response)
- llama3.1:70b (complex reasoning)
- mistral:7b (fallback)
- phi3:medium (calculator assistance)
- nomic-embed-text (embeddings)

### 16.5 Neo4j Initialization

Database initialization includes creating uniqueness constraints, vector indexes for document and concept embeddings (768 dimensions, cosine similarity), full-text indexes for content search, and LOINC code registry population.

---

## 17. Testing Strategy

### 17.1 EPIC FHIR Testing

#### 17.1.1 EPIC Sandbox Testing

All FHIR integration testing uses the EPIC Sandbox environment:
- Sandbox URL: https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
- Test patients with known clinical data
- Validation of all FHIR resource queries
- OAuth 2.0 flow testing with EPIC sandbox credentials

#### 17.1.2 FHIR Mock Testing

For unit and integration testing without EPIC connectivity:
- FHIR resource fixtures with representative clinical data
- Mock FHIR server using HAPI FHIR test framework
- Simulated FHIR Bundle responses for all resource types
- Error handling testing (timeout, 401, 403, 404, rate limiting)

#### 17.1.3 Lab Retrieval Validation

- Verify all 17+ urology-specific LOINC codes are queried
- Validate date-windowed lab retrieval (6-month default)
- Test LOINC code categorization (endocrine, stone, general, tumor markers)
- Validate lab result sorting (reverse chronological)

### 17.2 Word Document Testing

- Validate document structure matches template specification
- Verify formatting (fonts, sizes, colors, tables)
- Test IPSS table rendering with sample data
- Test PSA curve formatting (monospace, "H" flag, chronological order)
- Validate pathology section preserves specimen-level detail
- Test document accessibility (heading structure, alt text)
- Cross-platform compatibility (Word for Windows, Mac, mobile)

### 17.3 LLM Testing

- Dynamic model discovery from Ollama and Anthropic
- Model switching without session interruption
- Extraction agent accuracy against reference clinical data
- Assessment/plan generation quality validation
- Fallback behavior when primary model unavailable

### 17.4 Unit Testing

pytest for all Python modules with 80% minimum coverage. Calculator algorithms require 100% coverage with validation against published examples.

### 17.5 Integration Testing

API endpoint testing with pytest-asyncio. FHIR client integration testing. LLM provider integration testing. Word document generation testing.

### 17.6 End-to-End Testing

Playwright for browser automation. Full workflow testing from EPIC authentication to Word document download. Accessibility testing with axe-core. WCAG 2.1 AA compliance validation.

### 17.7 Security Testing

- OAuth 2.0 PKCE flow validation
- Token management security audit
- Credential encryption verification
- Zero-persistence PHI validation (memory scanning)
- FHIR scope enforcement testing
- Penetration testing by security team

---

## 18. Risk Assessment

### 18.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| EPIC FHIR API changes | Medium | High | Version pinning, adapter pattern, FHIR R4 compliance |
| LLM accuracy issues | Medium | High | Rigorous prompt engineering, human review workflow |
| FHIR rate limiting | Medium | Medium | Request batching, caching, exponential backoff |
| Ollama availability | Low | High | Anthropic fallback, health monitoring |
| Word document formatting issues | Low | Medium | Template testing, cross-platform validation |
| EPIC sandbox vs production differences | Medium | Medium | Phased rollout, comprehensive FHIR testing |

### 18.2 Security Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| PHI exposure through FHIR | Low | Critical | Zero-persistence architecture, memory isolation |
| OAuth token compromise | Low | High | PKCE, server-side tokens, automatic expiration |
| Credential theft | Low | High | AES-256-GCM encryption, vault-based master key |
| FHIR scope escalation | Low | High | Minimum required scopes, EPIC-enforced ACL |
| Data breach | Low | Critical | TLS 1.3, encryption at rest for credentials |

### 18.3 Integration Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| EPIC App Orchard rejection | Medium | High | Early submission, compliance review, iteration |
| FHIR data quality variability | Medium | Medium | Robust parsing, fallback extraction patterns |
| LOINC code coverage gaps | Low | Medium | Extensible LOINC registry, manual code addition |
| Network connectivity issues | Medium | Medium | Retry logic, graceful degradation, offline mode |

### 18.4 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| User adoption resistance | Medium | High | Training program, champion users |
| EPIC workflow disruption | Medium | Medium | EHR launch integration, minimal workflow changes |
| Model availability | Low | Medium | Dynamic model discovery, multiple providers |
| Support burden | Medium | Medium | Comprehensive documentation, help system |

---

## Appendices

### Appendix A: LOINC Code Reference

#### A.1 PSA Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 2857-1 | Prostate specific Ag [Mass/volume] in Serum or Plasma | ng/mL |
| 10886-0 | Prostate specific Ag free [Mass/volume] in Serum or Plasma | ng/mL |
| 12841-3 | Prostate specific Ag free/Prostate specific Ag.total in Serum or Plasma | % |
| 35741-8 | PSA [Mass/volume] in Serum or Plasma by Detection limit <= 0.01 ng/mL | ng/mL |

#### A.2 Testosterone Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 2986-8 | Testosterone [Mass/volume] in Serum or Plasma | ng/dL |
| 2991-8 | Testosterone Free [Mass/volume] in Serum or Plasma | pg/mL |
| 49041-6 | Testosterone.bioavailable [Mass/volume] in Serum or Plasma | ng/dL |

#### A.3 Endocrine Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 2243-4 | Estradiol (E2) [Mass/volume] in Serum or Plasma | pg/mL |
| 10501-5 | Luteinizing hormone (LH) [Units/volume] in Serum or Plasma | mIU/mL |
| 15067-2 | Follicle stimulating hormone (FSH) [Units/volume] in Serum or Plasma | mIU/mL |
| 2731-8 | Parathyrin.intact [Mass/volume] in Serum or Plasma | pg/mL |

#### A.4 Tumor Marker Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 1834-1 | Alpha-1-Fetoprotein [Mass/volume] in Serum or Plasma | ng/mL |
| 21198-7 | Choriogonadotropin.beta subunit [Units/volume] in Serum or Plasma | mIU/mL |
| 2532-0 | Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma | U/L |

#### A.5 Urinalysis Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 5794-3 | Microscopic observation [Identifier] in Urine sediment by Light microscopy | - |
| 24356-8 | Urinalysis complete panel in Urine | - |
| 630-4 | Bacteria identified in Urine by Culture | - |

#### A.6 Litholink/Stone Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 57362-1 | 24 hour urine panel | - |
| 49054-9 | Oxalate [Moles/time] in 24 hour Urine | mg/24h |
| 2881-1 | Citrate [Moles/time] in 24 hour Urine | mg/24h |
| 21482-5 | Calcium [Mass/time] in 24 hour Urine | mg/24h |
| 2777-1 | Urate [Mass/volume] in Serum or Plasma | mg/dL |
| 2160-0 | Creatinine [Mass/volume] in Serum or Plasma | mg/dL |
| 2075-0 | Chloride [Moles/volume] in Serum or Plasma | mmol/L |
| 2947-0 | Sodium [Moles/volume] in Serum or Plasma | mmol/L |
| 6298-4 | Potassium [Moles/volume] in Blood | mmol/L |
| 1989-3 | 25-Hydroxyvitamin D2+D3 [Mass/volume] in Serum or Plasma | ng/mL |

#### A.7 General Lab Panel

| LOINC Code | Display Name | Units |
|------------|-------------|-------|
| 58410-2 | CBC panel - Blood by Automated count | - |
| 51990-0 | Basic metabolic panel - Serum or Plasma | - |
| 24323-8 | Comprehensive metabolic panel - Serum or Plasma | - |

### Appendix B: FHIR Resource Examples

#### B.1 Lab Observation (PSA)

```json
{
  "resourceType": "Observation",
  "id": "psa-example-001",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "laboratory"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "2857-1",
      "display": "Prostate specific Ag [Mass/volume] in Serum or Plasma"
    }]
  },
  "effectiveDateTime": "2025-12-15T10:30:00Z",
  "valueQuantity": {
    "value": 5.2,
    "unit": "ng/mL",
    "system": "http://unitsofmeasure.org",
    "code": "ng/mL"
  },
  "referenceRange": [{
    "low": {"value": 0.0, "unit": "ng/mL"},
    "high": {"value": 4.0, "unit": "ng/mL"}
  }],
  "interpretation": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
      "code": "H",
      "display": "High"
    }]
  }]
}
```

### Appendix C: Clinical Calculator Reference

| Calculator | Inputs | Output | Risk Categories |
|------------|--------|--------|-----------------|
| PSA Kinetics | PSA values, time points | PSAV, PSADT | Based on thresholds |
| PCPT 2.0 | Age, race, family hx, PSA, DRE | Probability (0-100%) | Continuous |
| CAPRA Score | PSA, Gleason, stage, % cores | 0-10 points | Low/Intermediate/High |
| NCCN Risk | PSA, Gleason, stage, cores | Categorical | Very Low to Very High |
| RENAL Score | R, E, N, A, L components | 4-12 points | Low/Moderate/High complexity |
| SSIGN Score | TNM, size, grade, necrosis | 0-17 points | 5 risk groups |
| IMDC Criteria | KPS, time, labs | 0-6 factors | Favorable/Intermediate/Poor |
| IPSS | 7 symptom scores + bother | 0-35 (symptoms) + 0-6 (bother) | Mild/Moderate/Severe |
| STONE Score | Size, tract, obstruction, neutrophils, erythrocytes | 0-13 | Low/Moderate/High |

### Appendix D: Error Codes

| Code | Category | Description |
|------|----------|-------------|
| EVAUCDA-001 | LLM | Ollama connection failed |
| EVAUCDA-002 | LLM | Model not available |
| EVAUCDA-003 | LLM | Generation timeout |
| EVAUCDA-004 | LLM | Anthropic API error |
| EVAUCDA-010 | Database | Neo4j connection failed |
| EVAUCDA-011 | Database | Vector search failed |
| EVAUCDA-020 | Calculator | Invalid input parameters |
| EVAUCDA-021 | Calculator | Calculator not found |
| EVAUCDA-030 | Template | Template not found |
| EVAUCDA-031 | Template | Template parsing error |
| EVAUCDA-040 | Auth | EPIC OAuth failed |
| EVAUCDA-041 | Auth | EPIC token expired |
| EVAUCDA-042 | Auth | EPIC scope denied |
| EVAUCDA-043 | Auth | Session expired |
| EVAUCDA-050 | FHIR | EPIC FHIR connection failed |
| EVAUCDA-051 | FHIR | FHIR resource not found |
| EVAUCDA-052 | FHIR | FHIR rate limit exceeded |
| EVAUCDA-053 | FHIR | FHIR query timeout |
| EVAUCDA-054 | FHIR | Invalid FHIR resource |
| EVAUCDA-060 | Word | Document generation failed |
| EVAUCDA-061 | Word | Template rendering error |

### Appendix E: Glossary

| Term | Definition |
|------|------------|
| CAPRA | Cancer of the Prostate Risk Assessment |
| EPIC | Electronic health record system by Epic Systems Corporation |
| FHIR | Fast Healthcare Interoperability Resources (HL7 standard) |
| IMDC | International Metastatic RCC Database Consortium |
| LLM | Large Language Model |
| LOINC | Logical Observation Identifiers Names and Codes |
| PHI | Protected Health Information |
| PKCE | Proof Key for Code Exchange (OAuth 2.0 extension) |
| PSADT | PSA Doubling Time |
| PSAV | PSA Velocity |
| RAG | Retrieval-Augmented Generation |
| RENAL | Radius, Exophytic, Nearness, Anterior/posterior, Location |
| SMART | Substitutable Medical Applications, Reusable Technologies |
| SSIGN | Stage, Size, Grade, Necrosis |
| TLS | Transport Layer Security |

### Appendix F: Document Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Technical Lead | | | |
| Clinical Advisor | | | |
| Security Officer | | | |
| EPIC Integration Lead | | | |
| Project Manager | | | |
| Executive Sponsor | | | |

---

*This document is confidential and intended for internal technical use only.*

**Document Version:** 1.0
**Last Updated:** February 2, 2026
**Next Review:** May 2, 2026
