

---

## 5. Data Layer Design

### 5.1 Neo4j Schema Design

#### 5.1.1 Node Types

```cypher
// Clinical Knowledge Nodes
(:Document {
    id: STRING,
    title: STRING,
    source: STRING,          // "AUA", "NCCN", "EAU", "peer_reviewed"
    content: STRING,
    embedding: LIST<FLOAT>,  // 768-dim PubMedBERT vector
    created_at: DATETIME,
    document_type: STRING,   // "guideline", "reference", "calculator"
    specialty: STRING,       // "prostate", "kidney", "bladder", etc.
    publication_date: DATE,
    version: STRING
})

(:ClinicalConcept {
    id: STRING,
    name: STRING,
    category: STRING,        // "prostate_cancer", "kidney_cancer", etc.
    description: STRING,
    embedding: LIST<FLOAT>,  // 768-dim PubMedBERT vector
    icd10_codes: LIST<STRING>,
    snomed_codes: LIST<STRING>,
    loinc_codes: LIST<STRING>
})

(:Calculator {
    id: STRING,
    name: STRING,
    category: STRING,
    description: STRING,
    formula: STRING,
    inputs: LIST<STRING>,
    interpretation: STRING,
    references: LIST<STRING>,
    fhir_auto_populate: BOOLEAN,
    loinc_mappings: MAP       // Input field -> LOINC code mapping
})

(:Template {
    id: STRING,
    name: STRING,
    type: STRING,            // "clinic_note", "consult", "preop", "postop"
    content: STRING,
    sections: LIST<STRING>,
    word_style_config: MAP,  // python-docx style parameters
    active: BOOLEAN
})

(:Guideline {
    id: STRING,
    organization: STRING,    // "AUA", "NCCN", "EAU"
    title: STRING,
    version: STRING,
    publication_date: DATE,
    content: STRING,
    embedding: LIST<FLOAT>,
    url: STRING
})

(:LOINCCode {
    code: STRING,
    display_name: STRING,
    component: STRING,
    property: STRING,
    system: STRING,
    category: STRING,        // "endocrine", "stone", "general", "tumor_marker"
    urology_relevance: STRING
})

(:FHIRResourceSchema {
    resource_type: STRING,   // "Observation", "DiagnosticReport", etc.
    profile_url: STRING,
    search_parameters: LIST<STRING>,
    supported_scopes: LIST<STRING>
})
```

#### 5.1.2 Relationship Types

```cypher
// Knowledge Graph Relationships
(:Document)-[:REFERENCES]->(:ClinicalConcept)
(:Document)-[:CITES]->(:Document)
(:ClinicalConcept)-[:RELATED_TO]->(:ClinicalConcept)
(:ClinicalConcept)-[:DIAGNOSED_BY]->(:LOINCCode)
(:Calculator)-[:APPLIES_TO]->(:ClinicalConcept)
(:Calculator)-[:DERIVED_FROM]->(:Document)
(:Calculator)-[:USES_LAB {input_field: STRING}]->(:LOINCCode)
(:Guideline)-[:RECOMMENDS]->(:ClinicalConcept)
(:Guideline)-[:SUPERSEDES]->(:Guideline)
(:Guideline)-[:PUBLISHED_BY {organization: STRING}]->(:Document)

// Template Relationships
(:Template)-[:INCLUDES_SECTION {order: INTEGER}]->(:TemplateSection)

// FHIR Schema Relationships
(:LOINCCode)-[:MAPS_TO]->(:FHIRResourceSchema)
(:FHIRResourceSchema)-[:CONTAINS]->(:LOINCCode)
```

#### 5.1.3 Vector Index Configuration

```cypher
// PubMedBERT document embeddings (768-dimensional)
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document)
ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

// PubMedBERT concept embeddings
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept)
ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

// PubMedBERT guideline embeddings
CREATE VECTOR INDEX guideline_embeddings IF NOT EXISTS
FOR (g:Guideline)
ON (g.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}
```

#### 5.1.4 Full-Text Search Indexes

```cypher
// Full-text search for document content
CREATE FULLTEXT INDEX document_content IF NOT EXISTS
FOR (d:Document) ON EACH [d.content, d.title];

// Full-text search for clinical concepts
CREATE FULLTEXT INDEX concept_search IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];

// Full-text search for guidelines
CREATE FULLTEXT INDEX guideline_search IF NOT EXISTS
FOR (g:Guideline) ON EACH [g.title, g.content];

// LOINC code search
CREATE FULLTEXT INDEX loinc_search IF NOT EXISTS
FOR (l:LOINCCode) ON EACH [l.display_name, l.component];
```

#### 5.1.5 Constraints

```cypher
CREATE CONSTRAINT document_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT calculator_id IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT template_id IF NOT EXISTS
FOR (t:Template) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT guideline_id IF NOT EXISTS
FOR (g:Guideline) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT loinc_code IF NOT EXISTS
FOR (l:LOINCCode) REQUIRE l.code IS UNIQUE;

CREATE CONSTRAINT fhir_resource_type IF NOT EXISTS
FOR (f:FHIRResourceSchema) REQUIRE f.resource_type IS UNIQUE;
```

### 5.2 SQLite Schema (Settings and Audit Database)

```sql
-- EPIC Connection Configuration
CREATE TABLE epic_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    fhir_base_url TEXT NOT NULL,
    client_id TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    scopes TEXT NOT NULL,
    token_endpoint TEXT,
    authorize_endpoint TEXT,
    -- Encrypted fields (Fernet AES-256)
    client_secret_encrypted BLOB,
    connection_status TEXT DEFAULT 'disconnected',
    last_auth_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM Provider Configuration
CREATE TABLE llm_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    provider_name TEXT NOT NULL,           -- 'ollama' or 'anthropic'
    host TEXT,                             -- Ollama host URL
    api_key_encrypted BLOB,               -- Anthropic API key (encrypted)
    default_model TEXT,
    temperature REAL DEFAULT 0.3,
    max_tokens INTEGER DEFAULT 4096,
    is_active BOOLEAN DEFAULT 1,
    last_health_check TIMESTAMP,
    health_status TEXT DEFAULT 'unknown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider_name)
);

-- Dynamic Model Cache
CREATE TABLE discovered_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_size TEXT,
    context_window INTEGER,
    capabilities TEXT,                     -- JSON array of capabilities
    last_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_available BOOLEAN DEFAULT 1,
    UNIQUE(provider_name, model_name)
);

-- User Preferences
CREATE TABLE user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    default_llm_provider TEXT DEFAULT 'ollama',
    default_model TEXT DEFAULT 'llama3.1:8b',
    default_note_type TEXT DEFAULT 'clinic_note',
    default_template TEXT DEFAULT 'urology_clinic',
    word_template_style TEXT DEFAULT 'professional',
    module_defaults JSON,
    display_preferences JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session Audit Log (PHI-free)
CREATE TABLE session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,                  -- "fhir_fetch", "note_generation", "calculator", "word_export"
    note_type TEXT,
    modules_used TEXT,                     -- JSON array
    llm_provider TEXT,
    model_used TEXT,
    fhir_resources_queried TEXT,           -- JSON array of resource types
    tokens_used INTEGER,
    duration_ms INTEGER,
    success BOOLEAN,
    error_code TEXT,
    -- NEVER logged: clinical_input, generated_note, patient_id, any PHI
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Word Document Export Log
CREATE TABLE word_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_id TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL,
    note_type TEXT NOT NULL,
    template_used TEXT,
    page_count INTEGER,
    generation_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- NEVER logged: document content, patient data
);

-- Credential Encryption Keys
CREATE TABLE encryption_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id TEXT UNIQUE NOT NULL,
    key_purpose TEXT NOT NULL,             -- "epic_credentials", "api_keys"
    encrypted_key BLOB NOT NULL,           -- Master-key encrypted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rotated_at TIMESTAMP
);
```

### 5.3 FHIR Resource to Note Section Mapping

This mapping defines how FHIR R4 resources are transformed into clinical note sections:

```python
FHIR_TO_NOTE_MAPPING = {
    # Note Section -> FHIR Resource Configuration
    "chief_complaint": {
        "resources": ["Encounter"],
        "search_params": {"_sort": "-date", "_count": 1},
        "extraction": "reason_code_display"
    },
    "hpi": {
        "resources": ["DocumentReference", "Condition", "Encounter"],
        "search_params": {
            "DocumentReference": {"type": "11488-4", "category": "clinical-note"},
            "Condition": {"clinical-status": "active"},
            "Encounter": {"_sort": "-date", "_count": 5}
        },
        "extraction": "ai_agent_synthesis"
    },
    "ipss": {
        "resources": ["Observation"],
        "search_params": {"code": "80976-4"},  # IPSS LOINC
        "extraction": "structured_questionnaire"
    },
    "psa_curve": {
        "resources": ["Observation"],
        "search_params": {"code": "2857-1"},   # PSA Total LOINC
        "extraction": "chronological_series"
    },
    "testosterone_curve": {
        "resources": ["Observation"],
        "search_params": {"code": "2986-8"},   # Testosterone Total LOINC
        "extraction": "chronological_series"
    },
    "medications": {
        "resources": ["MedicationStatement"],
        "search_params": {"status": "active"},
        "extraction": "active_list"
    },
    "allergies": {
        "resources": ["AllergyIntolerance"],
        "search_params": {},
        "extraction": "allergy_list_with_nka"
    },
    "pmh": {
        "resources": ["Condition"],
        "search_params": {"clinical-status": "active"},
        "extraction": "condition_list"
    },
    "psh": {
        "resources": ["Procedure"],
        "search_params": {"_sort": "-date"},
        "extraction": "procedure_list"
    },
    "family_history": {
        "resources": ["FamilyMemberHistory"],
        "search_params": {},
        "extraction": "family_condition_list"
    },
    "pathology": {
        "resources": ["DiagnosticReport"],
        "search_params": {"category": "PAT", "_sort": "-date"},
        "extraction": "pathology_detail_preservation"
    },
    "imaging": {
        "resources": ["DiagnosticReport"],
        "search_params": {"category": "IMG", "_sort": "-date"},
        "extraction": "imaging_summarization"
    },
    "endocrine_labs": {
        "resources": ["Observation"],
        "search_params": {
            "code": "2986-8,2991-8,2243-4,10501-5,15067-2,2731-8"
        },
        "extraction": "lab_table_format"
    },
    "stone_labs": {
        "resources": ["Observation"],
        "search_params": {
            "code": "57362-1,49054-9,2881-1,21482-5,2777-1,2160-0"
        },
        "extraction": "lab_table_format"
    },
    "general_labs": {
        "resources": ["Observation"],
        "search_params": {
            "category": "laboratory",
            "date": "ge{six_months_ago}"
        },
        "extraction": "lab_table_format"
    },
    "ros": {
        "resources": ["DocumentReference"],
        "search_params": {"type": "11488-4"},
        "extraction": "ros_template_merge"
    },
    "physical_exam": {
        "resources": ["DocumentReference"],
        "search_params": {"type": "11488-4"},
        "extraction": "pe_template_merge"
    },
    "assessment": {
        "resources": [],  # Synthesized from all other sections
        "search_params": {},
        "extraction": "ai_agent_synthesis"
    },
    "plan": {
        "resources": ["CarePlan", "ServiceRequest"],
        "search_params": {"status": "active"},
        "extraction": "ai_agent_synthesis"
    }
}
```

### 5.4 LOINC Code Registry

```python
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class LabCategory(Enum):
    PROSTATE = "prostate"
    ENDOCRINE = "endocrine"
    STONE = "stone"
    TUMOR_MARKER = "tumor_marker"
    RENAL = "renal"
    GENERAL = "general"
    URINALYSIS = "urinalysis"

@dataclass
class LOINCEntry:
    """LOINC code registry entry for urology lab mapping."""
    code: str
    display_name: str
    category: LabCategory
    component: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    clinical_significance: Optional[str] = None
    fhir_search_code: Optional[str] = None

    def __post_init__(self):
        if self.fhir_search_code is None:
            self.fhir_search_code = self.code

UROLOGY_LOINC_REGISTRY: List[LOINCEntry] = [
    # Prostate Cancer Markers
    LOINCEntry("2857-1", "PSA Total", LabCategory.PROSTATE,
               "Prostate specific Ag", "ng/mL", "0-4.0",
               "Primary prostate cancer screening/monitoring"),
    LOINCEntry("10886-0", "Free PSA", LabCategory.PROSTATE,
               "Prostate specific Ag.free", "ng/mL", None,
               "Free/Total ratio for cancer risk stratification"),
    LOINCEntry("12841-3", "Free/Total PSA %", LabCategory.PROSTATE,
               "Prostate specific Ag.free/Prostate specific Ag.total", "%", ">25%",
               "Ratio >25% suggests benign; <10% suggests malignancy"),

    # Endocrine Panel
    LOINCEntry("2986-8", "Testosterone Total", LabCategory.ENDOCRINE,
               "Testosterone", "ng/dL", "300-1000",
               "Hypogonadism evaluation; low if <300 ng/dL"),
    LOINCEntry("2991-8", "Free Testosterone", LabCategory.ENDOCRINE,
               "Testosterone.free", "pg/mL", "5-21",
               "Bioactive testosterone fraction"),
    LOINCEntry("49041-6", "Bioavailable Testosterone", LabCategory.ENDOCRINE,
               "Testosterone.bioavailable", "ng/dL", "131-682",
               "Non-SHBG-bound testosterone"),
    LOINCEntry("2243-4", "Estradiol", LabCategory.ENDOCRINE,
               "Estradiol (E2)", "pg/mL", "10-40",
               "Elevated in gynecomastia, aromatase excess"),
    LOINCEntry("10501-5", "LH", LabCategory.ENDOCRINE,
               "Luteinizing hormone", "mIU/mL", "1.7-8.6",
               "Primary vs secondary hypogonadism differentiation"),
    LOINCEntry("15067-2", "FSH", LabCategory.ENDOCRINE,
               "Follicle stimulating hormone", "mIU/mL", "1.5-12.4",
               "Spermatogenesis assessment; elevated in primary failure"),
    LOINCEntry("2731-8", "PTH Intact", LabCategory.ENDOCRINE,
               "Parathyrin.intact", "pg/mL", "15-65",
               "Hyperparathyroidism screening in stone patients"),

    # Tumor Markers
    LOINCEntry("1834-1", "AFP", LabCategory.TUMOR_MARKER,
               "Alpha-1-Fetoprotein", "ng/mL", "<10",
               "Testicular nonseminoma marker; hepatocellular carcinoma"),
    LOINCEntry("21198-7", "Beta-HCG", LabCategory.TUMOR_MARKER,
               "Choriogonadotropin.beta subunit", "mIU/mL", "<5",
               "Testicular cancer marker (seminoma and nonseminoma)"),
    LOINCEntry("2532-0", "LDH", LabCategory.TUMOR_MARKER,
               "Lactate dehydrogenase", "U/L", "140-280",
               "Testicular cancer staging; tumor burden marker"),

    # Urinalysis
    LOINCEntry("5794-3", "UA Microscopic", LabCategory.URINALYSIS,
               "Urinalysis microscopic panel", None, None,
               "Hematuria evaluation, infection screening"),
    LOINCEntry("24356-8", "UA Complete Panel", LabCategory.URINALYSIS,
               "Urinalysis complete panel", None, None,
               "Comprehensive urinalysis with microscopy"),
    LOINCEntry("630-4", "Urine Culture", LabCategory.URINALYSIS,
               "Bacteria identified in urine by culture", None, "No growth",
               "UTI identification and antibiotic sensitivity"),

    # Stone / Litholink Panel
    LOINCEntry("57362-1", "24h Urine Stone Panel", LabCategory.STONE,
               "24 hour urine stone risk panel", None, None,
               "Comprehensive metabolic stone evaluation"),
    LOINCEntry("49054-9", "Urine Oxalate 24h", LabCategory.STONE,
               "Oxalate 24 hour urine", "mg/24h", "<40",
               "Hyperoxaluria screening; calcium oxalate risk"),
    LOINCEntry("2881-1", "Urine Citrate 24h", LabCategory.STONE,
               "Citrate 24 hour urine", "mg/24h", ">320",
               "Hypocitraturia screening; protective factor"),
    LOINCEntry("21482-5", "Calcium 24h Urine", LabCategory.STONE,
               "Calcium 24 hour urine", "mg/24h", "<300",
               "Hypercalciuria screening"),
    LOINCEntry("2777-1", "Uric Acid Serum", LabCategory.STONE,
               "Urate", "mg/dL", "3.5-7.2",
               "Hyperuricemia; uric acid stone risk"),
    LOINCEntry("2160-0", "Creatinine Serum", LabCategory.RENAL,
               "Creatinine", "mg/dL", "0.7-1.3",
               "Renal function assessment"),
    LOINCEntry("2075-0", "Chloride Serum", LabCategory.STONE,
               "Chloride", "mEq/L", "96-106",
               "RTA evaluation in recurrent stone formers"),
    LOINCEntry("2947-0", "Sodium Serum", LabCategory.STONE,
               "Sodium", "mEq/L", "136-145",
               "Dietary sodium assessment for stone risk"),
    LOINCEntry("6298-4", "Potassium Serum", LabCategory.STONE,
               "Potassium", "mEq/L", "3.5-5.0",
               "Hypokalemia in RTA evaluation"),

    # General / Renal
    LOINCEntry("1989-3", "Vitamin D 25-OH", LabCategory.GENERAL,
               "25-Hydroxyvitamin D2+D3", "ng/mL", "30-100",
               "Calcium metabolism; stone disease evaluation"),
    LOINCEntry("58410-2", "CBC Panel", LabCategory.GENERAL,
               "CBC panel", None, None,
               "Pre-operative screening; anemia evaluation"),
    LOINCEntry("51990-0", "BMP", LabCategory.GENERAL,
               "Basic metabolic panel", None, None,
               "Renal function, electrolytes"),
    LOINCEntry("24323-8", "CMP", LabCategory.GENERAL,
               "Comprehensive metabolic panel", None, None,
               "Full metabolic assessment"),
    LOINCEntry("33914-3", "eGFR", LabCategory.RENAL,
               "Glomerular filtration rate", "mL/min/1.73m2", ">60",
               "Kidney function staging; nephron-sparing decisions"),

    # IPSS Questionnaire
    LOINCEntry("80976-4", "IPSS Total", LabCategory.GENERAL,
               "IPSS total score", "score", "0-35",
               "Lower urinary tract symptom severity"),
]

def get_loinc_codes_for_category(category: LabCategory) -> List[str]:
    """Get all LOINC codes for a specific lab category."""
    return [entry.code for entry in UROLOGY_LOINC_REGISTRY
            if entry.category == category]

def get_all_targeted_loinc_codes() -> str:
    """Get comma-separated LOINC codes for targeted urology lab queries."""
    return ",".join(entry.code for entry in UROLOGY_LOINC_REGISTRY)

def get_loinc_entry(code: str) -> Optional[LOINCEntry]:
    """Look up a LOINC entry by code."""
    for entry in UROLOGY_LOINC_REGISTRY:
        if entry.code == code:
            return entry
    return None
```

### 5.5 File Storage Structure

```
/epic-vaucda/
├── backend/
│   ├── app/
│   │   ├── api/v1/              # FastAPI route modules
│   │   ├── core/                # Configuration, security
│   │   ├── models/              # Pydantic schemas
│   │   ├── services/
│   │   │   ├── epic_fhir/       # FHIR integration layer
│   │   │   │   ├── client.py    # Async FHIR HTTP client
│   │   │   │   ├── oauth.py     # SMART on FHIR OAuth 2.0
│   │   │   │   ├── fetchers/    # Resource-specific fetchers
│   │   │   │   └── models.py    # FHIR resource Pydantic models
│   │   │   ├── llm/             # LLM provider layer
│   │   │   │   ├── ollama.py    # Ollama client + discovery
│   │   │   │   ├── anthropic.py # Anthropic client + discovery
│   │   │   │   ├── registry.py  # Dynamic model registry
│   │   │   │   └── provider.py  # Abstract provider interface
│   │   │   ├── note_processing/ # 5-stage pipeline
│   │   │   │   ├── agents/      # Extraction + synthesis agents
│   │   │   │   ├── extractors/  # Document-level extractors
│   │   │   │   └── pipeline.py  # Pipeline orchestrator
│   │   │   ├── word_generator/  # Word document generation
│   │   │   │   ├── generator.py # python-docx rendering
│   │   │   │   ├── styles.py    # Document styles/formatting
│   │   │   │   └── templates/   # Word template definitions
│   │   │   ├── calculators/     # 44 clinical calculators
│   │   │   └── rag/             # RAG pipeline
│   │   └── database/           # Neo4j + SQLite clients
│   ├── data/
│   │   ├── documents/
│   │   │   ├── guidelines/      # AUA, NCCN, EAU guidelines
│   │   │   ├── references/      # Peer-reviewed literature
│   │   │   └── calculators/     # Calculator documentation
│   │   ├── templates/
│   │   │   ├── word/            # Word document templates (.docx)
│   │   │   ├── clinic_notes/    # Note section templates
│   │   │   ├── consult_notes/
│   │   │   ├── preop_notes/
│   │   │   └── postop_notes/
│   │   └── exports/             # Generated Word documents (temporary)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── epic/            # EPIC settings components
│   │   │   ├── notes/           # Note generation components
│   │   │   ├── calculators/     # Calculator UI components
│   │   │   ├── evidence/        # Evidence search components
│   │   │   └── layout/          # Layout components
│   │   ├── hooks/               # Custom React hooks
│   │   ├── services/            # API client services
│   │   ├── stores/              # Zustand state stores
│   │   └── types/               # TypeScript type definitions
│   └── package.json
├── docker-compose.yml
├── .env.example
└── scripts/
    ├── init_neo4j.cypher
    ├── setup_ollama_models.sh
    └── generate_encryption_key.py
```
