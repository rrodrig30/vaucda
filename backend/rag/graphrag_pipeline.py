"""
Microsoft GraphRAG Pipeline Implementation

Full implementation of Microsoft's GraphRAG approach:
1. Entity/Relationship Extraction from text chunks
2. Graph Construction with entities as nodes, relationships as edges
3. Community Detection using Leiden algorithm
4. Hierarchical Summarization (chunk -> document -> community)
5. Global Search with Map-Reduce pattern
6. Local Search with entity-focused graph traversal

References:
- "From Local to Global: A Graph RAG Approach to Query-Focused Summarization" (Microsoft Research, 2024)
- https://microsoft.github.io/graphrag/
"""

import uuid
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import numpy as np

try:
    import igraph as ig
    import leidenalg
    LEIDEN_AVAILABLE = True
except ImportError:
    LEIDEN_AVAILABLE = False
    logging.warning("leidenalg not available. Install: pip install igraph leidenalg")

import aiohttp

logger = logging.getLogger(__name__)


class CommunityTier(Enum):
    """Community hierarchy tiers."""
    MAJOR = 0      # Large, high-level topics
    MEDIUM = 1     # Mid-level concepts
    MINOR = 2      # Specific subtopics


@dataclass
class GraphRAGCommunity:
    """A community detected by Leiden algorithm.

    Hierarchy fields (added for recursive Leiden, paper-faithful per
    Edge et al. 2024 "From Local to Global"):
      - level: 0 for root-level communities, 1 for sub-communities of a level-0
        community, etc.
      - parent_community_id: id of the parent Community when level > 0.
    Structured-report fields (B3): title/rating/rating_explanation/findings —
    populated by generate_community_summaries when JSON output parses.
    """
    id: str
    name: str
    description: str
    tier: int
    size: int
    entity_names: List[str]
    key_terms: List[str]
    embedding: Optional[List[float]] = None
    summary: str = ""
    document_ids: List[str] = field(default_factory=list)
    # Hierarchy (B1)
    level: int = 0
    parent_community_id: Optional[str] = None
    # Structured findings (B3)
    title: str = ""
    rating: int = 0  # 1-10 importance; 0 means unrated
    rating_explanation: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MapReduceResult:
    """Result from map-reduce global search."""
    query: str
    intermediate_answers: List[Dict[str, Any]]  # Per-community answers
    final_answer: str
    communities_queried: int
    total_time_seconds: float


@dataclass
class LocalSearchResult:
    """Result from local entity-focused search."""
    query: str
    query_entities: List[str]
    relevant_entities: List[Dict[str, Any]]
    relevant_relationships: List[Dict[str, Any]]
    relevant_chunks: List[Dict[str, Any]]
    context: str
    total_time_seconds: float


class GraphRAGPipeline:
    """
    Complete GraphRAG pipeline implementation.

    Orchestrates:
    - Entity extraction from chunks
    - Entity-relationship graph construction
    - Leiden community detection
    - Hierarchical summarization
    - Map-reduce global search
    - Local entity-focused search
    """

    # Prompts for LLM operations
    # Structured community-report prompt (B3, Edge et al. 2024 §3.2).
    # JSON output requested explicitly; parsed robustly with regex fallback.
    COMMUNITY_SUMMARY_PROMPT = """You are producing a structured community report for a knowledge-graph community.

COMMUNITY ENTITIES:
{entities}

RELATIONSHIPS:
{relationships}

Output ONLY valid JSON with this exact shape (no prose, no markdown fences):

{{
  "title": "<2-7 word descriptive title for the community>",
  "summary": "<3-5 sentence summary covering theme, key entities, key relationships, clinical relevance>",
  "rating": <integer 1-10 indicating overall importance / centrality of this cluster to the corpus>,
  "rating_explanation": "<one sentence justifying the rating>",
  "findings": [
    {{"description": "<one specific finding from this community>", "importance": <integer 1-10>}}
  ]
}}

RULES:
- 3 to 7 findings, each a single concrete claim grounded in the entities/relationships above.
- Importance integers must be 1-10.
- Output JSON only. No preamble. No code fences."""

    GLOBAL_SEARCH_MAP_PROMPT = """Based on the following community summary, answer the query if relevant information is present.

COMMUNITY: {community_name}
SUMMARY: {community_summary}

QUERY: {query}

If this community contains relevant information for the query, provide a concise answer based on the summary.
If this community is NOT relevant to the query, respond with: "NOT_RELEVANT"

ANSWER:"""

    # B2: helpfulness scoring of intermediate community answers (Edge et al. 2024 §3.4).
    # Score ONLY — keep the prompt focused so we can parse robustly.
    GLOBAL_SEARCH_SCORE_PROMPT = """Rate how helpful the following partial answer is for the user's query.

USER QUERY: {query}

PARTIAL ANSWER FROM COMMUNITY "{community_name}":
{answer}

Score the helpfulness on a 0-100 integer scale where:
  0   = totally irrelevant or contradicts the query
  30  = tangentially related, low signal
  60  = useful supporting detail
  90+ = directly and substantively answers the query

Output ONLY the integer score (0-100). No prose, no explanation."""

    GLOBAL_SEARCH_REDUCE_PROMPT = """You are synthesizing answers from multiple knowledge communities to provide a comprehensive response.

QUERY: {query}

COMMUNITY ANSWERS:
{community_answers}

Synthesize these answers into a single, comprehensive response that:
1. Combines information from all relevant communities
2. Resolves any conflicts or contradictions
3. Provides a well-structured answer
4. Cites which communities contributed key information

SYNTHESIZED ANSWER:"""

    LOCAL_SEARCH_ENTITY_PROMPT = """Extract the key entities from this query that should be used for graph traversal.

QUERY: {query}

Return a JSON list of entity names to search for:
["entity1", "entity2", ...]

Only return the JSON list, nothing else.

ENTITIES:"""

    LOCAL_SEARCH_RESPONSE_PROMPT = """Based on the following graph context, answer the query.

QUERY: {query}

RELEVANT ENTITIES:
{entities}

RELATIONSHIPS:
{relationships}

SUPPORTING TEXT:
{chunks}

Provide a detailed answer based on the graph context above.

ANSWER:"""

    def __init__(
        self,
        neo4j_client,
        ollama_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3.1:8b",
        embedding_model: str = "nomic-embed-text",
        max_concurrent: int = 5,
        llm_timeout: int = 180
    ):
        """
        Initialize the GraphRAG pipeline.

        Args:
            neo4j_client: Neo4j client for database operations
            ollama_base_url: Ollama API base URL
            llm_model: LLM model for text generation
            embedding_model: Model for embeddings
            max_concurrent: Max concurrent LLM requests
            llm_timeout: LLM request timeout
        """
        self.neo4j = neo4j_client
        self.ollama_url = ollama_base_url
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.max_concurrent = max_concurrent
        self.llm_timeout = llm_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _call_llm(self, prompt: str, temperature: float = 0.3) -> str:
        """Call Ollama LLM API.

        num_ctx and keep_alive are explicit. Without num_ctx Ollama will
        load `llama3.1:8b` (the default) with its training context
        (131,072 tokens) × OLLAMA_NUM_PARALLEL slots, which ends up
        allocating ~140 GB of KV cache and wedging the GPU. 8K is
        plenty for query-entity extraction / map-reduce / scoring
        prompts. keep_alive matches the rest of the codebase so the
        model stays GPU-resident between calls.
        """
        try:
            from app.config import settings as _app_settings
            _keep_alive = _app_settings.OLLAMA_KEEP_ALIVE
        except Exception:
            _keep_alive = "24h"
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": _keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
                "num_predict": 2048,
            },
        }

        try:
            async with self._semaphore:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.ollama_url}/api/generate",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.llm_timeout)
                    ) as response:
                        if response.status != 200:
                            body = await response.text()
                            logger.error(
                                f"LLM API error: status={response.status} "
                                f"model={self.llm_model} body={body[:200]}"
                            )
                            return ""
                        result = await response.json()
                        return result.get("response", "")
        except Exception as e:
            # Surface useful detail. Empty `e` was the original
            # symptom of the wedged-Ollama timeout cascade.
            logger.error(
                f"LLM call failed: {type(e).__name__}: {e!r} "
                f"(model={self.llm_model}, timeout={self.llm_timeout}s)"
            )
            return ""

    # Class-level cache of the local sentence-transformers model so
    # all GraphRAGPipeline instances share one loaded model. Loading
    # MiniLM costs ~300 MB of RAM and ~300 ms once; subsequent calls
    # are sub-millisecond per text.
    _local_st_model = None
    _local_st_lock = asyncio.Lock()

    @classmethod
    async def _ensure_local_st_model(cls):
        if cls._local_st_model is not None:
            return cls._local_st_model
        async with cls._local_st_lock:
            if cls._local_st_model is None:
                # Run the (potentially slow) load in a thread so we
                # don't block the event loop.
                def _load():
                    from sentence_transformers import SentenceTransformer
                    return SentenceTransformer(
                        "all-MiniLM-L6-v2",
                        local_files_only=True,
                    )
                cls._local_st_model = await asyncio.get_event_loop().run_in_executor(
                    None, _load
                )
                logger.info(
                    "GraphRAG embedding: loaded local sentence-transformers/"
                    "all-MiniLM-L6-v2 (384-dim) — replaces unreliable "
                    "Ollama nomic-embed-text endpoint"
                )
        return cls._local_st_model

    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using local sentence-transformers.

        Previously called Ollama's /api/embeddings with nomic-embed-text,
        but that endpoint became unreliable on this Ollama instance
        (connection-hang behavior, every call hit 60 s timeout). The
        sentence-transformers `all-MiniLM-L6-v2` model is already
        cached locally (see HF_HUB_OFFLINE setup) and produces 384-dim
        embeddings sub-millisecond per text after first load.

        Note: community-level embeddings stored in Neo4j must use the
        same model. Run compute_community_embeddings() once to
        recompute them at the new dimension after switching.
        """
        if not text:
            return []
        try:
            model = await self._ensure_local_st_model()
            # SentenceTransformer.encode is sync/CPU-or-GPU; offload
            # to thread pool so the event loop stays responsive.
            def _encode():
                return model.encode(text, normalize_embeddings=False).tolist()
            return await asyncio.get_event_loop().run_in_executor(None, _encode)
        except Exception as e:
            logger.error(
                f"Embedding call failed: {type(e).__name__}: {e!r} "
                f"(local sentence-transformers/all-MiniLM-L6-v2)"
            )
            return []

    # =========================================================================
    # Phase 1: Entity Extraction (delegated to entity_extractor.py)
    # =========================================================================

    async def extract_entities_from_database(
        self,
        batch_size: int = 100,
        max_chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract entities from all chunks in the database.

        This is Phase 1 of the GraphRAG pipeline.
        """
        from .entity_extractor import EntityExtractor, store_entities_in_neo4j

        # Get chunks from database
        query = """
        MATCH (c:Chunk)
        WHERE NOT EXISTS((c)-[:HAS_ENTITY]->(:Entity))
        RETURN c.id AS id, c.content AS content
        """
        if max_chunks:
            query += f" LIMIT {max_chunks}"

        chunks = await self.neo4j.execute_query(query)

        if not chunks:
            logger.info("No chunks without entities found")
            return {"extracted": 0, "total_chunks": 0}

        logger.info(f"Extracting entities from {len(chunks)} chunks")

        # Create extractor
        extractor = EntityExtractor(
            ollama_base_url=self.ollama_url,
            model=self.llm_model,
            max_concurrent=self.max_concurrent
        )

        # Extract entities
        result = await extractor.extract_from_chunks(
            [{"id": c["id"], "content": c["content"]} for c in chunks],
            progress_callback=lambda done, total: logger.info(f"Progress: {done}/{total}")
        )

        # Store in Neo4j
        await store_entities_in_neo4j(self.neo4j, result)

        return {
            "extracted_entities": result.entity_count,
            "extracted_relationships": result.relationship_count,
            "total_chunks": len(chunks),
            "time_seconds": result.total_time_seconds
        }

    # =========================================================================
    # Phase 2: Community Detection with Leiden
    # =========================================================================

    async def detect_communities(
        self,
        resolution: float = 1.0,
        min_community_size: int = 3,
        max_levels: int = 2,
        min_size_to_recurse: int = 15
    ) -> List[GraphRAGCommunity]:
        """
        Detect communities in the entity-relationship graph using HIERARCHICAL Leiden.

        This is Phase 2 of the GraphRAG pipeline. Implements the paper-faithful
        recursive scheme from Edge et al. 2024 "From Local to Global":

          1. Run Leiden on the full Entity/RELATED_TO graph -> level-0 communities.
          2. For each level-0 community whose size >= min_size_to_recurse, build
             the induced subgraph (entities + edges restricted to that community)
             and run Leiden again with the same resolution -> level-1 sub-communities.
          3. Optionally recurse one more level (controlled by max_levels) for
             very large clusters.

        Hierarchy is encoded on the returned GraphRAGCommunity objects via
        `level` and `parent_community_id` fields. The :HAS_SUBCOMMUNITY edge
        is materialised in store_communities below.

        Args:
            resolution: Leiden resolution parameter (>1 = more, smaller communities).
            min_community_size: Drop communities smaller than this at any level.
            max_levels: Maximum recursion depth. 1 = flat (level 0 only),
                2 = one round of subdivision (default), 3 = two rounds, etc.
            min_size_to_recurse: A community must have at least this many entities
                to be subdivided. Smaller clusters are kept flat at their level.

        Returns:
            Flat list of all communities across all levels. Hierarchy is
            recoverable via .level / .parent_community_id (and via
            HAS_SUBCOMMUNITY edges once stored).
        """
        if not LEIDEN_AVAILABLE:
            raise ImportError("Leiden algorithm requires: pip install igraph leidenalg")

        logger.info(
            "Running HIERARCHICAL Leiden community detection on entity graph "
            "(max_levels=%d, min_size_to_recurse=%d, resolution=%.2f)",
            max_levels, min_size_to_recurse, resolution
        )

        # ---- Pull the full entity / relationship graph once ----
        entities_query = """
        MATCH (e:Entity)
        RETURN e.name AS name, e.type AS type, e.description AS description
        """
        entities = await self.neo4j.execute_query(entities_query)

        relationships_query = """
        MATCH (e1:Entity)-[r:RELATED_TO]->(e2:Entity)
        RETURN e1.name AS source, e2.name AS target,
               r.type AS type, r.weight AS weight
        """
        relationships = await self.neo4j.execute_query(relationships_query)

        if not entities:
            logger.warning("No entities found for community detection")
            return []

        # ---- Build the FULL igraph; we'll use induced subgraphs for recursion ----
        entity_map = {e['name']: i for i, e in enumerate(entities)}
        edges = []
        weights = []

        for rel in relationships:
            if rel['source'] in entity_map and rel['target'] in entity_map:
                edges.append((entity_map[rel['source']], entity_map[rel['target']]))
                weights.append(rel.get('weight', 1.0) or 1.0)

        g = ig.Graph(n=len(entities), edges=edges, directed=False)
        g.vs['name'] = [e['name'] for e in entities]
        g.vs['type'] = [e['type'] for e in entities]
        g.vs['description'] = [e.get('description', '') for e in entities]
        if weights:
            g.es['weight'] = weights

        total_nodes = g.vcount()
        all_communities: List[GraphRAGCommunity] = []

        # ---- Recursive Leiden ----
        # Each work item: (subgraph, vertex_indices_in_full_graph, level, parent_id)
        # We drive recursion iteratively to keep stack flat & predictable.
        from collections import deque
        # Seed with the full graph at level 0.
        work: deque = deque()
        work.append((g, list(range(total_nodes)), 0, None))

        while work:
            sub_g, full_indices, level, parent_id = work.popleft()

            if sub_g.vcount() < min_community_size:
                continue

            sub_partition = leidenalg.find_partition(
                sub_g,
                leidenalg.RBConfigurationVertexPartition,
                weights='weight' if 'weight' in sub_g.es.attributes() else None,
                resolution_parameter=resolution,
                seed=42
            )

            for member_local_indices in sub_partition:
                if len(member_local_indices) < min_community_size:
                    continue

                # Map subgraph-local indices back to the original full-graph indices.
                member_full_indices = [full_indices[i] for i in member_local_indices]
                entity_names = [g.vs[i]['name'] for i in member_full_indices]
                entity_types = [g.vs[i]['type'] for i in member_full_indices]

                term_freq: Dict[str, int] = {}
                for name in entity_names:
                    for word in name.lower().split():
                        if len(word) > 3:
                            term_freq[word] = term_freq.get(word, 0) + 1
                key_terms = sorted(term_freq.keys(), key=lambda k: term_freq[k], reverse=True)[:10]

                name = self._generate_community_name(entity_names, entity_types, key_terms)
                size = len(member_full_indices)

                # Tier is now derived from level + size; level is the hierarchy axis.
                # Keep tier semantics for backward compat: level-0 large = MAJOR,
                # level-0 small = MEDIUM, deeper levels = MINOR.
                if level == 0 and size > total_nodes * 0.15:
                    tier = CommunityTier.MAJOR.value
                elif level == 0:
                    tier = CommunityTier.MEDIUM.value
                else:
                    tier = CommunityTier.MINOR.value

                comm = GraphRAGCommunity(
                    id=str(uuid.uuid4()),
                    name=name,
                    description=(
                        f"L{level} community of {size} entities related to "
                        f"{', '.join(key_terms[:3]) if key_terms else 'mixed topics'}"
                    ),
                    tier=tier,
                    size=size,
                    entity_names=entity_names,
                    key_terms=key_terms,
                    level=level,
                    parent_community_id=parent_id,
                )
                all_communities.append(comm)

                # Recurse if we still have levels and the cluster is large enough.
                if (level + 1) < max_levels and size >= min_size_to_recurse:
                    # Induced subgraph from the FULL graph restricted to this
                    # community's vertices. This carries weights through.
                    induced = g.subgraph(member_full_indices)
                    work.append((induced, member_full_indices, level + 1, comm.id))

        all_communities.sort(key=lambda c: (c.level, -c.size))

        # Diagnostics — modularity from the *root* partition is what users expect.
        try:
            root_partition = leidenalg.find_partition(
                g,
                leidenalg.RBConfigurationVertexPartition,
                weights='weight' if weights else None,
                resolution_parameter=resolution,
                seed=42
            )
            mod = root_partition.modularity
        except Exception:
            mod = float('nan')

        levels_seen = sorted({c.level for c in all_communities})
        logger.info(
            "Detected %d communities across levels %s (root modularity: %.3f)",
            len(all_communities), levels_seen, mod
        )
        return all_communities

    def _generate_community_name(
        self,
        entity_names: List[str],
        entity_types: List[str],
        key_terms: List[str]
    ) -> str:
        """Generate descriptive name for a community."""
        # Count entity types
        type_counts = {}
        for t in entity_types:
            type_counts[t] = type_counts.get(t, 0) + 1

        dominant_type = max(type_counts.keys(), key=lambda k: type_counts[k]) if type_counts else "Concept"

        # Use top key terms
        if key_terms:
            terms = [t.title() for t in key_terms[:2]]
            return f"{' & '.join(terms)} ({dominant_type})"
        elif entity_names:
            return f"{entity_names[0]} Cluster"
        else:
            return "Unnamed Community"

    async def store_communities(
        self,
        communities: List[GraphRAGCommunity]
    ) -> int:
        """Store detected communities in Neo4j.

        Schema (canonical writer, owned by this method):
          (:Community {
              id, name, description, tier, size, key_terms, created_at,
              level, parent_community_id,
              # Structured-report fields (B3) — populated later by
              # generate_community_summaries; kept nullable here.
              title, summary, rating, rating_explanation, findings_json
          })
          (:Entity)-[:BELONGS_TO_COMMUNITY]->(:Community)
          (:Document)-[:IN_COMMUNITY {entity_count}]->(:Community)
          (:Community)-[:HAS_SUBCOMMUNITY]->(:Community)   # B1 hierarchy
        """
        # First, clear old communities
        await self.neo4j.execute_query("MATCH (c:Community) DETACH DELETE c")

        stored = 0
        for comm in communities:
            # Create community node — includes hierarchy fields (B1).
            create_query = """
            CREATE (c:Community {
                id: $id,
                name: $name,
                description: $description,
                tier: $tier,
                size: $size,
                key_terms: $key_terms,
                level: $level,
                parent_community_id: $parent_community_id,
                created_at: datetime()
            })
            WITH c
            UNWIND $entity_names AS entity_name
            MATCH (e:Entity {name: entity_name})
            MERGE (e)-[:BELONGS_TO_COMMUNITY]->(c)
            """

            await self.neo4j.execute_query(create_query, {
                'id': comm.id,
                'name': comm.name,
                'description': comm.description,
                'tier': comm.tier,
                'size': comm.size,
                'key_terms': comm.key_terms,
                'level': comm.level,
                'parent_community_id': comm.parent_community_id,
                'entity_names': comm.entity_names
            })
            stored += 1

        # Materialise hierarchy edges: (parent)-[:HAS_SUBCOMMUNITY]->(child).
        # Built from parent_community_id stored on each child.
        hierarchy_query = """
        MATCH (child:Community)
        WHERE child.parent_community_id IS NOT NULL
        MATCH (parent:Community {id: child.parent_community_id})
        MERGE (parent)-[:HAS_SUBCOMMUNITY]->(child)
        """
        await self.neo4j.execute_query(hierarchy_query)

        # Link documents to communities through their chunks and entities
        link_query = """
        MATCH (d:Document)<-[:BELONGS_TO]-(chunk:Chunk)-[:HAS_ENTITY]->(e:Entity)-[:BELONGS_TO_COMMUNITY]->(c:Community)
        WITH d, c, count(DISTINCT e) AS entity_count
        MERGE (d)-[r:IN_COMMUNITY]->(c)
        SET r.entity_count = entity_count
        """
        await self.neo4j.execute_query(link_query)

        logger.info(f"Stored {stored} communities")
        return stored

    # =========================================================================
    # Phase 3: Hierarchical Summarization
    # =========================================================================

    @staticmethod
    def _parse_community_report(raw: str) -> Dict[str, Any]:
        """Parse the LLM's structured-report JSON robustly.

        Returns a dict with keys: title, summary, rating, rating_explanation,
        findings. Falls back to treating the raw text as a free-form summary
        if JSON parsing fails — preserving backward compatibility with old
        prompt outputs and any LLM that ignores the JSON instruction.
        """
        import json
        import re as _re

        if not raw:
            return {
                "title": "",
                "summary": "",
                "rating": 0,
                "rating_explanation": "",
                "findings": [],
            }

        text = raw.strip()
        # Strip markdown fences if the model emitted them despite instructions.
        text = _re.sub(r"^```(?:json)?\s*", "", text)
        text = _re.sub(r"\s*```\s*$", "", text)

        # Try to locate the outermost JSON object.
        json_obj = None
        match = _re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                json_obj = json.loads(match.group())
            except json.JSONDecodeError:
                json_obj = None

        if not isinstance(json_obj, dict):
            # Backward-compat: treat as plain summary text.
            return {
                "title": "",
                "summary": text,
                "rating": 0,
                "rating_explanation": "",
                "findings": [],
            }

        def _coerce_int(v, lo: int, hi: int, default: int = 0) -> int:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, iv))

        findings_raw = json_obj.get("findings") or []
        findings: List[Dict[str, Any]] = []
        if isinstance(findings_raw, list):
            for f in findings_raw:
                if isinstance(f, dict):
                    desc = str(f.get("description", "")).strip()
                    if not desc:
                        continue
                    findings.append({
                        "description": desc,
                        "importance": _coerce_int(f.get("importance"), 1, 10, 5),
                    })
                elif isinstance(f, str) and f.strip():
                    findings.append({"description": f.strip(), "importance": 5})

        return {
            "title": str(json_obj.get("title", "")).strip(),
            "summary": str(json_obj.get("summary", "")).strip(),
            "rating": _coerce_int(json_obj.get("rating"), 1, 10, 0),
            "rating_explanation": str(json_obj.get("rating_explanation", "")).strip(),
            "findings": findings,
        }

    async def generate_community_summaries(
        self,
        communities: Optional[List[GraphRAGCommunity]] = None
    ) -> int:
        """
        Generate STRUCTURED community reports for all communities using LLM.

        This is Phase 3 of the GraphRAG pipeline. Implements paper-faithful
        structured reports (B3) with title / summary / rating / findings, and
        persists each on the :Community node:

          c.title (str)
          c.summary (str)              -- backward-compatible plain text
          c.rating (int 1-10)          -- 0 if unparsed
          c.rating_explanation (str)
          c.findings_json (str)        -- JSON-encoded list of {description,importance}

        Old summaries already stored as c.summary are preserved as-is when the
        new run is skipped (the WHERE clause in the loader ignores already-summarized
        nodes).
        """
        import json as _json

        if communities is None:
            # Load from database — only nodes that don't have a parsed structured
            # report yet. Use c.title presence as the marker for "structured".
            query = """
            MATCH (c:Community)
            WHERE (c.summary IS NULL OR c.summary = '')
               OR (c.title IS NULL)
            RETURN c.id AS id, c.name AS name, c.description AS description,
                   c.key_terms AS key_terms
            """
            comm_data = await self.neo4j.execute_query(query)
            communities = [
                GraphRAGCommunity(
                    id=c['id'],
                    name=c['name'],
                    description=c.get('description', ''),
                    tier=0,
                    size=0,
                    entity_names=[],
                    key_terms=c.get('key_terms', [])
                )
                for c in comm_data
            ]

        if not communities:
            logger.info("No communities need summarization")
            return 0

        logger.info(f"Generating structured community reports for {len(communities)} communities")

        summarized = 0
        for comm in communities:
            # Get entities and relationships for this community
            entities_query = """
            MATCH (e:Entity)-[:BELONGS_TO_COMMUNITY]->(c:Community {id: $comm_id})
            RETURN e.name AS name, e.type AS type, e.description AS description
            LIMIT 50
            """
            entities = await self.neo4j.execute_query(entities_query, {'comm_id': comm.id})

            relationships_query = """
            MATCH (e1:Entity)-[:BELONGS_TO_COMMUNITY]->(c:Community {id: $comm_id})
            MATCH (e1)-[r:RELATED_TO]->(e2:Entity)
            WHERE (e2)-[:BELONGS_TO_COMMUNITY]->(c)
            RETURN e1.name AS source, r.type AS type, e2.name AS target
            LIMIT 100
            """
            relationships = await self.neo4j.execute_query(relationships_query, {'comm_id': comm.id})

            if not entities:
                continue

            # Format for prompt
            entities_text = "\n".join(
                f"- {e['name']} ({e['type']}): {e.get('description', '')}"
                for e in entities[:30]
            )
            relationships_text = "\n".join(
                f"- {r['source']} --[{r['type']}]--> {r['target']}"
                for r in relationships[:50]
            )

            prompt = self.COMMUNITY_SUMMARY_PROMPT.format(
                entities=entities_text,
                relationships=relationships_text or "No explicit relationships"
            )

            raw = await self._call_llm(prompt, temperature=0.3)
            if not raw:
                continue

            report = self._parse_community_report(raw)
            summary_text = report["summary"] or raw.strip()

            # Persist all structured fields. findings_json keeps it queryable
            # without exploding into N more nodes.
            update_query = """
            MATCH (c:Community {id: $comm_id})
            SET c.title = $title,
                c.summary = $summary,
                c.rating = $rating,
                c.rating_explanation = $rating_explanation,
                c.findings_json = $findings_json
            """
            await self.neo4j.execute_query(update_query, {
                'comm_id': comm.id,
                'title': report["title"],
                'summary': summary_text,
                'rating': report["rating"],
                'rating_explanation': report["rating_explanation"],
                'findings_json': _json.dumps(report["findings"]),
            })
            summarized += 1

            # Also create HierarchicalSummary node — same schema as before so
            # downstream readers (e.g. graphrag_retriever) keep working.
            summary_query = """
            MATCH (c:Community {id: $comm_id})
            CREATE (s:HierarchicalSummary {
                id: $summary_id,
                entity_id: $comm_id,
                entity_type: 'community',
                level: 'community',
                content: $summary,
                created_at: datetime()
            })
            CREATE (s)-[:SUMMARIZES]->(c)
            """
            await self.neo4j.execute_query(summary_query, {
                'comm_id': comm.id,
                'summary_id': str(uuid.uuid4()),
                'summary': summary_text,
            })

        logger.info(f"Generated {summarized} community reports")
        return summarized

    async def compute_community_embeddings(self) -> int:
        """Compute embeddings for communities based on their summaries."""
        query = """
        MATCH (c:Community)
        WHERE c.embedding IS NULL AND c.summary IS NOT NULL
        RETURN c.id AS id, c.name AS name, c.summary AS summary
        """
        communities = await self.neo4j.execute_query(query)

        if not communities:
            return 0

        updated = 0
        for comm in communities:
            text = f"{comm['name']}. {comm.get('summary', '')}"
            embedding = await self._get_embedding(text)

            if embedding:
                update_query = """
                MATCH (c:Community {id: $comm_id})
                SET c.embedding = $embedding
                """
                await self.neo4j.execute_query(update_query, {
                    'comm_id': comm['id'],
                    'embedding': embedding
                })
                updated += 1

        logger.info(f"Computed embeddings for {updated} communities")
        return updated

    # =========================================================================
    # Phase 4: Global Search with Map-Reduce
    # =========================================================================

    @staticmethod
    def _parse_score_0_100(raw: str) -> int:
        """Parse a 0-100 integer from possibly-noisy LLM output. Returns 0 on failure."""
        import re as _re
        if not raw:
            return 0
        m = _re.search(r"\b(\d{1,3})\b", raw)
        if not m:
            return 0
        try:
            v = int(m.group(1))
        except ValueError:
            return 0
        return max(0, min(100, v))

    async def global_search(
        self,
        query: str,
        max_communities: int = 10,
        parallel: bool = True,
        min_rating: int = 3,
        helpfulness_threshold: int = 30,
        max_answers_to_reduce: Optional[int] = None
    ) -> MapReduceResult:
        """
        Perform global search using map-reduce across communities.

        Implements Microsoft GraphRAG's global search strategy
        (Edge et al. 2024 §3.3-3.4) with paper-faithful enhancements:

          1. SELECT communities, pre-filtering by structured rating (B3) and
             ranking by rating x cosine_similarity to the query embedding.
          2. MAP: Query each selected community summary in parallel.
          3. FILTER: Drop NOT_RELEVANT.
          4. SCORE (B2): For each surviving partial answer, ask the LLM how
             helpful it is for the original query (0-100). Drop scores below
             helpfulness_threshold. Sort by score desc.
          5. REDUCE: Synthesize the top max_answers_to_reduce answers.

        Args:
            query: Natural-language query.
            max_communities: Max communities to consider in MAP.
            parallel: Run MAP and SCORE concurrently (under self._semaphore).
            min_rating: Skip communities whose c.rating < this. 0 disables.
                Default 3 per audit; pass 0 to include unrated/low-rated content.
            helpfulness_threshold: Drop partial answers below this score (0-100).
            max_answers_to_reduce: Pass at most this many top-scored answers
                to REDUCE. None = pass all surviving.
        """
        start_time = time.time()

        # B3: rating-aware community selection. We pull a generous candidate
        # pool, then score by rating * cosine(query, community.embedding).
        # Communities with rating < min_rating are dropped (unless min_rating=0).
        candidate_query = """
        MATCH (c:Community)
        WHERE c.summary IS NOT NULL AND c.summary <> ''
          AND ($min_rating = 0 OR coalesce(c.rating, 0) >= $min_rating
               OR coalesce(c.rating, 0) = 0)
        RETURN c.id AS id, c.name AS name, c.summary AS summary,
               c.tier AS tier, c.rating AS rating, c.embedding AS embedding,
               c.level AS level
        """
        candidates = await self.neo4j.execute_query(
            candidate_query,
            {'min_rating': min_rating}
        )

        if not candidates:
            return MapReduceResult(
                query=query,
                intermediate_answers=[],
                final_answer="No knowledge communities available for search.",
                communities_queried=0,
                total_time_seconds=time.time() - start_time
            )

        # Compute query embedding once for rating x similarity ranking. If the
        # embedding service is unavailable we fall back to rating-only ranking.
        q_emb = await self._get_embedding(query)

        def _cos(a: List[float], b: List[float]) -> float:
            if not a or not b or len(a) != len(b):
                return 0.0
            num = 0.0
            na = 0.0
            nb = 0.0
            for x, y in zip(a, b):
                num += x * y
                na += x * x
                nb += y * y
            if na == 0.0 or nb == 0.0:
                return 0.0
            return num / ((na ** 0.5) * (nb ** 0.5))

        ranked = []
        for c in candidates:
            rating = c.get('rating') or 0
            # Treat unrated (0) as a neutral 5 so we don't penalise legacy data.
            effective_rating = rating if rating > 0 else 5
            sim = _cos(q_emb, c.get('embedding') or [])
            # rating in [1,10], sim in [-1,1] (typically [0,1] for normalised
            # embeddings). Use rating as a multiplicative weight.
            score = effective_rating * (sim if sim > 0 else 0.05)
            ranked.append((score, c))

        ranked.sort(key=lambda t: t[0], reverse=True)
        communities = [c for _, c in ranked[:max_communities]]

        # MAP Phase: Query each selected community.
        intermediate_answers: List[Dict[str, Any]] = []

        async def query_community(comm: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            prompt = self.GLOBAL_SEARCH_MAP_PROMPT.format(
                community_name=comm['name'],
                community_summary=comm['summary'],
                query=query
            )
            response = await self._call_llm(prompt, temperature=0.5)
            if not response:
                return None
            response = response.strip()
            if "NOT_RELEVANT" in response:
                return None
            return {
                'community_id': comm['id'],
                'community_name': comm['name'],
                'response': response,
                'community_rating': comm.get('rating') or 0,
            }

        if parallel:
            map_results = await asyncio.gather(*[query_community(c) for c in communities])
            intermediate_answers = [r for r in map_results if r]
        else:
            for c in communities:
                r = await query_community(c)
                if r:
                    intermediate_answers.append(r)

        # SCORE Phase (B2): helpfulness scoring of partial answers.
        async def score_answer(ans: Dict[str, Any]) -> int:
            prompt = self.GLOBAL_SEARCH_SCORE_PROMPT.format(
                query=query,
                community_name=ans['community_name'],
                answer=ans['response'],
            )
            raw = await self._call_llm(prompt, temperature=0.0)
            return self._parse_score_0_100(raw)

        if intermediate_answers:
            if parallel:
                scores = await asyncio.gather(
                    *[score_answer(a) for a in intermediate_answers]
                )
            else:
                scores = []
                for a in intermediate_answers:
                    scores.append(await score_answer(a))

            for a, s in zip(intermediate_answers, scores):
                a['helpfulness'] = s

            # Drop low-scoring answers and sort by helpfulness desc.
            intermediate_answers = [
                a for a in intermediate_answers if a['helpfulness'] >= helpfulness_threshold
            ]
            intermediate_answers.sort(key=lambda a: a['helpfulness'], reverse=True)

            if max_answers_to_reduce is not None:
                intermediate_answers = intermediate_answers[:max_answers_to_reduce]

        # REDUCE Phase: Synthesize answers
        if not intermediate_answers:
            final_answer = "No relevant information found in the knowledge base for this query."
        elif len(intermediate_answers) == 1:
            final_answer = intermediate_answers[0]['response']
        else:
            community_answers = "\n\n".join(
                f"[{a['community_name']} | helpfulness={a.get('helpfulness', '?')}]\n{a['response']}"
                for a in intermediate_answers
            )

            reduce_prompt = self.GLOBAL_SEARCH_REDUCE_PROMPT.format(
                query=query,
                community_answers=community_answers
            )

            final_answer = await self._call_llm(reduce_prompt, temperature=0.3)

        elapsed = time.time() - start_time

        return MapReduceResult(
            query=query,
            intermediate_answers=intermediate_answers,
            final_answer=(final_answer or "").strip(),
            communities_queried=len(communities),
            total_time_seconds=elapsed
        )

    # =========================================================================
    # Phase 5: Local Search with Entity Extraction
    # =========================================================================

    async def local_search(
        self,
        query: str,
        max_entities: int = 20,
        max_chunks: int = 10
    ) -> LocalSearchResult:
        """
        Perform local search by extracting query entities and traversing graph.

        This implements Microsoft GraphRAG's local search strategy:
        1. Extract entities from the query
        2. Find matching entities in the graph
        3. Traverse relationships to gather context
        4. Retrieve relevant source chunks
        5. Generate response using gathered context
        """
        start_time = time.time()

        # Extract entities from query
        extract_prompt = self.LOCAL_SEARCH_ENTITY_PROMPT.format(query=query)
        entities_response = await self._call_llm(extract_prompt, temperature=0.1)

        # Parse entities
        import json
        import re
        query_entities = []
        try:
            json_match = re.search(r'\[.*\]', entities_response)
            if json_match:
                query_entities = json.loads(json_match.group())
        except:
            # Fallback: use query words as entities
            query_entities = [w for w in query.split() if len(w) > 3]

        if not query_entities:
            query_entities = [query]  # Use full query as fallback

        # Find matching entities in graph
        entities_query = """
        UNWIND $query_entities AS qe
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower(qe)
           OR toLower(qe) CONTAINS toLower(e.name)
        RETURN DISTINCT e.name AS name, e.type AS type, e.description AS description
        LIMIT $max_entities
        """
        relevant_entities = await self.neo4j.execute_query(entities_query, {
            'query_entities': query_entities,
            'max_entities': max_entities
        })

        # Get relationships for these entities
        if relevant_entities:
            entity_names = [e['name'] for e in relevant_entities]
            relationships_query = """
            MATCH (e1:Entity)-[r:RELATED_TO]->(e2:Entity)
            WHERE e1.name IN $entity_names OR e2.name IN $entity_names
            RETURN e1.name AS source, r.type AS type, e2.name AS target,
                   r.description AS description
            LIMIT 100
            """
            relevant_relationships = await self.neo4j.execute_query(relationships_query, {
                'entity_names': entity_names
            })
        else:
            relevant_relationships = []

        # Get relevant chunks
        chunks_query = """
        MATCH (c:Chunk)
        WHERE any(qe IN $query_entities WHERE toLower(c.content) CONTAINS toLower(qe))
        MATCH (c)-[:BELONGS_TO]->(d:Document)
        RETURN c.content AS content, d.title AS document_title
        LIMIT $max_chunks
        """
        relevant_chunks = await self.neo4j.execute_query(chunks_query, {
            'query_entities': query_entities,
            'max_chunks': max_chunks
        })

        # Build context
        entities_text = "\n".join(
            f"- {e['name']} ({e['type']}): {e.get('description', '')}"
            for e in relevant_entities
        ) or "No matching entities found"

        relationships_text = "\n".join(
            f"- {r['source']} --[{r['type']}]--> {r['target']}"
            for r in relevant_relationships
        ) or "No relationships found"

        chunks_text = "\n\n".join(
            f"[{c.get('document_title', 'Unknown')}]\n{c['content'][:500]}"
            for c in relevant_chunks
        ) or "No supporting text found"

        # Generate response
        response_prompt = self.LOCAL_SEARCH_RESPONSE_PROMPT.format(
            query=query,
            entities=entities_text,
            relationships=relationships_text,
            chunks=chunks_text
        )

        context = await self._call_llm(response_prompt, temperature=0.3)

        elapsed = time.time() - start_time

        return LocalSearchResult(
            query=query,
            query_entities=query_entities,
            relevant_entities=[dict(e) for e in relevant_entities],
            relevant_relationships=[dict(r) for r in relevant_relationships],
            relevant_chunks=[dict(c) for c in relevant_chunks],
            context=context.strip(),
            total_time_seconds=elapsed
        )

    # =========================================================================
    # Full Pipeline Execution
    # =========================================================================

    async def run_full_pipeline(
        self,
        extract_entities: bool = True,
        detect_communities: bool = True,
        generate_summaries: bool = True,
        compute_embeddings: bool = True,
        max_chunks_for_extraction: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run the complete GraphRAG pipeline.

        Args:
            extract_entities: Whether to extract entities from chunks
            detect_communities: Whether to run Leiden community detection
            generate_summaries: Whether to generate community summaries
            compute_embeddings: Whether to compute community embeddings
            max_chunks_for_extraction: Limit chunks for entity extraction

        Returns:
            Pipeline execution results
        """
        results = {
            'started_at': datetime.utcnow().isoformat(),
            'stages': {}
        }

        total_start = time.time()

        # Phase 1: Entity Extraction
        if extract_entities:
            logger.info("=" * 50)
            logger.info("PHASE 1: Entity Extraction")
            logger.info("=" * 50)
            extraction_result = await self.extract_entities_from_database(
                max_chunks=max_chunks_for_extraction
            )
            results['stages']['entity_extraction'] = extraction_result

        # Phase 2: Community Detection
        if detect_communities:
            logger.info("=" * 50)
            logger.info("PHASE 2: Community Detection")
            logger.info("=" * 50)
            communities = await self.detect_communities()
            stored = await self.store_communities(communities)
            results['stages']['community_detection'] = {
                'communities_detected': len(communities),
                'communities_stored': stored
            }

        # Phase 3: Hierarchical Summarization
        if generate_summaries:
            logger.info("=" * 50)
            logger.info("PHASE 3: Hierarchical Summarization")
            logger.info("=" * 50)
            summarized = await self.generate_community_summaries()
            results['stages']['summarization'] = {
                'summaries_generated': summarized
            }

        # Phase 4: Compute Embeddings
        if compute_embeddings:
            logger.info("=" * 50)
            logger.info("PHASE 4: Community Embeddings")
            logger.info("=" * 50)
            embedded = await self.compute_community_embeddings()
            results['stages']['embeddings'] = {
                'embeddings_computed': embedded
            }

        total_time = time.time() - total_start
        results['total_time_seconds'] = total_time
        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info("=" * 50)
        logger.info(f"PIPELINE COMPLETE in {total_time:.1f}s")
        logger.info("=" * 50)

        return results
