# VAUCDA Neo4j Database

Production-ready Neo4j database architecture for VAUCDA's hybrid graph + vector search capabilities.

## Quick Start

### 1. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit with your secure password
nano .env
```

### 2. Start Neo4j

```bash
# Start Neo4j container
docker-compose -f docker-compose.neo4j.yml up -d

# Wait for Neo4j to be ready (30-60 seconds)
docker logs -f vaucda-neo4j

# Initialize schema (constraints, indexes, TTL jobs)
../scripts/neo4j/init_neo4j.sh
```

### 3. Verify Installation

```bash
# Access Neo4j Browser
open http://localhost:7474

# Login with credentials from .env
# Username: neo4j
# Password: (from NEO4J_PASSWORD in .env)

# Run health check
python ../scripts/neo4j/monitor_neo4j.py
```

## Architecture Overview

### Database Structure

- **Clinical Knowledge Graph**: Documents, ClinicalConcepts, Calculators
- **Vector Search**: 768-dimensional embeddings for RAG retrieval
- **Ephemeral Sessions**: 30-minute TTL for HIPAA compliance
- **Audit Logging**: Metadata-only tracking (no PHI)

### Performance Targets

| Operation | Target Latency | Throughput |
|-----------|---------------|------------|
| Vector search (top-10) | < 100ms | 500+ queries/sec |
| Hybrid retrieval | < 250ms | 300+ queries/sec |
| Session creation | < 50ms | 1000+ ops/sec |

### Key Features

- **Sub-second RAG retrieval** via HNSW vector indexes
- **HIPAA-compliant** with zero PHI persistence
- **Automatic TTL cleanup** for sessions and audit logs
- **Production-ready** connection pooling (100 connections)
- **Horizontally scalable** for 500+ concurrent users

## Directory Structure

```
neo4j/
├── conf/
│   └── neo4j.conf              # Production configuration
├── docker-compose.neo4j.yml    # Container orchestration
├── .env.example                # Environment template
└── README.md                   # This file

backend/database/
├── neo4j_client.py             # Python driver client
├── neo4j_queries.py            # Query library
└── migrations/neo4j/
    └── init_schema.cypher      # Schema initialization

scripts/neo4j/
├── init_neo4j.sh               # Initialize database
├── backup_neo4j.sh             # Backup procedure
├── restore_neo4j.sh            # Restore procedure
└── monitor_neo4j.py            # Health monitoring
```

## Configuration

### Memory Configuration (32GB Server)

```properties
# Heap: 8GB
dbms.memory.heap.initial_size=8g
dbms.memory.heap.max_size=8g

# Page Cache: 16GB
dbms.memory.pagecache.size=16g
```

For 64GB servers, update to:
- Heap: 16GB
- Page Cache: 40GB

### Connection Pooling

```properties
# Bolt connections
dbms.connector.bolt.thread_pool.min_size=50
dbms.connector.bolt.thread_pool.max_size=400
```

### Vector Index Settings

```cypher
// Document embeddings (768 dimensions)
CREATE VECTOR INDEX document_embeddings
FOR (d:Document) ON (d.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine',
        `vector.hnsw.m`: 16,
        `vector.hnsw.ef_construction`: 200
    }
};
```

## Operations

### Database Initialization

```bash
# Initialize schema, indexes, and constraints
./scripts/neo4j/init_neo4j.sh

# Verify indexes are online
cypher-shell "SHOW INDEXES YIELD name, state"
```

### Backup and Restore

```bash
# Create backup
./scripts/neo4j/backup_neo4j.sh

# List available backups
ls -lh /backups/neo4j/

# Restore from backup
./scripts/neo4j/restore_neo4j.sh /backups/neo4j/vaucda_neo4j_20250129_120000.tar.gz
```

### Monitoring

```bash
# Run health check
python scripts/neo4j/monitor_neo4j.py

# Check logs
docker logs vaucda-neo4j

# View slow queries
docker exec vaucda-neo4j cat /logs/query.log | grep "time=" | awk '{if ($NF > 1000) print}'
```

### Session TTL Cleanup

Sessions are automatically deleted after 30 minutes via APOC periodic procedure.

Manual cleanup:
```cypher
MATCH (s:Session)
WHERE s.expires_at < datetime() AND s.status = 'active'
SET s.status = 'expired'
WITH s
DETACH DELETE s
RETURN count(s) AS deleted_count;
```

## Python Client Usage

### Basic Connection

```python
from backend.database.neo4j_client import Neo4jClient, Neo4jConfig

# Initialize client
config = Neo4jConfig()
client = Neo4jClient(config)

# Verify connectivity
await client.verify_connectivity()
```

### Vector Search

```python
# Retrieve top-5 similar documents
results = await client.vector_search_documents(
    query_embedding=[0.1, 0.2, ..., 0.5],  # 768-dim vector
    k=5,
    category="prostate"
)

for doc in results:
    print(f"{doc['title']}: {doc['similarity_score']}")
```

### Hybrid Retrieval (Vector + Graph)

```python
# Vector search with graph context
results = await client.hybrid_search(
    query_embedding=[...],
    k=5,
    category="kidney"
)

for doc in results:
    print(f"Document: {doc['title']}")
    print(f"Concepts: {doc['related_concepts']}")
    print(f"Calculators: {doc['applicable_calculators']}")
```

### Session Management

```python
# Create session (30-minute TTL)
session = await client.create_session(
    session_id="abc123",
    user_id="user456",
    note_type="clinic_note",
    llm_provider="ollama",
    model_used="llama3.1:8b",
    selected_modules=["capra_score"]
)

# Update with metrics
await client.update_session_metrics(
    session_id="abc123",
    generation_time_ms=2500,
    tokens_used=1024
)
```

### Audit Logging (HIPAA-Compliant)

```python
# Create audit log (metadata only, NO PHI)
audit_id = await client.create_audit_log(
    session_id="abc123",
    user_id="user456",
    action="note_generation",
    module_used="capra_score",
    input_hash="sha256_hash_of_input",  # Hash only, not actual input
    output_hash="sha256_hash_of_output",
    duration_ms=2500,
    tokens_used=1024,
    llm_provider="ollama",
    model_used="llama3.1:8b",
    success=True
)
```

## HIPAA Compliance

### What is Stored

- Clinical knowledge (guidelines, calculators) - NOT patient-specific
- Session metadata (timestamps, user IDs, module usage)
- Audit logs (hashed identifiers only)

### What is NEVER Stored

- Patient clinical input
- Generated clinical notes
- Patient identifiers (MRN, SSN)
- Any Protected Health Information (PHI)

### Session TTL

All sessions are automatically deleted after 30 minutes:

```cypher
// Automatic cleanup via APOC
CALL apoc.periodic.repeat(
    'session-ttl-cleanup',
    'MATCH (s:Session)
     WHERE s.expires_at < datetime()
     DETACH DELETE s',
    300  // Every 5 minutes
);
```

## Scaling

### Horizontal Scaling (500+ Users)

For production deployments exceeding 500 concurrent users:

1. **Deploy Neo4j Causal Cluster**: 3+ core servers
2. **Add Read Replicas**: For vector search queries
3. **Enable Load Balancing**: Use Neo4j routing

Update `docker-compose.neo4j.yml`:

```yaml
# Uncomment neo4j-replica service
# Update core count in neo4j service configuration
```

### Vertical Scaling

| Server RAM | Heap | Page Cache | Max Users |
|------------|------|------------|-----------|
| 32GB | 8GB | 16GB | 500 |
| 64GB | 16GB | 40GB | 1000 |
| 128GB | 32GB | 80GB | 2000+ |

## Troubleshooting

### Vector Indexes Not Online

```cypher
SHOW INDEXES YIELD name, state WHERE name IN ['document_embeddings', 'concept_embeddings'];
```

If not online, rebuild:
```cypher
DROP INDEX document_embeddings IF EXISTS;
CREATE VECTOR INDEX document_embeddings ...;
```

### High Memory Usage

Check page cache hit rate:
```cypher
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Page cache")
YIELD attributes
RETURN attributes.HitRatio.value;
```

Target: > 85% hit rate

### Connection Pool Exhausted

Increase pool size in `neo4j.conf`:
```properties
dbms.connector.bolt.thread_pool.max_size=600
```

### Slow Queries

Enable query logging and analyze:
```bash
docker exec vaucda-neo4j cat /logs/query.log | grep "time=" | sort -t'=' -k2 -n | tail -20
```

## Documentation

- **Architecture**: `/docs/NEO4J_ARCHITECTURE.md`
- **Query Library**: `backend/database/neo4j_queries.py`
- **Client Reference**: `backend/database/neo4j_client.py`

## Support

For issues or questions:
1. Check logs: `docker logs vaucda-neo4j`
2. Run health check: `python scripts/neo4j/monitor_neo4j.py`
3. Review documentation: `/docs/NEO4J_ARCHITECTURE.md`

---

**Version**: 1.0
**Last Updated**: November 29, 2025
