#!/usr/bin/env python3
"""Check Neo4j database statistics"""
import asyncio
from dotenv import load_dotenv

load_dotenv()

from database.neo4j_client import Neo4jClient, Neo4jConfig

async def check_stats():
    config = Neo4jConfig()
    client = Neo4jClient(config)

    try:
        async with client.driver.session() as session:
            # Count documents
            result = await session.run("MATCH (d:Document) RETURN count(d) as count")
            doc_count = (await result.single())['count']
            print(f"📄 Documents: {doc_count}")

            # Count chunks
            result = await session.run("MATCH (c:Chunk) RETURN count(c) as count")
            chunk_count = (await result.single())['count']
            print(f"📦 Chunks: {chunk_count}")

            # Count relationships
            result = await session.run("MATCH ()-[r:HAS_CHUNK]->() RETURN count(r) as count")
            rel_count = (await result.single())['count']
            print(f"🔗 Relationships: {rel_count}")

            # Sample document
            result = await session.run("MATCH (d:Document) RETURN d.title, d.category LIMIT 3")
            print(f"\n📋 Sample documents:")
            async for record in result:
                print(f"  - {record['d.title']} ({record['d.category']})")

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_stats())
