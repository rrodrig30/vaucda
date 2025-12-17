"""
Base classes for clinical calculators.

Defines abstract base class and data models for all VAUCDA calculators.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime
from enum import Enum


class CalculatorCategory(Enum):
    """Calculator categories."""
    PROSTATE_CANCER = "prostate_cancer"
    KIDNEY_CANCER = "kidney_cancer"
    BLADDER_CANCER = "bladder_cancer"
    MALE_VOIDING = "male_voiding"
    FEMALE_UROLOGY = "female_urology"
    RECONSTRUCTIVE = "reconstructive"
    MALE_FERTILITY = "male_fertility"
    HYPOGONADISM = "hypogonadism"
    STONES = "stones"
    SURGICAL_PLANNING = "surgical_planning"


class InputType(Enum):
    """Types of calculator inputs."""
    NUMERIC = "numeric"
    ENUM = "enum"
    BOOLEAN = "boolean"
    TEXT = "text"
    DATE = "date"


@dataclass
class InputMetadata:
    """
    Metadata describing a calculator input field.

    Provides rich information for frontends to:
    - Display appropriate input widgets
    - Show validation hints and tooltips
    - Validate inputs client-side
    - Display helpful examples
    """
    field_name: str
    display_name: str
    input_type: InputType
    required: bool = True
    description: str = ""
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    default_value: Optional[Any] = None
    example: Optional[str] = None
    help_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "field_name": self.field_name,
            "display_name": self.display_name,
            "input_type": self.input_type.value,
            "required": self.required,
            "description": self.description,
            "unit": self.unit,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "allowed_values": self.allowed_values,
            "default_value": self.default_value,
            "example": self.example,
            "help_text": self.help_text
        }


@dataclass
class CalculatorInput:
    """Input for a clinical calculator."""
    calculator_id: str
    inputs: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CalculatorResult:
    """Result from a clinical calculator."""
    calculator_id: str
    calculator_name: str
    result: Any  # Can be number, string, dict, etc.
    interpretation: str
    category: str = ""
    risk_level: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_inputs: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def format_output(self) -> str:
        """Format result for display in clinical note."""
        output = [f"**{self.calculator_name}**\n"]

        # Add result
        if isinstance(self.result, dict):
            output.append("Results:")
            for key, value in self.result.items():
                output.append(f"  - {key}: {value}")
        else:
            output.append(f"Result: {self.result}")

        # Add interpretation
        output.append(f"\nInterpretation: {self.interpretation}")

        # Add category/risk if present
        if self.category:
            output.append(f"Category: {self.category}")
        if self.risk_level:
            output.append(f"Risk Level: {self.risk_level}")

        # Add recommendations
        if self.recommendations:
            output.append("\nRecommendations:")
            for rec in self.recommendations:
                output.append(f"  - {rec}")

        # Add references
        if self.references:
            output.append("\nReferences:")
            for ref in self.references:
                output.append(f"  - {ref}")

        return "\n".join(output)


class ValidationError(Exception):
    """Exception raised for invalid calculator inputs."""
    pass


class ClinicalCalculator(ABC):
    """
    Abstract base class for all clinical calculators.

    All calculators must implement:
    1. validate_inputs() - Validate input parameters
    2. calculate() - Perform the calculation
    3. Properties for name, category, description, references
    """

    def __init__(self):
        """Initialize calculator."""
        self.calculator_id = self.__class__.__name__.lower()

    @property
    @abstractmethod
    def name(self) -> str:
        """Calculator display name."""
        pass

    @property
    @abstractmethod
    def category(self) -> CalculatorCategory:
        """Calculator category."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of calculator purpose."""
        pass

    @property
    @abstractmethod
    def references(self) -> List[str]:
        """List of primary references/citations."""
        pass

    @property
    def required_inputs(self) -> List[str]:
        """
        List of required input parameter names.
        Override if needed for dynamic inputs.
        """
        return []

    @property
    def optional_inputs(self) -> List[str]:
        """
        List of optional input parameter names.
        Override if needed.
        """
        return []

    def get_input_schema(self) -> List[InputMetadata]:
        """
        Get detailed metadata for all calculator inputs.

        Override this method in calculator implementations to provide
        rich input metadata for frontend display and validation.

        Returns:
            List of InputMetadata objects describing each input field

        Example:
            return [
                InputMetadata(
                    field_name="psa",
                    display_name="PSA",
                    input_type=InputType.NUMERIC,
                    required=True,
                    description="Prostate-Specific Antigen level",
                    unit="ng/mL",
                    min_value=0,
                    max_value=500,
                    example="4.5",
                    help_text="Normal range: 0-4 ng/mL"
                ),
                InputMetadata(
                    field_name="gleason_primary",
                    display_name="Gleason Primary",
                    input_type=InputType.ENUM,
                    required=True,
                    description="Primary Gleason score",
                    allowed_values=[1, 2, 3, 4, 5],
                    example="3"
                )
            ]
        """
        return []

    @abstractmethod
    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters.

        Args:
            inputs: Dictionary of input parameters

        Returns:
            Tuple of (is_valid, error_message)
            error_message is None if valid
        """
        pass

    @abstractmethod
    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """
        Execute the clinical calculation.

        Args:
            inputs: Validated input parameters

        Returns:
            CalculatorResult with results and interpretation

        Raises:
            ValidationError: If inputs are invalid
        """
        pass

    def run(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """
        Validate inputs and run calculation.

        Args:
            inputs: Input parameters

        Returns:
            CalculatorResult

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        is_valid, error_msg = self.validate_inputs(inputs)
        if not is_valid:
            raise ValidationError(f"{self.name}: {error_msg}")

        # Calculate
        result = self.calculate(inputs)

        # Ensure raw inputs are stored
        result.raw_inputs = inputs

        return result

    def _validate_range(
        self,
        value: Any,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        param_name: str = "value"
    ) -> Tuple[bool, Optional[str]]:
        """
        Helper to validate numeric range.

        Args:
            value: Value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            param_name: Parameter name for error message

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            num_value = float(value)

            if min_val is not None and num_value < min_val:
                return False, f"{param_name} must be >= {min_val}"

            if max_val is not None and num_value > max_val:
                return False, f"{param_name} must be <= {max_val}"

            return True, None

        except (ValueError, TypeError):
            return False, f"{param_name} must be a number"

    def _validate_required(
        self,
        inputs: Dict[str, Any],
        required_keys: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Helper to validate required inputs are present.

        Args:
            inputs: Input dictionary
            required_keys: List of required keys

        Returns:
            Tuple of (is_valid, error_message)
        """
        missing = [key for key in required_keys if key not in inputs or inputs[key] is None]

        if missing:
            return False, f"Missing required inputs: {', '.join(missing)}"

        return True, None

    def _validate_enum(
        self,
        value: Any,
        allowed_values: List[Any],
        param_name: str = "value"
    ) -> Tuple[bool, Optional[str]]:
        """
        Helper to validate enum/categorical values.

        Args:
            value: Value to validate
            allowed_values: List of allowed values
            param_name: Parameter name for error message

        Returns:
            Tuple of (is_valid, error_message)
        """
        if value not in allowed_values:
            return False, f"{param_name} must be one of: {allowed_values}"

        return True, None
