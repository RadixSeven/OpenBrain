"""Tests for API-calling functions using respx to mock httpx."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from main import (
    fetch_all_thoughts,
    fetch_tag_rules,
    get_current_prompt,
    reclassify_thought,
    sb_rpc,
    update_thought_metadata,
    verify_thought,
)

# ---------------------------------------------------------------------------
# sb_rpc
# ---------------------------------------------------------------------------


class TestSbRpc:
    @respx.mock
    def test_calls_correct_url(self, config: dict[str, str]) -> None:
        route = respx.post("https://test.supabase.co/rest/v1/rpc/my_func").respond(
            json={"ok": True}
        )
        result = sb_rpc(config, "my_func", {"key": "val"})
        assert result == {"ok": True}
        assert route.called

    @respx.mock
    def test_raises_on_error(self, config: dict[str, str]) -> None:
        respx.post("https://test.supabase.co/rest/v1/rpc/bad_func").respond(
            status_code=500
        )
        with pytest.raises(httpx.HTTPStatusError):
            sb_rpc(config, "bad_func")

    @respx.mock
    def test_default_empty_params(self, config: dict[str, str]) -> None:
        route = respx.post("https://test.supabase.co/rest/v1/rpc/no_params").respond(
            json=[]
        )
        sb_rpc(config, "no_params")
        assert route.called
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {}


# ---------------------------------------------------------------------------
# fetch_all_thoughts
# ---------------------------------------------------------------------------


class TestFetchAllThoughts:
    @respx.mock
    def test_single_batch(
        self,
        config: dict[str, str],
        sample_thoughts: list[dict[str, Any]],
    ) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(
            json=sample_thoughts
        )
        result = fetch_all_thoughts(config)
        assert len(result) == 3

    @respx.mock
    def test_empty_response(self, config: dict[str, str]) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(json=[])
        result = fetch_all_thoughts(config)
        assert result == []

    @respx.mock
    def test_multi_batch(self, config: dict[str, str]) -> None:
        """When the first batch is full-sized, pagination continues."""
        full_batch = [{"id": f"id-{i}", "content": f"t{i}"} for i in range(1000)]
        partial_batch = [{"id": "id-last", "content": "last"}]
        route = respx.get("https://test.supabase.co/rest/v1/thoughts").mock(
            side_effect=[
                httpx.Response(200, json=full_batch),
                httpx.Response(200, json=partial_batch),
            ]
        )
        result = fetch_all_thoughts(config)
        assert len(result) == 1001
        assert route.call_count == 2

    @respx.mock
    def test_raises_on_http_error(self, config: dict[str, str]) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            fetch_all_thoughts(config)


# ---------------------------------------------------------------------------
# get_current_prompt
# ---------------------------------------------------------------------------


class TestGetCurrentPrompt:
    @respx.mock
    def test_returns_first_from_list(
        self,
        config: dict[str, str],
        sample_prompt_info: dict[str, Any],
    ) -> None:
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[sample_prompt_info]
        )
        result = get_current_prompt(config)
        assert result["model_string"] == "openai/gpt-5.2"

    @respx.mock
    def test_returns_dict_directly(self, config: dict[str, str]) -> None:
        data = {"model_string": "test-model", "prompt_template_text": "..."}
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=data
        )
        result = get_current_prompt(config)
        assert result["model_string"] == "test-model"

    @respx.mock
    def test_empty_list_returns_empty(self, config: dict[str, str]) -> None:
        """Edge case: RPC returns empty list (no prompt configured)."""
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[]
        )
        result = get_current_prompt(config)
        assert isinstance(result, list)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# fetch_tag_rules
# ---------------------------------------------------------------------------


class TestFetchTagRules:
    @respx.mock
    def test_returns_rules(
        self,
        config: dict[str, str],
        sample_tag_rules: list[dict[str, str]],
    ) -> None:
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(
            json=sample_tag_rules
        )
        result = fetch_tag_rules(config)
        assert len(result) == 2
        assert result[0]["if_present"] == "romantic_or_sexual_relationship"

    @respx.mock
    def test_raises_on_error(self, config: dict[str, str]) -> None:
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            fetch_tag_rules(config)


# ---------------------------------------------------------------------------
# reclassify_thought
# ---------------------------------------------------------------------------


class TestReclassifyThought:
    @respx.mock
    def test_successful_classification(self, config: dict[str, str]) -> None:
        meta = {"visibility": ["sfw", "work"], "type": "task"}
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [{"message": {"content": json.dumps(meta)}}],
            }
        )
        result = reclassify_thought("Review the PR", "prompt...", "gpt-5", config)
        assert result == meta

    @respx.mock
    def test_malformed_response_returns_fallback(self, config: dict[str, str]) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [{"message": {"content": "not json"}}],
            }
        )
        result = reclassify_thought("test", "prompt", "model", config)
        assert result["visibility"] == ["uncategorized"]

    @respx.mock
    def test_missing_keys_returns_fallback(self, config: dict[str, str]) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"unexpected": "shape"}
        )
        result = reclassify_thought("test", "prompt", "model", config)
        assert result["visibility"] == ["uncategorized"]

    @respx.mock
    def test_http_error_raises(self, config: dict[str, str]) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            status_code=429
        )
        with pytest.raises(httpx.HTTPStatusError):
            reclassify_thought("test", "prompt", "model", config)


# ---------------------------------------------------------------------------
# update_thought_metadata
# ---------------------------------------------------------------------------


class TestUpdateThoughtMetadata:
    @respx.mock
    def test_sends_patch(self, config: dict[str, str]) -> None:
        route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        update_thought_metadata("abc-123", {"visibility": ["sfw"]}, config)
        assert route.called
        req = route.calls[0].request
        body = json.loads(req.content)
        assert body["metadata"] == {"visibility": ["sfw"]}
        assert "updated_at" in body

    @respx.mock
    def test_raises_on_error(self, config: dict[str, str]) -> None:
        respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=500
        )
        with pytest.raises(httpx.HTTPStatusError):
            update_thought_metadata("abc", {}, config)


# ---------------------------------------------------------------------------
# verify_thought
# ---------------------------------------------------------------------------


class TestVerifyThought:
    @respx.mock
    def test_sends_patch_with_verified_timestamp(self, config: dict[str, str]) -> None:
        route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        verify_thought("abc-123", {"visibility": ["personal"]}, config)
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert "visibility_verified_by_human_at" in body
        assert body["metadata"] == {"visibility": ["personal"]}
        assert body["updated_at"] == body["visibility_verified_by_human_at"]

    @respx.mock
    def test_raises_on_error(self, config: dict[str, str]) -> None:
        respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=403
        )
        with pytest.raises(httpx.HTTPStatusError):
            verify_thought("abc", {}, config)
