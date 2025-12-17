"""
Neo4j Query Library for VAUCDA

Comprehensive collection of optimized Cypher queries for:
- Vector similarity search
- Graph traversal
- Session management
- Audit logging
- Data ingestion
- Analytics

All queries are production-ready and HIPAA-compliant (no PHI in queries).
"""

from typing import Dict, Any

# =============================================================================
# VECTOR SEARCH QUERIES
# =============================================================================

VECTOR_SEARCH_DOCUMENTS = """
// Vector similarity search on Document nodes
// Returns top-K most similar documents to query embedding

CALL db.index.vector.queryNodes('document_embeddings', $k, $query_embedding)
YIELD node, score

WHERE ($category IS NULL OR node.category = $category)
  AND ($min_year IS NULL OR node.publication_date.year >= $min_year)
  AND ($source IS NULL OR node.source = $source)

RETURN node.id AS doc_id,
       node.title AS title,
       node.content AS content,
       node.summary AS summary,
       node.source AS source,
       node.category AS category,
       node.document_type AS document_type,
       node.version AS version,
       node.publication_date AS publication_date,
       node.keywords AS keywords,
       score AS similarity_score
ORDER BY score DESC
LIMIT $k
"""

VECTOR_SEARCH_CONCEPTS = """
// Vector similarity search on ClinicalConcept nodes
// Useful for concept-based retrieval and classification

CALL db.index.vector.queryNodes('concept_embeddings', $k, $query_embedding)
YIELD node, score

WHERE ($category IS NULL OR node.category = $category)

RETURN node.id AS concept_id,
       node.name AS concept_name,
       node.description AS description,
       node.category AS category,
       node.icd10_codes AS icd10_codes,
       node.snomed_codes AS snomed_codes,
       node.severity AS severity,
       score AS similarity_score
ORDER BY score DESC
LIMIT $k
"""

HYBRID_SEARCH_WITH_CONTEXT = """
// Hybrid retrieval: Vector search + Graph traversal
// Enriches vector search results with graph context

CALL db.index.vector.queryNodes('document_embeddings', $k, $query_embedding)
YIELD node AS doc, score

WHERE ($category IS NULL OR doc.category = $category)

// Graph traversal for related clinical concepts
MATCH (doc)-[:REFERENCES]->(concept:ClinicalConcept)

// Find applicable calculators
OPTIONAL MATCH (concept)<-[:APPLIES_TO]-(calc:Calculator)

// Find cited documents (evidence chain)
OPTIONAL MATCH (doc)-[:CITES]->(cited_doc:Document)

RETURN doc.id AS document_id,
       doc.title AS document_title,
       doc.content AS content,
       doc.summary AS summary,
       doc.source AS source,
       doc.version AS version,
       score AS vector_score,
       collect(DISTINCT {
           name: concept.name,
           icd10: concept.icd10_codes,
           severity: concept.severity
       }) AS related_concepts,
       collect(DISTINCT calc.name) AS applicable_calculators,
       collect(DISTINCT cited_doc.title) AS cited_documents
ORDER BY score DESC
LIMIT $k
"""

MULTI_HOP_RETRIEVAL = """
// Multi-hop graph retrieval
// Starting from vector search, traverse 2-3 hops for deep context

CALL db.index.vector.queryNodes('document_embeddings', 5, $query_embedding)
YIELD node AS doc, score

WHERE doc.category = $category

// 1st hop: Clinical concepts referenced
MATCH (doc)-[:REFERENCES]->(concept1:ClinicalConcept)

// 2nd hop: Related clinical concepts
MATCH (concept1)-[:RELATED_TO]-(concept2:ClinicalConcept)

// 3rd hop: Documents referencing related concepts
MATCH (concept2)<-[:REFERENCES]-(related_doc:Document)

WHERE related_doc.id <> doc.id  // Exclude original document

RETURN doc.id AS primary_doc_id,
       doc.title AS primary_title,
       score AS primary_score,
       collect(DISTINCT concept1.name)[..5] AS direct_concepts,
       collect(DISTINCT concept2.name)[..10] AS related_concepts,
       collect(DISTINCT {
           id: related_doc.id,
           title: related_doc.title,
           source: related_doc.source
       })[..5] AS related_documents
ORDER BY score DESC
LIMIT 3
"""

# =============================================================================
# FULL-TEXT SEARCH QUERIES
# =============================================================================

FULLTEXT_SEARCH_DOCUMENTS = """
// Full-text search on Document nodes
// Complements vector search for exact keyword matching

CALL db.index.fulltext.queryNodes('document_fulltext', $search_query)
YIELD node, score

WHERE ($category IS NULL OR node.category = $category)

RETURN node.id AS doc_id,
       node.title AS title,
       node.summary AS summary,
       node.source AS source,
       node.category AS category,
       score AS text_score
ORDER BY score DESC
LIMIT $limit
"""

FULLTEXT_SEARCH_CONCEPTS = """
// Full-text search on ClinicalConcept nodes

CALL db.index.fulltext.queryNodes('concept_fulltext', $search_query)
YIELD node, score

RETURN node.id AS concept_id,
       node.name AS concept_name,
       node.description AS description,
       node.category AS category,
       node.icd10_codes AS icd10_codes,
       score AS text_score
ORDER BY score DESC
LIMIT $limit
"""

# =============================================================================
# SESSION MANAGEMENT QUERIES
# =============================================================================

CREATE_SESSION = """
// Create new session with 30-minute TTL
// HIPAA-compliant: Stores metadata only, no PHI

MERGE (u:User {user_id: $user_id})

CREATE (s:Session {
    id: apoc.create.uuid(),
    session_id: $session_id,
    user_id: $user_id,
    note_type: $note_type,
    llm_provider: $llm_provider,
    model_used: $model_used,
    selected_modules: $selected_modules,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    last_accessed: datetime(),
    status: 'active'
})

CREATE (s)-[:BELONGS_TO]->(u)

RETURN s.id AS session_db_id,
       s.session_id AS session_id,
       s.created_at AS created_at,
       s.expires_at AS expires_at
"""

GET_SESSION = """
// Retrieve active session by ID

MATCH (s:Session {session_id: $session_id})
WHERE s.status = 'active' AND s.expires_at > datetime()

RETURN s.id AS session_db_id,
       s.session_id AS session_id,
       s.user_id AS user_id,
       s.note_type AS note_type,
       s.llm_provider AS llm_provider,
       s.model_used AS model_used,
       s.selected_modules AS selected_modules,
       s.created_at AS created_at,
       s.expires_at AS expires_at,
       s.last_accessed AS last_accessed
"""

UPDATE_SESSION_METRICS = """
// Update session with performance metrics

MATCH (s:Session {session_id: $session_id})
WHERE s.status = 'active'

SET s.generation_time_ms = $generation_time_ms,
    s.tokens_used = $tokens_used,
    s.last_accessed = datetime()

RETURN count(s) AS updated_count
"""

CLEANUP_EXPIRED_SESSIONS = """
// Delete sessions past their 30-minute TTL
// Runs automatically via APOC periodic procedure

MATCH (s:Session)
WHERE s.expires_at < datetime() AND s.status = 'active'

SET s.status = 'expired'

WITH s
DETACH DELETE s

RETURN count(s) AS deleted_count
"""

GET_ACTIVE_SESSION_COUNT = """
// Count currently active sessions

MATCH (s:Session {status: 'active'})
WHERE s.expires_at > datetime()

RETURN count(s) AS active_session_count
"""

GET_USER_SESSIONS = """
// Get all sessions for a user (for admin/debugging)

MATCH (u:User {user_id: $user_id})<-[:BELONGS_TO]-(s:Session)

RETURN s.session_id AS session_id,
       s.created_at AS created_at,
       s.expires_at AS expires_at,
       s.status AS status,
       s.note_type AS note_type,
       s.llm_provider AS llm_provider
ORDER BY s.created_at DESC
LIMIT 20
"""

# =============================================================================
# AUDIT LOGGING QUERIES
# =============================================================================

CREATE_AUDIT_LOG = """
// Create audit log entry (metadata only, NO PHI)

CREATE (a:AuditLog {
    id: apoc.create.uuid(),
    session_id: $session_id,
    user_id: $user_id,
    action: $action,
    module_used: $module_used,
    input_hash: $input_hash,
    output_hash: $output_hash,
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

RETURN a.id AS audit_log_id,
       a.created_at AS created_at
"""

GET_AUDIT_LOGS_BY_USER = """
// Retrieve audit logs for a specific user

MATCH (a:AuditLog {user_id: $user_id})

RETURN a.id AS audit_log_id,
       a.session_id AS session_id,
       a.action AS action,
       a.module_used AS module_used,
       a.duration_ms AS duration_ms,
       a.tokens_used AS tokens_used,
       a.llm_provider AS llm_provider,
       a.success AS success,
       a.created_at AS created_at
ORDER BY a.created_at DESC
LIMIT $limit
"""

GET_AUDIT_LOGS_BY_SESSION = """
// Retrieve all audit logs for a session

MATCH (a:AuditLog)-[:LOGGED]->(s:Session {session_id: $session_id})

RETURN a.id AS audit_log_id,
       a.action AS action,
       a.module_used AS module_used,
       a.duration_ms AS duration_ms,
       a.success AS success,
       a.error_code AS error_code,
       a.created_at AS created_at
ORDER BY a.created_at ASC
"""

CLEANUP_EXPIRED_AUDIT_LOGS = """
// Delete audit logs older than 90 days
// Runs automatically via APOC periodic procedure

MATCH (a:AuditLog)
WHERE a.expires_at < datetime()

DETACH DELETE a

RETURN count(a) AS deleted_count
"""

GET_USAGE_STATISTICS = """
// Aggregate usage statistics by action type
// For analytics dashboard

MATCH (a:AuditLog)
WHERE a.created_at >= datetime() - duration({days: $days})

WITH a.action AS action,
     count(a) AS usage_count,
     avg(a.duration_ms) AS avg_duration_ms,
     sum(a.tokens_used) AS total_tokens,
     sum(CASE WHEN a.success THEN 1 ELSE 0 END) AS success_count

RETURN action,
       usage_count,
       round(avg_duration_ms) AS avg_duration_ms,
       total_tokens,
       success_count,
       round(100.0 * success_count / usage_count, 2) AS success_rate
ORDER BY usage_count DESC
"""

# =============================================================================
# CALCULATOR & TEMPLATE QUERIES
# =============================================================================

GET_CALCULATOR_BY_ID = """
// Retrieve calculator metadata

MATCH (calc:Calculator {calculator_id: $calculator_id})

RETURN calc.id AS id,
       calc.calculator_id AS calculator_id,
       calc.name AS name,
       calc.category AS category,
       calc.description AS description,
       calc.inputs AS inputs,
       calc.outputs AS outputs,
       calc.interpretation_ranges AS interpretation_ranges,
       calc.references AS references,
       calc.algorithm_version AS algorithm_version
"""

GET_CALCULATORS_BY_CATEGORY = """
// List all calculators in a category

MATCH (calc:Calculator)
WHERE calc.category = $category

RETURN calc.calculator_id AS calculator_id,
       calc.name AS name,
       calc.description AS description,
       calc.usage_count AS usage_count
ORDER BY calc.name
"""

GET_ALL_CALCULATOR_CATEGORIES = """
// List all calculator categories with counts

MATCH (calc:Calculator)

WITH calc.category AS category, count(calc) AS calculator_count

RETURN category,
       calculator_count
ORDER BY category
"""

INCREMENT_CALCULATOR_USAGE = """
// Increment usage counter for a calculator

MATCH (calc:Calculator {calculator_id: $calculator_id})

SET calc.usage_count = coalesce(calc.usage_count, 0) + 1,
    calc.last_used = datetime()

RETURN calc.usage_count AS new_usage_count
"""

GET_TEMPLATE_BY_ID = """
// Retrieve template by ID

MATCH (t:Template {template_id: $template_id})
WHERE t.active = true

RETURN t.id AS id,
       t.template_id AS template_id,
       t.name AS name,
       t.type AS type,
       t.content AS content,
       t.sections AS sections,
       t.version AS version
"""

GET_TEMPLATES_BY_TYPE = """
// List all templates of a specific type

MATCH (t:Template)
WHERE t.type = $template_type AND t.active = true

RETURN t.template_id AS template_id,
       t.name AS name,
       t.version AS version
ORDER BY t.name
"""

# =============================================================================
# DATA INGESTION QUERIES
# =============================================================================

BATCH_INGEST_DOCUMENTS = """
// Batch ingest documents with embeddings

UNWIND $documents AS doc

MERGE (d:Document {id: doc.id})
SET d.title = doc.title,
    d.content = doc.content,
    d.summary = doc.summary,
    d.embedding = doc.embedding,
    d.category = doc.category,
    d.source = doc.source,
    d.document_type = doc.document_type,
    d.specialty = doc.specialty,
    d.version = doc.version,
    d.publication_date = date(doc.publication_date),
    d.keywords = doc.keywords,
    d.created_at = coalesce(d.created_at, datetime()),
    d.updated_at = datetime()

RETURN count(d) AS ingested_count
"""

CREATE_DOCUMENT_CONCEPT_RELATIONSHIPS = """
// Link documents to clinical concepts they reference

UNWIND $relationships AS rel

MATCH (d:Document {id: rel.document_id})
MATCH (c:ClinicalConcept {concept_id: rel.concept_id})

MERGE (d)-[r:REFERENCES]->(c)
SET r.relevance = rel.relevance,
    r.created_at = datetime()

RETURN count(r) AS relationships_created
"""

BATCH_INGEST_CLINICAL_CONCEPTS = """
// Batch ingest clinical concepts with embeddings

UNWIND $concepts AS concept

MERGE (c:ClinicalConcept {id: concept.id})
SET c.concept_id = concept.concept_id,
    c.name = concept.name,
    c.synonyms = concept.synonyms,
    c.description = concept.description,
    c.category = concept.category,
    c.embedding = concept.embedding,
    c.icd10_codes = concept.icd10_codes,
    c.snomed_codes = concept.snomed_codes,
    c.cpt_codes = concept.cpt_codes,
    c.severity = concept.severity,
    c.is_diagnosis = concept.is_diagnosis,
    c.is_procedure = concept.is_procedure,
    c.created_at = coalesce(c.created_at, datetime()),
    c.updated_at = datetime()

RETURN count(c) AS ingested_count
"""

BATCH_INGEST_CALCULATORS = """
// Batch ingest calculator metadata

UNWIND $calculators AS calc

MERGE (c:Calculator {id: calc.id})
SET c.calculator_id = calc.calculator_id,
    c.name = calc.name,
    c.category = calc.category,
    c.description = calc.description,
    c.formula = calc.formula,
    c.algorithm_version = calc.algorithm_version,
    c.inputs = calc.inputs,
    c.outputs = calc.outputs,
    c.interpretation_ranges = calc.interpretation_ranges,
    c.references = calc.references,
    c.validation_status = calc.validation_status,
    c.usage_count = coalesce(c.usage_count, 0),
    c.created_at = coalesce(c.created_at, datetime()),
    c.updated_at = datetime()

RETURN count(c) AS ingested_count
"""

# =============================================================================
# GRAPH ANALYTICS QUERIES
# =============================================================================

GET_MOST_REFERENCED_CONCEPTS = """
// Find most frequently referenced clinical concepts

MATCH (d:Document)-[r:REFERENCES]->(c:ClinicalConcept)

WITH c, count(r) AS reference_count

RETURN c.name AS concept_name,
       c.category AS category,
       c.icd10_codes AS icd10_codes,
       reference_count
ORDER BY reference_count DESC
LIMIT $limit
"""

GET_CITATION_NETWORK = """
// Analyze document citation network for a category

MATCH (d1:Document)-[:CITES]->(d2:Document)
WHERE d1.category = $category AND d2.category = $category

WITH d1, d2, count(*) AS citation_count

RETURN d1.title AS citing_document,
       d2.title AS cited_document,
       citation_count
ORDER BY citation_count DESC
LIMIT 50
"""

GET_CONCEPT_SIMILARITY_NETWORK = """
// Find related clinical concepts based on co-occurrence in documents

MATCH (c1:ClinicalConcept)<-[:REFERENCES]-(d:Document)-[:REFERENCES]->(c2:ClinicalConcept)
WHERE c1.id < c2.id  // Avoid duplicates

WITH c1, c2, count(d) AS co_occurrence_count
WHERE co_occurrence_count >= 3  // At least 3 shared documents

RETURN c1.name AS concept1,
       c2.name AS concept2,
       co_occurrence_count
ORDER BY co_occurrence_count DESC
LIMIT 100
"""

# =============================================================================
# HEALTH CHECK & MONITORING QUERIES
# =============================================================================

HEALTH_CHECK = """
// Basic health check query

RETURN 1 AS health,
       datetime() AS timestamp
"""

GET_INDEX_STATUS = """
// Check status of all indexes

SHOW INDEXES
YIELD name, state, type, populationPercent
WHERE name IN ['document_embeddings', 'concept_embeddings', 'document_fulltext', 'concept_fulltext']

RETURN name,
       state,
       type,
       populationPercent
"""

GET_DATABASE_STATISTICS = """
// Database statistics for monitoring

MATCH (n)

WITH labels(n) AS nodeLabels, count(n) AS nodeCount

UNWIND nodeLabels AS label

RETURN label,
       sum(nodeCount) AS total_nodes
ORDER BY total_nodes DESC
"""

GET_RELATIONSHIP_STATISTICS = """
// Relationship statistics

MATCH ()-[r]->()

WITH type(r) AS relationship_type, count(r) AS relationship_count

RETURN relationship_type,
       relationship_count
ORDER BY relationship_count DESC
"""

# =============================================================================
# QUERY TEMPLATES (For Parameterized Execution)
# =============================================================================

QUERY_TEMPLATES: Dict[str, str] = {
    # Vector search
    "vector_search_documents": VECTOR_SEARCH_DOCUMENTS,
    "vector_search_concepts": VECTOR_SEARCH_CONCEPTS,
    "hybrid_search_with_context": HYBRID_SEARCH_WITH_CONTEXT,
    "multi_hop_retrieval": MULTI_HOP_RETRIEVAL,

    # Full-text search
    "fulltext_search_documents": FULLTEXT_SEARCH_DOCUMENTS,
    "fulltext_search_concepts": FULLTEXT_SEARCH_CONCEPTS,

    # Session management
    "create_session": CREATE_SESSION,
    "get_session": GET_SESSION,
    "update_session_metrics": UPDATE_SESSION_METRICS,
    "cleanup_expired_sessions": CLEANUP_EXPIRED_SESSIONS,
    "get_active_session_count": GET_ACTIVE_SESSION_COUNT,
    "get_user_sessions": GET_USER_SESSIONS,

    # Audit logging
    "create_audit_log": CREATE_AUDIT_LOG,
    "get_audit_logs_by_user": GET_AUDIT_LOGS_BY_USER,
    "get_audit_logs_by_session": GET_AUDIT_LOGS_BY_SESSION,
    "cleanup_expired_audit_logs": CLEANUP_EXPIRED_AUDIT_LOGS,
    "get_usage_statistics": GET_USAGE_STATISTICS,

    # Calculators & templates
    "get_calculator_by_id": GET_CALCULATOR_BY_ID,
    "get_calculators_by_category": GET_CALCULATORS_BY_CATEGORY,
    "get_all_calculator_categories": GET_ALL_CALCULATOR_CATEGORIES,
    "increment_calculator_usage": INCREMENT_CALCULATOR_USAGE,
    "get_template_by_id": GET_TEMPLATE_BY_ID,
    "get_templates_by_type": GET_TEMPLATES_BY_TYPE,

    # Data ingestion
    "batch_ingest_documents": BATCH_INGEST_DOCUMENTS,
    "create_document_concept_relationships": CREATE_DOCUMENT_CONCEPT_RELATIONSHIPS,
    "batch_ingest_clinical_concepts": BATCH_INGEST_CLINICAL_CONCEPTS,
    "batch_ingest_calculators": BATCH_INGEST_CALCULATORS,

    # Analytics
    "get_most_referenced_concepts": GET_MOST_REFERENCED_CONCEPTS,
    "get_citation_network": GET_CITATION_NETWORK,
    "get_concept_similarity_network": GET_CONCEPT_SIMILARITY_NETWORK,

    # Health & monitoring
    "health_check": HEALTH_CHECK,
    "get_index_status": GET_INDEX_STATUS,
    "get_database_statistics": GET_DATABASE_STATISTICS,
    "get_relationship_statistics": GET_RELATIONSHIP_STATISTICS,
}


def get_query(query_name: str) -> str:
    """
    Retrieve a query template by name.

    Args:
        query_name: Name of the query template

    Returns:
        Cypher query string

    Raises:
        KeyError: If query name not found
    """
    if query_name not in QUERY_TEMPLATES:
        raise KeyError(f"Query template '{query_name}' not found")

    return QUERY_TEMPLATES[query_name]
