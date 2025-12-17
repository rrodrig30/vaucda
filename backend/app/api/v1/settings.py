"""
User Settings API endpoints
Handles user preferences and configuration
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_optional_user
from app.database.sqlite_models import User, UserPreferences
from app.database.sqlite_session import get_db
from app.config import settings
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


router = APIRouter()


# Request/Response Models
class UserSettingsResponse(BaseModel):
    """Response model for user settings."""
    default_llm: str = Field(..., description="Default LLM provider (ollama, anthropic, openai)")
    default_model: str = Field(..., description="Default LLM model name")
    default_template: str = Field(..., description="Default note template")
    llm_temperature: Optional[float] = Field(0.3, description="LLM temperature (0.0-1.0)")
    llm_max_tokens: Optional[int] = Field(4000, description="Maximum tokens to generate")
    llm_top_p: Optional[float] = Field(0.9, description="Top-p sampling parameter")
    llm_frequency_penalty: Optional[float] = Field(0.0, description="Frequency penalty")
    llm_presence_penalty: Optional[float] = Field(0.0, description="Presence penalty")
    module_defaults: Optional[Dict[str, Any]] = Field(None, description="Default modules configuration")
    display_preferences: Optional[Dict[str, Any]] = Field(None, description="Display preferences")
    openevidence_configured: bool = Field(False, description="Whether OpenEvidence is configured")

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """Request model for updating user settings."""
    default_llm: Optional[str] = Field(None, description="Default LLM provider")
    default_model: Optional[str] = Field(None, description="Default LLM model")
    default_template: Optional[str] = Field(None, description="Default note template")
    llm_temperature: Optional[float] = Field(None, description="LLM temperature (0.0-1.0)")
    llm_max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    llm_top_p: Optional[float] = Field(None, description="Top-p sampling parameter")
    llm_frequency_penalty: Optional[float] = Field(None, description="Frequency penalty")
    llm_presence_penalty: Optional[float] = Field(None, description="Presence penalty")
    module_defaults: Optional[Dict[str, Any]] = Field(None, description="Default modules configuration")
    display_preferences: Optional[Dict[str, Any]] = Field(None, description="Display preferences")
    openevidence_username: Optional[str] = Field(None, description="OpenEvidence username")
    openevidence_password: Optional[str] = Field(None, description="OpenEvidence password")


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
        UserSettingsResponse: User settings and preferences
    """
    try:
        # If no authenticated user, return system defaults
        if not current_user:
            logger.info("No authenticated user, returning default settings")
            return UserSettingsResponse(
                default_llm="ollama",
                default_model="llama3.1:8b",
                default_template="urology_clinic",
                llm_temperature=0.3,
                llm_max_tokens=4000,
                llm_top_p=0.9,
                llm_frequency_penalty=0.0,
                llm_presence_penalty=0.0,
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
                default_llm="ollama",
                default_model="llama3.1:8b",
                default_template="urology_clinic",
                module_defaults={},
                display_preferences={}
            )
            db.add(prefs)
            await db.commit()
            await db.refresh(prefs)
            logger.info(f"Created default preferences for user {current_user.user_id}")

        return UserSettingsResponse(
            default_llm=prefs.default_llm,
            default_model=prefs.default_model,
            default_template=prefs.default_template,
            llm_temperature=prefs.llm_temperature or 0.3,
            llm_max_tokens=prefs.llm_max_tokens or 4000,
            llm_top_p=prefs.llm_top_p or 0.9,
            llm_frequency_penalty=prefs.llm_frequency_penalty or 0.0,
            llm_presence_penalty=prefs.llm_presence_penalty or 0.0,
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
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user settings.

    Updates user preferences with the provided values. Only non-null fields
    are updated. OpenEvidence credentials are encrypted before storage.

    If no user is authenticated, returns defaults (changes are not persisted).

    Args:
        settings_update: Settings to update (partial update allowed)
        current_user: Optional authenticated user
        db: Database session

    Returns:
        UserSettingsResponse: Updated user settings

    Raises:
        HTTPException: 500 if update fails
    """
    try:
        # If no authenticated user, return defaults (can't persist changes)
        if not current_user:
            logger.warning("Settings update attempted without authentication - returning defaults")
            return UserSettingsResponse(
                default_llm=settings_update.default_llm or "ollama",
                default_model=settings_update.default_model or "llama3.1:8b",
                default_template=settings_update.default_template or "urology_clinic",
                llm_temperature=settings_update.llm_temperature or 0.3,
                llm_max_tokens=settings_update.llm_max_tokens or 4000,
                llm_top_p=settings_update.llm_top_p or 0.9,
                llm_frequency_penalty=settings_update.llm_frequency_penalty or 0.0,
                llm_presence_penalty=settings_update.llm_presence_penalty or 0.0,
                module_defaults=settings_update.module_defaults or {},
                display_preferences=settings_update.display_preferences or {},
                openevidence_configured=False
            )

        # Get existing preferences
        stmt = select(UserPreferences).where(UserPreferences.user_id == current_user.user_id)
        result = await db.execute(stmt)
        prefs = result.scalars().first()

        # Create if doesn't exist
        if not prefs:
            prefs = UserPreferences(
                user_id=current_user.user_id,
                default_llm="ollama",
                default_model="llama3.1:8b",
                default_template="urology_clinic"
            )
            db.add(prefs)

        # Update preference fields
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
        if settings_update.llm_top_p is not None:
            prefs.llm_top_p = settings_update.llm_top_p
        if settings_update.llm_frequency_penalty is not None:
            prefs.llm_frequency_penalty = settings_update.llm_frequency_penalty
        if settings_update.llm_presence_penalty is not None:
            prefs.llm_presence_penalty = settings_update.llm_presence_penalty
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

        return UserSettingsResponse(
            default_llm=prefs.default_llm,
            default_model=prefs.default_model,
            default_template=prefs.default_template,
            llm_temperature=prefs.llm_temperature or 0.3,
            llm_max_tokens=prefs.llm_max_tokens or 4000,
            llm_top_p=prefs.llm_top_p or 0.9,
            llm_frequency_penalty=prefs.llm_frequency_penalty or 0.0,
            llm_presence_penalty=prefs.llm_presence_penalty or 0.0,
            module_defaults=prefs.module_defaults,
            display_preferences=prefs.display_preferences,
            openevidence_configured=bool(current_user.openevidence_username)
        )

    except Exception as e:
        user_info = current_user.user_id if current_user else "anonymous"
        logger.error(f"Error updating settings for user {user_info}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user settings"
        )
