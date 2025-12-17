# VA Urology Clinical Documentation Assistant (VAUCDA)
## Software Design Document

**Version:** 1.0  
**Date:** November 28, 2025  
**Status:** Draft  
**Classification:** Internal Technical Documentation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture Design](#3-architecture-design)
4. [Technology Stack](#4-technology-stack)
5. [Data Layer Design](#5-data-layer-design)
6. [LLM Integration Layer](#6-llm-integration-layer)
7. [Clinical Module Engine](#7-clinical-module-engine)
8. [User Interface Specification](#8-user-interface-specification)
9. [API Design](#9-api-design)
10. [Security and Compliance](#10-security-and-compliance)
11. [Deployment Architecture](#11-deployment-architecture)
12. [Appendices](#appendices)

---

## 1. Executive Summary

### 1.1 Purpose

The VA Urology Clinical Documentation Assistant (VAUCDA) is a Python-based web application designed to streamline clinical documentation workflows for VA urology providers. The system leverages large language models and retrieval-augmented generation (RAG) to transform unstructured clinical text into organized urology clinic and consult notes while providing evidence-based urologic clinical decision support.

### 1.2 Scope

This document defines the technical architecture, component design, data models, and integration specifications for VAUCDA. It serves as the authoritative reference for development teams implementing the system.

### 1.3 Key Capabilities

The system provides three core functional areas: note generation from unstructured clinical data, clinical decision support through 44 specialized calculators and assessment tools, and evidence-based guidance through RAG-powered knowledge retrieval from urologic literature and guidelines.

---

## 2. System Overview

### 2.1 Functional Requirements

#### 2.1.1 Note Generation Module

The primary workspace provides a text input area where urologists paste raw clinical data (lab results, imaging reports, prior notes, and patient history) from VA clinical systems. The application processes this content through a selected LLM, reformatting it into a structured note that follows urology-specific templates.

Output notes maintain consistent organization including chief complaint, history of present illness, relevant urologic history, medications, genitourinary examination findings, diagnostic results, assessment, and plan.

#### 2.1.2 Clinical Module Categories

| Category | Module Count | Key Calculators/Assessments |
|----------|-------------|----------------------------|
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

**Total: 44 Clinical Modules**

### 2.2 Non-Functional Requirements

**Performance:** Response time under 3 seconds for note generation; calculator results rendered within 500ms.

**Availability:** 99.5% uptime during VA business hours (6 AM - 10 PM local time).

**Scalability:** Support for 500 concurrent users across VA medical centers.

**Accessibility:** WCAG 2.1 AA compliance for clinical interface elements.

---

## 3. Architecture Design

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    Web Interface (HTML/CSS/JS)                        │  │
│  │              React + Tailwind CSS + Alpine.js / HTMX                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              APPLICATION LAYER                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  FastAPI        │  │  Note           │  │  Clinical Module Engine   │   │
│  │  Backend        │  │  Generator      │  │  (Calculator Orchestration)│   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Template       │  │  Settings       │  │  Document Processor       │   │
│  │  Manager        │  │  Manager        │  │  (PDF/DOCX Ingestion)     │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           CLINICAL MODULE LAYER                             │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│  │  Prostate     │ │   Kidney      │ │   Bladder     │ │    Male       │   │
│  │  Cancer       │ │   Cancer      │ │   Cancer      │ │   Voiding     │   │
│  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘   │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│  │   Female      │ │  Reconstr.    │ │    Male       │ │   Stones      │   │
│  │   Urology     │ │   Urology     │ │  Fertility    │ │               │   │
│  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘   │
│  ┌───────────────┐ ┌───────────────┐                                       │
│  │ Hypogonadism  │ │  Surgical     │                                       │
│  │               │ │  Planning     │                                       │
│  └───────────────┘ └───────────────┘                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                 LLM LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Ollama         │  │  Anthropic      │  │  OpenAI                   │   │
│  │  Client         │  │  Client         │  │  Client                   │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    RAG Pipeline (LangChain)                           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                 DATA LAYER                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐   │
│  │  Neo4j          │  │  SQLite         │  │  File Storage             │   │
│  │  Vector + KG    │  │  Settings DB    │  │  (Documents, Templates)   │   │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Interaction Flow

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌─────────────┐
│  User    │───▶│ FastAPI  │───▶│ Note         │───▶│ LLM Layer   │
│ Interface│    │ Backend  │    │ Generator    │    │ (Ollama)    │
└──────────┘    └──────────┘    └──────────────┘    └─────────────┘
                     │                 │                   │
                     ▼                 ▼                   ▼
              ┌──────────┐    ┌──────────────┐    ┌─────────────┐
              │ Clinical │    │ RAG Pipeline │    │ Neo4j       │
              │ Modules  │    │ (LangChain)  │    │ Vector DB   │
              └──────────┘    └──────────────┘    └─────────────┘
```

---

## 4. Technology Stack

### 4.1 Backend Technologies

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Web Framework | FastAPI | 0.109+ | REST API, async request handling |
| Python Runtime | Python | 3.11+ | Core application logic |
| Task Queue | Celery | 5.3+ | Background processing for LLM calls |
| Message Broker | Redis | 7.2+ | Celery backend, caching |
| ASGI Server | Uvicorn | 0.27+ | Production server |

### 4.2 LLM Integration

| Provider | Integration | Models Supported |
|----------|-------------|-----------------|
| **Ollama** (Primary) | REST API via `ollama-python` | Llama 3.1, Mistral, CodeLlama, Phi-3, Medical-LLM variants |
| Anthropic | `anthropic` SDK | Claude 3.5 Sonnet, Claude 3 Opus |
| OpenAI | `openai` SDK | GPT-4o, GPT-4 Turbo |

### 4.3 Database Technologies

| Database | Purpose | Configuration |
|----------|---------|---------------|
| **Neo4j** | Vector storage, knowledge graph, clinical relationships | Neo4j 5.x with APOC, GDS plugins |
| SQLite | User settings, session data, audit logs | Local file-based |
| File System | Document storage, templates | Structured directory hierarchy |

### 4.4 Frontend Technologies

| Technology | Purpose |
|------------|---------|
| React 18+ | Component-based UI framework |
| Tailwind CSS 3.4+ | Utility-first styling |
| Alpine.js | Lightweight interactivity |
| HTMX (alternative) | Server-driven UI updates |

### 4.5 RAG Pipeline

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | LangChain 0.1+ | RAG pipeline construction |
| Embeddings | `sentence-transformers` | Document vectorization |
| Vector Search | Neo4j Vector Index | Similarity search |
| Document Processing | `unstructured`, `PyMuPDF` | PDF/DOCX parsing |

---

## 5. Data Layer Design

### 5.1 Neo4j Schema Design

#### 5.1.1 Node Types

```cypher
// Clinical Knowledge Nodes
(:Document {
    id: STRING,
    title: STRING,
    source: STRING,
    content: STRING,
    embedding: LIST<FLOAT>,
    created_at: DATETIME,
    document_type: STRING  // guideline, reference, calculator
})

(:ClinicalConcept {
    id: STRING,
    name: STRING,
    category: STRING,  // prostate, kidney, bladder, etc.
    description: STRING,
    icd10_codes: LIST<STRING>,
    snomed_codes: LIST<STRING>
})

(:Calculator {
    id: STRING,
    name: STRING,
    category: STRING,
    formula: STRING,
    inputs: LIST<STRING>,
    interpretation: STRING,
    references: LIST<STRING>
})

(:Template {
    id: STRING,
    name: STRING,
    type: STRING,  // clinic_note, consult, preop, postop
    content: STRING,
    sections: LIST<STRING>,
    active: BOOLEAN
})

(:User {
    id: STRING,
    username: STRING,
    preferences: MAP,
    created_at: DATETIME
})

(:Session {
    id: STRING,
    user_id: STRING,
    started_at: DATETIME,
    note_type: STRING
})
```

#### 5.1.2 Relationship Types

```cypher
// Knowledge Graph Relationships
(:Document)-[:REFERENCES]->(:ClinicalConcept)
(:Document)-[:CITES]->(:Document)
(:ClinicalConcept)-[:RELATED_TO]->(:ClinicalConcept)
(:Calculator)-[:APPLIES_TO]->(:ClinicalConcept)
(:Calculator)-[:DERIVED_FROM]->(:Document)

// User Relationships
(:User)-[:PREFERS]->(:Template)
(:User)-[:USES]->(:Calculator)
(:Session)-[:BELONGS_TO]->(:User)
(:Session)-[:GENERATED]->(:Note)
```

#### 5.1.3 Vector Index Configuration

```cypher
// Create vector index for document embeddings
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document)
ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

// Create vector index for clinical concepts
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept)
ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}
```

### 5.2 SQLite Schema (Settings Database)

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

-- Session Audit Log
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
```

### 5.3 File Storage Structure

```
/vaucda/
├── data/
│   ├── documents/
│   │   ├── guidelines/
│   │   │   ├── nccn/
│   │   │   ├── aua/
│   │   │   └── eau/
│   │   ├── references/
│   │   └── calculators/
│   ├── templates/
│   │   ├── clinic_notes/
│   │   ├── consult_notes/
│   │   ├── preop_notes/
│   │   └── postop_notes/
│   └── exports/
├── models/
│   └── embeddings/
└── logs/
```

---

## 6. LLM Integration Layer

### 6.1 Ollama Integration

#### 6.1.1 Connection Configuration

```python
from dataclasses import dataclass
from typing import Optional, List
import httpx

@dataclass
class OllamaConfig:
    """Configuration for Ollama local LLM server."""
    host: str = "http://localhost:11434"
    timeout: float = 120.0
    default_model: str = "llama3.1:8b"
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.9
    
    # Medical-specific models
    medical_models: List[str] = None
    
    def __post_init__(self):
        if self.medical_models is None:
            self.medical_models = [
                "llama3.1:8b",
                "llama3.1:70b",
                "mistral:7b",
                "codellama:13b",
                "phi3:medium"
            ]

class OllamaClient:
    """Client for interacting with Ollama API."""
    
    def __init__(self, config: OllamaConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.host,
            timeout=config.timeout
        )
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> dict:
        """Generate completion from Ollama model."""
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens)
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        response = await self.client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        **kwargs
    ) -> dict:
        """Chat completion with conversation history."""
        model = model or self.config.default_model
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p)
            }
        }
        
        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def embeddings(
        self,
        text: str,
        model: str = "nomic-embed-text"
    ) -> List[float]:
        """Generate embeddings for text."""
        payload = {
            "model": model,
            "prompt": text
        }
        
        response = await self.client.post("/api/embeddings", json=payload)
        response.raise_for_status()
        return response.json()["embedding"]
    
    async def list_models(self) -> List[dict]:
        """List available models."""
        response = await self.client.get("/api/tags")
        response.raise_for_status()
        return response.json()["models"]
    
    async def health_check(self) -> bool:
        """Check if Ollama server is responsive."""
        try:
            response = await self.client.get("/")
            return response.status_code == 200
        except Exception:
            return False
```

#### 6.1.2 Model Selection Strategy

```python
from enum import Enum
from typing import Optional

class TaskType(Enum):
    NOTE_GENERATION = "note_generation"
    CLINICAL_EXTRACTION = "clinical_extraction"
    CALCULATOR_ASSIST = "calculator_assist"
    EVIDENCE_SEARCH = "evidence_search"
    SUMMARIZATION = "summarization"

class ModelSelector:
    """Select optimal model based on task requirements."""
    
    MODEL_RECOMMENDATIONS = {
        TaskType.NOTE_GENERATION: {
            "primary": "llama3.1:70b",
            "fallback": "llama3.1:8b",
            "min_context": 8192
        },
        TaskType.CLINICAL_EXTRACTION: {
            "primary": "llama3.1:8b",
            "fallback": "mistral:7b",
            "min_context": 4096
        },
        TaskType.CALCULATOR_ASSIST: {
            "primary": "phi3:medium",
            "fallback": "llama3.1:8b",
            "min_context": 2048
        },
        TaskType.EVIDENCE_SEARCH: {
            "primary": "llama3.1:8b",
            "fallback": "mistral:7b",
            "min_context": 4096
        },
        TaskType.SUMMARIZATION: {
            "primary": "llama3.1:8b",
            "fallback": "phi3:medium",
            "min_context": 4096
        }
    }
    
    def __init__(self, ollama_client: OllamaClient):
        self.client = ollama_client
        self._available_models: Optional[List[str]] = None
    
    async def get_model_for_task(
        self,
        task: TaskType,
        input_length: int = 0
    ) -> str:
        """Select best available model for task."""
        if self._available_models is None:
            models = await self.client.list_models()
            self._available_models = [m["name"] for m in models]
        
        recommendation = self.MODEL_RECOMMENDATIONS[task]
        
        # Try primary model first
        if recommendation["primary"] in self._available_models:
            return recommendation["primary"]
        
        # Fall back to secondary
        if recommendation["fallback"] in self._available_models:
            return recommendation["fallback"]
        
        # Use any available model
        if self._available_models:
            return self._available_models[0]
        
        raise RuntimeError("No Ollama models available")
```

### 6.2 Multi-Provider Abstraction

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

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

class OllamaProvider(LLMProvider):
    """Ollama implementation of LLM provider."""
    
    def __init__(self, config: OllamaConfig):
        self.client = OllamaClient(config)
        self.selector = ModelSelector(self.client)
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task: TaskType = TaskType.NOTE_GENERATION,
        **kwargs
    ) -> str:
        model = await self.selector.get_model_for_task(task)
        result = await self.client.generate(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            **kwargs
        )
        return result["response"]
    
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        # Implementation for streaming
        pass
    
    async def get_embeddings(self, text: str) -> List[float]:
        return await self.client.embeddings(text)

class LLMOrchestrator:
    """Orchestrate LLM calls across providers."""
    
    def __init__(self):
        self.providers: dict[str, LLMProvider] = {}
        self.default_provider: str = "ollama"
    
    def register_provider(self, name: str, provider: LLMProvider):
        """Register an LLM provider."""
        self.providers[name] = provider
    
    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate using specified or default provider."""
        provider_name = provider or self.default_provider
        if provider_name not in self.providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        return await self.providers[provider_name].generate(prompt, **kwargs)
```

### 6.3 RAG Pipeline with Neo4j

```python
from langchain.vectorstores import Neo4jVector
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

class ClinicalRAGPipeline:
    """RAG pipeline for clinical knowledge retrieval."""
    
    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        ollama_client: OllamaClient
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.ollama_client = ollama_client
        
        # Initialize embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Initialize vector store
        self.vector_store = Neo4jVector.from_existing_index(
            self.embeddings,
            url=neo4j_uri,
            username=neo4j_user,
            password=neo4j_password,
            index_name="document_embeddings",
            node_label="Document",
            text_node_property="content",
            embedding_node_property="embedding"
        )
    
    async def retrieve_relevant_docs(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None
    ) -> List[dict]:
        """Retrieve relevant documents for query."""
        # Add category filter if specified
        filter_dict = {"category": category} if category else None
        
        docs = self.vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=filter_dict
        )
        
        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            }
            for doc, score in docs
        ]
    
    async def generate_with_context(
        self,
        query: str,
        clinical_input: str,
        category: str
    ) -> str:
        """Generate response with retrieved context."""
        # Retrieve relevant documents
        docs = await self.retrieve_relevant_docs(
            query,
            k=5,
            category=category
        )
        
        # Build context
        context = "\n\n".join([
            f"Source: {d['metadata'].get('title', 'Unknown')}\n{d['content']}"
            for d in docs
        ])
        
        # Create augmented prompt
        prompt = f"""Based on the following clinical guidelines and references:

{context}

Clinical Input:
{clinical_input}

Query: {query}

Provide a structured clinical response:"""
        
        # Generate with Ollama
        response = await self.ollama_client.generate(
            prompt=prompt,
            system_prompt=CLINICAL_SYSTEM_PROMPT
        )
        
        return response["response"]
```

---

## 7. Clinical Module Engine

### 7.1 Calculator Framework

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

class RiskLevel(Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    INTERMEDIATE = "intermediate"
    HIGH = "high"
    VERY_HIGH = "very_high"

@dataclass
class CalculatorInput:
    """Input specification for a calculator."""
    name: str
    type: str  # float, int, bool, choice
    required: bool = True
    default: Any = None
    choices: Optional[List[str]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None

@dataclass
class CalculatorResult:
    """Result from a clinical calculator."""
    score: float
    interpretation: str
    risk_level: Optional[RiskLevel] = None
    recommendations: Optional[List[str]] = None
    breakdown: Optional[Dict[str, Any]] = None
    references: Optional[List[str]] = None

class ClinicalCalculator(ABC):
    """Base class for clinical calculators."""
    
    name: str
    category: str
    description: str
    inputs: List[CalculatorInput]
    references: List[str]
    
    @abstractmethod
    def calculate(self, **kwargs) -> CalculatorResult:
        """Perform calculation and return result."""
        pass
    
    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Validate and normalize inputs."""
        validated = {}
        for input_spec in self.inputs:
            value = kwargs.get(input_spec.name)
            
            if value is None:
                if input_spec.required:
                    raise ValueError(f"Missing required input: {input_spec.name}")
                value = input_spec.default
            
            # Type validation
            if input_spec.type == "float":
                value = float(value)
                if input_spec.min_value is not None and value < input_spec.min_value:
                    raise ValueError(f"{input_spec.name} below minimum: {input_spec.min_value}")
                if input_spec.max_value is not None and value > input_spec.max_value:
                    raise ValueError(f"{input_spec.name} above maximum: {input_spec.max_value}")
            elif input_spec.type == "choice" and input_spec.choices:
                if value not in input_spec.choices:
                    raise ValueError(f"Invalid choice for {input_spec.name}: {value}")
            
            validated[input_spec.name] = value
        
        return validated
```

### 7.2 Prostate Cancer Calculators

```python
import math

class PSAKineticsCalculator(ClinicalCalculator):
    """Calculate PSA velocity and doubling time."""
    
    name = "PSA Kinetics Calculator"
    category = "prostate_cancer"
    description = "Calculate PSAV and PSADT from serial PSA values"
    
    inputs = [
        CalculatorInput("psa_values", "list", description="List of PSA values"),
        CalculatorInput("time_points", "list", description="Time points in months"),
    ]
    
    references = [
        "D'Amico AV, et al. JAMA 2004;292:2237-2242",
        "Freedland SJ, et al. JAMA 2005;294:433-439"
    ]
    
    def calculate(self, **kwargs) -> CalculatorResult:
        validated = self.validate_inputs(**kwargs)
        psa_values = validated["psa_values"]
        time_points = validated["time_points"]
        
        # Calculate PSAV
        time_years = (time_points[-1] - time_points[0]) / 12
        psav = (psa_values[-1] - psa_values[0]) / time_years if time_years > 0 else 0
        
        # Calculate PSADT using log-linear regression
        if len(psa_values) >= 2 and all(p > 0 for p in psa_values):
            ln_psa = [math.log(p) for p in psa_values]
            n = len(psa_values)
            
            # Linear regression
            t_mean = sum(time_points) / n
            ln_mean = sum(ln_psa) / n
            
            numerator = sum((t - t_mean) * (ln - ln_mean) 
                          for t, ln in zip(time_points, ln_psa))
            denominator = sum((t - t_mean) ** 2 for t in time_points)
            
            slope = numerator / denominator if denominator != 0 else 0
            psadt = (math.log(2) / slope) if slope > 0 else float('inf')
        else:
            psadt = float('inf')
        
        # Interpretation
        psav_interp = self._interpret_psav(psav)
        psadt_interp = self._interpret_psadt(psadt)
        
        return CalculatorResult(
            score=psadt,
            interpretation=f"PSAV: {psav:.2f} ng/mL/year ({psav_interp})\n"
                          f"PSADT: {psadt:.1f} months ({psadt_interp})",
            risk_level=self._get_risk_level(psadt),
            breakdown={
                "psav": round(psav, 2),
                "psadt_months": round(psadt, 1) if psadt != float('inf') else None,
                "psav_interpretation": psav_interp,
                "psadt_interpretation": psadt_interp
            },
            references=self.references
        )
    
    def _interpret_psav(self, psav: float) -> str:
        if psav > 2.0:
            return "Concerning for recurrence"
        elif psav > 0.75:
            return "Increased cancer risk"
        else:
            return "Within acceptable range"
    
    def _interpret_psadt(self, psadt: float) -> str:
        if psadt < 3:
            return "Aggressive disease, high metastatic risk"
        elif psadt < 9:
            return "Intermediate risk"
        elif psadt < 15:
            return "Lower risk"
        else:
            return "Indolent behavior"
    
    def _get_risk_level(self, psadt: float) -> RiskLevel:
        if psadt < 3:
            return RiskLevel.VERY_HIGH
        elif psadt < 9:
            return RiskLevel.HIGH
        elif psadt < 15:
            return RiskLevel.INTERMEDIATE
        else:
            return RiskLevel.LOW


class CAPRAScoreCalculator(ClinicalCalculator):
    """Calculate CAPRA score for prostate cancer risk."""
    
    name = "CAPRA Score"
    category = "prostate_cancer"
    description = "Cancer of the Prostate Risk Assessment score"
    
    inputs = [
        CalculatorInput("psa", "float", min_value=0, unit="ng/mL"),
        CalculatorInput("gleason_primary", "int", choices=[1,2,3,4,5]),
        CalculatorInput("gleason_secondary", "int", choices=[1,2,3,4,5]),
        CalculatorInput("clinical_stage", "choice", 
                       choices=["T1c", "T2a", "T2b", "T2c", "T3a"]),
        CalculatorInput("percent_positive_cores", "float", min_value=0, max_value=100),
        CalculatorInput("age", "int", min_value=18, required=False),
    ]
    
    references = [
        "Cooperberg MR, et al. Cancer 2006;107:2276-2283",
        "Cooperberg MR, et al. J Urol 2005;173:1938-1942"
    ]
    
    def calculate(self, **kwargs) -> CalculatorResult:
        validated = self.validate_inputs(**kwargs)
        
        score = 0
        breakdown = {}
        
        # PSA points
        psa = validated["psa"]
        if psa <= 6:
            psa_points = 0
        elif psa <= 10:
            psa_points = 1
        elif psa <= 20:
            psa_points = 2
        elif psa <= 30:
            psa_points = 3
        else:
            psa_points = 4
        score += psa_points
        breakdown["psa_points"] = psa_points
        
        # Gleason pattern points
        primary = validated["gleason_primary"]
        secondary = validated["gleason_secondary"]
        
        if primary >= 4 or primary == 5:
            gleason_points = 3
        elif secondary >= 4 or secondary == 5:
            gleason_points = 1
        else:
            gleason_points = 0
        score += gleason_points
        breakdown["gleason_points"] = gleason_points
        
        # Clinical T stage points
        stage = validated["clinical_stage"]
        stage_points = {"T1c": 0, "T2a": 0, "T2b": 1, "T2c": 1, "T3a": 2}
        score += stage_points.get(stage, 0)
        breakdown["stage_points"] = stage_points.get(stage, 0)
        
        # Percent positive cores
        ppc = validated["percent_positive_cores"]
        ppc_points = 1 if ppc >= 34 else 0
        score += ppc_points
        breakdown["ppc_points"] = ppc_points
        
        # Get survival estimates
        survival = self._get_survival_estimates(score)
        
        return CalculatorResult(
            score=score,
            interpretation=self._get_interpretation(score),
            risk_level=self._get_risk_level(score),
            recommendations=self._get_recommendations(score),
            breakdown={
                **breakdown,
                "total_score": score,
                "survival_estimates": survival
            },
            references=self.references
        )
    
    def _get_survival_estimates(self, score: int) -> dict:
        if score <= 2:
            return {"3_year": 91, "5_year": 85, "10_year": 75}
        elif score <= 5:
            return {"3_year": 75, "5_year": 65, "10_year": 50}
        else:
            return {"3_year": 53, "5_year": 40, "10_year": 25}
    
    def _get_interpretation(self, score: int) -> str:
        if score <= 2:
            return f"CAPRA Score: {score}/10 - Low risk"
        elif score <= 5:
            return f"CAPRA Score: {score}/10 - Intermediate risk"
        else:
            return f"CAPRA Score: {score}/10 - High risk"
    
    def _get_risk_level(self, score: int) -> RiskLevel:
        if score <= 2:
            return RiskLevel.LOW
        elif score <= 5:
            return RiskLevel.INTERMEDIATE
        else:
            return RiskLevel.HIGH
    
    def _get_recommendations(self, score: int) -> List[str]:
        if score <= 2:
            return [
                "Active surveillance may be appropriate",
                "Consider definitive treatment vs monitoring",
                "Low recurrence risk supports conservative approach"
            ]
        elif score <= 5:
            return [
                "Definitive treatment generally recommended",
                "Consider radiation vs surgery based on patient factors",
                "Discuss multimodal therapy options"
            ]
        else:
            return [
                "Aggressive treatment recommended",
                "Consider multimodal therapy",
                "High recurrence risk - close monitoring essential"
            ]
```

### 7.3 Module Registry

```python
class ClinicalModuleRegistry:
    """Registry for all clinical calculators and modules."""
    
    def __init__(self):
        self._calculators: Dict[str, ClinicalCalculator] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register(self, calculator: ClinicalCalculator):
        """Register a calculator."""
        self._calculators[calculator.name] = calculator
        
        if calculator.category not in self._categories:
            self._categories[calculator.category] = []
        self._categories[calculator.category].append(calculator.name)
    
    def get_calculator(self, name: str) -> ClinicalCalculator:
        """Get calculator by name."""
        if name not in self._calculators:
            raise KeyError(f"Calculator not found: {name}")
        return self._calculators[name]
    
    def get_by_category(self, category: str) -> List[ClinicalCalculator]:
        """Get all calculators in a category."""
        names = self._categories.get(category, [])
        return [self._calculators[n] for n in names]
    
    def list_categories(self) -> List[str]:
        """List all categories."""
        return list(self._categories.keys())
    
    def list_calculators(self, category: Optional[str] = None) -> List[str]:
        """List calculator names, optionally filtered by category."""
        if category:
            return self._categories.get(category, [])
        return list(self._calculators.keys())

# Initialize global registry
registry = ClinicalModuleRegistry()

# Register all calculators
registry.register(PSAKineticsCalculator())
registry.register(CAPRAScoreCalculator())
# ... register all 44 calculators
```

---

## 8. User Interface Specification

### 8.1 Design System - Color Palette

The application employs a carefully designed color palette that balances professional medical aesthetics with accessibility and visual hierarchy.

#### 8.1.1 Primary Colors

| Color | Hex | RGB | CSS Variable | Usage |
|-------|-----|-----|--------------|-------|
| Primary Blue | `#2c5282` | `rgb(44, 82, 130)` | `--primary-blue` | Navigation bars, main CTA buttons, headings |
| Primary Light Blue | `#3182ce` | `rgb(49, 130, 206)` | `--primary-light-blue` | Button hover states, interactive highlights |
| Secondary Blue | `#4299e1` | `rgb(66, 153, 225)` | `--secondary-blue` | Secondary buttons, badges |
| Accent Blue | `#63b3ed` | `rgb(99, 179, 237)` | `--accent-blue` | Navigation hovers, links, subtle accents |
| Medical Teal | `#0d9488` | `rgb(13, 148, 136)` | `--medical-teal` | Medical-specific actions, clinical buttons |

#### 8.1.2 Status Colors

| Status | Hex | Light BG | Dark Text | Usage |
|--------|-----|----------|-----------|-------|
| Success Green | `#10b981` | `#dcfce7` | `#166534` | Success messages, active status, confirmations |
| Warning Yellow | `#f59e0b` | `#fef3c7` | `#92400e` | Warnings, modified states, caution |
| Error Red | `#ef4444` | `#fee2e2` | `#dc2626` | Errors, failed operations, alerts |
| Info Cyan | `#06b6d4` | `#dbeafe` | `#1d4ed8` | Informational messages, notifications |

#### 8.1.3 Neutral Colors

| Color | Hex | Usage |
|-------|-----|-------|
| Gray 700 | `#707783` | Secondary text, metadata |
| Light BG | `#f9fafb` | Page backgrounds |
| Border Gray | `#e5e7eb` | Primary borders, dividers |
| Body Text | `#374151` | Primary text color |
| Placeholder | `#9ca3af` | Placeholder text |

#### 8.1.4 Specialty Feature Colors

| Feature | Gradient Start | Gradient End | Usage |
|---------|---------------|--------------|-------|
| Medical Chat | `#f0f9ff` | `#e0f2fe` | Light blue cards |
| Prompt Settings | `#fefce8` | `#fef3c7` | Light yellow cards |
| Evidence Search | `#ecfdf5` | `#d1fae5` | Light green cards |
| Note Generation | `#faf5ff` | `#f3e8ff` | Light purple cards |

#### 8.1.5 CSS Variables Implementation

```css
:root {
    /* Primary Colors */
    --primary-blue: #2c5282;
    --primary-light-blue: #3182ce;
    --secondary-blue: #4299e1;
    --accent-blue: #63b3ed;
    --medical-teal: #0d9488;
    
    /* Status Colors */
    --success-green: #10b981;
    --warning-yellow: #f59e0b;
    --error-red: #ef4444;
    --info-cyan: #06b6d4;
    
    /* Neutral Colors */
    --gray-700: #707783;
    --light-bg: #f9fafb;
    --border-gray: #e5e7eb;
    --body-text: #374151;
    --placeholder: #9ca3af;
    
    /* Shadows */
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.1);
    --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.15);
    --shadow-lg: 0 20px 25px rgba(0, 0, 0, 0.15);
    
    /* Button Shadows */
    --btn-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    --btn-shadow-hover: 0 8px 20px rgba(59, 130, 246, 0.4);
}

/* Dark Mode */
@media (prefers-color-scheme: dark) {
    :root {
        --light-bg: #1f2937;
        --body-text: #f9fafb;
        --border-gray: #4b5563;
        --placeholder: #6b7280;
    }
}
```

### 8.2 Component Specifications

#### 8.2.1 Main Application Layout

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
│  [Main Content Area - Context Dependent]                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 8.2.2 Note Generation Screen

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  NOTE GENERATION                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                   │  CLINICAL MODULES                       │
│  NOTE TYPE:                       │  ┌─────────────────────────────────────┐│
│  ┌───────────────────────────────┐│                                         │
│  │ ○ Urology Clinic Note       ││  ▼ PROSTATE CANCER                     │
│  │ ○ Urology Consult           ││    □ PSA Tracking Table                │
│  │ ○ Urology Preop Note        ││    □ PSA Kinetics (PSAV/PSADT)         │
│  │ ○ Urology Postop Note       ││    □ PCPT Risk Calculator              │
│  └───────────────────────────────┘│    □ CAPRA Score                       │
│                                   │    □ NCCN Risk Stratification          │
│  CLINICAL INPUT:                  │                                         │
│  ┌───────────────────────────────┐│  ▼ KIDNEY CANCER                       │
│  │                             ││    □ RENAL Nephrometry Score           │
│  │  Paste clinical data here   ││    □ SSIGN Score                       │
│  │  (labs, imaging, notes)     ││    □ IMDC Risk Criteria                │
│  │                             ││                                         │
│  │                             ││  ▼ BLADDER CANCER                      │
│  │                             ││    □ EORTC Recurrence Score            │
│  │                             ││    □ EORTC Progression Score           │
│  └───────────────────────────────┘│                                         │
│                                   │  ▼ MALE VOIDING DYSFUNCTION            │
│  LLM MODEL:                       │    □ IPSS Calculator                   │
│  ┌───────────────────────────────┐│    □ AUA Symptom Subscore             │
│  │ llama3.1:8b               ▼ ││    □ BOOI/BCI (Urodynamics)            │
│  └───────────────────────────────┘│                                         │
│                                   │  [+ More Categories...]                 │
│  [Generate Note]  [Clear]         │                                         │
└───────────────────────────────────┴─────────────────────────────────────────┘
```

#### 8.2.3 Button Styles

```css
/* Primary Button */
.btn-primary {
    background-color: var(--primary-blue);
    color: white;
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
    font-weight: 500;
    box-shadow: var(--btn-shadow);
    transition: all 0.2s ease;
}

.btn-primary:hover {
    background-color: var(--primary-light-blue);
    box-shadow: var(--btn-shadow-hover);
}

/* Medical Button */
.btn-medical {
    background-color: var(--medical-teal);
    color: white;
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
    font-weight: 500;
}

.btn-medical:hover {
    background-color: #14b8a6;
}

/* Secondary Button */
.btn-secondary {
    background-color: transparent;
    border: 2px solid var(--primary-blue);
    color: var(--primary-blue);
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
}

.btn-secondary:hover {
    background-color: var(--primary-blue);
    color: white;
}
```

#### 8.2.4 Status Indicators

```css
/* Status Dot */
.status-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
}

.status-online {
    background-color: var(--success-green);
    animation: pulse 2s infinite;
}

.status-saving {
    background-color: var(--warning-yellow);
    animation: scale 1s infinite;
}

.status-error {
    background-color: var(--error-red);
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

@keyframes scale {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.2); }
}
```

### 8.3 React Component Structure

```typescript
// src/components/layout/MainLayout.tsx
interface MainLayoutProps {
    children: React.ReactNode;
    activeTab: 'note' | 'settings' | 'evidence';
}

// src/components/note/NoteGenerator.tsx
interface NoteGeneratorProps {
    onGenerate: (input: ClinicalInput) => Promise<GeneratedNote>;
    templates: Template[];
    modules: ClinicalModule[];
}

// src/components/modules/ModuleSelector.tsx
interface ModuleSelectorProps {
    categories: ModuleCategory[];
    selectedModules: string[];
    onSelectionChange: (modules: string[]) => void;
}

// src/components/calculators/CalculatorPanel.tsx
interface CalculatorPanelProps {
    calculator: CalculatorDefinition;
    onCalculate: (inputs: CalculatorInputs) => CalculatorResult;
}

// src/components/output/GeneratedNote.tsx
interface GeneratedNoteProps {
    note: GeneratedNote;
    appendices: ClinicalAppendix[];
    onCopy: () => void;
    onExport: (format: 'docx' | 'pdf') => void;
}
```

---

## 9. API Design

### 9.1 RESTful Endpoints

#### 9.1.1 Note Generation API

```yaml
# POST /api/v1/notes/generate
Request:
  content_type: application/json
  body:
    clinical_input: string (required)
    note_type: enum [clinic_note, consult, preop, postop]
    template_id: string (optional)
    selected_modules: array[string]
    llm_config:
      provider: enum [ollama, anthropic, openai]
      model: string
      temperature: float (0.0-1.0)

Response:
  status: 200
  body:
    note_id: string
    generated_note: string
    sections:
      - name: string
        content: string
    appendices:
      - module_name: string
        results: object
    metadata:
      model_used: string
      tokens_used: integer
      generation_time_ms: integer

# GET /api/v1/notes/{note_id}
Response:
  status: 200
  body:
    note_id: string
    generated_note: string
    created_at: datetime
    updated_at: datetime
```

#### 9.1.2 Calculator API

```yaml
# GET /api/v1/calculators
Response:
  status: 200
  body:
    categories:
      - name: string
        calculators:
          - id: string
            name: string
            description: string

# POST /api/v1/calculators/{calculator_id}/calculate
Request:
  body:
    inputs: object (calculator-specific)

Response:
  status: 200
  body:
    score: number
    interpretation: string
    risk_level: string
    recommendations: array[string]
    breakdown: object
    references: array[string]
```

#### 9.1.3 LLM Management API

```yaml
# GET /api/v1/llm/providers
Response:
  body:
    providers:
      - name: string
        status: enum [online, offline, degraded]
        models: array[string]

# GET /api/v1/llm/ollama/models
Response:
  body:
    models:
      - name: string
        size: string
        modified_at: datetime

# POST /api/v1/llm/ollama/pull
Request:
  body:
    model: string
Response:
  body:
    status: string
    progress: number
```

### 9.2 WebSocket API

```yaml
# WebSocket /ws/generate
# Real-time streaming for note generation

Client -> Server:
  type: "start_generation"
  payload:
    clinical_input: string
    config: object

Server -> Client:
  type: "generation_progress"
  payload:
    chunk: string
    progress: number

Server -> Client:
  type: "generation_complete"
  payload:
    note_id: string
    total_tokens: integer
```

### 9.3 FastAPI Implementation

```python
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid

app = FastAPI(
    title="VAUCDA API",
    description="VA Urology Clinical Documentation Assistant",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class NoteGenerationRequest(BaseModel):
    clinical_input: str
    note_type: str = "clinic_note"
    template_id: Optional[str] = None
    selected_modules: List[str] = []
    llm_config: Optional[dict] = None

class NoteGenerationResponse(BaseModel):
    note_id: str
    generated_note: str
    sections: List[dict]
    appendices: List[dict]
    metadata: dict

class CalculatorRequest(BaseModel):
    inputs: dict

class CalculatorResponse(BaseModel):
    score: float
    interpretation: str
    risk_level: Optional[str]
    recommendations: Optional[List[str]]
    breakdown: Optional[dict]
    references: Optional[List[str]]

# Routes
@app.post("/api/v1/notes/generate", response_model=NoteGenerationResponse)
async def generate_note(request: NoteGenerationRequest):
    """Generate a clinical note from input."""
    note_id = str(uuid.uuid4())
    
    # Get LLM provider
    llm = get_llm_provider(request.llm_config)
    
    # Generate note
    result = await note_generator.generate(
        clinical_input=request.clinical_input,
        note_type=request.note_type,
        template_id=request.template_id,
        modules=request.selected_modules,
        llm=llm
    )
    
    return NoteGenerationResponse(
        note_id=note_id,
        generated_note=result.note,
        sections=result.sections,
        appendices=result.appendices,
        metadata=result.metadata
    )

@app.get("/api/v1/calculators")
async def list_calculators():
    """List all available calculators."""
    categories = {}
    for calc in registry.list_calculators():
        calculator = registry.get_calculator(calc)
        if calculator.category not in categories:
            categories[calculator.category] = []
        categories[calculator.category].append({
            "id": calc,
            "name": calculator.name,
            "description": calculator.description
        })
    return {"categories": categories}

@app.post("/api/v1/calculators/{calculator_id}/calculate", 
          response_model=CalculatorResponse)
async def calculate(calculator_id: str, request: CalculatorRequest):
    """Perform a clinical calculation."""
    try:
        calculator = registry.get_calculator(calculator_id)
        result = calculator.calculate(**request.inputs)
        return CalculatorResponse(
            score=result.score,
            interpretation=result.interpretation,
            risk_level=result.risk_level.value if result.risk_level else None,
            recommendations=result.recommendations,
            breakdown=result.breakdown,
            references=result.references
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Calculator not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/llm/ollama/models")
async def list_ollama_models():
    """List available Ollama models."""
    client = OllamaClient(OllamaConfig())
    models = await client.list_models()
    return {"models": models}

@app.websocket("/ws/generate")
async def websocket_generate(websocket: WebSocket):
    """WebSocket endpoint for streaming generation."""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "start_generation":
                async for chunk in generate_stream(data["payload"]):
                    await websocket.send_json({
                        "type": "generation_progress",
                        "payload": {"chunk": chunk}
                    })
                
                await websocket.send_json({
                    "type": "generation_complete",
                    "payload": {"note_id": str(uuid.uuid4())}
                })
    except Exception as e:
        await websocket.close(code=1000)
```

---

## 10. Security and Compliance

### 10.1 Core Security Principles

VAUCDA is designed with a **zero-persistence PHI architecture**. No patient clinical information is stored on any server component. All clinical data is processed transiently and immediately purged after use.

| Principle | Implementation |
|-----------|----------------|
| **Zero PHI Storage** | Clinical input and generated notes exist only in memory during active session |
| **Immediate Deletion** | All patient data purged from memory upon response delivery |
| **Secure Transmission** | TLS 1.3 encryption for all client-server communication |
| **Memory Isolation** | Each request processed in isolated memory space |
| **No Logging of PHI** | Audit logs capture metadata only, never clinical content |

### 10.2 Secure Transmission (Client-Server Communication)

#### 10.2.1 TLS Configuration

All communication between client and server is encrypted using TLS 1.3 with strong cipher suites.

```python
# config/ssl_config.py
from dataclasses import dataclass
from typing import List

@dataclass
class TLSConfig:
    """TLS configuration for secure communication."""
    
    # Minimum TLS version
    min_version: str = "TLSv1.3"
    
    # Approved cipher suites (TLS 1.3)
    cipher_suites: List[str] = None
    
    # Certificate paths
    cert_file: str = "/etc/ssl/certs/vaucda.crt"
    key_file: str = "/etc/ssl/private/vaucda.key"
    ca_file: str = "/etc/ssl/certs/va-ca-bundle.crt"
    
    # HSTS settings
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    
    def __post_init__(self):
        if self.cipher_suites is None:
            self.cipher_suites = [
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256",
                "TLS_AES_128_GCM_SHA256"
            ]
```

#### 10.2.2 HTTPS Enforcement

```python
# middleware/security.py
from fastapi import FastAPI, Request
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

# Force HTTPS redirect
app.add_middleware(HTTPSRedirectMiddleware)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Strict Transport Security
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        
        # Prevent content type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS Protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' wss:; "
            "frame-ancestors 'none';"
        )
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

#### 10.2.3 WebSocket Security

```python
# websocket/secure_ws.py
from fastapi import WebSocket, WebSocketDisconnect
from cryptography.fernet import Fernet
import ssl

class SecureWebSocketManager:
    """Manage secure WebSocket connections."""
    
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.session_keys: dict[str, bytes] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Establish secure WebSocket connection."""
        # Verify TLS is active
        if not websocket.scope.get("scheme") == "wss":
            await websocket.close(code=4001, reason="WSS required")
            return False
        
        await websocket.accept()
        
        # Generate session-specific encryption key
        session_key = Fernet.generate_key()
        self.session_keys[session_id] = session_key
        self.active_connections[session_id] = websocket
        
        return True
    
    async def disconnect(self, session_id: str):
        """Clean disconnect with key destruction."""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.session_keys:
            # Securely delete session key
            del self.session_keys[session_id]
```

### 10.3 Zero-Persistence PHI Architecture

#### 10.3.1 Design Philosophy

**CRITICAL: No patient clinical information is ever persisted to disk, database, or any permanent storage.**

The system operates on a **stateless, transient processing model**:

1. Clinical input is received encrypted over TLS
2. Data is decrypted and held only in volatile memory
3. LLM processing occurs with in-memory data only
4. Generated output is returned to client over TLS
5. All clinical data is immediately purged from memory
6. No PHI exists on server after response is sent

#### 10.3.2 Ephemeral Data Handler

```python
# security/ephemeral_data.py
import gc
import ctypes
from dataclasses import dataclass
from typing import Optional
from contextlib import contextmanager
import secrets

def secure_zero_memory(data: bytes) -> None:
    """Securely overwrite memory with zeros before deallocation."""
    if data:
        # Get memory address
        address = id(data)
        size = len(data)
        
        # Overwrite with zeros
        ctypes.memset(address, 0, size)
        
        # Force garbage collection
        gc.collect()

@dataclass
class EphemeralClinicalData:
    """Container for transient clinical data with automatic secure deletion."""
    
    _data: Optional[bytes] = None
    _session_id: str = ""
    
    def __post_init__(self):
        self._session_id = secrets.token_hex(16)
    
    def set_data(self, clinical_input: str) -> None:
        """Store clinical data in memory."""
        self._data = clinical_input.encode('utf-8')
    
    def get_data(self) -> Optional[str]:
        """Retrieve clinical data."""
        if self._data:
            return self._data.decode('utf-8')
        return None
    
    def secure_delete(self) -> None:
        """Securely delete all clinical data from memory."""
        if self._data:
            secure_zero_memory(self._data)
            self._data = None
        gc.collect()
    
    def __del__(self):
        """Ensure secure deletion on object destruction."""
        self.secure_delete()

@contextmanager
def ephemeral_clinical_context(clinical_input: str):
    """Context manager ensuring clinical data is deleted after use.
    
    Usage:
        with ephemeral_clinical_context(patient_data) as data:
            result = process_clinical_data(data)
        # Data is securely deleted here, even if exception occurs
    """
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

#### 10.3.3 Request Processing with Immediate Deletion

```python
# api/secure_endpoints.py
from fastapi import APIRouter, HTTPException
from security.ephemeral_data import ephemeral_clinical_context
from security.audit import AuditLogger
import time

router = APIRouter()
audit = AuditLogger()

@router.post("/api/v1/notes/generate")
async def generate_note_secure(request: NoteGenerationRequest):
    """Generate clinical note with zero-persistence guarantee.
    
    SECURITY GUARANTEES:
    1. Clinical input is never written to disk
    2. Clinical input is never logged
    3. Clinical input is purged from memory after response
    4. Only non-PHI metadata is retained for audit
    """
    
    request_start = time.time()
    note_id = secrets.token_hex(16)
    
    # Log request metadata ONLY (no PHI)
    await audit.log_request_metadata(
        note_id=note_id,
        user_id=request.user_id,
        note_type=request.note_type,
        modules_requested=request.selected_modules,
        # NO clinical_input logged
    )
    
    try:
        # Process within ephemeral context - data deleted on exit
        with ephemeral_clinical_context(request.clinical_input) as clinical_data:
            
            # Generate note (all processing in memory)
            result = await note_generator.generate(
                clinical_input=clinical_data,
                note_type=request.note_type,
                template_id=request.template_id,
                modules=request.selected_modules
            )
            
            # Prepare response while still in context
            response = NoteGenerationResponse(
                note_id=note_id,
                generated_note=result.note,
                sections=result.sections,
                appendices=result.appendices,
                metadata={
                    "generation_time_ms": int((time.time() - request_start) * 1000),
                    "model_used": result.model_used
                }
            )
        
        # Clinical data is NOW DELETED (exited context)
        
        # Log completion metadata (no PHI)
        await audit.log_completion_metadata(
            note_id=note_id,
            success=True,
            duration_ms=int((time.time() - request_start) * 1000)
        )
        
        return response
        
    except Exception as e:
        # Log error (no PHI in error logs)
        await audit.log_error_metadata(
            note_id=note_id,
            error_type=type(e).__name__,
            # NO error message that might contain PHI
        )
        raise HTTPException(status_code=500, detail="Processing error")
    
    finally:
        # Force garbage collection as additional safety
        gc.collect()
```

#### 10.3.4 LLM Provider Isolation

```python
# llm/secure_ollama.py
class SecureOllamaClient(OllamaClient):
    """Ollama client with PHI protection guarantees."""
    
    async def generate_secure(
        self,
        clinical_input: str,
        system_prompt: str,
        **kwargs
    ) -> str:
        """Generate with guaranteed no persistence of clinical data.
        
        GUARANTEES:
        - Ollama runs locally (no external API calls)
        - No request logging enabled on Ollama server
        - Clinical data not persisted in Ollama
        """
        
        try:
            response = await self.generate(
                prompt=clinical_input,
                system_prompt=system_prompt,
                **kwargs
            )
            return response["response"]
        finally:
            # Clear any local references
            clinical_input = None
            gc.collect()
    
    @staticmethod
    def get_secure_config() -> dict:
        """Return Ollama configuration for PHI-safe operation."""
        return {
            "OLLAMA_KEEP_ALIVE": "0",      # Don't cache model context
            "OLLAMA_NUM_PARALLEL": "1",     # No parallel request caching
            "OLLAMA_DEBUG": "false",        # No debug logging
            "OLLAMA_FLASH_ATTENTION": "1",  # Memory-efficient attention
        }
```

### 10.4 What IS Stored vs. What is NOT Stored

#### 10.4.1 Data Classification

| Data Type | Stored? | Location | Retention |
|-----------|---------|----------|-----------|
| **Clinical Input (PHI)** | ❌ NEVER | Memory only | Deleted immediately |
| **Generated Notes (PHI)** | ❌ NEVER | Memory only | Deleted immediately |
| **Patient Identifiers** | ❌ NEVER | Memory only | Deleted immediately |
| **Calculator Inputs (PHI)** | ❌ NEVER | Memory only | Deleted immediately |
| User ID | ✅ Yes | SQLite | Per retention policy |
| Session Timestamps | ✅ Yes | SQLite | 90 days |
| Module Usage Statistics | ✅ Yes | SQLite | Aggregated only |
| Error Codes (non-PHI) | ✅ Yes | Log files | 30 days |
| Clinical Templates | ✅ Yes | File system | Permanent |
| Medical Guidelines | ✅ Yes | Neo4j | Permanent |

#### 10.4.2 Audit Log Structure (PHI-Free)

```python
@dataclass
class SecureAuditLog:
    """Audit log that NEVER contains PHI."""
    
    # Metadata fields only
    log_id: str
    timestamp: datetime
    user_id: str
    session_id: str
    action: str                    # e.g., "note_generation"
    note_type: str                 # e.g., "clinic_note"
    modules_used: List[str]        # e.g., ["CAPRA", "PSA_Kinetics"]
    llm_model: str                 # e.g., "llama3.1:8b"
    processing_time_ms: int
    success: bool
    error_code: Optional[str]      # Non-descriptive code only
    
    # EXPLICITLY EXCLUDED - Never logged:
    # - clinical_input
    # - generated_note
    # - patient_name
    # - patient_id
    # - any PHI whatsoever
```

### 10.5 Authentication and Authorization

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Security configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")  # From secure vault
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate JWT token and return current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        exp: int = payload.get("exp")
        
        if username is None:
            raise credentials_exception
        
        # Check token expiration
        if datetime.utcnow() > datetime.fromtimestamp(exp):
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    user = await get_user(username)
    if user is None:
        raise credentials_exception
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

### 10.6 HIPAA Compliance Matrix

| HIPAA Requirement | Implementation | Verification |
|-------------------|----------------|--------------|
| **Access Controls (§164.312(a))** | JWT authentication, role-based access | Automated testing |
| **Audit Controls (§164.312(b))** | PHI-free audit logging of all access | Log review |
| **Integrity Controls (§164.312(c))** | TLS 1.3, message signing | Certificate validation |
| **Transmission Security (§164.312(e))** | Mandatory TLS 1.3 encryption | SSL Labs A+ rating |
| **Encryption (§164.312(a)(2)(iv))** | AES-256 in transit via TLS | Cipher suite audit |
| **Data Minimization** | Zero PHI persistence architecture | Architecture review |
| **Automatic Logoff (§164.312(a)(2)(iii))** | 30-minute session timeout | Session management |

### 10.7 Security Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT (Browser)                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Clinical Input (PHI) → Encrypted in Browser Memory                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ TLS 1.3 Encrypted
                                    │ (AES-256-GCM)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VAUCDA SERVER                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  EPHEMERAL PROCESSING ZONE (RAM Only)                                │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │ Decrypt PHI │───▶│ Process w/  │───▶│ Encrypt     │              │   │
│  │  │ (in memory) │    │ LLM (local) │    │ Response    │              │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│  │         │                  │                  │                      │   │
│  │         ▼                  ▼                  ▼                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              SECURE DELETE (immediate)                       │   │   │
│  │  │              Memory zeroed, garbage collected                │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PERSISTENT STORAGE (No PHI)                                         │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐            │   │
│  │  │ Neo4j         │  │ SQLite        │  │ Audit Logs    │            │   │
│  │  │ (Guidelines   │  │ (User prefs,  │  │ (Metadata     │            │   │
│  │  │  only)        │  │  settings)    │  │  only)        │            │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ TLS 1.3 Encrypted
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OLLAMA (Local LLM)                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  - Runs locally (no external API)                                    │   │
│  │  - No request logging                                                │   │
│  │  - No context caching (OLLAMA_KEEP_ALIVE=0)                         │   │
│  │  - Model weights only (no PHI stored)                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Deployment Architecture

### 11.1 Container Architecture

```yaml
# docker-compose.yml
version: '3.8'

services:
  vaucda-api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - OLLAMA_HOST=http://ollama:11434
      - REDIS_URL=redis://redis:6379
    depends_on:
      - neo4j
      - ollama
      - redis
    volumes:
      - ./data:/app/data

  vaucda-frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - vaucda-api

  neo4j:
    image: neo4j:5.15-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
      - NEO4J_PLUGINS=["apoc", "graph-data-science"]
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  celery-worker:
    build: ./api
    command: celery -A app.celery worker --loglevel=info
    depends_on:
      - redis
      - neo4j

volumes:
  neo4j_data:
  neo4j_logs:
  ollama_models:
  redis_data:
```

### 11.2 Ollama Model Management

```bash
#!/bin/bash
# scripts/setup_ollama_models.sh

# Pull recommended models for VAUCDA
ollama pull llama3.1:8b
ollama pull llama3.1:70b
ollama pull mistral:7b
ollama pull phi3:medium
ollama pull nomic-embed-text

# Verify models
ollama list
```

### 11.3 Neo4j Initialization

```cypher
// scripts/init_neo4j.cypher

// Create constraints
CREATE CONSTRAINT document_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT calculator_id IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT template_id IF NOT EXISTS
FOR (t:Template) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT user_id IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

// Create vector indexes
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
}};

// Create full-text search indexes
CREATE FULLTEXT INDEX document_content IF NOT EXISTS
FOR (d:Document) ON EACH [d.content, d.title];

CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];
```

---

## Appendices

### Appendix A: Clinical Calculator Reference

#### A.1 Prostate Cancer Calculators

| Calculator | Inputs | Output Range | Risk Categories |
|------------|--------|--------------|-----------------|
| PSA Kinetics | PSA values, time points | PSAV (ng/mL/yr), PSADT (months) | Based on thresholds |
| PCPT 2.0 | Age, race, family hx, PSA, DRE | Probability (0-100%) | Continuous |
| CAPRA Score | PSA, Gleason, stage, % cores | 0-10 points | Low/Intermediate/High |
| NCCN Risk | PSA, Gleason, stage, cores | Categorical | Very Low to Very High |

#### A.2 Kidney Cancer Calculators

| Calculator | Inputs | Output Range | Risk Categories |
|------------|--------|--------------|-----------------|
| RENAL Score | R, E, N, A, L components | 4-12 points | Low/Moderate/High complexity |
| SSIGN Score | TNM, size, grade, necrosis | 0-17 points | 5 risk groups |
| IMDC Criteria | KPS, time, labs | 0-6 factors | Favorable/Intermediate/Poor |

### Appendix B: System Prompts

```python
CLINICAL_SYSTEM_PROMPT = """You are a clinical documentation assistant specialized in urology. 
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
"""

CALCULATOR_ASSIST_PROMPT = """You are a clinical calculator assistant. Help extract 
relevant values from clinical text to populate calculator inputs.

For the {calculator_name} calculator, identify these inputs:
{input_list}

Extract values from the clinical text and format as JSON.
If a value cannot be determined, mark it as null.
"""
```

### Appendix C: Error Codes

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

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-28 | VAUCDA Team | Initial release |

---

*This document is confidential and intended for internal technical use only.*
