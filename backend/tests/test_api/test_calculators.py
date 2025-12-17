"""
Tests for Calculators API endpoints.

Tests:
- List all calculators
- Get calculator details
- Execute calculator
- Batch calculator execution
- Input validation
- Error handling
"""

import pytest
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.unit
class TestCalculatorListing:
    """Test calculator listing endpoints."""

    async def test_list_all_calculators(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test listing all calculators."""
        response = await authenticated_client.get("/api/v1/calculators")

        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) == 10  # 10 categories

    async def test_list_calculators_by_category(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test listing calculators by category."""
        response = await authenticated_client.get(
            "/api/v1/calculators/category/prostate"
        )

        assert response.status_code == 200
        data = response.json()
        assert "calculators" in data
        # Prostate category should have 7 calculators
        assert len(data["calculators"]) == 7

    async def test_get_calculator_details(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting calculator details."""
        response = await authenticated_client.get(
            "/api/v1/calculators/psa_kinetics"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "psa_kinetics"
        assert "name" in data
        assert "description" in data
        assert "inputs" in data
        assert "category" in data

    async def test_get_nonexistent_calculator(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting nonexistent calculator returns 404."""
        response = await authenticated_client.get(
            "/api/v1/calculators/nonexistent_calc"
        )

        assert response.status_code == 404


@pytest.mark.api
@pytest.mark.calculator
class TestCalculatorExecution:
    """Test calculator execution endpoints."""

    async def test_execute_psa_kinetics(
        self,
        authenticated_client: AsyncClient,
        sample_calculator_inputs: dict,
    ):
        """Test PSA kinetics calculator execution."""
        response = await authenticated_client.post(
            "/api/v1/calculators/psa_kinetics/calculate",
            json={"inputs": sample_calculator_inputs["psa_kinetics"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "interpretation" in data
        assert "psav" in data["result"]
        assert "psadt_months" in data["result"]

    async def test_execute_pcpt_risk(
        self,
        authenticated_client: AsyncClient,
        sample_calculator_inputs: dict,
    ):
        """Test PCPT risk calculator execution."""
        response = await authenticated_client.post(
            "/api/v1/calculators/pcpt_risk/calculate",
            json={"inputs": sample_calculator_inputs["pcpt_risk"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "cancer_risk" in data["result"]

    async def test_execute_with_invalid_inputs(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test calculator execution with invalid inputs."""
        response = await authenticated_client.post(
            "/api/v1/calculators/psa_kinetics/calculate",
            json={"inputs": {"invalid_field": "invalid_value"}},
        )

        assert response.status_code == 400

    async def test_execute_with_missing_inputs(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test calculator execution with missing required inputs."""
        response = await authenticated_client.post(
            "/api/v1/calculators/psa_kinetics/calculate",
            json={"inputs": {}},
        )

        assert response.status_code == 400


@pytest.mark.api
@pytest.mark.calculator
class TestBatchCalculation:
    """Test batch calculator execution."""

    async def test_batch_calculate_multiple(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test batch calculation with multiple calculators."""
        response = await authenticated_client.post(
            "/api/v1/calculators/batch/calculate",
            json={
                "calculators": [
                    {
                        "id": "psa_kinetics",
                        "inputs": {
                            "psa_values": [4.0, 6.0],
                            "time_points_months": [0, 12],
                        },
                    },
                    {
                        "id": "pcpt_risk",
                        "inputs": {
                            "age": 65,
                            "race": "caucasian",
                            "family_history": False,
                            "psa": 5.0,
                            "dre_abnormal": False,
                            "prior_biopsy": False,
                        },
                    },
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2


@pytest.mark.api
@pytest.mark.performance
class TestCalculatorPerformance:
    """Test calculator performance."""

    async def test_calculator_execution_speed(
        self,
        authenticated_client: AsyncClient,
        performance_timer,
    ):
        """Test calculator executes within performance target."""
        performance_timer.start()

        response = await authenticated_client.post(
            "/api/v1/calculators/psa_kinetics/calculate",
            json={
                "inputs": {
                    "psa_values": [4.0, 6.0],
                    "time_points_months": [0, 12],
                }
            },
        )

        performance_timer.stop()

        assert response.status_code == 200
        # Target: < 500ms for calculator execution
        performance_timer.assert_max_duration(500)

    async def test_batch_calculator_speed(
        self,
        authenticated_client: AsyncClient,
        performance_timer,
    ):
        """Test batch calculator execution performance."""
        performance_timer.start()

        response = await authenticated_client.post(
            "/api/v1/calculators/batch/calculate",
            json={
                "calculators": [
                    {
                        "id": f"calc_{i}",
                        "inputs": {"value": i},
                    }
                    for i in range(10)
                ]
            },
        )

        performance_timer.stop()

        # Batch of 10 should complete quickly
        performance_timer.assert_max_duration(2000)
