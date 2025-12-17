#!/bin/bash
# Backup Neo4j database for VAUCDA
# Creates full backup of Neo4j data directory

set -e

echo "========================================="
echo "VAUCDA Neo4j Backup"
echo "========================================="

# Configuration
BACKUP_DIR=${NEO4J_BACKUP_DIR:-"/backups/neo4j"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="vaucda_neo4j_${TIMESTAMP}"
RETENTION_DAYS=${NEO4J_BACKUP_RETENTION_DAYS:-30}

echo ""
echo "Configuration:"
echo "  Backup Directory: $BACKUP_DIR"
echo "  Backup Name: $BACKUP_NAME"
echo "  Retention: $RETENTION_DAYS days"
echo ""

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Stop Neo4j container
echo "[1/5] Stopping Neo4j container..."
if docker-compose -f /home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml stop neo4j; then
    echo "✓ Neo4j stopped"
else
    echo "✗ ERROR: Failed to stop Neo4j"
    exit 1
fi

# Create backup archive
echo ""
echo "[2/5] Creating backup archive..."
if tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C /var/lib/neo4j data logs; then
    echo "✓ Backup created: ${BACKUP_NAME}.tar.gz"
else
    echo "✗ ERROR: Backup creation failed"
    docker-compose -f /home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml start neo4j
    exit 1
fi

# Start Neo4j container
echo ""
echo "[3/5] Starting Neo4j container..."
if docker-compose -f /home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml start neo4j; then
    echo "✓ Neo4j started"
else
    echo "✗ ERROR: Failed to start Neo4j"
    exit 1
fi

# Wait for Neo4j to be ready
echo ""
echo "[4/5] Waiting for Neo4j to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-changeme123}" "RETURN 1" > /dev/null 2>&1; then
        echo "✓ Neo4j is ready"
        break
    fi

    attempt=$((attempt + 1))
    sleep 2
done

# Verify backup file
echo ""
echo "[5/5] Verifying backup..."
if [ -f "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" ]; then
    BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
    echo "✓ Backup verified"
    echo "  Size: $BACKUP_SIZE"
else
    echo "✗ ERROR: Backup file not found"
    exit 1
fi

# Cleanup old backups
echo ""
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "vaucda_neo4j_*.tar.gz" -mtime +$RETENTION_DAYS -delete
REMAINING_BACKUPS=$(ls -1 "$BACKUP_DIR"/vaucda_neo4j_*.tar.gz 2>/dev/null | wc -l)
echo "✓ Remaining backups: $REMAINING_BACKUPS"

echo ""
echo "========================================="
echo "✓ Backup completed successfully"
echo "  Location: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo "========================================="
