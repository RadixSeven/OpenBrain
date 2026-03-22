"""Tests for JSON→domain parsing functions."""

from __future__ import annotations

import pytest
import respx
from main import (
    _parse_metadata,
    _parse_scan_cache,
    _parse_tag_rule,
    _parse_thought,
    reclassify_thought,
)
from models import Config, ScanCache, ThoughtMetadata


class TestParseMetadata:
    def test_non_dict_returns_default(self) -> None:
        assert _parse_metadata("not a dict") == ThoughtMetadata()
        assert _parse_metadata(None) == ThoughtMetadata()
        assert _parse_metadata(42) == ThoughtMetadata()


class TestParseThought:
    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected dict"):
            _parse_thought("not a dict")


class TestParseTagRule:
    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected dict"):
            _parse_tag_rule(123)


class TestParseScanCache:
    def test_non_dict_returns_default(self) -> None:
        assert _parse_scan_cache("bad") == ScanCache()


class TestReclassifyDefensiveBranches:
    """Cover the type-narrowing raise KeyError branches in reclassify_thought."""

    @respx.mock
    def test_non_dict_response(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json=["not", "a", "dict"]
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_choices_not_list(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": "not a list"}
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_choices_empty(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": []}
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_first_choice_not_dict(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": ["not a dict"]}
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_message_not_dict(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": [{"message": "not a dict"}]}
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_content_not_str(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"choices": [{"message": {"content": 42}}]}
        )
        result = reclassify_thought("text", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]
