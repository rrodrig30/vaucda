"""
Pydantic schemas for note generation API
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


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
