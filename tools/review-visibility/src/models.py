"""Type definitions for the review-visibility tool.

Domain types are dataclasses; JSON types use recursive type aliases.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# JSON value types (recursive definition)
# ---------------------------------------------------------------------------

type JsonValue = None | bool | int | float | str | list[JsonValue] | JsonObject
type JsonObject = dict[str, JsonValue]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Connection settings for Supabase and OpenRouter."""

    supabase_url: str
    supabase_key: str
    openrouter_api_key: str
    openrouter_base: str = "https://openrouter.ai/api/v1"


@dataclass
class TagRule:
    """A deterministic tag-removal rule."""

    if_present: str
    remove_tag: str


@dataclass
class ThoughtMetadata:
    """Metadata attached to a thought (the JSON blob stored in the DB)."""

    visibility: list[str] = field(default_factory=list)
    type: str = "observation"
    topics: list[str] = field(default_factory=list)


@dataclass
class Thought:
    """A thought record as returned by Supabase."""

    id: str
    content: str
    metadata: ThoughtMetadata
    visibility_verified_by_human_at: str | None = None
    created_at: str = ""
    submitted_by: str = ""


@dataclass
class PromptInfo:
    """Current categorization prompt from the DB."""

    prompt_template_text: str = ""
    model_string: str = ""
    prompt_template_id: str = ""


@dataclass
class ScanCache:
    """On-disk cache for scan results."""

    scanned: dict[str, ThoughtMetadata] = field(default_factory=dict)
    prompt_template_id: str | None = None
