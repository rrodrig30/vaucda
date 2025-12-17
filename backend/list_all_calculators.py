#!/usr/bin/env python3
"""List all 50 calculators by category."""

from calculators.registry import CalculatorRegistry

registry = CalculatorRegistry()
calculators = sorted(registry.get_all(), key=lambda c: (c.category.value, c.name))

print(f"Total Calculators: {len(calculators)}\n")
print("=" * 80)

prev_category = None
for calc in calculators:
    if prev_category != calc.category.value:
        print(f"\n{calc.category.value.upper().replace('_', ' ')} ({calc.category.value}):")
        print("-" * 80)
        prev_category = calc.category.value

    print(f"  {len([c for c in calculators if c.category == calc.category and calculators.index(c) <= calculators.index(calc)])}. {calc.name}")
    print(f"     ID: {calc.calculator_id}")
    print(f"     Inputs: {len(calc.required_inputs)} required, {len(calc.optional_inputs)} optional")
    print()
