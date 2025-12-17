#!/bin/bash
# Initialize Neo4j database for VAUCDA
# This script sets up the complete database schema, indexes, and constraints

set -e  # Exit on error

echo "========================================="
echo "VAUCDA Neo4j Database Initialization"
echo "========================================="

# Configuration
NEO4J_URI=${NEO4J_URI:-"bolt://localhost:7687"}
NEO4J_USER=${NEO4J_USER:-"neo4j"}
NEO4J_PASSWORD=${NEO4J_PASSWORD:-"changeme123"}
SCHEMA_FILE="/home/gulab/PythonProjects/VAUCDA/backend/database/migrations/neo4j/init_schema.cypher"

echo ""
echo "Configuration:"
echo "  URI: $NEO4J_URI"
echo "  User: $NEO4J_USER"
echo "  Schema File: $SCHEMA_FILE"
echo ""

# Wait for Neo4j to be ready
echo "[1/5] Waiting for Neo4j to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" > /dev/null 2>&1; then
        echo "✓ Neo4j is ready"
        break
    fi

    attempt=$((attempt + 1))
    echo "  Attempt $attempt/$max_attempts - waiting..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ ERROR: Neo4j did not become ready in time"
    exit 1
fi

# Execute schema initialization
echo ""
echo "[2/5] Executing schema initialization..."
if ! cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" --file "$SCHEMA_FILE"; then
    echo "✗ ERROR: Schema initialization failed"
    exit 1
fi
echo "✓ Schema initialized"

# Verify constraints
echo ""
echo "[3/5] Verifying constraints..."
constraint_count=$(cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "SHOW CONSTRAINTS YIELD name RETURN count(name) AS count" --format plain | tail -1)
echo "✓ Constraints created: $constraint_count"

# Verify indexes
echo ""
echo "[4/5] Verifying indexes..."
index_count=$(cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "SHOW INDEXES YIELD name RETURN count(name) AS count" --format plain | tail -1)
echo "✓ Indexes created: $index_count"

# Check vector index status
echo ""
echo "[5/5] Checking vector index status..."
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    "SHOW INDEXES YIELD name, state WHERE name IN ['document_embeddings', 'concept_embeddings'] RETURN name, state"
echo ""

echo "========================================="
echo "✓ Neo4j initialization completed"
echo "========================================="
