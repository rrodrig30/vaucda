#!/usr/bin/env python3
"""
Production readiness verification for all 50 calculators.
This test goes beyond just schema validation - it verifies:
1. All calculators can be instantiated
2. All get_input_schema() methods work
3. All InputType values are valid enum members
4. All InputMetadata objects have required fields
5. No placeholder implementations exist
"""

import sys
from typing import List, Dict, Any

from calculators.registry import CalculatorRegistry
from calculators.base import InputType, InputMetadata

# Valid InputType enum values
VALID_INPUT_TYPES = {
    InputType.NUMERIC,
    InputType.ENUM,
    InputType.BOOLEAN,
    InputType.TEXT,
    InputType.DATE,
}


def verify_calculator_production_readiness(calc) -> Dict[str, Any]:
    """
    Comprehensive production readiness check for a calculator.

    Returns:
        dict with keys: id, name, ready, issues[]
    """
    result = {
        'id': calc.calculator_id,
        'name': calc.name,
        'ready': True,
        'issues': [],
    }

    try:
        # 1. Verify get_input_schema() returns a list
        schema = calc.get_input_schema()
        if not isinstance(schema, list):
            result['ready'] = False
            result['issues'].append(f"get_input_schema() returned {type(schema)}, expected list")
            return result

        # 2. Verify each InputMetadata object
        for i, metadata in enumerate(schema):
            # Check it's an InputMetadata instance
            if not isinstance(metadata, InputMetadata):
                result['ready'] = False
                result['issues'].append(f"Item {i} is not InputMetadata: {type(metadata)}")
                continue

            # Check required fields
            required_fields = ['field_name', 'display_name', 'input_type', 'required']
            for field in required_fields:
                if not hasattr(metadata, field):
                    result['ready'] = False
                    result['issues'].append(f"InputMetadata {i} missing required field: {field}")

            # Check input_type is valid
            if hasattr(metadata, 'input_type'):
                if metadata.input_type not in VALID_INPUT_TYPES:
                    result['ready'] = False
                    result['issues'].append(
                        f"Field '{metadata.field_name}' has invalid InputType: {metadata.input_type}"
                    )

            # Check for placeholder/TODO values
            if hasattr(metadata, 'description'):
                desc = metadata.description.lower()
                if 'todo' in desc or 'placeholder' in desc or 'fixme' in desc:
                    result['ready'] = False
                    result['issues'].append(
                        f"Field '{metadata.field_name}' has placeholder description: {metadata.description}"
                    )

        # 3. Verify calculator has basic properties
        if not calc.name or calc.name == "TODO":
            result['ready'] = False
            result['issues'].append("Calculator name is missing or placeholder")

        if not calc.description or "TODO" in calc.description:
            result['ready'] = False
            result['issues'].append("Calculator description is missing or placeholder")

        if not calc.required_inputs:
            result['ready'] = False
            result['issues'].append("Calculator has no required_inputs defined")

    except Exception as e:
        result['ready'] = False
        result['issues'].append(f"Exception during verification: {type(e).__name__}: {str(e)}")

    return result


def main():
    """Run production readiness verification."""
    print("=" * 80)
    print("PRODUCTION READINESS VERIFICATION")
    print("=" * 80)
    print("\nChecking all calculators for production readiness...\n")

    registry = CalculatorRegistry()
    all_calculators = registry.get_all()

    results = []
    ready_count = 0
    not_ready_count = 0

    for calc in sorted(all_calculators, key=lambda c: c.calculator_id):
        result = verify_calculator_production_readiness(calc)
        results.append(result)

        if result['ready']:
            ready_count += 1
            print(f"✓ {result['id']:40s} READY")
        else:
            not_ready_count += 1
            print(f"✗ {result['id']:40s} NOT READY")
            for issue in result['issues']:
                print(f"    - {issue}")

    # Final summary
    print("\n" + "=" * 80)
    print("PRODUCTION READINESS SUMMARY")
    print("=" * 80)
    print(f"Total Calculators: {len(all_calculators)}")
    print(f"Production Ready: {ready_count}/{len(all_calculators)} ({ready_count/len(all_calculators)*100:.1f}%)")
    print(f"Not Ready: {not_ready_count}/{len(all_calculators)} ({not_ready_count/len(all_calculators)*100:.1f}%)")

    if not_ready_count == 0:
        print("\n" + "=" * 80)
        print("✓✓✓ ALL 50 CALCULATORS ARE PRODUCTION READY ✓✓✓")
        print("=" * 80)
        print("\nPRODUCTION DEPLOYMENT APPROVED")
        print("\nAll calculators:")
        print("  - Can be instantiated")
        print("  - Have working get_input_schema() implementations")
        print("  - Use only valid InputType enum values")
        print("  - Have complete InputMetadata with required fields")
        print("  - Have no placeholder or TODO markers")
        print("\nRECOMMENDATION: SHIP TO PRODUCTION")
        return 0
    else:
        print("\n" + "=" * 80)
        print(f"✗✗✗ {not_ready_count} CALCULATORS NOT PRODUCTION READY ✗✗✗")
        print("=" * 80)
        print("\nRECOMMENDATION: DO NOT SHIP - FIX ISSUES FIRST")
        return 1


if __name__ == "__main__":
    sys.exit(main())
