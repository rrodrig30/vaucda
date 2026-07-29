"""
VAUCDA Application Configuration
Loads all settings from environment variables (.env file)
"""
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application Configuration
    APP_NAME: str = "VAUCDA"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"

    # Server Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8027
    API_WORKERS: int = 4

    # Protocol Configuration
    USE_HTTPS: bool = False
    BACKEND_PORT: int = 8002
    FRONTEND_PORT: int = 3005

    @property
    def backend_protocol(self) -> str:
        """Get backend protocol (http or https)."""
        return "https" if self.USE_HTTPS else "http"

    @property
    def frontend_protocol(self) -> str:
        """Get frontend protocol (http or https)."""
        return "https" if self.USE_HTTPS else "http"

    # Database - Neo4j (REQUIRED for production - no defaults per rules.txt)
    NEO4J_URI: Optional[str] = None
    NEO4J_USER: Optional[str] = None
    NEO4J_PASSWORD: Optional[str] = None
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 100
    NEO4J_CONNECTION_TIMEOUT: int = 60
    NEO4J_ENCRYPTED: bool = True

    # Database - SQLite (REQUIRED for production - no defaults per rules.txt)
    SQLITE_DATABASE_URL: Optional[str] = None
    SQLITE_ECHO: bool = False

    # Database - Redis (REQUIRED for production - no defaults per rules.txt)
    REDIS_URL: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DECODE_RESPONSES: bool = True

    # Security - JWT
    JWT_SECRET_KEY: str = Field(
        default="CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARACTERS_LONG"
    )
    JWT_ALGORITHM: str = "HS256"
    # 480 minutes (8 hours) covers a full clinical work shift, so a
    # user who logs in at the start of clinic doesn't get logged out
    # mid-batch. Batches routinely take 15-20 min per file × dozens of
    # files, and the frontend doesn't currently auto-refresh on 401
    # (see api/notes.ts), so a short TTL means in-flight batches die
    # with a 401 error and force a re-login + restart. Was 30.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security - Password Hashing
    PASSWORD_HASH_ALGORITHM: str = "bcrypt"
    PASSWORD_HASH_ROUNDS: int = 12

    # Security - CORS
    CORS_ORIGINS: str = '["http://localhost:3000"]'
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = '["GET","POST","PUT","DELETE","OPTIONS"]'
    CORS_ALLOW_HEADERS: str = '["*"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        return json.loads(self.CORS_ORIGINS)

    @property
    def cors_methods_list(self) -> List[str]:
        """Parse CORS methods from JSON string."""
        return json.loads(self.CORS_ALLOW_METHODS)

    @property
    def cors_headers_list(self) -> List[str]:
        """Parse CORS headers from JSON string."""
        return json.loads(self.CORS_ALLOW_HEADERS)

    # LLM - Ollama (Primary Provider) - REQUIRED for production
    OLLAMA_BASE_URL: Optional[str] = None  # Must be set in .env
    OLLAMA_DEFAULT_MODEL: str = "llama3.1:8b"
    # OLLAMA_TIMEOUT: per-request timeout for Ollama /api/generate calls.
    # 1200 s (20 minutes) accommodates the observed worst case where
    # large files (>200 KB clinical input, complex pathology, and
    # heavy GraphRAG context) have taken up to 15 minutes to synthesize
    # a single stage. 20 minutes gives 5 minutes of headroom over that
    # observed maximum without flagging legitimately-slow calls as
    # failures. The previous value (3600 s / 1 hour) was excessive:
    # when Ollama serve was wedged — typically because some process
    # loaded an 8B model with its full 131K context, allocating ~140
    # GB on a 96 GB GPU — every parallel synthesis agent would block
    # for an hour before failing, then the batch processor would retry
    # the same file and burn another hour. With 20 min, a wedge is
    # detected in 20 min instead of 60 min, the batch fails fast, and
    # the user sees an actionable error from the pre-flight GPU health
    # check (app/services/ollama_health.py) on the next submission.
    OLLAMA_TIMEOUT: int = 1200
    OLLAMA_MAX_TOKENS: int = 8192  # Default 8K tokens, user configurable for larger context LLMs
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # GraphRAG runtime LLM (used by global_search map/score/reduce and
    # local_search query-entity extraction). Default to a fast cloud
    # model — local llama3.1:8b on this Ollama instance has been
    # observed to take 30+ s per call, making the multi-call
    # map-reduce path multi-minute. Cloud models typically respond in
    # 1-5 s. Override per-deployment via the GRAPHRAG_LLM_MODEL env
    # var. Embeddings remain on `OLLAMA_EMBEDDING_MODEL` (local) since
    # the cloud LLM does not expose an embeddings endpoint.
    GRAPHRAG_LLM_MODEL: str = "gpt-oss:120b-cloud"

    # LLM - Anthropic (Optional)
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-20250101"
    ANTHROPIC_MAX_TOKENS: int = 8096
    ANTHROPIC_TIMEOUT: int = 3600  # 1 hour timeout for complex note generation

    # LLM - OpenAI (Optional)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-4o"
    OPENAI_MAX_TOKENS: int = 8096
    OPENAI_TIMEOUT: int = 3600  # 1 hour timeout for complex note generation

    # RAG Configuration
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 768
    VECTOR_SEARCH_TOP_K: int = 5
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # UMLS Concept Linking
    UMLS_API_KEY: Optional[str] = None
    USE_UMLS_API: bool = True
    USE_SCISPACY_UMLS: bool = False
    QUICKUMLS_PATH: str = "./data/umls/quickumls"

    # OCR Configuration (Ollama vision model for scanned PDFs)
    OCR_TIMEOUT: int = 180  # seconds per page
    OCR_MAX_PAGES: int = 50  # Maximum pages to OCR
    OCR_DPI: int = 300  # DPI for PDF to image conversion (300 minimum for OCR)
    TEMP_FILE_DIR: str = "/tmp/vaucda"

    # Task-Specific LLM Defaults (configurable via .env)
    # These are used as database column defaults when no user preference exists
    # OCR Task: Vision model for document OCR
    OCR_LLM_PROVIDER: str = "ollama"
    OCR_LLM_MODEL: str = "qwen3-vl:32b"  # Vision model for document OCR (glm-ocr crashes on Ollama 0.17.x)
    OCR_LLM_TEMPERATURE: float = 0.1
    OCR_LLM_MAX_TOKENS: int = 4096

    # Stage 1 Task: Note generation/extraction
    STAGE1_LLM_PROVIDER: str = "ollama"
    STAGE1_LLM_MODEL: str = "llama3.1:8b"  # Default text model
    STAGE1_LLM_TEMPERATURE: float = 0.1
    STAGE1_LLM_MAX_TOKENS: int = 8192

    # Stage 2 Task: Assessment & Plan with RAG
    STAGE2_LLM_PROVIDER: str = "ollama"
    STAGE2_LLM_MODEL: str = "llama3.1:8b"  # Default text model
    STAGE2_LLM_TEMPERATURE: float = 0.0  # Zero for clinical accuracy
    STAGE2_LLM_MAX_TOKENS: int = 8192
    STAGE2_USE_RAG: bool = True
    STAGE2_USE_GRAPHRAG: bool = True
    STAGE2_RAG_TOP_K: int = 5

    # Legacy OCR_MODEL for backward compatibility (deprecated, use OCR_LLM_MODEL)
    @property
    def OCR_MODEL(self) -> str:
        return self.OCR_LLM_MODEL

    # LLM Concurrency & Retry
    OLLAMA_LOCAL_CONCURRENCY: int = 4  # Max concurrent requests to local Ollama models (prevents GPU contention)
    LLM_MAX_RETRIES: int = 5  # Max retries on 429 Too Many Requests
    LLM_RETRY_BASE_DELAY: float = 3.0  # Base delay in seconds (exponential backoff)

    # Model resident-time on Ollama. Sent as `keep_alive` in /api/generate
    # payloads. "0" or "0s" unloads after each request; "24h" or "-1"
    # keeps the model resident. Set high to avoid 30s cold-start on the
    # first request after backend idle.
    OLLAMA_KEEP_ALIVE: str = "24h"

    # Maximum num_ctx vaucda will automatically request for a LOCAL
    # (non-cloud) Ollama model when no per-task user override is set.
    # llm_config_manager.get_model_context_size() applies this as a
    # safety cap: even when MODEL_CONTEXT_SIZES lists the model's full
    # training context (e.g. 131072 for llama3.1:8b), local-model calls
    # without an explicit user value get clamped to this value. Cloud
    # models (``*-cloud`` / ``:cloud``) are exempt — they don't allocate
    # local VRAM.
    #
    # 16384 fits any synthesis sub-agent prompt (typically 2-4K input
    # + 2-8K output) while keeping the KV cache to single-digit GB.
    # Concrete failure mode the cap prevents: llama3.1:8b with the
    # full 131072 context allocates ~140 GB of KV cache on a 96 GB
    # H100, throwing the runner into thrash that blocks every
    # subsequent Ollama request (local AND cloud-proxied).
    OLLAMA_LOCAL_RUNTIME_MAX_CONTEXT: int = 16384

    # Pre-warm Stage 1 / Stage 2 / OCR models at backend startup so the
    # first user request does not pay the model-load cost.
    ENABLE_MODEL_PREWARM: bool = True

    # Skip pre-warming any LOCAL Ollama model whose on-disk size
    # exceeds this threshold (in GB). Models larger than the available
    # GPU VRAM either fail to load or fall back to slow CPU offload,
    # producing a 60s+ stall every backend restart for no benefit.
    # Cloud models (`:cloud` suffix) are always pre-warmed regardless
    # of size since they do not consume local VRAM.
    MODEL_PREWARM_MAX_LOCAL_GB: float = 60.0

    # Skip pre-warming preferences from system/seed accounts (admin
    # default user). Only the human user's actual configured models are
    # worth pre-warming. Set to "" to disable filtering.
    MODEL_PREWARM_SKIP_USER_EMAILS: str = "admin@vaucda.va.gov"

    # Batch Processing
    BATCH_ALLOWED_DIRS: str = '[]'  # JSON array of allowed base directories for batch processing
    BATCH_MAX_RETRIES: int = 3
    BATCH_FILE_SEPARATOR: str = "+++++++++"
    BATCH_FILE_TIMEOUT: int = 600  # seconds per file (10 minutes) — a stuck cloud
    # call auto-fails that one note so the batch moves on instead of freezing
    BATCH_MAX_FILES: int = 200  # maximum files in a single batch

    @property
    def batch_allowed_dirs_list(self) -> List[str]:
        """Parse batch allowed directories from JSON string."""
        return json.loads(self.BATCH_ALLOWED_DIRS)

    # Note Generation
    NOTE_GENERATION_TIMEOUT: int = 30
    NOTE_SESSION_TTL_MINUTES: int = 30
    MAX_NOTE_LENGTH: int = 10000

    # Celery Configuration (REQUIRED for async task processing)
    CELERY_BROKER_URL: Optional[str] = None  # Must be set in .env
    CELERY_RESULT_BACKEND: Optional[str] = None  # Must be set in .env
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: str = '["json"]'
    CELERY_TIMEZONE: str = "UTC"
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_TASK_TIME_LIMIT: int = 300
    CELERY_TASK_SOFT_TIME_LIMIT: int = 240

    @property
    def celery_accept_content_list(self) -> List[str]:
        """Parse Celery accept content from JSON string."""
        return json.loads(self.CELERY_ACCEPT_CONTENT)

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ANONYMOUS: int = 10
    RATE_LIMIT_AUTHENTICATED: int = 100
    RATE_LIMIT_ADMIN: int = 1000

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_DOCUMENT_TYPES: str = '["pdf","docx","txt"]'

    @property
    def allowed_document_types_list(self) -> List[str]:
        """Parse allowed document types from JSON string."""
        return json.loads(self.ALLOWED_DOCUMENT_TYPES)

    # Session Management
    SESSION_CLEANUP_INTERVAL_MINUTES: int = 5
    AUDIT_LOG_RETENTION_DAYS: int = 90

    # Monitoring
    ENABLE_PROMETHEUS: bool = True
    ENABLE_HEALTH_CHECKS: bool = True
    HEALTH_CHECK_INTERVAL: int = 30

    # OpenEvidence Integration
    OPENEVIDENCE_ENCRYPTION_KEY: Optional[str] = None

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret key is set in production."""
        if v == "CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARACTERS_LONG":
            raise ValueError(
                "JWT_SECRET_KEY must be changed from default value in production!"
            )
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long!")
        return v


# Create global settings instance
settings = Settings()
