# VAUCDA API Specification
**Complete REST API and WebSocket Documentation**

Version: 1.0
Date: November 28, 2025

---

## Base URL

```
Production: https://vaucda.va.gov/api/v1
Development: http://localhost:8000/api/v1
```

---

## Authentication

All API endpoints (except `/health`) require JWT authentication.

**Headers:**
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Token Endpoint:**
```
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=user&password=pass

Response:
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

## 1. Note Generation Endpoints

### POST /notes/generate

Generate a clinical note from unstructured input.

**Request:**
```json
{
  "clinical_input": "72 yo male with elevated PSA 8.5...",
  "note_type": "clinic_note",  // enum: clinic_note, consult, preop, postop
  "template_id": "urology_clinic_v1",  // optional
  "selected_modules": [
    "psa_kinetics",
    "capra_score",
    "nccn_risk"
  ],
  "llm_config": {
    "provider": "ollama",  // enum: ollama, anthropic, openai
    "model": "llama3.1:8b",
    "temperature": 0.3,
    "max_tokens": 4096
  }
}
```

**Response (200 OK):**
```json
{
  "note_id": "uuid-string",
  "generated_note": "UROLOGY CLINIC NOTE\n\nDate: 2025-11-28\n\nCC: Elevated PSA...",
  "sections": [
    {
      "name": "Chief Complaint",
      "content": "Elevated PSA"
    },
    {
      "name": "HPI",
      "content": "72-year-old male presents with..."
    }
  ],
  "appendices": [
    {
      "module_name": "CAPRA Score",
      "category": "prostate_cancer",
      "results": {
        "score": 5,
        "interpretation": "Intermediate risk",
        "risk_level": "intermediate",
        "breakdown": {
          "psa_points": 2,
          "gleason_points": 1,
          "stage_points": 0,
          "ppc_points": 1
        }
      }
    }
  ],
  "metadata": {
    "model_used": "llama3.1:8b",
    "provider": "ollama",
    "tokens_used": 1847,
    "generation_time_ms": 2341,
    "modules_executed": 3,
    "created_at": "2025-11-28T10:30:45Z"
  }
}
```

**Error Responses:**
```json
// 400 Bad Request
{
  "detail": "Invalid note_type. Must be one of: clinic_note, consult, preop, postop"
}

// 422 Unprocessable Entity
{
  "detail": [
    {
      "loc": ["body", "clinical_input"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}

// 500 Internal Server Error
{
  "error_code": "VAUCDA-001",
  "detail": "Ollama connection failed"
}
```

---

### POST /notes/generate/stream

Stream note generation in real-time via WebSocket (see WebSocket section).

---

### GET /notes/{note_id}

Retrieve a previously generated note (ephemeral storage, 30-minute TTL).

**Response (200 OK):**
```json
{
  "note_id": "uuid-string",
  "generated_note": "...",
  "created_at": "2025-11-28T10:30:45Z",
  "expires_at": "2025-11-28T11:00:45Z"
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "detail": "Note not found or expired"
}
```

---

## 2. Calculator Endpoints

### GET /calculators

List all available calculators organized by category.

**Response (200 OK):**
```json
{
  "categories": {
    "prostate_cancer": [
      {
        "id": "psa_kinetics",
        "name": "PSA Kinetics Calculator",
        "description": "Calculate PSAV and PSADT from serial PSA values",
        "inputs": [
          {
            "name": "psa_values",
            "type": "list",
            "description": "List of PSA values (ng/mL)",
            "required": true
          },
          {
            "name": "time_points",
            "type": "list",
            "description": "Time points in months",
            "required": true
          }
        ],
        "references": [
          "D'Amico AV, et al. JAMA 2004;292:2237-2242"
        ]
      }
    ],
    "kidney_cancer": [...],
    ...
  },
  "total_calculators": 44
}
```

---

### GET /calculators/{calculator_id}

Get detailed information about a specific calculator.

**Response (200 OK):**
```json
{
  "id": "capra_score",
  "name": "CAPRA Score",
  "category": "prostate_cancer",
  "description": "Cancer of the Prostate Risk Assessment score",
  "inputs": [
    {
      "name": "psa",
      "type": "float",
      "required": true,
      "min_value": 0.0,
      "unit": "ng/mL",
      "description": "PSA at diagnosis"
    },
    {
      "name": "gleason_primary",
      "type": "int",
      "required": true,
      "choices": [1, 2, 3, 4, 5],
      "description": "Primary Gleason pattern"
    },
    {
      "name": "gleason_secondary",
      "type": "int",
      "required": true,
      "choices": [1, 2, 3, 4, 5],
      "description": "Secondary Gleason pattern"
    },
    {
      "name": "clinical_stage",
      "type": "choice",
      "required": true,
      "choices": ["T1c", "T2a", "T2b", "T2c", "T3a"],
      "description": "Clinical T stage"
    },
    {
      "name": "percent_positive_cores",
      "type": "float",
      "required": true,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "description": "Percentage of positive biopsy cores"
    }
  ],
  "interpretation_guide": {
    "0-2": "Low risk (5-year RFS ~85%)",
    "3-5": "Intermediate risk (5-year RFS ~65%)",
    "6-10": "High risk (5-year RFS ~40%)"
  },
  "references": [
    "Cooperberg MR, et al. Cancer 2006;107:2276-2283",
    "Cooperberg MR, et al. J Urol 2005;173:1938-1942"
  ],
  "version": "1.0"
}
```

---

### POST /calculators/{calculator_id}/calculate

Execute a specific calculator.

**Request:**
```json
{
  "inputs": {
    "psa": 8.5,
    "gleason_primary": 3,
    "gleason_secondary": 4,
    "clinical_stage": "T2a",
    "percent_positive_cores": 45.0
  }
}
```

**Response (200 OK):**
```json
{
  "calculator_id": "capra_score",
  "score": 5,
  "interpretation": "CAPRA Score: 5/10 - Intermediate risk",
  "risk_level": "intermediate",
  "recommendations": [
    "Definitive treatment generally recommended",
    "Consider radiation vs surgery based on patient factors",
    "Discuss multimodal therapy options"
  ],
  "breakdown": {
    "psa_points": 2,
    "gleason_points": 1,
    "stage_points": 0,
    "ppc_points": 1,
    "total_score": 5,
    "survival_estimates": {
      "3_year": 75,
      "5_year": 65,
      "10_year": 50
    }
  },
  "references": [
    "Cooperberg MR, et al. Cancer 2006;107:2276-2283"
  ],
  "computation_time_ms": 12
}
```

**Error Responses:**
```json
// 400 Bad Request - Validation Error
{
  "detail": "Invalid input: psa below minimum value 0.0"
}

// 404 Not Found
{
  "detail": "Calculator not found: invalid_calculator_id"
}
```

---

### POST /calculators/batch

Execute multiple calculators in a single request.

**Request:**
```json
{
  "calculators": [
    {
      "calculator_id": "psa_kinetics",
      "inputs": {
        "psa_values": [4.2, 4.8, 6.1, 8.5],
        "time_points": [0, 6, 12, 18]
      }
    },
    {
      "calculator_id": "capra_score",
      "inputs": {
        "psa": 8.5,
        "gleason_primary": 3,
        "gleason_secondary": 4,
        "clinical_stage": "T2a",
        "percent_positive_cores": 45.0
      }
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "results": [
    {
      "calculator_id": "psa_kinetics",
      "status": "success",
      "result": {...}
    },
    {
      "calculator_id": "capra_score",
      "status": "success",
      "result": {...}
    }
  ],
  "total_calculators": 2,
  "successful": 2,
  "failed": 0
}
```

---

## 3. Template Management Endpoints

### GET /templates

List all available templates.

**Query Parameters:**
- `type` (optional): Filter by note type (clinic_note, consult, preop, postop)
- `active_only` (optional, default: true): Return only active templates

**Response (200 OK):**
```json
{
  "templates": [
    {
      "id": "urology_clinic_v1",
      "name": "Standard Urology Clinic Note",
      "type": "clinic_note",
      "active": true,
      "sections": [
        "CC",
        "HPI",
        "IPSS",
        "Social History",
        "Family History",
        "PSA Curve",
        "Labs",
        "Imaging",
        "ROS",
        "Physical Exam",
        "Assessment",
        "Plan"
      ],
      "created_at": "2025-11-01T00:00:00Z",
      "version": "1.0"
    }
  ],
  "total": 4
}
```

---

### GET /templates/{template_id}

Get a specific template.

**Response (200 OK):**
```json
{
  "id": "urology_clinic_v1",
  "name": "Standard Urology Clinic Note",
  "type": "clinic_note",
  "content": "CC:\n\nHPI:\n\n...",
  "sections": ["CC", "HPI", ...],
  "active": true,
  "created_at": "2025-11-01T00:00:00Z",
  "created_by": "admin",
  "version": "1.0"
}
```

---

### POST /templates

Create a new template (admin only).

**Request:**
```json
{
  "name": "Custom Clinic Note",
  "type": "clinic_note",
  "content": "CC:\n\nHPI:\n\n...",
  "sections": ["CC", "HPI", "Assessment", "Plan"],
  "active": true
}
```

**Response (201 Created):**
```json
{
  "id": "uuid-string",
  "name": "Custom Clinic Note",
  "type": "clinic_note",
  "created_at": "2025-11-28T10:30:45Z",
  "version": "1.0"
}
```

---

### PUT /templates/{template_id}

Update an existing template (admin only).

**Request:**
```json
{
  "content": "Updated template content...",
  "active": true
}
```

**Response (200 OK):**
```json
{
  "id": "uuid-string",
  "name": "Custom Clinic Note",
  "updated_at": "2025-11-28T10:35:00Z",
  "version": "1.1"
}
```

---

### DELETE /templates/{template_id}

Deactivate a template (admin only).

**Response (204 No Content)**

---

## 4. Settings Endpoints

### GET /settings

Get current user settings.

**Response (200 OK):**
```json
{
  "user_id": "uuid-string",
  "default_llm": "ollama",
  "default_model": "llama3.1:8b",
  "default_template": "urology_clinic_v1",
  "module_defaults": {
    "prostate_cancer": {
      "default_calculator": "capra_score",
      "auto_calculate_psa_kinetics": true,
      "include_nccn_risk": true
    },
    "kidney_cancer": {
      "default_nephrometry": "renal_score",
      "survival_model": "ssign_score"
    }
  },
  "display_preferences": {
    "show_confidence_intervals": true,
    "include_guideline_citations": true,
    "display_calculation_breakdown": true,
    "highlight_abnormal_values": true,
    "generate_visual_diagrams": true
  }
}
```

---

### PUT /settings

Update user settings.

**Request:**
```json
{
  "default_llm": "anthropic",
  "default_model": "claude-3-5-sonnet-20250101",
  "module_defaults": {
    "prostate_cancer": {
      "default_calculator": "nccn_risk",
      "auto_calculate_psa_kinetics": false
    }
  }
}
```

**Response (200 OK):**
```json
{
  "user_id": "uuid-string",
  "updated_at": "2025-11-28T10:40:00Z",
  "settings": {...}
}
```

---

## 5. LLM Management Endpoints

### GET /llm/providers

List all available LLM providers and their status.

**Response (200 OK):**
```json
{
  "providers": [
    {
      "name": "ollama",
      "status": "online",
      "host": "http://ollama:11434",
      "models": [
        {
          "name": "llama3.1:8b",
          "size": "4.7GB",
          "modified_at": "2025-11-20T00:00:00Z"
        },
        {
          "name": "llama3.1:70b",
          "size": "40GB",
          "modified_at": "2025-11-20T00:00:00Z"
        }
      ]
    },
    {
      "name": "anthropic",
      "status": "configured",
      "api_key_set": true,
      "models": [
        "claude-3-5-sonnet-20250101",
        "claude-3-opus-20240229"
      ]
    },
    {
      "name": "openai",
      "status": "configured",
      "api_key_set": true,
      "models": [
        "gpt-4o",
        "gpt-4-turbo"
      ]
    }
  ]
}
```

---

### GET /llm/ollama/models

List Ollama models available locally.

**Response (200 OK):**
```json
{
  "models": [
    {
      "name": "llama3.1:8b",
      "size": 4700000000,
      "size_human": "4.7GB",
      "modified_at": "2025-11-20T00:00:00Z",
      "digest": "sha256:...",
      "format": "gguf"
    }
  ],
  "total": 4
}
```

---

### POST /llm/ollama/pull

Pull a new Ollama model (admin only).

**Request:**
```json
{
  "model": "mistral:7b"
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "uuid-string",
  "status": "pulling",
  "model": "mistral:7b",
  "message": "Model pull initiated. Check /llm/ollama/pull/{task_id} for progress."
}
```

---

### GET /llm/ollama/pull/{task_id}

Get model pull status.

**Response (200 OK):**
```json
{
  "task_id": "uuid-string",
  "status": "completed",  // enum: pulling, completed, failed
  "progress": 100,
  "model": "mistral:7b",
  "size_pulled": 4200000000,
  "size_total": 4200000000,
  "completed_at": "2025-11-28T10:50:00Z"
}
```

---

## 6. Evidence Search Endpoints

### POST /evidence/search

Search clinical knowledge base using RAG.

**Request:**
```json
{
  "query": "Treatment options for high-risk prostate cancer",
  "category": "prostate_cancer",  // optional filter
  "k": 5,  // number of results
  "include_references": true
}
```

**Response (200 OK):**
```json
{
  "query": "Treatment options for high-risk prostate cancer",
  "results": [
    {
      "document_id": "uuid-string",
      "title": "NCCN Clinical Practice Guidelines: Prostate Cancer",
      "source": "NCCN Guidelines v2.2025",
      "content": "For high-risk localized prostate cancer, treatment options include...",
      "relevance_score": 0.92,
      "metadata": {
        "document_type": "guideline",
        "category": "prostate_cancer",
        "publication_date": "2025-01-15"
      }
    }
  ],
  "total_results": 5,
  "search_time_ms": 145
}
```

---

### POST /evidence/ingest

Ingest a new document into the knowledge base (admin only).

**Request (multipart/form-data):**
```
file: <PDF or DOCX file>
title: "AUA Guideline 2025"
source: "American Urological Association"
document_type: "guideline"
category: "prostate_cancer"
```

**Response (202 Accepted):**
```json
{
  "task_id": "uuid-string",
  "status": "processing",
  "message": "Document ingestion initiated"
}
```

---

## 7. Health Check Endpoints

### GET /health

General health check (no authentication required).

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-11-28T10:55:00Z",
  "uptime_seconds": 86400
}
```

---

### GET /health/detailed

Detailed health check (authentication required).

**Response (200 OK):**
```json
{
  "status": "healthy",
  "services": {
    "api": {
      "status": "healthy",
      "response_time_ms": 5
    },
    "neo4j": {
      "status": "healthy",
      "connection": "active",
      "response_time_ms": 12
    },
    "ollama": {
      "status": "healthy",
      "models_available": 4,
      "response_time_ms": 150
    },
    "redis": {
      "status": "healthy",
      "connection": "active"
    },
    "sqlite": {
      "status": "healthy",
      "path": "/app/data/settings/vaucda.db"
    }
  },
  "timestamp": "2025-11-28T10:55:00Z"
}
```

---

## 8. WebSocket Endpoints

### WS /ws/generate

Real-time note generation with streaming.

**Connection:**
```javascript
const ws = new WebSocket('wss://vaucda.va.gov/ws/generate?token=<jwt_token>');
```

**Client → Server (Start Generation):**
```json
{
  "type": "start_generation",
  "payload": {
    "clinical_input": "...",
    "note_type": "clinic_note",
    "selected_modules": ["capra_score"],
    "llm_config": {
      "provider": "ollama",
      "model": "llama3.1:8b"
    }
  }
}
```

**Server → Client (Progress Updates):**
```json
{
  "type": "generation_progress",
  "payload": {
    "chunk": "UROLOGY CLINIC NOTE\n\nDate: 2025-11-28\n\n",
    "progress": 15
  }
}
```

**Server → Client (Module Execution):**
```json
{
  "type": "module_progress",
  "payload": {
    "module": "capra_score",
    "status": "executing"
  }
}
```

**Server → Client (Completion):**
```json
{
  "type": "generation_complete",
  "payload": {
    "note_id": "uuid-string",
    "total_tokens": 1847,
    "generation_time_ms": 2341,
    "modules_executed": 1
  }
}
```

**Server → Client (Error):**
```json
{
  "type": "error",
  "payload": {
    "error_code": "VAUCDA-001",
    "message": "Ollama connection failed"
  }
}
```

---

## 9. Error Codes

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
| VAUCDA-050 | System | Internal server error |

---

## 10. Rate Limiting

All endpoints are rate-limited to prevent abuse:

- Anonymous requests: 10 requests/minute
- Authenticated users: 100 requests/minute
- Admin users: 1000 requests/minute

**Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1732790400
```

**Rate Limit Exceeded Response (429):**
```json
{
  "detail": "Rate limit exceeded. Try again in 30 seconds."
}
```

---

## 11. Pagination

Endpoints returning lists support pagination:

**Query Parameters:**
- `page` (default: 1)
- `page_size` (default: 20, max: 100)

**Response Format:**
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "has_next": true,
  "has_prev": false
}
```

---

## 12. Content Negotiation

The API supports multiple response formats:

- `application/json` (default)
- `application/xml`
- `text/plain`

**Request Header:**
```
Accept: application/json
```

---

This API specification provides the complete contract for all backend endpoints. All endpoints follow RESTful conventions and return consistent error responses.
