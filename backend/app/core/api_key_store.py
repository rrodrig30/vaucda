"""System-wide encrypted store for LLM provider API keys.

The note-generation pipeline consumes provider keys GLOBALLY via
``settings.ANTHROPIC_API_KEY`` / ``settings.OPENAI_API_KEY`` (there is no
per-request user context deep in the pipeline), so keys entered through the
Settings UI are stored system-wide, encrypted at rest, and applied to the live
``settings`` object — both at startup and immediately on save.

At rest: a Fernet-encrypted JSON blob next to the SQLite DB
(``backend/data/llm_api_keys.enc``). Never logged, never returned to the client
(only a boolean "configured" flag and a masked last-4 hint are exposed).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from cryptography.fernet import Fernet

from app.config import settings

logger = logging.getLogger(__name__)

# One key file per deployment, co-located with the SQLite DB.
_KEY_FILE = Path(__file__).resolve().parents[2] / "data" / "llm_api_keys.enc"

# Providers whose keys live here (Ollama is local / keyless).
PROVIDERS = ("anthropic", "openai")

# Which `settings` attribute each provider's key populates.
_SETTINGS_ATTR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# The deployment's original .env-provided keys, captured at import BEFORE any
# UI-managed override is applied. Clearing a UI key reverts to this value rather
# than nulling a key the deployment configured via environment.
_ENV_KEYS = {p: getattr(settings, _SETTINGS_ATTR[p], None) for p in PROVIDERS}


def _fernet() -> Fernet:
    """Fernet built from OPENEVIDENCE_ENCRYPTION_KEY (already a valid Fernet key
    used for credential encryption); falls back to a key derived from
    JWT_SECRET_KEY so encryption is always available."""
    raw = settings.OPENEVIDENCE_ENCRYPTION_KEY
    if raw:
        try:
            return Fernet(raw.encode() if isinstance(raw, str) else raw)
        except Exception:  # not a valid Fernet key — derive one below
            logger.warning("OPENEVIDENCE_ENCRYPTION_KEY is not a valid Fernet key; "
                           "deriving key-store cipher from JWT_SECRET_KEY")
    derived = base64.urlsafe_b64encode(
        hashlib.sha256((settings.JWT_SECRET_KEY or "vaucda").encode()).digest())
    return Fernet(derived)


def load_keys() -> Dict[str, str]:
    """Decrypt and return stored keys, e.g. ``{"anthropic": "sk-...", ...}``.
    Returns an empty dict if nothing is stored or decryption fails."""
    if not _KEY_FILE.exists():
        return {}
    try:
        data = _fernet().decrypt(_KEY_FILE.read_bytes())
        keys = json.loads(data.decode())
        return {k: v for k, v in keys.items() if k in PROVIDERS and v}
    except Exception as exc:  # corrupt / wrong key — never crash startup
        logger.error("Failed to read LLM key store: %s", exc)
        return {}


def _write_keys(keys: Dict[str, str]) -> None:
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = _fernet().encrypt(json.dumps(keys).encode())
    # Write atomically and restrict permissions.
    tmp = _KEY_FILE.with_suffix(".enc.tmp")
    tmp.write_bytes(payload)
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(_KEY_FILE)


def set_key(provider: str, key: Optional[str]) -> None:
    """Persist (or, when key is empty/None, remove) a provider's API key, then
    apply the change to the live ``settings`` object so it takes effect at once."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}")
    keys = load_keys()
    key = (key or "").strip()
    if key:
        keys[provider] = key
    else:
        keys.pop(provider, None)
    _write_keys(keys)
    # Reflect immediately into runtime settings; clearing reverts to the env key.
    setattr(settings, _SETTINGS_ATTR[provider], key or _ENV_KEYS.get(provider))
    logger.info("LLM API key for %s %s", provider, "set" if key else "cleared")


def apply_to_settings() -> None:
    """Load stored keys into the live ``settings`` object. Stored keys (managed
    through the UI) take precedence over env defaults. Call once at startup."""
    for provider, key in load_keys().items():
        setattr(settings, _SETTINGS_ATTR[provider], key)
    if load_keys():
        logger.info("Applied stored LLM API keys: %s",
                    ", ".join(sorted(load_keys().keys())))


def key_hint(provider: str) -> Optional[str]:
    """Masked hint (last 4 chars) for display, or None if not configured. Reads
    the live setting so an env-provided key also shows as configured."""
    val = getattr(settings, _SETTINGS_ATTR.get(provider, ""), None)
    if not val:
        return None
    tail = val[-4:] if len(val) >= 4 else val
    return f"••••{tail}"
