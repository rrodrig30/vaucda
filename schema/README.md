# VAUCDA Neo4j Schema

Complete Neo4j graph database schema for the VA Urology Clinical Documentation Assistant (VAUCDA).

## Overview

This schema implements a **hybrid knowledge graph + vector store** optimized for:
- **RAG (Retrieval-Augmented Generation)**: 768-dimensional vector similarity search
- **Clinical Decision Support**: 44 calculators across 10 urologic subspecialties
- **Knowledge Graph Navigation**: Semantic relationships between guidelines, literature, and clinical concepts
- **HIPAA Compliance**: Zero-persistence PHI architecture with 30-minute TTL

## Directory Structure

```
schema/
├── README.md                          # This file
├── SCHEMA_DOCUMENTATION.md            # Complete schema documentation
├── neo4j_schema.cypher                # Main schema definition
│
├── queries/
│   └── common_operations.cypher       # Frequently-used queries
│
├── sample_data/
│   └── load_sample_data.cypher        # Sample data for testing
│
└── migrations/
    └── 001_add_ambient_listening_support.cypher
```

## Quick Start

### 1. Prerequisites

- Neo4j 5.15+ with APOC and GDS plugins
- sentence-transformers/all-MiniLM-L6-v2 (768-dim embeddings)
- Python 3.11+ for data ingestion scripts

### 2. Initialize Schema

```bash
# Connect to Neo4j and create schema
cypher-shell -u neo4j -p <password> -f neo4j_schema.cypher

# Verify constraints and indexes
cypher-shell -u neo4j -p <password> -a neo4j://localhost:7687 \
  "SHOW CONSTRAINTS; SHOW INDEXES;"

# Wait for indexes to populate (up to 5 minutes)
cypher-shell -u neo4j -p <password> -a neo4j://localhost:7687 \
  "CALL db.awaitIndexes(300);"
```

### 3. Load Sample Data (Optional)

```bash
# Load test data
cypher-shell -u neo4j -p <password> -f sample_data/load_sample_data.cypher

# Verify data loaded
cypher-shell -u neo4j -p <password> -a neo4j://localhost:7687 \
  "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count;"
```

### 4. Set Up TTL Cleanup

The schema uses ephemeral Session nodes with a 30-minute TTL for HIPAA compliance.

**Option A: Cron Job**
```bash
# Add to crontab (runs every minute)
* * * * * curl -X POST http://localhost:8000/api/v1/admin/cleanup-sessions
```

**Option B: Systemd Timer**
```bash
# Create /etc/systemd/system/neo4j-ttl-cleanup.service
[Service]
Type=oneshot
ExecStart=/usr/bin/cypher-shell -u neo4j -p <password> \
  "MATCH (s:Session) WHERE s.expires_at < datetime() DETACH DELETE s;"

# Create /etc/systemd/system/neo4j-ttl-cleanup.timer
[Timer]
OnCalendar=*:0/1
Persistent=true

[Install]
WantedBy=timers.target

# Enable and start
sudo systemctl enable neo4j-ttl-cleanup.timer
sudo systemctl start neo4j-ttl-cleanup.timer
```

**Option C: APOC Periodic Commit (if APOC installed)**
```cypher
CALL apoc.periodic.commit(
  "MATCH (s:Session) WHERE s.expires_at < datetime()
   WITH s LIMIT 1000
   DETACH DELETE s
   RETURN count(*)",
  {interval: '60s'}
);
```

## Schema Components

### Node Types (7)

| Node Type | Purpose | Count (Production) | PHI Content |
|-----------|---------|-------------------|-------------|
| **Guideline** | Clinical practice guidelines (AUA, NCCN, EAU) | ~500 | No |
| **Calculator** | 44 clinical calculators | 44 | No |
| **Literature** | Journal articles, research papers | ~2,000 | No |
| **ClinicalConcept** | Diseases, treatments, procedures | ~1,000 | No |
| **DocumentChunk** | RAG-optimized chunks (512-1024 tokens) | ~10,000 | No |
| **Session** | Ephemeral user sessions (30-min TTL) | Variable | **YES** |
| **AuditLog** | Metadata-only audit trail | Variable | No |

### Relationship Types (8)

- `[:REFERENCES]` - Guideline → Literature (citations)
- `[:COVERS]` - Guideline → ClinicalConcept (topic mapping)
- `[:IMPLEMENTS]` - Calculator → Guideline (algorithm source)
- `[:APPLIES_TO]` - Calculator → ClinicalConcept (clinical applicability)
- `[:BELONGS_TO]` - DocumentChunk → Guideline/Literature (source document)
- `[:NEXT_CHUNK]` - DocumentChunk → DocumentChunk (sequential ordering)
- `[:RELATED_TO]` - ClinicalConcept → ClinicalConcept (clinical relationships)
- `[:USED_CALCULATOR]` - Session → Calculator (ephemeral usage tracking)

### Vector Indexes (4)

All use **cosine similarity** on **768-dimensional embeddings** from sentence-transformers/all-MiniLM-L6-v2:

1. **`document_chunk_embeddings`** (PRIMARY) - RAG retrieval on DocumentChunk nodes
2. **`guideline_embeddings`** - Direct guideline similarity search
3. **`literature_embeddings`** - Abstract-level literature search
4. **`concept_embeddings`** - Clinical concept similarity

### Property Indexes (21)

Optimized for common query patterns:
- Category filtering: `Guideline.category`, `Calculator.category`
- Date sorting: `Guideline.publication_date`, `AuditLog.timestamp`
- Lookup operations: `Literature.doi`, `Literature.pubmed_id`, `ClinicalConcept.icd10_code`
- TTL cleanup: `Session.expires_at`, `Session.created_at`

### Full-Text Indexes (5)

Keyword search across:
- `guideline_content_fulltext` - Guideline title + content
- `literature_content_fulltext` - Literature title + abstract + full_text
- `concept_fulltext` - ClinicalConcept name + description
- `chunk_content_fulltext` - DocumentChunk content
- `calculator_fulltext` - Calculator name + description

## Common Operations

### RAG Retrieval (Vector Search)

```cypher
// Basic vector search
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    5,
    $query_embedding
)
YIELD node AS chunk, score
WHERE score >= 0.7
MATCH (chunk)-[:BELONGS_TO]->(source)
RETURN chunk.content, source.title, score
ORDER BY score DESC;
```

### Session Management

```cypher
// Create session (30-min TTL)
CREATE (s:Session {
    session_id: randomUUID(),
    user_id: $user_id,
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    note_context: $clinical_data,
    active: true
})
RETURN s.session_id;

// Retrieve active session
MATCH (s:Session {session_id: $session_id})
WHERE s.expires_at > datetime() AND s.active = true
RETURN s.note_context;

// Delete session
MATCH (s:Session {session_id: $session_id})
DETACH DELETE s;
```

### Knowledge Graph Traversal

```cypher
// Evidence chain: Calculator → Guideline → Literature
MATCH path = (calc:Calculator {name: 'CAPRA Score'})
             -[:IMPLEMENTS]->(g:Guideline)
             -[:REFERENCES]->(lit:Literature)
RETURN calc.name, g.title, lit.doi;

// Related clinical concepts
MATCH (cc:ClinicalConcept {name: 'Prostate Adenocarcinoma'})
      -[r:RELATED_TO]->(related)
WHERE r.strength >= 0.7
RETURN related.name, r.relationship, r.strength
ORDER BY r.strength DESC;
```

### Audit Logging

```cypher
// Create audit log (NO PHI)
CREATE (a:AuditLog {
    id: randomUUID(),
    session_hash: $session_hash,  // SHA256 of session_id
    timestamp: datetime(),
    action_type: 'note_generation',
    user_id: $user_id,
    model_used: 'llama3.1:8b',
    tokens_used: 2048,
    duration_ms: 2340,
    success: true
});

// Retrieve user audit trail
MATCH (a:AuditLog {user_id: $user_id})
WHERE a.timestamp >= $start_date
RETURN a.timestamp, a.action_type, a.model_used, a.duration_ms
ORDER BY a.timestamp DESC
LIMIT 100;
```

## Data Ingestion

### 1. Generate Embeddings

Use `sentence-transformers/all-MiniLM-L6-v2` to generate 768-dimensional embeddings:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Generate embedding for guideline
text = "Prostate cancer risk stratification uses PSA, Gleason score, and clinical stage..."
embedding = model.encode(text).tolist()  # Returns 768-dim list

# Store in Neo4j
query = """
CREATE (g:Guideline {
    id: $id,
    title: $title,
    content: $content,
    embedding: $embedding,
    ...
})
"""
```

### 2. Chunk Documents

For RAG, chunk documents into 512-1024 token segments with 128-token overlap:

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1024,
    chunk_overlap=128,
    separators=["\n\n", "\n", ". ", " ", ""]
)

chunks = splitter.split_text(guideline_content)

for i, chunk_text in enumerate(chunks):
    chunk_embedding = model.encode(chunk_text).tolist()
    # Store in Neo4j as DocumentChunk node
```

### 3. Create Relationships

Link nodes to build knowledge graph:

```cypher
// Link calculator to guideline
MATCH (calc:Calculator {name: 'CAPRA Score'})
MATCH (g:Guideline {title: 'NCCN Prostate Cancer Guidelines 2024'})
CREATE (calc)-[:IMPLEMENTS {version: '1.2024', validated: true}]->(g);

// Link guideline to literature
MATCH (g:Guideline {id: $guideline_id})
MATCH (lit:Literature {doi: '10.1001/jama.292.18.2237'})
CREATE (g)-[:REFERENCES {citation_type: 'evidence', strength: 'high'}]->(lit);
```

## Performance Tuning

### Vector Search Optimization

```cypher
// Use appropriate top-k (5-10 is typical)
CALL db.index.vector.queryNodes(
    'document_chunk_embeddings',
    5,  // Don't retrieve 100 results if you only need 5
    $embedding
)
YIELD node, score
RETURN node.content;

// Apply filters AFTER vector search (not before)
CALL db.index.vector.queryNodes(...) YIELD node, score
WHERE score >= 0.7
MATCH (node)-[:BELONGS_TO]->(source)
WHERE source.category = 'prostate'  // Filter after retrieval
RETURN ...;
```

### Query Profiling

```cypher
// Profile query performance
PROFILE
MATCH (g:Guideline {category: 'prostate'})
RETURN g.title
ORDER BY g.publication_date DESC
LIMIT 5;

// Check index usage
EXPLAIN
MATCH (g:Guideline {category: 'prostate'})
RETURN g.title;
```

### Index Monitoring

```cypher
// Verify vector indexes are online
SHOW INDEXES
YIELD name, type, state
WHERE type = 'VECTOR'
RETURN name, state;

// Check index population status
CALL db.awaitIndexes(300);  // Wait up to 5 minutes
```

## HIPAA Compliance

### PHI Handling Rules

**WHERE PHI IS STORED:**
- **Session nodes ONLY**: `note_context` property
- **Maximum lifetime**: 30 minutes (automatic TTL deletion)
- **Immediate deletion**: When note generation completes

**WHERE PHI IS NEVER STORED:**
- AuditLog nodes (only metadata: hashed session_id, action type, performance metrics)
- Guideline/Literature/Calculator nodes (general medical knowledge)
- Neo4j query logs (queries are parameterized)

### Compliance Verification

```cypher
// Check for PHI violations in AuditLog
MATCH (a:AuditLog)
WHERE exists(a.clinical_input) OR exists(a.generated_note)
RETURN count(a) AS phi_violations;  // Should return 0

// Check for expired sessions
MATCH (s:Session)
WHERE s.expires_at < datetime()
RETURN count(s) AS expired_sessions;  // Should return 0 (TTL cleanup working)

// Verify all sessions have expiration
MATCH (s:Session)
WHERE NOT exists(s.expires_at)
RETURN count(s) AS sessions_without_ttl;  // Should return 0
```

## Troubleshooting

### Vector Search Returns No Results

**Check 1: Embeddings populated?**
```cypher
MATCH (dc:DocumentChunk)
WHERE dc.embedding IS NOT NULL
RETURN count(dc) AS chunks_with_embeddings;
```

**Check 2: Vector index online?**
```cypher
SHOW INDEXES YIELD name, state
WHERE name = 'document_chunk_embeddings'
RETURN state;  // Should be 'ONLINE'
```

**Check 3: Similarity threshold too high?**
```cypher
// Lower threshold to 0.5 or remove
CALL db.index.vector.queryNodes(...) YIELD node, score
WHERE score >= 0.5  // Instead of 0.7
RETURN ...;
```

### Slow Query Performance

**Check 1: Missing indexes?**
```cypher
EXPLAIN
MATCH (g:Guideline {category: 'prostate'})
RETURN g;
// Should show "NodeIndexSeek" not "NodeByLabelScan"
```

**Check 2: Using parameters?**
```cypher
// GOOD (enables query plan caching)
MATCH (g:Guideline {category: $category})

// BAD (query plan cache miss)
MATCH (g:Guideline {category: 'prostate'})
```

**Check 3: Limiting results?**
```cypher
// GOOD
CALL db.index.vector.queryNodes(..., 5, $embedding)  // Limit at source

// BAD
CALL db.index.vector.queryNodes(..., 100, $embedding)
... LIMIT 5  // Waste processing 95 results
```

### Session TTL Not Working

**Check 1: Cleanup job running?**
```bash
# Check cron logs
grep "cleanup-sessions" /var/log/syslog

# Or check systemd timer
systemctl status neo4j-ttl-cleanup.timer
```

**Check 2: Verify cleanup query**
```cypher
// Run manually to see count
MATCH (s:Session)
WHERE s.expires_at < datetime()
RETURN count(s) AS expired_sessions;
```

## Migrations

### Apply Migration 001 (Ambient Listening)

```bash
# Apply migration
cypher-shell -u neo4j -p <password> \
  -f migrations/001_add_ambient_listening_support.cypher

# Verify new constraints
cypher-shell -u neo4j -p <password> \
  "SHOW CONSTRAINTS WHERE name CONTAINS 'ambient';"

# Verify new indexes
cypher-shell -u neo4j -p <password> \
  "SHOW INDEXES WHERE name CONTAINS 'ambient';"
```

## Additional Resources

- **Complete Documentation**: [SCHEMA_DOCUMENTATION.md](SCHEMA_DOCUMENTATION.md)
- **Query Examples**: [queries/common_operations.cypher](queries/common_operations.cypher)
- **Sample Data**: [sample_data/load_sample_data.cypher](sample_data/load_sample_data.cypher)
- **Migration Scripts**: [migrations/](migrations/)

## Support

For schema questions or issues:
- **Technical Lead**: VAUCDA Development Team
- **Documentation**: See SCHEMA_DOCUMENTATION.md for comprehensive details
- **Neo4j Resources**: https://neo4j.com/docs/

---

**Schema Version**: 1.0
**Last Updated**: 2025-11-29
**Next Review**: 2026-02-28
