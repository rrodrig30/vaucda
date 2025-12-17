"""
Pydantic schemas for RAG API
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RAGSearchRequest(BaseModel):
    """Request schema for RAG search."""
    query: str = Field(
        ...,
        description="Search query",
        min_length=3
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of results to return"
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by category (prostate, kidney, etc.)"
    )
    search_strategy: str = Field(
        default="graph",
        description="Search strategy to use",
        pattern="^(vector|hybrid|graph|clinical)$"
    )
    patient_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Patient context for clinical search"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "management of localized prostate cancer",
                "limit": 5,
                "category": "prostate",
                "search_strategy": "graph"
            }
        }


class SearchResult(BaseModel):
    """Schema for a single search result."""
    content: str = Field(..., description="Document content")
    source: str = Field(..., description="Source of document")
    title: Optional[str] = Field(None, description="Document title")
    relevance: float = Field(..., description="Relevance score (0-1)", ge=0, le=1)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    related_concepts: List[str] = Field(
        default_factory=list,
        description="Related clinical concepts"
    )
    applicable_calculators: List[str] = Field(
        default_factory=list,
        description="Applicable calculators"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "content": "For patients with low-risk localized prostate cancer...",
                "source": "AUA",
                "title": "AUA Prostate Cancer Guidelines 2024",
                "relevance": 0.89,
                "metadata": {
                    "category": "prostate",
                    "publication_date": "2024-01-15",
                    "version": "2024.1"
                },
                "related_concepts": ["Active Surveillance", "Radiation Therapy", "Surgery"],
                "applicable_calculators": ["CAPRA", "PCPT Risk"]
            }
        }


class RAGSearchResponse(BaseModel):
    """Response schema for RAG search."""
    results: List[SearchResult] = Field(
        ...,
        description="Search results"
    )
    sources: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Source attribution"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Search metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "content": "Low-risk prostate cancer patients...",
                        "source": "AUA",
                        "title": "Prostate Cancer Guidelines",
                        "relevance": 0.89,
                        "metadata": {},
                        "related_concepts": [],
                        "applicable_calculators": []
                    }
                ],
                "sources": [
                    {
                        "id": "1",
                        "title": "AUA Prostate Cancer Guidelines 2024",
                        "source": "AUA",
                        "category": "prostate"
                    }
                ],
                "metadata": {
                    "query": "prostate cancer management",
                    "strategy": "graph",
                    "num_results": 5
                }
            }
        }


class CalculatorRecommendationRequest(BaseModel):
    """Request schema for calculator recommendations."""
    query: str = Field(
        ...,
        description="Clinical query",
        min_length=3
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of recommendations"
    )


class CalculatorRecommendationResponse(BaseModel):
    """Response schema for calculator recommendations."""
    calculators: List[Dict[str, Any]] = Field(
        ...,
        description="Recommended calculators"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Recommendation metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "calculators": [
                    {
                        "name": "PCPT Risk Calculator",
                        "calculator_id": "pcpt_risk",
                        "relevance_count": 3,
                        "description": "Estimates prostate cancer risk"
                    }
                ],
                "metadata": {
                    "query": "elevated PSA",
                    "num_recommendations": 3
                }
            }
        }
