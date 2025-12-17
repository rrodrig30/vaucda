# VAUCDA Quick Start Guide

**Fast track to get VAUCDA backend running in under 10 minutes**

---

## Prerequisites Check

```bash
# Verify installations
python3.11 --version  # Should be 3.11+
docker --version      # Should be 20.10+
docker-compose --version  # Should be 2.0+
```

---

## Option 1: Docker Deployment (Recommended)

### Step 1: Configure Environment

```bash
cd /home/gulab/PythonProjects/VAUCDA

# Create .env file (required)
cat > .env << 'EOF'
# Security - CHANGE THESE!
JWT_SECRET_KEY=replace_with_secure_random_32plus_character_string
NEO4J_PASSWORD=secure_neo4j_password_here
OPENEVIDENCE_ENCRYPTION_KEY=replace_with_32_character_encryption_key

# Database
NEO4J_USER=neo4j
SECRET_KEY=another_secure_random_string

# API Keys (optional)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Environment
APP_ENV=development
DEBUG=true
EOF

# CRITICAL: Edit .env and change the placeholder values!
nano .env
```

### Step 2: Start All Services

```bash
# Start everything
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f vaucda-api
```

### Step 3: Initialize Database

```bash
# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Create SQLite tables
docker exec vaucda-api alembic upgrade head

# Create admin user
docker exec -it vaucda-api python scripts/create_admin_user.py
```

### Step 4: Verify Installation

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Should return:
# {"status":"healthy","app":"VAUCDA","version":"1.0.0",...}

# API documentation
open http://localhost:8000/api/docs
```

**Success!** Backend is now running at http://localhost:8000

---

## Option 2: Local Development Setup

### Step 1: Create Virtual Environment

```bash
cd /home/gulab/PythonProjects/VAUCDA/backend

# Create venv
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env

# REQUIRED changes:
# - JWT_SECRET_KEY (32+ random characters)
# - NEO4J_PASSWORD
# - OPENEVIDENCE_ENCRYPTION_KEY
```

### Step 3: Start External Services

```bash
# Start Neo4j, Redis, Ollama via Docker
docker-compose up -d neo4j redis ollama

# Wait for services (30 seconds)
sleep 30
```

### Step 4: Initialize Database

```bash
# Create SQLite tables
alembic upgrade head

# Or run initialization script
bash scripts/create_initial_migration.sh
```

### Step 5: Pull Ollama Models

```bash
# Pull required models (this takes 5-15 minutes)
docker exec -it vaucda-ollama ollama pull llama3.1:8b
docker exec -it vaucda-ollama ollama pull nomic-embed-text

# Verify
docker exec -it vaucda-ollama ollama list
```

### Step 6: Run Application

```bash
# Development mode (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use Python directly
python app/main.py
```

### Step 7: Create Admin User

```bash
# In another terminal (with venv activated)
python scripts/create_admin_user.py
```

**Success!** API is running at http://localhost:8000

---

## Testing the API

### 1. Register a User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@va.gov",
    "password": "SecurePass123",
    "full_name": "Dr. Test User"
  }'
```

### 2. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@va.gov",
    "password": "SecurePass123"
  }'

# Copy the access_token from response
```

### 3. Get User Info

```bash
# Replace YOUR_TOKEN with the access_token from login
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/auth/me
```

### 4. Check Detailed Health

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/health/detailed
```

---

## Common Issues & Solutions

### Issue: "JWT_SECRET_KEY must be changed from default"

**Solution:**
```bash
# Generate a secure key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Add to .env
echo "JWT_SECRET_KEY=YOUR_GENERATED_KEY" >> .env
```

### Issue: "Connection refused" when connecting to Neo4j

**Solution:**
```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check Neo4j logs
docker logs vaucda-neo4j

# Verify password in .env matches
docker exec -it vaucda-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
```

### Issue: Ollama models not found

**Solution:**
```bash
# Check Ollama is running
docker ps | grep ollama

# Pull missing models
docker exec -it vaucda-ollama ollama pull llama3.1:8b
docker exec -it vaucda-ollama ollama pull nomic-embed-text

# List available models
docker exec -it vaucda-ollama ollama list
```

### Issue: SQLite database locked

**Solution:**
```bash
# Stop all processes using database
docker-compose down

# Remove database file
rm backend/data/vaucda.db

# Recreate database
docker-compose up -d
docker exec vaucda-api alembic upgrade head
```

---

## Next Steps

1. **Explore API Documentation**
   - Open http://localhost:8000/api/docs
   - Test endpoints interactively

2. **Implement Remaining Features**
   - See BACKEND_IMPLEMENTATION_SUMMARY.md for status
   - Follow IMPLEMENTATION_ROADMAP.md for phases

3. **Configure for Production**
   - Set DEBUG=false
   - Configure HTTPS/TLS
   - Set up monitoring
   - Configure backups

4. **Run Tests**
   ```bash
   pytest backend/tests/
   ```

---

## Useful Commands

```bash
# View all logs
docker-compose logs -f

# Stop all services
docker-compose down

# Restart specific service
docker-compose restart vaucda-api

# Access API container
docker exec -it vaucda-api bash

# Run Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# Create database migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

---

## Support Resources

- **Backend README:** `/home/gulab/PythonProjects/VAUCDA/backend/README.md`
- **Implementation Summary:** `/home/gulab/PythonProjects/VAUCDA/BACKEND_IMPLEMENTATION_SUMMARY.md`
- **Architecture:** `/home/gulab/PythonProjects/VAUCDA/ARCHITECTURE.md`
- **API Specification:** `/home/gulab/PythonProjects/VAUCDA/API_SPECIFICATION.md`

---

**Last Updated:** November 29, 2025
