"""
Activate GraphRAG Features - Full Microsoft GraphRAG Implementation

This script runs the complete GraphRAG pipeline as outlined by Microsoft:
1. Entity Extraction - Extract entities and relationships from text chunks using LLM
2. Graph Construction - Build entity-relationship graph in Neo4j
3. Community Detection - Use Leiden algorithm to detect communities
4. Hierarchical Summarization - Generate summaries at all levels
5. Embedding Generation - Compute embeddings for communities

Run: cd backend && python scripts/activate_graphrag.py

For large datasets (2500+ docs), this may take several hours.
Use --quick for a faster subset extraction.
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.neo4j_client import Neo4jClient, Neo4jConfig
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_neo4j_client() -> Neo4jClient:
    """Get connected Neo4j client."""
    config = Neo4jConfig(
        uri=settings.NEO4J_URI,
        username=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        encrypted=settings.NEO4J_ENCRYPTED
    )
    client = Neo4jClient(config)

    if not await client.verify_connectivity():
        raise RuntimeError("Cannot connect to Neo4j")

    return client


async def get_database_stats(client: Neo4jClient) -> dict:
    """Get current database statistics."""
    async with client.driver.session() as session:
        # Query each count separately to avoid memory issues
        docs_result = await session.run('MATCH (d:Document) RETURN count(d) as count')
        docs_record = await docs_result.single()
        docs = docs_record['count']

        chunks_result = await session.run('MATCH (c:Chunk) RETURN count(c) as count')
        chunks_record = await chunks_result.single()
        chunks = chunks_record['count']

        entities_result = await session.run('MATCH (e:Entity) RETURN count(e) as count')
        entities_record = await entities_result.single()
        entities = entities_record['count']

        rels_result = await session.run('MATCH ()-[r:RELATED_TO]->() RETURN count(r) as count')
        rels_record = await rels_result.single()
        relationships = rels_record['count']

        comms_result = await session.run('MATCH (c:Community) RETURN count(c) as count')
        comms_record = await comms_result.single()
        communities = comms_record['count']

        summaries_result = await session.run('MATCH (s:HierarchicalSummary) RETURN count(s) as count')
        summaries_record = await summaries_result.single()
        summaries = summaries_record['count']

        return {
            'documents': docs,
            'chunks': chunks,
            'entities': entities,
            'relationships': relationships,
            'communities': communities,
            'summaries': summaries
        }


async def clear_existing_graphrag_data(client: Neo4jClient):
    """Clear existing GraphRAG data to start fresh."""
    logger.info("Clearing existing GraphRAG data...")

    async with client.driver.session() as session:
        # Clear communities
        await session.run("MATCH (c:Community) DETACH DELETE c")
        # Clear entities
        await session.run("MATCH (e:Entity) DETACH DELETE e")
        # Clear hierarchical summaries
        await session.run("MATCH (hs:HierarchicalSummary) DETACH DELETE hs")

    logger.info("Cleared existing GraphRAG data")


async def link_chunks_to_entities(client: Neo4jClient):
    """Create relationships from chunks to their extracted entities."""
    query = """
    MATCH (c:Chunk), (e:Entity)
    WHERE toLower(c.content) CONTAINS toLower(e.name)
    MERGE (c)-[:HAS_ENTITY]->(e)
    """
    await client.execute_query(query)
    logger.info("Linked chunks to entities")


async def run_full_graphrag_pipeline(
    client: Neo4jClient,
    max_chunks: int = None,
    skip_extraction: bool = False
):
    """Run the complete Microsoft GraphRAG pipeline."""
    from rag.graphrag_pipeline import GraphRAGPipeline

    # Initialize pipeline
    pipeline = GraphRAGPipeline(
        neo4j_client=client,
        ollama_base_url=settings.OLLAMA_BASE_URL or "http://localhost:11434",
        llm_model=settings.OLLAMA_DEFAULT_MODEL or "llama3.1:8b",
        embedding_model=settings.OLLAMA_EMBEDDING_MODEL or "nomic-embed-text",
        max_concurrent=12,
        llm_timeout=300
    )

    # Run full pipeline
    results = await pipeline.run_full_pipeline(
        extract_entities=not skip_extraction,
        detect_communities=True,
        generate_summaries=True,
        compute_embeddings=True,
        max_chunks_for_extraction=max_chunks
    )

    return results


async def run_legacy_category_communities(client: Neo4jClient):
    """
    Fallback: Create simple category-based communities.
    Use this when entity extraction is not feasible.
    """
    logger.info("Creating category-based communities (legacy mode)...")

    async with client.driver.session() as session:
        # Get categories
        result = await session.run('''
            MATCH (d:Document)
            RETURN DISTINCT d.category as category, count(d) as doc_count
        ''')

        categories = []
        async for record in result:
            categories.append({
                'category': record['category'],
                'count': record['doc_count']
            })

        # Create community for each category
        for cat in categories:
            category = cat['category']
            if not category:
                continue

            # Create community node
            await session.run('''
                MERGE (c:Community {category: $category})
                SET c.name = $name,
                    c.tier = 0,
                    c.size = $size,
                    c.created_at = datetime()
                WITH c
                MATCH (d:Document {category: $category})
                MERGE (d)-[:BELONGS_TO_COMMUNITY]->(c)
            ''', {
                'category': category,
                'name': f"Community: {category.replace('_', ' ').title()}",
                'size': cat['count']
            })
            logger.info(f"  Created community for {category} ({cat['count']} docs)")

        return len(categories)


async def main():
    """Main activation workflow."""
    parser = argparse.ArgumentParser(description='Activate GraphRAG features')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: process only 100 chunks')
    parser.add_argument('--max-chunks', type=int, default=None,
                        help='Maximum chunks to process for entity extraction')
    parser.add_argument('--legacy', action='store_true',
                        help='Use legacy category-based communities')
    parser.add_argument('--skip-extraction', action='store_true',
                        help='Skip entity extraction (use existing entities)')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing GraphRAG data first')
    args = parser.parse_args()

    print("=" * 70)
    print("MICROSOFT GRAPHRAG ACTIVATION")
    print("=" * 70)

    if args.quick:
        print("\nQUICK MODE: Processing limited subset")
        args.max_chunks = 100

    start_time = time.time()

    # Connect to Neo4j
    print("\n1. Connecting to Neo4j...")
    client = await get_neo4j_client()
    print("   Connected!")

    # Get initial stats
    print("\n2. Current database state:")
    stats = await get_database_stats(client)
    print(f"   Documents:     {stats['documents']}")
    print(f"   Chunks:        {stats['chunks']}")
    print(f"   Entities:      {stats['entities']}")
    print(f"   Relationships: {stats['relationships']}")
    print(f"   Communities:   {stats['communities']}")
    print(f"   Summaries:     {stats['summaries']}")

    if stats['documents'] == 0:
        print("\n   ERROR: No documents in database. Upload documents first.")
        await client.close()
        return

    if stats['chunks'] == 0:
        print("\n   ERROR: No chunks in database. Run document ingestion first.")
        await client.close()
        return

    # Optionally clear existing data
    if args.clear:
        print("\n3. Clearing existing GraphRAG data...")
        await clear_existing_graphrag_data(client)
        stats = await get_database_stats(client)

    # Run pipeline
    if args.legacy:
        print("\n4. Running LEGACY category-based community detection...")
        communities = await run_legacy_category_communities(client)
        print(f"   Created {communities} category-based communities")
    else:
        print("\n4. Running FULL Microsoft GraphRAG pipeline...")
        print("   This will:")
        print("   - Extract entities and relationships from chunks using LLM")
        print("   - Build entity-relationship graph")
        print("   - Detect communities using Leiden algorithm")
        print("   - Generate community summaries using LLM")
        print("   - Compute community embeddings")

        if not args.skip_extraction:
            print("\n   Note: Entity extraction is LLM-intensive and may take time.")
            print(f"   Processing {args.max_chunks or 'all'} chunks...")

        try:
            results = await run_full_graphrag_pipeline(
                client,
                max_chunks=args.max_chunks,
                skip_extraction=args.skip_extraction
            )

            print("\n   Pipeline Results:")
            for stage, data in results.get('stages', {}).items():
                print(f"   - {stage}: {data}")

        except ImportError as e:
            print(f"\n   ERROR: Missing dependencies: {e}")
            print("   Install with: pip install igraph leidenalg")
            print("\n   Falling back to legacy mode...")
            communities = await run_legacy_category_communities(client)
            print(f"   Created {communities} category-based communities")

    # Link chunks to entities
    print("\n5. Linking chunks to entities...")
    await link_chunks_to_entities(client)

    # Final stats
    print("\n6. Final database state:")
    final_stats = await get_database_stats(client)
    print(f"   Documents:     {final_stats['documents']}")
    print(f"   Chunks:        {final_stats['chunks']}")
    print(f"   Entities:      {final_stats['entities']} (was {stats['entities']})")
    print(f"   Relationships: {final_stats['relationships']} (was {stats['relationships']})")
    print(f"   Communities:   {final_stats['communities']} (was {stats['communities']})")
    print(f"   Summaries:     {final_stats['summaries']} (was {stats['summaries']})")

    duration = time.time() - start_time
    print(f"\n   Total time: {duration:.1f}s ({duration/60:.1f} minutes)")

    await client.close()

    print("\n" + "=" * 70)
    print("GRAPHRAG ACTIVATION COMPLETE")
    print("=" * 70)
    print("\nYou can now use GraphRAG search via:")
    print("  POST /api/v1/rag/search")
    print("  Body: {\"query\": \"...\", \"search_strategy\": \"graphrag\"}")
    print("\nSearch modes:")
    print("  - global: Map-reduce across all communities")
    print("  - local: Entity-focused graph traversal")
    print("  - hybrid: Global then local (default)")


if __name__ == "__main__":
    asyncio.run(main())
