"""Authentication request/response schemas."""
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# Valid dropdown options
VALID_POSITIONS = Literal[
    "Physician-Faculty",
    "Physician-Fellow",
    "Physician-Resident",
    "APP-PA",
    "APP-NP",
    "Staff"
]

VALID_SPECIALTIES = Literal[
    "Urology",
    "ENT",
    "Hospital Medicine"
]


class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    # User profile information
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    initials: str = Field(..., min_length=1, max_length=10)
    position: VALID_POSITIONS
    specialty: VALID_SPECIALTIES

    # OpenEvidence credentials (optional)
    openevidence_username: Optional[str] = Field(None, max_length=255)
    openevidence_password: Optional[str] = Field(None, max_length=255)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("initials")
    @classmethod
    def validate_initials(cls, v: str) -> str:
        """Validate initials are uppercase letters."""
        if not v.isupper():
            raise ValueError("Initials must be uppercase letters")
        if not v.replace(" ", "").isalpha():
            raise ValueError("Initials must only contain letters")
        return v


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefresh(BaseModel):
    """Token refresh request."""
    refresh_token: str


class UserResponse(BaseModel):
    """User information response."""
    user_id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]  # Deprecated, kept for backwards compatibility
    initials: Optional[str]
    position: Optional[str]
    specialty: Optional[str]
    role: str
    is_active: bool
    created_at: str
    last_login: Optional[str]

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    """Password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v
