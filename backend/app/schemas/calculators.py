"""
Pydantic schemas for calculator API
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class CalculatorRequest(BaseModel):
    """Request schema for calculator execution."""
    inputs: Dict[str, Any] = Field(
        ...,
        description="Calculator input values"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "inputs": {
                    "psa": 8.5,
                    "age": 65,
                    "family_history": True,
                    "prior_biopsy": False
                }
            }
        }


class CalculatorResponse(BaseModel):
    """Response schema for calculator execution."""
    calculator_id: str = Field(..., description="Calculator identifier")
    result: Any = Field(..., description="Calculation result")
    interpretation: str = Field(..., description="Human-readable interpretation")
    recommendations: List[str] = Field(
        default_factory=list,
        description="Clinical recommendations"
    )
    formatted_output: str = Field(
        default="",
        description="Formatted output for display"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "calculator_id": "pcpt_risk",
                "result": {"cancer_risk": 0.23, "high_grade_risk": 0.08},
                "interpretation": "Patient has 23% risk of prostate cancer and 8% risk of high-grade disease",
                "recommendations": [
                    "Consider prostate biopsy",
                    "Discuss risks and benefits with patient"
                ],
                "formatted_output": "Prostate Cancer Risk: 23%\nHigh-Grade Risk: 8%",
                "metadata": {
                    "calculator_version": "2.0",
                    "reference": "Thompson et al. NEJM 2006"
                }
            }
        }


class CalculatorInfo(BaseModel):
    """Schema for calculator information."""
    id: str
    name: str
    description: str
    category: str
    required_inputs: List[str]
    optional_inputs: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    input_schema: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Rich input metadata for form building and validation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "pcpt_risk",
                "name": "PCPT Prostate Cancer Risk Calculator",
                "description": "Estimates risk of prostate cancer and high-grade disease",
                "category": "prostate",
                "required_inputs": ["age", "psa", "dre_result", "family_history", "prior_biopsy"],
                "optional_inputs": ["race"],
                "references": [
                    "Thompson IM, et al. NEJM 2006;355:1995-2004"
                ],
                "input_schema": [
                    {
                        "field_name": "psa",
                        "display_name": "PSA",
                        "input_type": "numeric",
                        "required": True,
                        "description": "Prostate-Specific Antigen level",
                        "unit": "ng/mL",
                        "min_value": 0.0,
                        "max_value": 500.0,
                        "example": "4.5",
                        "help_text": "Normal range: 0-4 ng/mL"
                    }
                ]
            }
        }


class CalculatorListResponse(BaseModel):
    """Response schema for calculator list."""
    calculators: Dict[str, List[CalculatorInfo]] = Field(
        ...,
        description="Calculators organized by category"
    )
    total: int = Field(..., description="Total number of calculators")

    class Config:
        json_schema_extra = {
            "example": {
                "calculators": {
                    "prostate": [
                        {
                            "id": "pcpt_risk",
                            "name": "PCPT Risk Calculator",
                            "description": "Prostate cancer risk estimation",
                            "category": "prostate",
                            "required_inputs": ["age", "psa"],
                            "optional_inputs": [],
                            "references": []
                        }
                    ],
                    "kidney": []
                },
                "total": 44
            }
        }
