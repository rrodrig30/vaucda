#!/usr/bin/env python3
"""
VAUCDA Secrets Generation Script
================================

This script generates secure secrets for production deployment.
Use this to create random passwords and keys for:
- JWT tokens
- Database passwords
- Encryption keys
- Redis passwords

Usage:
    python scripts/generate_secrets.py > secrets.txt

Then copy the generated values to your .env file.
"""

import secrets
import argparse
import sys
from cryptography.fernet import Fernet


def generate_jwt_secret(length: int = 32) -> str:
    """Generate a secure JWT secret key."""
    return secrets.token_urlsafe(length)


def generate_password(length: int = 24) -> str:
    """Generate a secure random password."""
    return secrets.token_urlsafe(length)


def generate_fernet_key() -> str:
    """Generate a Fernet encryption key for credential storage."""
    return Fernet.generate_key().decode()


def generate_hex_key(length: int = 32) -> str:
    """Generate a secure hexadecimal key."""
    return secrets.token_hex(length)


def print_production_secrets():
    """Print all generated secrets for production use."""
    print("=" * 80)
    print("VAUCDA PRODUCTION SECRETS GENERATOR")
    print("=" * 80)
    print()
    print("CRITICAL: Use these values in your .env files")
    print("NEVER commit .env files to version control")
    print()
    print("=" * 80)
    print("SECURITY SECRETS")
    print("=" * 80)
    print()
    print("# JWT Secret Key (for token generation)")
    print(f"JWT_SECRET_KEY={generate_jwt_secret(32)}")
    print()
    print("# Secret Key (legacy, for backward compatibility)")
    print(f"SECRET_KEY={generate_jwt_secret(32)}")
    print()

    print("=" * 80)
    print("DATABASE SECRETS")
    print("=" * 80)
    print()
    print("# Neo4j Database Password")
    print(f"NEO4J_PASSWORD={generate_password(24)}")
    print()
    print("# Redis Password")
    print(f"REDIS_PASSWORD={generate_password(24)}")
    print()
    print("# SQLite Database (no password needed)")
    print("SQLITE_DATABASE_URL=sqlite+aiosqlite:////app/data/vaucda.db")
    print()

    print("=" * 80)
    print("ENCRYPTION KEYS")
    print("=" * 80)
    print()
    print("# Fernet encryption key (for OpenEvidence credentials)")
    print("# Used for encrypting user credentials stored in database")
    print(f"OPENEVIDENCE_ENCRYPTION_KEY={generate_fernet_key()}")
    print()

    print("=" * 80)
    print("OPTIONAL API KEYS")
    print("=" * 80)
    print()
    print("# Anthropic Claude API Key (optional)")
    print("ANTHROPIC_API_KEY=sk-ant-xxxxx")
    print()
    print("# OpenAI GPT API Key (optional)")
    print("OPENAI_API_KEY=sk-xxxxx")
    print()

    print("=" * 80)
    print("INSTRUCTIONS")
    print("=" * 80)
    print()
    print("1. Copy the values above")
    print("2. Update your .env files:")
    print("   - /backend/.env")
    print("   - /.env (root directory)")
    print()
    print("3. Ensure proper file permissions:")
    print("   chmod 600 .env backend/.env")
    print()
    print("4. Restart services:")
    print("   docker-compose down && docker-compose up -d")
    print()
    print("=" * 80)


def print_development_secrets():
    """Print safe secrets for development use."""
    print("=" * 80)
    print("VAUCDA DEVELOPMENT SECRETS (NOT FOR PRODUCTION)")
    print("=" * 80)
    print()
    print("These are example values for development/testing only")
    print()
    print(f"JWT_SECRET_KEY={generate_jwt_secret(32)}")
    print(f"SECRET_KEY={generate_jwt_secret(32)}")
    print(f"NEO4J_PASSWORD={generate_password(24)}")
    print(f"REDIS_PASSWORD={generate_password(24)}")
    print(f"OPENEVIDENCE_ENCRYPTION_KEY={generate_fernet_key()}")
    print()


def validate_secrets(secrets_dict: dict) -> bool:
    """Validate that all required secrets are present and valid."""
    required_keys = [
        'JWT_SECRET_KEY',
        'SECRET_KEY',
        'NEO4J_PASSWORD',
        'REDIS_PASSWORD',
        'OPENEVIDENCE_ENCRYPTION_KEY'
    ]

    for key in required_keys:
        if key not in secrets_dict:
            print(f"ERROR: Missing required secret: {key}", file=sys.stderr)
            return False
        if not secrets_dict[key] or len(str(secrets_dict[key])) < 16:
            print(f"ERROR: Invalid secret value for {key}", file=sys.stderr)
            return False

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate secure secrets for VAUCDA deployment'
    )
    parser.add_argument(
        '--env',
        choices=['production', 'development'],
        default='production',
        help='Environment type (default: production)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate secrets from .env file'
    )

    args = parser.parse_args()

    if args.env == 'production':
        print_production_secrets()
    else:
        print_development_secrets()


if __name__ == '__main__':
    main()
