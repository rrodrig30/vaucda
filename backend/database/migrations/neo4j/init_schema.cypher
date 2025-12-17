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

// Document embeddings index (768 dimensions, cosine similarity)
// This is the PRIMARY index for RAG retrieval
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200,
        `vector.quantization.enabled`: false
    }
};

// ClinicalConcept embeddings index (768 dimensions, cosine similarity)
// For concept-based semantic search
CREATE VECTOR INDEX concept_embeddings IF NOT EXISTS
FOR (c:ClinicalConcept) ON (c.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
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
