"""
Clinical Calculator API endpoints
Handles all 44 urological calculators
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_active_user, get_optional_user
from app.database.sqlite_models import User
from app.schemas.calculators import (
    CalculatorRequest,
    CalculatorResponse,
    CalculatorInfo,
    CalculatorListResponse
)
from calculators.registry import registry as calculator_registry
from calculators.base import CalculatorCategory

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=CalculatorListResponse)
async def list_calculators(
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    List all available calculators organized by category.

    Returns all 44 urological calculators with metadata including:
    - ID, name, description
    - Category (prostate, kidney, bladder, etc.)
    - Required and optional inputs
    - References
    """
    try:
        # Get calculators organized by category
        by_category = calculator_registry.list_by_category()

        # Convert to CalculatorInfo schema
        calculators_dict = {}
        total = 0

        for category, calcs in by_category.items():
            calc_infos = []
            for calc_meta in calcs:
                # Get full calculator for detailed info
                calc = calculator_registry.get(calc_meta["id"])
                if calc:
                    info = CalculatorInfo(
                        id=calc.calculator_id,
                        name=calc.name,
                        description=calc.description,
                        category=calc.category.value,
                        required_inputs=calc.required_inputs,
                        optional_inputs=calc.optional_inputs,
                        references=calc.references
                    )
                    calc_infos.append(info)
                    total += 1

            calculators_dict[category] = calc_infos

        user_id = current_user.id if current_user else "anonymous"
        logger.info(f"Listed {total} calculators for user {user_id}")

        return CalculatorListResponse(
            calculators=calculators_dict,
            total=total
        )

    except Exception as e:
        logger.error(f"Failed to list calculators: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list calculators: {str(e)}"
        )


@router.get("/{calculator_id}", response_model=CalculatorInfo)
async def get_calculator(
    calculator_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed information about a specific calculator.

    Returns:
    - Calculator metadata
    - Required and optional inputs
    - Input validation rules (if available)
    - Input schema with rich metadata
    - References and citations
    """
    try:
        # Get calculator from registry
        calculator = calculator_registry.get(calculator_id)

        if not calculator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calculator '{calculator_id}' not found"
            )

        # Get input schema if available
        input_schema = calculator.get_input_schema()
        schema_dict = [metadata.to_dict() for metadata in input_schema] if input_schema else None

        logger.info(f"Retrieved calculator info: {calculator_id}")

        return CalculatorInfo(
            id=calculator.calculator_id,
            name=calculator.name,
            description=calculator.description,
            category=calculator.category.value,
            required_inputs=calculator.required_inputs,
            optional_inputs=calculator.optional_inputs,
            references=calculator.references,
            input_schema=schema_dict
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get calculator {calculator_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get calculator: {str(e)}"
        )


@router.get("/{calculator_id}/input-schema")
async def get_calculator_input_schema(
    calculator_id: str
):
    """
    Get detailed input schema for a specific calculator.

    Returns rich metadata for each input field including:
    - Field type (numeric, enum, boolean, etc.)
    - Validation rules (min/max, allowed values)
    - Display information (labels, descriptions, help text)
    - Units and examples

    This enables frontends to:
    - Build intelligent forms with proper validation
    - Display helpful tooltips and guidance
    - Show acceptable value ranges and options
    - Pre-populate fields from clinical context
    """
    try:
        # Get calculator from registry
        calculator = calculator_registry.get(calculator_id)

        if not calculator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calculator '{calculator_id}' not found"
            )

        # Get input schema
        input_schema = calculator.get_input_schema()

        # Convert to dict format for JSON serialization
        schema_dict = [metadata.to_dict() for metadata in input_schema]

        logger.info(f"Retrieved input schema for calculator: {calculator_id}")

        return {
            "calculator_id": calculator_id,
            "calculator_name": calculator.name,
            "input_schema": schema_dict
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get input schema for {calculator_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get input schema: {str(e)}"
        )


@router.post("/{calculator_id}/calculate", response_model=CalculatorResponse)
async def calculate(
    calculator_id: str,
    request: CalculatorRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Execute a specific calculator with provided inputs.

    Workflow:
    1. Validate calculator exists
    2. Validate inputs against calculator requirements
    3. Execute calculation
    4. Return results with interpretation and recommendations

    **Note:** Only metadata is logged (no patient data).
    """
    try:
        # Get calculator from registry
        calculator = calculator_registry.get(calculator_id)

        if not calculator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calculator '{calculator_id}' not found"
            )

        logger.info(f"User {current_user.id} executing calculator: {calculator_id}")

        # Validate inputs
        is_valid, error_message = calculator.validate_inputs(request.inputs)

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid inputs: {error_message}"
            )

        # Execute calculator
        result = calculator.calculate(request.inputs)

        # Build response
        response = CalculatorResponse(
            calculator_id=calculator_id,
            result=result.result,
            interpretation=result.interpretation,
            recommendations=result.recommendations,
            formatted_output=result.format_output(),
            metadata={
                "calculator_name": calculator.name,
                "category": calculator.category.value,
                "references": calculator.references
            }
        )

        logger.info(f"Calculator {calculator_id} executed successfully")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calculator execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculator execution failed: {str(e)}"
        )


@router.get("/category/{category}")
async def get_calculators_by_category(
    category: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all calculators in a specific category.

    Categories:
    - prostate
    - kidney
    - bladder
    - voiding
    - female
    - reconstructive
    - fertility
    - hypogonadism
    - stones
    - surgical
    """
    try:
        # Validate category
        try:
            cat_enum = CalculatorCategory(category)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category: {category}"
            )

        # Get calculators in category
        calculators = calculator_registry.get_by_category(cat_enum)

        # Convert to response format
        calc_list = []
        for calc in calculators:
            calc_list.append({
                "id": calc.calculator_id,
                "name": calc.name,
                "description": calc.description,
                "required_inputs": calc.required_inputs,
                "optional_inputs": calc.optional_inputs
            })

        logger.info(f"Retrieved {len(calc_list)} calculators in category: {category}")

        return {
            "category": category,
            "calculators": calc_list,
            "total": len(calc_list)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get calculators by category: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get calculators: {str(e)}"
        )


@router.post("/batch/calculate")
async def batch_calculate(
    requests: list[dict],
    current_user: User = Depends(get_current_active_user)
):
    """
    Execute multiple calculators in a single request.

    Useful for running multiple related calculators simultaneously.

    Request format:
    ```
    [
        {"calculator_id": "pcpt_risk", "inputs": {...}},
        {"calculator_id": "capra", "inputs": {...}}
    ]
    ```
    """
    try:
        results = []

        for req in requests:
            calculator_id = req.get("calculator_id")
            inputs = req.get("inputs", {})

            if not calculator_id:
                results.append({
                    "calculator_id": None,
                    "error": "Missing calculator_id"
                })
                continue

            # Get calculator
            calculator = calculator_registry.get(calculator_id)

            if not calculator:
                results.append({
                    "calculator_id": calculator_id,
                    "error": f"Calculator not found: {calculator_id}"
                })
                continue

            # Validate and execute
            try:
                is_valid, error_message = calculator.validate_inputs(inputs)

                if not is_valid:
                    results.append({
                        "calculator_id": calculator_id,
                        "error": f"Invalid inputs: {error_message}"
                    })
                    continue

                # Execute
                result = calculator.calculate(inputs)

                results.append({
                    "calculator_id": calculator_id,
                    "calculator_name": calculator.name,
                    "result": result.result,
                    "interpretation": result.interpretation,
                    "recommendations": result.recommendations,
                    "formatted_output": result.format_output()
                })

            except Exception as e:
                results.append({
                    "calculator_id": calculator_id,
                    "error": str(e)
                })

        logger.info(f"Batch calculation completed: {len(results)} calculators")

        return {
            "results": results,
            "total": len(results),
            "successful": len([r for r in results if "error" not in r])
        }

    except Exception as e:
        logger.error(f"Batch calculation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch calculation failed: {str(e)}"
        )
