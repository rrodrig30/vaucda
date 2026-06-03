"""
OCR Service with multi-provider LLM support.

Converts PDF pages to images and extracts text via vision model.
Used as fallback when PyPDF2 cannot extract text (scanned documents).

Supports configurable LLM providers (Ollama, Anthropic, OpenAI) via LLMTaskConfig.
"""

import base64
import logging
from typing import List, Optional, TYPE_CHECKING
import aiohttp
import fitz  # PyMuPDF

from app.services.llm_config_manager import get_model_context_size

from app.config import settings

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig

logger = logging.getLogger(__name__)


class OCRService:
    """
    OCR service with multi-provider LLM support.

    Handles:
    - PDF to image conversion using PyMuPDF
    - OCR via vision models (Ollama, Anthropic, OpenAI)
    - Multi-page document processing
    """

    def __init__(
        self,
        ollama_base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        dpi: Optional[int] = None,
        task_config: Optional["LLMTaskConfig"] = None
    ):
        """
        Initialize OCR service.

        Args:
            ollama_base_url: Ollama API base URL (defaults to settings)
            model: OCR model name (defaults to settings.OCR_MODEL) - ignored if task_config provided
            timeout: Timeout per page in seconds (defaults to settings.OCR_TIMEOUT)
            dpi: DPI for PDF rendering (defaults to settings.OCR_DPI)
            task_config: Optional LLMTaskConfig for multi-provider routing
        """
        self.task_config = task_config
        self.dpi = dpi or settings.OCR_DPI
        self.max_pages = settings.OCR_MAX_PAGES

        # If task_config is provided, use its settings
        if task_config:
            self.provider = task_config.provider.lower()
            self.model = task_config.model
            self.timeout = timeout or settings.OCR_TIMEOUT
            self.temperature = task_config.temperature
            self.max_tokens = task_config.max_tokens

            # Set provider-specific URLs
            if self.provider == "ollama":
                self.ollama_url = ollama_base_url or settings.OLLAMA_BASE_URL
                if not self.ollama_url:
                    raise ValueError("OLLAMA_BASE_URL must be configured for Ollama OCR")
            else:
                self.ollama_url = None  # Not needed for Anthropic/OpenAI
        else:
            # Legacy behavior: use Ollama
            self.provider = "ollama"
            self.ollama_url = ollama_base_url or settings.OLLAMA_BASE_URL
            self.model = model or settings.OCR_MODEL
            self.timeout = timeout or settings.OCR_TIMEOUT
            self.temperature = 0.1
            self.max_tokens = 8192

            if not self.ollama_url:
                raise ValueError("OLLAMA_BASE_URL must be configured for OCR service")

    def pdf_to_images(self, pdf_bytes: bytes) -> List[bytes]:
        """
        Convert PDF pages to PNG images using PyMuPDF.

        Args:
            pdf_bytes: PDF file content as bytes

        Returns:
            List of PNG image bytes, one per page
        """
        images = []
        doc = None

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = min(len(doc), self.max_pages)

            logger.info(f"Converting {page_count} PDF pages to images at {self.dpi} DPI")

            for page_num in range(page_count):
                page = doc[page_num]
                # Render at specified DPI for good OCR quality
                mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                images.append(pix.tobytes("png"))

            if len(doc) > self.max_pages:
                logger.warning(
                    f"PDF has {len(doc)} pages, only processing first {self.max_pages}"
                )

        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            raise
        finally:
            if doc:
                doc.close()

        return images

    async def extract_text_from_image(self, image_bytes: bytes) -> str:
        """
        Send image to configured LLM provider for text extraction.

        Supports Ollama, Anthropic Claude, and OpenAI GPT-4V.

        Args:
            image_bytes: PNG image content as bytes

        Returns:
            Extracted text from the image
        """
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        ocr_prompt = (
            "You are performing OCR (Optical Character Recognition) on a scanned clinical document page. "
            "Extract EVERY SINGLE WORD of text visible in this image — headers, body text, "
            "tables, lists, numbers, dates, lab values, medication names, and all fine print. "
            "Do NOT summarize. Do NOT skip any text no matter how small. "
            "Do NOT add commentary, explanations, or descriptions of the image. "
            "Preserve the original formatting and layout. "
            "Output ONLY the raw extracted text, exactly as it appears on the page."
        )

        if self.provider == "ollama":
            return await self._ocr_with_ollama(image_b64, ocr_prompt)
        elif self.provider == "anthropic":
            return await self._ocr_with_anthropic(image_b64, ocr_prompt)
        elif self.provider == "openai":
            return await self._ocr_with_openai(image_b64, ocr_prompt)
        else:
            raise RuntimeError(f"Unknown OCR provider: {self.provider}")

    async def _ocr_with_ollama(self, image_b64: str, prompt: str) -> str:
        """Extract text using Ollama vision model."""
        # Ensure enough output tokens for full-page OCR
        # A dense clinical page can have 3000+ words = 4000+ tokens
        num_predict = max(self.max_tokens, 8192)

        # Resolution order (see llm_config_manager docstring):
        #   user-set task_config.num_ctx -> lookup table -> DEFAULT_CONTEXT_SIZE
        if self.task_config is not None and self.task_config.num_ctx is not None:
            num_ctx = self.task_config.num_ctx
            ctx_source = "user"
        else:
            num_ctx = get_model_context_size(self.model)
            ctx_source = "lookup"
        logger.info(f"OCR num_ctx={num_ctx} for model {self.model} (source={ctx_source})")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            "options": {
                "temperature": self.temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
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
                        error_text = await response.text()
                        logger.error(f"Ollama OCR error: {response.status} - {error_text}")
                        raise RuntimeError(f"OCR request failed: {response.status}")

                    result = await response.json()
                    return result.get("response", "")

        except aiohttp.ClientError as e:
            logger.error(f"Ollama connection error: {e}")
            raise RuntimeError(f"Failed to connect to Ollama for OCR: {e}")
        except Exception as e:
            logger.error(f"Ollama OCR extraction failed: {e}")
            raise

    async def _ocr_with_anthropic(self, image_b64: str, prompt: str) -> str:
        """Extract text using Anthropic Claude vision model."""
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not configured for OCR")

        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Claude vision message format
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                }
            },
            {"type": "text", "text": prompt}
        ]

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": content}],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Anthropic OCR error: {response.status} - {error_text}")
                        raise RuntimeError(f"Anthropic OCR request failed: {response.status}")

                    result = await response.json()
                    content_blocks = result.get("content", [])
                    text_parts = [c.get("text", "") for c in content_blocks if c.get("type") == "text"]
                    return "".join(text_parts)

        except aiohttp.ClientError as e:
            logger.error(f"Anthropic connection error: {e}")
            raise RuntimeError(f"Failed to connect to Anthropic for OCR: {e}")
        except Exception as e:
            logger.error(f"Anthropic OCR extraction failed: {e}")
            raise

    async def _ocr_with_openai(self, image_b64: str, prompt: str) -> str:
        """Extract text using OpenAI GPT-4V model."""
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not configured for OCR")

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        # GPT-4V vision message format
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
            },
            {"type": "text", "text": prompt}
        ]

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": content}],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI OCR error: {response.status} - {error_text}")
                        raise RuntimeError(f"OpenAI OCR request failed: {response.status}")

                    result = await response.json()
                    choices = result.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                    return ""

        except aiohttp.ClientError as e:
            logger.error(f"OpenAI connection error: {e}")
            raise RuntimeError(f"Failed to connect to OpenAI for OCR: {e}")
        except Exception as e:
            logger.error(f"OpenAI OCR extraction failed: {e}")
            raise

    async def process_pdf_with_ocr(self, pdf_bytes: bytes) -> tuple[str, int]:
        """
        Convert PDF to images and OCR each page.

        Args:
            pdf_bytes: PDF file content as bytes

        Returns:
            Tuple of (combined_text, page_count)
        """
        # Convert PDF pages to images
        images = self.pdf_to_images(pdf_bytes)

        if not images:
            logger.warning("No images extracted from PDF")
            return "", 0

        logger.info(f"Processing {len(images)} pages with OCR model {self.model}")

        # OCR each page
        page_texts = []
        consecutive_failures = 0
        max_consecutive_failures = 2  # Stop early if model can't load
        for i, image_bytes in enumerate(images):
            logger.debug(f"OCR processing page {i + 1}/{len(images)}")
            try:
                text = await self.extract_text_from_image(image_bytes)
                if text:
                    page_texts.append(f"--- Page {i + 1} ---\n{text}")
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except RuntimeError as e:
                consecutive_failures += 1
                logger.error(f"OCR failed for page {i + 1}: {e}")
                if consecutive_failures >= max_consecutive_failures:
                    error_msg = str(e)
                    if "model failed to load" in error_msg or "500" in error_msg:
                        logger.error(
                            f"OCR model failed to load after {consecutive_failures} consecutive failures. "
                            "Aborting remaining pages. Check Ollama server logs and available VRAM."
                        )
                    else:
                        logger.error(
                            f"OCR failed {consecutive_failures} consecutive pages. Aborting remaining pages."
                        )
                    raise RuntimeError(
                        f"OCR model unavailable: {error_msg}. "
                        "Ensure the model is loaded and sufficient VRAM is available."
                    )
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"OCR failed for page {i + 1}: {e}")
                if consecutive_failures >= max_consecutive_failures:
                    raise

        if not page_texts:
            logger.error("OCR produced no text from any page")
            return "", 0

        # Combine only successfully extracted text
        combined_text = "\n\n".join(page_texts)

        logger.info(f"OCR complete: {len(combined_text)} characters from {len(page_texts)}/{len(images)} pages")

        return combined_text, len(images)

    async def check_availability(self) -> bool:
        """
        Check if Ollama OCR model is available.

        Returns:
            True if model is available, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return False

                    result = await response.json()
                    models = result.get("models", [])

                    # Check if our OCR model is available
                    for model in models:
                        model_name = model.get("name", "")
                        if model_name.startswith(self.model.split(":")[0]):
                            return True

                    logger.warning(f"OCR model {self.model} not found in Ollama")
                    return False

        except Exception as e:
            logger.error(f"Failed to check Ollama availability: {e}")
            return False
