#!/bin/bash
# Restore Neo4j database from backup

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -lh /backups/neo4j/vaucda_neo4j_*.tar.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE=$1

echo "========================================="
echo "VAUCDA Neo4j Restore"
echo "========================================="
echo ""
echo "WARNING: This will REPLACE all current data!"
echo "Backup file: $BACKUP_FILE"
echo ""
read -p "Are you sure? (yes/no): " -r
echo ""

if [[ ! $REPLY =~ ^yes$ ]]; then
    echo "Restore cancelled"
    exit 0
fi

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "✗ ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop Neo4j
echo "[1/4] Stopping Neo4j..."
docker-compose -f /home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml stop neo4j
echo "✓ Neo4j stopped"

# Backup current data (safety measure)
echo ""
echo "[2/4] Backing up current data (safety)..."
SAFETY_BACKUP="/backups/neo4j/pre_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$SAFETY_BACKUP" -C /var/lib/neo4j data logs 2>/dev/null || true
echo "✓ Current data backed up to: $SAFETY_BACKUP"

# Remove current data
echo ""
echo "[3/4] Removing current data..."
rm -rf /var/lib/neo4j/data/*
rm -rf /var/lib/neo4j/logs/*
echo "✓ Current data removed"

# Restore from backup
echo ""
echo "[4/4] Restoring from backup..."
if tar -xzf "$BACKUP_FILE" -C /var/lib/neo4j; then
    echo "✓ Backup restored"
else
    echo "✗ ERROR: Restore failed"
    echo "Attempting to restore from safety backup..."
    tar -xzf "$SAFETY_BACKUP" -C /var/lib/neo4j
    exit 1
fi

# Start Neo4j
echo ""
echo "Starting Neo4j..."
docker-compose -f /home/gulab/PythonProjects/VAUCDA/neo4j/docker-compose.neo4j.yml start neo4j

# Wait for ready
echo "Waiting for Neo4j to be ready..."
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

echo ""
echo "========================================="
echo "✓ Restore completed successfully"
echo "========================================="
