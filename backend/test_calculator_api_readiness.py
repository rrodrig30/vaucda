#!/usr/bin/env python3
"""
Calculator API Readiness Testing
================================

Tests that all 50 calculators are ready for API integration:
1. All calculators can be instantiated
2. All input schemas can be serialized to JSON
3. All calculators can execute with valid inputs
4. All results can be serialized to JSON
5. All calculators are registered and discoverable
"""

import sys
import json
import time
from typing import Dict, Any

from calculators.registry import CalculatorRegistry
from calculators.base import CalculatorCategory


class APIReadinessResults:
    """Collect and report API readiness test results."""

    def __init__(self):
        self.total_tests = 0
        self.passed = 0
        self.failed = 0
        self.failures = []

    def add_pass(self):
        self.passed += 1

    def add_failure(self, test_name: str, calc_id: str, message: str):
        self.failed += 1
        self.failures.append({
            'test': test_name,
            'calculator_id': calc_id,
            'message': message
        })

    def print_summary(self):
        print("\n" + "=" * 100)
        print("API READINESS TEST SUMMARY")
        print("=" * 100)
        print(f"\nTotal Tests: {self.total_tests}")
        print(f"Passed: {self.passed} ({self.passed/self.total_tests*100:.1f}%)")
        print(f"Failed: {self.failed} ({self.failed/self.total_tests*100:.1f}%)")

        if self.failures:
            print("\n" + "-" * 100)
            print("FAILURES")
            print("-" * 100)
            for failure in self.failures:
                print(f"  [{failure['test']}] {failure['calculator_id']}")
                print(f"    {failure['message']}")

        print("\n" + "=" * 100)
        if self.failed == 0:
            print("RESULT: ALL CALCULATORS ARE API READY")
            print("=" * 100)
            print("\nAll 50 calculators can be integrated with the API:")
            print("  - Input schemas are JSON serializable")
            print("  - Calculations execute successfully")
            print("  - Results are JSON serializable")
            print("  - All calculators are registered and discoverable")
            return 0
        else:
            print(f"RESULT: {self.failed} CALCULATORS NOT API READY")
            print("=" * 100)
            return 1


def test_json_schema_serialization(calc, results: APIReadinessResults) -> bool:
    """Test that input schema can be serialized to JSON."""
    test_name = "JSON Schema Serialization"

    try:
        schema = calc.get_input_schema()
        schema_dict = [metadata.to_dict() for metadata in schema]

        # Try to serialize to JSON
        json_str = json.dumps(schema_dict, indent=2)

        # Try to deserialize back
        json.loads(json_str)

        return True

    except Exception as e:
        results.add_failure(test_name, calc.calculator_id,
                          f"Schema serialization failed: {type(e).__name__}: {str(e)}")
        return False


def test_calculator_info_serialization(calc, results: APIReadinessResults) -> bool:
    """Test that calculator info can be serialized to JSON."""
    test_name = "Calculator Info Serialization"

    try:
        info = {
            "id": calc.calculator_id,
            "name": calc.name,
            "description": calc.description,
            "category": calc.category.value,
            "required_inputs": calc.required_inputs,
            "optional_inputs": calc.optional_inputs,
            "references": calc.references
        }

        # Try to serialize to JSON
        json_str = json.dumps(info, indent=2)

        # Try to deserialize back
        json.loads(json_str)

        return True

    except Exception as e:
        results.add_failure(test_name, calc.calculator_id,
                          f"Info serialization failed: {type(e).__name__}: {str(e)}")
        return False


def test_result_serialization(calc, results: APIReadinessResults) -> bool:
    """Test that calculation result can be serialized to JSON."""
    test_name = "Result Serialization"

    try:
        # Build minimal valid inputs
        schema = calc.get_input_schema()
        test_inputs = {}

        for metadata in schema:
            if not metadata.required:
                continue

            from calculators.base import InputType
            if metadata.input_type == InputType.NUMERIC:
                if metadata.example:
                    try:
                        test_inputs[metadata.field_name] = float(metadata.example)
                    except:
                        test_inputs[metadata.field_name] = metadata.min_value or 1.0
                elif metadata.min_value is not None:
                    test_inputs[metadata.field_name] = metadata.min_value
                else:
                    test_inputs[metadata.field_name] = 1.0

            elif metadata.input_type == InputType.ENUM:
                if metadata.allowed_values:
                    test_inputs[metadata.field_name] = metadata.allowed_values[0]

            elif metadata.input_type == InputType.BOOLEAN:
                test_inputs[metadata.field_name] = True

            elif metadata.input_type == InputType.TEXT:
                if metadata.example and metadata.example.startswith('['):
                    test_inputs[metadata.field_name] = json.loads(metadata.example)
                else:
                    test_inputs[metadata.field_name] = metadata.example or "test"

        # Execute calculation
        result = calc.calculate(test_inputs)

        # Build response object (as API would)
        response = {
            "calculator_id": calc.calculator_id,
            "calculator_name": calc.name,
            "result": result.result,
            "interpretation": result.interpretation,
            "risk_level": result.risk_level,
            "recommendations": result.recommendations,
            "category": calc.category.value,
            "references": calc.references
        }

        # Try to serialize to JSON
        json_str = json.dumps(response, indent=2, default=str)

        # Try to deserialize back
        json.loads(json_str)

        return True

    except Exception as e:
        results.add_failure(test_name, calc.calculator_id,
                          f"Result serialization failed: {type(e).__name__}: {str(e)}")
        return False


def test_calculator(calc, results: APIReadinessResults):
    """Run all API readiness tests for a single calculator."""
    calc_id = calc.calculator_id
    results.total_tests += 3  # 3 tests per calculator

    print(f"Testing {calc_id:45s} ", end="", flush=True)

    # Run all tests
    schema_ok = test_json_schema_serialization(calc, results)
    info_ok = test_calculator_info_serialization(calc, results)
    result_ok = test_result_serialization(calc, results)

    # Track passes
    if schema_ok:
        results.add_pass()
    if info_ok:
        results.add_pass()
    if result_ok:
        results.add_pass()

    # Overall status
    if schema_ok and info_ok and result_ok:
        print("[PASS]")
    else:
        print("[FAIL]")


def test_registry_completeness(results: APIReadinessResults):
    """Test that registry has all 50 calculators."""
    test_name = "Registry Completeness"
    results.total_tests += 1

    print(f"Testing {test_name:45s} ", end="", flush=True)

    registry = CalculatorRegistry()
    all_calculators = registry.get_all()

    if len(all_calculators) == 50:
        results.add_pass()
        print("[PASS]")
    else:
        results.add_failure(
            test_name,
            "registry",
            f"Expected 50 calculators, found {len(all_calculators)}"
        )
        print("[FAIL]")


def test_category_distribution(results: APIReadinessResults):
    """Test that calculators are properly distributed across categories."""
    test_name = "Category Distribution"
    results.total_tests += 1

    print(f"Testing {test_name:45s} ", end="", flush=True)

    registry = CalculatorRegistry()
    by_category = registry.list_by_category()

    # Verify we have 10 categories
    if len(by_category) == 10:
        results.add_pass()
        print("[PASS]")
    else:
        results.add_failure(
            test_name,
            "registry",
            f"Expected 10 categories, found {len(by_category)}"
        )
        print("[FAIL]")


def main():
    """Run API readiness tests."""
    print("=" * 100)
    print("CALCULATOR API READINESS TESTING")
    print("=" * 100)
    print("\nVerifying all 50 calculators are ready for API integration\n")
    print("=" * 100)

    results = APIReadinessResults()

    # Test registry
    test_registry_completeness(results)
    test_category_distribution(results)

    # Test each calculator
    registry = CalculatorRegistry()
    all_calculators = registry.get_all()

    for calc in sorted(all_calculators, key=lambda c: c.calculator_id):
        test_calculator(calc, results)

    # Print summary
    exit_code = results.print_summary()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
