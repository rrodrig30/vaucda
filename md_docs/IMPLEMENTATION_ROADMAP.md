# VAUCDA Implementation Roadmap
**Phased Development Strategy with Dependency Graph**

Version: 1.0
Date: November 28, 2025

---

## Overview

This roadmap outlines the complete implementation strategy for VAUCDA, organized into logical phases with clear dependencies and milestones. Total estimated timeline: **16-20 weeks** for full production deployment.

**CRITICAL REQUIREMENTS:**
- NO mock code, placeholders, or fallbacks
- 100% functionality at each phase completion
- All components fully integrated and tested
- COT/TOT reasoning applied at each decision point
- Zero-persistence PHI architecture throughout

---

## Phase 1: Foundation & Infrastructure (Weeks 1-3)

### Week 1: Project Setup & Core Infrastructure

**Objectives:**
- Initialize project structure
- Set up development environment
- Configure Docker containers
- Establish CI/CD pipeline

**Tasks:**
1. Create complete directory structure (as specified in ARCHITECTURE.md)
2. Initialize Git repository with proper .gitignore
3. Set up Python virtual environment
4. Create requirements.txt with all dependencies
5. Configure Docker Compose for all services
6. Set up Neo4j with APOC and GDS plugins
7. Configure Redis
8. Pull Ollama models (llama3.1:8b, llama3.1:70b, mistral:7b, phi3:medium, nomic-embed-text)
9. Create .env from .env.example
10. Set up logging infrastructure

**Deliverables:**
- ✅ Fully functional Docker Compose environment
- ✅ All services running and healthy
- ✅ Database schemas initialized
- ✅ Development environment ready

**Testing:**
- All containers start successfully
- Health checks pass for all services
- Databases accept connections
- Ollama models pulled and accessible

---

### Week 2: Database Layer & Core Models

**Objectives:**
- Implement Neo4j schema
- Implement SQLite schema
- Create base data models
- Establish database clients

**Tasks:**
1. **Neo4j Implementation:**
   - Execute init_schema.cypher (create constraints, indexes)
   - Create neo4j_client.py with connection pooling
   - Implement vector index for 768-dim embeddings
   - Create full-text search indexes
   - Test vector similarity search

2. **SQLite Implementation:**
   - Execute init_schema.sql
   - Create sqlite_client.py with async support
   - Implement migrations system
   - Create audit logging tables

3. **Pydantic Models:**
   - Create all Neo4j node models
   - Create all SQLite table models
   - Define request/response schemas
   - Implement validation rules

**Deliverables:**
- ✅ Neo4j schema fully implemented
- ✅ SQLite schema fully implemented
- ✅ All database models defined
- ✅ Database clients operational

**Testing:**
- Create, read, update, delete operations for all models
- Vector search functionality
- Constraint enforcement
- Transaction rollback testing

---

### Week 3: FastAPI Core & Authentication

**Objectives:**
- Build FastAPI application structure
- Implement authentication system
- Create health check endpoints
- Establish API error handling

**Tasks:**
1. **FastAPI Setup:**
   - Create main.py with app initialization
   - Configure CORS middleware
   - Set up security middleware
   - Implement request/response logging

2. **Authentication:**
   - Implement JWT token generation
   - Create login endpoint
   - Implement token validation middleware
   - Add role-based access control (RBAC)
   - Create user management endpoints

3. **Core Endpoints:**
   - /health (basic health check)
   - /health/detailed (service status)
   - /auth/token (login)
   - /auth/refresh (token refresh)

4. **Security:**
   - Implement ephemeral_data.py (PHI-free architecture)
   - Create audit logging (metadata only)
   - Set up TLS/SSL configuration
   - Implement rate limiting

**Deliverables:**
- ✅ FastAPI app running
- ✅ Authentication working
- ✅ Security middleware active
- ✅ Health checks operational

**Testing:**
- Login/logout flows
- Token expiration
- Rate limiting
- CORS functionality
- Security headers validation

---

## Phase 2: LLM Integration & RAG Pipeline (Weeks 4-6)

### Week 4: Ollama Integration & Provider Abstraction

**Objectives:**
- Implement Ollama client
- Create LLM provider abstraction
- Build model selector
- Test LLM connectivity

**Tasks:**
1. **Ollama Client (`backend/llm/providers/ollama.py`):**
   - Implement OllamaClient class
   - Add generate() method
   - Add generate_stream() method
   - Add embeddings() method
   - Add list_models() method
   - Add health_check() method
   - Implement timeout handling
   - Add retry logic

2. **Provider Abstraction (`backend/llm/base.py`):**
   - Create LLMProvider interface
   - Define standard methods
   - Implement error handling

3. **Model Selector (`backend/llm/model_selector.py`):**
   - Map tasks to optimal models
   - Implement fallback logic
   - Add model availability checking

4. **Anthropic & OpenAI Clients (Optional):**
   - Implement AnthropicProvider
   - Implement OpenAIProvider
   - Add API key validation

5. **Orchestrator (`backend/llm/orchestrator.py`):**
   - Implement provider registry
   - Add provider switching logic
   - Create unified interface

**Deliverables:**
- ✅ Ollama fully integrated
- ✅ All LLM providers working
- ✅ Model selection operational
- ✅ Provider abstraction complete

**Testing:**
- Generate text with all providers
- Stream generation
- Model switching
- Timeout handling
- Error recovery

---

### Week 5: RAG Pipeline Implementation

**Objectives:**
- Build RAG pipeline
- Implement embeddings generation
- Create document ingestion system
- Test vector search

**Tasks:**
1. **Embeddings (`backend/rag/embeddings.py`):**
   - Initialize sentence-transformers
   - Implement embedding generation (768-dim)
   - Add batch processing
   - Implement caching

2. **Document Ingestion (`backend/rag/ingestion.py`):**
   - PDF parsing (PyMuPDF)
   - DOCX parsing (python-docx)
   - Text chunking (unstructured)
   - Embedding generation
   - Neo4j storage

3. **Retriever (`backend/rag/retriever.py`):**
   - Vector similarity search
   - Category filtering
   - Top-k retrieval
   - Relevance scoring

4. **Context Builder (`backend/rag/context_builder.py`):**
   - Assemble retrieved documents
   - Format context for LLM
   - Handle max context length

5. **RAG Pipeline (`backend/rag/pipeline.py`):**
   - Orchestrate retrieval
   - Augment prompts
   - Generate with context

**Deliverables:**
- ✅ Document ingestion working
- ✅ Vector search operational
- ✅ RAG pipeline functional
- ✅ Context assembly complete

**Testing:**
- Ingest sample documents
- Query vector store
- Verify retrieval accuracy
- Test context assembly
- End-to-end RAG generation

---

### Week 6: System Prompts & Note Generation Core

**Objectives:**
- Load and parse urology_prompt.txt
- Build note generation orchestrator
- Implement template system
- Create note formatting

**Tasks:**
1. **Prompts (`backend/llm/prompts.py`):**
   - Load urology_prompt.txt
   - Create prompt templates
   - Add variable substitution
   - Implement prompt versioning

2. **Template Manager (`backend/core/template_manager.py`):**
   - Load templates from /data/templates/
   - Parse template structure
   - Implement section mapping
   - Add template CRUD operations

3. **Note Generator (`backend/core/note_generator.py`):**
   - Orchestrate note generation
   - Parse clinical input
   - Call LLM with RAG context
   - Format output according to template
   - Handle errors gracefully

4. **Document Processor (`backend/core/document_processor.py`):**
   - Parse uploaded documents
   - Extract clinical data
   - Prepare for LLM processing

**Deliverables:**
- ✅ System prompts loaded
- ✅ Note generation working
- ✅ Templates operational
- ✅ Document processing functional

**Testing:**
- Generate notes with various inputs
- Test all template types
- Verify IPSS table generation
- Test PSA curve formatting
- Validate output structure

---

## Phase 3: Clinical Calculator Engine (Weeks 7-11)

### Week 7-8: Base Calculator Framework + Prostate/Kidney Modules (14 calculators)

**Objectives:**
- Build calculator base class
- Implement registry system
- Create validation framework
- Implement Prostate Cancer calculators (7)
- Implement Kidney Cancer calculators (4)

**Tasks:**
1. **Calculator Base (`backend/calculators/base.py`):**
   - Create ClinicalCalculator abstract class
   - Define CalculatorInput dataclass
   - Define CalculatorResult dataclass
   - Implement validate_inputs() method
   - Add error handling

2. **Registry (`backend/calculators/registry.py`):**
   - Create ClinicalModuleRegistry
   - Implement register() method
   - Add get_calculator() method
   - Add get_by_category() method
   - Create list_calculators() method

3. **Validators (`backend/calculators/validators.py`):**
   - Input type validation
   - Range validation
   - Required field validation
   - Choice validation

4. **Prostate Cancer Calculators (7):**
   - `psa_kinetics.py` - PSA Velocity/Doubling Time
   - `pcpt.py` - PCPT Risk Calculator 2.0
   - `capra.py` - CAPRA Score
   - `nccn_risk.py` - NCCN Risk Stratification
   - `nccn_diagnostic.py` - NCCN Diagnostic Workup
   - `nccn_surveillance.py` - NCCN Surveillance Schedule
   - `psa_tracking.py` - PSA Tracking Table

5. **Kidney Cancer Calculators (4):**
   - `renal_score.py` - RENAL Nephrometry Score
   - `ssign_score.py` - SSIGN Score
   - `imdc_criteria.py` - IMDC Risk Criteria
   - `survival_estimate.py` - Survival Estimation

**Deliverables:**
- ✅ Calculator framework complete
- ✅ Registry operational
- ✅ 11 calculators implemented
- ✅ All calculators validated against published examples

**Testing:**
- Validate each calculator against reference values
- Test edge cases
- Verify 100% accuracy
- Test error handling

---

### Week 9: Bladder, Voiding, Female Urology (13 calculators)

**Objectives:**
- Implement Bladder Cancer calculators (3)
- Implement Male Voiding calculators (5)
- Implement Female Urology calculators (5)

**Tasks:**
1. **Bladder Cancer Calculators (3):**
   - `eortc_recurrence.py` - EORTC Recurrence Score
   - `eortc_progression.py` - EORTC Progression Score
   - `survival_estimate.py` - Survival Estimation

2. **Male Voiding Calculators (5):**
   - `ipss.py` - IPSS Calculator
   - `aua_subscore.py` - AUA Symptom Subscore Analysis
   - `booi_bci.py` - BOOI/BCI (Urodynamics)
   - `uroflow.py` - Uroflowmetry Interpretation
   - `pvr_assessment.py` - Post-Void Residual Assessment

3. **Female Urology Calculators (5):**
   - `udi_iiq.py` - UDI-6/IIQ-7 Scores
   - `oab_q.py` - OAB-q Assessment
   - `pop_q.py` - POP-Q Staging
   - `sui_severity.py` - SUI Severity (Stamey/Sandvik)
   - `bladder_diary.py` - Bladder Diary Analysis

**Deliverables:**
- ✅ 13 additional calculators implemented
- ✅ Total: 24/44 calculators complete
- ✅ All calculators validated

**Testing:**
- Validate against clinical examples
- Test all input combinations
- Verify output formatting

---

### Week 10: Reconstructive, Fertility, Hypogonadism (12 calculators)

**Objectives:**
- Implement Reconstructive Urology calculators (4)
- Implement Male Fertility calculators (5)
- Implement Hypogonadism calculators (3)

**Tasks:**
1. **Reconstructive Urology Calculators (4):**
   - `stricture_complexity.py` - Stricture Complexity Score
   - `pfui_classification.py` - PFUI Classification
   - `fistula_classification.py` - Fistula Classification
   - `peyronies_assessment.py` - Peyronie's Assessment

2. **Male Fertility Calculators (5):**
   - `semen_analysis.py` - Semen Analysis Interpretation (WHO 2021)
   - `hormonal_panel.py` - Hormonal Evaluation Panel
   - `varicocele_grading.py` - Varicocele Grading
   - `azoospermia_workup.py` - Azoospermia Classification
   - `dfi_interpretation.py` - Sperm DNA Fragmentation

3. **Hypogonadism Calculators (3):**
   - `testosterone_eval.py` - Testosterone Evaluation
   - `adam_questionnaire.py` - ADAM Questionnaire
   - `treatment_monitoring.py` - Treatment Monitoring Panel

**Deliverables:**
- ✅ 12 additional calculators implemented
- ✅ Total: 36/44 calculators complete
- ✅ All calculators validated

**Testing:**
- Clinical validation
- Edge case testing
- Output verification

---

### Week 11: Urolithiasis, Surgical Planning (8 calculators)

**Objectives:**
- Implement Urolithiasis calculators (4)
- Implement Surgical Planning calculators (4)
- Complete all 44 calculators

**Tasks:**
1. **Urolithiasis Calculators (4):**
   - `stone_score.py` - STONE Score
   - `passage_probability.py` - Passage Probability Calculator
   - `urine_24hr.py` - 24-Hour Urine Analysis
   - `prevention_plan.py` - Stone Prevention Plan

2. **Surgical Planning Calculators (4):**
   - `frailty_scale.py` - Clinical Frailty Scale
   - `rcri.py` - Revised Cardiac Risk Index
   - `nsqip.py` - ACS NSQIP Risk Calculator (link to external)
   - `life_expectancy.py` - 10/15-Year Life Expectancy

**Deliverables:**
- ✅ All 44 calculators implemented
- ✅ 100% calculator accuracy validated
- ✅ Complete calculator documentation
- ✅ Registry fully populated

**Testing:**
- Comprehensive validation suite
- Performance testing
- Integration testing with note generation

---

## Phase 4: API Endpoints & Frontend (Weeks 12-14)

### Week 12: Complete Backend API Implementation

**Objectives:**
- Implement all REST API endpoints
- Create WebSocket streaming
- Add endpoint testing

**Tasks:**
1. **Note Endpoints (`backend/api/v1/notes.py`):**
   - POST /notes/generate
   - GET /notes/{note_id}
   - DELETE /notes/{note_id}

2. **Calculator Endpoints (`backend/api/v1/calculators.py`):**
   - GET /calculators
   - GET /calculators/{calculator_id}
   - POST /calculators/{calculator_id}/calculate
   - POST /calculators/batch

3. **Template Endpoints (`backend/api/v1/templates.py`):**
   - GET /templates
   - GET /templates/{template_id}
   - POST /templates (admin)
   - PUT /templates/{template_id} (admin)
   - DELETE /templates/{template_id} (admin)

4. **Settings Endpoints (`backend/api/v1/settings.py`):**
   - GET /settings
   - PUT /settings

5. **LLM Endpoints (`backend/api/v1/llm.py`):**
   - GET /llm/providers
   - GET /llm/ollama/models
   - POST /llm/ollama/pull (admin)
   - GET /llm/ollama/pull/{task_id}

6. **Evidence Endpoints (`backend/api/v1/evidence.py`):**
   - POST /evidence/search
   - POST /evidence/ingest (admin)

7. **WebSocket (`backend/api/websockets/streaming.py`):**
   - WS /ws/generate

**Deliverables:**
- ✅ All API endpoints implemented
- ✅ WebSocket streaming working
- ✅ API documentation complete
- ✅ Endpoint tests passing

**Testing:**
- API integration tests
- WebSocket connection tests
- Rate limiting tests
- Error handling tests

---

### Week 13-14: React Frontend Implementation

**Objectives:**
- Build complete React frontend
- Implement all UI components
- Integrate with backend API
- Apply VAUCDA color palette

**Tasks:**
1. **Project Setup:**
   - Initialize React + TypeScript + Vite
   - Configure Tailwind CSS with VAUCDA colors
   - Set up Redux Toolkit
   - Configure Axios

2. **Layout Components:**
   - MainLayout.tsx
   - Header.tsx
   - Navigation.tsx (3 tabs: Note Generation, Settings, Open Evidence)
   - TabContainer.tsx

3. **Note Generation Components:**
   - NoteGenerator.tsx (main interface)
   - NoteTypeSelector.tsx (radio buttons)
   - ClinicalInputArea.tsx (textarea)
   - GeneratedNoteDisplay.tsx (formatted output)
   - NoteExporter.tsx (copy/export)

4. **Module Components:**
   - ModuleSelector.tsx (44 calculators in 10 categories)
   - CategoryAccordion.tsx (collapsible categories)
   - CalculatorPanel.tsx (individual calculator)
   - CalculatorInputForm.tsx (dynamic forms)
   - CalculatorResults.tsx (formatted results)

5. **Settings Components:**
   - SettingsPanel.tsx
   - TemplateSettings.tsx
   - LLMSettings.tsx (provider/model selection)
   - ModuleDefaults.tsx

6. **Evidence Search Components:**
   - EvidenceSearch.tsx
   - SearchResults.tsx
   - DocumentViewer.tsx

7. **Common Components:**
   - Button.tsx (primary, secondary, medical)
   - Card.tsx
   - Modal.tsx
   - StatusIndicator.tsx
   - LoadingSpinner.tsx
   - ErrorBoundary.tsx

8. **Services:**
   - noteService.ts
   - calculatorService.ts
   - templateService.ts
   - settingsService.ts

9. **State Management:**
   - noteSlice.ts
   - settingsSlice.ts
   - uiSlice.ts

**Deliverables:**
- ✅ Complete React application
- ✅ All UI components functional
- ✅ Full API integration
- ✅ VAUCDA branding applied

**Testing:**
- Component unit tests
- Integration tests
- E2E tests with Playwright
- Accessibility testing (WCAG 2.1 AA)

---

## Phase 5: Celery Tasks & Background Processing (Week 15)

### Week 15: Asynchronous Processing

**Objectives:**
- Implement Celery tasks
- Add background job processing
- Create task monitoring

**Tasks:**
1. **Celery App (`backend/tasks/celery_app.py`):**
   - Initialize Celery
   - Configure broker/backend
   - Set up task routing

2. **Note Tasks (`backend/tasks/note_tasks.py`):**
   - async_generate_note task
   - Add progress tracking
   - Implement error handling

3. **Ingestion Tasks (`backend/tasks/ingestion_tasks.py`):**
   - async_ingest_document task
   - Batch ingestion
   - Progress reporting

4. **Monitoring:**
   - Task status endpoints
   - Celery Flower dashboard
   - Task result retrieval

**Deliverables:**
- ✅ Celery workers operational
- ✅ Background tasks working
- ✅ Task monitoring available

**Testing:**
- Task execution
- Task cancellation
- Error handling
- Result retrieval

---

## Phase 6: Testing, Security & Deployment (Week 16-20)

### Week 16: Comprehensive Testing

**Objectives:**
- Complete unit test suite
- Integration testing
- E2E testing
- Performance testing

**Tasks:**
1. **Unit Tests:**
   - Backend: 80%+ coverage
   - Calculators: 100% coverage
   - Frontend: 70%+ coverage

2. **Integration Tests:**
   - API endpoints
   - Database operations
   - LLM integration
   - RAG pipeline

3. **E2E Tests:**
   - Complete note generation workflow
   - Calculator execution
   - Settings management
   - Evidence search

4. **Performance Tests:**
   - Note generation < 3s
   - Calculator execution < 500ms
   - 500 concurrent users
   - Database query optimization

**Deliverables:**
- ✅ Complete test suite
- ✅ All tests passing
- ✅ Performance targets met

---

### Week 17: Security Hardening

**Objectives:**
- Security audit
- HIPAA compliance verification
- Penetration testing
- PHI leak detection

**Tasks:**
1. **Security Audit:**
   - Code review for vulnerabilities
   - Dependency scanning
   - Secret detection
   - TLS configuration review

2. **HIPAA Compliance:**
   - Verify zero PHI persistence
   - Audit log verification
   - Encryption validation
   - Access control testing

3. **Penetration Testing:**
   - Authentication bypass attempts
   - SQL injection testing
   - XSS testing
   - Rate limit testing

4. **PHI Leak Detection:**
   - Memory inspection
   - Log analysis
   - Database verification
   - Network traffic analysis

**Deliverables:**
- ✅ Security audit passed
- ✅ HIPAA compliant
- ✅ No vulnerabilities

---

### Week 18: Documentation & Training

**Objectives:**
- Complete technical documentation
- Create user guides
- Admin documentation
- Training materials

**Tasks:**
1. **Technical Documentation:**
   - API reference (complete)
   - Architecture documentation
   - Database schema docs
   - Deployment guide

2. **User Documentation:**
   - User guide
   - Calculator reference
   - Quick start guide
   - FAQ

3. **Admin Documentation:**
   - Installation guide
   - Configuration guide
   - Backup/restore procedures
   - Troubleshooting guide

4. **Training Materials:**
   - Video tutorials
   - Screenshot guides
   - Use case examples

**Deliverables:**
- ✅ Complete documentation
- ✅ Training materials ready

---

### Week 19: Production Deployment Preparation

**Objectives:**
- Production environment setup
- Data migration
- SSL/TLS configuration
- Monitoring setup

**Tasks:**
1. **Environment Setup:**
   - Production .env configuration
   - SSL certificates
   - VA network integration
   - DNS configuration

2. **Data Migration:**
   - Ingest clinical guidelines (NCCN, AUA, EAU)
   - Populate calculator documentation
   - Load note templates
   - Create admin user

3. **Monitoring:**
   - Prometheus metrics
   - Grafana dashboards
   - Log aggregation
   - Alert configuration

4. **Backup:**
   - Automated backup scripts
   - Disaster recovery plan
   - Backup testing

**Deliverables:**
- ✅ Production environment ready
- ✅ Data migrated
- ✅ Monitoring operational

---

### Week 20: Production Deployment & Validation

**Objectives:**
- Deploy to production
- User acceptance testing
- Go-live support
- Performance monitoring

**Tasks:**
1. **Deployment:**
   - Deploy Docker containers
   - Configure Nginx
   - Start all services
   - Verify health checks

2. **User Acceptance Testing:**
   - Clinical workflow testing
   - Calculator validation
   - Performance verification
   - User feedback collection

3. **Go-Live:**
   - Gradual rollout
   - User onboarding
   - Support availability
   - Issue tracking

4. **Monitoring:**
   - Performance metrics
   - Error tracking
   - User analytics
   - System health

**Deliverables:**
- ✅ Production deployment complete
- ✅ UAT passed
- ✅ System operational

---

## Dependency Graph

```
Phase 1: Foundation
    ├── Docker Setup
    ├── Database Schemas
    └── Development Environment
            ↓
Phase 2: LLM & RAG
    ├── Ollama Integration (depends on Docker)
    ├── RAG Pipeline (depends on Neo4j)
    └── Note Generation Core (depends on LLM + RAG)
            ↓
Phase 3: Clinical Calculators
    ├── Calculator Framework
    ├── Prostate/Kidney (weeks 7-8)
    ├── Bladder/Voiding/Female (week 9)
    ├── Reconstructive/Fertility/Hypogonadism (week 10)
    └── Stones/Surgical (week 11)
            ↓
Phase 4: API & Frontend
    ├── REST API (depends on all backend logic)
    ├── WebSocket (depends on Note Generation)
    └── React Frontend (depends on API)
            ↓
Phase 5: Background Processing
    └── Celery Tasks (depends on API)
            ↓
Phase 6: Testing & Deployment
    ├── Testing (depends on all features)
    ├── Security (depends on complete system)
    └── Deployment (depends on testing pass)
```

---

## Success Criteria

Each phase must meet these criteria before proceeding:

1. **Functionality**: 100% of features working as designed
2. **Testing**: All tests passing with required coverage
3. **Documentation**: Complete and up-to-date
4. **Performance**: Meets all performance targets
5. **Security**: Passes security audit
6. **Code Quality**: Meets linting and formatting standards
7. **Integration**: All components working together
8. **No Fallbacks**: No mock code, placeholders, or TODOs

---

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|---------------------|
| LLM performance issues | Rigorous model selection and testing; fallback models |
| Calculator accuracy | 100% validation against published examples; clinical SME review |
| Integration complexity | Incremental integration; comprehensive integration tests |
| HIPAA compliance | Zero-persistence architecture; security audits at each phase |
| Schedule delays | Buffer time in estimates; parallel workstreams where possible |
| Resource constraints | Prioritize critical path items; flexible resource allocation |

---

This roadmap provides a comprehensive, dependency-aware implementation strategy for VAUCDA with clear milestones and success criteria at each phase.
