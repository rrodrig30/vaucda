# VAUCDA Deployment Guide

**Complete Production Deployment Documentation for VA Urology Clinical Documentation Assistant**

Version: 1.0.0
Last Updated: 2025-11-29
Status: Production Ready

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Setup](#database-setup)
4. [Service Deployment](#service-deployment)
5. [Initial Data Load](#initial-data-load)
6. [Frontend Deployment](#frontend-deployment)
7. [Production Checklist](#production-checklist)
8. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### Required Software

#### Docker & Docker Compose
```bash
# Verify Docker installation
docker --version
# Required: Docker 20.10+

docker-compose --version
# Required: Docker Compose 2.0+
```

**Installation (Ubuntu/Debian):**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

#### Node.js (for frontend development)
```bash
# Required: Node.js 18+
node --version

# Installation
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

#### Python (for backend development)
```bash
# Required: Python 3.11+
python3 --version

# Installation (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip
```

#### Git
```bash
# Required for version control
git --version

# Installation
sudo apt-get install -y git
```

### System Requirements

#### Minimum Requirements
- **CPU**: 4 cores
- **RAM**: 8GB
- **Disk**: 50GB free space
- **OS**: Ubuntu 20.04+, RHEL 8+, or compatible Linux

#### Recommended Requirements (Production)
- **CPU**: 8+ cores (16+ for high load)
- **RAM**: 16GB (32GB+ for high load)
- **Disk**: 100GB+ SSD
- **GPU**: NVIDIA GPU with 16GB+ VRAM (for Ollama LLMs)
- **Network**: 1Gbps+

#### GPU Requirements (Optional but Recommended)

For optimal Ollama performance:
```bash
# Verify NVIDIA GPU
nvidia-smi

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Network Ports

Ensure the following ports are available:

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Frontend | 3000 | HTTP | React application |
| Backend API | 8000 | HTTP/WS | FastAPI server |
| Neo4j HTTP | 7474 | HTTP | Neo4j browser |
| Neo4j Bolt | 7687 | Bolt | Neo4j database |
| Ollama | 11434 | HTTP | LLM inference |
| Redis | 6379 | TCP | Cache/queue |
| Nginx | 80 | HTTP | Reverse proxy |
| Nginx SSL | 443 | HTTPS | Secure proxy |

---

## 2. Environment Setup

### Clone Repository

```bash
# Clone the repository
git clone https://github.com/va/vaucda.git
cd vaucda

# Or if using internal VA GitLab
git clone https://gitlab.va.gov/urology/vaucda.git
cd vaucda
```

### Backend Environment Configuration

```bash
# Copy example environment file
cp backend/.env.example backend/.env

# Edit configuration
nano backend/.env
```

**Critical Configuration Items:**

#### Application Settings
```bash
APP_NAME=VAUCDA
APP_VERSION=1.0.0
DEBUG=false                    # MUST be false in production
LOG_LEVEL=INFO                 # Use INFO or WARNING in production
ENVIRONMENT=production
```

#### Server Configuration
```bash
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4                  # Adjust based on CPU cores (2x cores)
```

#### Database Configuration - Neo4j
```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_THIS_TO_SECURE_PASSWORD_MIN_16_CHARS
NEO4J_DATABASE=neo4j
NEO4J_MAX_CONNECTION_POOL_SIZE=100
NEO4J_CONNECTION_TIMEOUT=60
```

#### Database Configuration - Redis
```bash
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=50
REDIS_DECODE_RESPONSES=true
```

#### Security Configuration - JWT

**CRITICAL: Generate secure random keys**

```bash
# Generate JWT secret key (32+ characters)
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"

# Copy output to .env file
JWT_SECRET_KEY=<generated_key_here>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

#### Security Configuration - Password Hashing
```bash
PASSWORD_HASH_ALGORITHM=bcrypt
PASSWORD_HASH_ROUNDS=12        # Higher = more secure but slower
```

#### Security Configuration - CORS
```bash
# Production CORS settings
CORS_ORIGINS=["https://vaucda.va.gov","https://api.vaucda.va.gov"]
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE","OPTIONS"]
CORS_ALLOW_HEADERS=["*"]
```

#### LLM Configuration - Ollama (Primary)
```bash
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_DEFAULT_MODEL=llama3.1:8b          # Default model
OLLAMA_TIMEOUT=120
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

#### LLM Configuration - Anthropic (Optional)
```bash
# Leave blank if not using
ANTHROPIC_API_KEY=sk-ant-xxxxx
ANTHROPIC_DEFAULT_MODEL=claude-3-5-sonnet-20250101
ANTHROPIC_MAX_TOKENS=8096
ANTHROPIC_TIMEOUT=60
```

#### LLM Configuration - OpenAI (Optional)
```bash
# Leave blank if not using
OPENAI_API_KEY=sk-xxxxx
OPENAI_DEFAULT_MODEL=gpt-4o
OPENAI_MAX_TOKENS=8096
OPENAI_TIMEOUT=60
```

#### RAG Configuration
```bash
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=768
VECTOR_SEARCH_TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

#### Rate Limiting
```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_ANONYMOUS=10        # Requests per minute
RATE_LIMIT_AUTHENTICATED=100   # Requests per minute
RATE_LIMIT_ADMIN=1000          # Requests per minute
```

#### OpenEvidence Encryption
```bash
# Generate encryption key for stored credentials
python3 -c "from cryptography.fernet import Fernet; print('OPENEVIDENCE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# Copy output to .env file
OPENEVIDENCE_ENCRYPTION_KEY=<generated_key_here>
```

### Frontend Environment Configuration

```bash
# Copy example environment file
cp frontend/.env.example frontend/.env

# Edit configuration
nano frontend/.env
```

**Frontend Configuration:**

```bash
# API Configuration
VITE_API_BASE_URL=https://api.vaucda.va.gov     # Production URL
VITE_WS_URL=wss://api.vaucda.va.gov             # WebSocket URL

# Feature Flags
VITE_ENABLE_DEVTOOLS=false                      # Disable in production
```

### Root Environment Configuration

Create a `.env` file in the root directory for Docker Compose:

```bash
# Copy from backend or create new
cp backend/.env .env

# Additional Docker-specific settings
nano .env
```

**Add Docker-specific variables:**
```bash
# Docker Configuration
COMPOSE_PROJECT_NAME=vaucda
DOCKER_BUILDKIT=1
COMPOSE_DOCKER_CLI_BUILD=1

# Service Ports
API_PORT=8000
FRONTEND_PORT=3000

# GPU Configuration (if available)
GPU_DEVICE_COUNT=1

# Ollama Models to Pull
OLLAMA_NOTE_GENERATION_MODEL=llama3.1:70b
OLLAMA_CLINICAL_EXTRACTION_MODEL=llama3.1:8b
OLLAMA_CALCULATOR_ASSIST_MODEL=phi3:medium
```

### Verify Configuration

```bash
# Verify .env files exist
ls -la backend/.env frontend/.env .env

# Verify critical secrets are set (should NOT show default values)
grep "CHANGE_THIS" backend/.env
# Should return no results if properly configured

# Verify JWT key is set
grep "JWT_SECRET_KEY" backend/.env | wc -c
# Should be > 50 characters
```

---

## 3. Database Setup

### Neo4j Initialization

#### Start Neo4j Container

```bash
# Start only Neo4j service first
docker-compose up -d neo4j

# Wait for Neo4j to be healthy (may take 60 seconds)
docker-compose ps neo4j

# Check logs
docker-compose logs neo4j
```

#### Create Vector Indexes

```bash
# Access Neo4j Cypher Shell
docker exec -it vaucda-neo4j cypher-shell -u neo4j -p <your_password>

# Or execute directly
docker exec vaucda-neo4j cypher-shell -u neo4j -p <your_password> << 'EOF'

// Create Document nodes index
CREATE INDEX document_source_idx IF NOT EXISTS FOR (d:Document) ON (d.source);
CREATE INDEX document_category_idx IF NOT EXISTS FOR (d:Document) ON (d.category);

// Create vector index for embeddings
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document)
ON d.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};

// Create Chunk nodes index
CREATE INDEX chunk_document_idx IF NOT EXISTS FOR (c:Chunk) ON (c.document_id);

// Create vector index for chunk embeddings
CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
FOR (c:Chunk)
ON c.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};

// Create User nodes index
CREATE INDEX user_email_idx IF NOT EXISTS FOR (u:User) ON (u.email);
CREATE INDEX user_username_idx IF NOT EXISTS FOR (u:User) ON (u.username);

// Create Session nodes index
CREATE INDEX session_user_idx IF NOT EXISTS FOR (s:Session) ON (s.user_id);
CREATE INDEX session_active_idx IF NOT EXISTS FOR (s:Session) ON (s.is_active);

// Verify indexes
SHOW INDEXES;

EOF
```

#### Verify Neo4j Setup

```bash
# Verify indexes were created
docker exec vaucda-neo4j cypher-shell -u neo4j -p <your_password> "SHOW INDEXES;"

# Test connection from backend
docker run --rm --network vaucda_vaucda-network \
  -e NEO4J_URI=bolt://neo4j:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=<your_password> \
  python:3.11 python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j', '<your_password>'))
with driver.session() as session:
    result = session.run('RETURN 1 AS num')
    print('Neo4j connection successful:', result.single()['num'])
driver.close()
"
```

### SQLite Database Setup

SQLite database is automatically created on first run. To pre-initialize:

```bash
# Create data directory
mkdir -p data

# Database will be created at: data/vaucda.db
# Permissions are set automatically by Docker
```

### Redis Setup

```bash
# Start Redis service
docker-compose up -d redis

# Verify Redis is healthy
docker-compose ps redis

# Test Redis connection
docker exec vaucda-redis redis-cli ping
# Should return: PONG

# Test from backend container (after it's running)
docker exec vaucda-api python3 -c "
import redis
r = redis.from_url('redis://redis:6379/0')
r.set('test', 'success')
print('Redis test:', r.get('test').decode())
r.delete('test')
"
```

### Running Alembic Migrations

```bash
# Start backend service
docker-compose up -d vaucda-api

# Run migrations to create SQLite tables
docker exec vaucda-api alembic upgrade head

# Verify migrations
docker exec vaucda-api alembic current

# Check SQLite database
docker exec vaucda-api python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/vaucda.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
print('Tables:', [row[0] for row in cursor.fetchall()])
conn.close()
"
```

---

## 4. Service Deployment

### Docker Compose Deployment (Recommended)

#### Build All Services

```bash
# Build all images
docker-compose build

# Or build with no cache (if issues occur)
docker-compose build --no-cache
```

#### Start All Services

```bash
# Start all services in detached mode
docker-compose up -d

# Or start with logs visible (for debugging)
docker-compose up

# Monitor startup
docker-compose logs -f
```

#### Verify All Services Are Healthy

```bash
# Check service status
docker-compose ps

# All services should show "healthy" or "running"
# Example output:
#   NAME                    STATUS
#   vaucda-api              Up (healthy)
#   vaucda-frontend         Up
#   vaucda-neo4j            Up (healthy)
#   vaucda-ollama           Up
#   vaucda-redis            Up (healthy)
#   vaucda-celery-worker    Up
#   vaucda-celery-beat      Up

# Check individual service health
curl http://localhost:8000/api/v1/health
# Should return: {"status":"healthy","timestamp":"...","services":{...}}

curl http://localhost:3000
# Should return: HTML content

# Check Neo4j browser
curl http://localhost:7474
# Should return: Neo4j browser interface
```

#### Pull Ollama Models

**This is a critical step and may take 30-60 minutes depending on network speed.**

```bash
# Pull Llama 3.1 70B for high-quality note generation
docker exec vaucda-ollama ollama pull llama3.1:70b
# Size: ~40GB

# Pull Llama 3.1 8B for fast clinical extraction
docker exec vaucda-ollama ollama pull llama3.1:8b
# Size: ~4.7GB

# Pull Phi-3 Medium for calculator assistance
docker exec vaucda-ollama ollama pull phi3:medium
# Size: ~7.9GB

# Pull Mistral 7B (general purpose)
docker exec vaucda-ollama ollama pull mistral:7b
# Size: ~4.1GB

# Pull embedding model
docker exec vaucda-ollama ollama pull nomic-embed-text
# Size: ~274MB

# Verify models are available
docker exec vaucda-ollama ollama list
```

#### Configure Celery Workers

```bash
# Verify Celery worker is running
docker-compose logs celery-worker

# Should see: "celery@<hostname> ready"

# Verify Celery beat scheduler is running
docker-compose logs celery-beat

# Test Celery task
docker exec vaucda-api python3 -c "
from backend.tasks.celery_app import celery_app
from backend.tasks.example_tasks import test_task
result = test_task.delay('test')
print('Task ID:', result.id)
print('Task status:', result.status)
"
```

### Manual Deployment (Without Docker)

#### Backend Manual Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Set environment variables
export $(cat .env | xargs)

# Run Alembic migrations
alembic upgrade head

# Start Uvicorn server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# In separate terminal, start Celery worker
celery -A backend.tasks.celery_app worker --loglevel=info --concurrency=4

# In another terminal, start Celery beat
celery -A backend.tasks.celery_app beat --loglevel=info
```

#### Frontend Manual Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Serve with production server (or use nginx)
npm run preview

# Or use serve
npx serve -s dist -l 3000
```

#### External Service Setup

You'll need to manually install and configure:
- Neo4j 5.15+
- Redis 7.2+
- Ollama (with GPU support)

---

## 5. Initial Data Load

### Create Admin User

```bash
# Run admin user creation script
docker exec -it vaucda-api python scripts/create_admin_user.py

# Follow prompts:
# Enter admin username: admin
# Enter admin email: admin@va.gov
# Enter admin password: <secure_password>
# Confirm password: <secure_password>

# Verify user was created
docker exec vaucda-api python3 -c "
from backend.database.sqlite_client import get_user_by_email
import asyncio
async def check():
    user = await get_user_by_email('admin@va.gov')
    print('Admin user exists:', user is not None)
asyncio.run(check())
"
```

### Ingest Clinical Guidelines (Optional)

```bash
# Create documents directory
mkdir -p data/documents

# Copy your clinical guideline PDFs/documents
cp /path/to/nccn_prostate.pdf data/documents/
cp /path/to/aua_guidelines.pdf data/documents/
cp /path/to/eau_guidelines.pdf data/documents/

# Run document ingestion script
docker exec vaucda-api python scripts/ingest_documents.py \
  --input-dir /app/data/documents \
  --chunk-size 1000 \
  --chunk-overlap 200

# This will:
# 1. Extract text from PDFs
# 2. Chunk documents into smaller pieces
# 3. Generate embeddings using sentence-transformers
# 4. Store in Neo4j with vector indexes

# Verify documents were ingested
docker exec vaucda-neo4j cypher-shell -u neo4j -p <your_password> \
  "MATCH (d:Document) RETURN count(d) AS document_count;"

docker exec vaucda-neo4j cypher-shell -u neo4j -p <your_password> \
  "MATCH (c:Chunk) RETURN count(c) AS chunk_count;"
```

### Verify Vector Indexes

```bash
# Test vector search
docker exec vaucda-api python3 << 'EOF'
from backend.rag.neo4j_vector_store import Neo4jVectorStore
from backend.rag.embeddings import get_embedding_model
import asyncio

async def test_search():
    store = Neo4jVectorStore()
    embedding_model = get_embedding_model()

    query = "What are the treatment options for high-risk prostate cancer?"
    query_embedding = embedding_model.encode(query).tolist()

    results = await store.similarity_search(query_embedding, k=5)
    print(f"Found {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"{i}. Score: {result['score']:.3f}, Source: {result['source']}")

asyncio.run(test_search())
EOF
```

### Test RAG Pipeline

```bash
# End-to-end RAG test
docker exec vaucda-api python3 << 'EOF'
from backend.rag.rag_pipeline import RAGPipeline
import asyncio

async def test_rag():
    pipeline = RAGPipeline()

    query = "What is the recommended PSA screening interval for low-risk patients?"
    results = await pipeline.search(query, category="prostate_cancer", k=3)

    print(f"Query: {query}")
    print(f"Results: {len(results)}")
    for result in results:
        print(f"  - {result['source']}: {result['content'][:100]}...")

asyncio.run(test_rag())
EOF
```

### Test Calculator Endpoints

```bash
# Test CAPRA Score calculator
curl -X POST http://localhost:8000/api/v1/calculators/capra_score/calculate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -d '{
    "inputs": {
      "age": 65,
      "psa": 8.5,
      "gleason_primary": 3,
      "gleason_secondary": 4,
      "clinical_stage": "T2a",
      "percent_positive_cores": 45.0
    }
  }'

# Should return CAPRA score and risk stratification
```

---

## 6. Frontend Deployment

### Development Build

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Access at http://localhost:5173
```

### Production Build

```bash
cd frontend

# Build for production
npm run build

# This creates optimized bundle in dist/

# Preview production build
npm run preview
```

### Nginx Configuration

Create `/etc/nginx/sites-available/vaucda`:

```nginx
# VAUCDA Nginx Configuration
server {
    listen 80;
    server_name vaucda.va.gov;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vaucda.va.gov;

    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/vaucda.crt;
    ssl_certificate_key /etc/nginx/ssl/vaucda.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' https:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;

    # Frontend (React)
    location / {
        root /var/www/vaucda/frontend/dist;
        try_files $uri $uri/ /index.html;

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 120s;
    }

    # WebSocket for streaming
    location /ws/ {
        proxy_pass http://localhost:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
    }

    # Logging
    access_log /var/log/nginx/vaucda_access.log;
    error_log /var/log/nginx/vaucda_error.log;
}
```

Enable configuration:
```bash
sudo ln -s /etc/nginx/sites-available/vaucda /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### HTTPS/SSL Setup

#### Using Let's Encrypt (Recommended)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d vaucda.va.gov

# Certificates auto-renew
sudo certbot renew --dry-run
```

#### Using VA Certificates

```bash
# Copy VA-provided certificates
sudo mkdir -p /etc/nginx/ssl
sudo cp vaucda.crt /etc/nginx/ssl/
sudo cp vaucda.key /etc/nginx/ssl/
sudo chmod 600 /etc/nginx/ssl/vaucda.key
sudo chown root:root /etc/nginx/ssl/*
```

---

## 7. Production Checklist

### Pre-Deployment Verification

```bash
# 1. Check all containers are running
docker-compose ps | grep -v "Up"
# Should return no results

# 2. Verify health endpoints
curl -f http://localhost:8000/api/v1/health || echo "API health check failed"
curl -f http://localhost:3000 || echo "Frontend check failed"

# 3. Check logs for errors
docker-compose logs --tail=100 | grep -i error
docker-compose logs --tail=100 | grep -i exception

# 4. Verify database connections
docker exec vaucda-api python3 -c "
from backend.database.neo4j_client import Neo4jClient
from backend.database.sqlite_client import get_db
from backend.database.redis_client import get_redis
import asyncio

async def check_connections():
    # Neo4j
    neo4j = Neo4jClient()
    print('Neo4j:', 'OK' if await neo4j.verify_connectivity() else 'FAILED')

    # Redis
    redis = await get_redis()
    print('Redis:', 'OK' if await redis.ping() else 'FAILED')

    # SQLite is file-based, just check file exists
    import os
    print('SQLite:', 'OK' if os.path.exists('/app/data/vaucda.db') else 'FAILED')

asyncio.run(check_connections())
"

# 5. Test authentication
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@va.gov","password":"<your_password>"}'
# Should return JWT token

# 6. Verify Ollama models
docker exec vaucda-ollama ollama list | grep -E "llama3.1|phi3|nomic-embed"
# Should show all required models

# 7. Check disk space
df -h
# Ensure >20GB free

# 8. Check memory usage
free -h
docker stats --no-stream
```

### Security Hardening

```bash
# 1. Verify no default passwords in use
grep -r "changeme\|password\|CHANGE_THIS" backend/.env
# Should return no results

# 2. Check file permissions
ls -la backend/.env
# Should be: -rw------- (600) or -rw-r----- (640)

# 3. Verify HTTPS is enforced
curl -I http://vaucda.va.gov
# Should return 301 redirect to HTTPS

# 4. Check security headers
curl -I https://vaucda.va.gov
# Should include: X-Frame-Options, X-Content-Type-Options, etc.

# 5. Verify rate limiting
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/health
done
# Should show 429 (Too Many Requests) after 10 requests
```

### Performance Tuning

```bash
# 1. Optimize Ollama for GPU
docker exec vaucda-ollama nvidia-smi
# Verify GPU is detected

# 2. Configure Redis maxmemory
docker exec vaucda-redis redis-cli CONFIG SET maxmemory 2gb
docker exec vaucda-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# 3. Tune Neo4j memory (in docker-compose.yml)
# NEO4J_dbms_memory_heap_max__size=4G (for production)
# NEO4J_dbms_memory_pagecache_size=2G

# 4. Scale workers based on load
# In .env: API_WORKERS=<num_cpu_cores * 2>
# In .env: CELERY_WORKER_CONCURRENCY=<num_cpu_cores>
```

---

## 8. Troubleshooting

### Common Issues

#### Issue: Container fails to start

```bash
# Check logs
docker-compose logs <service_name>

# Common causes:
# 1. Port already in use
sudo netstat -tulpn | grep <port>
# Kill process or change port

# 2. Missing environment variables
docker-compose config | grep -A5 environment

# 3. Insufficient disk space
df -h
docker system prune -a
```

#### Issue: Neo4j connection refused

```bash
# Verify Neo4j is running
docker-compose ps neo4j

# Check Neo4j logs
docker-compose logs neo4j | tail -50

# Test connection
docker exec vaucda-neo4j cypher-shell -u neo4j -p <password> "RETURN 1;"

# Restart Neo4j
docker-compose restart neo4j
docker-compose logs -f neo4j
```

#### Issue: Ollama model download fails

```bash
# Check disk space (models are large)
df -h

# Check Ollama logs
docker-compose logs ollama

# Manually pull models
docker exec -it vaucda-ollama ollama pull llama3.1:8b

# Verify models
docker exec vaucda-ollama ollama list
```

#### Issue: Frontend can't connect to API

```bash
# Check CORS configuration in backend/.env
grep CORS backend/.env

# Verify API is accessible
curl http://localhost:8000/api/v1/health

# Check frontend .env
cat frontend/.env
# VITE_API_BASE_URL should match API URL

# Rebuild frontend
cd frontend
npm run build
```

#### Issue: Authentication fails

```bash
# Verify JWT secret is set
grep JWT_SECRET_KEY backend/.env

# Check user exists
docker exec vaucda-api python3 -c "
from backend.database.sqlite_client import get_user_by_email
import asyncio
async def check():
    user = await get_user_by_email('admin@va.gov')
    print('User exists:', user is not None)
asyncio.run(check())
"

# Reset admin password
docker exec -it vaucda-api python scripts/create_admin_user.py
```

#### Issue: High memory usage

```bash
# Check container stats
docker stats

# Common causes:
# 1. Ollama models loaded in memory
# - Models stay loaded based on OLLAMA_KEEP_ALIVE setting

# 2. Neo4j heap size too large
# - Adjust in docker-compose.yml

# 3. Too many API workers
# - Reduce API_WORKERS in .env

# Restart services
docker-compose restart
```

#### Issue: Slow note generation

```bash
# Check GPU availability
docker exec vaucda-ollama nvidia-smi

# If no GPU, use smaller models
# In backend/.env:
# OLLAMA_DEFAULT_MODEL=llama3.1:8b (instead of 70b)

# Monitor Ollama resource usage
docker stats vaucda-ollama

# Check Ollama logs for errors
docker-compose logs ollama | grep -i error
```

### Health Check Commands

```bash
# Full system health check script
cat > health_check.sh << 'EOF'
#!/bin/bash

echo "=== VAUCDA System Health Check ==="

# 1. Container status
echo -e "\n1. Container Status:"
docker-compose ps

# 2. API health
echo -e "\n2. API Health:"
curl -s http://localhost:8000/api/v1/health | jq .

# 3. Frontend
echo -e "\n3. Frontend:"
curl -s -o /dev/null -w "Status: %{http_code}\n" http://localhost:3000

# 4. Neo4j
echo -e "\n4. Neo4j:"
docker exec vaucda-neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN 'Connected' AS status;" 2>&1 | tail -1

# 5. Redis
echo -e "\n5. Redis:"
docker exec vaucda-redis redis-cli ping

# 6. Ollama
echo -e "\n6. Ollama Models:"
docker exec vaucda-ollama ollama list

# 7. Disk space
echo -e "\n7. Disk Space:"
df -h | grep -E "Filesystem|/dev/sda"

# 8. Memory
echo -e "\n8. Memory Usage:"
free -h

# 9. Docker resource usage
echo -e "\n9. Docker Resource Usage:"
docker stats --no-stream

echo -e "\n=== Health Check Complete ==="
EOF

chmod +x health_check.sh
./health_check.sh
```

### Log Collection

```bash
# Collect all logs for troubleshooting
mkdir -p logs/$(date +%Y%m%d_%H%M%S)
docker-compose logs > logs/$(date +%Y%m%d_%H%M%S)/all_services.log
docker-compose logs vaucda-api > logs/$(date +%Y%m%d_%H%M%S)/api.log
docker-compose logs vaucda-frontend > logs/$(date +%Y%m%d_%H%M%S)/frontend.log
docker-compose logs neo4j > logs/$(date +%Y%m%d_%H%M%S)/neo4j.log
docker-compose logs ollama > logs/$(date +%Y%m%d_%H%M%S)/ollama.log
docker-compose logs redis > logs/$(date +%Y%m%d_%H%M%S)/redis.log
docker-compose logs celery-worker > logs/$(date +%Y%m%d_%H%M%S)/celery_worker.log

# Compress logs
tar -czf logs_$(date +%Y%m%d_%H%M%S).tar.gz logs/$(date +%Y%m%d_%H%M%S)/
```

---

## Support

For issues or questions:

- **Email**: vaucda-support@va.gov
- **Internal Docs**: https://vaucda.va.gov/docs
- **Issue Tracker**: VA GitLab

---

## Appendix

### Useful Commands Reference

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart a service
docker-compose restart <service_name>

# View logs
docker-compose logs -f <service_name>

# Execute command in container
docker exec -it <container_name> <command>

# Scale workers
docker-compose up -d --scale celery-worker=4

# Rebuild a service
docker-compose build --no-cache <service_name>
docker-compose up -d <service_name>

# Clean up
docker-compose down -v  # Remove volumes (WARNING: deletes data)
docker system prune -a  # Clean up unused images
```

### Backup and Restore

```bash
# Backup Neo4j
docker exec vaucda-neo4j neo4j-admin dump --database=neo4j --to=/backups/neo4j-$(date +%Y%m%d).dump

# Backup SQLite
docker exec vaucda-api cp /app/data/vaucda.db /app/data/backups/vaucda-$(date +%Y%m%d).db

# Restore Neo4j
docker-compose stop neo4j
docker exec vaucda-neo4j neo4j-admin load --database=neo4j --from=/backups/neo4j-20250129.dump
docker-compose start neo4j

# Restore SQLite
docker exec vaucda-api cp /app/data/backups/vaucda-20250129.db /app/data/vaucda.db
docker-compose restart vaucda-api
```

---

**Deployment Guide Version**: 1.0.0
**Last Updated**: 2025-11-29
**Maintained by**: VA Urology VAUCDA Team
