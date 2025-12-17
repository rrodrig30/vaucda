"""
LLM Helper

Provides LLM synthesis functionality for note processing agents.
"""

import requests
import json
import logging
from typing import Optional
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when LLM provider fails to generate response."""
    pass


def synthesize_with_llm(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.0,  # Zero temperature = fully deterministic, eliminates creative hallucinations
    system_prompt: Optional[str] = None
) -> str:
    """
    Call Ollama LLM to synthesize text from a prompt.

    Args:
        prompt: The user prompt to send to the LLM
        model: Model name (if None, uses settings.OLLAMA_DEFAULT_MODEL)
        temperature: Temperature for generation (default: 0.0 for fully deterministic clinical documentation)
        system_prompt: Optional system prompt

    Returns:
        LLM response text

    Raises:
        LLMProviderError: If LLM fails to generate response
    """
    # Use provided model or fall back to settings default
    if model is None:
        model = settings.OLLAMA_DEFAULT_MODEL

    logger.info(f"Using LLM model: {model} (temperature: {temperature})")

    if not settings.OLLAMA_BASE_URL:
        raise LLMProviderError("OLLAMA_BASE_URL not configured in .env")

    try:
        # Ollama API endpoint from settings
        url = f"{settings.OLLAMA_BASE_URL}/api/generate"

        # Build request
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False
        }

        if system_prompt:
            payload["system"] = system_prompt

        # Call Ollama with timeout from settings
        response = requests.post(url, json=payload, timeout=settings.OLLAMA_TIMEOUT)
        response.raise_for_status()

        result = response.json()
        return result.get("response", "").strip()

    except requests.exceptions.RequestException as e:
        logger.error(f"LLM synthesis failed: {str(e)}")
        raise LLMProviderError(f"Failed to connect to Ollama at {url}: {str(e)}")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"LLM response parsing failed: {str(e)}")
        raise LLMProviderError(f"Invalid response from Ollama: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in LLM synthesis: {str(e)}")
        raise LLMProviderError(f"Unexpected LLM error: {str(e)}")


def combine_sections_with_llm(
    section_name: str,
    section_instances: list,
    instructions: str,
    model: Optional[str] = None
) -> str:
    """
    Combine multiple instances of a section using LLM.

    Args:
        section_name: Name of the section (e.g., "Chief Complaint", "HPI")
        section_instances: List of section texts from different notes
        instructions: Specific instructions for how to combine
        model: Model name

    Returns:
        Combined section text
    """
    # Filter out empty instances
    valid_instances = [inst for inst in section_instances if inst and inst.strip()]

    if not valid_instances:
        return ""

    # If only one instance, return it directly
    if len(valid_instances) == 1:
        return valid_instances[0]

    # Build prompt for LLM
    prompt = f"""You are a clinical documentation assistant. Your task is to combine multiple {section_name} entries into a single, cohesive {section_name}.

{instructions}

Here are the {section_name} entries from different clinical notes:

"""

    for i, instance in enumerate(valid_instances, 1):
        prompt += f"\n--- Entry {i} ---\n{instance}\n"

    prompt += f"\n\nPlease synthesize these into a single, comprehensive {section_name}. Focus on the most current and clinically relevant information.\n\nIMPORTANT: Return ONLY the synthesized content. Do NOT include any meta-commentary, explanations, notes, or phrases like 'Here is...', 'I have combined...', 'Note:', etc. Just return the clean, synthesized {section_name} text."

    # Call LLM with zero temperature for deterministic clinical synthesis
    result = synthesize_with_llm(
        prompt=prompt,
        model=model,
        temperature=0.0
    )

    return result
