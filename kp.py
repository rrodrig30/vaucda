#!/usr/bin/env python3
"""
Kill Port (kp.py)

Utility script to kill processes running on a specified port.

Usage:
    python kp.py           # Kills process on port 3005 (default)
    python kp.py 8002      # Kills process on port 8002
"""

import subprocess
import sys
import argparse


def kill_port(port: int) -> None:
    """
    Kill process running on the specified port.

    Args:
        port: Port number to kill
    """
    try:
        # Find process ID using lsof
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0 or not result.stdout.strip():
            print(f"No process found running on port {port}")
            return

        pids = result.stdout.strip().split('\n')

        for pid in pids:
            if pid:
                print(f"Killing process {pid} on port {port}...")
                subprocess.run(['kill', '-9', pid], check=False)

        print(f"✓ Successfully killed process(es) on port {port}")

    except FileNotFoundError:
        print("Error: 'lsof' command not found. Please install it:")
        print("  Ubuntu/Debian: sudo apt-get install lsof")
        print("  macOS: lsof is typically pre-installed")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Kill processes running on a specified port',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kp.py           # Kill port 3005 (default)
  python kp.py 8002      # Kill port 8002
  python kp.py 5432      # Kill port 5432
        """
    )

    parser.add_argument(
        'port',
        nargs='?',
        type=int,
        default=3005,
        help='Port number to kill (default: 3005)'
    )

    args = parser.parse_args()

    # Validate port range
    if not (1 <= args.port <= 65535):
        print(f"Error: Invalid port number {args.port}. Must be between 1 and 65535.")
        sys.exit(1)

    kill_port(args.port)


if __name__ == '__main__':
    main()
