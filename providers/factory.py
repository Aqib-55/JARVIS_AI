"""
Provider factory — creates AI model provider instances.

To add a new provider:
  1. Create a new module in providers/ (e.g. providers/openai.py).
  2. Implement BaseProvider.
  3. Add an entry to _PROVIDERS below.
"""

import logging

from providers.base import BaseProvider
from providers.gemini import GeminiProvider

logger = logging.getLogger(__name__)

# Registry of available providers
_PROVIDERS: dict[str, type[BaseProvider]] = {
    "gemini": GeminiProvider,
}


def get_provider(name: str = "gemini", **kwargs) -> BaseProvider:
    """
    Create and return an AI provider instance.

    Args:
        name: Provider name (e.g. "gemini").
        **kwargs: Extra arguments forwarded to the provider constructor.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    provider_class = _PROVIDERS.get(name.lower())
    if provider_class is None:
        available = ", ".join(_PROVIDERS.keys())
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")

    logger.info("Creating provider: %s", name)
    return provider_class(**kwargs)
