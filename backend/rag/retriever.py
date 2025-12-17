"""
RAG Retriever for VAUCDA
Implements vector search, hybrid search, and graph-augmented retrieval
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import numpy as np

from database.neo4j_client import Neo4jClient
from rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


@dataclass
class RetrievedDocument:
    """Represents a retrieved document from RAG."""
    doc_id: str
    title: str
    content: str
    summary: Optional[str]
    source: str
    category: str
    similarity_score: float
    metadata: Dict[str, Any]
    related_concepts: List[str] = None
    applicable_calculators: List[str] = None

    def __post_init__(self):
        if self.related_concepts is None:
            self.related_concepts = []
        if self.applicable_calculators is None:
            self.applicable_calculators = []


class RAGRetriever:
    """
    RAG Retrieval engine with multiple search strategies.

    Features:
    - Vector similarity search
    - Hybrid search (vector + BM25 keyword)
    - Graph-augmented search (enriches with Neo4j relationships)
    - Re-ranking and filtering
    """

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        embedding_generator: EmbeddingGenerator
    ):
        """
        Initialize RAG retriever.

        Args:
            neo4j_client: Neo4j database client
            embedding_generator: Embedding generator for queries
        """
        self.neo4j = neo4j_client
        self.embedder = embedding_generator
        logger.info("RAG retriever initialized")

    async def vector_search(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None,
        min_publication_year: Optional[int] = None,
        similarity_threshold: float = 0.7
    ) -> List[RetrievedDocument]:
        """
        Vector similarity search in Neo4j.

        Args:
            query: Search query
            k: Number of results to return
            category: Filter by category (prostate, kidney, etc.)
            min_publication_year: Minimum publication year
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of retrieved documents sorted by similarity
        """
        # Generate query embedding
        query_embedding = self.embedder.generate_embedding(query)

        # Search Neo4j
        results = await self.neo4j.vector_search_documents(
            query_embedding=query_embedding.tolist(),
            k=k * 2,  # Fetch more for filtering
            category=category,
            min_publication_year=min_publication_year
        )

        # Convert to RetrievedDocument objects
        documents = []
        for result in results:
            # Filter by similarity threshold
            if result["similarity_score"] < similarity_threshold:
                continue

            doc = RetrievedDocument(
                doc_id=result["doc_id"],
                title=result["title"],
                content=result["content"],
                summary=result.get("summary"),
                source=result["source"],
                category=result["category"],
                similarity_score=result["similarity_score"],
                metadata={
                    "version": result.get("version"),
                    "publication_date": result.get("publication_date"),
                }
            )
            documents.append(doc)

            if len(documents) >= k:
                break

        logger.info(f"Vector search returned {len(documents)} documents for query: {query[:50]}...")
        return documents

    async def hybrid_search(
        self,
        query: str,
        k: int = 5,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        category: Optional[str] = None
    ) -> List[RetrievedDocument]:
        """
        Hybrid search combining vector similarity and keyword matching.

        Args:
            query: Search query
            k: Number of results
            vector_weight: Weight for vector search (0-1)
            keyword_weight: Weight for keyword search (0-1)
            category: Filter by category

        Returns:
            List of retrieved documents with hybrid scores
        """
        # Generate query embedding
        query_embedding = self.embedder.generate_embedding(query)

        # Execute hybrid search in Neo4j
        # This uses both vector index and full-text index
        neo4j_query = """
        // Vector search
        CALL db.index.vector.queryNodes('document_embeddings', $k * 2, $query_embedding)
        YIELD node AS doc_vector, score AS vector_score

        // Keyword search using full-text index
        CALL db.index.fulltext.queryNodes('document_fulltext', $query_text)
        YIELD node AS doc_keyword, score AS keyword_score

        // Combine results
        WITH doc_vector, vector_score, doc_keyword, keyword_score
        WHERE doc_vector.id = doc_keyword.id
          AND ($category IS NULL OR doc_vector.category = $category)

        // Compute hybrid score
        WITH doc_vector AS doc,
             ($vector_weight * vector_score + $keyword_weight * keyword_score) AS hybrid_score

        RETURN doc.id AS doc_id,
               doc.title AS title,
               doc.content AS content,
               doc.summary AS summary,
               doc.source AS source,
               doc.category AS category,
               doc.version AS version,
               doc.publication_date AS publication_date,
               hybrid_score AS similarity_score
        ORDER BY hybrid_score DESC
        LIMIT $k
        """

        try:
            async with self.neo4j.driver.session() as session:
                result = await session.run(
                    neo4j_query,
                    query_embedding=query_embedding.tolist(),
                    query_text=query,
                    k=k,
                    vector_weight=vector_weight,
                    keyword_weight=keyword_weight,
                    category=category
                )

                documents = []
                async for record in result:
                    doc = RetrievedDocument(
                        doc_id=record["doc_id"],
                        title=record["title"],
                        content=record["content"],
                        summary=record["summary"],
                        source=record["source"],
                        category=record["category"],
                        similarity_score=record["similarity_score"],
                        metadata={
                            "version": record["version"],
                            "publication_date": record["publication_date"],
                        }
                    )
                    documents.append(doc)

                logger.info(f"Hybrid search returned {len(documents)} documents")
                return documents

        except Exception as e:
            logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
            # Fallback to vector search
            return await self.vector_search(query, k, category)

    async def graph_augmented_search(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None
    ) -> List[RetrievedDocument]:
        """
        Graph-augmented search: retrieve documents and enrich with graph relationships.

        Enriches results with:
        - Related clinical concepts
        - Applicable calculators
        - Referenced guidelines

        Args:
            query: Search query
            k: Number of results
            category: Filter by category

        Returns:
            List of retrieved documents with graph context
        """
        # Generate query embedding
        query_embedding = self.embedder.generate_embedding(query)

        # Execute graph-augmented search
        results = await self.neo4j.hybrid_search(
            query_embedding=query_embedding.tolist(),
            k=k,
            category=category
        )

        # Convert to RetrievedDocument objects
        documents = []
        for result in results:
            doc = RetrievedDocument(
                doc_id=result["document_id"],
                title=result["title"],
                content=result["content"],
                summary=result.get("summary"),
                source=result.get("source", "Unknown"),
                category=result.get("category", "general"),
                similarity_score=result["vector_score"],
                metadata={},
                related_concepts=result.get("related_concepts", []),
                applicable_calculators=result.get("applicable_calculators", [])
            )
            documents.append(doc)

        logger.info(
            f"Graph-augmented search returned {len(documents)} documents "
            f"with enriched context"
        )
        return documents

    async def semantic_rerank(
        self,
        query: str,
        documents: List[RetrievedDocument],
        top_k: int = 5
    ) -> List[RetrievedDocument]:
        """
        Re-rank documents using more sophisticated semantic similarity.

        Args:
            query: Original query
            documents: Documents to re-rank
            top_k: Number of top documents to return

        Returns:
            Re-ranked documents
        """
        if not documents:
            return []

        # Generate query embedding
        query_embedding = self.embedder.generate_embedding(query)

        # Re-score each document
        for doc in documents:
            # Generate embedding for document content
            doc_embedding = self.embedder.generate_embedding(doc.content[:1000])

            # Compute semantic similarity
            similarity = self.embedder.compute_similarity(query_embedding, doc_embedding)

            # Update score (blend with original score)
            doc.similarity_score = (doc.similarity_score + similarity) / 2

        # Sort by updated score
        documents.sort(key=lambda x: x.similarity_score, reverse=True)

        logger.info(f"Re-ranked {len(documents)} documents, returning top {top_k}")
        return documents[:top_k]

    async def search_by_clinical_scenario(
        self,
        scenario: str,
        patient_context: Optional[Dict[str, Any]] = None,
        k: int = 5
    ) -> List[RetrievedDocument]:
        """
        Search optimized for clinical scenarios.

        Enhances query with patient context and medical terminology.

        Args:
            scenario: Clinical scenario description
            patient_context: Optional patient context (age, gender, conditions)
            k: Number of results

        Returns:
            Retrieved documents relevant to clinical scenario
        """
        # Enhance query with patient context
        enhanced_query = scenario

        if patient_context:
            context_parts = []
            if "age" in patient_context:
                context_parts.append(f"patient age {patient_context['age']}")
            if "gender" in patient_context:
                context_parts.append(f"{patient_context['gender']} patient")
            if "conditions" in patient_context:
                context_parts.append(f"with {', '.join(patient_context['conditions'])}")

            if context_parts:
                enhanced_query = f"{scenario} ({'; '.join(context_parts)})"

        logger.info(f"Clinical scenario search: {enhanced_query}")

        # Use graph-augmented search for best results
        return await self.graph_augmented_search(
            query=enhanced_query,
            k=k
        )

    async def get_related_calculators(
        self,
        query: str,
        k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find calculators relevant to a clinical query.

        Args:
            query: Clinical query
            k: Number of calculators

        Returns:
            List of calculator metadata
        """
        # Search for documents, then extract calculator relationships
        documents = await self.graph_augmented_search(query, k=k)

        # Collect unique calculators
        calculators = {}
        for doc in documents:
            for calc_name in doc.applicable_calculators:
                if calc_name not in calculators:
                    calculators[calc_name] = {
                        "name": calc_name,
                        "relevance_count": 1
                    }
                else:
                    calculators[calc_name]["relevance_count"] += 1

        # Sort by relevance
        sorted_calcs = sorted(
            calculators.values(),
            key=lambda x: x["relevance_count"],
            reverse=True
        )

        logger.info(f"Found {len(sorted_calcs)} related calculators")
        return sorted_calcs[:k]
