"""Shared fixtures for review-visibility tests."""

from __future__ import annotations

import pytest
from models import Config, PromptInfo, TagRule, Thought, ThoughtMetadata

# Proxy env vars that can cause httpx to try SOCKS/HTTP proxy transports,
# breaking respx mocking. Remove them for all tests.
_PROXY_VARS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
]


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove proxy env vars so httpx doesn't try to use a SOCKS proxy."""
    for var in _PROXY_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def config() -> Config:
    """Fake Supabase / OpenRouter config for tests."""
    return Config(
        supabase_url="https://test.supabase.co",
        supabase_key="test-service-role-key",
        openrouter_api_key="test-openrouter-key",
    )


@pytest.fixture
def sample_thought() -> Thought:
    """A single thought record as returned by Supabase."""
    return Thought(
        id="aaaa-bbbb-cccc-dddd",
        content="The weather is nice today",
        metadata=ThoughtMetadata(
            type="observation",
            topics=["weather"],
            visibility=["sfw"],
        ),
        visibility_verified_by_human_at=None,
        created_at="2026-03-16T12:00:00Z",
        submitted_by="user",
    )


@pytest.fixture
def sample_thoughts() -> list[Thought]:
    """Multiple thought records."""
    return [
        Thought(
            id="id-1",
            content="First thought",
            metadata=ThoughtMetadata(visibility=["sfw"], type="observation"),
            visibility_verified_by_human_at=None,
            created_at="2026-03-16T12:00:00Z",
            submitted_by="user",
        ),
        Thought(
            id="id-2",
            content="Kind Truth is a great name",
            metadata=ThoughtMetadata(visibility=["personal"], type="observation"),
            visibility_verified_by_human_at="2026-03-15T10:00:00Z",
            created_at="2026-03-15T10:00:00Z",
            submitted_by="mcp claude",
        ),
        Thought(
            id="id-3",
            content="Review the PR for the API",
            metadata=ThoughtMetadata(visibility=["sfw", "work"], type="task"),
            visibility_verified_by_human_at=None,
            created_at="2026-03-14T08:00:00Z",
            submitted_by="user",
        ),
    ]


@pytest.fixture
def sample_tag_rules() -> list[TagRule]:
    """Tag rules as returned by Supabase."""
    return [
        TagRule(if_present="romantic_or_sexual_relationship", remove_tag="sfw"),
        TagRule(if_present="lgbtq_identity", remove_tag="sfw"),
    ]


@pytest.fixture
def sample_prompt_info() -> PromptInfo:
    """Prompt info as returned by get_current_prompt RPC."""
    return PromptInfo(
        prompt_template_text="Extract metadata...",
        model_string="openai/gpt-5.2",
        prompt_template_id="a0a0a0a0-b1b1-c2c2-d3d3-e4e4e4e4e4e4",
    )
