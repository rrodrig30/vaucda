#!/usr/bin/env python3
"""Debug PSH regex."""

import re
from pathlib import Path

# Sample PSH section from input
sample = """PAST SURGICAL HISTORY:
1. Lymphadenectomy, neck
2. Bone spur in feet
3. Medi Port
4. BM aspirate

PSA CURVE:
[r] Jun 24, 2024 09:36   0.52 on finasteride"""

print("Sample input:")
print("="*80)
print(sample)
print("="*80)

# Test pattern
pattern = r'(?:PSH|PAST SURGICAL HISTORY):\s*(.*?)(?=\n\s*[A-Z][A-Z\s]+:|\n\s*={10,}|$)'

match = re.search(pattern, sample, re.IGNORECASE | re.DOTALL | re.MULTILINE)
if match:
    result = match.group(1).strip()
    print(f"\nExtracted ({len(result)} chars):")
    print("-"*80)
    print(result)
    print("-"*80)

    lines = result.split('\n')
    print(f"\nLines: {len(lines)}")
    for i, line in enumerate(lines, 1):
        print(f"  {i}. {repr(line)}")
else:
    print("NO MATCH!")
