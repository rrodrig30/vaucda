#!/usr/bin/env python3
"""
Live API Tests for Calculator Input Schema Implementation.

Tests against the running backend on port 8002.
Requires a valid user account for authentication.
"""

import requests
import json
import sys
from typing import Dict, Any, List
from datetime import datetime


# Configuration
BASE_URL = "http://localhost:8002"
API_BASE = f"{BASE_URL}/api/v1"

# Test credentials
TEST_USERNAME = "testuser_schema"
TEST_PASSWORD = "TestPass123!"


class TestResults:
    """Track test results."""

    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, test_name: str):
        self.total += 1
        self.passed += 1
        print(f"  PASS: {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.total += 1
        self.failed += 1
        self.errors.append({"test": test_name, "error": error})
        print(f"  FAIL: {test_name}")
        print(f"        {error}")

    def summary(self):
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {self.total}")
        print(f"Passed:      {self.passed}")
        print(f"Failed:      {self.failed}")
        print(f"Pass Rate:   {(self.passed / self.total * 100) if self.total > 0 else 0:.1f}%")

        if self.errors:
            print("\nFAILED TESTS:")
            for i, error in enumerate(self.errors, 1):
                print(f"\n{i}. {error['test']}")
                print(f"   {error['error']}")


def authenticate() -> str:
    """Authenticate and get access token."""
    print("Authenticating...")

    # Use email for login (not username)
    email = "testschema@test.com"  # The registered email

    response = requests.post(
        f"{API_BASE}/auth/login",
        json={
            "email": email,
            "password": TEST_PASSWORD
        },
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        print(f"Authentication failed: {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    token = response.json()["access_token"]
    print(f"Authenticated successfully as {email}")
    return token


def make_request(method: str, endpoint: str, token: str, **kwargs) -> requests.Response:
    """Make authenticated API request."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"{API_BASE}{endpoint}"
    return requests.request(method, url, headers=headers, **kwargs)


def test_get_capra_input_schema(token: str, results: TestResults):
    """Test GET /calculators/capracalculator/input-schema."""
    print("\nTest: GET /calculators/capracalculator/input-schema")

    response = make_request("GET", "/calculators/capracalculator/input-schema", token)

    try:
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        assert "calculator_id" in data, "Response missing calculator_id"
        assert "calculator_name" in data, "Response missing calculator_name"
        assert "input_schema" in data, "Response missing input_schema"

        assert data["calculator_id"] == "capracalculator"
        assert isinstance(data["input_schema"], list)

        results.add_pass("Get CAPRA input schema endpoint")
        return data["input_schema"]

    except AssertionError as e:
        results.add_fail("Get CAPRA input schema endpoint", str(e))
        return None


def test_schema_has_all_fields(schema: List[Dict], results: TestResults):
    """Test that schema has all 5 required CAPRA fields."""
    print("\nTest: Schema has all required fields")

    try:
        assert schema is not None, "Schema is None"
        assert len(schema) == 5, f"Expected 5 fields, got {len(schema)}"

        field_names = {field["field_name"] for field in schema}
        required_fields = {
            "psa",
            "gleason_primary",
            "gleason_secondary",
            "t_stage",
            "percent_positive_cores"
        }

        assert field_names == required_fields, \
            f"Field mismatch. Expected: {required_fields}, Got: {field_names}"

        results.add_pass("Schema has all 5 required fields")

    except AssertionError as e:
        results.add_fail("Schema has all 5 required fields", str(e))


def test_field_metadata_completeness(schema: List[Dict], results: TestResults):
    """Test that each field has complete metadata."""
    print("\nTest: Field metadata completeness")

    try:
        assert schema is not None, "Schema is None"

        for field in schema:
            assert "field_name" in field, f"Field missing field_name"
            assert "display_name" in field, f"Field {field.get('field_name')} missing display_name"
            assert "input_type" in field, f"Field {field['field_name']} missing input_type"
            assert "required" in field, f"Field {field['field_name']} missing required"
            assert "description" in field, f"Field {field['field_name']} missing description"

            assert field["field_name"] != "", "field_name cannot be empty"
            assert field["display_name"] != "", "display_name cannot be empty"
            assert field["input_type"] != "", "input_type cannot be empty"
            assert field["description"] != "", "description cannot be empty"
            assert field["required"] is True, f"Field {field['field_name']} should be required"

        results.add_pass("All fields have complete metadata")

    except AssertionError as e:
        results.add_fail("All fields have complete metadata", str(e))


def test_numeric_fields_have_min_max(schema: List[Dict], results: TestResults):
    """Test numeric fields have min/max values."""
    print("\nTest: Numeric fields have min/max values")

    try:
        assert schema is not None, "Schema is None"

        numeric_fields = ["psa", "percent_positive_cores"]

        for field in schema:
            if field["field_name"] in numeric_fields:
                assert field["input_type"] == "numeric", \
                    f"Field {field['field_name']} should be numeric type"

                assert "min_value" in field, \
                    f"Numeric field {field['field_name']} missing min_value"
                assert "max_value" in field, \
                    f"Numeric field {field['field_name']} missing max_value"

                assert field["min_value"] is not None
                assert field["max_value"] is not None
                assert field["min_value"] >= 0
                assert field["max_value"] > field["min_value"]

        results.add_pass("Numeric fields have valid min/max values")

    except AssertionError as e:
        results.add_fail("Numeric fields have valid min/max values", str(e))


def test_enum_fields_have_allowed_values(schema: List[Dict], results: TestResults):
    """Test enum fields have allowed_values."""
    print("\nTest: Enum fields have allowed_values")

    try:
        assert schema is not None, "Schema is None"

        enum_fields = ["gleason_primary", "gleason_secondary", "t_stage"]

        for field in schema:
            if field["field_name"] in enum_fields:
                assert field["input_type"] == "enum", \
                    f"Field {field['field_name']} should be enum type"

                assert "allowed_values" in field, \
                    f"Enum field {field['field_name']} missing allowed_values"

                assert field["allowed_values"] is not None
                assert isinstance(field["allowed_values"], list)
                assert len(field["allowed_values"]) > 0

        results.add_pass("Enum fields have valid allowed_values")

    except AssertionError as e:
        results.add_fail("Enum fields have valid allowed_values", str(e))


def test_all_fields_have_help_and_examples(schema: List[Dict], results: TestResults):
    """Test all fields have help_text and examples."""
    print("\nTest: All fields have help_text and examples")

    try:
        assert schema is not None, "Schema is None"

        for field in schema:
            assert "help_text" in field, f"Field {field['field_name']} missing help_text"
            assert field["help_text"] is not None
            assert field["help_text"] != ""

            assert "example" in field, f"Field {field['field_name']} missing example"
            assert field["example"] is not None
            assert field["example"] != ""

        results.add_pass("All fields have help_text and examples")

    except AssertionError as e:
        results.add_fail("All fields have help_text and examples", str(e))


def test_psa_field_details(schema: List[Dict], results: TestResults):
    """Test PSA field specific requirements."""
    print("\nTest: PSA field details")

    try:
        assert schema is not None, "Schema is None"

        psa_field = next((f for f in schema if f["field_name"] == "psa"), None)
        assert psa_field is not None, "PSA field not found"

        assert psa_field["display_name"] == "PSA"
        assert psa_field["input_type"] == "numeric"
        assert psa_field["required"] is True
        assert psa_field["unit"] == "ng/mL"
        assert psa_field["min_value"] == 0.0
        assert psa_field["max_value"] == 500.0
        assert "Prostate-Specific Antigen" in psa_field["description"]

        results.add_pass("PSA field has correct details")

    except AssertionError as e:
        results.add_fail("PSA field has correct details", str(e))


def test_gleason_fields_details(schema: List[Dict], results: TestResults):
    """Test Gleason score field details."""
    print("\nTest: Gleason fields details")

    try:
        assert schema is not None, "Schema is None"

        for field_name in ["gleason_primary", "gleason_secondary"]:
            gleason_field = next((f for f in schema if f["field_name"] == field_name), None)
            assert gleason_field is not None, f"{field_name} not found"

            assert gleason_field["input_type"] == "enum"
            assert gleason_field["required"] is True
            assert gleason_field["allowed_values"] == [1, 2, 3, 4, 5]
            assert "Gleason" in gleason_field["display_name"]

        results.add_pass("Gleason fields have correct details")

    except AssertionError as e:
        results.add_fail("Gleason fields have correct details", str(e))


def test_t_stage_field_details(schema: List[Dict], results: TestResults):
    """Test T stage field details."""
    print("\nTest: T stage field details")

    try:
        assert schema is not None, "Schema is None"

        t_stage_field = next((f for f in schema if f["field_name"] == "t_stage"), None)
        assert t_stage_field is not None, "T stage field not found"

        assert t_stage_field["display_name"] == "Clinical T Stage"
        assert t_stage_field["input_type"] == "enum"
        assert t_stage_field["required"] is True

        expected_stages = ["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b"]
        assert t_stage_field["allowed_values"] == expected_stages

        results.add_pass("T stage field has correct details")

    except AssertionError as e:
        results.add_fail("T stage field has correct details", str(e))


def test_percent_positive_cores_details(schema: List[Dict], results: TestResults):
    """Test percent positive cores field details."""
    print("\nTest: Percent positive cores field details")

    try:
        assert schema is not None, "Schema is None"

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

        results.add_pass("Percent positive cores field has correct details")

    except AssertionError as e:
        results.add_fail("Percent positive cores field has correct details", str(e))


def test_calculator_info_includes_schema(token: str, results: TestResults):
    """Test that GET /calculators/{id} includes input_schema."""
    print("\nTest: Calculator info endpoint includes input_schema")

    response = make_request("GET", "/calculators/capracalculator", token)

    try:
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()

        assert "input_schema" in data, "input_schema missing from calculator info"
        assert data["input_schema"] is not None
        assert isinstance(data["input_schema"], list)
        assert len(data["input_schema"]) > 0

        results.add_pass("Calculator info includes input_schema")

    except AssertionError as e:
        results.add_fail("Calculator info includes input_schema", str(e))


def test_schema_consistency_between_endpoints(token: str, results: TestResults):
    """Test schema is identical between both endpoints."""
    print("\nTest: Schema consistency between endpoints")

    try:
        # Get from dedicated endpoint
        response1 = make_request("GET", "/calculators/capracalculator/input-schema", token)
        assert response1.status_code == 200
        schema1 = response1.json()["input_schema"]

        # Get from info endpoint
        response2 = make_request("GET", "/calculators/capracalculator", token)
        assert response2.status_code == 200
        schema2 = response2.json()["input_schema"]

        assert schema1 == schema2, "Schemas differ between endpoints"

        results.add_pass("Schema consistency between endpoints")

    except AssertionError as e:
        results.add_fail("Schema consistency between endpoints", str(e))


def test_nonexistent_calculator_404(token: str, results: TestResults):
    """Test that nonexistent calculator returns 404."""
    print("\nTest: Nonexistent calculator returns 404")

    response = make_request("GET", "/calculators/nonexistent_xyz/input-schema", token)

    try:
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

        results.add_pass("Nonexistent calculator returns 404")

    except AssertionError as e:
        results.add_fail("Nonexistent calculator returns 404", str(e))


def test_valid_input_executes_successfully(token: str, results: TestResults):
    """Test that valid input based on schema executes successfully."""
    print("\nTest: Valid input executes calculator successfully")

    valid_input = {
        "psa": 6.5,
        "gleason_primary": 3,
        "gleason_secondary": 4,
        "t_stage": "T2a",
        "percent_positive_cores": 40.0,
    }

    response = make_request(
        "POST",
        "/calculators/capracalculator/calculate",
        token,
        json={"inputs": valid_input}
    )

    try:
        assert response.status_code == 200, \
            f"Valid input should succeed, got {response.status_code}: {response.text}"

        results.add_pass("Valid input executes calculator successfully")

    except AssertionError as e:
        results.add_fail("Valid input executes calculator successfully", str(e))


def test_invalid_numeric_value_fails(token: str, results: TestResults):
    """Test that invalid numeric value fails validation."""
    print("\nTest: Invalid numeric value fails validation")

    invalid_input = {
        "psa": 600.0,  # Exceeds max_value of 500
        "gleason_primary": 3,
        "gleason_secondary": 4,
        "t_stage": "T2a",
        "percent_positive_cores": 40.0,
    }

    response = make_request(
        "POST",
        "/calculators/capracalculator/calculate",
        token,
        json={"inputs": invalid_input}
    )

    try:
        assert response.status_code == 400, \
            f"Invalid PSA should fail, got {response.status_code}"

        results.add_pass("Invalid numeric value fails validation")

    except AssertionError as e:
        results.add_fail("Invalid numeric value fails validation", str(e))


def test_invalid_enum_value_fails(token: str, results: TestResults):
    """Test that invalid enum value fails validation."""
    print("\nTest: Invalid enum value fails validation")

    invalid_input = {
        "psa": 6.5,
        "gleason_primary": 10,  # Not in allowed values [1,2,3,4,5]
        "gleason_secondary": 4,
        "t_stage": "T2a",
        "percent_positive_cores": 40.0,
    }

    response = make_request(
        "POST",
        "/calculators/capracalculator/calculate",
        token,
        json={"inputs": invalid_input}
    )

    try:
        assert response.status_code == 400, \
            f"Invalid Gleason score should fail, got {response.status_code}"

        results.add_pass("Invalid enum value fails validation")

    except AssertionError as e:
        results.add_fail("Invalid enum value fails validation", str(e))


def test_missing_required_field_fails(token: str, results: TestResults):
    """Test that missing required field fails validation."""
    print("\nTest: Missing required field fails validation")

    invalid_input = {
        # "psa": 6.5,  # MISSING
        "gleason_primary": 3,
        "gleason_secondary": 4,
        "t_stage": "T2a",
        "percent_positive_cores": 40.0,
    }

    response = make_request(
        "POST",
        "/calculators/capracalculator/calculate",
        token,
        json={"inputs": invalid_input}
    )

    try:
        assert response.status_code == 400, \
            f"Missing required field should fail, got {response.status_code}"

        results.add_pass("Missing required field fails validation")

    except AssertionError as e:
        results.add_fail("Missing required field fails validation", str(e))


def main():
    """Run all tests."""
    print("=" * 80)
    print("CALCULATOR INPUT SCHEMA - LIVE API TESTS")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Backend URL: {BASE_URL}")
    print(f"Test User: {TEST_USERNAME}")
    print("=" * 80)

    results = TestResults()

    # Authenticate
    token = authenticate()

    # Run tests
    print("\n" + "=" * 80)
    print("SCHEMA ENDPOINT TESTS")
    print("=" * 80)

    schema = test_get_capra_input_schema(token, results)

    print("\n" + "=" * 80)
    print("SCHEMA STRUCTURE TESTS")
    print("=" * 80)

    test_schema_has_all_fields(schema, results)
    test_field_metadata_completeness(schema, results)
    test_numeric_fields_have_min_max(schema, results)
    test_enum_fields_have_allowed_values(schema, results)
    test_all_fields_have_help_and_examples(schema, results)

    print("\n" + "=" * 80)
    print("FIELD-SPECIFIC TESTS")
    print("=" * 80)

    test_psa_field_details(schema, results)
    test_gleason_fields_details(schema, results)
    test_t_stage_field_details(schema, results)
    test_percent_positive_cores_details(schema, results)

    print("\n" + "=" * 80)
    print("ENDPOINT INTEGRATION TESTS")
    print("=" * 80)

    test_calculator_info_includes_schema(token, results)
    test_schema_consistency_between_endpoints(token, results)
    test_nonexistent_calculator_404(token, results)

    print("\n" + "=" * 80)
    print("VALIDATION INTEGRATION TESTS")
    print("=" * 80)

    test_valid_input_executes_successfully(token, results)
    test_invalid_numeric_value_fails(token, results)
    test_invalid_enum_value_fails(token, results)
    test_missing_required_field_fails(token, results)

    # Print summary
    results.summary()

    print(f"\nCompleted at: {datetime.now().isoformat()}")
    print("=" * 80)

    # Return exit code
    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
