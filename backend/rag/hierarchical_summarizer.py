"""
Hierarchical Summarizer for GraphRAG

Creates multi-level summaries:
- Chunk level: Key phrases and main points
- Document level: Abstract summary of the document
- Community level: Thematic summary of related documents

Summaries enable global search (community level) before drilling down to local search (chunk level).
"""

import uuid
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SummaryLevel(Enum):
    """Levels in the summary hierarchy."""
    CHUNK = 0
    DOCUMENT = 1
    COMMUNITY = 2
    GLOBAL = 3


@dataclass
class HierarchicalSummary:
    """A summary at any level of the hierarchy."""
    id: str
    entity_id: str  # ID of the chunk/document/community being summarized
    entity_type: str  # 'chunk', 'document', 'community'
    level: int  # 0=chunk, 1=document, 2=community, 3=global
    content: str
    key_phrases: List[str]
    token_count: int
    model_used: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class HierarchicalSummarizer:
    """
    Creates hierarchical summaries using LLM at multiple levels.

    The hierarchy allows GraphRAG to:
    1. Search community summaries for global context
    2. Drill down into relevant document summaries
    3. Retrieve specific chunks for detailed information
    """

    def __init__(
        self,
        model: Optional[str] = None,
        chunk_summary_max_tokens: int = 100,
        document_summary_max_tokens: int = 200,
        community_summary_max_tokens: int = 300
    ):
        """
        Initialize the summarizer.

        Args:
            model: LLM model to use (defaults to settings.OLLAMA_DEFAULT_MODEL)
            chunk_summary_max_tokens: Max tokens for chunk summaries
            document_summary_max_tokens: Max tokens for document summaries
            community_summary_max_tokens: Max tokens for community summaries
        """
        self.model = model
        self.chunk_max_tokens = chunk_summary_max_tokens
        self.document_max_tokens = document_summary_max_tokens
        self.community_max_tokens = community_summary_max_tokens

    def _call_llm(
        self,
        prompt: str,
        max_tokens: int,
        system_prompt: Optional[str] = None
    ) -> str:
        """Call LLM for summarization."""
        try:
            from app.services.note_processing.llm_helper import synthesize_with_llm
            return synthesize_with_llm(
                prompt=prompt,
                model=self.model,
                temperature=0.0,  # Deterministic for consistent summaries
                system_prompt=system_prompt,
                max_tokens=max_tokens
            )
        except ImportError:
            logger.warning("LLM helper not available, returning empty summary")
            return ""

    def summarize_chunk(
        self,
        chunk_text: str,
        chunk_id: str,
        document_title: Optional[str] = None
    ) -> HierarchicalSummary:
        """
        Create a summary of a single chunk.

        For chunks, we extract key phrases and create a one-sentence summary.

        Args:
            chunk_text: The text content of the chunk
            chunk_id: Unique identifier for the chunk
            document_title: Optional title of parent document for context

        Returns:
            HierarchicalSummary for the chunk
        """
        context = f" from document '{document_title}'" if document_title else ""

        prompt = f"""Summarize this clinical text{context} in 1-2 sentences.
Extract 3-5 key clinical phrases.

TEXT:
{chunk_text[:2000]}

OUTPUT FORMAT:
SUMMARY: [1-2 sentence summary]
KEY PHRASES: [phrase1], [phrase2], [phrase3]"""

        system_prompt = "You are a clinical documentation specialist. Be precise and factual."

        response = self._call_llm(prompt, self.chunk_max_tokens, system_prompt)

        # Parse response
        summary = ""
        key_phrases = []

        for line in response.split('\n'):
            if line.startswith('SUMMARY:'):
                summary = line.replace('SUMMARY:', '').strip()
            elif line.startswith('KEY PHRASES:'):
                phrases_str = line.replace('KEY PHRASES:', '').strip()
                key_phrases = [p.strip() for p in phrases_str.split(',') if p.strip()]

        return HierarchicalSummary(
            id=str(uuid.uuid4()),
            entity_id=chunk_id,
            entity_type='chunk',
            level=SummaryLevel.CHUNK.value,
            content=summary or response[:200],
            key_phrases=key_phrases,
            token_count=len(response.split()),
            model_used=self.model or 'default'
        )

    def summarize_document(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str,
        document_title: str,
        document_type: Optional[str] = None
    ) -> HierarchicalSummary:
        """
        Create a summary of a document from its chunks.

        Document summaries provide mid-level context for retrieval.

        Args:
            chunks: List of chunk dicts with 'content' and optionally 'summary'
            document_id: Unique identifier for the document
            document_title: Title of the document
            document_type: Type of document (guideline, paper, etc.)

        Returns:
            HierarchicalSummary for the document
        """
        # Build context from chunks (prefer summaries if available)
        chunk_texts = []
        for chunk in chunks[:10]:  # Limit to first 10 chunks
            if chunk.get('summary'):
                chunk_texts.append(chunk['summary'])
            elif chunk.get('content'):
                chunk_texts.append(chunk['content'][:500])

        combined_text = '\n---\n'.join(chunk_texts)

        doc_type_str = f" ({document_type})" if document_type else ""

        prompt = f"""Summarize this clinical document in 2-3 sentences.
Include: main topic, key findings/recommendations, and clinical relevance.

DOCUMENT: {document_title}{doc_type_str}

CONTENT EXCERPTS:
{combined_text[:3000]}

OUTPUT FORMAT:
SUMMARY: [2-3 sentence summary]
MAIN TOPICS: [topic1], [topic2], [topic3]
CLINICAL RELEVANCE: [brief relevance statement]"""

        system_prompt = "You are a clinical documentation specialist summarizing medical literature."

        response = self._call_llm(prompt, self.document_max_tokens, system_prompt)

        # Parse response
        summary = ""
        topics = []

        for line in response.split('\n'):
            if line.startswith('SUMMARY:'):
                summary = line.replace('SUMMARY:', '').strip()
            elif line.startswith('MAIN TOPICS:'):
                topics_str = line.replace('MAIN TOPICS:', '').strip()
                topics = [t.strip() for t in topics_str.split(',') if t.strip()]

        return HierarchicalSummary(
            id=str(uuid.uuid4()),
            entity_id=document_id,
            entity_type='document',
            level=SummaryLevel.DOCUMENT.value,
            content=summary or response[:300],
            key_phrases=topics,
            token_count=len(response.split()),
            model_used=self.model or 'default'
        )

    def summarize_community(
        self,
        document_summaries: List[str],
        community_id: str,
        community_name: str,
        key_terms: List[str]
    ) -> HierarchicalSummary:
        """
        Create a thematic summary of a community of related documents.

        Community summaries enable global search across document clusters.

        Args:
            document_summaries: List of document summary texts
            community_id: Unique identifier for the community
            community_name: Name of the community
            key_terms: Key terms associated with the community

        Returns:
            HierarchicalSummary for the community
        """
        summaries_text = '\n'.join(f"- {s}" for s in document_summaries[:20])
        terms_str = ', '.join(key_terms[:10])

        prompt = f"""Synthesize this group of related clinical documents into a thematic summary.
Identify the common themes, key clinical concepts, and practical applications.

COMMUNITY: {community_name}
KEY TERMS: {terms_str}

DOCUMENT SUMMARIES:
{summaries_text}

OUTPUT FORMAT:
THEME: [main thematic focus of this document cluster]
SUMMARY: [3-4 sentence synthesis of the community's content]
KEY CONCEPTS: [concept1], [concept2], [concept3]
CLINICAL APPLICATIONS: [brief statement on clinical use]"""

        system_prompt = "You are synthesizing clinical knowledge across related documents."

        response = self._call_llm(prompt, self.community_max_tokens, system_prompt)

        # Parse response
        summary = ""
        concepts = []
        theme = ""

        for line in response.split('\n'):
            if line.startswith('THEME:'):
                theme = line.replace('THEME:', '').strip()
            elif line.startswith('SUMMARY:'):
                summary = line.replace('SUMMARY:', '').strip()
            elif line.startswith('KEY CONCEPTS:'):
                concepts_str = line.replace('KEY CONCEPTS:', '').strip()
                concepts = [c.strip() for c in concepts_str.split(',') if c.strip()]

        full_summary = f"{theme}. {summary}" if theme else summary

        return HierarchicalSummary(
            id=str(uuid.uuid4()),
            entity_id=community_id,
            entity_type='community',
            level=SummaryLevel.COMMUNITY.value,
            content=full_summary or response[:400],
            key_phrases=concepts,
            token_count=len(response.split()),
            model_used=self.model or 'default'
        )

    def build_hierarchy(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str,
        document_title: str
    ) -> List[HierarchicalSummary]:
        """
        Build full summary hierarchy for a document.

        Creates chunk-level and document-level summaries.

        Args:
            chunks: List of chunk dicts with 'id', 'content'
            document_id: Document ID
            document_title: Document title

        Returns:
            List of all generated summaries
        """
        summaries = []

        # Summarize each chunk
        for chunk in chunks:
            chunk_summary = self.summarize_chunk(
                chunk_text=chunk.get('content', ''),
                chunk_id=chunk.get('id', str(uuid.uuid4())),
                document_title=document_title
            )
            summaries.append(chunk_summary)

        # Create document summary from chunk summaries
        chunks_with_summaries = [
            {'summary': s.content, 'content': c.get('content', '')}
            for s, c in zip(summaries, chunks)
        ]

        doc_summary = self.summarize_document(
            chunks=chunks_with_summaries,
            document_id=document_id,
            document_title=document_title
        )
        summaries.append(doc_summary)

        return summaries


async def generate_summaries_for_community(
    neo4j_client,
    community_id: str,
    model: Optional[str] = None
) -> HierarchicalSummary:
    """
    Generate a summary for a community by aggregating document summaries.

    Args:
        neo4j_client: Neo4j client instance
        community_id: ID of the community to summarize
        model: LLM model to use

    Returns:
        Community summary
    """
    # Get community info and document summaries
    query = """
    MATCH (c:Community {id: $community_id})
    OPTIONAL MATCH (d:Document)-[:BELONGS_TO_COMMUNITY]->(c)
    OPTIONAL MATCH (s:HierarchicalSummary)-[:SUMMARIZES]->(d)
    WHERE s.level = 1
    RETURN c.name AS community_name,
           c.key_terms AS key_terms,
           collect(DISTINCT s.content) AS document_summaries
    """

    result = await neo4j_client.execute_query(query, {'community_id': community_id})

    if not result:
        raise ValueError(f"Community {community_id} not found")

    record = result[0]

    summarizer = HierarchicalSummarizer(model=model)

    return summarizer.summarize_community(
        document_summaries=record.get('document_summaries', []),
        community_id=community_id,
        community_name=record.get('community_name', 'Unknown'),
        key_terms=record.get('key_terms', [])
    )


async def store_summary_in_neo4j(
    neo4j_client,
    summary: HierarchicalSummary
) -> str:
    """
    Store a hierarchical summary in Neo4j.

    Args:
        neo4j_client: Neo4j client instance
        summary: The summary to store

    Returns:
        ID of the stored summary
    """
    query = """
    MERGE (s:HierarchicalSummary {id: $id})
    SET s.entity_id = $entity_id,
        s.entity_type = $entity_type,
        s.level = $level,
        s.content = $content,
        s.key_phrases = $key_phrases,
        s.token_count = $token_count,
        s.model_used = $model_used,
        s.created_at = datetime()
    WITH s
    MATCH (e)
    WHERE (e:Chunk AND e.id = $entity_id)
       OR (e:Document AND e.id = $entity_id)
       OR (e:Community AND e.id = $entity_id)
    MERGE (s)-[:SUMMARIZES]->(e)
    RETURN s.id AS id
    """

    result = await neo4j_client.execute_query(query, {
        'id': summary.id,
        'entity_id': summary.entity_id,
        'entity_type': summary.entity_type,
        'level': summary.level,
        'content': summary.content,
        'key_phrases': summary.key_phrases,
        'token_count': summary.token_count,
        'model_used': summary.model_used
    })

    return summary.id
