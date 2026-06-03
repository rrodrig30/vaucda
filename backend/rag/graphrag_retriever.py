"""
GraphRAG Retriever

Implements Microsoft GraphRAG-style retrieval:
1. Global Search: Map-reduce across community summaries
2. Local Search: Entity-focused graph traversal + chunk retrieval
3. Hybrid Search: Global context + local specifics

Based on "From Local to Global: A Graph RAG Approach to Query-Focused Summarization"
(Microsoft Research, 2024)

This provides hierarchical retrieval that first identifies relevant
document clusters, then retrieves specific chunks from those clusters.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .community_detection import Community
from .hierarchical_summarizer import HierarchicalSummary, SummaryLevel
from .umls_linker import UMLSLinker

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """GraphRAG search modes."""
    GLOBAL = "global"  # Search community summaries only
    LOCAL = "local"  # Search within specific communities
    HYBRID = "hybrid"  # Global then local (default GraphRAG approach)


@dataclass
class CommunitySearchResult:
    """Result from community-level search."""
    community_id: str
    community_name: str
    summary: str
    relevance_score: float
    tier: int
    document_count: int


@dataclass
class ChunkSearchResult:
    """Result from chunk-level search."""
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    relevance_score: float
    community_id: Optional[str] = None
    centrality_score: float = 0.0


@dataclass
class GraphRAGContext:
    """Complete context retrieved by GraphRAG."""
    query: str
    mode: SearchMode
    community_results: List[CommunitySearchResult]
    chunk_results: List[ChunkSearchResult]
    expanded_query: Optional[str] = None
    total_communities_searched: int = 0
    total_chunks_searched: int = 0
    retrieval_time_seconds: float = 0.0


class GraphRAGRetriever:
    """
    Implements GraphRAG retrieval strategy.

    The retrieval follows Microsoft's GraphRAG approach:
    1. Global search finds relevant communities using their summaries
    2. Local search retrieves specific chunks from those communities
    3. Results are ranked by combined similarity, centrality, and diversity
    """

    def __init__(
        self,
        neo4j_client,
        embedding_model=None,
        umls_linker: Optional[UMLSLinker] = None,
        global_top_k: int = 5,
        local_top_k: int = 10,
        similarity_threshold: float = 0.7,
        use_query_expansion: bool = True
    ):
        """
        Initialize the GraphRAG retriever.

        Args:
            neo4j_client: Neo4j client for database queries
            embedding_model: Model for generating query embeddings
            umls_linker: UMLS linker for query expansion
            global_top_k: Number of communities to retrieve in global search
            local_top_k: Number of chunks to retrieve in local search
            similarity_threshold: Minimum similarity for matches
            use_query_expansion: Whether to expand queries with UMLS synonyms
        """
        self.neo4j_client = neo4j_client
        self.embedding_model = embedding_model
        self.umls_linker = umls_linker
        self.global_top_k = global_top_k
        self.local_top_k = local_top_k
        self.similarity_threshold = similarity_threshold
        self.use_query_expansion = use_query_expansion

    async def _get_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for query text."""
        if self.embedding_model:
            return self.embedding_model.encode(query).tolist()

        # Fallback: try to import from embeddings module
        try:
            from .embeddings import EmbeddingModel
            model = EmbeddingModel()
            return model.embed_text(query)
        except ImportError:
            logger.warning("No embedding model available")
            return []

    def _expand_query(self, query: str) -> str:
        """Expand query with UMLS synonyms."""
        if not self.use_query_expansion or not self.umls_linker:
            return query

        return self.umls_linker.expand_query_with_synonyms(query, max_synonyms=3)

    async def global_search(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[CommunitySearchResult]:
        """
        Search community summaries for relevant document clusters.

        This is the first stage of GraphRAG retrieval, identifying
        which communities contain relevant content.

        Args:
            query: Search query
            top_k: Number of communities to return

        Returns:
            List of relevant communities with scores
        """
        top_k = top_k or self.global_top_k

        # Get query embedding
        query_embedding = await self._get_query_embedding(query)

        if not query_embedding:
            # Fallback to keyword search
            return await self._global_search_keywords(query, top_k)

        # Vector search on community embeddings
        # NOTE: Communities are written by GraphRAGPipeline.store_communities with c.id
        # (see graphrag_pipeline.py:457). We read/filter on c.id, not c.category.
        search_query = """
        CALL db.index.vector.queryNodes('community_embeddings', $top_k, $embedding)
        YIELD node, score
        MATCH (node:Community)
        OPTIONAL MATCH (s:HierarchicalSummary)-[:SUMMARIZES]->(node)
        RETURN node.id AS community_id,
               node.name AS community_name,
               COALESCE(s.content, node.summary, '') AS summary,
               score AS relevance_score,
               node.tier AS tier,
               node.size AS document_count
        ORDER BY score DESC
        LIMIT $top_k
        """

        try:
            results = await self.neo4j_client.execute_query(search_query, {
                'embedding': query_embedding,
                'top_k': top_k
            })

            return [
                CommunitySearchResult(
                    community_id=r['community_id'],
                    community_name=r['community_name'],
                    summary=r['summary'] or '',
                    relevance_score=r['relevance_score'],
                    tier=r['tier'] or 0,
                    document_count=r['document_count'] or 0
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Global search failed: {e}")
            return []

    async def _global_search_keywords(
        self,
        query: str,
        top_k: int
    ) -> List[CommunitySearchResult]:
        """Fallback keyword-based global search using UMLS concepts."""
        # Search documents matching query, then aggregate by community.
        # Documents reach communities via Entity links (see GraphRAGPipeline.store_communities
        # at graphrag_pipeline.py:484, which creates (Document)-[:IN_COMMUNITY]->(Community)).
        # We query on c.id since that's the property store_communities sets.
        search_query = """
        MATCH (d:Document)-[:IN_COMMUNITY|BELONGS_TO_COMMUNITY]->(comm:Community)
        WHERE toLower(d.title) CONTAINS toLower($query)
        WITH comm, count(d) AS doc_count
        OPTIONAL MATCH (s:HierarchicalSummary)-[:SUMMARIZES]->(comm)
        RETURN comm.id AS community_id,
               comm.name AS community_name,
               COALESCE(s.content, comm.summary, '') AS summary,
               toFloat(doc_count) AS relevance_score,
               comm.tier AS tier,
               comm.size AS document_count
        ORDER BY doc_count DESC
        LIMIT $top_k
        """

        try:
            results = await self.neo4j_client.execute_query(search_query, {
                'query': query,
                'top_k': top_k
            })

            return [
                CommunitySearchResult(
                    community_id=r['community_id'],
                    community_name=r['community_name'],
                    summary=r['summary'] or '',
                    relevance_score=r['relevance_score'],
                    tier=r['tier'] or 0,
                    document_count=r['document_count'] or 0
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Keyword global search failed: {e}")
            return []

    async def local_search(
        self,
        query: str,
        community_ids: List[str],
        top_k: Optional[int] = None
    ) -> List[ChunkSearchResult]:
        """
        Search for specific chunks within selected communities.

        This is the second stage of GraphRAG retrieval, finding
        specific content within relevant communities.

        Args:
            query: Search query
            community_ids: List of community IDs to search within
            top_k: Number of chunks to return

        Returns:
            List of relevant chunks with scores
        """
        top_k = top_k or self.local_top_k

        if not community_ids:
            # Search all chunks if no communities specified
            return await self._search_all_chunks(query, top_k)

        # Get query embedding
        query_embedding = await self._get_query_embedding(query)

        if not query_embedding:
            return await self._local_search_keywords(query, community_ids, top_k)

        # Vector search restricted to chunks in specified communities.
        # Documents -> Community via IN_COMMUNITY (set by store_communities at
        # graphrag_pipeline.py:484-490). We filter on c.id (the canonical key).
        search_query = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $top_k * 2, $embedding)
        YIELD node, score
        MATCH (node:Chunk)-[:BELONGS_TO]->(d:Document)
        OPTIONAL MATCH (d)-[:IN_COMMUNITY|BELONGS_TO_COMMUNITY]->(c:Community)
        WHERE c.id IN $community_ids OR size($community_ids) = 0
        RETURN toString(node.chunk_index) AS chunk_id,
               d.filename AS document_id,
               d.title AS document_title,
               node.content AS content,
               score AS relevance_score,
               c.id AS community_id
        ORDER BY score DESC
        LIMIT $top_k
        """

        try:
            results = await self.neo4j_client.execute_query(search_query, {
                'embedding': query_embedding,
                'community_ids': community_ids,
                'top_k': top_k
            })

            return [
                ChunkSearchResult(
                    chunk_id=r['chunk_id'],
                    document_id=r['document_id'],
                    document_title=r['document_title'] or '',
                    content=r['content'] or '',
                    relevance_score=r['relevance_score'],
                    community_id=r['community_id']
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Local search failed: {e}")
            return []

    async def _search_all_chunks(
        self,
        query: str,
        top_k: int
    ) -> List[ChunkSearchResult]:
        """Search all chunks without community filtering."""
        query_embedding = await self._get_query_embedding(query)

        if not query_embedding:
            return []

        search_query = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $top_k, $embedding)
        YIELD node, score
        MATCH (node:Chunk)-[:BELONGS_TO]->(d:Document)
        OPTIONAL MATCH (d)-[:IN_COMMUNITY|BELONGS_TO_COMMUNITY]->(c:Community)
        RETURN toString(node.chunk_index) AS chunk_id,
               d.filename AS document_id,
               d.title AS document_title,
               node.content AS content,
               score AS relevance_score,
               c.id AS community_id
        ORDER BY score DESC
        LIMIT $top_k
        """

        try:
            results = await self.neo4j_client.execute_query(search_query, {
                'embedding': query_embedding,
                'top_k': top_k
            })

            return [
                ChunkSearchResult(
                    chunk_id=r['chunk_id'],
                    document_id=r['document_id'],
                    document_title=r['document_title'] or '',
                    content=r['content'] or '',
                    relevance_score=r['relevance_score'],
                    community_id=r['community_id']
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"All-chunk search failed: {e}")
            return []

    async def _local_search_keywords(
        self,
        query: str,
        community_ids: List[str],
        top_k: int
    ) -> List[ChunkSearchResult]:
        """Fallback keyword-based local search."""
        search_query = """
        MATCH (chunk:Chunk)-[:BELONGS_TO]->(doc:Document)
        WHERE toLower(chunk.content) CONTAINS toLower($query)
           OR toLower(doc.title) CONTAINS toLower($query)
        OPTIONAL MATCH (doc)-[:IN_COMMUNITY|BELONGS_TO_COMMUNITY]->(c:Community)
        WHERE c.id IN $community_ids OR size($community_ids) = 0
        RETURN toString(chunk.chunk_index) AS chunk_id,
               doc.filename AS document_id,
               doc.title AS document_title,
               chunk.content AS content,
               1.0 AS relevance_score,
               c.id AS community_id
        LIMIT $top_k
        """

        try:
            results = await self.neo4j_client.execute_query(search_query, {
                'query': query,
                'community_ids': community_ids,
                'top_k': top_k
            })

            return [
                ChunkSearchResult(
                    chunk_id=r['chunk_id'],
                    document_id=r['document_id'],
                    document_title=r['document_title'] or '',
                    content=r['content'] or '',
                    relevance_score=r['relevance_score'],
                    community_id=r['community_id']
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Keyword local search failed: {e}")
            return []

    async def retrieve(
        self,
        query: str,
        mode: SearchMode = SearchMode.HYBRID
    ) -> GraphRAGContext:
        """
        Main retrieval method implementing GraphRAG strategy.

        Args:
            query: Search query
            mode: Search mode (GLOBAL, LOCAL, or HYBRID)

        Returns:
            GraphRAGContext with all retrieved results
        """
        import time
        start_time = time.time()

        # Optionally expand query with UMLS synonyms
        expanded_query = self._expand_query(query) if self.use_query_expansion else None

        search_query = expanded_query or query

        community_results = []
        chunk_results = []

        if mode == SearchMode.GLOBAL:
            # Global search only - return community summaries
            community_results = await self.global_search(search_query)

        elif mode == SearchMode.LOCAL:
            # Local search only - search all chunks directly
            chunk_results = await self.local_search(search_query, [])

        else:  # HYBRID (default GraphRAG approach)
            # Stage 1: Global search to find relevant communities
            community_results = await self.global_search(search_query)

            # Stage 2: Local search within top communities
            if community_results:
                community_ids = [c.community_id for c in community_results]
                chunk_results = await self.local_search(search_query, community_ids)
            else:
                # Fallback to searching all chunks
                chunk_results = await self.local_search(search_query, [])

        elapsed = time.time() - start_time

        return GraphRAGContext(
            query=query,
            mode=mode,
            community_results=community_results,
            chunk_results=chunk_results,
            expanded_query=expanded_query,
            total_communities_searched=len(community_results),
            total_chunks_searched=len(chunk_results),
            retrieval_time_seconds=elapsed
        )

    def format_context_for_llm(
        self,
        context: GraphRAGContext,
        include_community_context: bool = True,
        max_chunk_tokens: int = 4000
    ) -> str:
        """
        Format retrieved context for LLM consumption.

        Args:
            context: GraphRAG retrieval results
            include_community_context: Whether to include community summaries
            max_chunk_tokens: Maximum tokens for chunk content

        Returns:
            Formatted context string for LLM prompt
        """
        parts = []

        # Add community context (high-level overview)
        if include_community_context and context.community_results:
            parts.append("=== RELEVANT KNOWLEDGE AREAS ===")
            for c in context.community_results[:3]:
                parts.append(f"\n[{c.community_name}]")
                parts.append(c.summary)

        # Add chunk content (specific details)
        if context.chunk_results:
            parts.append("\n\n=== RELEVANT SOURCES ===")
            token_count = 0
            for chunk in context.chunk_results:
                chunk_text = f"\n[Source: {chunk.document_title}]\n{chunk.content}\n"
                chunk_tokens = len(chunk_text.split())

                if token_count + chunk_tokens > max_chunk_tokens:
                    break

                parts.append(chunk_text)
                token_count += chunk_tokens

        return '\n'.join(parts)


async def create_graphrag_retriever(
    neo4j_client,
    quickumls_path: Optional[str] = None
) -> GraphRAGRetriever:
    """
    Factory function to create a configured GraphRAG retriever.

    Args:
        neo4j_client: Neo4j client instance
        quickumls_path: Optional path to QuickUMLS installation

    Returns:
        Configured GraphRAGRetriever
    """
    umls_linker = None
    if quickumls_path:
        umls_linker = UMLSLinker(quickumls_path=quickumls_path)

    return GraphRAGRetriever(
        neo4j_client=neo4j_client,
        umls_linker=umls_linker
    )
