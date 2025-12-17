"""
RAG Pipeline Orchestration
Complete RAG workflow from query to augmented context
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rag.retriever import RAGRetriever, RetrievedDocument
from rag.document_parser import get_document_parser
from rag.chunking import MedicalDocumentChunker, DocumentType
from rag.embeddings import EmbeddingGenerator
from database.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """
    Complete RAG context for LLM augmentation.

    Contains retrieved documents, assembled context, and source attribution.
    """
    context: str  # Assembled context text for LLM
    sources: List[Dict[str, str]]  # Source attribution
    documents: List[RetrievedDocument]  # Full retrieved documents
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_context(self) -> bool:
        """Check if context contains meaningful information."""
        return len(self.context.strip()) > 0

    @property
    def num_sources(self) -> int:
        """Number of unique sources."""
        return len(self.sources)


class RAGPipeline:
    """
    Complete RAG pipeline orchestration.

    Workflow:
    1. Retrieve relevant documents
    2. Assemble context from documents
    3. Add source attribution
    4. Format for LLM consumption
    """

    def __init__(
        self,
        retriever: RAGRetriever,
        neo4j_client: Optional[Neo4jClient] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        max_context_length: int = 4000,
        include_metadata: bool = True
    ):
        """
        Initialize RAG pipeline.

        Args:
            retriever: RAG retriever instance
            neo4j_client: Neo4j client for storing documents (optional)
            embedding_generator: Embedding generator instance (optional)
            max_context_length: Maximum context length in characters
            include_metadata: Whether to include metadata in context
        """
        self.retriever = retriever
        self.neo4j_client = neo4j_client
        self.embedding_generator = embedding_generator
        self.max_context_length = max_context_length
        self.include_metadata = include_metadata

        # Initialize document processing components
        self.document_parser = get_document_parser()
        self.chunker = MedicalDocumentChunker()

        logger.info("RAG pipeline initialized")

    async def retrieve_and_augment(
        self,
        query: str,
        k: int = 5,
        search_strategy: str = "graph",
        category: Optional[str] = None,
        patient_context: Optional[Dict[str, Any]] = None
    ) -> RAGContext:
        """
        Complete RAG workflow: retrieve, assemble, and format context.

        Args:
            query: User query
            k: Number of documents to retrieve
            search_strategy: Strategy ("vector", "hybrid", "graph", "clinical")
            category: Filter by category
            patient_context: Optional patient context for clinical search

        Returns:
            RAGContext with assembled context and sources
        """
        # 1. Retrieve relevant documents
        documents = await self._retrieve_documents(
            query=query,
            k=k,
            strategy=search_strategy,
            category=category,
            patient_context=patient_context
        )

        if not documents:
            logger.warning(f"No documents retrieved for query: {query}")
            return RAGContext(
                context="",
                sources=[],
                documents=[],
                metadata={"query": query, "strategy": search_strategy}
            )

        # 2. Assemble context
        context_text = self._assemble_context(documents)

        # 3. Extract sources
        sources = self._extract_sources(documents)

        # 4. Build metadata
        metadata = {
            "query": query,
            "strategy": search_strategy,
            "num_documents": len(documents),
            "avg_similarity": sum(d.similarity_score for d in documents) / len(documents),
            "category": category
        }

        logger.info(
            f"RAG pipeline complete: {len(documents)} documents, "
            f"context length: {len(context_text)} chars"
        )

        return RAGContext(
            context=context_text,
            sources=sources,
            documents=documents,
            metadata=metadata
        )

    async def _retrieve_documents(
        self,
        query: str,
        k: int,
        strategy: str,
        category: Optional[str],
        patient_context: Optional[Dict[str, Any]]
    ) -> List[RetrievedDocument]:
        """Execute retrieval based on strategy."""
        if strategy == "vector":
            return await self.retriever.vector_search(query, k, category)

        elif strategy == "hybrid":
            return await self.retriever.hybrid_search(query, k, category=category)

        elif strategy == "graph":
            return await self.retriever.graph_augmented_search(query, k, category)

        elif strategy == "clinical":
            return await self.retriever.search_by_clinical_scenario(
                scenario=query,
                patient_context=patient_context,
                k=k
            )

        else:
            logger.warning(f"Unknown strategy '{strategy}', using graph search")
            return await self.retriever.graph_augmented_search(query, k, category)

    def _assemble_context(self, documents: List[RetrievedDocument]) -> str:
        """
        Assemble context from retrieved documents.

        Formats documents with source attribution and metadata.
        Truncates to max_context_length if needed.
        """
        context_parts = []
        current_length = 0

        for idx, doc in enumerate(documents, 1):
            # Build document section
            doc_parts = []

            # Header with source
            header = f"[Source {idx}: {doc.source} - {doc.title}]"
            doc_parts.append(header)

            # Add metadata if enabled
            if self.include_metadata:
                meta_parts = []
                if doc.category:
                    meta_parts.append(f"Category: {doc.category}")
                if doc.metadata.get("publication_date"):
                    meta_parts.append(f"Date: {doc.metadata['publication_date']}")
                if doc.similarity_score:
                    meta_parts.append(f"Relevance: {doc.similarity_score:.2f}")

                if meta_parts:
                    doc_parts.append(f"({', '.join(meta_parts)})")

            # Add summary if available, otherwise content preview
            if doc.summary:
                doc_parts.append(f"\n{doc.summary}")
            else:
                # Use first 500 chars of content
                preview = doc.content[:500]
                if len(doc.content) > 500:
                    preview += "..."
                doc_parts.append(f"\n{preview}")

            # Add related concepts and calculators if available
            if doc.related_concepts:
                concepts = ", ".join(doc.related_concepts[:5])
                doc_parts.append(f"\nRelated Concepts: {concepts}")

            if doc.applicable_calculators:
                calcs = ", ".join(doc.applicable_calculators[:3])
                doc_parts.append(f"\nApplicable Calculators: {calcs}")

            # Combine document parts
            doc_text = "\n".join(doc_parts)
            doc_length = len(doc_text)

            # Check if adding this document exceeds limit
            if current_length + doc_length > self.max_context_length:
                # Truncate this document to fit
                remaining = self.max_context_length - current_length
                if remaining > 200:  # Only add if meaningful space remains
                    doc_text = doc_text[:remaining] + "\n[Content truncated due to length]"
                    context_parts.append(doc_text)
                break
            else:
                context_parts.append(doc_text)
                current_length += doc_length + 2  # +2 for separator

        # Join all documents with separator
        context = "\n\n---\n\n".join(context_parts)

        logger.debug(f"Assembled context: {len(context)} chars from {len(context_parts)} documents")
        return context

    def _extract_sources(self, documents: List[RetrievedDocument]) -> List[Dict[str, str]]:
        """
        Extract source attribution from documents.

        Returns list of dicts with source information for citations.
        """
        sources = []

        for idx, doc in enumerate(documents, 1):
            source_info = {
                "id": str(idx),
                "title": doc.title,
                "source": doc.source,
                "category": doc.category,
            }

            # Add publication date if available
            if doc.metadata.get("publication_date"):
                source_info["date"] = str(doc.metadata["publication_date"])

            # Add version if available
            if doc.metadata.get("version"):
                source_info["version"] = doc.metadata["version"]

            sources.append(source_info)

        return sources

    def augment_prompt(
        self,
        base_prompt: str,
        rag_context: RAGContext,
        instructions: Optional[str] = None
    ) -> str:
        """
        Inject RAG context into LLM prompt.

        Args:
            base_prompt: Base prompt/query
            rag_context: RAG context to inject
            instructions: Optional instructions for using context

        Returns:
            Augmented prompt with context
        """
        if not rag_context.has_context:
            return base_prompt

        # Default instructions
        if not instructions:
            instructions = (
                "Use the following clinical knowledge and guidelines to inform your response. "
                "Cite sources using [Source N] notation when referencing specific information."
            )

        # Assemble augmented prompt
        augmented_parts = [
            instructions,
            "",
            "=== CLINICAL KNOWLEDGE BASE ===",
            rag_context.context,
            "=== END KNOWLEDGE BASE ===",
            "",
            "Query:",
            base_prompt
        ]

        augmented_prompt = "\n".join(augmented_parts)

        logger.debug(f"Augmented prompt length: {len(augmented_prompt)} chars")
        return augmented_prompt

    def format_sources_for_output(self, sources: List[Dict[str, str]]) -> str:
        """
        Format sources for inclusion in output/response.

        Args:
            sources: List of source dictionaries

        Returns:
            Formatted source list as string
        """
        if not sources:
            return ""

        formatted = ["**Sources:**\n"]

        for source in sources:
            parts = [f"[{source['id']}]", source['title']]

            if source.get('source'):
                parts.append(f"({source['source']})")

            if source.get('date'):
                parts.append(f"- {source['date']}")

            if source.get('version'):
                parts.append(f"v{source['version']}")

            formatted.append(" ".join(parts))

        return "\n".join(formatted)

    async def get_calculator_recommendations(
        self,
        query: str,
        k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get calculator recommendations for a clinical query.

        Args:
            query: Clinical query
            k: Number of recommendations

        Returns:
            List of recommended calculators
        """
        calculators = await self.retriever.get_related_calculators(query, k)

        logger.info(f"Retrieved {len(calculators)} calculator recommendations")
        return calculators

    async def ingest_document(
        self,
        file_path: str,
        category: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ingest a document into the knowledge base.

        Complete pipeline:
        1. Parse document (PDF/DOCX/TXT)
        2. Chunk text using appropriate strategy
        3. Generate embeddings for chunks
        4. Store chunks in Neo4j with vector index

        Args:
            file_path: Path to document file
            category: Document category (prostate, kidney, bladder, etc.)
            metadata: Optional additional metadata

        Returns:
            Dictionary with ingestion results:
            - document_id: Neo4j node ID
            - chunks_created: Number of chunks
            - embeddings_generated: Number of embeddings
            - status: success/error
        """
        if not self.neo4j_client:
            raise RuntimeError("Neo4j client required for document ingestion")

        if not self.embedding_generator:
            raise RuntimeError("Embedding generator required for document ingestion")

        try:
            logger.info(f"Ingesting document: {file_path}")

            # Step 1: Parse document
            parsed = self.document_parser.parse_file(file_path)
            text = parsed['text']
            file_metadata = parsed['metadata']

            # Combine metadata
            combined_metadata = {
                **file_metadata,
                'category': category,
                'ingestion_date': datetime.utcnow().isoformat(),
                **(metadata or {})
            }

            # Determine document type for chunking
            doc_type = self._infer_document_type(category, text, file_metadata)

            logger.info(f"Document type inferred: {doc_type.value}")

            # Step 2: Chunk document
            chunks = self.chunker.chunk_document(
                text=text,
                doc_type=doc_type,
                metadata=combined_metadata
            )

            logger.info(f"Created {len(chunks)} chunks")

            # Step 3: Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = self.embedding_generator.generate_embeddings_batch(
                texts=chunk_texts,
                batch_size=32,
                show_progress=True
            )

            logger.info(f"Generated {len(embeddings)} embeddings")

            # Step 4: Store in Neo4j
            # Create document node
            document_query = """
            CREATE (d:Document {
                title: $title,
                filename: $filename,
                category: $category,
                file_type: $file_type,
                ingestion_date: $ingestion_date,
                num_chunks: $num_chunks,
                author: $author,
                source: $source
            })
            RETURN id(d) as doc_id
            """

            document_params = {
                'title': combined_metadata.get('title', file_metadata.get('filename', 'Untitled')),
                'filename': file_metadata.get('filename', Path(file_path).name),
                'category': category,
                'file_type': file_metadata.get('file_type', 'unknown'),
                'ingestion_date': combined_metadata['ingestion_date'],
                'num_chunks': len(chunks),
                'author': combined_metadata.get('author', 'Unknown'),
                'source': combined_metadata.get('original_filename', file_metadata.get('filename', ''))
            }

            async with self.neo4j_client.driver.session() as session:
                result = await session.run(document_query, document_params)
                record = await result.single()
                document_id = record['doc_id']

            logger.info(f"Created document node: {document_id}")

            # Create chunk nodes and link to document
            chunks_created = 0
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_query = """
                MATCH (d:Document) WHERE id(d) = $doc_id
                CREATE (c:Chunk {
                    content: $content,
                    chunk_index: $chunk_index,
                    total_chunks: $total_chunks,
                    section: $section,
                    embedding: $embedding
                })
                CREATE (c)-[:BELONGS_TO]->(d)
                RETURN id(c) as chunk_id
                """

                chunk_params = {
                    'doc_id': document_id,
                    'content': chunk.content,
                    'chunk_index': chunk.chunk_index,
                    'total_chunks': chunk.total_chunks,
                    'section': chunk.metadata.get('section', 'Unknown'),
                    'embedding': embedding.tolist()
                }

                async with self.neo4j_client.driver.session() as session:
                    await session.run(chunk_query, chunk_params)
                chunks_created += 1

            logger.info(f"Created {chunks_created} chunk nodes")

            # Create vector index if doesn't exist
            try:
                index_query = """
                CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
                FOR (c:Chunk)
                ON c.embedding
                OPTIONS {indexConfig: {
                    `vector.dimensions`: 384,
                    `vector.similarity_function`: 'cosine'
                }}
                """
                async with self.neo4j_client.driver.session() as session:
                    await session.run(index_query, {})
                logger.info("Vector index created/verified")
            except Exception as e:
                logger.warning(f"Vector index creation skipped (may already exist): {e}")

            return {
                'status': 'success',
                'document_id': document_id,
                'chunks_created': chunks_created,
                'embeddings_generated': len(embeddings),
                'category': category,
                'filename': file_metadata.get('filename'),
                'document_type': doc_type.value
            }

        except Exception as e:
            logger.error(f"Document ingestion failed: {e}", exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'file_path': file_path
            }

    def _infer_document_type(
        self,
        category: str,
        text: str,
        metadata: Dict[str, Any]
    ) -> DocumentType:
        """
        Infer document type from category and content.

        Args:
            category: Document category
            text: Document text
            metadata: Document metadata

        Returns:
            Inferred DocumentType
        """
        # Check title/filename for calculator keywords
        title = metadata.get('title', '').lower()
        filename = metadata.get('filename', '').lower()

        if any(kw in title or kw in filename for kw in [
            'calculator', 'score', 'index', 'risk assessment'
        ]):
            return DocumentType.CALCULATOR

        # Check for guideline keywords
        if any(kw in title or kw in filename for kw in [
            'guideline', 'aua', 'nccn', 'eau', 'recommendation', 'consensus'
        ]):
            return DocumentType.GUIDELINE

        # Check content for literature patterns
        if any(pattern in text[:2000].lower() for pattern in [
            'abstract', 'introduction', 'methods', 'results', 'discussion',
            'conclusion', 'references'
        ]):
            return DocumentType.LITERATURE

        # Default to general
        return DocumentType.GENERAL

    async def get_knowledge_base_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge base.

        Returns:
            Dictionary with stats:
            - total_documents: Number of documents
            - total_chunks: Number of chunks
            - categories: Document count by category
            - file_types: Document count by file type
        """
        if not self.neo4j_client:
            raise RuntimeError("Neo4j client required for knowledge base stats")

        try:
            # Total documents and chunks
            stats_query = """
            MATCH (d:Document)
            OPTIONAL MATCH (c:Chunk)-[:BELONGS_TO]->(d)
            RETURN count(DISTINCT d) as total_documents,
                   count(c) as total_chunks
            """
            async with self.neo4j_client.driver.session() as session:
                result = await session.run(stats_query, {})
                record = await result.single()
                stats = dict(record)

            # Categories breakdown
            category_query = """
            MATCH (d:Document)
            RETURN d.category as category, count(d) as count
            ORDER BY count DESC
            """
            async with self.neo4j_client.driver.session() as session:
                result = await session.run(category_query, {})
                categories = {record['category']: record['count'] async for record in result}

            # File types breakdown
            filetype_query = """
            MATCH (d:Document)
            RETURN d.file_type as file_type, count(d) as count
            ORDER BY count DESC
            """
            async with self.neo4j_client.driver.session() as session:
                result = await session.run(filetype_query, {})
                file_types = {record['file_type']: record['count'] async for record in result}

            logger.info(
                f"Knowledge base stats: {stats['total_documents']} documents, "
                f"{stats['total_chunks']} chunks"
            )

            return {
                'total_documents': stats['total_documents'],
                'total_chunks': stats['total_chunks'],
                'categories': categories,
                'file_types': file_types,
                'avg_chunks_per_document': (
                    stats['total_chunks'] / stats['total_documents']
                    if stats['total_documents'] > 0 else 0
                )
            }

        except Exception as e:
            logger.error(f"Failed to get knowledge base stats: {e}")
            return {
                'error': str(e),
                'total_documents': 0,
                'total_chunks': 0,
                'categories': {},
                'file_types': {}
            }
