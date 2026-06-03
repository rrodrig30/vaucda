"""
Community Detection for GraphRAG

Uses the Leiden algorithm to detect communities in the document-concept graph.
Communities enable hierarchical retrieval: global search across communities,
then local search within relevant communities.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

try:
    import igraph as ig
    import leidenalg
    LEIDEN_AVAILABLE = True
except ImportError:
    LEIDEN_AVAILABLE = False
    logging.warning("leidenalg not available. Install with: pip install igraph leidenalg")

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False


@dataclass
class Community:
    """Represents a detected community of related documents/concepts."""
    id: str
    name: str
    description: str
    size: int
    tier: int  # 0=global, 1=major, 2=minor
    document_ids: List[str]
    concept_names: List[str]
    key_terms: List[str]
    embedding: Optional[List[float]] = None
    modularity_contribution: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CommunityDetectionResult:
    """Result of community detection algorithm."""
    communities: List[Community]
    total_modularity: float
    num_documents: int
    num_concepts: int
    algorithm: str
    resolution: float
    detection_time_seconds: float


class CommunityDetector:
    """
    Detects communities in a document-concept graph using the Leiden algorithm.

    The Leiden algorithm improves upon Louvain by guaranteeing well-connected
    communities and faster convergence.
    """

    def __init__(
        self,
        resolution: float = 1.0,
        min_community_size: int = 3,
        random_state: int = 42
    ):
        """
        Initialize the community detector.

        Args:
            resolution: Leiden resolution parameter (higher = more communities)
            min_community_size: Minimum number of nodes for a valid community
            random_state: Random seed for reproducibility
        """
        self.resolution = resolution
        self.min_community_size = min_community_size
        self.random_state = random_state

        if not LEIDEN_AVAILABLE:
            raise ImportError(
                "Leiden algorithm requires igraph and leidenalg packages. "
                "Install with: pip install igraph leidenalg"
            )

    def build_graph_from_neo4j_data(
        self,
        documents: List[Dict[str, Any]],
        concepts: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> ig.Graph:
        """
        Build an igraph Graph from Neo4j export data.

        Args:
            documents: List of document nodes with 'id', 'title', 'embedding'
            concepts: List of concept nodes with 'id', 'name', 'embedding'
            relationships: List of relationships with 'source', 'target', 'type', 'weight'

        Returns:
            igraph.Graph object ready for community detection
        """
        # Create node mapping
        node_map = {}
        node_data = []

        # Add documents
        for doc in documents:
            node_id = len(node_data)
            node_map[doc['id']] = node_id
            node_data.append({
                'name': doc['id'],
                'type': 'document',
                'label': doc.get('title', doc['id']),
                'embedding': doc.get('embedding')
            })

        # Add concepts
        for concept in concepts:
            node_id = len(node_data)
            node_map[concept['id']] = node_id
            node_data.append({
                'name': concept['id'],
                'type': 'concept',
                'label': concept.get('name', concept['id']),
                'embedding': concept.get('embedding')
            })

        # Build edges
        edges = []
        edge_weights = []

        for rel in relationships:
            source_id = rel.get('source') or rel.get('source_id')
            target_id = rel.get('target') or rel.get('target_id')

            if source_id in node_map and target_id in node_map:
                edges.append((node_map[source_id], node_map[target_id]))
                edge_weights.append(rel.get('weight', 1.0))

        # Create graph
        g = ig.Graph(n=len(node_data), edges=edges, directed=False)

        # Add node attributes
        for attr in ['name', 'type', 'label']:
            g.vs[attr] = [n[attr] for n in node_data]

        # Add edge weights
        if edge_weights:
            g.es['weight'] = edge_weights

        return g

    def detect_communities(
        self,
        graph: ig.Graph,
        use_weights: bool = True
    ) -> Tuple[List[List[int]], float]:
        """
        Run Leiden algorithm to detect communities.

        Args:
            graph: igraph.Graph object
            use_weights: Whether to use edge weights in community detection

        Returns:
            Tuple of (community_membership_lists, modularity_score)
        """
        # Run Leiden algorithm
        partition = leidenalg.find_partition(
            graph,
            leidenalg.RBConfigurationVertexPartition,
            weights='weight' if use_weights and 'weight' in graph.es.attributes() else None,
            resolution_parameter=self.resolution,
            seed=self.random_state
        )

        # Get communities as lists of node indices
        communities = list(partition)

        # Filter by minimum size
        communities = [c for c in communities if len(c) >= self.min_community_size]

        # Calculate modularity
        modularity = partition.modularity

        return communities, modularity

    def extract_community_info(
        self,
        graph: ig.Graph,
        community_nodes: List[int]
    ) -> Dict[str, Any]:
        """
        Extract information about a community for naming and description.

        Args:
            graph: The full graph
            community_nodes: List of node indices in this community

        Returns:
            Dict with document_ids, concept_names, key_terms
        """
        document_ids = []
        concept_names = []

        for node_idx in community_nodes:
            node_type = graph.vs[node_idx]['type']
            node_name = graph.vs[node_idx]['name']
            node_label = graph.vs[node_idx]['label']

            if node_type == 'document':
                document_ids.append(node_name)
            elif node_type == 'concept':
                concept_names.append(node_label)

        # Extract key terms from concept names (most frequent words)
        term_freq = {}
        for name in concept_names:
            for word in name.lower().split():
                if len(word) > 3:  # Skip short words
                    term_freq[word] = term_freq.get(word, 0) + 1

        key_terms = sorted(term_freq.keys(), key=lambda k: term_freq[k], reverse=True)[:10]

        return {
            'document_ids': document_ids,
            'concept_names': concept_names,
            'key_terms': key_terms
        }

    def compute_community_embedding(
        self,
        graph: ig.Graph,
        community_nodes: List[int]
    ) -> Optional[List[float]]:
        """
        Compute aggregate embedding for a community by averaging member embeddings.

        Args:
            graph: The full graph
            community_nodes: List of node indices in this community

        Returns:
            Average embedding vector or None if no embeddings available
        """
        embeddings = []

        for node_idx in community_nodes:
            embedding = graph.vs[node_idx].get('embedding')
            if embedding is not None:
                embeddings.append(np.array(embedding))

        if not embeddings:
            return None

        # Compute centroid
        centroid = np.mean(embeddings, axis=0)

        # Normalize
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm

        return centroid.tolist()

    def generate_community_name(
        self,
        key_terms: List[str],
        concept_names: List[str]
    ) -> str:
        """Generate a descriptive name for a community."""
        if key_terms:
            # Use top 2-3 key terms
            name_terms = key_terms[:3]
            return " / ".join(t.title() for t in name_terms)
        elif concept_names:
            # Use first concept name
            return concept_names[0]
        else:
            return "Unnamed Community"

    def assign_community_tier(
        self,
        size: int,
        total_nodes: int,
        num_communities: int
    ) -> int:
        """
        Assign a tier level to a community based on its relative size.

        Tier 0: Major communities (top 20% by size)
        Tier 1: Medium communities (next 30%)
        Tier 2: Minor communities (remaining 50%)
        """
        if num_communities <= 3:
            # Small number of communities - all are major
            return 0

        size_ratio = size / total_nodes

        if size_ratio > 0.15:
            return 0  # Major
        elif size_ratio > 0.05:
            return 1  # Medium
        else:
            return 2  # Minor

    def detect(
        self,
        documents: List[Dict[str, Any]],
        concepts: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]]
    ) -> CommunityDetectionResult:
        """
        Main entry point: detect communities from Neo4j data.

        Args:
            documents: Document nodes from Neo4j
            concepts: ClinicalConcept nodes from Neo4j
            relationships: Edges between nodes

        Returns:
            CommunityDetectionResult with all detected communities
        """
        import time
        start_time = time.time()

        # Build graph
        graph = self.build_graph_from_neo4j_data(documents, concepts, relationships)

        if graph.vcount() == 0:
            return CommunityDetectionResult(
                communities=[],
                total_modularity=0.0,
                num_documents=0,
                num_concepts=0,
                algorithm="leiden",
                resolution=self.resolution,
                detection_time_seconds=0.0
            )

        # Detect communities
        community_lists, modularity = self.detect_communities(graph)

        # Build Community objects
        communities = []
        total_nodes = graph.vcount()

        for idx, node_list in enumerate(community_lists):
            info = self.extract_community_info(graph, node_list)
            embedding = self.compute_community_embedding(graph, node_list)

            name = self.generate_community_name(
                info['key_terms'],
                info['concept_names']
            )

            tier = self.assign_community_tier(
                len(node_list),
                total_nodes,
                len(community_lists)
            )

            community = Community(
                id=str(uuid.uuid4()),
                name=name,
                description=f"Community of {len(info['document_ids'])} documents and {len(info['concept_names'])} concepts",
                size=len(node_list),
                tier=tier,
                document_ids=info['document_ids'],
                concept_names=info['concept_names'],
                key_terms=info['key_terms'],
                embedding=embedding
            )

            communities.append(community)

        # Sort by size (largest first)
        communities.sort(key=lambda c: c.size, reverse=True)

        elapsed = time.time() - start_time

        return CommunityDetectionResult(
            communities=communities,
            total_modularity=modularity,
            num_documents=len(documents),
            num_concepts=len(concepts),
            algorithm="leiden",
            resolution=self.resolution,
            detection_time_seconds=elapsed
        )


async def detect_communities_from_neo4j(
    neo4j_client,
    resolution: float = 1.0,
    min_community_size: int = 3
) -> CommunityDetectionResult:
    """
    Detect communities by querying Neo4j for documents, concepts, and relationships.

    Args:
        neo4j_client: Neo4j client instance with query methods
        resolution: Leiden resolution parameter
        min_community_size: Minimum community size

    Returns:
        CommunityDetectionResult
    """
    # Query documents
    documents_query = """
    MATCH (d:Document)
    RETURN d.id AS id, d.title AS title, d.embedding AS embedding
    """
    documents = await neo4j_client.execute_query(documents_query)

    # Query concepts
    concepts_query = """
    MATCH (c:ClinicalConcept)
    RETURN c.id AS id, c.name AS name, c.embedding AS embedding
    """
    concepts = await neo4j_client.execute_query(concepts_query)

    # Query relationships (document-concept and concept-concept)
    relationships_query = """
    MATCH (d:Document)-[r:REFERENCES]->(c:ClinicalConcept)
    RETURN d.id AS source, c.id AS target, type(r) AS type, r.weight AS weight
    UNION
    MATCH (c1:ClinicalConcept)-[r:RELATED_TO]->(c2:ClinicalConcept)
    RETURN c1.id AS source, c2.id AS target, type(r) AS type, r.weight AS weight
    """
    relationships = await neo4j_client.execute_query(relationships_query)

    # Run detection
    detector = CommunityDetector(
        resolution=resolution,
        min_community_size=min_community_size
    )

    return detector.detect(
        documents=[dict(r) for r in documents],
        concepts=[dict(r) for r in concepts],
        relationships=[dict(r) for r in relationships]
    )


async def store_communities_in_neo4j(
    neo4j_client,
    result: CommunityDetectionResult
) -> int:
    """
    Store detected communities in Neo4j.

    SCHEMA NOTE — community storage is owned by GraphRAGPipeline.store_communities
    (rag/graphrag_pipeline.py:445). That function is the canonical writer used by
    the production indexing path. This function is kept for the legacy
    Document/ClinicalConcept graph (detect_communities_from_neo4j above) but is
    aligned to the SAME node properties (c.id, c.name, c.tier, c.size, c.summary,
    c.key_terms, c.embedding) and edge semantics so the retriever can read either
    writer's output uniformly:

      - Entity nodes link via   (Entity)-[:BELONGS_TO_COMMUNITY]->(Community)
        (written by GraphRAGPipeline)
      - Document nodes link via (Document)-[:IN_COMMUNITY]->(Community)
        (written here, matching graphrag_pipeline.py:484-490)

    The schema mismatch flagged by audit (this function previously wrote
    (Document)-[:BELONGS_TO_COMMUNITY] which collided with Entity links of the
    same edge name) has been resolved by switching to IN_COMMUNITY for documents.

    Args:
        neo4j_client: Neo4j client instance
        result: Community detection result

    Returns:
        Number of communities stored
    """
    stored = 0

    for community in result.communities:
        # Create / update community node (canonical key = c.id).
        create_query = """
        MERGE (c:Community {id: $id})
        SET c.name = $name,
            c.description = $description,
            c.size = $size,
            c.tier = $tier,
            c.key_terms = $key_terms,
            c.embedding = $embedding,
            c.created_at = datetime(),
            c.modularity_contribution = $modularity
        WITH c
        UNWIND $document_ids AS doc_id
        MATCH (d:Document {id: doc_id})
        MERGE (d)-[:IN_COMMUNITY]->(c)
        """

        await neo4j_client.execute_query(
            create_query,
            {
                'id': community.id,
                'name': community.name,
                'description': community.description,
                'size': community.size,
                'tier': community.tier,
                'key_terms': community.key_terms,
                'embedding': community.embedding,
                'modularity': community.modularity_contribution,
                'document_ids': community.document_ids
            }
        )

        # If concept names map to Entity nodes (Entity-rooted graph), also link
        # them via BELONGS_TO_COMMUNITY so the retriever's Entity-side queries
        # work uniformly. Best-effort: only links Entities that already exist.
        if community.concept_names:
            entity_link_query = """
            MATCH (c:Community {id: $id})
            UNWIND $entity_names AS en
            MATCH (e:Entity {name: en})
            MERGE (e)-[:BELONGS_TO_COMMUNITY]->(c)
            """
            await neo4j_client.execute_query(
                entity_link_query,
                {'id': community.id, 'entity_names': community.concept_names}
            )

        stored += 1

    return stored
