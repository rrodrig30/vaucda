# VAUCDA Backend API

**VA Urology Clinical Documentation Assistant - FastAPI Backend**

Production-ready REST API server with LLM integration, RAG pipeline, and 44 clinical calculators.

## Architecture Overview

```
FastAPI Application (Python 3.11+)
├── Authentication (JWT)
├── Clinical Note Generation (LLM + RAG)
├── 44 Urological Calculators
├── Template Management
├── User Settings
└── Background Task Processing (Celery)

Databases:
├── Neo4j 5.15+ (Vector Store + Knowledge Graph)
├── SQLite (User Data, Settings, Audit Logs)
└── Redis 7.2+ (Cache + Message Broker)

LLM Providers:
├── Ollama (Primary - Local Models)
├── Anthropic Claude (Optional)
└── OpenAI GPT (Optional)
```

## Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for containerized deployment)
- **Neo4j 5.15+** with APOC and GDS plugins
- **Redis 7.2+**
- **Ollama** with models: llama3.1:8b, llama3.1:70b, nomic-embed-text

## Quick Start

### 1. Environment Setup

```bash
# Clone repository
cd /home/gulab/PythonProjects/VAUCDA/backend

# Copy environment template
cp .env.example .env

# Edit .env file with your configuration
nano .env
```

**CRITICAL:** Update these values in `.env`:
- `JWT_SECRET_KEY`: Generate a secure 32+ character random string
- `NEO4J_PASSWORD`: Set Neo4j database password
- `OPENEVIDENCE_ENCRYPTION_KEY`: Generate a 32-byte key for Fernet encryption

### 2. Install Dependencies

#### Option A: Virtual Environment (Development)

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

#### Option B: Docker (Production)

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f vaucda-api

# Stop services
docker-compose down
```

### 3. Database Initialization

#### SQLite Database

```bash
# Initialize SQLite tables
alembic upgrade head

# Or run directly in Python
python -c "from app.database.sqlite_session import init_db; import asyncio; asyncio.run(init_db())"
```

#### Neo4j Database

```bash
# Start Neo4j
docker-compose up -d neo4j

# Access Neo4j Browser
open http://localhost:7474

# Run initialization script
cat backend/database/migrations/neo4j/init_schema.cypher | \
  docker exec -i vaucda-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD
```

### 4. Pull Ollama Models

```bash
# Start Ollama
docker-compose up -d ollama

# Pull required models
docker exec -it vaucda-ollama ollama pull llama3.1:8b
docker exec -it vaucda-ollama ollama pull llama3.1:70b
docker exec -it vaucda-ollama ollama pull nomic-embed-text
docker exec -it vaucda-ollama ollama pull phi3:medium
docker exec -it vaucda-ollama ollama pull mistral:7b
```

### 5. Run Application

#### Development Mode

```bash
# Activate virtual environment
source venv/bin/activate

# Run with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or run directly
python app/main.py
```

#### Production Mode (Docker)

```bash
# Start all services
docker-compose up -d

# Scale API replicas for high availability
docker-compose up -d --scale vaucda-api=4 --scale celery-worker=4
```

### 6. Verify Installation

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Detailed health check (requires authentication)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/v1/health/detailed

# API Documentation
open http://localhost:8000/api/docs
```

## API Endpoints

### Authentication

- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user info
- `POST /api/v1/auth/change-password` - Change password

### Clinical Note Generation

- `POST /api/v1/notes/generate` - Generate clinical note
- `GET /api/v1/notes/{note_id}` - Retrieve generated note

### Clinical Calculators

- `GET /api/v1/calculators` - List all 44 calculators
- `GET /api/v1/calculators/{calculator_id}` - Get calculator details
- `POST /api/v1/calculators/{calculator_id}/calculate` - Execute calculator

### User Settings

- `GET /api/v1/settings` - Get user settings
- `PUT /api/v1/settings` - Update user settings

### Health Checks

- `GET /api/v1/health` - Basic health check (no auth)
- `GET /api/v1/health/detailed` - Detailed service status (requires auth)
- `GET /api/v1/health/ready` - Kubernetes readiness probe
- `GET /api/v1/health/live` - Kubernetes liveness probe

## Configuration

### Environment Variables

All configuration is managed through the `.env` file. See `.env.example` for complete list.

#### Key Settings:

| Variable | Description | Example |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | Secret for JWT signing | Random 32+ char string |
| `NEO4J_URI` | Neo4j connection URI | `bolt://neo4j:7687` |
| `NEO4J_PASSWORD` | Neo4j password | `secure_password` |
| `OLLAMA_BASE_URL` | Ollama API endpoint | `http://ollama:11434` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_api/test_auth.py -v
```

### Code Quality

```bash
# Format code with black
black app/

# Sort imports
isort app/

# Lint code
flake8 app/

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# View migration history
alembic history
```

## Production Deployment

### Docker Compose Deployment

1. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

2. **Build Images**
   ```bash
   docker-compose build
   ```

3. **Start Services**
   ```bash
   docker-compose up -d
   ```

4. **Initialize Databases**
   ```bash
   # SQLite
   docker exec vaucda-api alembic upgrade head

   # Neo4j
   docker exec -i vaucda-neo4j cypher-shell -u neo4j -p PASSWORD < init_schema.cypher
   ```

5. **Create Admin User**
   ```bash
   docker exec -it vaucda-api python scripts/create_admin_user.py
   ```

### Kubernetes Deployment

See `deployment/kubernetes/` directory for Kubernetes manifests.

### Monitoring

- **Prometheus Metrics**: Available at `/metrics` (if enabled)
- **Health Checks**: `/api/v1/health`, `/api/v1/health/ready`, `/api/v1/health/live`
- **Logs**: Structured JSON logs to stdout

## Security

### HIPAA Compliance

- **Zero PHI Persistence**: All clinical data is ephemeral (30-minute TTL)
- **Audit Logging**: Metadata-only logs (no PHI)
- **Encryption**:
  - JWT tokens for authentication
  - TLS 1.3 for data in transit
  - Fernet encryption for sensitive credentials
- **Session Management**: Automatic 30-minute timeout
- **Access Control**: Role-based (user, admin)

### Security Best Practices

- Change all default passwords
- Use strong JWT secret (32+ characters)
- Enable HTTPS in production
- Configure CORS properly
- Rate limit enabled by default
- Regular security updates

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

```bash
# Check Neo4j is running
docker ps | grep neo4j
docker logs vaucda-neo4j

# Verify connection
docker exec -it vaucda-neo4j cypher-shell -u neo4j -p PASSWORD "RETURN 1"
```

#### 2. Ollama Model Not Found

```bash
# List available models
docker exec -it vaucda-ollama ollama list

# Pull missing model
docker exec -it vaucda-ollama ollama pull llama3.1:8b
```

#### 3. JWT Token Errors

- Verify `JWT_SECRET_KEY` is set and consistent across all services
- Check token expiration time
- Ensure system clocks are synchronized

#### 4. Permission Denied Errors

```bash
# Fix data directory permissions
sudo chown -R $USER:$USER ./data
chmod -R 755 ./data
```

## Performance Optimization

### API Server

- Run 4+ replicas behind load balancer (500+ concurrent users)
- Configure connection pooling
- Enable Redis caching

### Database

- Neo4j: Allocate 8GB heap + 16GB page cache for 32GB RAM server
- Redis: Configure max memory and eviction policy
- SQLite: Use WAL mode for concurrent reads

### LLM Processing

- Use Celery workers for async processing
- Configure GPU for Ollama (NVIDIA required)
- Implement request queuing for rate limiting

## Architecture Details

### Technology Stack

- **Framework**: FastAPI 0.109+
- **Python**: 3.11+
- **Databases**: Neo4j 5.15, SQLite, Redis 7.2
- **Task Queue**: Celery 5.3+
- **LLM**: Ollama, Anthropic, OpenAI
- **RAG**: LangChain, sentence-transformers

### Directory Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Settings (loaded from .env)
│   ├── api/v1/                 # API endpoints
│   ├── core/                   # Core utilities (security, etc.)
│   ├── database/               # Database models and clients
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # Business logic
│   └── workers/                # Celery tasks
├── tests/                      # Test suite
├── alembic/                    # Database migrations
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
└── .env                        # Configuration (NOT in git)
```

## Support

For issues and questions:
- Review `/home/gulab/PythonProjects/VAUCDA/ARCHITECTURE.md`
- Check `/home/gulab/PythonProjects/VAUCDA/API_SPECIFICATION.md`
- View logs: `docker-compose logs -f vaucda-api`

## License

VA Internal Use Only
