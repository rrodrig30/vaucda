

---

## 8. LLM Integration Layer

### 8.1 Abstract Provider Interface

```python
# llm/provider.py
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

class TaskType(Enum):
    NOTE_GENERATION = "note_generation"
    CLINICAL_EXTRACTION = "clinical_extraction"
    CALCULATOR_ASSIST = "calculator_assist"
    EVIDENCE_SEARCH = "evidence_search"
    SUMMARIZATION = "summarization"
    ASSESSMENT = "assessment"

@dataclass
class ModelInfo:
    """Information about an available LLM model."""
    provider: str            # "ollama" or "anthropic"
    name: str                # Model identifier
    display_name: str        # Human-readable name
    size: Optional[str]      # e.g., "8B", "70B"
    context_window: int      # Max context tokens
    max_output: int          # Max output tokens
    capabilities: List[str]  # e.g., ["chat", "code", "medical"]
    is_available: bool = True
    last_checked: Optional[str] = None

class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Supports Ollama and Anthropic only (no OpenAI per requirements).
    Each provider implements dynamic model discovery.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """Generate completion from the provider."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Generate completion with streaming output."""
        pass

    @abstractmethod
    async def discover_models(self) -> List[ModelInfo]:
        """Discover available models from this provider at runtime."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is online and responsive."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider identifier."""
        pass
```

### 8.2 Ollama Provider with Dynamic Discovery

```python
# llm/ollama.py
from typing import Optional, List, AsyncIterator
from dataclasses import dataclass
import httpx
from .provider import LLMProvider, ModelInfo, TaskType

@dataclass
class OllamaConfig:
    """Configuration for Ollama local LLM server."""
    host: str = "http://localhost:11434"
    timeout: float = 120.0
    default_model: str = "llama3.1:8b"
    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.9

class OllamaProvider(LLMProvider):
    """Ollama LLM provider with dynamic model discovery.

    Connects to local Ollama server and discovers available models
    via the /api/tags endpoint at runtime.
    """

    def __init__(self, config: OllamaConfig):
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.host,
            timeout=config.timeout
        )
        self._model_cache: Optional[List[ModelInfo]] = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """Generate completion from Ollama model.

        Args:
            prompt: User prompt text
            system_prompt: System-level instructions
            model: Model name (uses default if not specified)
            temperature: Generation temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        model = model or self.config.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": kwargs.get("top_p", self.config.top_p),
                "num_predict": max_tokens,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "")

    async def chat(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Chat completion with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name override

        Returns:
            Assistant response text
        """
        model = model or self.config.default_model

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", self.config.top_p),
            }
        }

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("message", {}).get("content", "")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream generation token by token.

        Yields:
            Individual text chunks as they are generated
        """
        model = model or self.config.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with self._client.stream(
            "POST", "/api/generate", json=payload
        ) as response:
            response.raise_for_status()
            import json
            async for line in response.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    text = chunk.get("response", "")
                    if text:
                        yield text
                    if chunk.get("done", False):
                        break

    async def generate_embeddings(
        self,
        text: str,
        model: str = "nomic-embed-text"
    ) -> List[float]:
        """Generate embeddings using Ollama embedding model.

        Args:
            text: Text to embed
            model: Embedding model name

        Returns:
            Embedding vector as list of floats
        """
        payload = {
            "model": model,
            "prompt": text
        }

        response = await self._client.post("/api/embeddings", json=payload)
        response.raise_for_status()
        return response.json()["embedding"]

    async def discover_models(self) -> List[ModelInfo]:
        """Discover locally available Ollama models via /api/tags.

        Queries the Ollama server to enumerate all locally installed
        models, their sizes, and capabilities.

        Returns:
            List of ModelInfo for each available model
        """
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        data = response.json()

        models = []
        for model_data in data.get("models", []):
            name = model_data.get("name", "")
            size = model_data.get("size", 0)
            details = model_data.get("details", {})

            # Estimate context window from model family
            context_window = self._estimate_context_window(name, details)

            # Determine capabilities
            capabilities = self._determine_capabilities(name)

            # Format size for display
            size_gb = size / (1024 ** 3) if size else 0
            size_display = f"{size_gb:.1f}GB" if size_gb > 0 else "unknown"

            models.append(ModelInfo(
                provider="ollama",
                name=name,
                display_name=name,
                size=size_display,
                context_window=context_window,
                max_output=context_window // 4,
                capabilities=capabilities,
                is_available=True,
                last_checked=model_data.get("modified_at")
            ))

        self._model_cache = models
        return models

    async def pull_model(self, model_name: str) -> AsyncIterator[dict]:
        """Pull/download a model from Ollama registry.

        Args:
            model_name: Model to pull (e.g., "llama3.1:8b")

        Yields:
            Progress update dictionaries
        """
        payload = {"name": model_name, "stream": True}

        async with self._client.stream(
            "POST", "/api/pull", json=payload
        ) as response:
            response.raise_for_status()
            import json
            async for line in response.aiter_lines():
                if line:
                    yield json.loads(line)

    async def health_check(self) -> bool:
        """Check if Ollama server is responsive."""
        try:
            response = await self._client.get("/")
            return response.status_code == 200
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "ollama"

    def _estimate_context_window(self, name: str, details: dict) -> int:
        """Estimate context window from model name/details."""
        name_lower = name.lower()
        # Known model context windows
        if "llama3" in name_lower or "llama-3" in name_lower:
            return 131072 if "3.1" in name_lower else 8192
        elif "mistral" in name_lower:
            return 32768
        elif "phi" in name_lower:
            return 128000 if "phi-3" in name_lower else 4096
        elif "gemma" in name_lower:
            return 8192
        elif "qwen" in name_lower:
            return 32768
        elif "codellama" in name_lower:
            return 16384
        return details.get("context_length", 4096)

    def _determine_capabilities(self, name: str) -> List[str]:
        """Determine model capabilities from name."""
        name_lower = name.lower()
        caps = ["chat"]

        if any(kw in name_lower for kw in ["code", "coder", "codellama"]):
            caps.append("code")
        if any(kw in name_lower for kw in ["med", "clinical", "bio", "pubmed"]):
            caps.append("medical")
        if any(kw in name_lower for kw in ["embed", "nomic"]):
            caps = ["embedding"]
        if any(kw in name_lower for kw in ["70b", "72b", "34b"]):
            caps.append("large_context")

        return caps

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()
```

### 8.3 Anthropic Provider with Dynamic Discovery

```python
# llm/anthropic_provider.py
from typing import Optional, List, AsyncIterator
from dataclasses import dataclass
import anthropic
from .provider import LLMProvider, ModelInfo, TaskType

@dataclass
class AnthropicConfig:
    """Configuration for Anthropic Claude API."""
    api_key: str
    default_model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 4096
    temperature: float = 0.3

# Known Anthropic models with capabilities
ANTHROPIC_MODELS = [
    {
        "name": "claude-opus-4-5-20251101",
        "display": "Claude Opus 4.5",
        "context": 200000,
        "max_output": 32000,
        "capabilities": ["chat", "code", "medical", "large_context", "vision"]
    },
    {
        "name": "claude-sonnet-4-20250514",
        "display": "Claude Sonnet 4",
        "context": 200000,
        "max_output": 16000,
        "capabilities": ["chat", "code", "medical", "large_context"]
    },
    {
        "name": "claude-3-5-sonnet-20241022",
        "display": "Claude 3.5 Sonnet",
        "context": 200000,
        "max_output": 8192,
        "capabilities": ["chat", "code", "medical", "large_context"]
    },
    {
        "name": "claude-3-5-haiku-20241022",
        "display": "Claude 3.5 Haiku",
        "context": 200000,
        "max_output": 8192,
        "capabilities": ["chat", "code", "fast"]
    },
    {
        "name": "claude-3-opus-20240229",
        "display": "Claude 3 Opus",
        "context": 200000,
        "max_output": 4096,
        "capabilities": ["chat", "code", "medical", "large_context"]
    },
    {
        "name": "claude-3-haiku-20240307",
        "display": "Claude 3 Haiku",
        "context": 200000,
        "max_output": 4096,
        "capabilities": ["chat", "fast"]
    },
]

class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider with dynamic model discovery.

    Uses the Anthropic Python SDK for API calls and discovers
    available models at runtime.
    """

    def __init__(self, config: AnthropicConfig):
        self.config = config
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)
        self._model_cache: Optional[List[ModelInfo]] = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> str:
        """Generate completion from Anthropic Claude.

        Args:
            prompt: User prompt text
            system_prompt: System-level instructions
            model: Model name (uses default if not specified)
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        model = model or self.config.default_model

        messages = [{"role": "user", "content": prompt}]

        create_kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system_prompt:
            create_kwargs["system"] = system_prompt

        response = await self._client.messages.create(**create_kwargs)

        # Extract text from response content blocks
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return "".join(text_parts)

    async def chat(
        self,
        messages: List[dict],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Chat completion with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System instructions
            model: Model name override

        Returns:
            Assistant response text
        """
        model = model or self.config.default_model

        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        if system_prompt:
            create_kwargs["system"] = system_prompt

        response = await self._client.messages.create(**create_kwargs)

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return "".join(text_parts)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream generation from Anthropic Claude.

        Yields:
            Text chunks as they are generated
        """
        model = model or self.config.default_model

        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        if system_prompt:
            create_kwargs["system"] = system_prompt

        async with self._client.messages.stream(**create_kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def discover_models(self) -> List[ModelInfo]:
        """Discover available Anthropic models.

        Tests each known model for availability by attempting a
        minimal API call.

        Returns:
            List of ModelInfo for available models
        """
        available_models = []

        for model_def in ANTHROPIC_MODELS:
            model_info = ModelInfo(
                provider="anthropic",
                name=model_def["name"],
                display_name=model_def["display"],
                size=None,
                context_window=model_def["context"],
                max_output=model_def["max_output"],
                capabilities=model_def["capabilities"],
                is_available=True,
            )

            # Verify availability with a minimal test call
            try:
                await self._client.messages.create(
                    model=model_def["name"],
                    max_tokens=1,
                    messages=[{"role": "user", "content": "test"}],
                )
                model_info.is_available = True
            except anthropic.NotFoundError:
                model_info.is_available = False
            except anthropic.AuthenticationError:
                model_info.is_available = False
            except Exception:
                # Rate limit or other transient - assume available
                model_info.is_available = True

            available_models.append(model_info)

        self._model_cache = [m for m in available_models if m.is_available]
        return self._model_cache

    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        try:
            await self._client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "anthropic"

    async def close(self) -> None:
        """Close Anthropic client."""
        await self._client.close()
```

### 8.4 Dynamic Model Discovery Registry

```python
# llm/registry.py
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
from .provider import LLMProvider, ModelInfo, TaskType
from .ollama import OllamaProvider
from .anthropic_provider import AnthropicProvider

@dataclass
class ProviderStatus:
    """Runtime status of an LLM provider."""
    name: str
    is_online: bool = False
    models: List[ModelInfo] = field(default_factory=list)
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None

class DynamicModelRegistry:
    """Central registry for runtime model discovery across providers.

    Polls configured providers to discover available models,
    tracks provider health, and recommends models for tasks.
    """

    # Task-to-model recommendations
    TASK_RECOMMENDATIONS: Dict[TaskType, Dict[str, List[str]]] = {
        TaskType.NOTE_GENERATION: {
            "ollama": ["llama3.1:70b", "llama3.1:8b", "mistral:7b"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        },
        TaskType.CLINICAL_EXTRACTION: {
            "ollama": ["llama3.1:8b", "mistral:7b", "phi3:medium"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        },
        TaskType.CALCULATOR_ASSIST: {
            "ollama": ["phi3:medium", "llama3.1:8b"],
            "anthropic": ["claude-3-5-haiku-20241022", "claude-3-haiku-20240307"],
        },
        TaskType.EVIDENCE_SEARCH: {
            "ollama": ["llama3.1:8b", "mistral:7b"],
            "anthropic": ["claude-3-5-sonnet-20241022"],
        },
        TaskType.SUMMARIZATION: {
            "ollama": ["llama3.1:8b", "phi3:medium"],
            "anthropic": ["claude-3-5-haiku-20241022"],
        },
        TaskType.ASSESSMENT: {
            "ollama": ["llama3.1:70b", "llama3.1:8b"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        },
    }

    # Discovery cache TTL
    CACHE_TTL = timedelta(minutes=5)

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._status: Dict[str, ProviderStatus] = {}
        self._discovery_lock = asyncio.Lock()

    def register_provider(self, provider: LLMProvider) -> None:
        """Register an LLM provider for discovery."""
        name = provider.get_provider_name()
        self._providers[name] = provider
        self._status[name] = ProviderStatus(name=name)

    async def discover_all_models(
        self,
        force_refresh: bool = False
    ) -> Dict[str, List[ModelInfo]]:
        """Discover available models from all registered providers.

        Args:
            force_refresh: Bypass cache and re-poll all providers

        Returns:
            Dictionary of provider name -> list of available models
        """
        async with self._discovery_lock:
            results = {}

            for name, provider in self._providers.items():
                status = self._status[name]

                # Check cache validity
                if (not force_refresh
                    and status.last_checked
                    and datetime.utcnow() - status.last_checked < self.CACHE_TTL
                    and status.is_online):
                    results[name] = status.models
                    continue

                # Poll provider
                try:
                    is_healthy = await provider.health_check()
                    if is_healthy:
                        models = await provider.discover_models()
                        status.is_online = True
                        status.models = models
                        status.error_message = None
                    else:
                        status.is_online = False
                        status.models = []
                        status.error_message = "Health check failed"
                except Exception as e:
                    status.is_online = False
                    status.models = []
                    status.error_message = str(e)

                status.last_checked = datetime.utcnow()
                results[name] = status.models

            return results

    async def get_model_for_task(
        self,
        task: TaskType,
        preferred_provider: Optional[str] = None,
    ) -> tuple:
        """Get the best available model for a given task.

        Args:
            task: Type of task to perform
            preferred_provider: Provider preference (optional)

        Returns:
            Tuple of (provider_name, model_name)

        Raises:
            RuntimeError: If no suitable model is available
        """
        all_models = await self.discover_all_models()

        recommendations = self.TASK_RECOMMENDATIONS.get(task, {})

        # Try preferred provider first
        if preferred_provider and preferred_provider in all_models:
            rec_models = recommendations.get(preferred_provider, [])
            available_names = {m.name for m in all_models[preferred_provider]}
            for model_name in rec_models:
                if model_name in available_names:
                    return (preferred_provider, model_name)
            # Use any available model from preferred provider
            if all_models[preferred_provider]:
                return (preferred_provider, all_models[preferred_provider][0].name)

        # Try all providers in recommendation order
        for provider_name, rec_models in recommendations.items():
            if provider_name not in all_models:
                continue
            available_names = {m.name for m in all_models[provider_name]}
            for model_name in rec_models:
                if model_name in available_names:
                    return (provider_name, model_name)

        # Last resort: any available model from any provider
        for provider_name, models in all_models.items():
            if models:
                return (provider_name, models[0].name)

        raise RuntimeError("No LLM models available from any provider")

    async def get_provider(self, name: str) -> LLMProvider:
        """Get a registered provider by name."""
        if name not in self._providers:
            raise ValueError(f"Provider not registered: {name}")
        return self._providers[name]

    async def get_all_status(self) -> List[ProviderStatus]:
        """Get status of all registered providers."""
        await self.discover_all_models()
        return list(self._status.values())

    async def get_flat_model_list(self) -> List[ModelInfo]:
        """Get a flat list of all available models across all providers."""
        all_models = await self.discover_all_models()
        flat = []
        for models in all_models.values():
            flat.extend(models)
        return flat
```

### 8.5 LLM Orchestrator

```python
# llm/orchestrator.py
from typing import Optional, List, AsyncIterator
from .registry import DynamicModelRegistry
from .provider import LLMProvider, TaskType, ModelInfo

class LLMOrchestrator:
    """Orchestrate LLM calls across Ollama and Anthropic providers.

    Provides a unified interface for the application layer,
    handling provider selection, model routing, and failover.
    """

    def __init__(self, registry: DynamicModelRegistry):
        self.registry = registry

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task: TaskType = TaskType.NOTE_GENERATION,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate text using the best available model.

        If provider and model are specified, uses them directly.
        Otherwise, selects the best model for the task type.

        Args:
            prompt: User prompt
            system_prompt: System instructions
            task: Task type for model selection
            provider: Provider override
            model: Model override

        Returns:
            Generated text
        """
        if provider and model:
            llm = await self.registry.get_provider(provider)
            return await llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                **kwargs
            )

        # Auto-select provider and model
        selected_provider, selected_model = await self.registry.get_model_for_task(
            task=task,
            preferred_provider=provider,
        )

        llm = await self.registry.get_provider(selected_provider)
        return await llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            model=selected_model,
            **kwargs
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task: TaskType = TaskType.NOTE_GENERATION,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream generation using the best available model."""
        if not (provider and model):
            provider, model = await self.registry.get_model_for_task(
                task=task, preferred_provider=provider,
            )

        llm = await self.registry.get_provider(provider)
        async for chunk in llm.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            **kwargs
        ):
            yield chunk

    async def list_available_models(self) -> List[ModelInfo]:
        """List all available models across all providers."""
        return await self.registry.get_flat_model_list()
```

### 8.6 Clinical System Prompts

```python
# llm/prompts.py

CLINICAL_NOTE_SYSTEM_PROMPT = """You are a clinical documentation assistant specialized in urology (Dr. Rodriguez). Your role is to create structured urology clinic notes from clinical data extracted from EPIC FHIR.

CRITICAL RULES:
1. Use ONLY clinical data provided in the input. Never fabricate clinical information.
2. Maintain medical accuracy and use appropriate AUA/NCCN terminology.
3. Organize information according to the standard urology note template.
4. Provide COMPLETE information - no truncations of any section.
5. Include EVERY imaging result and EVERY pathology result.
6. Use chain of thought reasoning for clinical decision-making.
7. For PSA Curve: [r] format with H flag for values >4.0.
8. For follow-up visits, do NOT include "New Patient" in the chief complaint.
9. Assessment must be 4-8 sentences in narrative format.
10. Weight loss in managed programs (MOVE!, keto) should be framed positively.
11. Distinguish between pathologic and expected lifestyle changes.

Output the note in narrative format, without bullet points."""

ASSESSMENT_SYSTEM_PROMPT = """You are a urology specialist generating the Assessment section of a clinic note. Create a 4-8 sentence narrative summary that:

1. Integrates findings from HPI, labs, imaging, and pathology
2. Follows AUA guidelines; for cancer patients, NCCN guidelines
3. Considers full clinical context (intentional vs unintentional changes)
4. Does NOT express concern about intentional weight loss in managed programs
5. References relevant calculator results when available
6. Uses chain of thought reasoning

Return ONLY the assessment narrative. No meta-commentary."""

PLAN_SYSTEM_PROMPT = """You are a urology specialist generating the Plan section of a clinic note. Create a plan that:

1. Addresses each problem in the problem list
2. Follows AUA/NCCN evidence-based guidelines
3. Includes specific follow-up intervals
4. References relevant lab values and trending
5. Integrates calculator results into decision-making
6. Uses tree of thought exploration for treatment options

Return ONLY the plan content. No meta-commentary."""

CALCULATOR_ASSIST_PROMPT = """You are a clinical calculator assistant. Extract relevant values from the provided clinical data to populate calculator inputs.

For the {calculator_name} calculator, identify these inputs:
{input_list}

Extract values from the FHIR-provided clinical data and format as JSON.
If a value cannot be determined from the data, mark it as null.
Only use values explicitly present in the clinical data."""
```
