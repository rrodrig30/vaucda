# VAUCDA Neo4j Database Architecture
**Production-Ready Graph + Vector Database Design**

**Version:** 1.0
**Date:** November 29, 2025
**Classification:** Technical Architecture Documentation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Data Model Design](#3-data-model-design)
4. [Vector Search Architecture](#4-vector-search-architecture)
5. [Performance Optimization](#5-performance-optimization)
6. [HIPAA Compliance & Session Management](#6-hipaa-compliance--session-management)
7. [Integration Architecture](#7-integration-architecture)
8. [Deployment Strategy](#8-deployment-strategy)
9. [Monitoring & Maintenance](#9-monitoring--maintenance)
10. [Query Patterns & Examples](#10-query-patterns--examples)

---

## 1. Executive Summary

### 1.1 Architecture Overview

The VAUCDA Neo4j database architecture combines graph database capabilities with vector similarity search to provide:

- **Hybrid Retrieval**: Graph traversal + vector semantic search for RAG pipeline
- **Sub-Second Performance**: Optimized HNSW indexes for 768-dimensional embeddings
- **Clinical Knowledge Graph**: Structured relationships between urologic concepts
- **Ephemeral Session Management**: HIPAA-compliant 30-minute TTL with automatic cleanup
- **Production Scalability**: Support for 500+ concurrent users

### 1.2 Key Capabilities

| Capability | Implementation | Performance Target |
|------------|----------------|-------------------|
| Vector Search | HNSW index on 768-dim embeddings | < 100ms for top-10 results |
| Graph Traversal | Relationship-based context assembly | < 50ms for 3-hop queries |
| Session TTL | Time-based node expiration | Automatic cleanup every 5 minutes |
| Concurrent Users | Connection pooling (100 connections) | 500+ concurrent sessions |
| Data Ingestion | Batch operations with transactions | 1000+ docs/min |

### 1.3 Architecture Principles

**Zero PHI Persistence**: Sessions stored with metadata only, no clinical content
**Performance First**: Optimized indexes and query patterns for sub-second retrieval
**Graph-Native**: Leverages Neo4j's native graph algorithms for relationship traversal
**Vector-Enhanced**: HNSW indexes for fast similarity search on embeddings
**Horizontally Scalable**: Designed for Neo4j clustering in production

---

## 2. System Overview

### 2.1 Database Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NEO4J DATABASE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  CLINICAL KNOWLEDGE GRAPH                                            │   │
│  │                                                                       │   │
│  │  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐       │   │
│  │  │  Document    │─────▶│  Clinical    │─────▶│  Calculator  │       │   │
│  │  │  Nodes       │      │  Concept     │      │  Nodes       │       │   │
│  │  │  (Guidelines)│      │  Nodes       │      │  (Formulas)  │       │   │
│  │  └──────────────┘      └──────────────┘      └──────────────┘       │   │
│  │         │                     │                     │                │   │
│  │         │   REFERENCES        │   RELATED_TO        │  APPLIES_TO    │   │
│  │         └─────────────────────┴─────────────────────┘                │   │
│  │                                                                       │   │
│  │  [768-dim Vector Embeddings on Document + ClinicalConcept nodes]    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  EPHEMERAL SESSION LAYER (HIPAA-Compliant)                           │   │
│  │                                                                       │   │
│  │  ┌──────────────┐      ┌──────────────┐                              │   │
│  │  │  Session     │─────▶│  AuditLog    │                              │   │
│  │  │  Nodes       │      │  Nodes       │                              │   │
│  │  │  (30min TTL) │      │  (Metadata)  │                              │   │
│  │  └──────────────┘      └──────────────┘                              │   │
│  │         │                                                             │   │
│  │         │   TTL Cleanup: Automatic deletion after 30 minutes          │   │
│  │         │   Background Job: Runs every 5 minutes                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  CONFIGURATION LAYER                                                  │   │
│  │                                                                       │   │
│  │  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐       │   │
│  │  │  Template    │      │  User        │      │  Settings    │       │   │
│  │  │  Nodes       │      │  Nodes       │      │  Nodes       │       │   │
│  │  └──────────────┘      └──────────────┘      └──────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Node Type Summary

| Node Label | Purpose | Cardinality | Vector Index | TTL |
|------------|---------|-------------|--------------|-----|
| `:Document` | Clinical guidelines, references | 10,000+ | Yes (768-dim) | Permanent |
| `:ClinicalConcept` | Urologic diagnoses, procedures | 1,000+ | Yes (768-dim) | Permanent |
| `:Calculator` | Clinical calculator definitions | 44 | No | Permanent |
| `:Template` | Note templates | 50+ | No | Permanent |
| `:User` | User preferences | 500+ | No | Permanent |
| `:Session` | Active user sessions | 500 concurrent | No | 30 minutes |
| `:AuditLog` | Metadata-only logs | 100,000+ | No | 90 days |

### 2.3 Relationship Type Summary

| Relationship | Source | Target | Purpose | Properties |
|--------------|--------|--------|---------|------------|
| `:REFERENCES` | Document | ClinicalConcept | Citation linkage | `{relevance: FLOAT}` |
| `:CITES` | Document | Document | Literature references | `{citation_type: STRING}` |
| `:RELATED_TO` | ClinicalConcept | ClinicalConcept | Clinical associations | `{weight: FLOAT}` |
| `:APPLIES_TO` | Calculator | ClinicalConcept | Calculator applicability | `{priority: INT}` |
| `:DERIVED_FROM` | Calculator | Document | Evidence source | `{version: STRING}` |
| `:BELONGS_TO` | Session | User | Session ownership | `{created_at: DATETIME}` |
| `:LOGGED` | AuditLog | Session | Audit trail | `{action: STRING}` |

---

## 3. Data Model Design

### 3.1 Clinical Knowledge Nodes

#### 3.1.1 Document Nodes

```cypher
(:Document {
    // Core identifiers
    id: STRING (UUID),               // Primary key
    document_id: STRING,              // External document ID (e.g., NCCN-PROSTATE-2024)

    // Content
    title: STRING,                    // Document title
    content: STRING,                  // Full text content
    summary: STRING,                  // Executive summary (for display)

    // Metadata
    source: STRING,                   // Source organization (NCCN, AUA, EAU)
    document_type: STRING,            // guideline, reference, calculator_doc
    category: STRING,                 // prostate, kidney, bladder, etc.
    specialty: STRING,                // urology, oncology, radiology

    // Versioning
    version: STRING,                  // Document version (e.g., "2024.1")
    publication_date: DATE,           // Official publication date
    last_reviewed: DATE,              // Last clinical review

    // Vector embeddings
    embedding: LIST<FLOAT>,           // 768-dimensional vector

    // Search optimization
    keywords: LIST<STRING>,           // Extracted keywords for filtering

    // Timestamps
    created_at: DATETIME,
    updated_at: DATETIME
})
```

**Indexes:**
```cypher
// Uniqueness constraint
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

// Vector index for semantic search
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine',
        `vector.quantization.enabled`: false  // Full precision for medical accuracy
    }
};

// Full-text search index
CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
FOR (d:Document) ON EACH [d.title, d.content, d.summary];

// Property indexes for filtering
CREATE INDEX document_category IF NOT EXISTS
FOR (d:Document) ON (d.category);

CREATE INDEX document_source IF NOT EXISTS
FOR (d:Document) ON (d.source);

CREATE INDEX document_type IF NOT EXISTS
FOR (d:Document) ON (d.document_type);
```

#### 3.1.2 ClinicalConcept Nodes

```cypher
(:ClinicalConcept {
    // Core identifiers
    id: STRING (UUID),
    concept_id: STRING,               // SNOMED CT or ICD-10 code

    // Clinical information
    name: STRING,                     // Preferred clinical term
    synonyms: LIST<STRING>,           // Alternative names
    description: STRING,              // Clinical description
    category: STRING,                 // prostate, kidney, bladder, etc.

    // Medical coding
    icd10_codes: LIST<STRING>,        // ICD-10 diagnosis codes
    snomed_codes: LIST<STRING>,       // SNOMED CT codes
    cpt_codes: LIST<STRING>,          // CPT procedure codes (if applicable)

    // Clinical context
    severity: STRING,                 // low, moderate, high
    is_diagnosis: BOOLEAN,            // True if diagnosis vs procedure
    is_procedure: BOOLEAN,            // True if procedure vs diagnosis

    // Vector embeddings
    embedding: LIST<FLOAT>,           // 768-dimensional vector

    // Timestamps
    created_at: DATETIME,
    updated_at: DATETIME
})
```

**Indexes:**
```cypher
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (c:ClinicalConcept) REQUIRE c.id IS UNIQUE;

CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};

CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];

CREATE INDEX concept_category IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.category);
```

#### 3.1.3 Calculator Nodes

```cypher
(:Calculator {
    // Core identifiers
    id: STRING (UUID),
    calculator_id: STRING,            // Internal ID (e.g., "capra_score")

    // Calculator metadata
    name: STRING,                     // Display name
    category: STRING,                 // prostate_cancer, kidney_cancer, etc.
    description: STRING,              // Clinical purpose

    // Implementation
    formula: STRING,                  // Mathematical formula (for display)
    algorithm_version: STRING,        // Version of calculator algorithm
    implementation_class: STRING,     // Python class name

    // Clinical context
    inputs: LIST<STRING>,             // Required input parameters
    outputs: LIST<STRING>,            // Output values
    interpretation_ranges: MAP,       // Risk stratification thresholds

    // Evidence
    references: LIST<STRING>,         // PMID or DOI citations
    validation_status: STRING,        // validated, experimental

    // Usage metadata
    usage_count: INTEGER,             // Total times used
    last_used: DATETIME,              // Last usage timestamp

    // Timestamps
    created_at: DATETIME,
    updated_at: DATETIME
})
```

**Indexes:**
```cypher
CREATE CONSTRAINT calculator_id_unique IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.id IS UNIQUE;

CREATE INDEX calculator_category IF NOT EXISTS
FOR (c:Calculator) ON (c.category);
```

### 3.2 Ephemeral Session Nodes (HIPAA-Compliant)

#### 3.2.1 Session Nodes

```cypher
(:Session {
    // Core identifiers
    id: STRING (UUID),
    session_id: STRING,               // External session ID (from JWT)

    // User association
    user_id: STRING,                  // Associated user

    // Session metadata (NO PHI)
    note_type: STRING,                // clinic_note, consult, preop, postop
    llm_provider: STRING,             // ollama, anthropic, openai
    model_used: STRING,               // llama3.1:8b, claude-3-sonnet, etc.
    selected_modules: LIST<STRING>,   // Calculator IDs used

    // Performance metrics
    generation_time_ms: INTEGER,
    tokens_used: INTEGER,

    // TTL management
    created_at: DATETIME,
    expires_at: DATETIME,             // created_at + 30 minutes
    last_accessed: DATETIME,

    // Status
    status: STRING                    // active, expired, deleted
})
```

**Indexes:**
```cypher
CREATE CONSTRAINT session_id_unique IF NOT EXISTS
FOR (s:Session) REQUIRE s.id IS UNIQUE;

// Index for TTL cleanup queries
CREATE INDEX session_expires_at IF NOT EXISTS
FOR (s:Session) ON (s.expires_at);

CREATE INDEX session_status IF NOT EXISTS
FOR (s:Session) ON (s.status);

CREATE INDEX session_user_id IF NOT EXISTS
FOR (s:Session) ON (s.user_id);
```

**CRITICAL: TTL Cleanup Mechanism**

Sessions are automatically deleted after 30 minutes using a background Cypher procedure:

```cypher
// Run every 5 minutes via scheduled task
CALL apoc.periodic.repeat(
    'session-ttl-cleanup',
    'MATCH (s:Session)
     WHERE s.expires_at < datetime() AND s.status = "active"
     SET s.status = "expired"
     WITH s
     DETACH DELETE s',
    300  // Run every 300 seconds (5 minutes)
);
```

#### 3.2.2 AuditLog Nodes (Metadata Only)

```cypher
(:AuditLog {
    // Core identifiers
    id: STRING (UUID),

    // Session association
    session_id: STRING,               // Associated session
    user_id: STRING,                  // User who performed action

    // Action metadata (NO PHI)
    action: STRING,                   // note_generation, calculator_use, evidence_search
    module_used: STRING,              // Specific calculator or tool used

    // Input/Output hashes (NOT actual content)
    input_hash: STRING,               // SHA256 hash of input (for duplicate detection)
    output_hash: STRING,              // SHA256 hash of output

    // Performance metrics
    duration_ms: INTEGER,
    tokens_used: INTEGER,
    llm_provider: STRING,
    model_used: STRING,

    // Result status
    success: BOOLEAN,
    error_code: STRING,               // Non-descriptive error code (VAUCDA-###)

    // Timestamps
    created_at: DATETIME,
    expires_at: DATETIME              // created_at + 90 days
})
```

**Indexes:**
```cypher
CREATE CONSTRAINT auditlog_id_unique IF NOT EXISTS
FOR (a:AuditLog) REQUIRE a.id IS UNIQUE;

CREATE INDEX auditlog_session IF NOT EXISTS
FOR (a:AuditLog) ON (a.session_id);

CREATE INDEX auditlog_user IF NOT EXISTS
FOR (a:AuditLog) ON (a.user_id);

CREATE INDEX auditlog_created IF NOT EXISTS
FOR (a:AuditLog) ON (a.created_at);

CREATE INDEX auditlog_expires IF NOT EXISTS
FOR (a:AuditLog) ON (a.expires_at);
```

### 3.3 Configuration Nodes

#### 3.3.1 Template Nodes

```cypher
(:Template {
    id: STRING (UUID),
    template_id: STRING,
    name: STRING,
    type: STRING,                     // clinic_note, consult, preop, postop
    content: STRING,                  // Template content with placeholders
    sections: LIST<STRING>,           // Section names in order
    active: BOOLEAN,
    version: STRING,
    created_at: DATETIME,
    updated_at: DATETIME
})
```

#### 3.3.2 User Nodes

```cypher
(:User {
    id: STRING (UUID),
    user_id: STRING,                  // External user ID (from VA system)
    username: STRING,
    role: STRING,                     // user, admin
    preferences: MAP,                 // User preferences (JSON)
    default_template: STRING,
    default_llm_provider: STRING,
    created_at: DATETIME,
    last_login: DATETIME
})
```

---

## 4. Vector Search Architecture

### 4.1 Embedding Strategy

**Model**: sentence-transformers/all-MiniLM-L6-v2
**Dimensions**: 768
**Similarity Function**: Cosine similarity
**Embedding Generation**: HuggingFace Transformers via LangChain

### 4.2 HNSW Index Configuration

Neo4j uses Hierarchical Navigable Small World (HNSW) graphs for fast approximate nearest neighbor search.

```cypher
// Document embeddings - Primary RAG retrieval
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,                    // Max connections per layer
        `vector.hnsw.ef_construction`: 200,     // Exploration during construction
        `vector.quantization.enabled`: false    // Disable quantization for accuracy
    }
};

// ClinicalConcept embeddings - Concept-based retrieval
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200
    }
};
```

**HNSW Parameter Tuning:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `m` | 16 | Balance between accuracy and memory (default for medical use) |
| `ef_construction` | 200 | Higher value for better index quality (construction time trade-off) |
| `quantization` | Disabled | Medical applications require full precision |

### 4.3 Vector Search Queries

#### 4.3.1 Basic Similarity Search

```cypher
// Find top-K similar documents to query embedding
WITH $query_embedding AS queryVector

CALL db.index.vector.queryNodes('document_embeddings', 10, queryVector)
YIELD node, score

RETURN node.id AS doc_id,
       node.title AS title,
       node.summary AS summary,
       node.source AS source,
       score AS similarity_score
ORDER BY score DESC
LIMIT 10;
```

#### 4.3.2 Filtered Vector Search

```cypher
// Vector search with category filter
WITH $query_embedding AS queryVector,
     $category AS categoryFilter

CALL db.index.vector.queryNodes('document_embeddings', 20, queryVector)
YIELD node, score

WHERE node.category = categoryFilter
  AND node.publication_date >= date('2020-01-01')  // Recent guidelines only

RETURN node.id AS doc_id,
       node.title AS title,
       node.content AS content,
       node.version AS version,
       score AS similarity_score
ORDER BY score DESC
LIMIT 5;
```

#### 4.3.3 Hybrid Retrieval (Vector + Graph)

```cypher
// Combined vector search + graph traversal for context-aware retrieval
WITH $query_embedding AS queryVector,
     $category AS categoryFilter

// Step 1: Vector search for relevant documents
CALL db.index.vector.queryNodes('document_embeddings', 10, queryVector)
YIELD node AS doc, score

WHERE doc.category = categoryFilter

// Step 2: Graph traversal to find related clinical concepts
MATCH (doc)-[:REFERENCES]->(concept:ClinicalConcept)

// Step 3: Find calculators applicable to these concepts
OPTIONAL MATCH (concept)<-[:APPLIES_TO]-(calc:Calculator)

// Return combined results
RETURN doc.id AS document_id,
       doc.title AS document_title,
       doc.content AS content,
       score AS vector_score,
       collect(DISTINCT concept.name) AS related_concepts,
       collect(DISTINCT calc.name) AS applicable_calculators
ORDER BY score DESC
LIMIT 5;
```

### 4.4 Performance Benchmarks

| Query Type | Target Latency | Expected Throughput |
|------------|----------------|---------------------|
| Top-10 vector search | < 100ms | 500+ queries/sec |
| Filtered vector search (category) | < 150ms | 400+ queries/sec |
| Hybrid vector + graph traversal | < 250ms | 300+ queries/sec |
| Batch embedding generation | < 2s for 100 docs | 50+ docs/sec |

---

## 5. Performance Optimization

### 5.1 Neo4j Configuration (Production)

**File**: `/neo4j/conf/neo4j.conf`

```properties
# Memory Configuration (for 32GB RAM server)
dbms.memory.heap.initial_size=8g
dbms.memory.heap.max_size=8g
dbms.memory.pagecache.size=16g

# Connection Configuration
dbms.connector.bolt.listen_address=0.0.0.0:7687
dbms.connector.bolt.thread_pool.min_size=50
dbms.connector.bolt.thread_pool.max_size=400

# Transaction Configuration
dbms.transaction.timeout=30s
dbms.transaction.concurrent.maximum=1000

# Query Performance
dbms.query.cache.size=1000
cypher.query_cache_size=1000

# Vector Search Optimization
db.index.vector.ephemeral_graph_enabled=true

# Plugins
dbms.security.procedures.unrestricted=apoc.*,gds.*
dbms.security.procedures.allowlist=apoc.*,gds.*

# Logging
dbms.logs.query.enabled=true
dbms.logs.query.threshold=1s
dbms.logs.query.parameter_logging_enabled=false  # HIPAA: No query parameters logged

# Security
dbms.ssl.policy.bolt.enabled=true
dbms.ssl.policy.bolt.base_directory=/var/lib/neo4j/certificates/bolt
```

### 5.2 Connection Pooling

**Python Driver Configuration:**

```python
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable
import asyncio
from typing import Optional

class Neo4jConnectionPool:
    """Managed Neo4j connection pool with health checking."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        max_connection_lifetime: int = 3600,  # 1 hour
        max_connection_pool_size: int = 100,
        connection_acquisition_timeout: int = 60
    ):
        self.driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            max_connection_lifetime=max_connection_lifetime,
            max_connection_pool_size=max_connection_pool_size,
            connection_acquisition_timeout=connection_acquisition_timeout,
            encrypted=True,
            trust=True
        )

    def close(self):
        self.driver.close()

    async def verify_connectivity(self) -> bool:
        """Verify database connectivity."""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                return result.single()["test"] == 1
        except ServiceUnavailable:
            return False
```

### 5.3 Query Optimization Strategies

#### 5.3.1 Use APOC for Batch Operations

```cypher
// Batch document ingestion with APOC
CALL apoc.periodic.iterate(
    'UNWIND $documents AS doc RETURN doc',
    'MERGE (d:Document {id: doc.id})
     SET d.title = doc.title,
         d.content = doc.content,
         d.embedding = doc.embedding,
         d.category = doc.category,
         d.created_at = datetime()',
    {batchSize: 1000, parallel: true, params: {documents: $doc_list}}
);
```

#### 5.3.2 Use Graph Data Science for Advanced Analytics

```cypher
// Create in-memory graph projection for analysis
CALL gds.graph.project(
    'clinical-knowledge-graph',
    ['Document', 'ClinicalConcept', 'Calculator'],
    ['REFERENCES', 'RELATED_TO', 'APPLIES_TO']
);

// Run PageRank to find most important documents
CALL gds.pageRank.stream('clinical-knowledge-graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).title AS document, score
ORDER BY score DESC
LIMIT 10;
```

### 5.4 Caching Strategy

**Redis Integration for Embedding Cache:**

```python
import redis
import hashlib
import json
from typing import List, Optional

class EmbeddingCache:
    """Redis cache for frequently accessed embeddings."""

    def __init__(self, redis_url: str):
        self.redis_client = redis.from_url(redis_url)
        self.cache_ttl = 3600  # 1 hour

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Retrieve cached embedding."""
        cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
        cached = self.redis_client.get(cache_key)
        return json.loads(cached) if cached else None

    def set_embedding(self, text: str, embedding: List[float]):
        """Store embedding in cache."""
        cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
        self.redis_client.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(embedding)
        )
```

---

## 6. HIPAA Compliance & Session Management

### 6.1 Zero-Persistence PHI Architecture

**CRITICAL PRINCIPLE**: Neo4j stores NO patient clinical information.

What is stored:
- Clinical knowledge (guidelines, references) - NOT patient-specific
- Session metadata - timestamps, user IDs, module usage
- Audit logs - hashed identifiers only, no content

What is NEVER stored:
- Patient clinical input
- Generated clinical notes
- Patient identifiers (MRN, SSN, etc.)
- Any Protected Health Information (PHI)

### 6.2 Session TTL Implementation

#### 6.2.1 Session Creation with Expiration

```cypher
// Create new session with 30-minute TTL
MERGE (u:User {user_id: $user_id})

CREATE (s:Session {
    id: apoc.create.uuid(),
    session_id: $session_id,
    user_id: $user_id,
    note_type: $note_type,
    llm_provider: $llm_provider,
    model_used: $model_used,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    last_accessed: datetime(),
    status: 'active'
})

CREATE (s)-[:BELONGS_TO]->(u)

RETURN s.id AS session_id, s.expires_at AS expires_at;
```

#### 6.2.2 Automatic TTL Cleanup

**Background Cleanup Job (runs every 5 minutes):**

```cypher
// Delete expired sessions
MATCH (s:Session)
WHERE s.expires_at < datetime()
  AND s.status = 'active'

// Mark as expired first (for audit trail)
SET s.status = 'expired'

WITH s

// Detach and delete
DETACH DELETE s

RETURN count(s) AS sessions_deleted;
```

**Python Implementation of Cleanup Scheduler:**

```python
import schedule
import time
from neo4j import GraphDatabase

class SessionCleanupScheduler:
    """Background scheduler for session TTL cleanup."""

    def __init__(self, driver: GraphDatabase.driver):
        self.driver = driver

    def cleanup_expired_sessions(self):
        """Delete expired sessions from Neo4j."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Session)
                WHERE s.expires_at < datetime() AND s.status = 'active'
                SET s.status = 'expired'
                WITH s
                DETACH DELETE s
                RETURN count(s) AS deleted_count
            """)

            deleted_count = result.single()["deleted_count"]
            print(f"Cleaned up {deleted_count} expired sessions")
            return deleted_count

    def start(self):
        """Start the cleanup scheduler."""
        schedule.every(5).minutes.do(self.cleanup_expired_sessions)

        while True:
            schedule.run_pending()
            time.sleep(60)
```

### 6.3 Audit Logging (Metadata Only)

```cypher
// Create audit log entry (NO PHI)
CREATE (a:AuditLog {
    id: apoc.create.uuid(),
    session_id: $session_id,
    user_id: $user_id,
    action: $action,                      // e.g., 'note_generation'
    module_used: $module_used,            // e.g., 'capra_score'
    input_hash: $input_hash,              // SHA256 hash only
    output_hash: $output_hash,            // SHA256 hash only
    duration_ms: $duration_ms,
    tokens_used: $tokens_used,
    llm_provider: $llm_provider,
    model_used: $model_used,
    success: $success,
    error_code: $error_code,
    created_at: datetime(),
    expires_at: datetime() + duration({days: 90})
})

WITH a

MATCH (s:Session {session_id: $session_id})
CREATE (a)-[:LOGGED]->(s)

RETURN a.id AS audit_log_id;
```

### 6.4 HIPAA Compliance Checklist

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Access Controls (164.312(a)) | JWT authentication via FastAPI | Implemented |
| Audit Controls (164.312(b)) | Metadata-only audit logs in Neo4j | Implemented |
| Integrity Controls (164.312(c)) | TLS 1.3 for Neo4j Bolt protocol | Implemented |
| Transmission Security (164.312(e)) | Encrypted Bolt connections | Implemented |
| PHI Minimization | Zero PHI storage in Neo4j | Implemented |
| Automatic Logoff (164.312(a)(2)(iii)) | 30-minute session TTL | Implemented |
| Data Backup | Neo4j backups contain NO PHI | Verified |

---

## 7. Integration Architecture

### 7.1 FastAPI Integration

**Python Client Implementation:**

See `/home/gulab/PythonProjects/VAUCDA/backend/database/neo4j_client.py` for full implementation.

**Key Integration Points:**

1. **RAG Pipeline**: Vector search for document retrieval
2. **Clinical Modules**: Calculator metadata and relationships
3. **Session Management**: TTL-based session tracking
4. **Audit Logging**: Metadata-only activity logs

### 7.2 LangChain RAG Integration

```python
from langchain.vectorstores import Neo4jVector
from langchain.embeddings import HuggingFaceEmbeddings

class ClinicalRAGPipeline:
    """RAG pipeline using Neo4j vector search."""

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

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
        """Retrieve top-K relevant documents."""
        filter_dict = {"category": category} if category else None

        docs = await self.vector_store.asimilarity_search_with_score(
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
```

### 7.3 Redis Caching Integration

```python
class CachedNeo4jClient:
    """Neo4j client with Redis caching layer."""

    def __init__(self, neo4j_client, redis_client):
        self.neo4j = neo4j_client
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour

    async def cached_vector_search(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None
    ) -> List[dict]:
        """Vector search with Redis caching."""
        # Generate cache key
        cache_key = f"vsearch:{hashlib.sha256(query.encode()).hexdigest()}:{category}:{k}"

        # Check cache
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # Query Neo4j
        results = await self.neo4j.vector_search(query, k, category)

        # Cache results
        self.redis.setex(cache_key, self.cache_ttl, json.dumps(results))

        return results
```

### 7.4 Celery Background Jobs

```python
from celery import Celery

celery_app = Celery('vaucda', broker='redis://localhost:6379/0')

@celery_app.task
def ingest_documents_batch(documents: List[dict]):
    """Background job for batch document ingestion."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        session.run("""
            UNWIND $documents AS doc
            MERGE (d:Document {id: doc.id})
            SET d.title = doc.title,
                d.content = doc.content,
                d.embedding = doc.embedding,
                d.category = doc.category,
                d.created_at = datetime()
        """, documents=documents)

    driver.close()
```

---

## 8. Deployment Strategy

### 8.1 Docker Compose Configuration

See `/home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml`

### 8.2 Persistent Volume Management

```yaml
volumes:
  neo4j_data:
    driver: local
    driver_opts:
      type: none
      device: /var/lib/neo4j/data
      o: bind

  neo4j_logs:
    driver: local
    driver_opts:
      type: none
      device: /var/log/neo4j
      o: bind

  neo4j_import:
    driver: local
    driver_opts:
      type: none
      device: /var/lib/neo4j/import
      o: bind
```

### 8.3 Backup and Restore

**Backup Procedure:**

```bash
#!/bin/bash
# /opt/vaucda/scripts/neo4j_backup.sh

BACKUP_DIR="/backups/neo4j"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Stop Neo4j
docker-compose -f /opt/vaucda/neo4j/docker-compose.neo4j.yml stop neo4j

# Backup data directory
tar -czf "${BACKUP_DIR}/neo4j_data_${TIMESTAMP}.tar.gz" /var/lib/neo4j/data

# Start Neo4j
docker-compose -f /opt/vaucda/neo4j/docker-compose.neo4j.yml start neo4j

# Verify backup
if [ -f "${BACKUP_DIR}/neo4j_data_${TIMESTAMP}.tar.gz" ]; then
    echo "Backup successful: neo4j_data_${TIMESTAMP}.tar.gz"
else
    echo "Backup failed!"
    exit 1
fi
```

**Restore Procedure:**

```bash
#!/bin/bash
# /opt/vaucda/scripts/neo4j_restore.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

# Stop Neo4j
docker-compose -f /opt/vaucda/neo4j/docker-compose.neo4j.yml stop neo4j

# Restore data
tar -xzf "$BACKUP_FILE" -C /var/lib/neo4j/

# Start Neo4j
docker-compose -f /opt/vaucda/neo4j/docker-compose.neo4j.yml start neo4j
```

### 8.4 Monitoring and Health Checks

**Health Check Query:**

```cypher
// Health check query (run every 30 seconds)
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Transactions")
YIELD attributes
RETURN attributes.NumberOfOpenTransactions.value AS open_transactions,
       attributes.PeakNumberOfConcurrentTransactions.value AS peak_transactions;
```

**Python Health Check:**

```python
async def check_neo4j_health(driver) -> dict:
    """Check Neo4j database health."""
    try:
        with driver.session() as session:
            # Check connectivity
            result = session.run("RETURN 1 AS health")
            if result.single()["health"] != 1:
                return {"status": "unhealthy", "reason": "Query failed"}

            # Check vector indexes
            indexes = session.run("SHOW INDEXES YIELD name, state WHERE name IN ['document_embeddings', 'concept_embeddings']")
            index_states = {record["name"]: record["state"] for record in indexes}

            if any(state != "ONLINE" for state in index_states.values()):
                return {"status": "degraded", "reason": "Vector indexes not online", "indexes": index_states}

            return {"status": "healthy", "indexes": index_states}

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

---

## 9. Monitoring & Maintenance

### 9.1 Performance Metrics

**Key Metrics to Monitor:**

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| Query latency (p95) | Via logs | > 1 second |
| Vector search latency | Via logs | > 200ms |
| Active connections | JMX | > 350 |
| Heap memory usage | JMX | > 90% |
| Page cache hit rate | JMX | < 85% |
| Session count | `MATCH (s:Session) RETURN count(s)` | > 600 |

### 9.2 Maintenance Procedures

#### 9.2.1 Weekly Maintenance

```cypher
// Analyze database statistics (run weekly)
CALL db.stats.retrieve('GRAPH COUNTS');

// Check index health
SHOW INDEXES YIELD name, state, populationPercent;

// Cleanup old audit logs (older than 90 days)
MATCH (a:AuditLog)
WHERE a.expires_at < datetime()
DETACH DELETE a;
```

#### 9.2.2 Monthly Maintenance

```bash
#!/bin/bash
# Monthly Neo4j maintenance

# 1. Full backup
/opt/vaucda/scripts/neo4j_backup.sh

# 2. Analyze database size
docker exec neo4j-container du -sh /data/databases/neo4j

# 3. Check slow queries
docker exec neo4j-container grep "time=" /logs/query.log | awk '{if ($NF > 1000) print}' | tail -50
```

### 9.3 Scaling Strategy

**Horizontal Scaling (Production):**

For production deployments exceeding 500 concurrent users:

1. **Neo4j Causal Cluster**: Deploy 3+ core servers for high availability
2. **Read Replicas**: Add read replicas for vector search queries
3. **Load Balancing**: Use Neo4j's built-in routing for read/write separation

```python
# Cluster-aware driver configuration
driver = GraphDatabase.driver(
    "neo4j://neo4j-cluster:7687",  # Cluster endpoint
    auth=(username, password),
    max_connection_pool_size=200,  # Increased for cluster
    routing_context={"policy": "round_robin"}
)
```

---

## 10. Query Patterns & Examples

See `/home/gulab/PythonProjects/VAUCDA/backend/database/neo4j_queries.py` for complete query library.

### 10.1 Common Query Patterns

**Pattern 1: RAG Document Retrieval**

```cypher
// Retrieve top-K documents with graph context
WITH $query_embedding AS queryVector, $category AS cat

CALL db.index.vector.queryNodes('document_embeddings', 10, queryVector)
YIELD node AS doc, score

WHERE doc.category = cat

MATCH (doc)-[:REFERENCES]->(concept:ClinicalConcept)
OPTIONAL MATCH (concept)<-[:APPLIES_TO]-(calc:Calculator)

RETURN doc.id AS document_id,
       doc.title AS title,
       doc.content AS content,
       score AS relevance_score,
       collect(DISTINCT concept.name) AS related_concepts,
       collect(DISTINCT calc.name) AS applicable_calculators
ORDER BY score DESC
LIMIT 5;
```

**Pattern 2: Session Management**

```cypher
// Create session with audit log
MERGE (u:User {user_id: $user_id})

CREATE (s:Session {
    id: apoc.create.uuid(),
    session_id: $session_id,
    user_id: $user_id,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    status: 'active'
})

CREATE (a:AuditLog {
    id: apoc.create.uuid(),
    session_id: $session_id,
    action: 'session_created',
    created_at: datetime()
})

CREATE (s)-[:BELONGS_TO]->(u)
CREATE (a)-[:LOGGED]->(s)

RETURN s.id AS session_id, s.expires_at;
```

**Pattern 3: Calculator Discovery**

```cypher
// Find applicable calculators for a clinical concept
MATCH (concept:ClinicalConcept {name: $concept_name})
MATCH (concept)<-[:APPLIES_TO]-(calc:Calculator)
MATCH (calc)-[:DERIVED_FROM]->(doc:Document)

RETURN calc.name AS calculator_name,
       calc.description AS description,
       calc.inputs AS required_inputs,
       collect(doc.title) AS evidence_sources
ORDER BY calc.usage_count DESC;
```

---

## Appendix A: Schema Initialization Scripts

See `/home/gulab/PythonProjects/VAUCDA/backend/database/migrations/neo4j/init_schema.cypher`

## Appendix B: Performance Tuning Guide

**For 32GB RAM Server:**
- Heap: 8GB
- Page Cache: 16GB
- Remaining: OS and other services

**For 64GB RAM Server:**
- Heap: 16GB
- Page Cache: 40GB
- Remaining: OS and other services

## Appendix C: Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Slow vector searches | Index not online | Run `SHOW INDEXES` to verify |
| High memory usage | Large result sets | Add `LIMIT` clauses to queries |
| Connection timeouts | Pool exhausted | Increase `max_connection_pool_size` |
| TTL not working | APOC not installed | Verify APOC plugin installation |

---

**Document Version:** 1.0
**Last Updated:** November 29, 2025
**Next Review:** February 29, 2026
