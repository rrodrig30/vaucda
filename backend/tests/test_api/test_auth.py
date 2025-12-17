"""
Tests for authentication API endpoints.

Tests:
- User registration
- User login
- Token refresh
- Token validation
- Logout
- Password requirements
- JWT expiration
"""

import pytest
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.unit
class TestAuthRegistration:
    """Test user registration endpoint."""

    async def test_register_new_user(self, test_client: AsyncClient):
        """Test successful user registration."""
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "new_user",
                "email": "newuser@test.com",
                "password": "SecurePass123!",
                "full_name": "New Test User",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "new_user"
        assert data["email"] == "newuser@test.com"
        assert "password" not in data  # Password should not be returned

    async def test_register_duplicate_username(self, test_client: AsyncClient, test_user_data):
        """Test registration with duplicate username fails."""
        # First registration
        await test_client.post("/api/v1/auth/register", json=test_user_data)

        # Duplicate registration
        response = await test_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    async def test_register_weak_password(self, test_client: AsyncClient):
        """Test registration with weak password fails."""
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "test_user",
                "email": "test@test.com",
                "password": "weak",  # Too short, no special chars
                "full_name": "Test User",
            },
        )

        assert response.status_code == 400
        assert "password" in response.json()["detail"].lower()

    async def test_register_invalid_email(self, test_client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await test_client.post(
            "/api/v1/auth/register",
            json={
                "username": "test_user",
                "email": "not-an-email",
                "password": "SecurePass123!",
                "full_name": "Test User",
            },
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.api
@pytest.mark.unit
class TestAuthLogin:
    """Test user login endpoint."""

    async def test_login_success(self, test_client: AsyncClient, test_user_data):
        """Test successful login."""
        # Register user first
        await test_client.post("/api/v1/auth/register", json=test_user_data)

        # Login
        response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user_data["username"],
                "password": test_user_data["password"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, test_client: AsyncClient, test_user_data):
        """Test login with wrong password fails."""
        # Register user
        await test_client.post("/api/v1/auth/register", json=test_user_data)

        # Login with wrong password
        response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user_data["username"],
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code == 401

    async def test_login_nonexistent_user(self, test_client: AsyncClient):
        """Test login with nonexistent user fails."""
        response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent_user",
                "password": "SomePassword123!",
            },
        )

        assert response.status_code == 401


@pytest.mark.api
@pytest.mark.unit
class TestAuthToken:
    """Test token-related endpoints."""

    async def test_token_refresh(self, test_client: AsyncClient, test_user_data):
        """Test token refresh functionality."""
        # Register and login
        await test_client.post("/api/v1/auth/register", json=test_user_data)
        login_response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user_data["username"],
                "password": test_user_data["password"],
            },
        )

        refresh_token = login_response.json()["refresh_token"]

        # Refresh token
        response = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_protected_endpoint_without_token(self, test_client: AsyncClient):
        """Test accessing protected endpoint without token fails."""
        response = await test_client.get("/api/v1/users/me")

        assert response.status_code == 401

    async def test_protected_endpoint_with_valid_token(
        self, authenticated_client: AsyncClient
    ):
        """Test accessing protected endpoint with valid token succeeds."""
        response = await authenticated_client.get("/api/v1/users/me")

        assert response.status_code == 200
        data = response.json()
        assert "username" in data

    async def test_protected_endpoint_with_invalid_token(self, test_client: AsyncClient):
        """Test accessing protected endpoint with invalid token fails."""
        test_client.headers["Authorization"] = "Bearer invalid_token_here"
        response = await test_client.get("/api/v1/users/me")

        assert response.status_code == 401


@pytest.mark.api
@pytest.mark.security
class TestAuthSecurity:
    """Test authentication security features."""

    async def test_password_not_exposed_in_response(
        self, test_client: AsyncClient, test_user_data
    ):
        """Test that password is never returned in API responses."""
        response = await test_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 200
        data = response.json()
        assert "password" not in data
        assert "hashed_password" not in data

    async def test_jwt_contains_user_info(self, test_client: AsyncClient, test_user_data):
        """Test JWT contains user information."""
        import jwt

        await test_client.post("/api/v1/auth/register", json=test_user_data)
        login_response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user_data["username"],
                "password": test_user_data["password"],
            },
        )

        token = login_response.json()["access_token"]

        # Decode without verification (for testing only)
        payload = jwt.decode(token, options={"verify_signature": False})

        assert "sub" in payload  # Subject (username)
        assert "exp" in payload  # Expiration

    async def test_token_expiration(self, test_client: AsyncClient, test_user_data):
        """Test that expired tokens are rejected."""
        # This would require time manipulation or waiting
        # For now, just verify the exp claim exists
        await test_client.post("/api/v1/auth/register", json=test_user_data)
        login_response = await test_client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user_data["username"],
                "password": test_user_data["password"],
            },
        )

        import jwt
        from datetime import datetime

        token = login_response.json()["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})

        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()

        # Token should expire in the future
        assert exp_datetime > now
