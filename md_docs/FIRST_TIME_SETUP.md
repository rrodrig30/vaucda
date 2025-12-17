# VAUCDA First-Time Setup Guide

This guide walks you through setting up VAUCDA from scratch.

---

## 🎯 Quick Start (TL;DR)

```bash
# 1. Make scripts executable
chmod +x start.sh stop.sh

# 2. Run first-time setup
./scripts/first_time_setup.sh

# 3. Start services
./start.sh

# 4. Open browser
open http://localhost:5173
```

**Default credentials:** `admin` / `admin123`

---

## 📋 Prerequisites

### Required Software

| Software | Minimum Version | Check Command | Install Link |
|----------|----------------|---------------|--------------|
| Python | 3.10+ | `python3 --version` | https://python.org |
| Node.js | 18+ | `node --version` | https://nodejs.org |
| npm | 8+ | `npm --version` | (comes with Node.js) |
| Git | 2.0+ | `git --version` | https://git-scm.com |

### Optional (But Recommended)

| Software | Purpose | Install Link |
|----------|---------|--------------|
| Neo4j | RAG vector search | https://neo4j.com/download/ |
| CUDA | GPU acceleration | https://developer.nvidia.com/cuda-downloads |
| ffmpeg | Better audio support | https://ffmpeg.org/download.html |

---

## 🚀 Step-by-Step Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/VAUCDA.git
cd VAUCDA
```

### 2. Make Scripts Executable

```bash
chmod +x start.sh stop.sh
```

### 3. Backend Setup

#### 3.1 Create Virtual Environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3.2 Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**This installs:**
- FastAPI (web framework)
- Whisper (speech-to-text)
- Pyannote (speaker diarization) - optional
- Neo4j driver (vector database) - optional
- And 30+ other packages

**Expected time:** 5-10 minutes

#### 3.3 Download Whisper Model (One-Time)

```bash
python -c "import whisper; whisper.load_model('medium.en')"
```

**Size:** ~1.5GB
**Expected time:** 5-10 minutes (depends on internet speed)

The model will be cached in `~/.cache/whisper/` and won't need to be downloaded again.

#### 3.4 Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit .env file
nano .env  # or use your favorite editor
```

**Required settings:**

```bash
# Application
SECRET_KEY=your-secret-key-here-change-in-production
DATABASE_URL=sqlite:///./vaucda.db

# LLM Providers (at least one required)
OLLAMA_BASE_URL=http://localhost:11434  # If using Ollama
ANTHROPIC_API_KEY=sk-ant-xxxxx         # If using Claude
OPENAI_API_KEY=sk-xxxxx                # If using GPT

# Optional: Speaker Diarization
HUGGINGFACE_TOKEN=hf_xxxxx             # Get from https://huggingface.co/settings/tokens

# Optional: Neo4j for RAG
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password
```

**Generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 3.5 Initialize Database

```bash
# Create SQLite database and tables
python -c "from app.database.sqlite_db import init_db; init_db()"
```

This creates:
- `vaucda.db` - Main SQLite database
- User accounts table
- Settings table
- Session management

#### 3.6 Create Admin User

```bash
python -c "
from app.database.sqlite_db import SessionLocal
from app.database.sqlite_models import User
from app.core.security import get_password_hash

db = SessionLocal()
admin = User(
    username='admin',
    email='admin@vaucda.local',
    hashed_password=get_password_hash('admin123'),
    role='admin',
    is_active=True
)
db.add(admin)
db.commit()
print('Admin user created: admin / admin123')
print('⚠️  Change password after first login!')
"
```

---

### 4. Frontend Setup

```bash
cd ../frontend  # From backend directory
npm install
```

**This installs:**
- React 18
- TypeScript
- Vite (build tool)
- TailwindCSS
- And 100+ other packages

**Expected time:** 3-5 minutes

#### 4.1 Configure Frontend Environment

```bash
# Create .env file
cat > .env << 'EOF'
VITE_API_BASE_URL=http://localhost:8000
EOF
```

---

### 5. Optional: Neo4j Setup (For RAG Features)

#### 5.1 Install Neo4j

**Using Docker (Easiest):**
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -e NEO4J_PLUGINS='["apoc","graph-data-science"]' \
  neo4j:5.13
```

**Or download:** https://neo4j.com/download/

#### 5.2 Create Vector Index

```bash
cd ../backend
source venv/bin/activate

python -c "
from backend.database.neo4j_client import Neo4jClient, Neo4jConfig

config = Neo4jConfig()
client = Neo4jClient(config)

# Create vector index for RAG
client.create_vector_index()
print('Vector index created!')
"
```

#### 5.3 (Optional) Ingest Knowledge Base

```bash
# Ingest clinical guidelines into Neo4j
python scripts/ingest_guidelines.py
```

---

### 6. Optional: LLM Setup

#### Option A: Ollama (Local, Free)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull recommended models
ollama pull llama3.1:8b        # For note generation
ollama pull llama3.1:70b       # For complex clinical reasoning (if GPU available)
ollama pull mistral:7b         # Alternative lightweight model

# Verify
ollama list
```

#### Option B: Anthropic Claude (Cloud, Paid)

1. Get API key: https://console.anthropic.com/
2. Add to `backend/.env`:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```

#### Option C: OpenAI GPT (Cloud, Paid)

1. Get API key: https://platform.openai.com/api-keys
2. Add to `backend/.env`:
   ```bash
   OPENAI_API_KEY=sk-xxxxx
   ```

---

### 7. Optional: Pyannote Setup (Speaker Diarization)

#### 7.1 Install Pyannote

```bash
cd backend
source venv/bin/activate
pip install pyannote.audio
```

#### 7.2 Get HuggingFace Token

1. Create account: https://huggingface.co/join
2. Get token: https://huggingface.co/settings/tokens
3. Accept model terms: https://huggingface.co/pyannote/speaker-diarization-3.1

#### 7.3 Add to Environment

```bash
# Add to backend/.env
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 🎬 First Run

### Start Services

```bash
# From project root
./start.sh
```

**What happens:**
1. ✅ Checks Python/Node.js installed
2. ✅ Verifies environment variables
3. ✅ Installs missing dependencies
4. ✅ Downloads Whisper model (if needed)
5. ✅ Initializes database
6. ✅ Starts backend on http://localhost:8000
7. ✅ Starts frontend on http://localhost:5173

**Expected output:**
```
╔════════════════════════════════════════════════════════════╗
║                  VAUCDA Started Successfully!              ║
╚════════════════════════════════════════════════════════════╝

Services:
  ✓ Backend:  http://localhost:8000
  ✓ Frontend: http://localhost:5173
  ✓ API Docs: http://localhost:8000/docs
```

### Access Application

1. Open browser: http://localhost:5173
2. Login with: `admin` / `admin123`
3. **Change password immediately!**

---

## ✅ Verify Installation

### 1. Check Backend Health

```bash
curl http://localhost:8000/api/v1/health
```

**Expected:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "api": {"status": "healthy"},
    "ollama": {"status": "healthy", "models_available": 2}
  }
}
```

### 2. Check Frontend

Open http://localhost:5173 - should see login page

### 3. Test Note Generation

1. Login to application
2. Navigate to **Note Generation**
3. Paste sample clinical data:
   ```
   72 yo M with PSA 8.5 ng/mL
   Gleason 3+4=7 on biopsy
   4/12 cores positive
   Clinical stage T1c
   ```
4. Click **"Generate Preliminary Note"**
5. Should see organized note with extracted entities

### 4. Test Ambient Listening (Optional)

1. Click **"Start Listening"**
2. Grant microphone permission
3. Speak: "Patient is a seventy-two year old male"
4. Should see transcription appear in real-time

---

## 🔧 Troubleshooting

### Backend Won't Start

**Error: "Port 8000 already in use"**
```bash
# Find process using port 8000
lsof -ti:8000

# Kill it
kill -9 $(lsof -ti:8000)

# Or use stop.sh
./stop.sh
```

**Error: "Whisper model not found"**
```bash
cd backend
source venv/bin/activate
python -c "import whisper; whisper.load_model('medium.en')"
```

**Error: "HUGGINGFACE_TOKEN not set"**
- This is a warning, not an error
- Speaker diarization will be disabled
- Application still works for transcription

### Frontend Won't Start

**Error: "Cannot find module"**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

**Error: "VITE_API_BASE_URL not defined"**
```bash
cd frontend
echo "VITE_API_BASE_URL=http://localhost:8000" > .env
```

### Database Errors

**Error: "Database is locked"**
```bash
# Stop all services
./stop.sh

# Remove lock
rm backend/vaucda.db-wal backend/vaucda.db-shm

# Restart
./start.sh
```

### Neo4j Connection Failed

```bash
# Check if Neo4j is running
docker ps | grep neo4j

# If not running, start it
docker start neo4j

# Check logs
docker logs neo4j
```

---

## 📊 Resource Requirements

### Minimum System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| Disk | 20 GB | 50+ GB |
| GPU | None | NVIDIA 6GB+ VRAM |

### Disk Space Breakdown

| Component | Size |
|-----------|------|
| Python dependencies | ~2 GB |
| Node modules | ~500 MB |
| Whisper model | ~1.5 GB |
| Pyannote model | ~300 MB |
| Neo4j | ~1 GB |
| Application data | Grows with use |

---

## 🔐 Security Checklist

Before deploying to production:

- [ ] Change default admin password
- [ ] Generate new SECRET_KEY
- [ ] Use strong database passwords
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall rules
- [ ] Set up backup procedures
- [ ] Review HIPAA compliance settings
- [ ] Enable audit logging
- [ ] Restrict API access
- [ ] Configure rate limiting

---

## 📝 Post-Setup Configuration

### 1. Configure Default Settings

1. Login to application
2. Navigate to **Settings**
3. Set:
   - Default LLM provider
   - Default note type
   - RAG preferences
   - Calculator defaults

### 2. Import Clinical Guidelines (Optional)

```bash
cd backend
source venv/bin/activate
python scripts/ingest_guidelines.py --source nccn --category prostate
python scripts/ingest_guidelines.py --source aua --category bladder
```

### 3. Create Additional Users

```bash
cd backend
source venv/bin/activate
python scripts/create_user.py --username drsmith --role user --email drsmith@example.com
```

---

## 🆘 Getting Help

### Resources

- **Documentation:** `docs/` directory
- **API Docs:** http://localhost:8000/docs (when running)
- **GitHub Issues:** https://github.com/yourusername/VAUCDA/issues

### Logs

Check logs for debugging:

```bash
# Backend logs
tail -f backend/logs/backend.log

# Frontend logs
tail -f frontend/logs/frontend.log

# Both at once
tail -f backend/logs/backend.log frontend/logs/frontend.log
```

### Support Channels

- GitHub Discussions (for questions)
- GitHub Issues (for bugs)
- Email: support@vaucda.example.com

---

## 🎉 Next Steps

After successful setup:

1. **Read the Two-Stage Workflow Guide:** `docs/TWO_STAGE_WORKFLOW.md`
2. **Review Ambient Listening Setup:** `docs/AMBIENT_LISTENING_SETUP.md`
3. **Explore Calculator Documentation:** `docs/VAUCDA.md`
4. **Try Sample Clinical Scenarios:** `docs/examples/`
5. **Configure for your institution:** `docs/DEPLOYMENT.md`

---

## 🔄 Regular Maintenance

### Daily

```bash
# Check service health
curl http://localhost:8000/api/v1/health
```

### Weekly

```bash
# Update dependencies
cd backend && source venv/bin/activate && pip list --outdated
cd frontend && npm outdated

# Backup database
cp backend/vaucda.db backend/backups/vaucda_$(date +%Y%m%d).db
```

### Monthly

```bash
# Update Whisper model (if new version available)
pip install --upgrade openai-whisper

# Update Ollama models
ollama pull llama3.1:8b

# Review audit logs
python scripts/analyze_usage.py --month $(date +%Y-%m)
```

---

**Congratulations! VAUCDA is now set up and ready to use! 🎊**

For questions or issues during setup, please check the troubleshooting section above or open a GitHub issue.
