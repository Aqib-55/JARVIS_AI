"""
Provider factory — creates the active AI model provider instance.

JARVIS uses Ollama as its sole local AI provider.

To add another local provider in future:
  1. Create providers/newprovider.py implementing BaseProvider.
  2. Add an entry to _PROVIDERS below.
  3. Set AI_PROVIDER=newprovider in .env.
"""

import logging
import os

from config.settings import settings
from providers.base import BaseProvider
from providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)

# Registry of available providers — Ollama is the only active provider
_PROVIDERS: dict[str, type[BaseProvider]] = {
    "ollama": OllamaProvider,
}


def _is_local_only() -> bool:
    """Read LOCAL_AI_ONLY from environment at call-time (allows test monkeypatching)."""
    env_val = os.environ.get("LOCAL_AI_ONLY", "").strip().lower()
    if env_val in ("false", "0", "no"):
        return False
    if env_val in ("true", "1", "yes"):
        return True
    # Fall back to settings singleton
    return settings.LOCAL_AI_ONLY


def get_provider(name: str = "ollama", **kwargs) -> BaseProvider:
    """
    Create and return an AI provider instance.

    Args:
        name: Provider name. Must be 'ollama'. Any other value raises ValueError.
        **kwargs: Extra arguments forwarded to the provider constructor.

    Raises:
        ValueError: If the provider name is not recognised.
        RuntimeError: If LOCAL_AI_ONLY=true and a non-local provider is requested.
    """
    provider_name = name.lower().strip()

    # LOCAL_AI_ONLY guard — read live from env so tests can monkeypatch
    if _is_local_only() and provider_name != "ollama":
        raise RuntimeError(
            f"LOCAL_AI_ONLY=true but provider '{provider_name}' was requested. "
            "Only 'ollama' is permitted in local-only mode."
        )

    provider_class = _PROVIDERS.get(provider_name)
    if provider_class is None:
        available = ", ".join(_PROVIDERS.keys())
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Available providers: {available}. "
            "Set AI_PROVIDER=ollama in your .env file."
        )

    logger.info("Creating provider: %s", provider_name)
    return provider_class(**kwargs)
