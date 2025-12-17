# VAUCDA Quick Start Guide

## Prerequisites

1. **Python 3.12+** installed
2. **Docker** installed (for Neo4j and Redis)
3. **Ollama** installed and running

## Step 1: Start Required Services

### Start Neo4j
```bash
docker run -d --name vaucda-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/changeme123 \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:latest
```

### Start Redis
```bash
docker run -d --name vaucda-redis \
  -p 6379:6379 \
  redis:latest
```

### Start Ollama
```bash
ollama serve

# In another terminal:
ollama pull llama3.1:8b
```

## Step 2: Configure Environment

Create `.env` file in project root:

```bash
# Database
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme123

REDIS_HOST=localhost
REDIS_PORT=6379

# LLM
LLM_PRIMARY_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# Optional: Anthropic
ANTHROPIC_API_KEY=your-api-key-here
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Optional: OpenAI
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o

# App
DEBUG=True
LOG_LEVEL=INFO
SECRET_KEY=your-secret-key-change-this-in-production
```

## Step 3: Install Dependencies

```bash
cd /home/gulab/PythonProjects/VAUCDA

# Activate virtual environment
source .venv/bin/activate

# Install new dependencies
pip install sentence-transformers
pip install tiktoken
pip install PyPDF2
pip install python-docx
```

## Step 4: Initialize Neo4j Vector Indexes

```bash
# Connect to Neo4j browser: http://localhost:7474
# Run these Cypher queries:

# Create vector index for documents
CREATE VECTOR INDEX document_embeddings IF NOT EXISTS
FOR (d:Document)
ON d.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};

# Create full-text index for hybrid search
CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
FOR (d:Document)
ON EACH [d.title, d.content, d.summary];

# Create indexes for fast lookups
CREATE INDEX calculator_id IF NOT EXISTS FOR (c:Calculator) ON (c.calculator_id);
CREATE INDEX concept_name IF NOT EXISTS FOR (c:ClinicalConcept) ON (c.name);
CREATE INDEX session_id IF NOT EXISTS FOR (s:Session) ON (s.session_id);
```

## Step 5: Start the Backend

```bash
cd backend

# Run FastAPI server
python -m app.main

# Or use uvicorn directly:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at: http://localhost:8000

API Documentation: http://localhost:8000/api/docs

## Step 6: Test the System

### 6.1 Create a User

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_doctor",
    "email": "doctor@va.gov",
    "full_name": "Dr. Test",
    "password": "SecurePassword123!",
    "institution": "VA Medical Center"
  }'
```

### 6.2 Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_doctor",
    "password": "SecurePassword123!"
  }'

# Save the access_token from response
export TOKEN="your-access-token-here"
```

### 6.3 List Calculators

```bash
curl -X GET "http://localhost:8000/api/v1/calculators" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.4 Run a Calculator

```bash
curl -X POST "http://localhost:8000/api/v1/calculators/pcpt_risk/calculate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "age": 65,
      "psa": 8.5,
      "dre_result": "normal",
      "family_history": true,
      "prior_biopsy": false,
      "race": "white"
    }
  }'
```

### 6.5 Generate a Note (Without RAG)

```bash
curl -X POST "http://localhost:8000/api/v1/notes/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input_text": "65 year old male with PSA 8.5, normal DRE, family history of prostate cancer. No prior biopsy. Considering prostate biopsy.",
    "note_type": "clinic",
    "llm_provider": "ollama",
    "calculator_ids": ["pcpt_risk"],
    "use_rag": false,
    "temperature": 0.3
  }'
```

## Step 7: Populate Knowledge Base (Optional)

### Download Sample Documents

```bash
mkdir -p ~/vaucda_docs

# Download AUA guidelines, research papers, etc.
# Save as PDF or DOCX in ~/vaucda_docs
```

### Ingest Documents

```bash
cd /home/gulab/PythonProjects/VAUCDA

# Ingest single file
python scripts/ingest_documents.py \
  --file ~/vaucda_docs/aua_guideline.pdf \
  --doc-type guideline \
  --category prostate \
  --source AUA \
  --version 2024.1 \
  --publication-date 2024-01-15

# Ingest entire directory
python scripts/ingest_documents.py \
  --directory ~/vaucda_docs \
  --doc-type literature \
  --category kidney \
  --recursive
```

### Test RAG Search

```bash
curl -X POST "http://localhost:8000/api/v1/rag/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "treatment options for localized prostate cancer",
    "limit": 5,
    "search_strategy": "graph"
  }'
```

### Generate Note with RAG

```bash
curl -X POST "http://localhost:8000/api/v1/notes/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input_text": "65 year old male with newly diagnosed low-risk prostate cancer. PSA 6.2, Gleason 3+3, clinical stage T1c. Patient interested in treatment options.",
    "note_type": "clinic",
    "llm_provider": "ollama",
    "calculator_ids": ["capra", "pcpt_risk"],
    "use_rag": true,
    "temperature": 0.3
  }'
```

## Step 8: Use External Integrations

### OpenEvidence

```bash
# First, save OpenEvidence credentials in settings
curl -X POST "http://localhost:8000/api/v1/settings/integrations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "openevidence_username": "your-username",
    "openevidence_password": "your-password"
  }'

# Generate OpenEvidence query
curl -X GET "http://localhost:8000/api/v1/rag/openevidence-query?query=prostate+cancer+screening" \
  -H "Authorization: Bearer $TOKEN"

# Returns URL to open in browser
```

### NSQIP

```bash
curl -X GET "http://localhost:8000/api/v1/rag/nsqip-link" \
  -H "Authorization: Bearer $TOKEN"

# Returns NSQIP calculator URL
```

## Common Issues & Solutions

### Issue: Neo4j Connection Failed

**Solution:**
```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check Neo4j logs
docker logs vaucda-neo4j

# Restart Neo4j
docker restart vaucda-neo4j
```

### Issue: Ollama Not Responding

**Solution:**
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Restart Ollama
# macOS/Linux:
ollama serve

# Verify model is pulled
ollama list
```

### Issue: Redis Connection Error

**Solution:**
```bash
# Check Redis is running
docker ps | grep redis

# Test Redis
redis-cli ping

# Restart Redis
docker restart vaucda-redis
```

### Issue: Embedding Generation Slow

**Solution:**
```bash
# Check if GPU is available
python -c "import torch; print(torch.cuda.is_available())"

# If GPU available, it will be used automatically
# If not, consider adding GPU or increasing Redis cache TTL
```

## Development Workflow

### 1. Make Code Changes

```bash
# Code is located in:
backend/rag/          # RAG components
backend/app/services/ # Note generation
backend/app/api/v1/   # API endpoints
backend/calculators/  # Calculators
```

### 2. Test Changes

```bash
# Run with reload for development
uvicorn app.main:app --reload
```

### 3. Check Logs

```bash
# Backend logs show in terminal
# Look for errors, warnings, and INFO messages

# Neo4j browser for database inspection:
# http://localhost:7474
```

### 4. API Testing

Use the interactive API docs:
- http://localhost:8000/api/docs

Or use curl/Postman/HTTPie for manual testing.

## Production Deployment

### 1. Update Environment Variables

```bash
DEBUG=False
LOG_LEVEL=WARNING
SECRET_KEY=strong-random-secret-key

# Use production databases
NEO4J_URI=bolt://production-neo4j:7687
REDIS_HOST=production-redis

# Configure production LLMs
ANTHROPIC_API_KEY=production-key
```

### 2. Use Production Server

```bash
# Use gunicorn instead of uvicorn
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### 3. Set Up HTTPS

```bash
# Use nginx as reverse proxy
# Configure SSL certificates
# Enable rate limiting
```

## Next Steps

1. **Populate Knowledge Base** - Ingest clinical guidelines and literature
2. **Configure LLM Providers** - Add API keys for Anthropic/OpenAI
3. **Customize Templates** - Modify note templates in `urology_prompt.txt`
4. **Add Calculators** - Implement additional specialty-specific calculators
5. **Deploy Frontend** - Set up React frontend to consume APIs

## Support

- **Documentation**: See IMPLEMENTATION_COMPLETE.md for detailed architecture
- **API Docs**: http://localhost:8000/api/docs
- **Logs**: Check terminal output for errors and warnings

## Security Notes

- **Never commit .env file** - Contains secrets
- **Change default passwords** - Neo4j, secret keys
- **Use HTTPS in production** - Protect PHI
- **Review HIPAA compliance** - Notes are not persisted by default
- **Audit logs** - Only metadata, no PHI

---

**Quick Start Guide - Version 1.0**
*Last Updated: November 29, 2025*
