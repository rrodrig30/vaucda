"""
Tests for RAG API endpoints.

Tests:
- Semantic search
- Calculator recommendations
- OpenEvidence integration
- NSQIP link generation
- Knowledge base statistics
"""

import pytest
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.rag
class TestRAGSearch:
    """Test RAG search endpoints."""

    async def test_semantic_search(
        self,
        authenticated_client: AsyncClient,
        mock_neo4j_driver,
    ):
        """Test semantic search in knowledge base."""
        response = await authenticated_client.post(
            "/api/v1/rag/search",
            json={
                "query": "treatment options for localized prostate cancer",
                "limit": 5,
                "category": "prostate",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) <= 5

    async def test_search_with_category_filter(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test search with category filtering."""
        response = await authenticated_client.post(
            "/api/v1/rag/search",
            json={
                "query": "kidney tumor assessment",
                "category": "kidney",
                "limit": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        for result in data["results"]:
            assert result["category"] == "kidney"

    async def test_hybrid_search_strategy(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test hybrid search strategy."""
        response = await authenticated_client.post(
            "/api/v1/rag/search",
            json={
                "query": "bladder cancer staging",
                "search_strategy": "hybrid",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["strategy"] == "hybrid"

    async def test_graph_search_strategy(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test graph-augmented search."""
        response = await authenticated_client.post(
            "/api/v1/rag/search",
            json={
                "query": "prostate biopsy indications",
                "search_strategy": "graph",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Graph search should include related concepts
        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            # May have related concepts
            assert "content" in result


@pytest.mark.api
@pytest.mark.rag
class TestCalculatorRecommendations:
    """Test calculator recommendation endpoints."""

    async def test_recommend_calculators(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test calculator recommendations based on clinical scenario."""
        response = await authenticated_client.post(
            "/api/v1/rag/recommend-calculators",
            json={
                "clinical_scenario": "65 yo male with PSA 8.5, considering biopsy",
                "category": "prostate",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "recommended_calculators" in data
        # Should recommend PSA-related calculators
        calc_ids = [c["id"] for c in data["recommended_calculators"]]
        assert "psa_kinetics" in calc_ids or "pcpt_risk" in calc_ids


@pytest.mark.api
@pytest.mark.integration
class TestExternalIntegrations:
    """Test external integration endpoints."""

    async def test_openevidence_query(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test OpenEvidence query link generation."""
        response = await authenticated_client.get(
            "/api/v1/rag/openevidence-query",
            params={"query": "prostate cancer active surveillance"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "openevidence.com" in data["url"]

    async def test_nsqip_link(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test NSQIP link generation."""
        response = await authenticated_client.get("/api/v1/rag/nsqip-link")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "riskcalculator" in data["url"]


@pytest.mark.api
@pytest.mark.rag
class TestKnowledgeBaseStats:
    """Test knowledge base statistics endpoints."""

    async def test_get_stats(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting knowledge base statistics."""
        response = await authenticated_client.get("/api/v1/rag/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_documents" in data
        assert "categories" in data
        assert "sources" in data


@pytest.mark.api
@pytest.mark.performance
class TestRAGPerformance:
    """Test RAG performance."""

    async def test_search_response_time(
        self,
        authenticated_client: AsyncClient,
        performance_timer,
    ):
        """Test RAG search completes within performance target."""
        performance_timer.start()

        response = await authenticated_client.post(
            "/api/v1/rag/search",
            json={
                "query": "bladder cancer treatment",
                "limit": 5,
            },
        )

        performance_timer.stop()

        assert response.status_code == 200
        # Target: < 3 seconds for RAG search
        performance_timer.assert_max_duration(3000)
