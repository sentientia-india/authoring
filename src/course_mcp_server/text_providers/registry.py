from __future__ import annotations

from dataclasses import replace

from ..security import RequestContext
from .anthropic import AnthropicConfig, AnthropicTextProvider
from .base import TextProvider, TextProviderError, resolve_api_key
from .deepseek import DeepSeekConfig, DeepSeekTextProvider
from .gemini import GeminiConfig, GeminiTextProvider
from .openai import OpenAIConfig, OpenAITextProvider
from .openrouter import OpenRouterConfig, OpenRouterTextProvider

# Synthetic identity used only when get_text_provider() is called without its own
# RequestContext (mirrors openrouter.py's _SYSTEM_REQUEST_CONTEXT /
# generic_openai_compatible.py's same-named constant). resolve_api_key() accepts
# request_context purely so an audit-event write at the call site can correlate "who this
# key resolution was for" -- it performs no I/O with it and does not gate the key-resolution
# outcome on it, so a placeholder is safe here.
_SYSTEM_REQUEST_CONTEXT = RequestContext(tenant_id="system", user_id="system")

# provider_id values this registry accepts, kept in one place so callers (schemas.py's
# Literal, tests, docs) can be checked against it rather than re-listing the strings.
KNOWN_PROVIDER_IDS = (
    "openrouter",
    "deepseek",
    "openai",
    "anthropic",
    "gemini",
    "openai_compatible",
)


def _env_backed_provider(
    provider_id: str,
    *,
    api_key: str | None,
    model: str | None,
) -> TextProvider:
    """Build one of the from_env()-only adapters (deepseek/openai/anthropic/gemini), applying
    an optional per-request api_key/model override on top of the env-resolved config.

    None of these adapters expose an api_key constructor kwarg the way OpenRouterTextProvider
    does (see openrouter.py's resolve_api_key-based constructor) -- they only have `from_env()`.
    So the override is applied here, once, by replacing fields on the env-resolved config
    dataclass before constructing the provider, rather than duplicating that logic per adapter.

    The api_key is resolved via resolve_api_key() (same helper OpenRouterTextProvider and
    GenericOpenAICompatibleProvider use) rather than a plain None-check, so every provider this
    factory builds gets a `key_source` attribute ("env" vs "request") like those two already do
    -- these four adapter classes don't set that attribute themselves, so it's assigned onto the
    constructed instance here. When api_key is None this resolves to the exact same env-var
    value from_env() would have used, so the effective api_key is unchanged either way.
    """
    config_cls, provider_cls = {
        "deepseek": (DeepSeekConfig, DeepSeekTextProvider),
        "openai": (OpenAIConfig, OpenAITextProvider),
        "anthropic": (AnthropicConfig, AnthropicTextProvider),
        "gemini": (GeminiConfig, GeminiTextProvider),
    }[provider_id]

    config = config_cls.from_env()
    resolved_key, key_source = resolve_api_key(
        provider_id,
        _SYSTEM_REQUEST_CONTEXT,
        request_key=api_key,
    )
    overrides = {"api_key": resolved_key}
    if model is not None:
        overrides["model"] = model
    config = replace(config, **overrides)
    provider = provider_cls(config)
    provider.key_source = key_source
    return provider


def get_text_provider(
    provider_id: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> TextProvider:
    """Factory: build the right TextProvider adapter for `provider_id`.

    `api_key`/`base_url`/`model` are optional per-request overrides (e.g. a caller's
    bring-your-own-key/model for that single request) layered on top of each adapter's
    normal env-resolved defaults -- see each adapter's `from_env()` for what "normal"
    means. `base_url` and `model` are both REQUIRED when provider_id == "openai_compatible"
    since that adapter has no fixed default endpoint or model to fall back to.

    Raises TextProviderError for an unknown provider_id, or for "openai_compatible" missing
    either base_url or model.
    """
    if provider_id == "openrouter":
        config = OpenRouterConfig.from_env()
        if model is not None:
            config = replace(config, model=model)
        # api_key is passed as the constructor kwarg (not folded into `config` here) so it goes
        # through OpenRouterTextProvider's own resolve_api_key()-based resolution -- that keeps
        # the "explicit request key never falls back to reading *_API_KEY from the environment"
        # guarantee OpenRouterTextProvider already provides (see its docstring/tests) intact.
        return OpenRouterTextProvider(config, api_key=api_key)

    if provider_id in ("deepseek", "openai", "anthropic", "gemini"):
        return _env_backed_provider(provider_id, api_key=api_key, model=model)

    if provider_id == "openai_compatible":
        if not base_url or not model:
            raise TextProviderError(
                "openai_compatible requires both text_provider_base_url and text_provider_model"
            )
        # Imported lazily/defensively: this adapter module (generic_openai_compatible.py) may
        # land slightly after this registry within the same development cycle -- see this
        # module's docstring/task notes. Importing it only inside this branch means the rest of
        # get_text_provider() (and this module's import at all) keeps working even if that file
        # is briefly missing.
        try:
            from .generic_openai_compatible import GenericOpenAICompatibleProvider
        except ImportError as exc:  # pragma: no cover - only hit while the adapter is missing
            raise TextProviderError(
                "openai_compatible provider adapter (generic_openai_compatible.py) is not available"
            ) from exc
        return GenericOpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model)

    raise TextProviderError(
        f"Unknown text provider_id: {provider_id!r} (expected one of {KNOWN_PROVIDER_IDS})"
    )
