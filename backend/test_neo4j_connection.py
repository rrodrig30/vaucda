#!/usr/bin/env python3
"""Test Neo4j connection"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from database.neo4j_client import Neo4jClient, Neo4jConfig

async def test_connection():
    config = Neo4jConfig()
    print(f"URI: {config.uri}")
    print(f"User: {config.username}")
    print(f"Encrypted: {config.encrypted}")

    client = Neo4jClient(config)

    try:
        connected = await client.verify_connectivity()
        if connected:
            print("✓ Successfully connected to Neo4j!")
        else:
            print("✗ Failed to connect to Neo4j")
    except Exception as e:
        print(f"✗ Connection error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_connection())
