"""
Pytest configuration and shared fixtures for VAUCDA testing.

Provides:
- Test database fixtures
- Mock LLM providers
- Test data generators
- Integration test helpers
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from faker import Faker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend and parent to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..')
parent_path = os.path.join(os.path.dirname(__file__), '../..')
sys.path.insert(0, backend_path)
sys.path.insert(0, parent_path)

from app.config import Settings
from app.database.sqlite_models import Base
# from app.main import create_app  # Skip for now - has import issues

# Initialize faker for test data
fake = Faker()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings with in-memory databases."""
    return Settings(
        SQLITE_DATABASE_URL="sqlite+aiosqlite:///:memory:",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USER="neo4j",
        NEO4J_PASSWORD="test123",
        REDIS_URL="redis://localhost:6379/0",
        JWT_SECRET_KEY="test-secret-key-for-testing-minimum-32-chars-long",
        DEBUG=True,
        OLLAMA_BASE_URL="http://localhost:11434",
    )


@pytest_asyncio.fixture
async def test_db_engine(test_settings):
    """Create test database engine."""
    engine = create_async_engine(
        test_settings.SQLITE_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_app(test_settings, test_db_session):
    """Create test FastAPI application."""
    # app = create_app()
    from fastapi import FastAPI
    app = FastAPI()

    # Override settings - skip if no dependency injection for settings
    # app.dependency_overrides[get_settings] = lambda: test_settings

    yield app

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    mock = AsyncMock()

    # Mock generate method
    mock.generate = AsyncMock(return_value="Generated clinical note text with proper structure.")

    # Mock generate_stream method
    async def mock_stream(*args, **kwargs):
        chunks = ["Generated ", "clinical ", "note ", "text."]
        for chunk in chunks:
            yield chunk

    mock.generate_stream = mock_stream

    # Mock get_embeddings method
    mock.get_embeddings = AsyncMock(return_value=[0.1] * 768)

    return mock


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j driver for testing."""
    mock_driver = MagicMock()
    mock_session = MagicMock()

    # Mock session context manager
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver.session.return_value.__exit__.return_value = None

    # Mock query results
    mock_result = MagicMock()
    mock_result.data.return_value = [
        {
            "content": "Test guideline content",
            "title": "Test Guideline",
            "source": "AUA",
            "score": 0.95,
        }
    ]
    mock_session.run.return_value = mock_result

    return mock_driver


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    mock = MagicMock()

    # Mock get/set methods
    mock.get = MagicMock(return_value=None)
    mock.set = MagicMock(return_value=True)
    mock.delete = MagicMock(return_value=True)
    mock.exists = MagicMock(return_value=False)

    return mock


# Test data generators


@pytest.fixture
def sample_clinical_input() -> str:
    """Generate sample clinical input text."""
    return """
    Patient: 65-year-old male
    Chief Complaint: Elevated PSA

    HPI: Patient presents with PSA of 8.5 ng/mL on routine screening.
    Prior PSA values: 6.2 (1 year ago), 7.1 (6 months ago).
    No urinary symptoms. No hematuria.

    PMH: Hypertension, Type 2 Diabetes

    Medications: Metformin 1000mg BID, Lisinopril 20mg daily

    Family History: Father with prostate cancer at age 70

    Physical Exam:
    - DRE: Prostate approximately 40g, smooth, no nodules
    - No suprapubic tenderness

    Labs:
    - PSA: 8.5 ng/mL
    - Free PSA: 15%
    - Creatinine: 1.1 mg/dL

    Assessment: Elevated PSA with family history of prostate cancer

    Plan: Discuss prostate biopsy options. Risk stratification.
    """


@pytest.fixture
def sample_calculator_inputs() -> dict:
    """Generate sample calculator inputs."""
    return {
        "psa_kinetics": {
            "psa_values": [6.2, 7.1, 8.5],
            "time_points": [0, 6, 12],  # months
        },
        "pcpt_risk": {
            "age": 65,
            "race": "caucasian",
            "family_history": True,
            "psa": 8.5,
            "dre_abnormal": False,
            "prior_biopsy": False,
        },
        "capra": {
            "psa": 8.5,
            "gleason_primary": 3,
            "gleason_secondary": 4,
            "clinical_stage": "T2a",
            "percent_positive_cores": 30,
            "age": 65,
        },
    }


@pytest.fixture
def expected_calculator_results() -> dict:
    """Expected calculator results for validation."""
    return {
        "psa_kinetics": {
            "psav": pytest.approx(2.3, rel=0.1),  # ng/mL/year
            "psadt": pytest.approx(9.5, rel=0.2),  # months
        },
        "pcpt_risk": {
            "cancer_risk": pytest.approx(0.23, rel=0.05),
            "high_grade_risk": pytest.approx(0.08, rel=0.02),
        },
        "capra": {
            "score": 4,  # 0-10 scale
            "risk_category": "intermediate",
        },
    }


@pytest.fixture
def sample_note_templates() -> dict:
    """Sample note templates for testing."""
    return {
        "clinic": {
            "name": "Urology Clinic Note",
            "sections": ["CC", "HPI", "PMH", "Medications", "PE", "Assessment", "Plan"],
        },
        "consult": {
            "name": "Urology Consult",
            "sections": ["Reason for Consult", "HPI", "Review of Systems", "Assessment", "Recommendations"],
        },
    }


@pytest.fixture
def sample_rag_documents() -> list:
    """Sample RAG documents for testing."""
    return [
        {
            "id": "doc1",
            "title": "AUA Prostate Cancer Guidelines 2024",
            "content": "For patients with localized prostate cancer, active surveillance is recommended for low-risk disease.",
            "source": "AUA",
            "category": "prostate",
            "embedding": [0.1] * 768,
        },
        {
            "id": "doc2",
            "title": "NCCN Prostate Cancer Guidelines",
            "content": "Risk stratification should include PSA, Gleason score, and clinical stage.",
            "source": "NCCN",
            "category": "prostate",
            "embedding": [0.2] * 768,
        },
    ]


# Authentication fixtures


@pytest.fixture
def test_user_data() -> dict:
    """Test user data."""
    return {
        "username": "test_urologist",
        "email": "test@vaucda.test",
        "password": "SecureTestPassword123!",
        "full_name": "Dr. Test Urologist",
    }


@pytest_asyncio.fixture
async def authenticated_client(test_client, test_user_data) -> AsyncClient:
    """Client with authentication token."""
    # Register user
    response = await test_client.post("/api/v1/auth/register", json=test_user_data)
    assert response.status_code == 200

    # Login
    response = await test_client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["username"], "password": test_user_data["password"]},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    # Set auth header
    test_client.headers["Authorization"] = f"Bearer {token}"

    return test_client


# Performance testing fixtures


@pytest.fixture
def performance_timer():
    """Timer for performance testing."""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = time.time()

        def stop(self):
            self.end_time = time.time()

        @property
        def elapsed_ms(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time) * 1000
            return None

        def assert_max_duration(self, max_ms: float):
            assert self.elapsed_ms is not None, "Timer not stopped"
            assert self.elapsed_ms < max_ms, f"Duration {self.elapsed_ms}ms exceeds max {max_ms}ms"

    return Timer()


# Markers for test categorization


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "calculator: Calculator tests")
    config.addinivalue_line("markers", "rag: RAG pipeline tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
