"""
LLM Helper

Provides LLM synthesis functionality for note processing agents.
Supports multi-provider routing via LLMTaskConfig.

Performance optimizations:
- num_ctx set to practical limits per model (8K-16K for local GPU performance)
- Async HTTP calls via httpx for non-blocking operations
- Both sync and async versions for compatibility
"""

import requests
import json
import logging
import httpx
import asyncio
import threading
import time
from typing import Optional, TYPE_CHECKING
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

# Concurrency limiter for local Ollama models.
# With OLLAMA_NUM_PARALLEL=16, sending 16 concurrent requests causes each to get
# 1/16th GPU compute, making individual requests extremely slow (1 min -> 16 min).
# Limiting to 4 concurrent requests balances parallelism with per-request speed.
# Cloud models (e.g., kimi:cloud) are NOT limited — they have server-side scaling.
_local_ollama_semaphore: threading.Semaphore = None  # type: ignore  # Lazy init


def _get_local_semaphore() -> threading.Semaphore:
    """Get semaphore for local Ollama models only (not cloud models)."""
    global _local_ollama_semaphore
    if _local_ollama_semaphore is None:
        _local_ollama_semaphore = threading.Semaphore(settings.OLLAMA_LOCAL_CONCURRENCY)
    return _local_ollama_semaphore


# Canonical cloud-model detector — single source of truth in
# llm_config_manager. The previous local copy used ``':cloud' in
# model.lower()`` which MISSED the ``-cloud`` suffix variant (e.g.
# ``gpt-oss:120b-cloud``), so cloud models were incorrectly throttled
# by the local-concurrency semaphore. Importing the shared helper
# fixes that latent bug.
from app.services.llm_config_manager import is_cloud_model as _is_cloud_model

from app.config import settings

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig

# Configure logging
logger = logging.getLogger(__name__)

# Import context size config from the single source of truth
# This eliminates duplicate MODEL_CONTEXT_SIZES dicts that can drift out of sync
from app.services.llm_config_manager import (
    get_model_context_size,
    MODEL_CONTEXT_SIZES,
    DEFAULT_CONTEXT_SIZE,
)

# Thread-local storage for current task config
# This allows note_builder to set a config that all agents will use
_thread_local = threading.local()


def set_current_task_config(config: Optional["LLMTaskConfig"]) -> None:
    """
    Set the current task config for this thread.
    Called by note_builder before processing.
    """
    _thread_local.task_config = config
    if config:
        logger.info(f"Set current task config: provider={config.provider}, model={config.model}")


def get_current_task_config() -> Optional["LLMTaskConfig"]:
    """
    Get the current task config for this thread.
    Returns None if no config has been set.
    """
    return getattr(_thread_local, 'task_config', None)


@contextmanager
def task_config_context(config: Optional["LLMTaskConfig"]):
    """
    Context manager for temporarily setting task config.

    Usage:
        with task_config_context(my_config):
            # All synthesize_with_llm calls here will use my_config
            build_urology_note(...)
    """
    old_config = get_current_task_config()
    set_current_task_config(config)
    try:
        yield
    finally:
        set_current_task_config(old_config)


def run_with_task_config(
    task_config: Optional["LLMTaskConfig"],
    func,
    *args,
    **kwargs,
):
    """Invoke ``func`` with ``task_config`` established on the current thread.

    Restores the prior task_config after the call (correctness for any
    caller that's already running inside a different thread-local
    setting; necessary for ThreadPoolExecutor worker reuse where the
    same worker thread may run many tasks).

    Purpose-built for ``ThreadPoolExecutor.submit`` from
    ``note_builder.build_urology_note``: ``threading.local`` state set
    by ``set_current_task_config`` on the parent thread does NOT
    propagate into worker threads, so without this wrapper every
    synthesis sub-agent call inside ``func`` would fall through
    ``synthesize_with_llm``'s legacy path — using
    ``settings.OLLAMA_DEFAULT_MODEL`` (historically ``llama3.1:8b``)
    instead of the user's configured Stage 2 model. That's both wrong
    (bypasses user intent) and dangerous (the legacy model + default
    context size has wedged the GPU multiple times).
    """
    previous = get_current_task_config()
    set_current_task_config(task_config)
    try:
        return func(*args, **kwargs)
    finally:
        set_current_task_config(previous)


class LLMProviderError(Exception):
    """Raised when LLM provider fails to generate response."""
    pass


def synthesize_with_llm(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.0,  # Zero temperature = fully deterministic, eliminates creative hallucinations
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    task_config: Optional["LLMTaskConfig"] = None
) -> str:
    """
    Call LLM to synthesize text from a prompt.

    Supports multi-provider routing via task_config parameter.
    If task_config is provided, uses the configured provider (Ollama, Anthropic, OpenAI).
    If no task_config provided, checks for current thread's task_config (set by note_builder).
    Otherwise, falls back to Ollama with provided model or settings default.

    Args:
        prompt: The user prompt to send to the LLM
        model: Model name (if None, uses settings.OLLAMA_DEFAULT_MODEL) - ignored if task_config provided
        temperature: Temperature for generation (default: 0.0) - ignored if task_config provided
        system_prompt: Optional system prompt
        max_tokens: Maximum tokens to generate - ignored if task_config provided
        task_config: Optional LLMTaskConfig for multi-provider routing

    Returns:
        LLM response text

    Raises:
        LLMProviderError: If LLM fails to generate response
    """
    # If task_config is provided explicitly, use it
    if task_config is not None:
        return _synthesize_with_config(prompt, task_config, system_prompt)

    # Check for thread-local task config (set by note_builder)
    current_config = get_current_task_config()
    if current_config is not None:
        return _synthesize_with_config(prompt, current_config, system_prompt)

    # Legacy behavior: use Ollama directly
    if model is None:
        model = settings.OLLAMA_DEFAULT_MODEL

    if max_tokens is None:
        max_tokens = settings.OLLAMA_MAX_TOKENS

    logger.info(f"Using LLM model: {model} (temperature: {temperature}, max_tokens: {max_tokens})")

    if not settings.OLLAMA_BASE_URL:
        raise LLMProviderError("OLLAMA_BASE_URL not configured in .env")

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    # No task_config provided to this ad-hoc legacy path, so num_ctx falls back
    # to the model's lookup-table value (or DEFAULT_CONTEXT_SIZE for unknowns).
    # Per-task user overrides flow through _synthesize_with_config below.
    num_ctx = get_model_context_size(model)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # keep_alive keeps the model resident on the GPU so subsequent
        # requests do not pay the ~30s load cost. Configurable via env.
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
        }
    }

    if system_prompt:
        payload["system"] = system_prompt

    max_retries = settings.LLM_MAX_RETRIES
    base_delay = settings.LLM_RETRY_BASE_DELAY
    use_semaphore = not _is_cloud_model(model)
    sem = _get_local_semaphore() if use_semaphore else None

    for attempt in range(1, max_retries + 1):
        if sem:
            sem.acquire()
        try:
            response = requests.post(url, json=payload, timeout=settings.OLLAMA_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.Timeout:
            logger.error(f"LLM synthesis timeout after {settings.OLLAMA_TIMEOUT}s")
            raise LLMProviderError(f"Failed to connect to Ollama at {url}: timeout")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500) and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"LLM {status} (attempt {attempt}/{max_retries}), "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            logger.error(f"LLM synthesis failed: {str(e)}")
            raise LLMProviderError(f"Failed to connect to Ollama at {url}: {str(e)}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"LLM response parsing failed: {str(e)}")
            raise LLMProviderError(f"Invalid response from Ollama: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in LLM synthesis: {str(e)}")
            raise LLMProviderError(f"Unexpected LLM error: {str(e)}")
        finally:
            if sem:
                sem.release()

    logger.error(f"LLM synthesis failed after {max_retries} retries (429)")
    raise LLMProviderError(f"Ollama overloaded after {max_retries} retries")


def _synthesize_with_config(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """
    Synthesize using task-specific config with multi-provider support.

    Routes to appropriate provider based on config.provider.

    Args:
        prompt: Input prompt
        config: LLMTaskConfig with provider and model settings
        system_prompt: Optional system prompt

    Returns:
        Generated text response
    """
    provider = config.provider.lower()

    logger.info(
        f"Using {provider} model: {config.model} "
        f"(temperature: {config.temperature}, max_tokens: {config.max_tokens})"
    )

    if provider == "ollama":
        return _call_ollama_sync(prompt, config, system_prompt)
    elif provider == "anthropic":
        return _call_anthropic_sync(prompt, config, system_prompt)
    elif provider == "openai":
        return _call_openai_sync(prompt, config, system_prompt)
    else:
        raise LLMProviderError(f"Unknown LLM provider: {provider}")


def _call_ollama_sync(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call Ollama API synchronously with retry on 429 and concurrency control."""
    if not settings.OLLAMA_BASE_URL:
        raise LLMProviderError("OLLAMA_BASE_URL not configured")

    # Resolution order (single source of truth, see llm_config_manager docstring):
    #   user-set config.num_ctx -> lookup table -> DEFAULT_CONTEXT_SIZE
    num_ctx = config.num_ctx if config and config.num_ctx is not None else get_model_context_size(config.model)
    logger.info(
        f"Ollama sync num_ctx={num_ctx} for model {config.model} "
        f"(source={'user' if config and config.num_ctx is not None else 'lookup'})"
    )

    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
            "num_ctx": num_ctx,
        }
    }

    if system_prompt:
        payload["system"] = system_prompt

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    max_retries = settings.LLM_MAX_RETRIES
    base_delay = settings.LLM_RETRY_BASE_DELAY
    use_semaphore = not _is_cloud_model(config.model)
    sem = _get_local_semaphore() if use_semaphore else None

    for attempt in range(1, max_retries + 1):
        if sem:
            sem.acquire()
        try:
            response = requests.post(url, json=payload, timeout=settings.OLLAMA_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.Timeout:
            logger.error(f"Ollama timeout after {settings.OLLAMA_TIMEOUT}s for model {config.model}")
            raise LLMProviderError(f"Ollama timeout for model {config.model}")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Ollama {status} (attempt {attempt}/{max_retries}), "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            logger.error(f"Ollama HTTP error: {e}")
            if status in (502, 503, 504):
                raise LLMProviderError(
                    f"LLM upstream unavailable ({status}) for model "
                    f"{config.model}. The provider is overloaded or down. "
                    f"Try again shortly or switch to a different model in Settings."
                )
            raise LLMProviderError(f"Ollama call failed: {e}")
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            raise LLMProviderError(f"Ollama call failed: {e}")
        finally:
            if sem:
                sem.release()

    logger.error(f"Ollama failed after {max_retries} retries (429 Too Many Requests)")
    raise LLMProviderError(f"Ollama overloaded after {max_retries} retries")


async def _call_ollama_async(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call Ollama API asynchronously using httpx with retry on 429."""
    if not settings.OLLAMA_BASE_URL:
        raise LLMProviderError("OLLAMA_BASE_URL not configured")

    # Resolution order (single source of truth, see llm_config_manager docstring):
    #   user-set config.num_ctx -> lookup table -> DEFAULT_CONTEXT_SIZE
    num_ctx = config.num_ctx if config and config.num_ctx is not None else get_model_context_size(config.model)
    logger.info(
        f"Ollama async num_ctx={num_ctx} for model {config.model} "
        f"(source={'user' if config and config.num_ctx is not None else 'lookup'})"
    )

    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": config.temperature,
            "num_predict": config.max_tokens,
            "num_ctx": num_ctx,
        }
    }

    if system_prompt:
        payload["system"] = system_prompt

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    max_retries = settings.LLM_MAX_RETRIES
    base_delay = settings.LLM_RETRY_BASE_DELAY

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

                result = response.json()
                return result.get("response", "").strip()

        except httpx.TimeoutException:
            logger.error(f"Ollama async timeout after {settings.OLLAMA_TIMEOUT}s for model {config.model}")
            raise LLMProviderError(f"Ollama timeout for model {config.model}")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Ollama async {status} (attempt {attempt}/{max_retries}), "
                    f"retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                continue
            logger.error(f"Ollama async HTTP error: {e}")
            if status in (502, 503, 504):
                raise LLMProviderError(
                    f"LLM upstream unavailable ({status}) for model "
                    f"{config.model}. The provider is overloaded or down. "
                    f"Try again shortly or switch to a different model in Settings."
                )
            raise LLMProviderError(f"Ollama call failed: {e}")
        except Exception as e:
            logger.error(f"Ollama async call failed: {e}")
            raise LLMProviderError(f"Ollama call failed: {e}")

    logger.error(f"Ollama async failed after {max_retries} retries (429 Too Many Requests)")
    raise LLMProviderError(f"Ollama overloaded after {max_retries} retries")


def _call_anthropic_sync(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call Anthropic Claude API synchronously."""
    if not settings.ANTHROPIC_API_KEY:
        raise LLMProviderError("ANTHROPIC_API_KEY not configured")

    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    messages = [{"role": "user", "content": prompt}]

    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "messages": messages,
    }

    if system_prompt:
        payload["system"] = system_prompt

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=settings.ANTHROPIC_TIMEOUT
        )
        response.raise_for_status()

        result = response.json()
        content = result.get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "".join(text_parts).strip()

    except requests.exceptions.Timeout:
        logger.error(f"Anthropic timeout after {settings.ANTHROPIC_TIMEOUT}s")
        raise LLMProviderError(f"Anthropic timeout for model {config.model}")
    except Exception as e:
        logger.error(f"Anthropic call failed: {e}")
        raise LLMProviderError(f"Anthropic call failed: {e}")


def _call_openai_sync(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call OpenAI API synchronously."""
    if not settings.OPENAI_API_KEY:
        raise LLMProviderError("OPENAI_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "messages": messages,
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.OPENAI_TIMEOUT
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        return ""

    except requests.exceptions.Timeout:
        logger.error(f"OpenAI timeout after {settings.OPENAI_TIMEOUT}s")
        raise LLMProviderError(f"OpenAI timeout for model {config.model}")
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        raise LLMProviderError(f"OpenAI call failed: {e}")


def combine_sections_with_llm(
    section_name: str,
    section_instances: list,
    instructions: str,
    model: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None,
    force_llm: bool = False,
) -> str:
    """
    Combine multiple instances of a section using LLM.

    Args:
        section_name: Name of the section (e.g., "Chief Complaint", "HPI")
        section_instances: List of section texts from different notes
        instructions: Specific instructions for how to combine
        model: Model name (ignored if task_config provided)
        task_config: Optional LLMTaskConfig for multi-provider routing
        force_llm: If True, do NOT short-circuit on single-instance input.
            Callers set this when the LLM must run the instructions even
            for a single prior note — e.g. the HPI agent uses it so the
            authoritative-facts enforcement block can rewrite a single
            contaminated prior HPI rather than passing it through verbatim.

    Returns:
        Combined section text
    """
    # Filter out empty instances
    valid_instances = [inst for inst in section_instances if inst and inst.strip()]

    if not valid_instances:
        return ""

    # If only one instance, return it directly UNLESS the caller demands
    # the LLM run (e.g. to apply authoritative-facts rewriting).
    if len(valid_instances) == 1 and not force_llm:
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
        temperature=0.0,
        task_config=task_config
    )

    return result


# =============================================================================
# ASYNC VERSIONS FOR PARALLEL AGENT EXECUTION
# =============================================================================

async def _call_anthropic_async(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call Anthropic Claude API asynchronously using httpx."""
    if not settings.ANTHROPIC_API_KEY:
        raise LLMProviderError("ANTHROPIC_API_KEY not configured")

    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    messages = [{"role": "user", "content": prompt}]

    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "messages": messages,
    }

    if system_prompt:
        payload["system"] = system_prompt

    try:
        async with httpx.AsyncClient(timeout=settings.ANTHROPIC_TIMEOUT) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            content = result.get("content", [])
            text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "".join(text_parts).strip()

    except httpx.TimeoutException:
        logger.error(f"Anthropic async timeout after {settings.ANTHROPIC_TIMEOUT}s")
        raise LLMProviderError(f"Anthropic timeout for model {config.model}")
    except Exception as e:
        logger.error(f"Anthropic async call failed: {e}")
        raise LLMProviderError(f"Anthropic call failed: {e}")


async def _call_openai_async(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """Call OpenAI API asynchronously using httpx."""
    if not settings.OPENAI_API_KEY:
        raise LLMProviderError("OPENAI_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.OPENAI_TIMEOUT) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""

    except httpx.TimeoutException:
        logger.error(f"OpenAI async timeout after {settings.OPENAI_TIMEOUT}s")
        raise LLMProviderError(f"OpenAI timeout for model {config.model}")
    except Exception as e:
        logger.error(f"OpenAI async call failed: {e}")
        raise LLMProviderError(f"OpenAI call failed: {e}")


async def synthesize_with_llm_async(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    task_config: Optional["LLMTaskConfig"] = None
) -> str:
    """
    Async version of synthesize_with_llm for parallel agent execution.

    Args:
        prompt: The user prompt to send to the LLM
        model: Model name (if None, uses settings.OLLAMA_DEFAULT_MODEL)
        temperature: Temperature for generation (default: 0.0)
        system_prompt: Optional system prompt
        max_tokens: Maximum tokens to generate
        task_config: Optional LLMTaskConfig for multi-provider routing

    Returns:
        LLM response text
    """
    # If task_config is provided explicitly, use it
    if task_config is not None:
        return await _synthesize_with_config_async(prompt, task_config, system_prompt)

    # Check for thread-local task config (set by note_builder)
    current_config = get_current_task_config()
    if current_config is not None:
        return await _synthesize_with_config_async(prompt, current_config, system_prompt)

    # Legacy fallback: use defaults from .env settings
    if model is None:
        model = settings.OLLAMA_DEFAULT_MODEL

    if max_tokens is None:
        max_tokens = settings.OLLAMA_MAX_TOKENS

    # Create a temporary config using .env defaults
    from app.services.llm_config_manager import LLMTaskConfig
    temp_config = LLMTaskConfig(
        provider=settings.STAGE1_LLM_PROVIDER,  # From .env, not hardcoded
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )

    return await _call_ollama_async(prompt, temp_config, system_prompt)


async def _synthesize_with_config_async(
    prompt: str,
    config: "LLMTaskConfig",
    system_prompt: Optional[str] = None
) -> str:
    """
    Async version of synthesize using task-specific config.

    Routes to appropriate async provider based on config.provider.
    """
    provider = config.provider.lower()

    logger.info(
        f"[ASYNC] Using {provider} model: {config.model} "
        f"(temperature: {config.temperature}, max_tokens: {config.max_tokens})"
    )

    if provider == "ollama":
        return await _call_ollama_async(prompt, config, system_prompt)
    elif provider == "anthropic":
        return await _call_anthropic_async(prompt, config, system_prompt)
    elif provider == "openai":
        return await _call_openai_async(prompt, config, system_prompt)
    else:
        raise LLMProviderError(f"Unknown LLM provider: {provider}")


async def combine_sections_with_llm_async(
    section_name: str,
    section_instances: list,
    instructions: str,
    model: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None
) -> str:
    """
    Async version of combine_sections_with_llm for parallel execution.

    Args:
        section_name: Name of the section (e.g., "Chief Complaint", "HPI")
        section_instances: List of section texts from different notes
        instructions: Specific instructions for how to combine
        model: Model name (ignored if task_config provided)
        task_config: Optional LLMTaskConfig for multi-provider routing

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
    result = await synthesize_with_llm_async(
        prompt=prompt,
        model=model,
        temperature=0.0,
        task_config=task_config
    )

    return result


def run_sync_in_thread(func, *args, **kwargs):
    """
    Run a synchronous function in a thread pool to avoid blocking.

    This is useful for running sync LLM calls in parallel.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        return future.result()
