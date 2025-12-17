# VAUCDA Deployment Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Docker and Docker Compose installed
- At least 10GB free disk space
- 4GB+ available RAM
- GPU optional (Ollama will use CPU if GPU not available)

### Step 1: Prepare Environment Files
```bash
cd /home/gulab/PythonProjects/VAUCDA

# Update root environment file
cp .env.example .env
# Edit .env and update CHANGE_THIS values

# Update backend environment file
cp backend/.env.example backend/.env
# Edit backend/.env and update CHANGE_THIS values

# Update frontend environment file
cp frontend/.env.example frontend/.env
# Edit frontend/.env and update API URLs if needed

# Set secure permissions
chmod 600 .env backend/.env frontend/.env
```

### Step 2: Generate Secure Secrets (Optional but Recommended)
```bash
# Generate new secrets for production
python scripts/generate_secrets.py --env production > /tmp/secrets.txt

# Copy values to your .env files
# Replace all CHANGE_THIS values with generated secrets
```

### Step 3: Start Services
```bash
# Start all services in background
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output shows all services with "Up" status
```

### Step 4: Initialize Databases
```bash
# Run initialization script
bash scripts/init_databases.sh

# Wait for all databases to be initialized
# Expected: "Database initialization complete!" message
```

### Step 5: Verify Deployment
```bash
# Test API health
curl http://localhost:8000/api/v1/health

# Test Ollama
curl http://localhost:11434/api/tags

# Access frontend
open http://localhost:3000
```

## Common Commands

### View Service Status
```bash
docker-compose ps
```

### View Service Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f vaucda-api
docker-compose logs -f vaucda-neo4j
docker-compose logs -f redis
```

### Stop Services
```bash
docker-compose down
```

### Restart Services
```bash
docker-compose restart
```

### Restart Specific Service
```bash
docker-compose restart vaucda-api
```

### Remove All Data (Careful!)
```bash
docker-compose down -v
```

## Configuration Quick Reference

### Root .env (.env)
- `COMPOSE_PROJECT_NAME`: Docker project name
- `API_PORT`: Backend API port (default: 8000)
- `FRONTEND_PORT`: Frontend port (default: 3000)
- `NEO4J_PASSWORD`: Database password
- `REDIS_PASSWORD`: Cache password
- `SECRET_KEY`: JWT secret

### Backend .env (backend/.env)
- `ENVIRONMENT`: production/development
- `DEBUG`: true/false
- `OLLAMA_BASE_URL`: Ollama server URL
- `ANTHROPIC_API_KEY`: Optional Claude API key
- `OPENAI_API_KEY`: Optional OpenAI API key

### Frontend .env (frontend/.env)
- `VITE_API_BASE_URL`: Backend API URL
- `VITE_WS_URL`: WebSocket URL
- `VITE_ENABLE_DEVTOOLS`: true/false (must be false in production)
- `VITE_ENABLE_RAG`: true/false
- `VITE_ENABLE_STREAMING`: true/false

## Health Checks

### API Health
```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"healthy",...}
```

### Database Health
```bash
# Neo4j
docker exec vaucda-neo4j cypher-shell -u neo4j -p <password> "RETURN 1"
# Expected: 1 row, 1 column: 1

# Redis
docker exec vaucda-redis redis-cli -a <password> ping
# Expected: PONG
```

### Ollama Health
```bash
curl http://localhost:11434/api/tags
# Expected: JSON with model information
```

## Troubleshooting

### Services Won't Start
```bash
# Check logs
docker-compose logs

# Verify Docker is running
docker ps

# Check disk space
df -h

# Check memory
free -h
```

### API Connection Refused
```bash
# Check if API container is running
docker-compose ps vaucda-api

# Check API logs
docker-compose logs vaucda-api

# Check if port is in use
lsof -i :8000
```

### Database Connection Failed
```bash
# Check Neo4j is healthy
docker-compose ps vaucda-neo4j

# Verify Neo4j password
echo "CHANGE_THIS_TO_SECURE_PASSWORD" | docker exec -i vaucda-neo4j cypher-shell

# Check Redis password
docker exec vaucda-redis redis-cli -a <password> ping
```

### Ollama Models Not Loaded
```bash
# Check Ollama logs
docker-compose logs vaucda-ollama

# Check available disk space
df -h

# Check available memory
free -h

# Manually pull models if needed
docker exec vaucda-ollama ollama pull llama3.1:8b
```

## Performance Tuning

### Increase Parallel Requests (Ollama)
Edit `.env`:
```bash
OLLAMA_NUM_PARALLEL=8  # Default: 4
```

### Adjust Celery Workers
Edit `.env`:
```bash
CELERY_WORKER_CONCURRENCY=8  # Default: 4
```

### GPU Configuration
For GPU support:
```bash
OLLAMA_RUNTIME=nvidia  # Use nvidia runtime
NVIDIA_VISIBLE_DEVICES=all  # Use all GPUs
```

For CPU-only:
```bash
OLLAMA_RUNTIME=runc  # Use default runc runtime
```

## Monitoring

### Docker Stats
```bash
docker stats

# Specific container
docker stats vaucda-api
```

### Service Resource Usage
```bash
docker ps --format "table {{.Names}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Container Logs with Timestamps
```bash
docker-compose logs --timestamps

# Last 100 lines
docker-compose logs --tail=100

# Last 5 minutes
docker-compose logs --since 5m
```

## Backup and Restore

### Backup Databases
```bash
# Neo4j backup
docker exec vaucda-neo4j neo4j-admin database dump neo4j /data/backups/neo4j.backup

# Redis backup
docker exec vaucda-redis redis-cli -a <password> BGSAVE

# SQLite backup
cp data/vaucda.db data/vaucda.db.backup
```

### Restore Databases
```bash
# Neo4j restore
docker exec vaucda-neo4j neo4j-admin database load neo4j /data/backups/neo4j.backup

# Redis restore
docker exec vaucda-redis redis-cli -a <password> DEBUG OBJECT mykey
```

## Security Checklist

Before production deployment:
- [ ] All CHANGE_THIS values replaced with unique secrets
- [ ] All passwords at least 24 characters
- [ ] File permissions set: `chmod 600 .env*`
- [ ] .env files added to .gitignore
- [ ] DEBUG=false in production
- [ ] VITE_ENABLE_DEVTOOLS=false in frontend
- [ ] SSL/TLS configured
- [ ] Database backups configured
- [ ] Monitoring and alerting set up
- [ ] Access control configured

## Support

### View Complete Documentation
- Full checklist: `DEPLOYMENT_VALIDATION_CHECKLIST.md`
- Architecture overview: `ARCHITECTURE.md`
- API specification: `API_SPECIFICATION.md`

### Get Help
1. Check service logs: `docker-compose logs`
2. Review configuration: `docker-compose config`
3. Check Docker system: `docker system df`
4. Verify health: `curl http://localhost:8000/api/v1/health`

---

**Last Updated**: 2025-11-29
**Version**: 1.0.0
