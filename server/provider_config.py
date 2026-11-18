"""Loads the server's AI provider chain and reloads it when providers.json changes."""

import json
import os
import threading

from db import DATA_DIR

from autocorrect_core import ProviderChain, build_chain

PROVIDERS_FILE = DATA_DIR / "providers.json"

# Model for each provider name when AI_PROVIDERS is given as a simple comma list.
_NAME_DEFAULTS = {
    "anthropic": lambda: {"type": "anthropic", "model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
                          "effort": os.environ.get("ANTHROPIC_EFFORT", "low")},
    "openrouter": lambda: {"type": "openrouter", "model": os.environ.get("OPENROUTER_MODEL", "")},
    "openai": lambda: {"type": "openai_compatible", "model": os.environ.get("OPENAI_MODEL", ""),
                       "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")},
}

_lock = threading.Lock()
_cache: tuple[float | None, ProviderChain] | None = None


def parse_spec(spec: str) -> list[dict]:
    """Accepts a JSON list/object, or a comma list of names like 'openrouter,anthropic'."""
    spec = spec.strip()
    if spec.startswith("[") or spec.startswith("{"):
        data = json.loads(spec)
        return data if isinstance(data, list) else [data]
    configs = []
    for item in (n.strip() for n in spec.split(",") if n.strip()):
        name, _, model = item.partition(":")  # optional "name:model", e.g. "openrouter:some/model"
        name = name.lower()
        if name not in _NAME_DEFAULTS:
            raise ValueError(f"unknown provider {name!r}; use {', '.join(_NAME_DEFAULTS)} or a JSON config")
        cfg = _NAME_DEFAULTS[name]()
        if model:
            cfg["model"] = model
        configs.append(cfg)
    return configs


def configured_specs() -> list[dict]:
    if PROVIDERS_FILE.exists():
        return json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    return parse_spec(os.environ.get("AI_PROVIDERS") or os.environ.get("PROVIDER") or "anthropic")


def current_chain() -> ProviderChain:
    global _cache
    mtime = PROVIDERS_FILE.stat().st_mtime if PROVIDERS_FILE.exists() else None
    with _lock:
        if _cache is None or _cache[0] != mtime:
            _cache = (mtime, build_chain(configured_specs()))
        return _cache[1]


def save(configs: list[dict]):
    build_chain(configs)  # validate before saving
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROVIDERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(configs, indent=2), encoding="utf-8")
    tmp.replace(PROVIDERS_FILE)


def reset():
    PROVIDERS_FILE.unlink(missing_ok=True)
