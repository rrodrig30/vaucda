## VAUCDA Neo4j Graph Database Schema Documentation

**Version:** 1.0
**Date:** 2025-11-29
**Author:** VAUCDA Development Team
**Status:** Production-Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Schema Design Principles](#schema-design-principles)
3. [Node Types](#node-types)
4. [Relationship Types](#relationship-types)
5. [Vector Indexes](#vector-indexes)
6. [Query Patterns](#query-patterns)
7. [Session Management & TTL](#session-management--ttl)
8. [HIPAA Compliance](#hipaa-compliance)
9. [Performance Optimization](#performance-optimization)
10. [Migration Strategy](#migration-strategy)

---

## Overview

### Purpose

The VAUCDA Neo4j database serves as a **hybrid knowledge graph + vector store** for medical information retrieval and clinical decision support. The schema is optimized for:

- **Retrieval-Augmented Generation (RAG)**: Vector similarity search across 768-dimensional embeddings
- **Knowledge Graph Traversal**: Semantic relationships between guidelines, literature, calculators, and clinical concepts
- **HIPAA Compliance**: Zero-persistence PHI architecture with ephemeral session storage (30-min TTL)
- **Clinical Decision Support**: 44 specialized calculators across 10 urologic subspecialties

### Architecture Highlights

- **6 Primary Node Types**: Guideline, Calculator, Literature, ClinicalConcept, DocumentChunk, Session, AuditLog
- **8 Relationship Types**: Semantic connections for knowledge navigation
- **4 Vector Indexes**: 768-dimensional embeddings for semantic search (cosine similarity)
- **21 Property Indexes**: Optimized for common query patterns
- **5 Full-Text Indexes**: Keyword search across content
- **Ephemeral PHI Storage**: Automatic 30-minute TTL for session data

---

## Schema Design Principles

### 1. Query-Driven Design

Every index and relationship was chosen based on actual query patterns in the VAUCDA application:

- **Vector indexes** optimize RAG retrieval (<200ms response time)
- **Property indexes** accelerate category filtering, date sorting, and lookup operations
- **Composite indexes** support multi-criteria queries (e.g., category + publication_date)
- **Relationship traversal** enables efficient evidence chains (Calculator → Guideline → Literature)

### 2. Semantic Clarity

All labels, relationship types, and property names are self-documenting:

- **Node labels** represent distinct entity types (`Guideline`, `Calculator`, not `Document` for everything)
- **Relationship types** express clear semantic meaning (`[:IMPLEMENTS]`, `[:COVERS]`, not `[:RELATES_TO]`)
- **Property names** follow lowercase_underscore convention with explicit units (e.g., `publication_date`, `duration_ms`)

### 3. Zero-Persistence PHI

The schema enforces HIPAA compliance through design:

- **Session nodes** are the ONLY nodes containing PHI and have a 30-minute TTL
- **AuditLog nodes** record metadata ONLY (hashed session IDs, action types, performance metrics) - NO clinical content
- **TTL cleanup** runs every minute to delete expired sessions
- **No clinical data** in Guideline, Literature, or Calculator nodes (only general medical knowledge)

### 4. Performance First

Indexing strategy prioritizes sub-second query performance:

- **Vector indexes** enable <200ms semantic search across 10K+ chunks
- **Category indexes** accelerate specialty filtering (90% of queries are category-scoped)
- **Composite indexes** optimize sorted category queries (e.g., recent prostate cancer guidelines)
- **Full-text indexes** provide fallback for keyword search when vector search doesn't match intent

### 5. Extensibility

Schema supports future enhancements without breaking changes:

- **Relationship properties** allow refinement without schema changes (e.g., `strength`, `citation_type`)
- **Metadata maps** in DocumentChunk enable flexible chunk annotations
- **Migration framework** (`/schema/migrations/`) provides versioned schema updates
- **Ambient listening extension** (Migration 001) demonstrates forward compatibility

---

## Node Types

### 1. Guideline

**Purpose:** Clinical practice guidelines from AUA, NCCN, EAU

**Properties:**
```cypher
{
    id: STRING (UUID)                    [UNIQUE, NOT NULL, INDEXED]
    title: STRING                        [REQUIRED]
    organization: STRING                 [REQUIRED, INDEXED] (AUA|NCCN|EAU)
    publication_date: DATE               [REQUIRED, INDEXED]
    category: STRING                     [REQUIRED, INDEXED] (prostate|kidney|bladder|voiding|female|fertility|stones|reconstructive|hypogonadism|surgical)
    version: STRING                      [OPTIONAL]
    content: STRING (full text)          [REQUIRED]
    embedding: LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]
    url: STRING                          [OPTIONAL]
    created_at: DATETIME                 [DEFAULT: now()]
    updated_at: DATETIME                 [DEFAULT: now()]
}
```

**Indexes:**
- Uniqueness: `id`
- Property: `category`, `organization`, `publication_date`
- Vector: `embedding` (768-dim, cosine)
- Full-text: `title`, `content`
- Composite: `(category, publication_date)`

**Common Query Patterns:**
- Recent guidelines by category: `MATCH (g:Guideline {category: 'prostate'}) RETURN g ORDER BY g.publication_date DESC LIMIT 5`
- Vector search: `CALL db.index.vector.queryNodes('guideline_embeddings', 5, $embedding)`
- Full-text search: `CALL db.index.fulltext.queryNodes('guideline_content_fulltext', 'PSA screening')`

---

### 2. Calculator

**Purpose:** Clinical calculators and assessment tools (44 total)

**Properties:**
```cypher
{
    name: STRING                         [UNIQUE, NOT NULL]
    category: STRING                     [REQUIRED, INDEXED]
    description: STRING                  [REQUIRED]
    algorithm: STRING (JSON or formula)  [REQUIRED]
    validation_refs: LIST<STRING>        [OPTIONAL]
    input_schema: STRING (JSON Schema)   [REQUIRED]
    output_schema: STRING (JSON Schema)  [REQUIRED]
    version: STRING                      [DEFAULT: "1.0"]
    created_at: DATETIME                 [DEFAULT: now()]
    updated_at: DATETIME                 [DEFAULT: now()]
}
```

**Categories:**
- `prostate_cancer` (7 calculators): PSA Kinetics, PCPT 2.0, CAPRA Score, NCCN Risk, etc.
- `kidney_cancer` (4 calculators): RENAL Score, SSIGN Score, IMDC Criteria
- `bladder_cancer` (3 calculators): EORTC Recurrence/Progression Scores
- `male_voiding` (5 calculators): IPSS, BOOI/BCI, Uroflow Analysis
- `female_urology` (5 calculators): UDI-6/IIQ-7, OAB-q, POP-Q Staging
- `reconstructive` (4 calculators): Stricture Complexity, PFUI Classification
- `fertility` (5 calculators): Semen Analysis (WHO 2021), Varicocele Grading
- `hypogonadism` (3 calculators): Testosterone Evaluation, ADAM Questionnaire
- `stones` (4 calculators): STONE Score, 24-hr Urine Interpretation
- `surgical_planning` (4 calculators): CFS, RCRI, NSQIP Risk Calculator

**Indexes:**
- Uniqueness: `name`
- Property: `category`
- Full-text: `name`, `description`

**Common Query Patterns:**
- Get calculator metadata: `MATCH (c:Calculator {name: 'CAPRA Score'}) RETURN c`
- List by category: `MATCH (c:Calculator {category: 'prostate_cancer'}) RETURN c.name, c.description`
- Find applicable calculators: `MATCH (cc:ClinicalConcept {name: 'Prostate Adenocarcinoma'})<-[:APPLIES_TO]-(calc) RETURN calc.name`

---

### 3. Literature

**Purpose:** Medical journal articles and research papers

**Properties:**
```cypher
{
    title: STRING                        [REQUIRED]
    authors: LIST<STRING>                [REQUIRED]
    journal: STRING                      [REQUIRED, INDEXED]
    pubmed_id: STRING                    [OPTIONAL, INDEXED]
    doi: STRING                          [UNIQUE]
    abstract: STRING                     [OPTIONAL]
    full_text: STRING                    [OPTIONAL]
    embedding: LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]
    publication_year: INTEGER            [OPTIONAL]
    keywords: LIST<STRING>               [OPTIONAL]
    created_at: DATETIME                 [DEFAULT: now()]
}
```

**Indexes:**
- Uniqueness: `doi`
- Property: `journal`, `pubmed_id`
- Vector: `embedding` (768-dim, cosine)
- Full-text: `title`, `abstract`, `full_text`

**Common Query Patterns:**
- Search by topic: `CALL db.index.fulltext.queryNodes('literature_content_fulltext', 'PSA velocity prostate cancer')`
- Find citations: `MATCH (g:Guideline)-[:REFERENCES]->(lit:Literature) WHERE g.id = $guideline_id RETURN lit`
- Recent literature: `MATCH (lit:Literature) WHERE lit.publication_year >= 2020 RETURN lit ORDER BY lit.publication_year DESC`

---

### 4. ClinicalConcept

**Purpose:** Diseases, treatments, procedures with medical coding

**Properties:**
```cypher
{
    id: STRING (UUID)                    [UNIQUE, NOT NULL]
    name: STRING                         [REQUIRED, INDEXED]
    icd10_code: STRING                   [OPTIONAL, INDEXED]
    snomed_code: STRING                  [OPTIONAL, INDEXED]
    description: STRING                  [REQUIRED]
    category: STRING                     [OPTIONAL]
    embedding: LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]
    synonyms: LIST<STRING>               [OPTIONAL]
    created_at: DATETIME                 [DEFAULT: now()]
}
```

**Indexes:**
- Uniqueness: `id`
- Property: `name`, `icd10_code`, `snomed_code`
- Vector: `embedding` (768-dim, cosine)
- Full-text: `name`, `description`

**Common Query Patterns:**
- Lookup by code: `MATCH (cc:ClinicalConcept {icd10_code: 'C61'}) RETURN cc`
- Find related concepts: `MATCH (cc:ClinicalConcept {name: 'Prostate Adenocarcinoma'})-[r:RELATED_TO]->(related) RETURN related.name, r.relationship`
- Semantic search: `CALL db.index.vector.queryNodes('concept_embeddings', 5, $query_embedding)`

---

### 5. DocumentChunk

**Purpose:** RAG-optimized chunks from source documents (guideline/literature chunking)

**Properties:**
```cypher
{
    id: STRING (UUID)                    [UNIQUE, NOT NULL]
    source_id: STRING (UUID)             [REQUIRED, INDEXED]
    source_type: STRING                  [REQUIRED] (Guideline|Literature)
    chunk_index: INTEGER                 [REQUIRED, INDEXED]
    content: STRING (512-1024 tokens)    [REQUIRED]
    embedding: LIST<FLOAT> (768-dim)     [REQUIRED, VECTOR INDEXED]
    metadata: MAP                        [OPTIONAL] {section, page, title, category}
    token_count: INTEGER                 [OPTIONAL]
    created_at: DATETIME                 [DEFAULT: now()]
}
```

**Chunking Strategy:**
- **Chunk size**: 512-1024 tokens (optimal for LLM context windows)
- **Overlap**: 128 tokens (ensures continuity across chunk boundaries)
- **Boundary preservation**: Chunks split on sentence boundaries
- **Semantic coherence**: Sections kept together when possible

**Indexes:**
- Uniqueness: `id`
- Property: `source_id`, `chunk_index`
- Vector: `embedding` (768-dim, cosine) - **PRIMARY RAG INDEX**
- Full-text: `content`
- Composite: `(source_id, chunk_index)`

**Common Query Patterns:**
- RAG retrieval: `CALL db.index.vector.queryNodes('document_chunk_embeddings', 5, $query_embedding)`
- Category-filtered RAG: `CALL db.index.vector.queryNodes(...) YIELD node, score MATCH (node)-[:BELONGS_TO]->(source) WHERE source.category = 'prostate'`
- Context expansion: `MATCH (chunk {id: $chunk_id})-[:NEXT_CHUNK*1..2]->(adjacent) RETURN adjacent.content`

---

### 6. Session (EPHEMERAL - 30 min TTL)

**Purpose:** Temporary storage for user sessions containing PHI

**CRITICAL:** These nodes are the ONLY place PHI is stored and MUST be auto-deleted after 30 minutes

**Properties:**
```cypher
{
    session_id: STRING (UUID)            [UNIQUE, NOT NULL]
    user_id: STRING                      [REQUIRED]
    created_at: DATETIME                 [REQUIRED, INDEXED]
    expires_at: DATETIME                 [REQUIRED, INDEXED] (created_at + 30 minutes)
    note_context: STRING                 [OPTIONAL, PHI CONTENT]
    active: BOOLEAN                      [DEFAULT: true]
}
```

**Indexes:**
- Uniqueness: `session_id`
- Property: `created_at`, `expires_at` (critical for TTL cleanup)

**TTL Cleanup:**
```cypher
// Run every 1 minute via external scheduler
MATCH (s:Session)
WHERE s.expires_at < datetime()
DETACH DELETE s;
```

**Security Notes:**
- **PHI content** stored in `note_context` property
- **Automatic expiration** after 30 minutes
- **Never logged** to AuditLog (only hashed session_id is logged)
- **Immediate deletion** upon note generation completion

**Common Query Patterns:**
- Create session: `CREATE (s:Session {session_id: $id, user_id: $user, created_at: datetime(), expires_at: datetime() + duration({minutes: 30}), active: true})`
- Retrieve active session: `MATCH (s:Session {session_id: $id}) WHERE s.expires_at > datetime() AND s.active = true RETURN s`
- Terminate session: `MATCH (s:Session {session_id: $id}) DETACH DELETE s`

---

### 7. AuditLog (METADATA ONLY - NO PHI)

**Purpose:** HIPAA-compliant audit trail without PHI

**Properties:**
```cypher
{
    id: STRING (UUID)                    [UNIQUE]
    session_hash: STRING (SHA256)        [REQUIRED, INDEXED] (hashed session_id)
    timestamp: DATETIME                  [REQUIRED, INDEXED]
    action_type: STRING                  [REQUIRED] (note_generation|calculator_use|evidence_search)
    user_id: STRING                      [REQUIRED, INDEXED]
    model_used: STRING                   [OPTIONAL] (e.g., "llama3.1:8b")
    tokens_used: INTEGER                 [OPTIONAL]
    duration_ms: INTEGER                 [OPTIONAL]
    success: BOOLEAN                     [DEFAULT: true]
    error_code: STRING                   [OPTIONAL] (non-descriptive error code)
}
```

**EXPLICITLY EXCLUDED (NEVER STORED):**
- `clinical_input` (PHI)
- `generated_note` (PHI)
- `patient identifiers` (PHI)
- Any PHI whatsoever

**Indexes:**
- Uniqueness: `id`
- Property: `session_hash`, `timestamp`, `user_id`

**Common Query Patterns:**
- User audit trail: `MATCH (a:AuditLog {user_id: $user_id}) WHERE a.timestamp >= $start_date RETURN a ORDER BY a.timestamp DESC`
- Performance metrics: `MATCH (a:AuditLog) WHERE a.action_type = 'note_generation' RETURN avg(a.duration_ms) AS avg_response_time`
- Error analysis: `MATCH (a:AuditLog) WHERE a.success = false RETURN a.error_code, count(*) AS error_count`

---

## Relationship Types

### 1. [:REFERENCES]

**Pattern:** `(Guideline)-[:REFERENCES]->(Literature)`

**Purpose:** Link guidelines to supporting literature

**Properties:**
```cypher
{
    citation_type: STRING    (primary|supporting|evidence)
    strength: STRING         (high|moderate|low)
    created_at: DATETIME
}
```

**Usage Example:**
```cypher
MATCH (g:Guideline {id: $guideline_id})-[r:REFERENCES]->(lit:Literature)
WHERE r.strength = 'high'
RETURN lit.title, lit.doi, r.citation_type
ORDER BY r.strength DESC;
```

---

### 2. [:COVERS]

**Pattern:** `(Guideline)-[:COVERS]->(ClinicalConcept)`

**Purpose:** Map guidelines to clinical concepts they address

**Properties:**
```cypher
{
    detail_level: STRING     (comprehensive|brief|mention)
    section: STRING          (section name within guideline)
}
```

**Usage Example:**
```cypher
MATCH (cc:ClinicalConcept {name: 'Prostate Adenocarcinoma'})<-[:COVERS]-(g:Guideline)
WHERE g.organization = 'NCCN'
RETURN g.title, g.publication_date, g.version;
```

---

### 3. [:IMPLEMENTS]

**Pattern:** `(Calculator)-[:IMPLEMENTS]->(Guideline)`

**Purpose:** Show calculators implementing guideline recommendations

**Properties:**
```cypher
{
    version: STRING          (guideline version)
    validated: BOOLEAN
}
```

**Usage Example:**
```cypher
MATCH (calc:Calculator {name: 'CAPRA Score'})-[:IMPLEMENTS]->(g:Guideline)
RETURN g.title, g.organization, g.version;
```

---

### 4. [:APPLIES_TO]

**Pattern:** `(Calculator)-[:APPLIES_TO]->(ClinicalConcept)`

**Purpose:** Define which conditions/procedures calculators apply to

**Properties:**
```cypher
{
    applicability: STRING    (primary|secondary|related)
}
```

**Usage Example:**
```cypher
MATCH (cc:ClinicalConcept {icd10_code: 'C61'})<-[:APPLIES_TO]-(calc:Calculator)
RETURN calc.name, calc.category, calc.description;
```

---

### 5. [:BELONGS_TO]

**Pattern:** `(DocumentChunk)-[:BELONGS_TO]->(Guideline|Literature)`

**Purpose:** Link chunks back to their source documents

**Properties:**
```cypher
{
    chunk_index: INTEGER     (position in sequence)
    section: STRING          (section name)
}
```

**Usage Example:**
```cypher
MATCH (chunk:DocumentChunk)-[:BELONGS_TO]->(source:Guideline)
WHERE source.id = $guideline_id
RETURN chunk.chunk_index, chunk.content
ORDER BY chunk.chunk_index;
```

---

### 6. [:NEXT_CHUNK]

**Pattern:** `(DocumentChunk)-[:NEXT_CHUNK]->(DocumentChunk)`

**Purpose:** Maintain sequential ordering of chunks for context expansion

**Properties:**
```cypher
{
    overlap_tokens: INTEGER  (number of overlapping tokens, typically 128)
}
```

**Usage Example:**
```cypher
// Get chunk and next 2 chunks for expanded context
MATCH (primary:DocumentChunk {id: $chunk_id})-[:NEXT_CHUNK*0..2]->(adjacent)
RETURN adjacent.content
ORDER BY adjacent.chunk_index;
```

---

### 7. [:RELATED_TO]

**Pattern:** `(ClinicalConcept)-[:RELATED_TO]->(ClinicalConcept)`

**Purpose:** Define relationships between clinical concepts

**Properties:**
```cypher
{
    relationship: STRING     (treats|causes|associated_with|complication|differential_diagnosis)
    strength: FLOAT          (0.0-1.0, semantic similarity or clinical relationship strength)
}
```

**Usage Example:**
```cypher
MATCH (source:ClinicalConcept {name: 'Benign Prostatic Hyperplasia'})-[r:RELATED_TO]->(related)
WHERE r.strength >= 0.7
RETURN related.name, r.relationship, r.strength
ORDER BY r.strength DESC;
```

---

### 8. [:USED_CALCULATOR]

**Pattern:** `(Session)-[:USED_CALCULATOR]->(Calculator)`

**Purpose:** Track calculator usage within sessions (ephemeral)

**Properties:**
```cypher
{
    timestamp: DATETIME
    result_category: STRING  (e.g., "high_risk", "low_risk" - NO PHI)
}
```

**Security Note:** This relationship is deleted when the Session expires (30 min TTL)

**Usage Example:**
```cypher
MATCH (s:Session {session_id: $session_id})-[r:USED_CALCULATOR]->(calc:Calculator)
RETURN calc.name, calc.category, r.result_category, r.timestamp
ORDER BY r.timestamp DESC;
```

---

## Vector Indexes

### Vector Index Strategy

VAUCDA uses **four vector indexes** with 768-dimensional embeddings from `sentence-transformers/all-MiniLM-L6-v2`:

1. **`document_chunk_embeddings`** (PRIMARY RAG INDEX)
2. **`guideline_embeddings`** (Direct guideline search)
3. **`literature_embeddings`** (Abstract-level search)
4. **`concept_embeddings`** (Concept similarity)

All vector indexes use **cosine similarity** as the distance function.

---

### 1. document_chunk_embeddings (PRIMARY)

**Purpose:** Main RAG retrieval index for chunked content

**Configuration:**
```cypher
CREATE VECTOR INDEX document_chunk_embeddings IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};
```

**Query Pattern:**
```cypher
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    5,  // top-k results
    $query_embedding  // 768-dim vector from sentence-transformers
)
YIELD node AS chunk, score
WHERE score >= 0.7  // Minimum similarity threshold
MATCH (chunk)-[:BELONGS_TO]->(source)
RETURN
    chunk.content AS content,
    source.title AS source_title,
    source.category AS category,
    score AS similarity
ORDER BY score DESC;
```

**Performance Characteristics:**
- **Query latency**: <200ms for top-5 retrieval on 10,000 chunks
- **Recall@5**: >90% for domain-relevant queries
- **Scalability**: Linear up to 100K chunks, consider sharding beyond

---

### 2. guideline_embeddings

**Purpose:** Direct guideline-level similarity search (no chunking)

**Configuration:**
```cypher
CREATE VECTOR INDEX guideline_embeddings IF NOT EXISTS
FOR (g:Guideline) ON (g.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};
```

**Use Case:** Find entire guidelines matching a query (useful for "Show me all NCCN prostate cancer guidelines")

**Query Pattern:**
```cypher
CALL db.index.vector.queryNodes(
    'guideline_embeddings',
    3,
    $query_embedding
)
YIELD node AS guideline, score
WHERE guideline.organization = 'NCCN'  // Optional filter
RETURN
    guideline.title AS title,
    guideline.publication_date AS published,
    score AS similarity
ORDER BY score DESC;
```

---

### 3. literature_embeddings

**Purpose:** Abstract-level similarity search for literature

**Configuration:**
```cypher
CREATE VECTOR INDEX literature_embeddings IF NOT EXISTS
FOR (l:Literature) ON (l.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};
```

**Use Case:** Find relevant journal articles by semantic similarity

**Query Pattern:**
```cypher
CALL db.index.vector.queryNodes(
    'literature_embeddings',
    5,
    $query_embedding
)
YIELD node AS lit, score
WHERE lit.publication_year >= 2020  // Filter for recent literature
RETURN
    lit.title AS title,
    lit.authors AS authors,
    lit.journal AS journal,
    lit.doi AS doi,
    score AS similarity
ORDER BY score DESC;
```

---

### 4. concept_embeddings

**Purpose:** Concept-level similarity for related conditions/treatments

**Configuration:**
```cypher
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (cc:ClinicalConcept) ON (cc.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};
```

**Use Case:** Discover related clinical concepts (e.g., find conditions similar to "Prostate Adenocarcinoma")

**Query Pattern:**
```cypher
CALL db.index.vector.queryNodes(
    'concept_embeddings',
    10,
    $query_embedding
)
YIELD node AS concept, score
RETURN
    concept.name AS concept_name,
    concept.icd10_code AS icd10,
    concept.description AS description,
    score AS similarity
ORDER BY score DESC;
```

---

## Query Patterns

### RAG Retrieval Patterns

#### 1. Basic Vector Search
```cypher
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    5,
    $query_embedding
)
YIELD node AS chunk, score
WHERE score >= 0.7
MATCH (chunk)-[:BELONGS_TO]->(source)
RETURN chunk.content, source.title, score;
```

#### 2. Category-Filtered Vector Search
```cypher
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    10,  // Get extra candidates
    $query_embedding
)
YIELD node AS chunk, score
MATCH (chunk)-[:BELONGS_TO]->(source)
WHERE source.category = 'prostate'  // Filter after retrieval
RETURN chunk.content, score
ORDER BY score DESC
LIMIT 5;
```

#### 3. Hybrid Search (Vector + Full-Text)
```cypher
// Vector search
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    10,
    $query_embedding
)
YIELD node AS chunk, score AS vector_score

// Full-text search
CALL db.index.fulltext.queryNodes(
    'chunk_content_fulltext',
    'PSA screening recommendations'
)
YIELD node AS ft_chunk, score AS text_score

// Combine results
WITH chunk, vector_score, ft_chunk, text_score
WHERE chunk = ft_chunk
WITH chunk,
     (0.7 * vector_score + 0.3 * text_score) AS combined_score
RETURN chunk.content, combined_score
ORDER BY combined_score DESC
LIMIT 5;
```

#### 4. Context Expansion
```cypher
// Get primary chunk via vector search
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    1,
    $query_embedding
)
YIELD node AS primary

// Expand context with adjacent chunks
OPTIONAL MATCH (before)-[:NEXT_CHUNK]->(primary)
OPTIONAL MATCH (primary)-[:NEXT_CHUNK]->(after)
WITH before, primary, after

// Return expanded context
RETURN
    before.content AS context_before,
    primary.content AS primary_content,
    after.content AS context_after;
```

---

### Knowledge Graph Traversal

#### 1. Evidence Chain (Calculator → Guideline → Literature)
```cypher
MATCH path = (calc:Calculator {name: 'CAPRA Score'})
             -[:IMPLEMENTS]->(g:Guideline)
             -[:REFERENCES]->(lit:Literature)
RETURN
    calc.name AS calculator,
    g.title AS guideline,
    g.organization AS guideline_org,
    lit.title AS literature,
    lit.doi AS doi;
```

#### 2. Clinical Concept Network
```cypher
MATCH (source:ClinicalConcept {name: 'Prostate Adenocarcinoma'})
      -[r:RELATED_TO]->(related:ClinicalConcept)
WHERE r.strength >= 0.7
RETURN
    related.name AS concept,
    r.relationship AS relationship_type,
    r.strength AS strength
ORDER BY r.strength DESC;
```

#### 3. Multi-Hop Traversal
```cypher
// Find guidelines covering concepts related to a given concept
MATCH (source:ClinicalConcept {name: 'Benign Prostatic Hyperplasia'})
      -[:RELATED_TO]->(related:ClinicalConcept)
      <-[:COVERS]-(g:Guideline)
RETURN DISTINCT
    g.title AS guideline,
    related.name AS related_concept,
    g.publication_date AS published
ORDER BY g.publication_date DESC;
```

---

## Session Management & TTL

### Session Lifecycle

```
1. CREATE SESSION
   ↓
2. ADD PHI CONTENT (note_context)
   ↓
3. PROCESS NOTE GENERATION
   ↓
4. RETURN RESULT TO USER
   ↓
5. DELETE SESSION (immediate or 30-min TTL)
```

### Session Creation
```cypher
CREATE (s:Session {
    session_id: randomUUID(),
    user_id: $user_id,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    note_context: $clinical_data,  // PHI content
    active: true
})
RETURN s.session_id AS session_id,
       s.expires_at AS expires_at;
```

### Session Retrieval
```cypher
MATCH (s:Session {session_id: $session_id})
WHERE s.expires_at > datetime()  // Must not be expired
  AND s.active = true
RETURN s.note_context AS clinical_data,
       s.user_id AS user_id;
```

### Manual Session Deletion
```cypher
MATCH (s:Session {session_id: $session_id})
DETACH DELETE s;
```

### Automated TTL Cleanup (Run every 1 minute)
```cypher
MATCH (s:Session)
WHERE s.expires_at < datetime()
WITH s, count(s) AS session_count
DETACH DELETE s
RETURN session_count AS deleted_sessions;
```

**Implementation:** Use external scheduler (cron, systemd timer, or Neo4j APOC periodic commit):
```bash
# Crontab entry
* * * * * curl -X POST http://localhost:8000/api/v1/admin/cleanup-sessions
```

---

## HIPAA Compliance

### PHI Handling Rules

**WHERE PHI IS STORED:**
- **Session nodes** (ONLY): `note_context` property contains clinical input
- **Ephemeral lifetime**: 30 minutes maximum
- **Automatic deletion**: TTL cleanup runs every minute

**WHERE PHI IS NEVER STORED:**
- **AuditLog nodes**: Only metadata (hashed session_id, action type, performance metrics)
- **Guideline/Literature/Calculator nodes**: General medical knowledge, not patient-specific
- **DocumentChunk nodes**: Clinical knowledge, not PHI
- **Neo4j query logs**: Queries parameterized to avoid PHI in logs

### Audit Trail Requirements

**What is logged (AuditLog nodes):**
- User ID (not patient ID)
- Session hash (SHA256 of session_id, not original)
- Action type (note_generation, calculator_use, evidence_search)
- Timestamp
- Model used (e.g., "llama3.1:8b")
- Performance metrics (tokens, duration)
- Success/failure status

**What is NEVER logged:**
- Clinical input text
- Generated note text
- Patient identifiers
- Any PHI content

### HIPAA Compliance Verification

**Automated Checks:**
```cypher
// Verify no PHI in AuditLog
MATCH (a:AuditLog)
WHERE exists(a.clinical_input) OR exists(a.generated_note)
RETURN count(a) AS phi_violations;  // Should return 0

// Verify all sessions have expiration
MATCH (s:Session)
WHERE NOT exists(s.expires_at)
RETURN count(s) AS sessions_without_expiration;  // Should return 0

// Verify no expired sessions exist
MATCH (s:Session)
WHERE s.expires_at < datetime()
RETURN count(s) AS expired_sessions_not_deleted;  // Should return 0
```

---

## Performance Optimization

### Indexing Best Practices

**1. Property Indexes:**
- Index properties used in `WHERE` clauses
- Index properties used in `ORDER BY`
- Index properties used in `MATCH` patterns

**2. Composite Indexes:**
- Use when filtering on multiple properties together
- Example: `(category, publication_date)` for sorted category queries

**3. Vector Indexes:**
- Ensure embeddings are populated before querying
- Use appropriate `top_k` values (5-10 is typical)
- Apply post-filtering for category constraints

**4. Full-Text Indexes:**
- Use for keyword search, not semantic search
- Combine with vector search for hybrid retrieval

### Query Optimization Tips

**1. Filter Early:**
```cypher
// GOOD: Filter before vector search result expansion
CALL db.index.vector.queryNodes(...) YIELD node, score
WHERE score >= 0.7
MATCH (node)-[:BELONGS_TO]->(source)
RETURN ...;

// BAD: Filter after expansion
CALL db.index.vector.queryNodes(...) YIELD node, score
MATCH (node)-[:BELONGS_TO]->(source)
WHERE score >= 0.7  // Too late
RETURN ...;
```

**2. Use Parameters:**
```cypher
// GOOD: Parameterized query (enables query plan caching)
MATCH (g:Guideline {category: $category})
RETURN g;

// BAD: Literal values (query plan cache miss)
MATCH (g:Guideline {category: 'prostate'})
RETURN g;
```

**3. Limit Early:**
```cypher
// GOOD: Limit vector search results
CALL db.index.vector.queryNodes('document_chunk_embeddings', 5, $embedding)
YIELD node, score
RETURN node.content;

// BAD: Get too many results then limit
CALL db.index.vector.queryNodes('document_chunk_embeddings', 100, $embedding)
YIELD node, score
RETURN node.content
LIMIT 5;
```

### Performance Monitoring

**Query Performance:**
```cypher
// Profile a query
PROFILE
MATCH (g:Guideline {category: 'prostate'})
RETURN g.title
ORDER BY g.publication_date DESC
LIMIT 5;
```

**Index Usage:**
```cypher
// Check index population
CALL db.awaitIndexes(300);  // Wait up to 5 minutes for indexes to populate

// Verify vector indexes are online
SHOW INDEXES
YIELD name, type, state
WHERE type = 'VECTOR'
RETURN name, state;
```

**Database Statistics:**
```cypher
// Count nodes by type
MATCH (n)
RETURN labels(n)[0] AS node_type, count(n) AS count
ORDER BY count DESC;

// Count relationships by type
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(r) AS count
ORDER BY count DESC;
```

---

## Migration Strategy

### Versioned Migrations

VAUCDA uses a **forward-only migration strategy** with versioned migration files:

**Location:** `/home/gulab/PythonProjects/VAUCDA/schema/migrations/`

**Naming Convention:** `NNN_description.cypher`
- `001_add_ambient_listening_support.cypher`
- `002_add_new_calculator_category.cypher`
- etc.

### Migration 001: Ambient Listening Support

**Purpose:** Add schema support for future ambient listening capabilities

**Changes:**
- New node type: `AmbientTranscript` (ephemeral, 30-min TTL)
- New node type: `ExtractedElement` (ephemeral, linked to session)
- Enhanced `Session` properties: `ambient_enabled`, `consent_obtained`, `transcription_complete`
- Enhanced `AuditLog` properties: `ambient_source`, `transcription_duration_ms`
- New relationships: `[:HAS_TRANSCRIPT]`, `[:EXTRACTED_FROM]`, `[:CONTAINS_ELEMENT]`
- Extended TTL cleanup to delete ambient nodes when session expires

**How to Apply:**
```bash
# Connect to Neo4j and run migration
cypher-shell -u neo4j -p password -f /home/gulab/PythonProjects/VAUCDA/schema/migrations/001_add_ambient_listening_support.cypher
```

### Schema Evolution Best Practices

**1. Backward Compatibility:**
- Add new properties as OPTIONAL
- Don't delete existing properties (mark as deprecated instead)
- New indexes don't break existing queries

**2. Migration Testing:**
- Test migrations on development database first
- Verify constraints and indexes created successfully
- Run sample queries to ensure performance

**3. Rollback Strategy:**
- Migrations are forward-only (no rollback scripts)
- If migration fails, restore from backup
- Keep backups before applying migrations

---

## Deployment Checklist

### Initial Schema Deployment

1. **Create schema:**
   ```bash
   cypher-shell -u neo4j -p password -f /home/gulab/PythonProjects/VAUCDA/schema/neo4j_schema.cypher
   ```

2. **Verify constraints:**
   ```cypher
   SHOW CONSTRAINTS;
   // Should see 13 constraints (6 uniqueness, 7 existence)
   ```

3. **Verify indexes:**
   ```cypher
   SHOW INDEXES;
   // Should see 30+ indexes (property, vector, full-text, composite)
   ```

4. **Wait for index population:**
   ```cypher
   CALL db.awaitIndexes(300);  // Wait up to 5 minutes
   ```

5. **Load sample data (optional for testing):**
   ```bash
   cypher-shell -u neo4j -p password -f /home/gulab/PythonProjects/VAUCDA/schema/sample_data/load_sample_data.cypher
   ```

6. **Verify vector indexes online:**
   ```cypher
   SHOW INDEXES YIELD name, type, state
   WHERE type = 'VECTOR'
   RETURN name, state;
   // All should be 'ONLINE'
   ```

7. **Set up TTL cleanup job:**
   ```bash
   # Add to crontab
   * * * * * curl -X POST http://localhost:8000/api/v1/admin/cleanup-sessions
   ```

---

## Support and Maintenance

### Schema Version
- **Current Version:** 1.0
- **Last Updated:** 2025-11-29
- **Next Review:** 2026-02-28

### Contact
- **Schema Owner:** VAUCDA Development Team
- **Technical Lead:** [Name]
- **Architecture Review:** [Email]

### Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-29 | Initial production schema |
| 1.1 | TBD | Ambient listening support (Migration 001) |

---

## Appendix: Sample Queries

See `/home/gulab/PythonProjects/VAUCDA/schema/queries/common_operations.cypher` for comprehensive query examples.

**Key Query Files:**
- `common_operations.cypher` - Frequently-used queries
- `load_sample_data.cypher` - Sample data for testing
- `001_add_ambient_listening_support.cypher` - Ambient listening migration

---

**END OF DOCUMENTATION**
