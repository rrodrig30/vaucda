"""
Document Processing Service

Handles PDF/TXT extraction with OCR fallback for scanned documents.
Used for clinical document uploads in Stage 1 note generation.

Supports task-specific LLM configuration via LLMTaskConfig.
"""

import io
import logging
from dataclasses import dataclass
from typing import Literal, Optional, TYPE_CHECKING

import PyPDF2
from fastapi import UploadFile

from app.services.ocr.ocr_service import OCRService

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig

logger = logging.getLogger(__name__)


@dataclass
class DocumentResult:
    """Result from document processing."""
    text: str
    extraction_method: Literal["text", "ocr"]
    page_count: int
    file_name: str
    file_size_bytes: int


class DocumentProcessor:
    """
    Document processing service for clinical document uploads.

    Handles PDF/TXT extraction with automatic OCR fallback for
    image-based (scanned) PDFs.

    Supports task-specific LLM configuration via LLMTaskConfig.
    """

    # Minimum characters per page to consider text extraction successful
    MIN_CHARS_PER_PAGE = 50

    def __init__(
        self,
        ocr_service: Optional[OCRService] = None,
        task_config: Optional["LLMTaskConfig"] = None
    ):
        """
        Initialize document processor.

        Args:
            ocr_service: OCR service instance (lazy initialized if not provided)
            task_config: Optional LLMTaskConfig for OCR provider/model settings
        """
        self._ocr_service = ocr_service
        self._task_config = task_config

    @property
    def ocr_service(self) -> OCRService:
        """Lazy initialize OCR service with task_config if provided."""
        if self._ocr_service is None:
            self._ocr_service = OCRService(task_config=self._task_config)
        return self._ocr_service

    async def process_document(self, file: UploadFile) -> DocumentResult:
        """
        Process uploaded document and extract text.

        For PDFs:
        1. Try text extraction with PyPDF2
        2. If minimal/no text found, use OCR via Ollama glm-ocr

        For TXT files:
        - Read directly with encoding detection

        Args:
            file: Uploaded file (PDF or TXT)

        Returns:
            DocumentResult with extracted text and metadata

        Raises:
            ValueError: If file type is not supported
        """
        content = await file.read()
        file_size = len(content)
        file_name = file.filename or "unknown"

        logger.info(f"Processing document: {file_name} ({file_size} bytes)")

        # Determine file type
        lower_name = file_name.lower()

        if lower_name.endswith('.txt'):
            text = self._process_text_file(content)
            return DocumentResult(
                text=text,
                extraction_method="text",
                page_count=1,
                file_name=file_name,
                file_size_bytes=file_size
            )

        elif lower_name.endswith('.pdf'):
            return await self._process_pdf_file(content, file_name, file_size)

        else:
            raise ValueError(
                f"Unsupported file type: {file_name}. "
                "Supported types: .pdf, .txt"
            )

    def _process_text_file(self, content: bytes) -> str:
        """
        Process text file with encoding detection.

        Args:
            content: File content as bytes

        Returns:
            Decoded text content
        """
        # Try UTF-8 first, then fall back to Latin-1
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = content.decode('latin-1')
            except UnicodeDecodeError:
                text = content.decode('utf-8', errors='ignore')

        logger.info(f"Text file processed: {len(text)} characters")
        return text

    async def _process_pdf_file(
        self,
        content: bytes,
        file_name: str,
        file_size: int
    ) -> DocumentResult:
        """
        Process PDF file with OCR fallback.

        Args:
            content: PDF file content as bytes
            file_name: Original file name
            file_size: File size in bytes

        Returns:
            DocumentResult with extracted text and metadata
        """
        # First, try direct text extraction with PyPDF2
        text, page_count = self._extract_text_from_pdf(content)

        # Check if extraction was successful
        if self._is_text_extraction_sufficient(text, page_count):
            logger.info(
                f"PDF text extraction successful: {len(text)} chars from {page_count} pages"
            )
            return DocumentResult(
                text=text,
                extraction_method="text",
                page_count=page_count,
                file_name=file_name,
                file_size_bytes=file_size
            )

        # Text extraction insufficient - likely a scanned document
        logger.info(
            f"PDF appears to be scanned (only {len(text)} chars from {page_count} pages). "
            "Falling back to OCR..."
        )

        # Use OCR
        try:
            ocr_text, ocr_pages = await self.ocr_service.process_pdf_with_ocr(content)

            if ocr_text:
                logger.info(f"OCR successful: {len(ocr_text)} chars from {ocr_pages} pages")
                return DocumentResult(
                    text=ocr_text,
                    extraction_method="ocr",
                    page_count=ocr_pages,
                    file_name=file_name,
                    file_size_bytes=file_size
                )
            else:
                # OCR returned no text
                logger.warning("OCR returned no text from document")
                raise RuntimeError(
                    "OCR could not extract any text from the scanned document. "
                    "Check that the OCR model is available and has sufficient resources."
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"OCR failed for {file_name}: {error_msg}")
            raise RuntimeError(
                f"Failed to process scanned PDF '{file_name}': {error_msg}"
            )

    def _extract_text_from_pdf(self, content: bytes) -> tuple[str, int]:
        """
        Extract text from PDF using PyPDF2.

        Args:
            content: PDF file content as bytes

        Returns:
            Tuple of (extracted_text, page_count)
        """
        text_parts = []
        page_count = 0

        try:
            pdf_file = io.BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            page_count = len(pdf_reader.pages)

            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        except Exception as e:
            logger.error(f"PyPDF2 extraction error: {e}")
            return "", 0

        return "\n\n".join(text_parts), page_count

    def _is_text_extraction_sufficient(self, text: str, page_count: int) -> bool:
        """
        Check if text extraction was sufficient.

        Heuristic: If we extracted less than MIN_CHARS_PER_PAGE per page,
        the PDF is likely scanned/image-based.

        Args:
            text: Extracted text
            page_count: Number of pages

        Returns:
            True if extraction is sufficient, False if OCR should be used
        """
        if not text or page_count == 0:
            return False

        chars_per_page = len(text) / page_count

        # If we have very little text per page, likely a scanned document
        return chars_per_page >= self.MIN_CHARS_PER_PAGE
