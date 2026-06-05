"""Pre-request Ollama / GPU health check.

The shared GPU on this host can be wedged by ANY process (not just
vaucda) that loads a model with a context size that exceeds available
VRAM. The most common signature: an 8B model loaded with its full 131K
training context allocates ~140 GB of KV cache on a 96 GB GPU, throwing
the runner into thrash mode that blocks every subsequent Ollama request
— local or cloud-proxied — until the runner is killed.

This module checks for that condition before vaucda submits a new
batch (or single-note request), so the user gets an immediate,
actionable error naming the offending model instead of watching the
batch processor burn through 20-minute timeouts on a wedged service.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# Cached GPU VRAM total. nvidia-smi is invoked once per process; the
# value can't change without a hardware swap, so a single lookup is
# sufficient. None means we tried and failed to determine it (no GPU,
# no nvidia-smi binary, etc.) and subsequent checks should pass through
# rather than block the pipeline.
_VRAM_TOTAL_MB_CACHE: Optional[int] = None
_VRAM_LOOKUP_ATTEMPTED: bool = False


def _gpu_total_vram_mb() -> Optional[int]:
    """Return total GPU VRAM in MB via nvidia-smi, cached after first call.

    Returns None when nvidia-smi is unavailable or the query fails —
    callers must treat None as "skip the check, don't block requests."
    """
    global _VRAM_TOTAL_MB_CACHE, _VRAM_LOOKUP_ATTEMPTED
    if _VRAM_LOOKUP_ATTEMPTED:
        return _VRAM_TOTAL_MB_CACHE
    _VRAM_LOOKUP_ATTEMPTED = True

    nvidia_smi = shutil.which('nvidia-smi')
    if not nvidia_smi:
        logger.info("nvidia-smi not found; Ollama health check will skip VRAM comparison")
        return None
    try:
        result = subprocess.run(
            [nvidia_smi,
             '--query-gpu=memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logger.warning(
                "nvidia-smi exited %d (stderr=%r); health check will skip VRAM check",
                result.returncode, result.stderr[:200],
            )
            return None
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        if not lines:
            return None
        # Single-GPU host — take the first device's VRAM.
        _VRAM_TOTAL_MB_CACHE = int(lines[0])
        logger.info("GPU total VRAM detected: %d MB", _VRAM_TOTAL_MB_CACHE)
        return _VRAM_TOTAL_MB_CACHE
    except Exception as e:
        logger.warning(
            "nvidia-smi query failed: %s; health check will skip VRAM check",
            e,
        )
        return None


@dataclass
class OllamaHealthResult:
    """Verdict from check_ollama_gpu_health().

    A False healthy means the synthesis pipeline should refuse new
    requests until the issue is resolved. `reason` is safe to surface
    in API responses and batch error messages — it names the offending
    model and the corrective action.
    """
    healthy: bool
    reason: str = ""
    total_vram_mb: Optional[int] = None
    loaded_vram_mb: int = 0
    problematic_models: List[str] = field(default_factory=list)


def check_ollama_gpu_health(
    headroom_mb: int = 2048,
    timeout_s: float = 5.0,
) -> OllamaHealthResult:
    """Verify Ollama is in a usable state for a new /api/generate call.

    Returns healthy=True when either:
      - No models exceed VRAM and total loaded VRAM + headroom < total,
        OR
      - We cannot determine GPU VRAM (no nvidia-smi → conservative
        pass-through; we can't know enough to fail safely).

    Returns healthy=False with a specific actionable `reason` when:
      - Ollama /api/ps is unreachable or returns an error (the service
        is itself down/hung), or
      - Any single loaded model claims more VRAM than the GPU has
        (the classic 131K-context-on-an-8B-model wedge signature), or
      - The sum of all loaded models' VRAM + headroom exceeds total
        (multi-model VRAM exhaustion).

    Args:
        headroom_mb: VRAM cushion to require above the loaded total.
            2 GB by default — enough room for a small new model load
            or a context-cache extension without OOM.
        timeout_s: Ollama /api/ps timeout. The check itself MUST NOT
            be slow. A hung Ollama produces an "unhealthy" verdict on
            timeout, which is the correct answer.
    """
    total_vram = _gpu_total_vram_mb()

    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return OllamaHealthResult(
            healthy=False,
            reason=(
                f"Ollama /api/ps unreachable ({type(e).__name__}: "
                f"{str(e)[:120]}). The service is down or hung. "
                "Restart it with `sudo systemctl restart ollama` "
                "before resubmitting."
            ),
            total_vram_mb=total_vram,
        )

    loaded = data.get('models', []) or []
    loaded_vram_bytes = sum(int(m.get('size_vram', 0) or 0) for m in loaded)
    loaded_vram_mb = loaded_vram_bytes // (1024 * 1024)

    if total_vram is None:
        # No GPU info — don't block. Surface what we know.
        return OllamaHealthResult(
            healthy=True,
            reason="nvidia-smi unavailable; VRAM comparison skipped",
            loaded_vram_mb=loaded_vram_mb,
        )

    # Single-model VRAM overshoot — the wedge signature.
    problematic: List[str] = []
    problematic_names: List[str] = []
    for m in loaded:
        sv_mb = int(m.get('size_vram', 0) or 0) // (1024 * 1024)
        if sv_mb > total_vram:
            name = m.get('name', '?')
            ctx = m.get('context_length', '?')
            problematic.append(
                f"{name} requests {sv_mb} MB VRAM (ctx={ctx}) vs "
                f"{total_vram} MB GPU total"
            )
            problematic_names.append(name)
    if problematic:
        return OllamaHealthResult(
            healthy=False,
            reason=(
                "Ollama has a model loaded that exceeds GPU VRAM, "
                "causing runner thrash that blocks ALL Ollama requests "
                "(local AND cloud-proxied). Offending model(s): "
                + "; ".join(problematic)
                + ". Kill the wedged runner before resubmitting "
                "(`sudo systemctl restart ollama`). The model that "
                "loaded with an excessive num_ctx is the culprit — "
                "fix its config to use a smaller context."
            ),
            total_vram_mb=total_vram,
            loaded_vram_mb=loaded_vram_mb,
            problematic_models=problematic_names,
        )

    # Aggregate VRAM exhaustion (multi-model overcommit).
    if loaded_vram_mb + headroom_mb > total_vram:
        return OllamaHealthResult(
            healthy=False,
            reason=(
                f"Loaded Ollama models occupy {loaded_vram_mb} MB of "
                f"VRAM (GPU total: {total_vram} MB; required headroom: "
                f"{headroom_mb} MB). A new request would OOM. Wait for "
                "Ollama keep_alive to expire and unload one of the "
                "models, or restart Ollama."
            ),
            total_vram_mb=total_vram,
            loaded_vram_mb=loaded_vram_mb,
            problematic_models=[m.get('name', '?') for m in loaded],
        )

    return OllamaHealthResult(
        healthy=True,
        total_vram_mb=total_vram,
        loaded_vram_mb=loaded_vram_mb,
    )


# Canonical cloud-model detector lives in llm_config_manager (the leaf
# module for model-name utilities). Imported here so this module's
# health-check logic and the LLM-call layer share one implementation.
from app.services.llm_config_manager import is_cloud_model as _is_cloud_model


def _probe_cloud_proxy(
    model: str,
    timeout_s: float = 10.0,
) -> tuple[bool, str]:
    """Tiny round-trip probe of a cloud-proxied model.

    Returns (ok, message). Used to verify that even when the local
    Ollama runner is wedged on an oversized local model, cloud-proxied
    requests still flow through ollama serve to ollama.com. Single-
    token generate is cheap and finishes in 1-3 s when the cloud is
    healthy.
    """
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r = client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": "ok",
                    "stream": False,
                    "options": {"num_predict": 1},
                    "keep_alive": 0,
                },
            )
            r.raise_for_status()
            return True, f"cloud probe of {model!r} ok"
    except Exception as e:
        return False, f"cloud probe of {model!r} failed: {type(e).__name__}: {str(e)[:120]}"


def check_ollama_health_for_workload(
    active_model: Optional[str] = None,
    headroom_mb: int = 2048,
    timeout_s: float = 5.0,
) -> OllamaHealthResult:
    """Workload-aware variant of ``check_ollama_gpu_health``.

    Same strict VRAM check as the base function, EXCEPT when:
      - The base check says unhealthy due to a local model exceeding
        VRAM (the wedge signature), AND
      - The active workload model is cloud-proxied (``*-cloud``), AND
      - A small cloud-route probe succeeds.

    In that combination, the local wedge does NOT block this workload
    — cloud-proxied requests go through ollama serve out to
    ollama.com and don't compete for local GPU compute. Returning
    healthy=True lets cloud-only workflows (e.g. vaucda's
    ``gpt-oss:120b-cloud`` synthesis) keep running while a separate
    process's local-model wedge is dealt with on its own timeline.

    When ``active_model`` is None or a local model, behavior is
    identical to ``check_ollama_gpu_health``.
    """
    base = check_ollama_gpu_health(headroom_mb=headroom_mb, timeout_s=timeout_s)
    if base.healthy:
        return base
    # Local is wedged. Only relax if the workload is cloud-routed.
    if not _is_cloud_model(active_model):
        return base
    cloud_ok, probe_msg = _probe_cloud_proxy(active_model, timeout_s=10.0)
    if not cloud_ok:
        # Cloud is ALSO broken — return the original unhealthy verdict,
        # augmented with the cloud failure.
        return OllamaHealthResult(
            healthy=False,
            reason=(
                base.reason
                + f" Also: {probe_msg}. Cloud route is not usable as a workaround."
            ),
            total_vram_mb=base.total_vram_mb,
            loaded_vram_mb=base.loaded_vram_mb,
            problematic_models=base.problematic_models,
        )
    # Cloud is responsive — let the workload proceed despite the local
    # wedge. Surface a clear warning in the reason so this isn't silent.
    return OllamaHealthResult(
        healthy=True,
        reason=(
            f"Local Ollama is wedged ({'; '.join(base.problematic_models) or 'unknown'}) "
            f"but workload uses cloud-proxied model {active_model!r} and "
            f"the cloud route is responsive. Proceeding on cloud-only path. "
            "Local-model requests would still fail — fix the wedge before "
            "switching the workload back to a local model."
        ),
        total_vram_mb=base.total_vram_mb,
        loaded_vram_mb=base.loaded_vram_mb,
        problematic_models=base.problematic_models,
    )


class OllamaWedgedError(RuntimeError):
    """Raised when the pre-flight check finds Ollama in a wedged state.

    Carries the OllamaHealthResult so callers can include the structured
    details in API responses without re-running the check.
    """

    def __init__(self, result: OllamaHealthResult):
        self.result = result
        super().__init__(result.reason)


def assert_ollama_healthy(active_model: Optional[str] = None) -> None:
    """Raise OllamaWedgedError if Ollama / GPU state cannot serve a request.

    If ``active_model`` is provided and is cloud-proxied, the check
    uses the workload-aware variant — a local-model wedge is tolerated
    when the cloud route is verified responsive.
    """
    if active_model is not None:
        result = check_ollama_health_for_workload(active_model=active_model)
    else:
        result = check_ollama_gpu_health()
    if not result.healthy:
        raise OllamaWedgedError(result)
