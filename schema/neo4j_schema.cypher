// ============================================================================
// VAUCDA Neo4j Graph Database Schema
// VA Urology Clinical Documentation Assistant
// ============================================================================
// Version: 1.0
// Date: 2025-11-29
// Purpose: Medical knowledge graph with vector search for RAG-powered
//          clinical decision support
// ============================================================================

// ============================================================================
// SECTION 1: CONSTRAINTS (Uniqueness and Existence)
// ============================================================================
// Constraints must be created before indexes and data insertion
// These enforce data integrity and enable performant lookups

// --- Guideline Constraints ---
CREATE CONSTRAINT guideline_id_unique IF NOT EXISTS
FOR (g:Guideline) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT guideline_id_exists IF NOT EXISTS
FOR (g:Guideline) REQUIRE g.id IS NOT NULL;

// --- Calculator Constraints ---
CREATE CONSTRAINT calculator_name_unique IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT calculator_name_exists IF NOT EXISTS
FOR (c:Calculator) REQUIRE c.name IS NOT NULL;

// --- Literature Constraints ---
CREATE CONSTRAINT literature_doi_unique IF NOT EXISTS
FOR (l:Literature) REQUIRE l.doi IS UNIQUE;

// --- ClinicalConcept Constraints ---
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (cc:ClinicalConcept) REQUIRE cc.id IS UNIQUE;

CREATE CONSTRAINT concept_id_exists IF NOT EXISTS
FOR (cc:ClinicalConcept) REQUIRE cc.id IS NOT NULL;

// --- DocumentChunk Constraints ---
CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (dc:DocumentChunk) REQUIRE dc.id IS UNIQUE;

CREATE CONSTRAINT chunk_id_exists IF NOT EXISTS
FOR (dc:DocumentChunk) REQUIRE dc.id IS NOT NULL;

// --- Session Constraints (Ephemeral - 30 min TTL) ---
CREATE CONSTRAINT session_id_unique IF NOT EXISTS
FOR (s:Session) REQUIRE s.session_id IS UNIQUE;

CREATE CONSTRAINT session_id_exists IF NOT EXISTS
FOR (s:Session) REQUIRE s.session_id IS NOT NULL;

// --- AuditLog Constraints ---
CREATE CONSTRAINT audit_log_id_unique IF NOT EXISTS
FOR (a:AuditLog) REQUIRE a.id IS UNIQUE;


// ============================================================================
// SECTION 2: PROPERTY INDEXES (Performance Optimization)
// ============================================================================
// These indexes optimize query performance for common lookup patterns

// --- Guideline Indexes ---
CREATE INDEX guideline_category_idx IF NOT EXISTS
FOR (g:Guideline) ON (g.category);

CREATE INDEX guideline_organization_idx IF NOT EXISTS
FOR (g:Guideline) ON (g.organization);

CREATE INDEX guideline_publication_date_idx IF NOT EXISTS
FOR (g:Guideline) ON (g.publication_date);

// --- Calculator Indexes ---
CREATE INDEX calculator_category_idx IF NOT EXISTS
FOR (c:Calculator) ON (c.category);

// --- Literature Indexes ---
CREATE INDEX literature_journal_idx IF NOT EXISTS
FOR (l:Literature) ON (l.journal);

CREATE INDEX literature_pubmed_id_idx IF NOT EXISTS
FOR (l:Literature) ON (l.pubmed_id);

// --- ClinicalConcept Indexes ---
CREATE INDEX concept_icd10_idx IF NOT EXISTS
FOR (cc:ClinicalConcept) ON (cc.icd10_code);

CREATE INDEX concept_snomed_idx IF NOT EXISTS
FOR (cc:ClinicalConcept) ON (cc.snomed_code);

CREATE INDEX concept_name_idx IF NOT EXISTS
FOR (cc:ClinicalConcept) ON (cc.name);

// --- DocumentChunk Indexes ---
CREATE INDEX chunk_source_id_idx IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.source_id);

CREATE INDEX chunk_index_idx IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.chunk_index);

// --- Session Indexes (TTL Cleanup) ---
CREATE INDEX session_expires_at_idx IF NOT EXISTS
FOR (s:Session) ON (s.expires_at);

CREATE INDEX session_created_at_idx IF NOT EXISTS
FOR (s:Session) ON (s.created_at);

// --- AuditLog Indexes ---
CREATE INDEX audit_timestamp_idx IF NOT EXISTS
FOR (a:AuditLog) ON (a.timestamp);

CREATE INDEX audit_user_id_idx IF NOT EXISTS
FOR (a:AuditLog) ON (a.user_id);

CREATE INDEX audit_session_hash_idx IF NOT EXISTS
FOR (a:AuditLog) ON (a.session_hash);


// ============================================================================
// SECTION 3: VECTOR INDEXES (Semantic Search for RAG)
// ============================================================================
// Vector indexes enable similarity search using 768-dimensional embeddings
// from sentence-transformers/all-MiniLM-L6-v2

// --- Primary Vector Index: DocumentChunk Embeddings ---
// This is the main RAG retrieval index for chunked content
CREATE VECTOR INDEX document_chunk_embeddings IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};

// --- Secondary Vector Index: Guideline Embeddings ---
// Enables direct guideline similarity search without chunking
CREATE VECTOR INDEX guideline_embeddings IF NOT EXISTS
FOR (g:Guideline) ON (g.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};

// --- Tertiary Vector Index: Literature Embeddings ---
// Abstract-level similarity search for literature
CREATE VECTOR INDEX literature_embeddings IF NOT EXISTS
FOR (l:Literature) ON (l.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};

// --- Quaternary Vector Index: ClinicalConcept Embeddings ---
// Concept-level similarity search for related conditions/treatments
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (cc:ClinicalConcept) ON (cc.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
};


// ============================================================================
// SECTION 4: FULL-TEXT SEARCH INDEXES
// ============================================================================
// Full-text indexes enable keyword search across text properties

// --- Guideline Content Full-Text Search ---
CREATE FULLTEXT INDEX guideline_content_fulltext IF NOT EXISTS
FOR (g:Guideline) ON EACH [g.title, g.content];

// --- Literature Content Full-Text Search ---
CREATE FULLTEXT INDEX literature_content_fulltext IF NOT EXISTS
FOR (l:Literature) ON EACH [l.title, l.abstract, l.full_text];

// --- ClinicalConcept Full-Text Search ---
CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS
FOR (cc:ClinicalConcept) ON EACH [cc.name, cc.description];

// --- DocumentChunk Content Full-Text Search ---
CREATE FULLTEXT INDEX chunk_content_fulltext IF NOT EXISTS
FOR (dc:DocumentChunk) ON EACH [dc.content];

// --- Calculator Full-Text Search ---
CREATE FULLTEXT INDEX calculator_fulltext IF NOT EXISTS
FOR (c:Calculator) ON EACH [c.name, c.description];


// ============================================================================
// SECTION 5: COMPOSITE INDEXES
// ============================================================================
// Composite indexes optimize queries with multiple filter criteria

// --- DocumentChunk: source_id + chunk_index (common access pattern) ---
CREATE INDEX chunk_source_and_index IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.source_id, dc.chunk_index);

// --- Guideline: category + publication_date (filtering + sorting) ---
CREATE INDEX guideline_category_date IF NOT EXISTS
FOR (g:Guideline) ON (g.category, g.publication_date);


// ============================================================================
// SECTION 6: NODE SCHEMA DOCUMENTATION
// ============================================================================
// This section documents the expected properties for each node type
// Neo4j is schema-flexible, but this serves as the canonical reference

/*
╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: Guideline                                                      ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Clinical practice guidelines from AUA, NCCN, EAU                ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE, NOT NULL]          ║
║   title           : STRING                    [REQUIRED]                  ║
║   organization    : STRING (AUA|NCCN|EAU)     [REQUIRED, INDEXED]         ║
║   publication_date: DATE                      [REQUIRED, INDEXED]         ║
║   category        : STRING                    [REQUIRED, INDEXED]         ║
║                     (prostate|kidney|bladder|voiding|female|fertility     ║
║                      |stones|reconstructive|hypogonadism|surgical)        ║
║   version         : STRING                    [OPTIONAL]                  ║
║   content         : STRING (full text)        [REQUIRED]                  ║
║   embedding       : LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]  ║
║   url             : STRING                    [OPTIONAL]                  ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║   updated_at      : DATETIME                  [DEFAULT: now()]            ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "550e8400-e29b-41d4-a716-446655440000",                          ║
║     title: "NCCN Prostate Cancer Guidelines 2024",                      ║
║     organization: "NCCN",                                                ║
║     publication_date: date("2024-01-15"),                                ║
║     category: "prostate",                                                ║
║     version: "1.2024",                                                   ║
║     content: "Prostate cancer screening recommendations...",             ║
║     embedding: [0.023, -0.145, 0.089, ...]                              ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: Calculator                                                     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Clinical calculators and assessment tools (44 total)            ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   name            : STRING                    [UNIQUE, NOT NULL]          ║
║   category        : STRING                    [REQUIRED, INDEXED]         ║
║   description     : STRING                    [REQUIRED]                  ║
║   algorithm       : STRING (JSON or formula)  [REQUIRED]                  ║
║   validation_refs : LIST<STRING>              [OPTIONAL]                  ║
║   input_schema    : STRING (JSON Schema)      [REQUIRED]                  ║
║   output_schema   : STRING (JSON Schema)      [REQUIRED]                  ║
║   version         : STRING                    [DEFAULT: "1.0"]            ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║   updated_at      : DATETIME                  [DEFAULT: now()]            ║
║                                                                           ║
║ CATEGORIES:                                                               ║
║   - prostate_cancer (7 calculators)                                      ║
║   - kidney_cancer (4 calculators)                                        ║
║   - bladder_cancer (3 calculators)                                       ║
║   - male_voiding (5 calculators)                                         ║
║   - female_urology (5 calculators)                                       ║
║   - reconstructive (4 calculators)                                       ║
║   - fertility (5 calculators)                                            ║
║   - hypogonadism (3 calculators)                                         ║
║   - stones (4 calculators)                                               ║
║   - surgical_planning (4 calculators)                                    ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     name: "CAPRA Score",                                                 ║
║     category: "prostate_cancer",                                         ║
║     description: "Cancer of Prostate Risk Assessment",                   ║
║     algorithm: "{...JSON representation...}",                            ║
║     validation_refs: ["Cooperberg MR, Cancer 2006"],                     ║
║     input_schema: "{...JSON Schema...}",                                 ║
║     output_schema: "{...JSON Schema...}"                                 ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: Literature                                                     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Medical journal articles and research papers                    ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   title           : STRING                    [REQUIRED]                  ║
║   authors         : LIST<STRING>              [REQUIRED]                  ║
║   journal         : STRING                    [REQUIRED, INDEXED]         ║
║   pubmed_id       : STRING                    [OPTIONAL, INDEXED]         ║
║   doi             : STRING                    [UNIQUE]                    ║
║   abstract        : STRING                    [OPTIONAL]                  ║
║   full_text       : STRING                    [OPTIONAL]                  ║
║   embedding       : LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]  ║
║   publication_year: INTEGER                   [OPTIONAL]                  ║
║   keywords        : LIST<STRING>              [OPTIONAL]                  ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     title: "PSA Velocity for Early Detection...",                        ║
║     authors: ["D'Amico AV", "Chen MH", "Roehl KA"],                      ║
║     journal: "JAMA",                                                     ║
║     pubmed_id: "15546998",                                               ║
║     doi: "10.1001/jama.292.18.2237",                                     ║
║     abstract: "CONTEXT: PSA velocity may improve...",                    ║
║     embedding: [0.012, -0.234, 0.156, ...]                              ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: ClinicalConcept                                                ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Diseases, treatments, procedures with medical coding            ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE, NOT NULL]          ║
║   name            : STRING                    [REQUIRED, INDEXED]         ║
║   icd10_code      : STRING                    [OPTIONAL, INDEXED]         ║
║   snomed_code     : STRING                    [OPTIONAL, INDEXED]         ║
║   description     : STRING                    [REQUIRED]                  ║
║   category        : STRING                    [OPTIONAL]                  ║
║   embedding       : LIST<FLOAT> (768-dim)     [OPTIONAL, VECTOR INDEXED]  ║
║   synonyms        : LIST<STRING>              [OPTIONAL]                  ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "cc-001-prostate-cancer",                                        ║
║     name: "Prostate Adenocarcinoma",                                     ║
║     icd10_code: "C61",                                                   ║
║     snomed_code: "399068003",                                            ║
║     description: "Malignant neoplasm of prostate gland",                 ║
║     category: "prostate",                                                ║
║     synonyms: ["Prostate Cancer", "Prostatic Carcinoma"]                 ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: DocumentChunk                                                  ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: RAG-optimized chunks from source documents                      ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE, NOT NULL]          ║
║   source_id       : STRING (UUID)             [REQUIRED, INDEXED]         ║
║   source_type     : STRING (Guideline|Lit)    [REQUIRED]                  ║
║   chunk_index     : INTEGER                   [REQUIRED, INDEXED]         ║
║   content         : STRING (512-1024 tokens)  [REQUIRED]                  ║
║   embedding       : LIST<FLOAT> (768-dim)     [REQUIRED, VECTOR INDEXED]  ║
║   metadata        : MAP                       [OPTIONAL]                  ║
║                     {section, page, title, category}                      ║
║   token_count     : INTEGER                   [OPTIONAL]                  ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║                                                                           ║
║ CHUNKING STRATEGY:                                                        ║
║   - Chunk size: 512-1024 tokens                                          ║
║   - Overlap: 128 tokens                                                  ║
║   - Preserve sentence boundaries                                         ║
║   - Maintain semantic coherence                                          ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "chunk-001-nccn-prostate",                                       ║
║     source_id: "550e8400-e29b-41d4-a716-446655440000",                  ║
║     source_type: "Guideline",                                            ║
║     chunk_index: 3,                                                      ║
║     content: "Risk stratification uses PSA, Gleason score...",           ║
║     embedding: [0.045, -0.123, 0.267, ...],                             ║
║     metadata: {section: "Risk Assessment", category: "prostate"}         ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: Session (EPHEMERAL - 30 MINUTE TTL)                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Temporary storage for user sessions containing PHI              ║
║ CRITICAL: These nodes MUST be auto-deleted after 30 minutes for HIPAA    ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   session_id      : STRING (UUID)             [UNIQUE, NOT NULL]          ║
║   user_id         : STRING                    [REQUIRED]                  ║
║   created_at      : DATETIME                  [REQUIRED, INDEXED]         ║
║   expires_at      : DATETIME                  [REQUIRED, INDEXED]         ║
║                     (created_at + 30 minutes)                             ║
║   note_context    : STRING                    [OPTIONAL, PHI CONTENT]     ║
║   active          : BOOLEAN                   [DEFAULT: true]             ║
║                                                                           ║
║ TTL CLEANUP QUERY (run every 1 minute via scheduler):                    ║
║   MATCH (s:Session)                                                      ║
║   WHERE s.expires_at < datetime()                                        ║
║   DETACH DELETE s                                                        ║
║                                                                           ║
║ SECURITY NOTES:                                                           ║
║   - Only metadata logged to AuditLog                                     ║
║   - PHI content never persisted outside Session nodes                    ║
║   - Automatic cleanup prevents retention beyond 30 min                   ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     session_id: "sess-20251129-abc123",                                  ║
║     user_id: "user-12345",                                               ║
║     created_at: datetime("2025-11-29T14:30:00Z"),                        ║
║     expires_at: datetime("2025-11-29T15:00:00Z"),                        ║
║     note_context: "...clinical data...",                                 ║
║     active: true                                                         ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: AuditLog (METADATA ONLY - NO PHI)                             ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: HIPAA-compliant audit trail without PHI                         ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE]                    ║
║   session_hash    : STRING (SHA256)           [REQUIRED, INDEXED]         ║
║                     (hashed session_id, not original)                     ║
║   timestamp       : DATETIME                  [REQUIRED, INDEXED]         ║
║   action_type     : STRING                    [REQUIRED]                  ║
║                     (note_generation|calculator_use|evidence_search)      ║
║   user_id         : STRING                    [REQUIRED, INDEXED]         ║
║   model_used      : STRING                    [OPTIONAL]                  ║
║   tokens_used     : INTEGER                   [OPTIONAL]                  ║
║   duration_ms     : INTEGER                   [OPTIONAL]                  ║
║   success         : BOOLEAN                   [DEFAULT: true]             ║
║   error_code      : STRING                    [OPTIONAL]                  ║
║                                                                           ║
║ EXPLICITLY EXCLUDED (NEVER STORED):                                      ║
║   - clinical_input (PHI)                                                 ║
║   - generated_note (PHI)                                                 ║
║   - patient identifiers (PHI)                                            ║
║   - Any PHI whatsoever                                                   ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "audit-001",                                                     ║
║     session_hash: "a3f5d1c2...",                                         ║
║     timestamp: datetime("2025-11-29T14:35:22Z"),                         ║
║     action_type: "note_generation",                                      ║
║     user_id: "user-12345",                                               ║
║     model_used: "llama3.1:8b",                                           ║
║     tokens_used: 2048,                                                   ║
║     duration_ms: 2340,                                                   ║
║     success: true                                                        ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝
*/


// ============================================================================
// SECTION 7: RELATIONSHIP SCHEMA DOCUMENTATION
// ============================================================================

/*
╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:REFERENCES]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Guideline)-[:REFERENCES]->(Literature)                         ║
║ PURPOSE: Link guidelines to supporting literature                        ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   citation_type   : STRING (primary|supporting|evidence)                 ║
║   strength        : STRING (high|moderate|low)                            ║
║   created_at      : DATETIME                                             ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:COVERS]                                                   ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Guideline)-[:COVERS]->(ClinicalConcept)                        ║
║ PURPOSE: Map guidelines to clinical concepts they address                ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   detail_level    : STRING (comprehensive|brief|mention)                 ║
║   section         : STRING (section name within guideline)                ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:IMPLEMENTS]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Calculator)-[:IMPLEMENTS]->(Guideline)                         ║
║ PURPOSE: Show calculators implementing guideline recommendations         ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   version         : STRING (guideline version)                            ║
║   validated       : BOOLEAN                                              ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:APPLIES_TO]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Calculator)-[:APPLIES_TO]->(ClinicalConcept)                   ║
║ PURPOSE: Define which conditions/procedures calculators apply to         ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   applicability   : STRING (primary|secondary|related)                   ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:BELONGS_TO]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (DocumentChunk)-[:BELONGS_TO]->(Guideline|Literature)           ║
║ PURPOSE: Link chunks back to their source documents                      ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   chunk_index     : INTEGER (position in sequence)                       ║
║   section         : STRING (section name)                                ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:NEXT_CHUNK]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (DocumentChunk)-[:NEXT_CHUNK]->(DocumentChunk)                  ║
║ PURPOSE: Maintain sequential ordering of chunks for context expansion    ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   overlap_tokens  : INTEGER (number of overlapping tokens)               ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:RELATED_TO]                                               ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (ClinicalConcept)-[:RELATED_TO]->(ClinicalConcept)              ║
║ PURPOSE: Define relationships between clinical concepts                  ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   relationship    : STRING (treats|causes|associated_with|complication)  ║
║   strength        : FLOAT (0.0-1.0, semantic similarity)                 ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:USED_CALCULATOR]                                          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Session)-[:USED_CALCULATOR]->(Calculator)                      ║
║ PURPOSE: Track calculator usage within sessions (ephemeral)              ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   timestamp       : DATETIME                                             ║
║   result_category : STRING (e.g., "high_risk", "low_risk")               ║
║                     (NO PHI - just risk category)                         ║
║                                                                           ║
║ NOTE: This relationship is deleted when Session expires (30 min TTL)     ║
╚═══════════════════════════════════════════════════════════════════════════╝
*/


// ============================================================================
// SECTION 8: INITIALIZATION VERIFICATION
// ============================================================================
// After running this schema, verify with these queries:

// Check all constraints exist:
// SHOW CONSTRAINTS;

// Check all indexes exist:
// SHOW INDEXES;

// Verify vector indexes are online:
// SHOW INDEXES YIELD name, type, state WHERE type = 'VECTOR';

// Check index population status:
// CALL db.awaitIndexes(300);


// ============================================================================
// SCHEMA CREATION COMPLETE
// ============================================================================
// This schema provides:
//   - 6 primary node types (Guideline, Calculator, Literature, ClinicalConcept,
//     DocumentChunk, Session, AuditLog)
//   - 21 property indexes for optimal query performance
//   - 4 vector indexes for semantic search (768-dim embeddings)
//   - 5 full-text indexes for keyword search
//   - 8 relationship types for knowledge graph traversal
//   - HIPAA-compliant ephemeral session handling (30-min TTL)
//   - Comprehensive audit logging (metadata only, no PHI)
//
// Next Steps:
//   1. Run sample data insertion (sample_data/load_sample_data.cypher)
//   2. Configure TTL cleanup job for Session nodes
//   3. Ingest clinical guidelines and literature
//   4. Generate embeddings for vector search
// ============================================================================
