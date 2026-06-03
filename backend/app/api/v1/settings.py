"""
User Settings API endpoints
Handles user preferences and configuration
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_optional_user, get_current_user
from app.database.sqlite_models import User, UserPreferences
from app.database.sqlite_session import get_db
from app.config import settings
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


router = APIRouter()


# Request/Response Models
class TaskLLMConfig(BaseModel):
    """Configuration for a specific LLM task."""
    provider: str = Field(..., description="LLM provider (ollama, anthropic, openai)")
    model: str = Field(..., description="LLM model name")
    temperature: float = Field(..., description="Temperature (0.0-1.0)")
    max_tokens: int = Field(..., description="Maximum tokens to generate (Ollama: num_predict)")
    num_ctx: Optional[int] = Field(None, description="Input context window in tokens (Ollama: num_ctx). Null = use model lookup table or default.")


class Stage2LLMConfig(TaskLLMConfig):
    """Configuration for Stage 2 LLM with RAG settings."""
    use_rag: bool = Field(True, description="Enable RAG retrieval")
    use_graphrag: bool = Field(True, description="Enable GraphRAG retrieval")
    rag_top_k: int = Field(5, description="Number of documents to retrieve")


class UserSettingsResponse(BaseModel):
    """Response model for user settings."""
    # Legacy fields (kept for backwards compatibility)
    default_llm: str = Field(..., description="Default LLM provider (ollama, anthropic, openai)")
    default_model: str = Field(..., description="Default LLM model name")
    default_template: str = Field(..., description="Default note template")
    llm_temperature: Optional[float] = Field(0.3, description="LLM temperature (0.0-1.0)")
    llm_max_tokens: Optional[int] = Field(4000, description="Maximum tokens to generate")
    llm_num_ctx: Optional[int] = Field(None, description="Default input context window (tokens)")
    llm_top_p: Optional[float] = Field(0.9, description="Top-p sampling parameter")
    llm_frequency_penalty: Optional[float] = Field(0.0, description="Frequency penalty")
    llm_presence_penalty: Optional[float] = Field(0.0, description="Presence penalty")

    # Task-Specific LLM Configuration
    ocr_llm: TaskLLMConfig = Field(..., description="OCR processing LLM configuration")
    stage1_llm: TaskLLMConfig = Field(..., description="Stage 1 note generation LLM configuration")
    stage2_llm: Stage2LLMConfig = Field(..., description="Stage 2 Assessment & Plan LLM configuration")

    module_defaults: Optional[Dict[str, Any]] = Field(None, description="Default modules configuration")
    display_preferences: Optional[Dict[str, Any]] = Field(None, description="Display preferences")
    openevidence_configured: bool = Field(False, description="Whether OpenEvidence is configured")

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """Request model for updating user settings."""
    # Legacy fields
    default_llm: Optional[str] = Field(None, description="Default LLM provider")
    default_model: Optional[str] = Field(None, description="Default LLM model")
    default_template: Optional[str] = Field(None, description="Default note template")
    llm_temperature: Optional[float] = Field(None, description="LLM temperature (0.0-1.0)")
    llm_max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    llm_num_ctx: Optional[int] = Field(None, ge=512, le=2_000_000, description="Input context window (tokens)")
    llm_top_p: Optional[float] = Field(None, description="Top-p sampling parameter")
    llm_frequency_penalty: Optional[float] = Field(None, description="Frequency penalty")
    llm_presence_penalty: Optional[float] = Field(None, description="Presence penalty")

    # Task-Specific LLM Configuration
    # OCR LLM settings
    ocr_llm_provider: Optional[str] = Field(None, description="OCR LLM provider")
    ocr_llm_model: Optional[str] = Field(None, description="OCR LLM model")
    ocr_llm_temperature: Optional[float] = Field(None, description="OCR LLM temperature")
    ocr_llm_max_tokens: Optional[int] = Field(None, description="OCR LLM max tokens")
    ocr_llm_num_ctx: Optional[int] = Field(None, ge=512, le=2_000_000, description="OCR input context window (tokens)")

    # Stage 1 LLM settings
    stage1_llm_provider: Optional[str] = Field(None, description="Stage 1 LLM provider")
    stage1_llm_model: Optional[str] = Field(None, description="Stage 1 LLM model")
    stage1_llm_temperature: Optional[float] = Field(None, description="Stage 1 LLM temperature")
    stage1_llm_max_tokens: Optional[int] = Field(None, description="Stage 1 LLM max tokens")
    stage1_llm_num_ctx: Optional[int] = Field(None, ge=512, le=2_000_000, description="Stage 1 input context window (tokens)")

    # Stage 2 LLM settings (with RAG)
    stage2_llm_provider: Optional[str] = Field(None, description="Stage 2 LLM provider")
    stage2_llm_model: Optional[str] = Field(None, description="Stage 2 LLM model")
    stage2_llm_temperature: Optional[float] = Field(None, description="Stage 2 LLM temperature")
    stage2_llm_max_tokens: Optional[int] = Field(None, description="Stage 2 LLM max tokens")
    stage2_llm_num_ctx: Optional[int] = Field(None, ge=512, le=2_000_000, description="Stage 2 input context window (tokens)")
    stage2_use_rag: Optional[bool] = Field(None, description="Enable RAG for Stage 2")
    stage2_use_graphrag: Optional[bool] = Field(None, description="Enable GraphRAG for Stage 2")
    stage2_rag_top_k: Optional[int] = Field(None, description="RAG top-k retrieval")

    module_defaults: Optional[Dict[str, Any]] = Field(None, description="Default modules configuration")
    display_preferences: Optional[Dict[str, Any]] = Field(None, description="Display preferences")
    openevidence_username: Optional[str] = Field(None, description="OpenEvidence username")
    openevidence_password: Optional[str] = Field(None, description="OpenEvidence password")


def _build_default_task_configs():
    """Build default task-specific LLM configurations from environment variables."""
    return {
        "ocr_llm": TaskLLMConfig(
            provider=settings.OCR_LLM_PROVIDER,
            model=settings.OCR_LLM_MODEL,
            temperature=settings.OCR_LLM_TEMPERATURE,
            max_tokens=settings.OCR_LLM_MAX_TOKENS,
            num_ctx=None,
        ),
        "stage1_llm": TaskLLMConfig(
            provider=settings.STAGE1_LLM_PROVIDER,
            model=settings.STAGE1_LLM_MODEL,
            temperature=settings.STAGE1_LLM_TEMPERATURE,
            max_tokens=settings.STAGE1_LLM_MAX_TOKENS,
            num_ctx=None,
        ),
        "stage2_llm": Stage2LLMConfig(
            provider=settings.STAGE2_LLM_PROVIDER,
            model=settings.STAGE2_LLM_MODEL,
            temperature=settings.STAGE2_LLM_TEMPERATURE,
            max_tokens=settings.STAGE2_LLM_MAX_TOKENS,
            num_ctx=None,
            use_rag=settings.STAGE2_USE_RAG,
            use_graphrag=settings.STAGE2_USE_GRAPHRAG,
            rag_top_k=settings.STAGE2_RAG_TOP_K
        )
    }


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user settings.

    Retrieves user preferences from the database. If no user is authenticated,
    returns default settings. If authenticated but no preferences exist,
    creates default preferences with standard values.

    Returns:
        UserSettingsResponse: User settings and preferences with task-specific LLM configs
    """
    try:
        default_configs = _build_default_task_configs()

        # If no authenticated user, return system defaults from environment
        if not current_user:
            logger.info("No authenticated user, returning default settings from environment")
            return UserSettingsResponse(
                default_llm=settings.STAGE1_LLM_PROVIDER,
                default_model=settings.STAGE1_LLM_MODEL,
                default_template="urology_clinic",
                llm_temperature=settings.STAGE1_LLM_TEMPERATURE,
                llm_max_tokens=settings.STAGE1_LLM_MAX_TOKENS,
                llm_num_ctx=None,
                llm_top_p=0.9,
                llm_frequency_penalty=0.0,
                llm_presence_penalty=0.0,
                ocr_llm=default_configs["ocr_llm"],
                stage1_llm=default_configs["stage1_llm"],
                stage2_llm=default_configs["stage2_llm"],
                module_defaults={},
                display_preferences={},
                openevidence_configured=False
            )

        # Query user preferences
        stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
        result = await db.execute(stmt)
        prefs = result.scalars().first()

        # Create default preferences if none exist
        if not prefs:
            prefs = UserPreferences(
                user_id=current_user.user_id,
                default_llm=settings.STAGE1_LLM_PROVIDER,
                default_model=settings.STAGE1_LLM_MODEL,
                default_template="urology_clinic",
                module_defaults={},
                display_preferences={}
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)
            logger.info(f"Created default preferences for user {current_user.user_id}")

        # Build task-specific LLM configs from user preferences with env fallbacks
        # IMPORTANT: Use explicit None checks, NOT 'or' operator, because empty strings are valid values
        # num_ctx: pass user value through unchanged (None means "defer to lookup table")
        ocr_llm = TaskLLMConfig(
            provider=prefs.ocr_llm_provider if prefs.ocr_llm_provider is not None else settings.OCR_LLM_PROVIDER,
            model=prefs.ocr_llm_model if prefs.ocr_llm_model is not None else settings.OCR_LLM_MODEL,
            temperature=prefs.ocr_llm_temperature if prefs.ocr_llm_temperature is not None else settings.OCR_LLM_TEMPERATURE,
            max_tokens=prefs.ocr_llm_max_tokens if prefs.ocr_llm_max_tokens is not None else settings.OCR_LLM_MAX_TOKENS,
            num_ctx=prefs.ocr_llm_num_ctx,
        )

        stage1_llm = TaskLLMConfig(
            provider=prefs.stage1_llm_provider if prefs.stage1_llm_provider is not None else settings.STAGE1_LLM_PROVIDER,
            model=prefs.stage1_llm_model if prefs.stage1_llm_model is not None else settings.STAGE1_LLM_MODEL,
            temperature=prefs.stage1_llm_temperature if prefs.stage1_llm_temperature is not None else settings.STAGE1_LLM_TEMPERATURE,
            max_tokens=prefs.stage1_llm_max_tokens if prefs.stage1_llm_max_tokens is not None else settings.STAGE1_LLM_MAX_TOKENS,
            num_ctx=prefs.stage1_llm_num_ctx,
        )

        stage2_llm = Stage2LLMConfig(
            provider=prefs.stage2_llm_provider if prefs.stage2_llm_provider is not None else settings.STAGE2_LLM_PROVIDER,
            model=prefs.stage2_llm_model if prefs.stage2_llm_model is not None else settings.STAGE2_LLM_MODEL,
            temperature=prefs.stage2_llm_temperature if prefs.stage2_llm_temperature is not None else settings.STAGE2_LLM_TEMPERATURE,
            max_tokens=prefs.stage2_llm_max_tokens if prefs.stage2_llm_max_tokens is not None else settings.STAGE2_LLM_MAX_TOKENS,
            num_ctx=prefs.stage2_llm_num_ctx,
            use_rag=prefs.stage2_use_rag if prefs.stage2_use_rag is not None else settings.STAGE2_USE_RAG,
            use_graphrag=prefs.stage2_use_graphrag if prefs.stage2_use_graphrag is not None else settings.STAGE2_USE_GRAPHRAG,
            rag_top_k=prefs.stage2_rag_top_k if prefs.stage2_rag_top_k is not None else settings.STAGE2_RAG_TOP_K
        )

        return UserSettingsResponse(
            default_llm=prefs.default_llm,
            default_model=prefs.default_model,
            default_template=prefs.default_template,
            # IMPORTANT: Use explicit None checks for zero-value preservation
            llm_temperature=prefs.llm_temperature if prefs.llm_temperature is not None else 0.3,
            llm_max_tokens=prefs.llm_max_tokens if prefs.llm_max_tokens is not None else 4000,
            llm_num_ctx=prefs.llm_num_ctx,
            llm_top_p=prefs.llm_top_p if prefs.llm_top_p is not None else 0.9,
            llm_frequency_penalty=prefs.llm_frequency_penalty if prefs.llm_frequency_penalty is not None else 0.0,
            llm_presence_penalty=prefs.llm_presence_penalty if prefs.llm_presence_penalty is not None else 0.0,
            ocr_llm=ocr_llm,
            stage1_llm=stage1_llm,
            stage2_llm=stage2_llm,
            module_defaults=prefs.module_defaults,
            display_preferences=prefs.display_preferences,
            openevidence_configured=bool(current_user.openevidence_username)
        )

    except Exception as e:
        user_info = current_user.user_id if current_user else "anonymous"
        logger.error(f"Error retrieving settings for user {user_info}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user settings"
        )


@router.put("", response_model=UserSettingsResponse)
async def update_settings(
    settings_update: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user settings.

    Updates user preferences with the provided values. Only non-null fields
    are updated. OpenEvidence credentials are encrypted before storage.

    Requires authentication - returns 401 if not authenticated.

    Args:
        settings_update: Settings to update (partial update allowed)
        current_user: Authenticated user (required)
        db: Database session

    Returns:
        UserSettingsResponse: Updated user settings

    Raises:
        HTTPException: 401 if not authenticated, 500 if update fails
    """
    logger.info(f"PUT /settings - user: {current_user.user_id}")

    try:
        default_configs = _build_default_task_configs()

        # Get existing preferences
        stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
        result = await db.execute(stmt)
        prefs = result.scalars().first()

        # Create if doesn't exist
        if not prefs:
            prefs = UserPreferences(
                user_id=current_user.user_id,
                default_llm=settings.STAGE1_LLM_PROVIDER,
                default_model=settings.STAGE1_LLM_MODEL,
                default_template="urology_clinic"
            )
            db.add(prefs)

        # Update legacy preference fields
        if settings_update.default_llm is not None:
            prefs.default_llm = settings_update.default_llm
        if settings_update.default_model is not None:
            prefs.default_model = settings_update.default_model
        if settings_update.default_template is not None:
            prefs.default_template = settings_update.default_template
        if settings_update.llm_temperature is not None:
            prefs.llm_temperature = settings_update.llm_temperature
        if settings_update.llm_max_tokens is not None:
            prefs.llm_max_tokens = settings_update.llm_max_tokens
        if settings_update.llm_num_ctx is not None:
            prefs.llm_num_ctx = settings_update.llm_num_ctx
        if settings_update.llm_top_p is not None:
            prefs.llm_top_p = settings_update.llm_top_p
        if settings_update.llm_frequency_penalty is not None:
            prefs.llm_frequency_penalty = settings_update.llm_frequency_penalty
        if settings_update.llm_presence_penalty is not None:
            prefs.llm_presence_penalty = settings_update.llm_presence_penalty

        # Update OCR LLM configuration
        if settings_update.ocr_llm_provider is not None:
            prefs.ocr_llm_provider = settings_update.ocr_llm_provider
        if settings_update.ocr_llm_model is not None:
            prefs.ocr_llm_model = settings_update.ocr_llm_model
        if settings_update.ocr_llm_temperature is not None:
            prefs.ocr_llm_temperature = settings_update.ocr_llm_temperature
        if settings_update.ocr_llm_max_tokens is not None:
            prefs.ocr_llm_max_tokens = settings_update.ocr_llm_max_tokens
        if settings_update.ocr_llm_num_ctx is not None:
            prefs.ocr_llm_num_ctx = settings_update.ocr_llm_num_ctx

        # Update Stage 1 LLM configuration
        if settings_update.stage1_llm_provider is not None:
            prefs.stage1_llm_provider = settings_update.stage1_llm_provider
        if settings_update.stage1_llm_model is not None:
            prefs.stage1_llm_model = settings_update.stage1_llm_model
        if settings_update.stage1_llm_temperature is not None:
            prefs.stage1_llm_temperature = settings_update.stage1_llm_temperature
        if settings_update.stage1_llm_max_tokens is not None:
            prefs.stage1_llm_max_tokens = settings_update.stage1_llm_max_tokens
        if settings_update.stage1_llm_num_ctx is not None:
            prefs.stage1_llm_num_ctx = settings_update.stage1_llm_num_ctx

        # Update Stage 2 LLM configuration (with RAG)
        if settings_update.stage2_llm_provider is not None:
            prefs.stage2_llm_provider = settings_update.stage2_llm_provider
        if settings_update.stage2_llm_model is not None:
            prefs.stage2_llm_model = settings_update.stage2_llm_model
        if settings_update.stage2_llm_temperature is not None:
            prefs.stage2_llm_temperature = settings_update.stage2_llm_temperature
        if settings_update.stage2_llm_max_tokens is not None:
            prefs.stage2_llm_max_tokens = settings_update.stage2_llm_max_tokens
        if settings_update.stage2_llm_num_ctx is not None:
            prefs.stage2_llm_num_ctx = settings_update.stage2_llm_num_ctx
        if settings_update.stage2_use_rag is not None:
            prefs.stage2_use_rag = settings_update.stage2_use_rag
        if settings_update.stage2_use_graphrag is not None:
            prefs.stage2_use_graphrag = settings_update.stage2_use_graphrag
        if settings_update.stage2_rag_top_k is not None:
            prefs.stage2_rag_top_k = settings_update.stage2_rag_top_k

        if settings_update.module_defaults is not None:
            prefs.module_defaults = settings_update.module_defaults
        if settings_update.display_preferences is not None:
            prefs.display_preferences = settings_update.display_preferences

        # Update OpenEvidence credentials if provided
        if settings_update.openevidence_username is not None:
            current_user.openevidence_username = settings_update.openevidence_username
        if settings_update.openevidence_password is not None:
            # Encrypt password before storing
            fernet = Fernet(settings.OPENEVIDENCE_ENCRYPTION_KEY.encode())
            encrypted = fernet.encrypt(settings_update.openevidence_password.encode())
            current_user.openevidence_password_encrypted = encrypted.decode()

        # Commit changes
        await db.commit()
        await db.refresh(prefs)

        logger.info(f"Updated settings for user {current_user.user_id}")

        # Build task-specific LLM configs from updated preferences with env fallbacks
        # IMPORTANT: Use explicit None checks, NOT 'or' operator, because empty strings are valid values
        # num_ctx: pass user value through unchanged (None means "defer to lookup table")
        ocr_llm = TaskLLMConfig(
            provider=prefs.ocr_llm_provider if prefs.ocr_llm_provider is not None else settings.OCR_LLM_PROVIDER,
            model=prefs.ocr_llm_model if prefs.ocr_llm_model is not None else settings.OCR_LLM_MODEL,
            temperature=prefs.ocr_llm_temperature if prefs.ocr_llm_temperature is not None else settings.OCR_LLM_TEMPERATURE,
            max_tokens=prefs.ocr_llm_max_tokens if prefs.ocr_llm_max_tokens is not None else settings.OCR_LLM_MAX_TOKENS,
            num_ctx=prefs.ocr_llm_num_ctx,
        )

        stage1_llm = TaskLLMConfig(
            provider=prefs.stage1_llm_provider if prefs.stage1_llm_provider is not None else settings.STAGE1_LLM_PROVIDER,
            model=prefs.stage1_llm_model if prefs.stage1_llm_model is not None else settings.STAGE1_LLM_MODEL,
            temperature=prefs.stage1_llm_temperature if prefs.stage1_llm_temperature is not None else settings.STAGE1_LLM_TEMPERATURE,
            max_tokens=prefs.stage1_llm_max_tokens if prefs.stage1_llm_max_tokens is not None else settings.STAGE1_LLM_MAX_TOKENS,
            num_ctx=prefs.stage1_llm_num_ctx,
        )

        stage2_llm = Stage2LLMConfig(
            provider=prefs.stage2_llm_provider if prefs.stage2_llm_provider is not None else settings.STAGE2_LLM_PROVIDER,
            model=prefs.stage2_llm_model if prefs.stage2_llm_model is not None else settings.STAGE2_LLM_MODEL,
            temperature=prefs.stage2_llm_temperature if prefs.stage2_llm_temperature is not None else settings.STAGE2_LLM_TEMPERATURE,
            max_tokens=prefs.stage2_llm_max_tokens if prefs.stage2_llm_max_tokens is not None else settings.STAGE2_LLM_MAX_TOKENS,
            num_ctx=prefs.stage2_llm_num_ctx,
            use_rag=prefs.stage2_use_rag if prefs.stage2_use_rag is not None else settings.STAGE2_USE_RAG,
            use_graphrag=prefs.stage2_use_graphrag if prefs.stage2_use_graphrag is not None else settings.STAGE2_USE_GRAPHRAG,
            rag_top_k=prefs.stage2_rag_top_k if prefs.stage2_rag_top_k is not None else settings.STAGE2_RAG_TOP_K
        )

        return UserSettingsResponse(
            default_llm=prefs.default_llm,
            default_model=prefs.default_model,
            default_template=prefs.default_template,
            # IMPORTANT: Use explicit None checks for zero-value preservation
            llm_temperature=prefs.llm_temperature if prefs.llm_temperature is not None else 0.3,
            llm_max_tokens=prefs.llm_max_tokens if prefs.llm_max_tokens is not None else 4000,
            llm_num_ctx=prefs.llm_num_ctx,
            llm_top_p=prefs.llm_top_p if prefs.llm_top_p is not None else 0.9,
            llm_frequency_penalty=prefs.llm_frequency_penalty if prefs.llm_frequency_penalty is not None else 0.0,
            llm_presence_penalty=prefs.llm_presence_penalty if prefs.llm_presence_penalty is not None else 0.0,
            ocr_llm=ocr_llm,
            stage1_llm=stage1_llm,
            stage2_llm=stage2_llm,
            module_defaults=prefs.module_defaults,
            display_preferences=prefs.display_preferences,
            openevidence_configured=bool(current_user.openevidence_username)
        )

    except Exception as e:
        logger.error(f"Error updating settings for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user settings"
        )
