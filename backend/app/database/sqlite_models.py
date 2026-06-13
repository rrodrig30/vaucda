"""
SQLAlchemy models for SQLite database
Stores user settings, session metadata, and audit logs (NO PHI)
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, JSON, Index, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

from app.config import settings

Base = declarative_base()


def _default_model_factory() -> str:
    """Default-model factory for new user_preferences rows.

    Reads ``settings.OLLAMA_DEFAULT_MODEL`` at INSERT time so the
    per-deployment env value (``OLLAMA_DEFAULT_MODEL=...``) flows into
    new user defaults instead of a hardcoded literal. Per rules.txt
    ("No hardcoded elements"), defaults that drive runtime behavior
    must come from environment configuration.
    """
    return settings.OLLAMA_DEFAULT_MODEL


class User(Base):
    """User account information."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # User profile information
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    full_name = Column(String(255), nullable=True)  # Deprecated, kept for backwards compatibility
    initials = Column(String(10), nullable=True)
    position = Column(String(50), nullable=True)  # Physician-Faculty, Physician-Fellow, Physician-Resident, APP-PA, APP-NP, Staff
    specialty = Column(String(50), nullable=True)  # Urology, ENT, Hospital Medicine

    role = Column(String(50), nullable=False, default="user")  # user, admin
    is_active = Column(Boolean, default=True, nullable=False)

    # OpenEvidence credentials (encrypted)
    openevidence_username = Column(String(255), nullable=True)
    openevidence_password_encrypted = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('ix_users_email_active', 'email', 'is_active'),
    )


class SessionLog(Base):
    """Session metadata logs (NO PHI - metadata only)."""

    __tablename__ = "session_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), nullable=False, index=True)  # UUID
    user_id = Column(String(36), nullable=False, index=True)

    # Session metadata (NO PHI)
    note_type = Column(String(50), nullable=True)  # clinic_note, consult, preop, postop
    llm_provider = Column(String(50), nullable=True)  # ollama, anthropic, openai
    model_used = Column(String(100), nullable=True)
    selected_modules = Column(JSON, nullable=True)  # List of calculator IDs used

    # Performance metrics
    generation_time_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index('ix_session_logs_user_created', 'user_id', 'created_at'),
        Index('ix_session_logs_expires', 'expires_at'),
    )


class AuditLog(Base):
    """Audit log for system actions (NO PHI - metadata only)."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=False, index=True)

    # Action metadata (NO PHI)
    action = Column(String(100), nullable=False)  # note_generation, calculator_use, etc.
    module_used = Column(String(100), nullable=True)  # Specific calculator or tool

    # Input/Output hashes (NOT actual content)
    input_hash = Column(String(64), nullable=True)  # SHA256 hash
    output_hash = Column(String(64), nullable=True)  # SHA256 hash

    # LLM metadata
    llm_provider = Column(String(50), nullable=True)
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)

    # Performance and status
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_code = Column(String(50), nullable=True)  # Non-descriptive error code (VAUCDA-###)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_audit_logs_user_created', 'user_id', 'created_at'),
        Index('ix_audit_logs_action', 'action'),
    )


class UserPreferences(Base):
    """User preferences and settings."""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), unique=True, nullable=False, index=True)

    # Legacy LLM preferences (kept for backwards compatibility)
    default_llm = Column(String(50), nullable=False, default="ollama")
    default_model = Column(String(100), nullable=False, default=_default_model_factory)

    # Legacy LLM generation parameters
    llm_temperature = Column(JSON, nullable=True)  # Default: 0.3
    llm_max_tokens = Column(Integer, nullable=True, default=4000)
    llm_num_ctx = Column(Integer, nullable=True, default=None)  # User override for input context window; NULL defers to lookup table
    llm_top_p = Column(JSON, nullable=True)  # Default: 0.9
    llm_frequency_penalty = Column(JSON, nullable=True)  # Default: 0.0
    llm_presence_penalty = Column(JSON, nullable=True)  # Default: 0.0

    # ==========================================================================
    # Task-Specific LLM Configuration
    # Each task (OCR, Stage 1, Stage 2) has its own provider, model, temperature
    # NOTE: Default values come from environment variables via Settings API layer
    # These columns are nullable to allow the API layer to apply env-based defaults
    # ==========================================================================

    # OCR Processing LLM Configuration
    ocr_llm_provider = Column(String(50), nullable=True)  # Default from env: OCR_LLM_PROVIDER
    ocr_llm_model = Column(String(100), nullable=True)  # Default from env: OCR_LLM_MODEL
    ocr_llm_temperature = Column(Float, nullable=True)  # Default from env: OCR_LLM_TEMPERATURE
    ocr_llm_max_tokens = Column(Integer, nullable=True)  # Default from env: OCR_LLM_MAX_TOKENS
    ocr_llm_num_ctx = Column(Integer, nullable=True, default=None)  # User-set input context window for OCR; NULL defers to model lookup

    # Stage 1: Note Generation/Extraction LLM Configuration
    stage1_llm_provider = Column(String(50), nullable=True)  # Default from env: STAGE1_LLM_PROVIDER
    stage1_llm_model = Column(String(100), nullable=True)  # Default from env: STAGE1_LLM_MODEL
    stage1_llm_temperature = Column(Float, nullable=True)  # Default from env: STAGE1_LLM_TEMPERATURE
    stage1_llm_max_tokens = Column(Integer, nullable=True)  # Default from env: STAGE1_LLM_MAX_TOKENS
    stage1_llm_num_ctx = Column(Integer, nullable=True, default=None)  # User-set input context window for Stage 1; NULL defers to model lookup

    # Stage 2: Assessment & Plan LLM Configuration (with RAG/GraphRAG)
    stage2_llm_provider = Column(String(50), nullable=True)  # Default from env: STAGE2_LLM_PROVIDER
    stage2_llm_model = Column(String(100), nullable=True)  # Default from env: STAGE2_LLM_MODEL
    stage2_llm_temperature = Column(Float, nullable=True)  # Default from env: STAGE2_LLM_TEMPERATURE
    stage2_llm_max_tokens = Column(Integer, nullable=True)  # Default from env: STAGE2_LLM_MAX_TOKENS
    stage2_llm_num_ctx = Column(Integer, nullable=True, default=None)  # User-set input context window for Stage 2; NULL defers to model lookup

    # RAG/GraphRAG Configuration for Stage 2 (defaults from env)
    stage2_use_rag = Column(Boolean, nullable=True)  # Default from env: STAGE2_USE_RAG
    stage2_use_graphrag = Column(Boolean, nullable=True)  # Default from env: STAGE2_USE_GRAPHRAG
    stage2_rag_top_k = Column(Integer, nullable=True)  # Default from env: STAGE2_RAG_TOP_K

    # Template preferences
    default_template = Column(String(100), nullable=False, default="urology_clinic")

    # Module defaults (JSON)
    module_defaults = Column(JSON, nullable=True)

    # Display preferences (JSON)
    display_preferences = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class UserRule(Base):
    """User-defined rules injected into the Assessment & Plan LLM prompt.

    Each rule is a short natural-language directive (e.g. "When ordering
    TRUS biopsy, also order a rectal swab for quinolone-resistant bacteria").
    Rules are loaded by ``LLMConfigManager`` and rendered as a dedicated
    "USER-DEFINED RULES" section in the Assessment and Plan agent prompts.
    """

    __tablename__ = "user_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=False, index=True)

    rule_text = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index('ix_user_rules_user_active', 'user_id', 'is_active'),
    )


class TemplateVersion(Base):
    """Template version history."""

    __tablename__ = "template_versions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String(36), nullable=False, index=True)
    version = Column(Integer, nullable=False)

    # Template content
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # clinic_note, consult, preop, postop
    content = Column(Text, nullable=False)
    sections = Column(JSON, nullable=True)  # List of section names

    # Metadata
    active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(36), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_template_versions_template_version', 'template_id', 'version', unique=True),
        Index('ix_template_versions_active', 'template_id', 'active'),
    )


class LLMModelCache(Base):
    """Cache metadata for LLM models."""

    __tablename__ = "llm_model_cache"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), unique=True, nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # ollama, anthropic, openai

    # Model metadata
    last_pulled = Column(DateTime(timezone=True), nullable=True)
    size_mb = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False, default="available")  # available, pulling, failed

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class CalculatorStats(Base):
    """Calculator usage statistics (aggregated, NO PHI)."""

    __tablename__ = "calculator_stats"

    id = Column(Integer, primary_key=True, index=True)
    calculator_id = Column(String(100), nullable=False, index=True)
    usage_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # Statistics
    usage_count = Column(Integer, nullable=False, default=0)
    avg_computation_time_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_calculator_stats_calc_date', 'calculator_id', 'usage_date', unique=True),
    )
