// VAUCDA Neo4j Database Schema Initialization
// This script creates all constraints, indexes, and initial configuration
// Run once during database setup

// ============================================================================
// CONSTRAINTS - Uniqueness and Existence
// ============================================================================

// Document node constraints
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

// ClinicalConcept node constraints
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (c:ClinicalConcept) REQUIRE c.id IS UNIQUE;

// Calculator node constraints
CREATE CONSTRAINT calculator_id_unique IF NOT EXISTS
FOR (calc:Calculator) REQUIRE calc.id IS UNIQUE;

// Template node constraints
CREATE CONSTRAINT template_id_unique IF NOT EXISTS
FOR (t:Template) REQUIRE t.id IS UNIQUE;

// User node constraints
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT user_username_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.username IS UNIQUE;

// Session node constraints
CREATE CONSTRAINT session_id_unique IF NOT EXISTS
FOR (s:Session) REQUIRE s.id IS UNIQUE;

// AuditLog node constraints
CREATE CONSTRAINT auditlog_id_unique IF NOT EXISTS
FOR (a:AuditLog) REQUIRE a.id IS UNIQUE;

// ============================================================================
// VECTOR INDEXES - For RAG and Semantic Search
// ============================================================================

// Chunk embeddings index (384 dimensions for all-MiniLM-L6-v2, cosine similarity)
// This is the PRIMARY index for RAG retrieval
// NOTE: Embeddings are stored on Chunk nodes, not Document nodes
CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
FOR (c:Chunk) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200,
        `vector.quantization.enabled`: false
    }
};

// ClinicalConcept embeddings index (384 dimensions for all-MiniLM-L6-v2, cosine similarity)
// For concept-based semantic search
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200,
        `vector.quantization.enabled`: false
    }
};

// ============================================================================
// FULL-TEXT SEARCH INDEXES
// ============================================================================

// Document full-text search (title + content + summary)
CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
FOR (d:Document) ON EACH [d.title, d.content, d.summary];

// ClinicalConcept full-text search (name + description)
CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS
FOR (c:ClinicalConcept) ON EACH [c.name, c.description];

// Calculator full-text search
CREATE FULLTEXT INDEX calculator_fulltext IF NOT EXISTS
FOR (calc:Calculator) ON EACH [calc.name, calc.description];

// ============================================================================
// PROPERTY INDEXES - For Filtering and Performance
// ============================================================================

// Document property indexes
CREATE INDEX document_category IF NOT EXISTS
FOR (d:Document) ON (d.category);

CREATE INDEX document_source IF NOT EXISTS
FOR (d:Document) ON (d.source);

CREATE INDEX document_type IF NOT EXISTS
FOR (d:Document) ON (d.document_type);

CREATE INDEX document_publication_date IF NOT EXISTS
FOR (d:Document) ON (d.publication_date);

// ClinicalConcept property indexes
CREATE INDEX concept_category IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.category);

CREATE INDEX concept_icd10 IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.icd10_codes);

// Calculator property indexes
CREATE INDEX calculator_category IF NOT EXISTS
FOR (calc:Calculator) ON (calc.category);

// Session property indexes (for TTL cleanup)
CREATE INDEX session_expires_at IF NOT EXISTS
FOR (s:Session) ON (s.expires_at);

CREATE INDEX session_status IF NOT EXISTS
FOR (s:Session) ON (s.status);

CREATE INDEX session_user_id IF NOT EXISTS
FOR (s:Session) ON (s.user_id);

CREATE INDEX session_created_at IF NOT EXISTS
FOR (s:Session) ON (s.created_at);

// AuditLog property indexes
CREATE INDEX auditlog_session IF NOT EXISTS
FOR (a:AuditLog) ON (a.session_id);

CREATE INDEX auditlog_user IF NOT EXISTS
FOR (a:AuditLog) ON (a.user_id);

CREATE INDEX auditlog_created IF NOT EXISTS
FOR (a:AuditLog) ON (a.created_at);

CREATE INDEX auditlog_expires IF NOT EXISTS
FOR (a:AuditLog) ON (a.expires_at);

CREATE INDEX auditlog_action IF NOT EXISTS
FOR (a:AuditLog) ON (a.action);

// User property indexes
CREATE INDEX user_username IF NOT EXISTS
FOR (u:User) ON (u.username);

CREATE INDEX user_role IF NOT EXISTS
FOR (u:User) ON (u.role);

// Template property indexes
CREATE INDEX template_type IF NOT EXISTS
FOR (t:Template) ON (t.type);

CREATE INDEX template_active IF NOT EXISTS
FOR (t:Template) ON (t.active);

// ============================================================================
// GRAPHRAG COMPONENTS - Communities and Hierarchical Summaries
// ============================================================================

// Community node constraints
CREATE CONSTRAINT community_id_unique IF NOT EXISTS
FOR (c:Community) REQUIRE c.id IS UNIQUE;

// HierarchicalSummary node constraints
CREATE CONSTRAINT summary_id_unique IF NOT EXISTS
FOR (s:HierarchicalSummary) REQUIRE s.id IS UNIQUE;

// OntologyConcept node constraints (UMLS/SNOMED)
CREATE CONSTRAINT ontology_umls_unique IF NOT EXISTS
FOR (o:OntologyConcept) REQUIRE o.umls_cui IS UNIQUE;

// Community embeddings index (384 dimensions for community-level retrieval)
CREATE VECTOR INDEX community_embeddings IF NOT EXISTS
FOR (c:Community) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 384,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200,
        `vector.quantization.enabled`: false
    }
};

// Community property indexes
CREATE INDEX community_tier IF NOT EXISTS
FOR (c:Community) ON (c.tier);

CREATE INDEX community_size IF NOT EXISTS
FOR (c:Community) ON (c.size);

// HierarchicalSummary property indexes
CREATE INDEX summary_entity_type IF NOT EXISTS
FOR (s:HierarchicalSummary) ON (s.entity_type);

CREATE INDEX summary_level IF NOT EXISTS
FOR (s:HierarchicalSummary) ON (s.level);

CREATE INDEX summary_entity_id IF NOT EXISTS
FOR (s:HierarchicalSummary) ON (s.entity_id);

// OntologyConcept property indexes
CREATE INDEX ontology_snomed IF NOT EXISTS
FOR (o:OntologyConcept) ON (o.snomed_id);

CREATE INDEX ontology_icd10 IF NOT EXISTS
FOR (o:OntologyConcept) ON (o.icd10_code);

CREATE INDEX ontology_preferred_term IF NOT EXISTS
FOR (o:OntologyConcept) ON (o.preferred_term);

// Full-text index for ontology concept search
CREATE FULLTEXT INDEX ontology_fulltext IF NOT EXISTS
FOR (o:OntologyConcept) ON EACH [o.preferred_term, o.synonyms_text];

// ============================================================================
// PERIODIC PROCEDURES - Background Jobs
// ============================================================================

// Session TTL Cleanup Job
// Runs every 5 minutes to delete expired sessions
CALL apoc.periodic.repeat(
    'session-ttl-cleanup',
    'MATCH (s:Session)
     WHERE s.expires_at < datetime() AND s.status = "active"
     SET s.status = "expired"
     WITH s
     DETACH DELETE s
     RETURN count(s) AS deleted_count',
    300
) YIELD name, delay, rate
RETURN name, delay, rate;

// AuditLog Cleanup Job
// Runs daily to delete audit logs older than 90 days
CALL apoc.periodic.repeat(
    'auditlog-cleanup',
    'MATCH (a:AuditLog)
     WHERE a.expires_at < datetime()
     DETACH DELETE a
     RETURN count(a) AS deleted_count',
    86400
) YIELD name, delay, rate
RETURN name, delay, rate;

// ============================================================================
// VERIFICATION QUERIES
// ============================================================================

// Verify all constraints are created
SHOW CONSTRAINTS YIELD name, type
RETURN name, type
ORDER BY name;

// Verify all indexes are created and online
SHOW INDEXES YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent
ORDER BY name;

// Verify periodic procedures are scheduled
CALL apoc.periodic.list()
YIELD name, delay, rate, done, cancelled
RETURN name, delay, rate, done, cancelled;

// ============================================================================
// INITIAL DATA SEEDING (Optional)
// ============================================================================

// Create default templates (example)
// Uncomment to seed initial templates

/*
CREATE (:Template {
    id: apoc.create.uuid(),
    template_id: 'urology_clinic_note',
    name: 'Urology Clinic Note',
    type: 'clinic_note',
    content: 'Chief Complaint:\n\nHPI:\n\nPMH:\n\nMedications:\n\nExam:\n\nAssessment:\n\nPlan:',
    sections: ['Chief Complaint', 'HPI', 'PMH', 'Medications', 'Exam', 'Assessment', 'Plan'],
    active: true,
    version: '1.0',
    created_at: datetime(),
    updated_at: datetime()
});
*/

// ============================================================================
// SCHEMA INITIALIZATION COMPLETE
// ============================================================================

RETURN "Neo4j schema initialization completed successfully" AS status;
