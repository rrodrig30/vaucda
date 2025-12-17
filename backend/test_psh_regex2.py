#!/usr/bin/env python3
"""Debug PSH regex with more detail."""

import re

# Sample PSH section from input
sample = """PAST SURGICAL HISTORY:
1. Lymphadenectomy, neck
2. Bone spur in feet
3. Medi Port
4. BM aspirate

PSA CURVE:
[r] Jun 24, 2024 09:36   0.52 on finasteride"""

print("Sample input (with visible newlines):")
print("="*80)
print(repr(sample))
print("="*80)

# Test different patterns
patterns = [
    (r'PAST SURGICAL HISTORY:\s*(.*?)(?=PSA CURVE:)', "Stop at PSA CURVE (no newline match)"),
    (r'PAST SURGICAL HISTORY:\s*(.*?)(?=\nPSA CURVE:)', "Stop at \\nPSA CURVE"),
    (r'PAST SURGICAL HISTORY:\s*(.*?)(?=\n[A-Z])', "Stop at \\n[A-Z]"),
    (r'PAST SURGICAL HISTORY:\s*(.*?)(?=\n\s*[A-Z][A-Z\s]+:)', "Current pattern"),
]

for pattern, desc in patterns:
    print(f"\nTesting: {desc}")
    print(f"Pattern: {pattern}")
    match = re.search(pattern, sample, re.DOTALL | re.MULTILINE)
    if match:
        result = match.group(1).strip()
        lines = result.split('\n')
        print(f"  ✅ Matched {len(lines)} lines")
        for i, line in enumerate(lines, 1):
            print(f"    {i}. {line}")
    else:
        print("  ❌ NO MATCH")
