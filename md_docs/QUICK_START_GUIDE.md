# VAUCDA Quick Start Guide

**Get VAUCDA running in 5 minutes**

Version: 1.0.0
Last Updated: 2025-11-29

---

## Prerequisites

Before starting, ensure you have:
- Docker 20.10+ installed
- Docker Compose 2.0+ installed
- 8GB+ RAM available
- 50GB+ free disk space
- NVIDIA GPU (optional, recommended for better performance)

---

## 5-Minute Quick Start

### Step 1: Clone and Configure (1 minute)

```bash
# Clone repository
git clone https://github.com/va/vaucda.git
cd vaucda

# Or for VA internal:
# git clone https://gitlab.va.gov/urology/vaucda.git
# cd vaucda

# Copy environment templates
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

### Step 2: Generate Secrets (30 seconds)

```bash
# Generate JWT secret key
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))" >> backend/.env

# Generate encryption key for OpenEvidence
python3 -c "from cryptography.fernet import Fernet; print('OPENEVIDENCE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())" >> backend/.env

# Set Neo4j password (replace with your secure password)
echo "NEO4J_PASSWORD=your_secure_password_here" >> backend/.env
echo "NEO4J_USER=neo4j" >> backend/.env

# Copy backend .env to root for Docker Compose
cp backend/.env .env
```

### Step 3: Start Services (2 minutes)

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy (this takes ~2 minutes)
# Monitor startup progress
docker-compose logs -f
# Press Ctrl+C to stop following logs once services are running
```

### Step 4: Initialize Database (1 minute)

```bash
# Run database migrations
docker exec vaucda-api alembic upgrade head

# Create admin user
docker exec -it vaucda-api python scripts/create_admin_user.py
# Follow prompts:
#   Username: admin
#   Email: admin@va.gov
#   Password: <create secure password>
#   Confirm: <same password>
```

### Step 5: Pull LLM Models (30 seconds to start, runs in background)

```bash
# Pull essential models (this runs in background automatically on startup)
# To manually pull smaller model for testing:
docker exec vaucda-ollama ollama pull llama3.1:8b

# Verify model is available
docker exec vaucda-ollama ollama list
```

### Step 6: Access Application (immediate)

Open your browser and navigate to:

- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/api/v1/health
- **Neo4j Browser**: http://localhost:7474 (user: neo4j, password: <your_password>)

---

## Verify Installation

### Quick Health Check

```bash
# Check all services are running
docker-compose ps

# Expected output: All services should show "Up" or "healthy"
# vaucda-api           Up (healthy)
# vaucda-frontend      Up
# vaucda-neo4j         Up (healthy)
# vaucda-ollama        Up
# vaucda-redis         Up (healthy)
# vaucda-celery-worker Up
# vaucda-celery-beat   Up
```

### Test API Endpoint

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Should return:
# {
#   "status": "healthy",
#   "timestamp": "2025-11-29T12:00:00Z",
#   "services": {
#     "api": "healthy",
#     "neo4j": "healthy",
#     "redis": "healthy",
#     "ollama": "healthy"
#   }
# }
```

### Test Frontend

```bash
# Check frontend is accessible
curl -I http://localhost:3000

# Should return: HTTP/1.1 200 OK
```

---

## First Login

1. Navigate to http://localhost:3000

2. Click "Login" or "Sign In"

3. Enter credentials:
   - Email: admin@va.gov
   - Password: <password you created>

4. You should be redirected to the main dashboard

---

## Testing Each Component

### 1. Authentication

**Test**: Register a new account and login

1. Navigate to http://localhost:3000/register
2. Fill in registration form:
   - Name: Test User
   - Email: test@va.gov
   - Password: TestPassword123!
3. Click "Register"
4. Login with new credentials

**Expected**: Successfully logged in and redirected to dashboard

---

### 2. Note Generation

**Test**: Generate a simple clinic note

1. Navigate to "Generate Note" page
2. Select "Clinic Note" type
3. Enter clinical input:
   ```
   72 yo male with elevated PSA 8.5 ng/mL. DRE shows firm nodule in right lobe.
   No urinary symptoms. Prior PSA 6.2 one year ago.
   ```
4. Click "Generate Note"

**Expected**:
- Structured note appears within 5-10 seconds
- Contains sections: HPI, Assessment, Plan
- Includes relevant clinical details

---

### 3. Clinical Calculators

**Test**: Run PSA Kinetics calculator

1. Navigate to "Calculators" > "Prostate Cancer"
2. Select "PSA Kinetics"
3. Enter PSA values:
   - Date 1: 2023-01-15, PSA: 4.2 ng/mL
   - Date 2: 2024-01-15, PSA: 6.2 ng/mL
   - Date 3: 2025-01-15, PSA: 8.5 ng/mL
4. Click "Calculate"

**Expected**:
- PSAV (Velocity): ~2.15 ng/mL/year
- PSADT (Doubling Time): calculated
- Interpretation: "Concerning" or similar
- Recommendations displayed

---

### 4. CAPRA Score Calculator

**Test**: Calculate prostate cancer risk

1. Navigate to "Calculators" > "Prostate Cancer" > "CAPRA Score"
2. Enter patient data:
   - Age: 65
   - PSA: 8.5 ng/mL
   - Gleason Primary: 3
   - Gleason Secondary: 4
   - Clinical Stage: T2a
   - Percent Positive Cores: 45%
3. Click "Calculate"

**Expected**:
- CAPRA Score: calculated (0-10)
- Risk Level: Low/Intermediate/High
- 5-year progression-free survival estimate
- 10-year survival estimates

---

### 5. RAG Evidence Search

**Test**: Search clinical guidelines

1. Navigate to "Evidence Search" or "Guidelines"
2. Enter query:
   ```
   Treatment options for high-risk prostate cancer
   ```
3. Select category: "Prostate Cancer"
4. Click "Search"

**Expected**:
- Returns 3-5 relevant guideline excerpts
- Each result shows:
  - Source (NCCN, AUA, or EAU)
  - Relevance score
  - Content snippet
  - Full text available on click

**Note**: This requires clinical guidelines to be ingested. If no results, guidelines need to be loaded (see Data Loading section).

---

### 6. Settings Management

**Test**: Update user preferences

1. Navigate to "Settings" or click profile icon
2. Update preferences:
   - LLM Provider: Select "Ollama"
   - Default Model: Select "llama3.1:8b"
   - Theme: Toggle dark/light mode
3. Click "Save"

**Expected**:
- Settings saved successfully
- UI updates reflect changes (e.g., dark mode)
- Preferences persist after logout/login

---

### 7. WebSocket Streaming

**Test**: Real-time note generation

1. Navigate to "Generate Note"
2. Enter clinical input
3. Click "Generate with Streaming"

**Expected**:
- Note text appears progressively (word by word or sentence by sentence)
- Progress indicator shows generation is ongoing
- Complete note appears in <10 seconds

---

## Load Sample Data (Optional)

### Ingest Clinical Guidelines

```bash
# Create documents directory
mkdir -p data/documents

# Add your PDF guidelines (examples)
# Copy NCCN, AUA, EAU guidelines to data/documents/

# Run ingestion (if ingest script exists)
docker exec vaucda-api python scripts/ingest_documents.py \
  --input-dir /app/data/documents \
  --chunk-size 1000 \
  --chunk-overlap 200

# Verify ingestion
docker exec vaucda-neo4j cypher-shell -u neo4j -p <password> \
  "MATCH (d:Document) RETURN count(d) AS count;"
```

### Create Sample Patient Data (Testing Only)

**WARNING**: Never use real PHI in development/testing

```bash
# Sample clinical scenarios for testing
docker exec vaucda-api python3 << 'EOF'
# This is a placeholder - create test data as needed
print("Sample data creation not implemented - use manual input for testing")
EOF
```

---

## API Testing with cURL

### Authentication

```bash
# Register new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@va.gov",
    "password": "TestPassword123!",
    "full_name": "Test User"
  }'

# Login and get token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@va.gov",
    "password": "TestPassword123!"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"
```

### Generate Note

```bash
# Generate clinic note
curl -X POST http://localhost:8000/api/v1/notes/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "clinical_input": "72 yo male with elevated PSA 8.5. DRE firm nodule right lobe.",
    "note_type": "clinic_note",
    "llm_config": {
      "provider": "ollama",
      "model": "llama3.1:8b"
    }
  }' | jq .
```

### Run Calculator

```bash
# CAPRA Score
curl -X POST http://localhost:8000/api/v1/calculators/capra_score/calculate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "inputs": {
      "age": 65,
      "psa": 8.5,
      "gleason_primary": 3,
      "gleason_secondary": 4,
      "clinical_stage": "T2a",
      "percent_positive_cores": 45.0
    }
  }' | jq .
```

### Search Evidence

```bash
# RAG search
curl -X POST http://localhost:8000/api/v1/evidence/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "Treatment options for high-risk prostate cancer",
    "category": "prostate_cancer",
    "k": 5
  }' | jq .
```

---

## Common Quick Start Issues

### Issue: Services not starting

```bash
# Check logs
docker-compose logs

# Restart services
docker-compose down
docker-compose up -d
```

### Issue: Port already in use

```bash
# Check what's using port 8000
sudo netstat -tulpn | grep 8000

# Kill process or change port in docker-compose.yml
# Edit docker-compose.yml: ports: - "8001:8000"
```

### Issue: Ollama model not found

```bash
# Check available models
docker exec vaucda-ollama ollama list

# Pull model manually
docker exec vaucda-ollama ollama pull llama3.1:8b

# Wait for download to complete (may take 5-10 minutes)
```

### Issue: Frontend can't connect to API

```bash
# Check frontend .env
cat frontend/.env
# Ensure: VITE_API_BASE_URL=http://localhost:8000

# Restart frontend
docker-compose restart vaucda-frontend
```

### Issue: "Connection refused" errors

```bash
# Wait for all services to be healthy
docker-compose ps

# Check health endpoint
curl http://localhost:8000/api/v1/health

# If still failing, check logs
docker-compose logs vaucda-api | tail -50
```

---

## Next Steps

### For Developers

1. **Explore the API**: http://localhost:8000/docs
2. **Read the Architecture**: See ARCHITECTURE.md
3. **Review the Code**: Backend in `/backend`, Frontend in `/frontend`
4. **Run Tests**: See TEST_EXECUTION_GUIDE.md
5. **Contribute**: Follow development standards in `rules.txt`

### For Production Deployment

1. **Review DEPLOYMENT_GUIDE.md**: Complete deployment instructions
2. **Security Hardening**: Change all default passwords and keys
3. **Configure HTTPS**: Set up SSL certificates
4. **Load Real Guidelines**: Ingest NCCN/AUA/EAU documents
5. **Performance Testing**: Test with expected user load
6. **Monitor Logs**: Set up log aggregation and monitoring

### For Clinical Use

1. **User Training**: Train staff on note generation workflow
2. **Calculator Validation**: Review calculator results with known cases
3. **Guideline Updates**: Establish process for updating clinical guidelines
4. **Feedback Loop**: Collect user feedback for improvements
5. **Compliance**: Ensure HIPAA compliance procedures are followed

---

## Resources

- **Full Documentation**: README.md
- **Deployment Guide**: DEPLOYMENT_GUIDE.md
- **API Reference**: http://localhost:8000/docs
- **Architecture**: ARCHITECTURE.md
- **Calculator Details**: docs/VAUCDA.md
- **Testing**: TEST_EXECUTION_GUIDE.md

---

## Support

- **Email**: vaucda-support@va.gov
- **Documentation**: https://vaucda.va.gov/docs
- **Issue Tracker**: VA GitLab

---

## Quick Reference Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f [service_name]

# Restart a service
docker-compose restart [service_name]

# Check service status
docker-compose ps

# Access container shell
docker exec -it [container_name] /bin/bash

# Health check
curl http://localhost:8000/api/v1/health

# Pull Ollama model
docker exec vaucda-ollama ollama pull llama3.1:8b

# Create admin user
docker exec -it vaucda-api python scripts/create_admin_user.py

# Run database migrations
docker exec vaucda-api alembic upgrade head
```

---

**Quick Start Guide Version**: 1.0.0
**Last Updated**: 2025-11-29
**Maintained by**: VA Urology VAUCDA Team

**You're now ready to use VAUCDA!**
