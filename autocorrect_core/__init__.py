"""
Shared core for the Autocorrect desktop app and server.

    from autocorrect_core import build_chain, Action

    chain = build_chain([{"type": "anthropic"}, {"type": "openrouter", "model": "..."}])
    chain.transform("helo wrld", Action.fix())

Providers are plain dicts, so switching method is a config change, not a code change.
See providers.py for the available types.
"""

from .prompts import Action, InvalidRequest
from .providers import PROVIDER_TYPES, ProviderChain, ProviderError, build_chain

__all__ = ["Action", "InvalidRequest", "PROVIDER_TYPES", "ProviderChain", "ProviderError", "build_chain"]
