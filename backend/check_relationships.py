#!/usr/bin/env python3
"""Check Neo4j relationships"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

from database.neo4j_client import Neo4jClient, Neo4jConfig

async def check_relationships():
    config = Neo4jConfig()
    client = Neo4jClient(config)

    try:
        async with client.driver.session() as session:
            # Check all relationship types
            result = await session.run("""
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as count
            """)
            print("Relationship types:")
            async for record in result:
                print(f"  {record['rel_type']}: {record['count']}")

            # Check document-chunk connections
            result = await session.run("""
                MATCH (d:Document)-[r]->(c:Chunk)
                RETURN type(r) as rel_type, count(r) as count
            """)
            print("\nDocument-Chunk relationships:")
            async for record in result:
                print(f"  {record['rel_type']}: {record['count']}")

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_relationships())
