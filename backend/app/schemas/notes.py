"""
Pydantic schemas for note generation API
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class NoteGenerateRequest(BaseModel):
    """Request schema for note generation."""
    input_text: str = Field(
        ...,
        description="Raw clinical input (labs, imaging, prior notes)",
        min_length=10
    )
    note_type: str = Field(
        default="clinic",
        description="Type of note to generate",
        pattern="^(clinic|consult|preop|postop|procedure|telephone)$"
    )
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider to use",
        pattern="^(ollama|anthropic|openai)$"
    )
    calculator_ids: List[str] = Field(
        default_factory=list,
        description="List of calculator IDs to run"
    )
    use_rag: bool = Field(
        default=True,
        description="Whether to use RAG for evidence-based guidance"
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="LLM temperature for generation"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens to generate"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "input_text": "65 yo M with PSA 8.2, prior normal DRE, family history of prostate cancer",
                "note_type": "clinic",
                "llm_provider": "ollama",
                "calculator_ids": ["pcpt_risk", "eortc_prostate"],
                "use_rag": True,
                "temperature": 0.3
            }
        }


class CalculatorResultSchema(BaseModel):
    """Schema for calculator result."""
    calculator_id: str
    calculator_name: str
    result: Any
    interpretation: str
    recommendations: List[str] = Field(default_factory=list)
    formatted_output: str = ""


class NoteResponse(BaseModel):
    """Response schema for generated note."""
    note_text: str = Field(..., description="Generated clinical note")
    calculator_results: List[CalculatorResultSchema] = Field(
        default_factory=list,
        description="Results from clinical calculators"
    )
    rag_sources: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Source citations from RAG"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Generation metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "note_text": "CC: Elevated PSA\n\nHPI: 65 year old male presents...",
                "calculator_results": [
                    {
                        "calculator_id": "pcpt_risk",
                        "calculator_name": "PCPT Risk Calculator",
                        "result": {"cancer_risk": 0.23},
                        "interpretation": "23% risk of prostate cancer",
                        "recommendations": ["Consider prostate biopsy"],
                        "formatted_output": "Risk: 23%"
                    }
                ],
                "rag_sources": [
                    {
                        "id": "1",
                        "title": "AUA Prostate Cancer Guidelines 2024",
                        "source": "AUA",
                        "category": "prostate"
                    }
                ],
                "metadata": {
                    "note_type": "clinic",
                    "llm_provider": "ollama",
                    "generation_time_seconds": 12.5,
                    "num_calculators": 1,
                    "rag_enabled": True
                }
            }
        }


class NoteListResponse(BaseModel):
    """Response schema for listing notes (future use)."""
    notes: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


# ============================================================================
# TWO-STAGE WORKFLOW SCHEMAS (Improved Clinical Workflow)
# ============================================================================

class ExtractedEntity(BaseModel):
    """Schema for extracted clinical entity."""
    field: str = Field(..., description="Field name (e.g., 'psa', 'gleason_primary')")
    value: Any = Field(..., description="Extracted value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    source_text: str = Field(..., description="Source text where entity was found")


class CalculatorSuggestion(BaseModel):
    """Schema for suggested calculator."""
    calculator_id: str = Field(..., description="Unique calculator identifier")
    calculator_name: str = Field(..., description="Display name")
    category: str = Field(..., description="Calculator category")
    confidence: str = Field(..., description="Confidence level: high, medium, low")
    auto_selected: bool = Field(..., description="Whether to auto-select this calculator")
    reason: str = Field(..., description="Explanation for suggestion")
    required_inputs: List[str] = Field(..., description="All required input fields")
    available_inputs: List[str] = Field(..., description="Inputs detected in clinical text")
    missing_inputs: List[str] = Field(..., description="Inputs not detected (need manual entry)")
    detected_entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted values")


class InitialNoteRequest(BaseModel):
    """Request schema for Stage 1: Initial note generation (no calculators)."""
    clinical_input: str = Field(
        ...,
        description="Raw clinical input (from ambient listening + pasted data)",
        min_length=10
    )
    note_type: str = Field(
        default="urology_clinic",
        description="Type of note to generate",
        pattern="^(urology_clinic|urology_consult)$"
    )
    patient_name: Optional[str] = Field(
        default=None,
        description="Patient full name for note header"
    )
    ssn_last4: Optional[str] = Field(
        default=None,
        description="Last 4 digits of patient SSN for identification"
    )
    visit_date: Optional[str] = Field(
        default=None,
        description="Anticipated date of visit (MM/DD/YYYY). Used for IPSS date and accurate age calculation."
    )
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider to use",
        pattern="^(ollama|anthropic|openai)$"
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Specific model name (e.g., 'llama3.1:8b')"
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="LLM temperature"
    )
    use_rag: bool = Field(
        default=True,
        description="Enable RAG (Retrieval-Augmented Generation)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "clinical_input": "72 yo male with PSA 8.5, Gleason 3+4 on biopsy, 4/12 cores positive. Discussed treatment options...",
                "note_type": "clinic_note",
                "llm_provider": "ollama",
                "temperature": 0.3
            }
        }


class InitialNoteResponse(BaseModel):
    """Response schema for Stage 1: Initial note with calculator suggestions."""
    preliminary_note: str = Field(..., description="Organized note WITHOUT assessment/plan")
    extracted_entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Clinical entities extracted from input"
    )
    suggested_calculators: List[CalculatorSuggestion] = Field(
        default_factory=list,
        description="Calculators suggested based on detected entities"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Generation metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "preliminary_note": "CHIEF COMPLAINT: Elevated PSA\n\nHPI: 72-year-old male...",
                "extracted_entities": [
                    {
                        "field": "psa",
                        "value": 8.5,
                        "confidence": 0.95,
                        "source_text": "PSA 8.5"
                    }
                ],
                "suggested_calculators": [
                    {
                        "calculator_id": "capra_score",
                        "calculator_name": "CAPRA Score",
                        "category": "prostate",
                        "confidence": "high",
                        "auto_selected": True,
                        "reason": "All required inputs detected",
                        "required_inputs": ["psa", "age", "gleason_primary", "gleason_secondary", "clinical_stage", "percent_positive_cores"],
                        "available_inputs": ["psa", "age", "gleason_primary", "gleason_secondary", "percent_positive_cores"],
                        "missing_inputs": ["clinical_stage"],
                        "detected_entities": {"psa": 8.5, "age": 72}
                    }
                ],
                "metadata": {
                    "generation_time_seconds": 3.2,
                    "entities_extracted": 6,
                    "calculators_suggested": 2
                }
            }
        }


class FinalNoteRequest(BaseModel):
    """Request schema for Stage 2: Final note with calculators."""
    preliminary_note: str = Field(
        ...,
        description="Preliminary note from Stage 1"
    )
    clinical_input: str = Field(
        ...,
        description="Original clinical input (for calculator execution)"
    )
    note_type: str = Field(
        default="urology_clinic",
        description="Type of note to generate",
        pattern="^(urology_clinic|urology_consult)$"
    )
    patient_name: Optional[str] = Field(
        default=None,
        description="Patient full name for note header"
    )
    ssn_last4: Optional[str] = Field(
        default=None,
        description="Last 4 digits of patient SSN for identification"
    )
    visit_date: Optional[str] = Field(
        default=None,
        description="Anticipated date of visit (MM/DD/YYYY). Used for IPSS date and accurate age calculation."
    )
    selected_calculators: List[str] = Field(
        default_factory=list,
        description="Calculator IDs selected by user"
    )
    additional_inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="User-provided values for missing calculator inputs"
    )
    use_rag: bool = Field(
        default=True,
        description="Whether to use RAG for evidence-based guidance"
    )
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider"
    )
    llm_model: Optional[str] = Field(default=None, description="Specific model")
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)

    class Config:
        json_schema_extra = {
            "example": {
                "preliminary_note": "CHIEF COMPLAINT: Elevated PSA...",
                "clinical_input": "72 yo male with PSA 8.5...",
                "selected_calculators": ["capra_score", "nccn_risk"],
                "additional_inputs": {
                    "clinical_stage": "T1c",
                    "family_history": False
                },
                "use_rag": True,
                "llm_provider": "ollama"
            }
        }


class FinalNoteResponse(BaseModel):
    """Response schema for Stage 2: Complete note with A&P."""
    final_note: str = Field(..., description="Complete note with Assessment & Plan")
    preliminary_note: Optional[str] = Field(
        default=None,
        description="Preliminary (Stage 1) note. Populated by Express path; "
                    "omitted by the standard /generate-final endpoint."
    )
    calculator_results: List[CalculatorResultSchema] = Field(
        default_factory=list,
        description="Results from executed calculators"
    )
    rag_sources: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Evidence sources from RAG"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Generation metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "final_note": "CLINIC NOTE - Urology\n\n[CC, HPI, Exam...]\n\nASSESSMENT & PLAN:\n1. Prostate Adenocarcinoma...",
                "calculator_results": [
                    {
                        "calculator_id": "capra_score",
                        "calculator_name": "CAPRA Score",
                        "result": {"score": 4, "risk_level": "Intermediate"},
                        "interpretation": "CAPRA Score 4/10: Intermediate risk",
                        "recommendations": ["Consider radical prostatectomy or radiation"],
                        "formatted_output": "CAPRA Score: 4/10 (Intermediate Risk)"
                    }
                ],
                "rag_sources": [
                    {"title": "NCCN Prostate Cancer Guidelines", "source": "NCCN"}
                ],
                "metadata": {
                    "generation_time_seconds": 8.4,
                    "calculators_executed": 2,
                    "rag_enabled": True
                }
            }
        }


# ============================================================================
# DOCUMENT UPLOAD SCHEMAS (OCR Support)
# ============================================================================

class DocumentUploadResponse(BaseModel):
    """Response from document upload endpoint with OCR support."""
    extracted_text: str = Field(..., description="Text extracted from document")
    temp_file_id: str = Field(..., description="ID for temp file (deleted after Stage 2)")
    extraction_method: Literal["text", "ocr"] = Field(
        ...,
        description="Method used: 'text' for direct extraction, 'ocr' for image-based PDFs"
    )
    page_count: int = Field(default=1, description="Number of pages processed")
    file_name: str = Field(..., description="Original file name")
    file_size_bytes: int = Field(..., description="Original file size in bytes")

    class Config:
        json_schema_extra = {
            "example": {
                "extracted_text": "Patient Name: John Doe\nDOB: 01/15/1960\nPSA: 8.5 ng/mL...",
                "temp_file_id": "sess_abc123_doc_xyz789",
                "extraction_method": "ocr",
                "page_count": 3,
                "file_name": "lab_results.pdf",
                "file_size_bytes": 524288
            }
        }


# ============================================================================
# BATCH PROCESSING SCHEMAS
# ============================================================================

class BatchProcessingRequest(BaseModel):
    """Request schema for batch processing a folder of clinical documents.

    LLM provider, model, temperature, and RAG settings are loaded from
    the user's saved preferences in the Settings page (Stage 1 and Stage 2 configs).
    """
    folder_path: str = Field(
        ...,
        description="Absolute path to folder containing clinical documents (.txt files)",
        min_length=1
    )
    visit_date: Optional[str] = Field(
        default=None,
        description="Anticipated date of visit (MM/DD/YYYY or YYYY-MM-DD). Used for IPSS date column and accurate age calculation from DOB."
    )


class BatchFileStatus(str, Enum):
    """Status of a single file in batch processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchFileResult(BaseModel):
    """Result for a single file in batch processing."""
    filename: str = Field(..., description="Original filename")
    output_filename: str = Field(..., description="Output filename (.vaucda)")
    note_type: str = Field(..., description="Detected note type (urology_clinic or urology_consult)")
    status: BatchFileStatus = Field(..., description="Processing status")
    attempts: int = Field(default=0, description="Number of processing attempts")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    generation_time_seconds: Optional[float] = Field(default=None, description="Time to generate")


class BatchProcessingResponse(BaseModel):
    """Response schema for batch processing completion."""
    total_files: int = Field(..., description="Total files found in folder")
    processed: int = Field(..., description="Successfully processed count")
    failed: int = Field(..., description="Failed count after max retries")
    results: List[BatchFileResult] = Field(default_factory=list, description="Per-file results")
    total_file: str = Field(..., description="Path to total.vaucda concatenation file")
    total_time_seconds: float = Field(..., description="Total batch processing time")


class BatchFolderFile(BaseModel):
    """Schema for a single file in batch folder listing."""
    filename: str = Field(..., description="File name")
    size_bytes: int = Field(..., description="File size in bytes")
    note_type: str = Field(..., description="Detected note type")
    output_filename: str = Field(..., description="Expected output filename (.vaucda)")


class BatchFolderListResponse(BaseModel):
    """Response schema for listing folder contents for batch processing."""
    folder_path: str = Field(..., description="Validated folder path")
    total_files: int = Field(..., description="Number of processable files")
    files: List[BatchFolderFile] = Field(default_factory=list, description="File details")
