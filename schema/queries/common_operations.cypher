// ============================================================================
// VAUCDA Common Query Operations
// ============================================================================
// Collection of frequently-used Cypher queries for VAUCDA operations
// ============================================================================

// ============================================================================
// SECTION 1: VECTOR SIMILARITY SEARCH (RAG Retrieval)
// ============================================================================

// ============================================================================
// Query 1.1: Basic Vector Similarity Search on DocumentChunks
// ============================================================================
// Purpose: Retrieve top-k similar chunks for RAG context assembly
// Parameters:
//   $query_embedding: LIST<FLOAT> (768-dim embedding vector)
//   $top_k: INTEGER (number of results, default 5)
//   $min_score: FLOAT (minimum similarity threshold, 0.0-1.0)
// ============================================================================

CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    $top_k,
    $query_embedding
)
YIELD node AS chunk, score
WHERE score >= $min_score
MATCH (chunk)-[:BELONGS_TO]->(source)
RETURN
    chunk.id AS chunk_id,
    chunk.content AS content,
    chunk.metadata AS metadata,
    score AS similarity_score,
    source.title AS source_title,
    source.category AS source_category,
    labels(source)[0] AS source_type
ORDER BY score DESC;


// ============================================================================
// Query 1.2: Category-Filtered Vector Search
// ============================================================================
// Purpose: Vector search with category filter (e.g., only "prostate" content)
// Parameters:
//   $query_embedding: LIST<FLOAT> (768-dim embedding vector)
//   $category: STRING (e.g., "prostate", "kidney", "bladder")
//   $top_k: INTEGER (number of results)
// ============================================================================

CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    $top_k,
    $query_embedding
)
YIELD node AS chunk, score
MATCH (chunk)-[:BELONGS_TO]->(source)
WHERE source.category = $category
RETURN
    chunk.id AS chunk_id,
    chunk.content AS content,
    chunk.metadata AS metadata,
    score AS similarity_score,
    source.title AS source_title,
    source.organization AS source_org
ORDER BY score DESC;


// ============================================================================
// Query 1.3: Multi-Chunk Context Expansion
// ============================================================================
// Purpose: Retrieve adjacent chunks for expanded context window
// Parameters:
//   $chunk_id: STRING (ID of the primary chunk)
//   $context_window: INTEGER (number of chunks before/after, default 1)
// ============================================================================

MATCH (primary:DocumentChunk {id: $chunk_id})
OPTIONAL MATCH path_before = (primary)-[:NEXT_CHUNK*1..$context_window]->(after)
OPTIONAL MATCH path_after = (before)-[:NEXT_CHUNK*1..$context_window]->(primary)
WITH primary,
     collect(DISTINCT before) AS chunks_before,
     collect(DISTINCT after) AS chunks_after
UNWIND (chunks_before + [primary] + chunks_after) AS chunk
RETURN chunk.id AS chunk_id,
       chunk.chunk_index AS position,
       chunk.content AS content
ORDER BY position;


// ============================================================================
// Query 1.4: Hybrid Search (Vector + Full-Text)
// ============================================================================
// Purpose: Combine vector similarity with keyword matching
// Parameters:
//   $query_embedding: LIST<FLOAT> (768-dim vector)
//   $query_text: STRING (search keywords)
//   $top_k: INTEGER
//   $vector_weight: FLOAT (0.0-1.0, default 0.7)
// ============================================================================

// Vector search
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    $top_k * 2,  // Get extra candidates for keyword filtering
    $query_embedding
)
YIELD node AS chunk, score AS vector_score

// Full-text search
CALL db.index.fulltext.queryNodes(
    'chunk_content_fulltext',
    $query_text
)
YIELD node AS ft_chunk, score AS text_score

// Combine results
WITH chunk, vector_score, ft_chunk, text_score
WHERE chunk = ft_chunk
WITH chunk,
     ($vector_weight * vector_score + (1 - $vector_weight) * text_score) AS combined_score
MATCH (chunk)-[:BELONGS_TO]->(source)
RETURN
    chunk.id AS chunk_id,
    chunk.content AS content,
    combined_score AS relevance_score,
    source.title AS source_title
ORDER BY combined_score DESC
LIMIT $top_k;


// ============================================================================
// SECTION 2: SESSION MANAGEMENT (Ephemeral PHI Storage)
// ============================================================================

// ============================================================================
// Query 2.1: Create New Session (30-min TTL)
// ============================================================================
// Purpose: Initialize ephemeral session for PHI handling
// Parameters:
//   $session_id: STRING (UUID)
//   $user_id: STRING
//   $note_context: STRING (optional PHI content)
// ============================================================================

CREATE (s:Session {
    session_id: $session_id,
    user_id: $user_id,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    note_context: $note_context,
    active: true
})
RETURN s.session_id AS session_id,
       s.created_at AS created_at,
       s.expires_at AS expires_at;


// ============================================================================
// Query 2.2: Retrieve Active Session
// ============================================================================
// Purpose: Get session data if not expired
// Parameters:
//   $session_id: STRING
// ============================================================================

MATCH (s:Session {session_id: $session_id})
WHERE s.expires_at > datetime() AND s.active = true
RETURN s.session_id AS session_id,
       s.user_id AS user_id,
       s.note_context AS note_context,
       s.created_at AS created_at,
       s.expires_at AS expires_at;


// ============================================================================
// Query 2.3: Delete Expired Sessions (TTL Cleanup)
// ============================================================================
// Purpose: Remove sessions past 30-minute expiration
// Schedule: Run every 1 minute via external scheduler
// Returns: Count of deleted sessions
// ============================================================================

MATCH (s:Session)
WHERE s.expires_at < datetime()
WITH s, count(s) AS session_count
DETACH DELETE s
RETURN session_count AS deleted_sessions;


// ============================================================================
// Query 2.4: Manually Terminate Session
// ============================================================================
// Purpose: Immediately delete session and all related data
// Parameters:
//   $session_id: STRING
// ============================================================================

MATCH (s:Session {session_id: $session_id})
DETACH DELETE s
RETURN true AS session_deleted;


// ============================================================================
// SECTION 3: AUDIT LOG OPERATIONS (Metadata Only - No PHI)
// ============================================================================

// ============================================================================
// Query 3.1: Create Audit Log Entry
// ============================================================================
// Purpose: Log user action metadata (NEVER log PHI)
// Parameters:
//   $session_hash: STRING (SHA256 hash of session_id)
//   $user_id: STRING
//   $action_type: STRING (note_generation|calculator_use|evidence_search)
//   $model_used: STRING (optional)
//   $tokens_used: INTEGER (optional)
//   $duration_ms: INTEGER (optional)
//   $success: BOOLEAN
//   $error_code: STRING (optional)
// ============================================================================

CREATE (a:AuditLog {
    id: randomUUID(),
    session_hash: $session_hash,
    timestamp: datetime(),
    action_type: $action_type,
    user_id: $user_id,
    model_used: $model_used,
    tokens_used: $tokens_used,
    duration_ms: $duration_ms,
    success: $success,
    error_code: $error_code
})
RETURN a.id AS audit_id,
       a.timestamp AS logged_at;


// ============================================================================
// Query 3.2: Retrieve User Audit Trail
// ============================================================================
// Purpose: Get audit logs for specific user
// Parameters:
//   $user_id: STRING
//   $limit: INTEGER (default 100)
//   $start_date: DATETIME (optional)
//   $end_date: DATETIME (optional)
// ============================================================================

MATCH (a:AuditLog {user_id: $user_id})
WHERE ($start_date IS NULL OR a.timestamp >= $start_date)
  AND ($end_date IS NULL OR a.timestamp <= $end_date)
RETURN a.id AS audit_id,
       a.timestamp AS timestamp,
       a.action_type AS action,
       a.model_used AS model,
       a.tokens_used AS tokens,
       a.duration_ms AS duration,
       a.success AS success,
       a.error_code AS error
ORDER BY a.timestamp DESC
LIMIT $limit;


// ============================================================================
// SECTION 4: CALCULATOR OPERATIONS
// ============================================================================

// ============================================================================
// Query 4.1: Get Calculator by Name
// ============================================================================
// Purpose: Retrieve calculator metadata and schemas
// Parameters:
//   $calculator_name: STRING
// ============================================================================

MATCH (c:Calculator {name: $calculator_name})
RETURN c.name AS name,
       c.category AS category,
       c.description AS description,
       c.algorithm AS algorithm,
       c.input_schema AS input_schema,
       c.output_schema AS output_schema,
       c.validation_refs AS references,
       c.version AS version;


// ============================================================================
// Query 4.2: List Calculators by Category
// ============================================================================
// Purpose: Get all calculators for a specific clinical category
// Parameters:
//   $category: STRING (e.g., "prostate_cancer")
// ============================================================================

MATCH (c:Calculator {category: $category})
RETURN c.name AS name,
       c.description AS description,
       c.version AS version
ORDER BY c.name;


// ============================================================================
// Query 4.3: Find Calculators for Clinical Concept
// ============================================================================
// Purpose: Discover applicable calculators for a condition/procedure
// Parameters:
//   $concept_name: STRING
// ============================================================================

MATCH (cc:ClinicalConcept {name: $concept_name})<-[:APPLIES_TO]-(calc:Calculator)
RETURN calc.name AS calculator_name,
       calc.category AS category,
       calc.description AS description
ORDER BY calc.category, calc.name;


// ============================================================================
// Query 4.4: Record Calculator Usage in Session
// ============================================================================
// Purpose: Link calculator usage to ephemeral session
// Parameters:
//   $session_id: STRING
//   $calculator_name: STRING
//   $result_category: STRING (e.g., "high_risk", NO PHI)
// ============================================================================

MATCH (s:Session {session_id: $session_id})
MATCH (c:Calculator {name: $calculator_name})
CREATE (s)-[r:USED_CALCULATOR {
    timestamp: datetime(),
    result_category: $result_category
}]->(c)
RETURN r.timestamp AS usage_timestamp;


// ============================================================================
// SECTION 5: KNOWLEDGE GRAPH TRAVERSAL
// ============================================================================

// ============================================================================
// Query 5.1: Find Related Clinical Concepts
// ============================================================================
// Purpose: Discover related conditions, treatments, complications
// Parameters:
//   $concept_name: STRING
//   $relationship_type: STRING (optional: treats|causes|associated_with)
//   $min_strength: FLOAT (0.0-1.0, default 0.5)
// ============================================================================

MATCH (source:ClinicalConcept {name: $concept_name})-[r:RELATED_TO]->(related:ClinicalConcept)
WHERE ($relationship_type IS NULL OR r.relationship = $relationship_type)
  AND r.strength >= $min_strength
RETURN related.name AS concept_name,
       related.icd10_code AS icd10,
       related.snomed_code AS snomed,
       r.relationship AS relationship_type,
       r.strength AS strength
ORDER BY r.strength DESC;


// ============================================================================
// Query 5.2: Get Guidelines Covering Clinical Concept
// ============================================================================
// Purpose: Find guidelines addressing specific condition/procedure
// Parameters:
//   $concept_name: STRING
//   $organization: STRING (optional: AUA|NCCN|EAU)
// ============================================================================

MATCH (cc:ClinicalConcept {name: $concept_name})<-[:COVERS]-(g:Guideline)
WHERE $organization IS NULL OR g.organization = $organization
RETURN g.title AS guideline_title,
       g.organization AS organization,
       g.publication_date AS published,
       g.version AS version,
       g.url AS url
ORDER BY g.publication_date DESC;


// ============================================================================
// Query 5.3: Guideline-Literature Citation Network
// ============================================================================
// Purpose: Explore evidence supporting guidelines
// Parameters:
//   $guideline_id: STRING
// ============================================================================

MATCH (g:Guideline {id: $guideline_id})-[r:REFERENCES]->(lit:Literature)
RETURN lit.title AS literature_title,
       lit.authors AS authors,
       lit.journal AS journal,
       lit.doi AS doi,
       r.citation_type AS citation_type,
       r.strength AS evidence_strength
ORDER BY r.strength DESC, lit.publication_year DESC;


// ============================================================================
// Query 5.4: Calculator Validation Chain
// ============================================================================
// Purpose: Trace calculator to guidelines and supporting literature
// Parameters:
//   $calculator_name: STRING
// ============================================================================

MATCH (calc:Calculator {name: $calculator_name})-[:IMPLEMENTS]->(g:Guideline)
OPTIONAL MATCH (g)-[:REFERENCES]->(lit:Literature)
RETURN calc.name AS calculator,
       g.title AS guideline,
       g.organization AS guideline_org,
       collect(DISTINCT lit.title) AS supporting_literature,
       collect(DISTINCT lit.doi) AS literature_dois;


// ============================================================================
// SECTION 6: GUIDELINE AND LITERATURE SEARCH
// ============================================================================

// ============================================================================
// Query 6.1: Full-Text Search Guidelines
// ============================================================================
// Purpose: Keyword search across guideline content
// Parameters:
//   $search_text: STRING (search query)
//   $category: STRING (optional filter)
//   $limit: INTEGER (default 10)
// ============================================================================

CALL db.index.fulltext.queryNodes(
    'guideline_content_fulltext',
    $search_text
)
YIELD node AS g, score
WHERE $category IS NULL OR g.category = $category
RETURN g.id AS guideline_id,
       g.title AS title,
       g.organization AS organization,
       g.category AS category,
       g.publication_date AS published,
       score AS relevance_score
ORDER BY score DESC
LIMIT $limit;


// ============================================================================
// Query 6.2: Search Literature by Topic
// ============================================================================
// Purpose: Find relevant journal articles
// Parameters:
//   $search_text: STRING
//   $journal_filter: STRING (optional)
//   $year_min: INTEGER (optional)
//   $limit: INTEGER (default 10)
// ============================================================================

CALL db.index.fulltext.queryNodes(
    'literature_content_fulltext',
    $search_text
)
YIELD node AS lit, score
WHERE ($journal_filter IS NULL OR lit.journal = $journal_filter)
  AND ($year_min IS NULL OR lit.publication_year >= $year_min)
RETURN lit.title AS title,
       lit.authors AS authors,
       lit.journal AS journal,
       lit.doi AS doi,
       lit.pubmed_id AS pubmed_id,
       lit.publication_year AS year,
       score AS relevance_score
ORDER BY score DESC
LIMIT $limit;


// ============================================================================
// Query 6.3: Recent Guidelines by Category
// ============================================================================
// Purpose: Get latest guidelines for specific specialty
// Parameters:
//   $category: STRING (e.g., "prostate")
//   $limit: INTEGER (default 5)
// ============================================================================

MATCH (g:Guideline {category: $category})
RETURN g.id AS guideline_id,
       g.title AS title,
       g.organization AS organization,
       g.publication_date AS published,
       g.version AS version,
       g.url AS url
ORDER BY g.publication_date DESC
LIMIT $limit;


// ============================================================================
// SECTION 7: DATA INGESTION HELPERS
// ============================================================================

// ============================================================================
// Query 7.1: Create Guideline with DocumentChunks
// ============================================================================
// Purpose: Insert guideline and associated chunks in single transaction
// Parameters:
//   $guideline: MAP {id, title, organization, publication_date, category,
//                    version, content, embedding, url}
//   $chunks: LIST<MAP> [{chunk_id, chunk_index, content, embedding, metadata}]
// ============================================================================

CREATE (g:Guideline {
    id: $guideline.id,
    title: $guideline.title,
    organization: $guideline.organization,
    publication_date: date($guideline.publication_date),
    category: $guideline.category,
    version: $guideline.version,
    content: $guideline.content,
    embedding: $guideline.embedding,
    url: $guideline.url,
    created_at: datetime(),
    updated_at: datetime()
})
WITH g
UNWIND $chunks AS chunk_data
CREATE (chunk:DocumentChunk {
    id: chunk_data.chunk_id,
    source_id: g.id,
    source_type: 'Guideline',
    chunk_index: chunk_data.chunk_index,
    content: chunk_data.content,
    embedding: chunk_data.embedding,
    metadata: chunk_data.metadata,
    created_at: datetime()
})
CREATE (chunk)-[:BELONGS_TO]->(g)
RETURN g.id AS guideline_id,
       count(chunk) AS chunks_created;


// ============================================================================
// Query 7.2: Create Sequential Chunk Relationships
// ============================================================================
// Purpose: Link chunks in reading order for context expansion
// Parameters:
//   $source_id: STRING (guideline or literature ID)
//   $overlap_tokens: INTEGER (default 128)
// ============================================================================

MATCH (chunk:DocumentChunk {source_id: $source_id})
WITH chunk ORDER BY chunk.chunk_index
WITH collect(chunk) AS chunks
UNWIND range(0, size(chunks) - 2) AS i
WITH chunks[i] AS current, chunks[i+1] AS next
CREATE (current)-[:NEXT_CHUNK {overlap_tokens: $overlap_tokens}]->(next)
RETURN count(*) AS relationships_created;


// ============================================================================
// Query 7.3: Link Calculator to Clinical Concepts
// ============================================================================
// Purpose: Create APPLIES_TO relationships
// Parameters:
//   $calculator_name: STRING
//   $concept_names: LIST<STRING>
// ============================================================================

MATCH (calc:Calculator {name: $calculator_name})
UNWIND $concept_names AS concept_name
MATCH (cc:ClinicalConcept {name: concept_name})
CREATE (calc)-[:APPLIES_TO {applicability: 'primary'}]->(cc)
RETURN calc.name AS calculator,
       collect(cc.name) AS linked_concepts;


// ============================================================================
// SECTION 8: ANALYTICS AND STATISTICS
// ============================================================================

// ============================================================================
// Query 8.1: Calculator Usage Statistics
// ============================================================================
// Purpose: Aggregate calculator usage by category
// Parameters:
//   $start_date: DATETIME
//   $end_date: DATETIME
// ============================================================================

MATCH (a:AuditLog)
WHERE a.action_type = 'calculator_use'
  AND a.timestamp >= $start_date
  AND a.timestamp <= $end_date
RETURN a.user_id AS user_id,
       count(*) AS total_calculations,
       collect(DISTINCT a.model_used) AS models_used,
       avg(a.duration_ms) AS avg_duration_ms,
       sum(a.tokens_used) AS total_tokens
ORDER BY total_calculations DESC;


// ============================================================================
// Query 8.2: Knowledge Graph Statistics
// ============================================================================
// Purpose: Get database metrics
// ============================================================================

// Count nodes by type
MATCH (n)
RETURN labels(n)[0] AS node_type,
       count(n) AS count
ORDER BY count DESC

UNION ALL

// Count relationships by type
MATCH ()-[r]->()
RETURN type(r) AS relationship_type,
       count(r) AS count
ORDER BY count DESC;


// ============================================================================
// Query 8.3: Vector Index Performance Check
// ============================================================================
// Purpose: Verify vector indexes are populated and performant
// ============================================================================

MATCH (dc:DocumentChunk)
WHERE dc.embedding IS NOT NULL
WITH count(dc) AS chunks_with_embeddings

MATCH (g:Guideline)
WHERE g.embedding IS NOT NULL
WITH chunks_with_embeddings, count(g) AS guidelines_with_embeddings

MATCH (lit:Literature)
WHERE lit.embedding IS NOT NULL
WITH chunks_with_embeddings, guidelines_with_embeddings, count(lit) AS literature_with_embeddings

RETURN chunks_with_embeddings AS chunk_embeddings,
       guidelines_with_embeddings AS guideline_embeddings,
       literature_with_embeddings AS literature_embeddings;


// ============================================================================
// END OF COMMON OPERATIONS
// ============================================================================
