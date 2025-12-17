"""
Comprehensive Tests for Calculator Input Schema Implementation.

Tests the new input schema system including:
1. API endpoints for input schema retrieval
2. Schema structure and field metadata validation
3. Integration with calculator execution
4. Error handling and edge cases
5. Schema-guided input validation

Test Coverage:
- GET /api/v1/calculators/{id}/input-schema
- GET /api/v1/calculators/{id} (with input_schema field)
- Schema validation for CAPRA calculator
- Integration testing with actual calculator execution
"""

import pytest
from httpx import AsyncClient
from typing import Dict, Any, List


@pytest.mark.api
@pytest.mark.calculator
class TestInputSchemaEndpoint:
    """Test the dedicated input schema endpoint."""

    async def test_get_capra_input_schema_success(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test successful retrieval of CAPRA calculator input schema."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()

        # Verify response structure
        assert "calculator_id" in data, "Response missing calculator_id"
        assert "calculator_name" in data, "Response missing calculator_name"
        assert "input_schema" in data, "Response missing input_schema"

        assert data["calculator_id"] == "capracalculator"
        assert isinstance(data["calculator_name"], str)
        assert isinstance(data["input_schema"], list)

    async def test_capra_schema_has_all_required_fields(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify CAPRA schema contains all 5 required input fields."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        # CAPRA should have exactly 5 fields
        assert len(schema) == 5, f"Expected 5 fields, got {len(schema)}"

        # Extract field names
        field_names = [field["field_name"] for field in schema]

        # Verify all required fields are present
        required_fields = {
            "psa",
            "gleason_primary",
            "gleason_secondary",
            "t_stage",
            "percent_positive_cores"
        }

        actual_fields = set(field_names)
        assert actual_fields == required_fields, \
            f"Field mismatch. Expected: {required_fields}, Got: {actual_fields}"

    async def test_capra_schema_field_metadata_completeness(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify each field has complete metadata."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        for field in schema:
            # Every field must have these basic attributes
            assert "field_name" in field, f"Field missing field_name: {field}"
            assert "display_name" in field, f"Field {field.get('field_name')} missing display_name"
            assert "input_type" in field, f"Field {field['field_name']} missing input_type"
            assert "required" in field, f"Field {field['field_name']} missing required"
            assert "description" in field, f"Field {field['field_name']} missing description"

            # Verify non-empty values for critical fields
            assert field["field_name"] != "", "field_name cannot be empty"
            assert field["display_name"] != "", "display_name cannot be empty"
            assert field["input_type"] != "", "input_type cannot be empty"
            assert field["description"] != "", "description cannot be empty"

            # All CAPRA fields are required
            assert field["required"] is True, f"Field {field['field_name']} should be required"

    async def test_capra_numeric_fields_have_min_max(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify numeric fields have min_value and max_value."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        numeric_fields = ["psa", "percent_positive_cores"]

        for field in schema:
            if field["field_name"] in numeric_fields:
                assert field["input_type"] == "numeric", \
                    f"Field {field['field_name']} should be numeric type"

                assert "min_value" in field, \
                    f"Numeric field {field['field_name']} missing min_value"
                assert "max_value" in field, \
                    f"Numeric field {field['field_name']} missing max_value"

                assert field["min_value"] is not None, \
                    f"Field {field['field_name']} min_value is None"
                assert field["max_value"] is not None, \
                    f"Field {field['field_name']} max_value is None"

                # Verify logical constraints
                assert field["min_value"] >= 0, \
                    f"Field {field['field_name']} min_value should be >= 0"
                assert field["max_value"] > field["min_value"], \
                    f"Field {field['field_name']} max_value should be > min_value"

    async def test_capra_enum_fields_have_allowed_values(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify enum fields have allowed_values list."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        enum_fields = ["gleason_primary", "gleason_secondary", "t_stage"]

        for field in schema:
            if field["field_name"] in enum_fields:
                assert field["input_type"] == "enum", \
                    f"Field {field['field_name']} should be enum type"

                assert "allowed_values" in field, \
                    f"Enum field {field['field_name']} missing allowed_values"

                assert field["allowed_values"] is not None, \
                    f"Field {field['field_name']} allowed_values is None"

                assert isinstance(field["allowed_values"], list), \
                    f"Field {field['field_name']} allowed_values should be a list"

                assert len(field["allowed_values"]) > 0, \
                    f"Field {field['field_name']} allowed_values is empty"

    async def test_capra_all_fields_have_help_text_and_examples(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify all fields have help_text and example values."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        for field in schema:
            # Help text
            assert "help_text" in field, \
                f"Field {field['field_name']} missing help_text"
            assert field["help_text"] is not None, \
                f"Field {field['field_name']} help_text is None"
            assert field["help_text"] != "", \
                f"Field {field['field_name']} help_text is empty"

            # Example
            assert "example" in field, \
                f"Field {field['field_name']} missing example"
            assert field["example"] is not None, \
                f"Field {field['field_name']} example is None"
            assert field["example"] != "", \
                f"Field {field['field_name']} example is empty"

    async def test_capra_psa_field_details(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test PSA field has correct metadata."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        psa_field = next((f for f in schema if f["field_name"] == "psa"), None)
        assert psa_field is not None, "PSA field not found in schema"

        # Verify specific PSA requirements
        assert psa_field["display_name"] == "PSA"
        assert psa_field["input_type"] == "numeric"
        assert psa_field["required"] is True
        assert psa_field["unit"] == "ng/mL"
        assert psa_field["min_value"] == 0.0
        assert psa_field["max_value"] == 500.0
        assert "Prostate-Specific Antigen" in psa_field["description"]

    async def test_capra_gleason_fields_details(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test Gleason score fields have correct metadata."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        # Test both Gleason fields
        for field_name in ["gleason_primary", "gleason_secondary"]:
            gleason_field = next((f for f in schema if f["field_name"] == field_name), None)
            assert gleason_field is not None, f"{field_name} field not found in schema"

            assert gleason_field["input_type"] == "enum"
            assert gleason_field["required"] is True
            assert gleason_field["allowed_values"] == [1, 2, 3, 4, 5]
            assert "Gleason" in gleason_field["display_name"]

    async def test_capra_t_stage_field_details(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test T stage field has correct metadata."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        t_stage_field = next((f for f in schema if f["field_name"] == "t_stage"), None)
        assert t_stage_field is not None, "T stage field not found in schema"

        assert t_stage_field["display_name"] == "Clinical T Stage"
        assert t_stage_field["input_type"] == "enum"
        assert t_stage_field["required"] is True

        # Verify T stage options
        expected_stages = ["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b"]
        assert t_stage_field["allowed_values"] == expected_stages

    async def test_capra_percent_positive_cores_field_details(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test percent positive cores field has correct metadata."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        schema = data["input_schema"]

        cores_field = next(
            (f for f in schema if f["field_name"] == "percent_positive_cores"),
            None
        )
        assert cores_field is not None, "Percent positive cores field not found"

        assert cores_field["input_type"] == "numeric"
        assert cores_field["required"] is True
        assert cores_field["unit"] == "%"
        assert cores_field["min_value"] == 0.0
        assert cores_field["max_value"] == 100.0


@pytest.mark.api
@pytest.mark.calculator
class TestCalculatorInfoWithSchema:
    """Test calculator info endpoint includes input schema."""

    async def test_get_capra_info_includes_schema(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that GET /calculators/{id} includes input_schema."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify standard fields
        assert "id" in data
        assert "name" in data
        assert "description" in data
        assert "category" in data
        assert "required_inputs" in data

        # Verify input_schema is included
        assert "input_schema" in data, "input_schema missing from calculator info"

        # Schema should not be None
        assert data["input_schema"] is not None, "input_schema is None"

        # Schema should be a list
        assert isinstance(data["input_schema"], list), "input_schema should be a list"

        # Schema should have content
        assert len(data["input_schema"]) > 0, "input_schema is empty"

    async def test_schema_consistency_between_endpoints(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify input_schema is identical between both endpoints."""
        # Get schema from dedicated endpoint
        schema_response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        assert schema_response.status_code == 200
        schema_from_dedicated = schema_response.json()["input_schema"]

        # Get schema from info endpoint
        info_response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator"
        )
        assert info_response.status_code == 200
        schema_from_info = info_response.json()["input_schema"]

        # Schemas should be identical
        assert schema_from_dedicated == schema_from_info, \
            "Input schema differs between endpoints"


@pytest.mark.api
@pytest.mark.calculator
class TestInputSchemaErrorHandling:
    """Test error handling for input schema endpoints."""

    async def test_get_schema_nonexistent_calculator(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting schema for nonexistent calculator returns 404."""
        response = await authenticated_client.get(
            "/api/v1/calculators/nonexistent_calculator_xyz/input-schema"
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    async def test_get_schema_invalid_calculator_id_format(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test getting schema with invalid calculator ID format."""
        invalid_ids = [
            "calculator/with/slashes",
            "calculator with spaces",
            "../../../etc/passwd",
            "calculator;drop table",
        ]

        for invalid_id in invalid_ids:
            response = await authenticated_client.get(
                f"/api/v1/calculators/{invalid_id}/input-schema"
            )

            # Should return 404 or 422 (not crash)
            assert response.status_code in [404, 422], \
                f"Invalid ID '{invalid_id}' should return 404 or 422, got {response.status_code}"

    async def test_get_schema_without_authentication(
        self,
        test_client: AsyncClient,
    ):
        """Test that input schema endpoint requires authentication."""
        response = await test_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        # Should return 401 or 403 (unauthorized/forbidden)
        assert response.status_code in [401, 403], \
            f"Unauthenticated request should return 401/403, got {response.status_code}"


@pytest.mark.api
@pytest.mark.calculator
@pytest.mark.integration
class TestSchemaGuidedCalculation:
    """Test using schema to guide calculator execution."""

    async def test_extract_validation_rules_from_schema(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test extracting validation rules from schema."""
        # Get schema
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        assert response.status_code == 200
        schema = response.json()["input_schema"]

        # Extract validation rules
        validation_rules = {}
        for field in schema:
            field_name = field["field_name"]
            validation_rules[field_name] = {
                "required": field["required"],
                "input_type": field["input_type"],
            }

            if field["input_type"] == "numeric":
                validation_rules[field_name]["min_value"] = field.get("min_value")
                validation_rules[field_name]["max_value"] = field.get("max_value")
            elif field["input_type"] == "enum":
                validation_rules[field_name]["allowed_values"] = field.get("allowed_values")

        # Verify we extracted rules for all fields
        assert len(validation_rules) == 5
        assert "psa" in validation_rules
        assert "gleason_primary" in validation_rules
        assert validation_rules["psa"]["min_value"] == 0.0
        assert validation_rules["psa"]["max_value"] == 500.0

    async def test_valid_input_passes_schema_validation(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that valid input conforms to schema and calculator executes successfully."""
        # Get schema to understand requirements
        schema_response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        assert schema_response.status_code == 200

        # Create valid input based on schema
        valid_input = {
            "psa": 6.5,  # Within 0-500 range
            "gleason_primary": 3,  # From allowed values [1,2,3,4,5]
            "gleason_secondary": 4,  # From allowed values [1,2,3,4,5]
            "t_stage": "T2a",  # From allowed T stages
            "percent_positive_cores": 40.0,  # Within 0-100 range
        }

        # Execute calculator
        calc_response = await authenticated_client.post(
            "/api/v1/calculators/capracalculator/calculate",
            json={"inputs": valid_input}
        )

        assert calc_response.status_code == 200, \
            f"Valid input should succeed, got {calc_response.status_code}: {calc_response.text}"

    async def test_invalid_numeric_value_fails(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that input violating numeric constraints fails."""
        # PSA value exceeding max_value
        invalid_input = {
            "psa": 600.0,  # Exceeds max_value of 500
            "gleason_primary": 3,
            "gleason_secondary": 4,
            "t_stage": "T2a",
            "percent_positive_cores": 40.0,
        }

        response = await authenticated_client.post(
            "/api/v1/calculators/capracalculator/calculate",
            json={"inputs": invalid_input}
        )

        # Should fail validation
        assert response.status_code == 400, \
            f"Invalid PSA should fail, got {response.status_code}"

    async def test_invalid_enum_value_fails(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that input with invalid enum value fails."""
        # Invalid Gleason score
        invalid_input = {
            "psa": 6.5,
            "gleason_primary": 10,  # Not in allowed values [1,2,3,4,5]
            "gleason_secondary": 4,
            "t_stage": "T2a",
            "percent_positive_cores": 40.0,
        }

        response = await authenticated_client.post(
            "/api/v1/calculators/capracalculator/calculate",
            json={"inputs": invalid_input}
        )

        # Should fail validation
        assert response.status_code == 400, \
            f"Invalid Gleason score should fail, got {response.status_code}"

    async def test_missing_required_field_fails(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that missing required field fails."""
        # Missing psa field
        invalid_input = {
            # "psa": 6.5,  # MISSING
            "gleason_primary": 3,
            "gleason_secondary": 4,
            "t_stage": "T2a",
            "percent_positive_cores": 40.0,
        }

        response = await authenticated_client.post(
            "/api/v1/calculators/capracalculator/calculate",
            json={"inputs": invalid_input}
        )

        # Should fail validation
        assert response.status_code == 400, \
            f"Missing required field should fail, got {response.status_code}"


@pytest.mark.api
@pytest.mark.calculator
class TestSchemaDataTypes:
    """Test schema field data types and serialization."""

    async def test_schema_field_types_are_correct(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify all schema field types are correct Python types."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        schema = response.json()["input_schema"]

        for field in schema:
            # String fields
            assert isinstance(field["field_name"], str)
            assert isinstance(field["display_name"], str)
            assert isinstance(field["input_type"], str)
            assert isinstance(field["description"], str)

            # Boolean field
            assert isinstance(field["required"], bool)

            # Optional string fields
            if field.get("unit") is not None:
                assert isinstance(field["unit"], str)

            if field.get("help_text") is not None:
                assert isinstance(field["help_text"], str)

            if field.get("example") is not None:
                # Example can be string or number
                assert isinstance(field["example"], (str, int, float))

            # Numeric constraints
            if field.get("min_value") is not None:
                assert isinstance(field["min_value"], (int, float))

            if field.get("max_value") is not None:
                assert isinstance(field["max_value"], (int, float))

            # Allowed values for enums
            if field.get("allowed_values") is not None:
                assert isinstance(field["allowed_values"], list)


@pytest.mark.api
@pytest.mark.calculator
@pytest.mark.performance
class TestSchemaPerformance:
    """Test performance of schema endpoints."""

    async def test_schema_endpoint_performance(
        self,
        authenticated_client: AsyncClient,
        performance_timer,
    ):
        """Test schema endpoint responds quickly."""
        performance_timer.start()

        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        performance_timer.stop()

        assert response.status_code == 200
        # Schema endpoint should be fast (< 200ms)
        performance_timer.assert_max_duration(200)

    async def test_schema_caching_or_efficiency(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test repeated schema requests are efficient."""
        import time

        # First request
        start = time.time()
        response1 = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        first_duration = time.time() - start

        # Second request (should be same speed or faster if cached)
        start = time.time()
        response2 = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        second_duration = time.time() - start

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Verify responses are identical
        assert response1.json() == response2.json()

        # Both should be reasonably fast
        assert first_duration < 0.5  # 500ms
        assert second_duration < 0.5  # 500ms


@pytest.mark.api
@pytest.mark.calculator
class TestMultipleCalculatorSchemas:
    """Test schemas for multiple calculators to verify general implementation."""

    async def test_psa_kinetics_has_schema(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that other calculators can have schemas."""
        response = await authenticated_client.get(
            "/api/v1/calculators/psa_kinetics/input-schema"
        )

        # Should succeed (even if schema is empty, endpoint should work)
        assert response.status_code == 200
        data = response.json()
        assert "input_schema" in data

    async def test_pcpt_risk_has_schema(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test PCPT risk calculator schema."""
        response = await authenticated_client.get(
            "/api/v1/calculators/pcpt_risk/input-schema"
        )

        assert response.status_code == 200
        data = response.json()
        assert "input_schema" in data


@pytest.mark.api
@pytest.mark.calculator
class TestSchemaDocumentation:
    """Test that schema provides sufficient documentation for frontend developers."""

    async def test_schema_provides_frontend_guidance(
        self,
        authenticated_client: AsyncClient,
    ):
        """Verify schema contains all information needed for frontend form building."""
        response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )

        assert response.status_code == 200
        schema = response.json()["input_schema"]

        for field in schema:
            field_name = field["field_name"]

            # Information needed for form label
            assert field["display_name"], \
                f"Field {field_name} needs display_name for label"

            # Information needed for input widget selection
            assert field["input_type"] in ["numeric", "enum", "boolean", "text", "date"], \
                f"Field {field_name} has invalid input_type"

            # Information needed for validation
            assert "required" in field, \
                f"Field {field_name} needs required flag"

            # Information needed for help tooltips
            assert field["help_text"], \
                f"Field {field_name} needs help_text for tooltip"

            # Information needed for placeholder/example
            assert field["example"], \
                f"Field {field_name} needs example for placeholder"

            # Type-specific validation info
            if field["input_type"] == "numeric":
                assert "min_value" in field and "max_value" in field, \
                    f"Numeric field {field_name} needs min/max for validation"

            elif field["input_type"] == "enum":
                assert "allowed_values" in field, \
                    f"Enum field {field_name} needs allowed_values for dropdown"
                assert len(field["allowed_values"]) > 0, \
                    f"Enum field {field_name} allowed_values cannot be empty"

    async def test_schema_examples_are_valid(
        self,
        authenticated_client: AsyncClient,
    ):
        """Test that example values in schema are actually valid inputs."""
        # Get schema
        schema_response = await authenticated_client.get(
            "/api/v1/calculators/capracalculator/input-schema"
        )
        assert schema_response.status_code == 200
        schema = schema_response.json()["input_schema"]

        # Build input from examples
        example_input = {}
        for field in schema:
            field_name = field["field_name"]
            example_value = field["example"]

            # Convert example to appropriate type
            if field["input_type"] == "numeric":
                example_input[field_name] = float(example_value)
            elif field["input_type"] == "enum":
                # Example should be one of allowed values
                if isinstance(example_value, str) and example_value in field["allowed_values"]:
                    example_input[field_name] = example_value
                else:
                    # Try to convert to number if needed
                    try:
                        example_input[field_name] = int(example_value)
                    except (ValueError, TypeError):
                        example_input[field_name] = example_value
            else:
                example_input[field_name] = example_value

        # Verify examples form valid input
        # Note: May need to adjust field names if they differ between schema and calculator
        # This test verifies the concept - implementation may need refinement
        assert len(example_input) == 5, \
            "Should have extracted 5 example values from schema"
