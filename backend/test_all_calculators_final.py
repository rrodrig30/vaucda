#!/usr/bin/env python3
"""
Final comprehensive verification of all calculators using the registry.
Tests that all calculators have working get_input_schema() implementations with valid InputType values.
"""

import sys
import traceback
from typing import Dict, Any

from calculators.registry import CalculatorRegistry
from calculators.base import InputType

# Valid InputType enum values
VALID_INPUT_TYPES = {
    InputType.NUMERIC,
    InputType.ENUM,
    InputType.BOOLEAN,
    InputType.TEXT,
    InputType.DATE,
}


def test_calculator(calc) -> Dict[str, Any]:
    """
    Test a single calculator's get_input_schema() method.

    Returns:
        dict: Test results with keys: 'id', 'name', 'success', 'error', 'schema_count', 'invalid_types'
    """
    result = {
        'id': calc.calculator_id,
        'name': calc.name,
        'success': False,
        'error': None,
        'schema_count': 0,
        'invalid_types': [],
    }

    try:
        # Call get_input_schema()
        schema = calc.get_input_schema()

        # Verify schema is a list
        if not isinstance(schema, list):
            result['error'] = f"get_input_schema() returned {type(schema)}, expected list"
            return result

        result['schema_count'] = len(schema)

        # Verify each InputMetadata has valid InputType
        for i, metadata in enumerate(schema):
            if not hasattr(metadata, 'input_type'):
                result['error'] = f"InputMetadata at index {i} missing 'input_type' attribute"
                return result

            if metadata.input_type not in VALID_INPUT_TYPES:
                result['invalid_types'].append({
                    'index': i,
                    'field_name': metadata.field_name if hasattr(metadata, 'field_name') else 'UNKNOWN',
                    'invalid_type': str(metadata.input_type),
                })

        # If we got here with no invalid types, it's a success
        if not result['invalid_types']:
            result['success'] = True
        else:
            result['error'] = f"Found {len(result['invalid_types'])} invalid InputType values"

    except AttributeError as e:
        result['error'] = f"AttributeError: {str(e)}"
        result['traceback'] = traceback.format_exc()
    except Exception as e:
        result['error'] = f"{type(e).__name__}: {str(e)}"
        result['traceback'] = traceback.format_exc()

    return result


def main():
    """Run comprehensive verification of all calculators."""
    print("=" * 80)
    print("FINAL COMPREHENSIVE CALCULATOR SCHEMA VERIFICATION")
    print("=" * 80)
    print("\nInitializing calculator registry...\n")

    # Get all calculators from registry
    registry = CalculatorRegistry()
    all_calculators = registry.get_all()

    print(f"Found {len(all_calculators)} registered calculators\n")
    print("Testing all calculators...\n")

    results = []
    working_count = 0
    broken_count = 0

    # Test each calculator
    for calc in sorted(all_calculators, key=lambda c: c.calculator_id):
        result = test_calculator(calc)
        results.append(result)

        if result['success']:
            working_count += 1
            print(f"✓ {result['id']:40s} {result['name']:45s} ({result['schema_count']} inputs)")
        else:
            broken_count += 1
            print(f"✗ {result['id']:40s} {result['name']:45s} FAILED")
            print(f"  Error: {result['error']}")
            if result['invalid_types']:
                for invalid in result['invalid_types']:
                    print(f"    - Field '{invalid['field_name']}': {invalid['invalid_type']}")
            if 'traceback' in result:
                print(f"\n{result['traceback']}\n")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Calculators: {len(all_calculators)}")
    print(f"Working: {working_count}/{len(all_calculators)} ({working_count/len(all_calculators)*100:.1f}%)")
    print(f"Broken: {broken_count}/{len(all_calculators)} ({broken_count/len(all_calculators)*100:.1f}%)")

    # Verification of the 3 fixed calculators
    print("\n" + "=" * 80)
    print("VERIFICATION OF FIXED CALCULATORS")
    print("=" * 80)

    fixed_calculators = {
        'psa_kinetics': None,
        'nsqip': None,
        'cci': None,
    }

    for result in results:
        if 'psa' in result['id'].lower() and 'kinetics' in result['id'].lower():
            fixed_calculators['psa_kinetics'] = result
        elif 'nsqip' in result['id'].lower():
            fixed_calculators['nsqip'] = result
        elif result['id'].lower() == 'ccicalculator':
            fixed_calculators['cci'] = result

    for name, result in fixed_calculators.items():
        if result:
            status = "FIXED ✓" if result['success'] else "STILL BROKEN ✗"
            print(f"{name.upper():20s}: {status}")
            if not result['success']:
                print(f"  Error: {result['error']}")
        else:
            print(f"{name.upper():20s}: NOT FOUND IN REGISTRY")

    if broken_count == 0:
        print("\n" + "=" * 80)
        print("✓ ALL CALCULATORS PASS - PRODUCTION READY")
        print("=" * 80)
        return 0
    else:
        print("\n" + "=" * 80)
        print(f"✗ {broken_count} CALCULATORS HAVE ISSUES - NOT PRODUCTION READY")
        print("=" * 80)
        print("\nBroken Calculators:")
        for result in results:
            if not result['success']:
                print(f"  - {result['id']}: {result['error']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
