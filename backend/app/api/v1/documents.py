"""
Document Processing API Endpoints

Handles document upload and text extraction for clinical note generation.
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Dict
import PyPDF2
import io

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/extract-text")
async def extract_text_from_pdf(
    file: UploadFile = File(...)
) -> Dict[str, str]:
    """
    Extract text from uploaded PDF or text file.

    Args:
        file: Uploaded file (PDF or TXT)

    Returns:
        Dictionary with extracted text

    Raises:
        HTTPException: If file processing fails
    """
    try:
        # Read file content
        content = await file.read()

        # Check file type
        if file.filename.lower().endswith('.pdf'):
            # Extract text from PDF
            try:
                pdf_file = io.BytesIO(content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)

                text_parts = []
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                extracted_text = '\n\n'.join(text_parts)

                if not extracted_text.strip():
                    logger.warning(f"No text extracted from PDF: {file.filename}")
                    raise HTTPException(
                        status_code=422,
                        detail="PDF contains no extractable text"
                    )

                logger.info(f"Extracted {len(extracted_text)} characters from PDF: {file.filename}")
                return {"text": extracted_text}

            except Exception as e:
                logger.error(f"Error extracting text from PDF {file.filename}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to extract text from PDF: {str(e)}"
                )

        elif file.filename.lower().endswith('.txt'):
            # Plain text file
            try:
                text = content.decode('utf-8')
                logger.info(f"Loaded {len(text)} characters from text file: {file.filename}")
                return {"text": text}
            except UnicodeDecodeError:
                try:
                    # Try Latin-1 encoding
                    text = content.decode('latin-1')
                    logger.info(f"Loaded {len(text)} characters from text file (latin-1): {file.filename}")
                    return {"text": text}
                except Exception as e:
                    logger.error(f"Error decoding text file {file.filename}: {e}")
                    raise HTTPException(
                        status_code=422,
                        detail="Unable to decode text file"
                    )

        else:
            raise HTTPException(
                status_code=422,
                detail="Unsupported file type. Only PDF and TXT files are supported."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing file {file.filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )
