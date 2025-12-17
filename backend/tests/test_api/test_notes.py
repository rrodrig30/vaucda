"""
Tests for Notes API endpoints.

Tests:
- Note generation (sync and streaming)
- Template listing
- Calculator integration
- RAG integration
- Error handling
"""

import pytest
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.integration
class TestNoteGeneration:
    """Test note generation endpoints."""

    async def test_generate_basic_note(
        self,
        authenticated_client: AsyncClient,
        sample_clinical_input: str,
        mock_llm_provider,
    ):
        """Test basic note generation."""
        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": sample_clinical_input,
                "note_type": "clinic",
                "llm_provider": "mock",
                "use_rag": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "note_text" in data
        assert "metadata" in data
        assert len(data["note_text"]) > 0

    async def test_generate_note_with_calculators(
        self,
        authenticated_client: AsyncClient,
        sample_clinical_input: str,
    ):
        """Test note generation with calculator integration."""
        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": sample_clinical_input,
                "note_type": "clinic",
                "calculator_ids": ["psa_kinetics", "pcpt_risk"],
                "use_rag": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "calculator_results" in data
        assert len(data["calculator_results"]) == 2

    async def test_generate_note_with_rag(
        self,
        authenticated_client: AsyncClient,
        sample_clinical_input: str,
        mock_neo4j_driver,
    ):
        """Test note generation with RAG integration."""
        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": sample_clinical_input,
                "note_type": "clinic",
                "use_rag": True,
                "rag_category": "prostate",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "rag_sources" in data
        # Should have evidence-based guidance

    async def test_generate_note_invalid_type(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test note generation with invalid note type."""
        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": "Test input",
                "note_type": "invalid_type",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_generate_note_empty_input(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test note generation with empty input."""
        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": "",
                "note_type": "clinic",
            },
        )

        assert response.status_code == 400


@pytest.mark.api
@pytest.mark.integration
class TestNoteStreaming:
    """Test streaming note generation."""

    async def test_streaming_note_generation(
        self,
        authenticated_client: AsyncClient,
        sample_clinical_input: str,
    ):
        """Test streaming note generation via WebSocket."""
        # WebSocket test would require special handling
        # For now, test the streaming endpoint exists
        response = await authenticated_client.get("/api/v1/notes/stream-info")

        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.unit
class TestTemplates:
    """Test template-related endpoints."""

    async def test_list_templates(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test listing available templates."""
        response = await authenticated_client.get("/api/v1/notes/templates")

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert len(data["templates"]) > 0

        # Verify template structure
        template = data["templates"][0]
        assert "id" in template
        assert "name" in template
        assert "type" in template

    async def test_get_specific_template(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting a specific template."""
        response = await authenticated_client.get("/api/v1/notes/templates/clinic")

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "clinic"
        assert "sections" in data


@pytest.mark.api
@pytest.mark.performance
class TestNotePerformance:
    """Test note generation performance."""

    async def test_note_generation_time(
        self,
        authenticated_client: AsyncClient,
        sample_clinical_input: str,
        performance_timer,
    ):
        """Test note generation completes within time limit."""
        performance_timer.start()

        response = await authenticated_client.post(
            "/api/v1/notes/generate",
            json={
                "input_text": sample_clinical_input,
                "note_type": "clinic",
                "use_rag": False,
            },
        )

        performance_timer.stop()

        assert response.status_code == 200
        # Target: < 30 seconds for note generation
        performance_timer.assert_max_duration(30000)
