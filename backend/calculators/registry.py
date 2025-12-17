"""
Calculator Registry for auto-discovery and management of all calculators.
"""

import logging
import importlib
import inspect
from typing import Dict, List, Optional, Type
from pathlib import Path

from calculators.base import ClinicalCalculator, CalculatorCategory

logger = logging.getLogger(__name__)


class CalculatorRegistry:
    """
    Registry for all clinical calculators with auto-discovery.
    Provides lookup by ID, category, and name.
    """

    _instance = None
    _calculators: Dict[str, Type[ClinicalCalculator]] = {}
    _initialized = False

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize registry."""
        if not self._initialized:
            self._discover_calculators()
            self._initialized = True

    def _discover_calculators(self):
        """Auto-discover all calculator classes."""
        logger.info("Discovering calculators...")

        # Get calculators directory
        calculators_dir = Path(__file__).parent

        # Categories to scan
        categories = [
            "prostate",
            "kidney",
            "bladder",
            "voiding",
            "female",
            "reconstructive",
            "fertility",
            "hypogonadism",
            "stones",
            "surgical",
        ]

        for category in categories:
            category_dir = calculators_dir / category
            if not category_dir.exists():
                continue

            # Scan Python files in category
            for py_file in category_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                # Import module
                module_name = f"calculators.{category}.{py_file.stem}"
                try:
                    module = importlib.import_module(module_name)

                    # Find calculator classes
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (
                            issubclass(obj, ClinicalCalculator)
                            and obj is not ClinicalCalculator
                            and not inspect.isabstract(obj)
                        ):
                            # Register calculator
                            calc_instance = obj()
                            calc_id = calc_instance.calculator_id
                            self._calculators[calc_id] = obj
                            logger.info(f"Registered calculator: {calc_id} ({calc_instance.name})")

                except Exception as e:
                    logger.error(f"Failed to import {module_name}: {str(e)}")

        logger.info(f"Total calculators registered: {len(self._calculators)}")

    def get(self, calculator_id: str) -> Optional[ClinicalCalculator]:
        """
        Get calculator instance by ID.

        Args:
            calculator_id: Calculator identifier

        Returns:
            Calculator instance or None if not found
        """
        calc_class = self._calculators.get(calculator_id)
        if calc_class:
            return calc_class()
        return None

    def get_by_category(self, category: CalculatorCategory) -> List[ClinicalCalculator]:
        """
        Get all calculators in a category.

        Args:
            category: Calculator category

        Returns:
            List of calculator instances
        """
        calculators = []
        for calc_class in self._calculators.values():
            calc = calc_class()
            if calc.category == category:
                calculators.append(calc)
        return calculators

    def get_all(self) -> List[ClinicalCalculator]:
        """
        Get all registered calculators.

        Returns:
            List of all calculator instances
        """
        return [calc_class() for calc_class in self._calculators.values()]

    def get_all_ids(self) -> List[str]:
        """
        Get all registered calculator IDs.

        Returns:
            List of calculator IDs
        """
        return list(self._calculators.keys())

    def get_calculator_info(self, calculator_id: str) -> Optional[Dict]:
        """
        Get information about a calculator.

        Args:
            calculator_id: Calculator identifier

        Returns:
            Dict with calculator info or None if not found
        """
        calc = self.get(calculator_id)
        if not calc:
            return None

        return {
            "id": calc.calculator_id,
            "name": calc.name,
            "category": calc.category.value,
            "description": calc.description,
            "required_inputs": calc.required_inputs,
            "optional_inputs": calc.optional_inputs,
            "references": calc.references,
        }

    def list_by_category(self) -> Dict[str, List[Dict]]:
        """
        List all calculators organized by category.

        Returns:
            Dict mapping category names to lists of calculator info
        """
        by_category = {}

        for category in CalculatorCategory:
            calculators = self.get_by_category(category)
            by_category[category.value] = [
                {
                    "id": calc.calculator_id,
                    "name": calc.name,
                    "description": calc.description,
                }
                for calc in calculators
            ]

        return by_category


# Global registry instance
registry = CalculatorRegistry()
