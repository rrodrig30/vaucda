"""
RAG Pipeline for VAUCDA
Retrieval-Augmented Generation for medical knowledge base

Includes full Microsoft GraphRAG implementation:
- Entity extraction from text chunks
- Leiden community detection
- Hierarchical summarization
- Map-reduce global search
- Entity-focused local search
"""

from rag.embeddings import EmbeddingGenerator
from rag.chunking import MedicalDocumentChunker, DocumentChunk
from rag.retriever import RAGRetriever
from rag.rag_pipeline import RAGPipeline, RAGContext

# GraphRAG components
from rag.graphrag_pipeline import GraphRAGPipeline, MapReduceResult, LocalSearchResult
from rag.graphrag_retriever import GraphRAGRetriever, SearchMode, GraphRAGContext
from rag.entity_extractor import EntityExtractor, Entity, Relationship
from rag.community_detection import CommunityDetector, Community
from rag.hierarchical_summarizer import HierarchicalSummarizer, HierarchicalSummary

__all__ = [
    # Standard RAG
    "EmbeddingGenerator",
    "MedicalDocumentChunker",
    "DocumentChunk",
    "RAGRetriever",
    "RAGPipeline",
    "RAGContext",
    # GraphRAG
    "GraphRAGPipeline",
    "GraphRAGRetriever",
    "SearchMode",
    "GraphRAGContext",
    "MapReduceResult",
    "LocalSearchResult",
    "EntityExtractor",
    "Entity",
    "Relationship",
    "CommunityDetector",
    "Community",
    "HierarchicalSummarizer",
    "HierarchicalSummary",
]
