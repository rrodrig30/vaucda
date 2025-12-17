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
    API_PORT: int = 8000
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
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
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # LLM - Anthropic (Optional)
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-20250101"
    ANTHROPIC_MAX_TOKENS: int = 8096
    ANTHROPIC_TIMEOUT: int = 60

    # LLM - OpenAI (Optional)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-4o"
    OPENAI_MAX_TOKENS: int = 8096
    OPENAI_TIMEOUT: int = 60

    # RAG Configuration
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 768
    VECTOR_SEARCH_TOP_K: int = 5
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

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
