#!/usr/bin/env python3
"""
Process saved documents into Neo4j RAG database.
Processes all documents in data/documents/ directory.
"""

import asyncio
import logging
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from rag.rag_pipeline import RAGPipeline
from rag.retriever import RAGRetriever
from rag.embeddings import EmbeddingGenerator
from database.neo4j_client import Neo4jClient, Neo4jConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def process_documents():
    """Process all saved documents into Neo4j."""

    # Initialize components
    logger.info("Initializing RAG pipeline...")
    neo4j_config = Neo4jConfig()
    neo4j_client = Neo4jClient(neo4j_config)
    embedding_generator = EmbeddingGenerator()
    retriever = RAGRetriever(neo4j_client, embedding_generator)

    rag_pipeline = RAGPipeline(
        retriever=retriever,
        neo4j_client=neo4j_client,
        embedding_generator=embedding_generator
    )

    # Find all documents
    docs_dir = Path("data/documents")
    if not docs_dir.exists():
        logger.error(f"Documents directory not found: {docs_dir}")
        return

    document_files = list(docs_dir.glob("*.pdf"))
    document_files.extend(docs_dir.glob("*.docx"))
    document_files.extend(docs_dir.glob("*.txt"))

    logger.info(f"Found {len(document_files)} documents to process")

    # Process each document
    processed = 0
    failed = 0

    for doc_path in document_files:
        try:
            # Extract category from filename
            filename = doc_path.name
            if filename.startswith("aua_core_curriculum_"):
                category = "aua_core_curriculum"
            elif filename.startswith("aua_guidelines_"):
                category = "aua_guidelines"
            elif filename.startswith("aua_updates_"):
                category = "aua_updates"
            elif filename.startswith("peer_reviewed_"):
                category = "peer_reviewed_papers"
            elif filename.startswith("nccn_guidelines_"):
                category = "nccn_guidelines"
            elif filename.startswith("best_practices_"):
                category = "best_practices"
            else:
                category = "other"

            logger.info(f"Processing: {filename} (category: {category})")

            # Ingest document
            result = await rag_pipeline.ingest_document(
                file_path=str(doc_path),
                category=category,
                metadata={
                    "original_filename": filename,
                    "file_type": doc_path.suffix[1:]  # Remove the dot
                }
            )

            processed += 1
            chunks = result.get("chunks", 0)
            logger.info(f"✓ {filename}: {chunks} chunks created")

        except Exception as e:
            failed += 1
            logger.error(f"✗ Failed to process {filename}: {e}")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"SUMMARY: Processed {processed}/{len(document_files)} documents")
    logger.info(f"  Success: {processed}")
    logger.info(f"  Failed:  {failed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("Starting document processing...")
    asyncio.run(process_documents())
    logger.info("Document processing complete!")
