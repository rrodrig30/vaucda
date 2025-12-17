"""
Medical Document Chunking Strategies
Implements hierarchical semantic chunking for clinical guidelines,
algorithm-based chunking for calculators, and section-based chunking for literature
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import tiktoken

logger = logging.getLogger(__name__)


class DocumentType(Enum):
    """Types of medical documents."""
    GUIDELINE = "guideline"  # AUA, NCCN, EAU guidelines
    CALCULATOR = "calculator"  # Calculator documentation
    LITERATURE = "literature"  # PubMed articles
    GENERAL = "general"  # Generic medical text


@dataclass
class DocumentChunk:
    """
    Represents a chunk of a medical document.

    Attributes:
        content: The text content of the chunk
        metadata: Metadata including source, section, etc.
        embedding: Optional embedding vector (768-dim)
        chunk_index: Index of chunk in document
        total_chunks: Total number of chunks in document
    """
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    chunk_index: int = 0
    total_chunks: int = 1

    @property
    def token_count(self) -> int:
        """
        Calculate exact token count using tiktoken.

        Raises:
            RuntimeError: If tiktoken is unavailable (required for token counting)
        """
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
            return len(encoding.encode(self.content))
        except Exception as e:
            raise RuntimeError(
                f"Failed to count tokens using tiktoken: {e}. "
                "Tiktoken is required for accurate token counting."
            )


class MedicalDocumentChunker:
    """
    Medical document chunking with document-type-aware strategies.

    Implements optimal chunking for:
    - Clinical guidelines (500-800 tokens, 100 token overlap, hierarchical)
    - Calculator docs (300-500 tokens, 50 token overlap, algorithm-based)
    - Medical literature (400-700 tokens, 50 token overlap, section-based)
    """

    def __init__(self):
        """
        Initialize chunker with tiktoken encoder.

        Raises:
            RuntimeError: If tiktoken cannot be initialized (required dependency)
        """
        try:
            self.encoder = tiktoken.encoding_for_model("gpt-4")
            logger.info("Tiktoken encoder initialized for GPT-4")
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize tiktoken encoder: {e}. "
                "Tiktoken is a required dependency for accurate token counting."
            )

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Exact token count

        Raises:
            RuntimeError: If token counting fails (should not happen after __init__)
        """
        try:
            return len(self.encoder.encode(text))
        except Exception as e:
            raise RuntimeError(f"Token counting failed: {e}")

    def _split_by_tokens(
        self,
        text: str,
        max_tokens: int,
        overlap_tokens: int = 0
    ) -> List[str]:
        """
        Split text into chunks of max_tokens with overlap.

        Uses tiktoken for precise token-based splitting. Ensures chunks
        do not exceed max_tokens while maintaining semantic overlap for context.

        Args:
            text: Text to split
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Tokens to overlap between chunks

        Returns:
            List of text chunks with token counts respected

        Raises:
            RuntimeError: If encoding/decoding fails
        """
        try:
            tokens = self.encoder.encode(text)
            chunks = []
            start = 0

            while start < len(tokens):
                end = start + max_tokens
                chunk_tokens = tokens[start:end]
                chunk_text = self.encoder.decode(chunk_tokens)
                chunks.append(chunk_text)

                # Move start position with overlap
                start = end - overlap_tokens if overlap_tokens > 0 else end

            logger.info(f"Split text into {len(chunks)} chunks (max {max_tokens} tokens each)")
            return chunks
        except Exception as e:
            raise RuntimeError(f"Token-based splitting failed: {e}")

    def chunk_guideline(
        self,
        text: str,
        metadata: Dict[str, Any],
        target_tokens: int = 650,
        overlap_tokens: int = 100
    ) -> List[DocumentChunk]:
        """
        Hierarchical semantic chunking for clinical guidelines.

        Strategy:
        - Preserve section structure
        - Target: 500-800 tokens per chunk
        - 100-token overlap for context preservation
        - Never split recommendations or evidence levels

        Args:
            text: Full guideline text
            metadata: Document metadata (source, category, etc.)
            target_tokens: Target tokens per chunk
            overlap_tokens: Overlap between chunks

        Returns:
            List of DocumentChunk objects
        """
        chunks = []

        # Detect and split by sections
        section_pattern = r'\n#+\s+(.+?)\n|^([A-Z][A-Z\s]+:)\s*\n'
        sections = re.split(section_pattern, text)

        current_section_title = metadata.get("title", "Introduction")
        current_text = ""

        for i, section in enumerate(sections):
            if section is None:
                continue

            # Check if this is a section header
            if re.match(r'^[A-Z][A-Z\s]+:?$', section.strip()):
                # Save previous section
                if current_text.strip():
                    section_chunks = self._chunk_section(
                        current_text,
                        current_section_title,
                        metadata,
                        target_tokens,
                        overlap_tokens
                    )
                    chunks.extend(section_chunks)

                # Start new section
                current_section_title = section.strip()
                current_text = ""
            else:
                current_text += section

        # Process final section
        if current_text.strip():
            section_chunks = self._chunk_section(
                current_text,
                current_section_title,
                metadata,
                target_tokens,
                overlap_tokens
            )
            chunks.extend(section_chunks)

        # Add chunk indices
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx
            chunk.total_chunks = len(chunks)

        logger.info(f"Chunked guideline into {len(chunks)} chunks")
        return chunks

    def _chunk_section(
        self,
        section_text: str,
        section_title: str,
        metadata: Dict[str, Any],
        target_tokens: int,
        overlap_tokens: int
    ) -> List[DocumentChunk]:
        """Chunk a single section preserving semantic structure."""
        chunks = []

        # Check if section fits in one chunk
        token_count = self._count_tokens(section_text)

        if token_count <= target_tokens:
            # Single chunk
            chunk_metadata = {
                **metadata,
                "section": section_title,
                "chunk_type": "complete_section"
            }
            chunks.append(DocumentChunk(
                content=section_text.strip(),
                metadata=chunk_metadata
            ))
        else:
            # Split section
            text_chunks = self._split_by_tokens(
                section_text,
                max_tokens=target_tokens,
                overlap_tokens=overlap_tokens
            )

            for idx, chunk_text in enumerate(text_chunks):
                chunk_metadata = {
                    **metadata,
                    "section": section_title,
                    "chunk_type": "section_part",
                    "part_index": idx
                }
                chunks.append(DocumentChunk(
                    content=chunk_text.strip(),
                    metadata=chunk_metadata
                ))

        return chunks

    def chunk_calculator(
        self,
        text: str,
        metadata: Dict[str, Any],
        target_tokens: int = 400,
        overlap_tokens: int = 50
    ) -> List[DocumentChunk]:
        """
        Algorithm-based chunking for calculator documentation.

        Strategy:
        - Target: 300-500 tokens per chunk
        - 50-token overlap
        - Preserve formulas and algorithms
        - Keep input/output definitions together

        Args:
            text: Calculator documentation
            metadata: Document metadata
            target_tokens: Target tokens per chunk
            overlap_tokens: Overlap between chunks

        Returns:
            List of DocumentChunk objects
        """
        chunks = []

        # Key sections for calculators
        section_markers = [
            r"(?i)^##?\s*inputs?:?\s*$",
            r"(?i)^##?\s*outputs?:?\s*$",
            r"(?i)^##?\s*formula:?\s*$",
            r"(?i)^##?\s*calculation:?\s*$",
            r"(?i)^##?\s*interpretation:?\s*$",
            r"(?i)^##?\s*references?:?\s*$",
        ]

        # Split by calculator sections
        combined_pattern = '|'.join(section_markers)
        parts = re.split(f'({combined_pattern})', text, flags=re.MULTILINE)

        current_section = "Overview"
        current_content = ""

        for part in parts:
            if re.match(combined_pattern, part, re.IGNORECASE | re.MULTILINE):
                # Save previous section
                if current_content.strip():
                    chunk_metadata = {
                        **metadata,
                        "section": current_section,
                        "document_type": "calculator"
                    }
                    chunks.append(DocumentChunk(
                        content=current_content.strip(),
                        metadata=chunk_metadata
                    ))

                # Start new section
                current_section = part.strip()
                current_content = ""
            else:
                current_content += part

        # Final section
        if current_content.strip():
            chunk_metadata = {
                **metadata,
                "section": current_section,
                "document_type": "calculator"
            }
            chunks.append(DocumentChunk(
                content=current_content.strip(),
                metadata=chunk_metadata
            ))

        # Add indices
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx
            chunk.total_chunks = len(chunks)

        logger.info(f"Chunked calculator into {len(chunks)} chunks")
        return chunks

    def chunk_literature(
        self,
        text: str,
        metadata: Dict[str, Any],
        target_tokens: int = 550,
        overlap_tokens: int = 50
    ) -> List[DocumentChunk]:
        """
        Section-based chunking for medical literature.

        Strategy:
        - Target: 400-700 tokens per chunk
        - 50-token overlap
        - Preserve abstract, methods, results, discussion sections
        - Keep tables and figures with their sections

        Args:
            text: Article text
            metadata: Document metadata
            target_tokens: Target tokens per chunk
            overlap_tokens: Overlap between chunks

        Returns:
            List of DocumentChunk objects
        """
        chunks = []

        # Common literature sections
        section_patterns = [
            r"(?i)^##?\s*abstract:?\s*$",
            r"(?i)^##?\s*introduction:?\s*$",
            r"(?i)^##?\s*methods?:?\s*$",
            r"(?i)^##?\s*results?:?\s*$",
            r"(?i)^##?\s*discussion:?\s*$",
            r"(?i)^##?\s*conclusion:?\s*$",
            r"(?i)^##?\s*references?:?\s*$",
        ]

        combined_pattern = '|'.join(section_patterns)
        parts = re.split(f'({combined_pattern})', text, flags=re.MULTILINE)

        current_section = "Title"
        current_content = ""

        for part in parts:
            if re.match(combined_pattern, part, re.IGNORECASE | re.MULTILINE):
                # Process previous section
                if current_content.strip():
                    section_chunks = self._chunk_section(
                        current_content,
                        current_section,
                        {**metadata, "document_type": "literature"},
                        target_tokens,
                        overlap_tokens
                    )
                    chunks.extend(section_chunks)

                # New section
                current_section = part.strip()
                current_content = ""
            else:
                current_content += part

        # Final section
        if current_content.strip():
            section_chunks = self._chunk_section(
                current_content,
                current_section,
                {**metadata, "document_type": "literature"},
                target_tokens,
                overlap_tokens
            )
            chunks.extend(section_chunks)

        # Add indices
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx
            chunk.total_chunks = len(chunks)

        logger.info(f"Chunked literature into {len(chunks)} chunks")
        return chunks

    def chunk_document(
        self,
        text: str,
        doc_type: DocumentType,
        metadata: Dict[str, Any]
    ) -> List[DocumentChunk]:
        """
        Chunk document using appropriate strategy based on type.

        Args:
            text: Document text
            doc_type: Type of document
            metadata: Document metadata

        Returns:
            List of DocumentChunk objects
        """
        if doc_type == DocumentType.GUIDELINE:
            return self.chunk_guideline(text, metadata)
        elif doc_type == DocumentType.CALCULATOR:
            return self.chunk_calculator(text, metadata)
        elif doc_type == DocumentType.LITERATURE:
            return self.chunk_literature(text, metadata)
        else:
            # Default: generic chunking
            return self._chunk_generic(text, metadata)

    def _chunk_generic(
        self,
        text: str,
        metadata: Dict[str, Any],
        target_tokens: int = 500,
        overlap_tokens: int = 50
    ) -> List[DocumentChunk]:
        """Generic chunking for unspecified document types."""
        text_chunks = self._split_by_tokens(
            text,
            max_tokens=target_tokens,
            overlap_tokens=overlap_tokens
        )

        chunks = []
        for idx, chunk_text in enumerate(text_chunks):
            chunk = DocumentChunk(
                content=chunk_text.strip(),
                metadata={**metadata, "document_type": "general"},
                chunk_index=idx,
                total_chunks=len(text_chunks)
            )
            chunks.append(chunk)

        logger.info(f"Chunked generic document into {len(chunks)} chunks")
        return chunks
