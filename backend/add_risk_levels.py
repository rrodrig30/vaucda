#!/usr/bin/env python3
"""Script to add risk_level to all calculators that don't have it."""

import os
import re
from pathlib import Path

def add_risk_level_to_calculator(file_path):
    """Add risk_level to a calculator file if missing."""
    with open(file_path, 'r') as f:
        content = f.read()

    # Skip if already has risk_level
    if 'risk_level=' in content:
        return False, "Already has risk_level"

    # Find the return CalculatorResult statement
    pattern = r'(return CalculatorResult\([^)]+?\))'
    matches = list(re.finditer(pattern, content, re.DOTALL))

    if not matches:
        return False, "No CalculatorResult found"

    # Get the last return statement (main one, not error cases)
    last_match = matches[-1]
    return_statement = last_match.group(1)

    # Check if it already has risk_level (double check)
    if 'risk_level=' in return_statement:
        return False, "Already has risk_level in return"

    # Determine risk_level variable to add based on context
    # Look for common patterns: severity, category, risk_group, risk_category, etc.
    risk_level_value = None

    # Search backwards from return statement for risk/severity variables
    before_return = content[:last_match.start()]

    # Common patterns to look for
    patterns_to_check = [
        (r'severity\s*=\s*["\']([^"\']+)["\']', 'severity'),
        (r'risk_category\s*=\s*["\']([^"\']+)["\']', 'risk_category'),
        (r'risk_group\s*=\s*["\']([^"\']+)["\']', 'risk_group'),
        (r'category\s*=\s*["\']([^"\']+)["\']', 'category'),
        (r'overall_risk\s*=\s*["\']([^"\']+)["\']', 'overall_risk'),
        (r'frailty_category\s*=\s*["\']([^"\']+)["\']', 'frailty_category'),
        (r'diagnosis\s*=\s*["\']([^"\']+)["\']', 'diagnosis'),
    ]

    for pattern, var_name in patterns_to_check:
        matches = list(re.finditer(pattern, before_return))
        if matches:
            # Use the variable name found
            risk_level_value = var_name
            break

    if not risk_level_value:
        # Default fallback - create a risk_level based on common patterns
        risk_level_value = '"Normal"  # TODO: Determine appropriate risk level'

    # Insert risk_level into the return statement
    # Find the position before references= or the last parameter
    insert_pos = return_statement.rfind('references=')
    if insert_pos == -1:
        insert_pos = return_statement.rfind(')')
        new_return = return_statement[:insert_pos] + f',\n            risk_level={risk_level_value}\n        ' + return_statement[insert_pos:]
    else:
        new_return = return_statement[:insert_pos] + f'risk_level={risk_level_value},\n            ' + return_statement[insert_pos:]

    # Replace in content
    new_content = content[:last_match.start()] + new_return + content[last_match.end():]

    # Write back
    with open(file_path, 'w') as f:
        f.write(new_content)

    return True, f"Added risk_level={risk_level_value}"

def main():
    base_dir = Path("/home/gulab/PythonProjects/VAUCDA/backend/calculators")
    categories = ["female", "reconstructive", "fertility", "hypogonadism", "stones", "surgical"]

    updated_count = 0
    skipped_count = 0

    for category in categories:
        category_dir = base_dir / category
        if not category_dir.exists():
            continue

        for py_file in category_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            success, message = add_risk_level_to_calculator(py_file)
            if success:
                print(f"✓ {py_file.name}: {message}")
                updated_count += 1
            else:
                print(f"✗ {py_file.name}: {message}")
                skipped_count += 1

    print(f"\nSummary: {updated_count} updated, {skipped_count} skipped")

if __name__ == "__main__":
    main()
