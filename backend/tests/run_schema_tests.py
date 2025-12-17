#!/usr/bin/env python3
"""
Test runner script for input schema tests.

This script:
1. Runs the calculator input schema tests against the live backend
2. Generates detailed test reports
3. Captures test results and errors
"""

import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path


def run_tests():
    """Run the input schema tests and capture results."""

    print("=" * 80)
    print("VAUCDA Calculator Input Schema Test Suite")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Backend: http://localhost:8002")
    print(f"Test file: tests/test_api/test_calculator_input_schema.py")
    print("=" * 80)
    print()

    # Run pytest with verbose output and JSON report
    test_file = "tests/test_api/test_calculator_input_schema.py"

    cmd = [
        "python", "-m", "pytest",
        test_file,
        "-v",  # Verbose output
        "-s",  # Show print statements
        "--tb=short",  # Short traceback format
        "--color=yes",  # Colored output
        "-W", "ignore::DeprecationWarning",  # Ignore deprecation warnings
        "--maxfail=5",  # Stop after 5 failures to avoid spam
    ]

    print("Running command:")
    print(" ".join(cmd))
    print()
    print("=" * 80)
    print()

    # Run tests
    result = subprocess.run(
        cmd,
        cwd="/home/gulab/PythonProjects/VAUCDA/backend",
        capture_output=False,  # Show output in real-time
        text=True
    )

    print()
    print("=" * 80)
    print(f"Completed at: {datetime.now().isoformat()}")
    print(f"Exit code: {result.returncode}")
    print("=" * 80)

    return result.returncode


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
