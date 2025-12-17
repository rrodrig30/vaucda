"""
Authentication API endpoints
Handles user registration, login, token refresh, and user management
"""
from datetime import datetime, timedelta
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet
import base64

from app.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
    get_current_user,
    get_current_active_user
)
from app.database.sqlite_models import User
from app.database.sqlite_session import get_db
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    TokenRefresh,
    UserResponse,
    PasswordChange
)


router = APIRouter()


def encrypt_openevidence_password(password: str) -> str:
    """Encrypt OpenEvidence password using Fernet symmetric encryption."""
    if not settings.OPENEVIDENCE_ENCRYPTION_KEY:
        raise ValueError("OPENEVIDENCE_ENCRYPTION_KEY not configured")

    # Ensure key is properly formatted for Fernet
    key = settings.OPENEVIDENCE_ENCRYPTION_KEY.encode()
    if len(key) != 44:  # Fernet keys must be 44 bytes (32 bytes base64-encoded)
        # Generate a valid key from the provided string
        key = base64.urlsafe_b64encode(key[:32].ljust(32, b'0'))

    fernet = Fernet(key)
    encrypted = fernet.encrypt(password.encode())
    return encrypted.decode()


def decrypt_openevidence_password(encrypted_password: str) -> str:
    """Decrypt OpenEvidence password."""
    if not settings.OPENEVIDENCE_ENCRYPTION_KEY:
        raise ValueError("OPENEVIDENCE_ENCRYPTION_KEY not configured")

    key = settings.OPENEVIDENCE_ENCRYPTION_KEY.encode()
    if len(key) != 44:
        key = base64.urlsafe_b64encode(key[:32].ljust(32, b'0'))

    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted_password.encode())
    return decrypted.decode()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user.

    - **email**: User email address (must be unique)
    - **password**: User password (min 8 characters, must include uppercase, lowercase, and digit)
    - **first_name**: User first name
    - **last_name**: User last name
    - **initials**: User initials (uppercase letters)
    - **position**: User position (Physician-Faculty, Physician-Fellow, etc.)
    - **specialty**: User specialty (Urology, ENT, Hospital Medicine)
    - **openevidence_username**: Optional OpenEvidence username
    - **openevidence_password**: Optional OpenEvidence password (will be encrypted)

    Special handling:
    - Users with email rodriguezr32@uthscsa.edu automatically receive admin role
    - All other users receive user role
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )

    # Encrypt OpenEvidence password if provided
    encrypted_oe_password = None
    if user_data.openevidence_password:
        try:
            encrypted_oe_password = encrypt_openevidence_password(user_data.openevidence_password)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to encrypt OpenEvidence credentials: {str(e)}"
            )

    # Determine user role based on email
    # Admin role for rodriguezr32@uthscsa.edu, user role for everyone else
    user_role = "admin" if user_data.email.lower() == "rodriguezr32@uthscsa.edu" else "user"

    # Construct full_name for backwards compatibility
    full_name = f"{user_data.first_name} {user_data.last_name}"

    # Create new user
    new_user = User(
        user_id=str(uuid.uuid4()),
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        full_name=full_name,
        initials=user_data.initials,
        position=user_data.position,
        specialty=user_data.specialty,
        role=user_role,
        is_active=True,
        openevidence_username=user_data.openevidence_username,
        openevidence_password_encrypted=encrypted_oe_password,
        created_at=datetime.utcnow()
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse(
        user_id=new_user.user_id,
        email=new_user.email,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        full_name=new_user.full_name,
        initials=new_user.initials,
        position=new_user.position,
        specialty=new_user.specialty,
        role=new_user.role,
        is_active=new_user.is_active,
        created_at=new_user.created_at.isoformat(),
        last_login=new_user.last_login.isoformat() if new_user.last_login else None
    )


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login and obtain JWT tokens.

    - **email**: User email address
    - **password**: User password

    Returns access token and refresh token.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    # Verify user exists and password is correct
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    # Create tokens
    access_token = create_access_token(data={"sub": user.user_id, "email": user.email})
    refresh_token = create_refresh_token(data={"sub": user.user_id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/token", response_model=Token)
async def get_token(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2-compatible token endpoint.

    Accepts form data with username (treated as email) and password.
    Returns access token and refresh token.

    This endpoint is compatible with OAuth2 password flow.
    """
    # Find user by email (username field is treated as email)
    result = await db.execute(
        select(User).where(User.email == username)
    )
    user = result.scalar_one_or_none()

    # Verify user exists and password is correct
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    # Create tokens
    access_token = create_access_token(data={"sub": user.user_id, "email": user.email})
    refresh_token = create_refresh_token(data={"sub": user.user_id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    - **refresh_token**: Valid refresh token

    Returns new access token and refresh token.
    """
    try:
        payload = decode_token(token_data.refresh_token)

        # Verify token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(User.user_id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": user.user_id, "email": user.email})
    refresh_token = create_refresh_token(data={"sub": user.user_id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user information.
    Requires valid access token.
    """
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        full_name=current_user.full_name,
        initials=current_user.initials,
        position=current_user.position,
        specialty=current_user.specialty,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
        last_login=current_user.last_login.isoformat() if current_user.last_login else None
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password.
    Requires valid access token and current password.
    """
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": "Password updated successfully"}
