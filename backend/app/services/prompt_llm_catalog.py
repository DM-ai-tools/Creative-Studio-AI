"""OpenRouter text LLMs for image variant prompt generation (Generate AI for all)."""

from __future__ import annotations

from app.core.config import settings
from app.schemas.generation import GenerationModelOption

# (provider, label, openrouter slug)
_PROMPT_LLM_SPECS: list[tuple[str, str, str]] = [
    ("anthropic", "Claude Sonnet 4.6", "anthropic/claude-sonnet-4.6"),
    ("anthropic", "Claude Haiku 4.5", "anthropic/claude-haiku-4.5"),
    ("anthropic", "Claude Opus 4", "anthropic/claude-opus-4"),
    ("openai", "GPT-4o", "openai/gpt-4o"),
    ("openai", "GPT-4o mini", "openai/gpt-4o-mini"),
    ("openai", "GPT-4.1", "openai/gpt-4.1"),
    ("openai", "o3-mini", "openai/o3-mini"),
    ("google", "Gemini 2.5 Flash", "google/gemini-2.5-flash"),
    ("google", "Gemini 2.5 Pro", "google/gemini-2.5-pro"),
    ("google", "Gemini 3 Flash Preview", "google/gemini-3-flash-preview"),
    ("x-ai", "Grok 3", "x-ai/grok-3"),
    ("x-ai", "Grok 3 mini", "x-ai/grok-3-mini"),
    ("x-ai", "Grok 4", "x-ai/grok-4"),
]

_ALLOWED_SLUGS: frozenset[str] = frozenset(slug for _, _, slug in _PROMPT_LLM_SPECS)


def default_prompt_llm_model() -> str:
    return (
        (settings.OPENROUTER_MODEL_CLAUDE_SCRIPT or "").strip()
        or "anthropic/claude-sonnet-4.6"
    )


def prompt_llm_catalog_options() -> list[GenerationModelOption]:
    default_slug = default_prompt_llm_model()
    out: list[GenerationModelOption] = []
    seen: set[str] = set()
    for provider, label, slug in _PROMPT_LLM_SPECS:
        if slug in seen:
            continue
        seen.add(slug)
        display = label
        if slug == default_slug:
            display = f"{label} (default)"
        out.append(
            GenerationModelOption(
                id=slug,
                label=display,
                provider_model=slug,
                modality="prompt_llm",
                provider=provider,
            )
        )
    if default_slug not in seen:
        out.insert(
            0,
            GenerationModelOption(
                id=default_slug,
                label=f"{default_slug} (default)",
                provider_model=default_slug,
                modality="prompt_llm",
                provider="other",
            ),
        )
    return out


def resolve_prompt_llm_model(requested: str | None) -> str:
    """Return an allowed OpenRouter slug; fall back to env default."""
    slug = (requested or "").strip()
    if slug and slug in _ALLOWED_SLUGS:
        return slug
    env_default = default_prompt_llm_model()
    if env_default in _ALLOWED_SLUGS:
        return env_default
    return "anthropic/claude-sonnet-4.6"
