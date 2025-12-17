#!/bin/bash

################################################################################
# VAUCDA Database Initialization Script
################################################################################
# This script initializes all databases and creates required schemas
#
# Prerequisites:
#   - Docker and docker-compose installed
#   - Services already running (docker-compose up -d)
#   - Environment variables loaded from .env
#
# Usage:
#   bash scripts/init_databases.sh
################################################################################

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
DOCKER_COMPOSE="docker-compose -f $PROJECT_DIR/docker-compose.yml"

# Load environment variables
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
else
    echo -e "${RED}ERROR: .env file not found${NC}"
    exit 1
fi

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if services are running
check_services() {
    log_info "Checking if services are running..."

    # Check Neo4j
    if ! docker ps | grep -q vaucda-neo4j; then
        log_error "Neo4j service is not running"
        return 1
    fi

    # Check Redis
    if ! docker ps | grep -q vaucda-redis; then
        log_error "Redis service is not running"
        return 1
    fi

    # Check Ollama
    if ! docker ps | grep -q vaucda-ollama; then
        log_error "Ollama service is not running"
        return 1
    fi

    log_success "All required services are running"
    return 0
}

# Wait for Neo4j to be healthy
wait_for_neo4j() {
    log_info "Waiting for Neo4j to be ready..."

    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if docker exec vaucda-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" > /dev/null 2>&1; then
            log_success "Neo4j is ready"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    log_error "Neo4j failed to start after $((max_attempts * 2)) seconds"
    return 1
}

# Wait for Redis to be healthy
wait_for_redis() {
    log_info "Waiting for Redis to be ready..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if docker exec vaucda-redis redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
            log_success "Redis is ready"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 1
    done

    log_error "Redis failed to start after $((max_attempts)) seconds"
    return 1
}

# Wait for Ollama to be healthy
wait_for_ollama() {
    log_info "Waiting for Ollama to be ready..."

    local max_attempts=120
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            log_success "Ollama is ready"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    log_warning "Ollama took longer than expected but continuing..."
    return 0
}

# Initialize Neo4j schema
initialize_neo4j_schema() {
    log_info "Initializing Neo4j schema..."

    # Create constraints and indexes
    docker exec vaucda-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" << 'EOF'
// Create constraints
CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS
FOR (e:Evidence) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT document_chunk_id_unique IF NOT EXISTS
FOR (dc:DocumentChunk) REQUIRE dc.id IS UNIQUE;

// Create indexes for performance
CREATE INDEX document_title IF NOT EXISTS
FOR (d:Document) ON (d.title);

CREATE INDEX document_chunk_content IF NOT EXISTS
FOR (dc:DocumentChunk) ON (dc.content);

CREATE INDEX evidence_source IF NOT EXISTS
FOR (e:Evidence) ON (e.source);

// Return confirmation
RETURN "Neo4j schema initialized successfully" AS status;
EOF

    local status=$?
    if [ $status -eq 0 ]; then
        log_success "Neo4j schema initialized"
        return 0
    else
        log_error "Failed to initialize Neo4j schema"
        return 1
    fi
}

# Initialize Redis data structures
initialize_redis() {
    log_info "Initializing Redis data structures..."

    # Create Redis keys for application configuration
    docker exec vaucda-redis redis-cli -a "$REDIS_PASSWORD" << 'EOF'
// Set cache keys
SET vaucda:config:initialized "true"
SET vaucda:config:version "1.0.0"
SET vaucda:config:init_time "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

// Create rate limit tracking
HSET vaucda:rate_limits anonymous 0
HSET vaucda:rate_limits authenticated 0
HSET vaucda:rate_limits admin 0

// Return confirmation
ECHO "Redis initialized successfully"
EOF

    log_success "Redis initialized"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."

    # Check if API container exists
    if ! docker ps -a | grep -q vaucda-api; then
        log_warning "API container not running, skipping migrations"
        return 0
    fi

    # Run Alembic migrations
    if docker exec vaucda-api alembic upgrade head > /dev/null 2>&1; then
        log_success "Database migrations completed"
        return 0
    else
        log_warning "Could not run migrations - API container may not be running yet"
        return 0
    fi
}

# Create admin user (if script exists)
create_admin_user() {
    log_info "Creating admin user..."

    if [ -f "$SCRIPTS_DIR/create_admin.py" ]; then
        if docker exec vaucda-api python scripts/create_admin.py > /dev/null 2>&1; then
            log_success "Admin user created"
        else
            log_warning "Could not create admin user - API setup may be incomplete"
        fi
    else
        log_warning "Admin user creation script not found"
    fi
}

# Verify database connectivity
verify_connectivity() {
    log_info "Verifying database connectivity..."

    # Test Neo4j
    if docker exec vaucda-neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" > /dev/null 2>&1; then
        log_success "Neo4j connectivity verified"
    else
        log_error "Neo4j connectivity check failed"
        return 1
    fi

    # Test Redis
    if docker exec vaucda-redis redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
        log_success "Redis connectivity verified"
    else
        log_error "Redis connectivity check failed"
        return 1
    fi

    log_success "All database connectivity verified"
    return 0
}

# Main execution
main() {
    echo ""
    log_info "Starting VAUCDA Database Initialization"
    echo ""

    # Check services
    if ! check_services; then
        log_error "Services not running. Start them with: docker-compose up -d"
        exit 1
    fi

    echo ""

    # Wait for services to be healthy
    if ! wait_for_neo4j; then
        exit 1
    fi

    echo ""

    if ! wait_for_redis; then
        exit 1
    fi

    echo ""

    if ! wait_for_ollama; then
        log_warning "Ollama may take longer to initialize models"
    fi

    echo ""

    # Initialize Neo4j
    if ! initialize_neo4j_schema; then
        log_warning "Neo4j schema initialization had issues, continuing..."
    fi

    echo ""

    # Initialize Redis
    if ! initialize_redis; then
        log_warning "Redis initialization had issues, continuing..."
    fi

    echo ""

    # Run migrations
    run_migrations

    echo ""

    # Create admin user
    create_admin_user

    echo ""

    # Verify connectivity
    if ! verify_connectivity; then
        log_error "Database connectivity verification failed"
        exit 1
    fi

    echo ""
    log_success "Database initialization complete!"
    echo ""
    echo "Next steps:"
    echo "1. Verify all services are healthy: docker-compose ps"
    echo "2. Check logs: docker-compose logs -f"
    echo "3. Access the application: http://localhost:3000"
    echo ""
}

# Run main function
main
