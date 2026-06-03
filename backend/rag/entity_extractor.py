"""
GraphRAG Entity and Relationship Extractor

Extracts entities and relationships from text chunks using LLM,
following the Microsoft GraphRAG approach.

The extraction pipeline:
1. Process each chunk through LLM to extract entities
2. Extract relationships between entities
3. Build entity-relationship graph for community detection
"""

import re
import json
import uuid
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import aiohttp

logger = logging.getLogger(__name__)


# Default entity types for clinical domain
CLINICAL_ENTITY_TYPES = [
    "Disease",
    "Symptom",
    "Medication",
    "Procedure",
    "AnatomicalStructure",
    "ClinicalFinding",
    "DiagnosticTest",
    "RiskFactor",
    "Treatment",
    "Biomarker",
    "GeneticMarker",
    "ClinicalGuideline",
    "EvidenceLevel",
    "Organization",
    "Researcher"
]

# Default relationship types
CLINICAL_RELATIONSHIP_TYPES = [
    "treats",
    "causes",
    "symptom_of",
    "diagnoses",
    "risk_factor_for",
    "associated_with",
    "located_in",
    "part_of",
    "contraindicated_for",
    "recommended_by",
    "measured_by",
    "indicates",
    "precedes",
    "follows"
]


@dataclass
class Entity:
    """Represents an extracted entity."""
    id: str
    name: str
    type: str
    description: str = ""
    source_chunk_id: Optional[str] = None
    confidence: float = 1.0

    def __hash__(self):
        return hash((self.name.lower(), self.type.lower()))

    def __eq__(self, other):
        if not isinstance(other, Entity):
            return False
        return self.name.lower() == other.name.lower() and self.type.lower() == other.type.lower()


@dataclass
class Relationship:
    """Represents an extracted relationship between entities."""
    id: str
    source_entity: str  # Entity name
    target_entity: str  # Entity name
    relationship_type: str
    description: str = ""
    weight: float = 1.0
    source_chunk_id: Optional[str] = None

    def __hash__(self):
        return hash((self.source_entity.lower(), self.target_entity.lower(), self.relationship_type.lower()))


@dataclass
class ExtractionResult:
    """Result of entity/relationship extraction from a chunk."""
    chunk_id: str
    entities: List[Entity]
    relationships: List[Relationship]
    extraction_time_seconds: float = 0.0


@dataclass
class GraphExtractionResult:
    """Result of full graph extraction from all chunks."""
    entities: Dict[str, Entity]  # name -> Entity (merged)
    relationships: List[Relationship]
    entity_count: int
    relationship_count: int
    chunk_count: int
    total_time_seconds: float


class EntityExtractor:
    """
    Extracts entities and relationships from text using LLM.

    Follows Microsoft GraphRAG approach:
    - Uses LLM prompts to extract structured entity/relationship data
    - Merges duplicate entities across chunks
    - Builds comprehensive entity-relationship graph
    """

    ENTITY_EXTRACTION_PROMPT = """You are an expert clinical knowledge extractor. Extract all entities and relationships from the following text.

ENTITY TYPES TO EXTRACT:
{entity_types}

RELATIONSHIP TYPES TO EXTRACT:
{relationship_types}

TEXT:
{text}

OUTPUT FORMAT (JSON):
{{
  "entities": [
    {{"name": "entity name", "type": "EntityType", "description": "brief description"}}
  ],
  "relationships": [
    {{"source": "source entity name", "target": "target entity name", "type": "relationship_type", "description": "brief description of relationship"}}
  ]
}}

RULES:
1. Extract ALL entities mentioned, even if they appear multiple times
2. Entity names should be normalized (e.g., "PSA" not "psa" or "Prostate-Specific Antigen")
3. Only extract relationships where BOTH entities exist in your entity list
4. Be specific with entity types - use the most appropriate type from the list
5. If uncertain about an entity type, use the closest match
6. Descriptions should be concise (1 sentence max)

Return ONLY valid JSON, no other text."""

    ENTITY_MERGE_PROMPT = """You are merging duplicate entities. Given these entity descriptions for "{entity_name}" (type: {entity_type}), create a single comprehensive description.

DESCRIPTIONS:
{descriptions}

Return a single merged description (1-2 sentences max) that captures the key information from all descriptions.
Return ONLY the merged description text, nothing else."""

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        entity_types: Optional[List[str]] = None,
        relationship_types: Optional[List[str]] = None,
        max_concurrent: int = 5,
        timeout: int = 120
    ):
        """
        Initialize the entity extractor.

        Args:
            ollama_base_url: Ollama API base URL
            model: LLM model to use
            entity_types: List of entity types to extract
            relationship_types: List of relationship types to extract
            max_concurrent: Max concurrent extraction requests
            timeout: Request timeout in seconds
        """
        self.ollama_url = ollama_base_url
        self.model = model
        self.entity_types = entity_types or CLINICAL_ENTITY_TYPES
        self.relationship_types = relationship_types or CLINICAL_RELATIONSHIP_TYPES
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _call_llm(self, prompt: str) -> str:
        """Call Ollama LLM API."""
        # num_ctx=8192 is plenty for entity extraction (each chunk is
        # ~500 tokens + ~1K prompt template + ~2K output = ~4K). The
        # default loaded context (n_ctx_train, e.g. 131072 for
        # llama3.1:8b) combined with OLLAMA_NUM_PARALLEL=16 produces
        # 16 * 131K ≈ 2M-token KV cache that exceeds H100 VRAM and
        # forces host-RAM swap, causing 2-minute timeouts. Explicit
        # 8192 keeps total KV cache under ~2 GB for 16 parallel slots.
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent extraction
                "num_predict": 2048,
                "num_ctx": 8192,
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        logger.error(f"LLM API error: {response.status}")
                        return ""
                    result = await response.json()
                    return result.get("response", "")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

    def _parse_extraction_response(self, response: str) -> Tuple[List[Dict], List[Dict]]:
        """Parse LLM response into entities and relationships."""
        # Try to extract JSON from response
        try:
            # Find JSON block in response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                entities = data.get("entities", [])
                relationships = data.get("relationships", [])
                return entities, relationships
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")

        return [], []

    async def extract_from_chunk(
        self,
        chunk_text: str,
        chunk_id: str
    ) -> ExtractionResult:
        """
        Extract entities and relationships from a single chunk.

        Args:
            chunk_text: Text content of the chunk
            chunk_id: Unique identifier for the chunk

        Returns:
            ExtractionResult with extracted entities and relationships
        """
        import time
        start_time = time.time()

        async with self._semaphore:
            prompt = self.ENTITY_EXTRACTION_PROMPT.format(
                entity_types=", ".join(self.entity_types),
                relationship_types=", ".join(self.relationship_types),
                text=chunk_text[:4000]  # Limit text length
            )

            response = await self._call_llm(prompt)

            entities_data, relationships_data = self._parse_extraction_response(response)

            # Convert to Entity objects
            entities = []
            # Defensive accessor: LLM may emit explicit JSON null for any
            # field; dict.get(key, default) returns None (not the default)
            # when the key is present-but-null. _s coerces that to "" and
            # always returns a stripped string.
            def _s(d, key, default=""):
                v = d.get(key, default)
                return (v if v is not None else default).strip() if isinstance(v, str) else (
                    str(v).strip() if v is not None else default
                )

            entity_names = set()
            for e in entities_data:
                if not isinstance(e, dict):
                    continue
                name = _s(e, "name")
                if name and name not in entity_names:
                    entity_names.add(name)
                    entities.append(Entity(
                        id=str(uuid.uuid4()),
                        name=name,
                        type=_s(e, "type", "Concept") or "Concept",
                        description=_s(e, "description"),
                        source_chunk_id=chunk_id,
                        confidence=1.0
                    ))

            # Convert to Relationship objects (only if both entities exist)
            relationships = []
            for r in relationships_data:
                if not isinstance(r, dict):
                    continue
                source = _s(r, "source")
                target = _s(r, "target")
                if source in entity_names and target in entity_names:
                    relationships.append(Relationship(
                        id=str(uuid.uuid4()),
                        source_entity=source,
                        target_entity=target,
                        relationship_type=_s(r, "type", "related_to") or "related_to",
                        description=_s(r, "description"),
                        weight=1.0,
                        source_chunk_id=chunk_id
                    ))

            elapsed = time.time() - start_time

            return ExtractionResult(
                chunk_id=chunk_id,
                entities=entities,
                relationships=relationships,
                extraction_time_seconds=elapsed
            )

    async def _merge_entity_descriptions(
        self,
        entity_name: str,
        entity_type: str,
        descriptions: List[str]
    ) -> str:
        """Merge multiple descriptions for the same entity using LLM."""
        if len(descriptions) <= 1:
            return descriptions[0] if descriptions else ""

        # Deduplicate descriptions
        unique_descriptions = list(set(d for d in descriptions if d))

        if len(unique_descriptions) <= 1:
            return unique_descriptions[0] if unique_descriptions else ""

        prompt = self.ENTITY_MERGE_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            descriptions="\n".join(f"- {d}" for d in unique_descriptions[:5])
        )

        response = await self._call_llm(prompt)
        return response.strip() or unique_descriptions[0]

    def _merge_entities(
        self,
        all_entities: List[Entity]
    ) -> Dict[str, Entity]:
        """
        Merge duplicate entities from multiple chunks.

        Entities with the same name and type are merged,
        with descriptions combined.

        Returns:
            Dict mapping normalized entity name to merged Entity
        """
        merged: Dict[str, Entity] = {}
        descriptions: Dict[str, List[str]] = {}

        for entity in all_entities:
            key = f"{entity.name.lower()}|{entity.type.lower()}"

            if key not in merged:
                merged[key] = Entity(
                    id=str(uuid.uuid4()),
                    name=entity.name,
                    type=entity.type,
                    description=entity.description,
                    confidence=entity.confidence
                )
                descriptions[key] = []

            if entity.description:
                descriptions[key].append(entity.description)

        # Concatenate unique descriptions as a baseline. The LLM-based merger
        # at _merge_entity_descriptions then runs as a post-pass via
        # _llm_merge_descriptions_async (see below) for entities that
        # accumulated more than _LLM_MERGE_DESCRIPTION_THRESHOLD distinct
        # descriptions — those are the ones a "|"-joined string starts to
        # damage. Stash the unique-descriptions list on the entity for the
        # async pass to read; we drop the attribute after merging.
        for key, entity in merged.items():
            unique_descs = list(set(descriptions[key]))
            entity._pending_descriptions = unique_descs  # consumed in async pass
            if len(unique_descs) > 1:
                entity.description = " | ".join(unique_descs[:3])
            elif unique_descs:
                entity.description = unique_descs[0]

        return {e.name: e for e in merged.values()}

    # Threshold above which we trigger the LLM-based description merger.
    # Below this the simple "|"-join is good enough and skipping the LLM call
    # keeps ingestion cheap.
    _LLM_MERGE_DESCRIPTION_THRESHOLD = 4

    async def _llm_merge_descriptions_async(
        self,
        merged_entities: Dict[str, Entity]
    ) -> None:
        """Run the LLM-backed description merger on entities that accumulated
        many distinct descriptions. Mutates entities in place. Drops the
        transient _pending_descriptions attribute on every entity afterwards.

        Cheap by default: only entities with >= _LLM_MERGE_DESCRIPTION_THRESHOLD
        distinct descriptions are sent to the LLM. Calls run concurrently
        under self._semaphore (already limits Ollama concurrency).
        """
        targets: List[Entity] = []
        for e in merged_entities.values():
            descs = getattr(e, '_pending_descriptions', None) or []
            if len(descs) >= self._LLM_MERGE_DESCRIPTION_THRESHOLD:
                targets.append(e)

        if targets:
            logger.info(
                "LLM-merging descriptions for %d entities with >= %d unique descriptions",
                len(targets), self._LLM_MERGE_DESCRIPTION_THRESHOLD
            )

            async def _merge_one(ent: Entity) -> None:
                try:
                    merged_desc = await self._merge_entity_descriptions(
                        entity_name=ent.name,
                        entity_type=ent.type,
                        descriptions=ent._pending_descriptions,
                    )
                    if merged_desc:
                        ent.description = merged_desc
                except Exception as exc:
                    # Don't fail the whole pipeline on a single merge error;
                    # the "|"-joined description is already in place.
                    logger.warning(
                        "LLM description merge failed for %r: %s",
                        ent.name, exc
                    )

            await asyncio.gather(*[_merge_one(t) for t in targets])

        # Clean up the transient attribute on all entities.
        for e in merged_entities.values():
            if hasattr(e, '_pending_descriptions'):
                try:
                    delattr(e, '_pending_descriptions')
                except AttributeError:
                    pass

    def _merge_relationships(
        self,
        all_relationships: List[Relationship],
        valid_entities: Set[str]
    ) -> List[Relationship]:
        """
        Merge duplicate relationships and filter to valid entities.

        Returns:
            List of unique relationships between valid entities
        """
        seen = set()
        merged = []

        for rel in all_relationships:
            # Only include if both entities are valid
            if rel.source_entity not in valid_entities or rel.target_entity not in valid_entities:
                continue

            # Create unique key for deduplication
            key = (rel.source_entity.lower(), rel.target_entity.lower(), rel.relationship_type.lower())

            if key not in seen:
                seen.add(key)
                merged.append(Relationship(
                    id=str(uuid.uuid4()),
                    source_entity=rel.source_entity,
                    target_entity=rel.target_entity,
                    relationship_type=rel.relationship_type,
                    description=rel.description,
                    weight=1.0
                ))
            else:
                # Increment weight for repeated relationships
                for m in merged:
                    if (m.source_entity.lower(), m.target_entity.lower(), m.relationship_type.lower()) == key:
                        m.weight += 1.0
                        break

        return merged

    async def extract_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None
    ) -> GraphExtractionResult:
        """
        Extract entities and relationships from multiple chunks.

        Args:
            chunks: List of chunk dicts with 'id' and 'content'
            progress_callback: Optional callback for progress updates

        Returns:
            GraphExtractionResult with merged entities and relationships
        """
        import time
        start_time = time.time()

        all_entities: List[Entity] = []
        all_relationships: List[Relationship] = []

        # Process chunks concurrently
        tasks = []
        for chunk in chunks:
            chunk_id = chunk.get('id', str(uuid.uuid4()))
            content = chunk.get('content', '')
            if content:
                tasks.append(self.extract_from_chunk(content, chunk_id))

        # Execute with progress tracking
        completed = 0
        total = len(tasks)

        for coro in asyncio.as_completed(tasks):
            # Per-chunk safety net: a single malformed chunk (LLM JSON
            # quirk, transient network blip, etc.) should never abort
            # the whole pipeline mid-run and lose all entities. If a
            # chunk raises, log and treat it as having extracted nothing.
            try:
                result = await coro
                all_entities.extend(result.entities)
                all_relationships.extend(result.relationships)
            except Exception as chunk_error:
                logger.error(
                    f"Chunk extraction failed (skipping): "
                    f"{type(chunk_error).__name__}: {chunk_error}"
                )

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        # Merge duplicates (sync concat pass + async LLM-merge for the heavy hitters)
        merged_entities = self._merge_entities(all_entities)
        await self._llm_merge_descriptions_async(merged_entities)
        valid_entity_names = set(merged_entities.keys())
        merged_relationships = self._merge_relationships(all_relationships, valid_entity_names)

        elapsed = time.time() - start_time

        logger.info(
            f"Extracted {len(merged_entities)} entities and {len(merged_relationships)} "
            f"relationships from {len(chunks)} chunks in {elapsed:.1f}s"
        )

        return GraphExtractionResult(
            entities=merged_entities,
            relationships=merged_relationships,
            entity_count=len(merged_entities),
            relationship_count=len(merged_relationships),
            chunk_count=len(chunks),
            total_time_seconds=elapsed
        )


async def store_entities_in_neo4j(
    neo4j_client,
    extraction_result: GraphExtractionResult,
    batch_size: int = 100
) -> int:
    """
    Store extracted entities and relationships in Neo4j.

    Creates:
    - Entity nodes with embeddings
    - RELATED_TO relationships between entities
    - Links from entities to source chunks

    Args:
        neo4j_client: Neo4j client instance
        extraction_result: Extraction results to store
        batch_size: Number of entities per batch

    Returns:
        Number of entities stored
    """
    import json as _json
    import os as _os

    stored = 0

    # Checkpoint Phase 1 results to disk BEFORE attempting Neo4j storage.
    # Without this, a Neo4j storage failure throws away 18+ hours of LLM
    # extraction work (happened once on 2026-05-04). Saved to a stable
    # path so a separate restore script can reload from disk.
    try:
        checkpoint_path = "/home/exx/PycharmProjects/vaucda/logs/graphrag_phase1_checkpoint.json"
        with open(checkpoint_path, "w") as cf:
            _json.dump({
                "entities": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "type": e.type,
                        "description": e.description,
                        "confidence": e.confidence,
                    }
                    for e in extraction_result.entities.values()
                ],
                "relationships": [
                    {
                        "source": r.source_entity,
                        "target": r.target_entity,
                        "type": r.relationship_type,
                        "description": r.description,
                        "weight": r.weight,
                    }
                    for r in extraction_result.relationships
                ],
            }, cf)
        size_mb = _os.path.getsize(checkpoint_path) / (1024 * 1024)
        logger.info(
            f"Phase 1 checkpoint written: {checkpoint_path} ({size_mb:.1f} MB, "
            f"{len(extraction_result.entities)} entities, "
            f"{len(extraction_result.relationships)} relationships)"
        )
    except Exception as ckpt_error:
        logger.error(f"Phase 1 checkpoint failed (continuing): {ckpt_error}")

    # Ensure the index that the relationship MERGE will rely on actually
    # exists. Without this, the relationship UNWIND below does a full
    # label scan of every Entity for each MATCH (e.g. 32B node visits at
    # ~140k entities × 230k MATCHes), which can take days. With the
    # constraint, each MATCH is an O(log n) index lookup.
    try:
        await neo4j_client.execute_query(
            "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        )
        logger.info("Ensured unique constraint on Entity.name")
    except Exception as idx_error:
        logger.warning(f"Could not create Entity.name constraint: {idx_error}")

    # Store entities in batches
    entities = list(extraction_result.entities.values())

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]

        entity_query = """
        UNWIND $entities AS e
        MERGE (entity:Entity {name: e.name})
        SET entity.id = e.id,
            entity.type = e.type,
            entity.description = e.description,
            entity.confidence = e.confidence,
            entity.created_at = datetime()
        """

        await neo4j_client.execute_query(entity_query, {
            'entities': [
                {
                    'id': e.id,
                    'name': e.name,
                    'type': e.type,
                    'description': e.description,
                    'confidence': e.confidence
                }
                for e in batch
            ]
        })

        stored += len(batch)

    # Store relationships in batches. The previous single-query UNWIND
    # over all 114k+ relationships in one transaction held a global lock
    # for hours and produced no streaming progress. Smaller batches let
    # transactions commit incrementally and surface progress to logs.
    rel_query = """
    UNWIND $relationships AS r
    MATCH (source:Entity {name: r.source})
    MATCH (target:Entity {name: r.target})
    MERGE (source)-[rel:RELATED_TO {type: r.type}]->(target)
    SET rel.description = r.description,
        rel.weight = r.weight,
        rel.created_at = datetime()
    """

    rel_batch_size = 1000
    rel_payload = [
        {
            'source': r.source_entity,
            'target': r.target_entity,
            'type': r.relationship_type,
            'description': r.description,
            'weight': r.weight,
        }
        for r in extraction_result.relationships
    ]

    rels_total = len(rel_payload)
    rels_stored = 0
    for i in range(0, rels_total, rel_batch_size):
        batch = rel_payload[i:i + rel_batch_size]
        await neo4j_client.execute_query(rel_query, {'relationships': batch})
        rels_stored += len(batch)
        if rels_stored % 10000 == 0 or rels_stored == rels_total:
            logger.info(
                f"Stored relationships: {rels_stored} / {rels_total}"
            )

    logger.info(f"Stored {stored} entities and {rels_total} relationships")

    return stored


async def compute_entity_embeddings(
    neo4j_client,
    embedding_model,
    batch_size: int = 50
) -> int:
    """
    Compute embeddings for entities that don't have them.

    Args:
        neo4j_client: Neo4j client instance
        embedding_model: Embedding model with encode() method
        batch_size: Batch size for processing

    Returns:
        Number of entities updated
    """
    # Get entities without embeddings
    query = """
    MATCH (e:Entity)
    WHERE e.embedding IS NULL
    RETURN e.name AS name, e.description AS description, e.type AS type
    """

    entities = await neo4j_client.execute_query(query)

    if not entities:
        return 0

    updated = 0

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]

        # Generate embeddings
        texts = [
            f"{e['type']}: {e['name']}. {e['description'] or ''}"
            for e in batch
        ]

        embeddings = embedding_model.encode(texts)

        # Update in Neo4j
        for entity, embedding in zip(batch, embeddings):
            update_query = """
            MATCH (e:Entity {name: $name})
            SET e.embedding = $embedding
            """
            await neo4j_client.execute_query(update_query, {
                'name': entity['name'],
                'embedding': embedding.tolist()
            })
            updated += 1

    logger.info(f"Computed embeddings for {updated} entities")
    return updated
