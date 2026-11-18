"""
AI providers. Each provider is configured by a dict:

    {"type": "anthropic",  "model": "claude-opus-5-5", "effort": "low", "api_key": "..."}
    {"type": "openrouter", "model": "<id from openrouter.ai/models>", "api_key": "..."}
    {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "model": "...", "api_key": "..."}
    {"type": "server", "url": "https://your-server", "access_code": "ABCD-EFGH-JKMN"}

"api_key" may be omitted (the provider's standard environment variable is used) or
written as "env:SOME_VAR". A list of providers forms a chain: if one fails
(outage, rate limit, bad key), the next one is tried.

To add a new kind of provider: subclass Provider and register it in PROVIDER_TYPES.
"""

import json
import os
import urllib.error
import urllib.request

from .prompts import SYSTEM_PROMPT, Action, user_prompt


class ProviderError(Exception):
    """A failure of one provider. `retryable` is False for errors that another provider can't fix."""

    def __init__(self, message: str, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


def _resolve_key(cfg: dict, default_env: str | None) -> str:
    key = cfg.get("api_key") or ""
    if key.startswith("env:"):
        key = os.environ.get(key[4:], "")
    if not key and default_env:
        key = os.environ.get(default_env, "")
    return key


def _post_json(url: str, body: dict, headers: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ProviderError(f"HTTP {e.code}", status=e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderError("unreachable") from e
    except ValueError as e:
        raise ProviderError("bad response") from e


class Provider:
    type = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    @property
    def name(self) -> str:
        return f"{self.type}:{self.cfg.get('model', '')}".rstrip(":")

    def transform(self, text: str, action: Action) -> str:
        raise NotImplementedError


class AnthropicProvider(Provider):
    type = "anthropic"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        import anthropic  # only needed when this provider is used

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=_resolve_key(cfg, "ANTHROPIC_API_KEY") or None)
        self.cfg.setdefault("model", "claude-opus-5-5")

    def transform(self, text: str, action: Action) -> str:
        a = self._anthropic
        try:
            response = self._client.beta.messages.create(
                model=self.cfg["model"],
                max_tokens=16000,
                output_config={"effort": self.cfg.get("effort", "low")},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt(text, action)}],
            )
        except a.APIStatusError as e:
            raise ProviderError(f"HTTP {e.status_code}", status=e.status_code) from e
        except a.APIConnectionError as e:
            raise ProviderError("unreachable") from e
        if response.stop_reason == "refusal":
            raise ProviderError("refused")
        return "".join(b.text for b in response.content if b.type == "text")


class OpenAICompatibleProvider(Provider):
    """Any service with an OpenAI-style /chat/completions endpoint (OpenAI, Gemini, Groq, Ollama, ...)."""

    type = "openai_compatible"
    default_base_url = "https://api.openai.com/v1"
    default_env = "OPENAI_API_KEY"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        if not cfg.get("model"):
            raise ValueError(f"provider '{self.type}' needs a \"model\"")
        self.base_url = (cfg.get("base_url") or self.default_base_url).rstrip("/")
        self.api_key = _resolve_key(cfg, self.default_env)

    def transform(self, text: str, action: Action) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = _post_json(
            f"{self.base_url}/chat/completions",
            {
                "model": self.cfg["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(text, action)},
                ],
            },
            headers,
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError("bad response") from e


class OpenRouterProvider(OpenAICompatibleProvider):
    type = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"
    default_env = "OPENROUTER_API_KEY"


class ServerProvider(Provider):
    """Your own Autocorrect server (customers use an access code, no AI key)."""

    type = "server"
    ERRORS = {
        401: ("Invalid access code.", False),
        429: ("Daily limit reached - try again tomorrow.", False),
        413: ("The text is too long.", False),
        503: ("The server is busy - try again in a moment.", True),
    }

    @property
    def name(self) -> str:
        return f"server:{self.cfg.get('url', '')}"

    def transform(self, text: str, action: Action) -> str:
        url = (self.cfg.get("url") or "").rstrip("/")
        if not url or not self.cfg.get("access_code"):
            raise ProviderError("server url / access code not set", retryable=False)
        try:
            data = _post_json(
                f"{url}/v1/transform",
                {"text": text, **action.to_dict()},
                {"Authorization": f"Bearer {self.cfg['access_code'].strip()}"},
            )
        except ProviderError as e:
            if e.status in self.ERRORS:
                msg, retryable = self.ERRORS[e.status]
                raise ProviderError(msg, retryable=retryable, status=e.status) from e
            raise
        return data.get("result", "")


PROVIDER_TYPES: dict[str, type[Provider]] = {
    p.type: p for p in (AnthropicProvider, OpenRouterProvider, OpenAICompatibleProvider, ServerProvider)
}


class ProviderChain:
    """Tries each provider in order until one succeeds."""

    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError("no AI providers configured")
        self.providers = providers

    def transform(self, text: str, action: Action, log=None) -> str:
        last: ProviderError | None = None
        for provider in self.providers:
            try:
                result = provider.transform(text, action).strip("\n")
                if not result:
                    raise ProviderError("empty response")
                return result
            except ProviderError as e:
                last = e
                if log:
                    log(f"{provider.name} failed: {e}")
                if not e.retryable:
                    break
        raise last  # type: ignore[misc]

    def describe(self) -> str:
        return " -> ".join(p.name for p in self.providers)


def build_chain(configs: list[dict] | dict) -> ProviderChain:
    if isinstance(configs, dict):
        configs = [configs]
    providers = []
    for cfg in configs:
        kind = cfg.get("type")
        if kind not in PROVIDER_TYPES:
            raise ValueError(f"unknown provider type {kind!r}; choose one of {', '.join(PROVIDER_TYPES)}")
        providers.append(PROVIDER_TYPES[kind](dict(cfg)))
    return ProviderChain(providers)
