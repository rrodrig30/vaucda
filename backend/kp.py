#!/usr/bin/env python3
"""
Kill Process (kp.py) - Kill processes running on a specified port.

Usage:
    python kp.py           # Kills processes on port 3005 (default)
    python kp.py 8002      # Kills processes on port 8002
    python kp.py 3000      # Kills processes on port 3000
"""

import subprocess
import sys
import argparse


def kill_process_on_port(port: int) -> None:
    """
    Kill all processes running on the specified port.

    Args:
        port: The port number to check and kill processes on
    """
    print(f"Checking for processes on port {port}...")

    try:
        # Find processes using lsof
        result = subprocess.run(
            ["lsof", f"-ti:{port}"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0 or not result.stdout.strip():
            print(f"No processes found running on port {port}")
            return

        # Get PIDs
        pids = result.stdout.strip().split('\n')
        print(f"Found {len(pids)} process(es) on port {port}: {', '.join(pids)}")

        # Kill each process
        for pid in pids:
            if pid:
                try:
                    subprocess.run(
                        ["kill", "-9", pid],
                        check=False,
                        stderr=subprocess.DEVNULL
                    )
                    print(f"  ✓ Killed process {pid}")
                except Exception as e:
                    print(f"  ✗ Failed to kill process {pid}: {e}")

        print(f"\nAll processes on port {port} have been terminated.")

    except FileNotFoundError:
        print("Error: 'lsof' command not found. Please install it:")
        print("  Ubuntu/Debian: sudo apt-get install lsof")
        print("  macOS: lsof should be pre-installed")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Kill processes running on a specified port",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kp.py           # Kill processes on port 3005 (default)
  python kp.py 8002      # Kill processes on port 8002
  python kp.py 3000      # Kill processes on port 3000
        """
    )
    parser.add_argument(
        "port",
        type=int,
        nargs="?",
        default=3005,
        help="Port number to check (default: 3005)"
    )

    args = parser.parse_args()

    # Validate port number
    if not (1 <= args.port <= 65535):
        print(f"Error: Invalid port number {args.port}. Must be between 1 and 65535.")
        sys.exit(1)

    kill_process_on_port(args.port)


if __name__ == "__main__":
    main()
