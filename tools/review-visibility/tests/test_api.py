"""Tests for API-calling functions using respx to mock httpx."""

from __future__ import annotations

import json

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
from models import Config, ThoughtMetadata

# ---------------------------------------------------------------------------
# sb_rpc
# ---------------------------------------------------------------------------


class TestSbRpc:
    @respx.mock
    def test_calls_correct_url(self, config: Config) -> None:
        route = respx.post("https://test.supabase.co/rest/v1/rpc/my_func").respond(
            json={"ok": True}
        )
        result = sb_rpc(config, "my_func", {"key": "val"})
        assert result == {"ok": True}
        assert route.called

    @respx.mock
    def test_raises_on_error(self, config: Config) -> None:
        respx.post("https://test.supabase.co/rest/v1/rpc/bad_func").respond(
            status_code=500
        )
        with pytest.raises(httpx.HTTPStatusError):
            sb_rpc(config, "bad_func")

    @respx.mock
    def test_default_empty_params(self, config: Config) -> None:
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
    def test_single_batch(self, config: Config) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(
            json=[
                {
                    "id": "id-1",
                    "content": "First thought",
                    "metadata": {"visibility": ["sfw"], "type": "observation"},
                    "visibility_verified_by_human_at": None,
                    "created_at": "2026-03-16T12:00:00Z",
                    "submitted_by": "user",
                },
                {
                    "id": "id-2",
                    "content": "Second thought",
                    "metadata": {"visibility": ["personal"], "type": "observation"},
                    "visibility_verified_by_human_at": None,
                    "created_at": "2026-03-15T10:00:00Z",
                    "submitted_by": "user",
                },
            ]
        )
        result = fetch_all_thoughts(config)
        assert len(result) == 2
        assert result[0].id == "id-1"
        assert result[0].metadata.visibility == ["sfw"]

    @respx.mock
    def test_empty_response(self, config: Config) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(json=[])
        result = fetch_all_thoughts(config)
        assert result == []

    @respx.mock
    def test_multi_batch(self, config: Config) -> None:
        """When the first batch is full-sized, pagination continues."""
        full_batch = [
            {"id": f"id-{i}", "content": f"t{i}", "metadata": {}} for i in range(1000)
        ]
        partial_batch = [{"id": "id-last", "content": "last", "metadata": {}}]
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
    def test_raises_on_http_error(self, config: Config) -> None:
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            fetch_all_thoughts(config)


# ---------------------------------------------------------------------------
# get_current_prompt
# ---------------------------------------------------------------------------


class TestGetCurrentPrompt:
    @respx.mock
    def test_returns_first_from_list(self, config: Config) -> None:
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[
                {
                    "prompt_template_text": "Extract metadata...",
                    "model_string": "openai/gpt-5.2",
                    "prompt_template_id": "a0a0a0a0",
                }
            ]
        )
        result = get_current_prompt(config)
        assert result.model_string == "openai/gpt-5.2"

    @respx.mock
    def test_returns_dict_directly(self, config: Config) -> None:
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json={"model_string": "test-model", "prompt_template_text": "..."}
        )
        result = get_current_prompt(config)
        assert result.model_string == "test-model"

    @respx.mock
    def test_empty_list_returns_empty(self, config: Config) -> None:
        """Edge case: RPC returns empty list (no prompt configured)."""
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[]
        )
        result = get_current_prompt(config)
        assert result.model_string == ""


# ---------------------------------------------------------------------------
# fetch_tag_rules
# ---------------------------------------------------------------------------


class TestFetchTagRules:
    @respx.mock
    def test_returns_rules(self, config: Config) -> None:
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(
            json=[
                {"if_present": "romantic_or_sexual_relationship", "remove_tag": "sfw"},
                {"if_present": "lgbtq_identity", "remove_tag": "sfw"},
            ]
        )
        result = fetch_tag_rules(config)
        assert len(result) == 2
        assert result[0].if_present == "romantic_or_sexual_relationship"

    @respx.mock
    def test_raises_on_error(self, config: Config) -> None:
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            fetch_tag_rules(config)


# ---------------------------------------------------------------------------
# reclassify_thought
# ---------------------------------------------------------------------------


class TestReclassifyThought:
    @respx.mock
    def test_successful_classification(self, config: Config) -> None:
        meta = {"visibility": ["sfw", "work"], "type": "task"}
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [{"message": {"content": json.dumps(meta)}}],
            }
        )
        result = reclassify_thought("Review the PR", "prompt...", "gpt-5", config)
        assert result.visibility == ["sfw", "work"]
        assert result.type == "task"

    @respx.mock
    def test_malformed_response_returns_fallback(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [{"message": {"content": "not json"}}],
            }
        )
        result = reclassify_thought("test", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_missing_keys_returns_fallback(self, config: Config) -> None:
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={"unexpected": "shape"}
        )
        result = reclassify_thought("test", "prompt", "model", config)
        assert result.visibility == ["uncategorized"]

    @respx.mock
    def test_http_error_raises(self, config: Config) -> None:
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
    def test_sends_patch(self, config: Config) -> None:
        route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        update_thought_metadata("abc-123", ThoughtMetadata(visibility=["sfw"]), config)
        assert route.called
        req = route.calls[0].request
        body = json.loads(req.content)
        assert body["metadata"] == {
            "visibility": ["sfw"],
            "type": "observation",
            "topics": [],
        }
        assert "updated_at" in body

    @respx.mock
    def test_raises_on_error(self, config: Config) -> None:
        respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=500
        )
        with pytest.raises(httpx.HTTPStatusError):
            update_thought_metadata("abc", ThoughtMetadata(), config)


# ---------------------------------------------------------------------------
# verify_thought
# ---------------------------------------------------------------------------


class TestVerifyThought:
    @respx.mock
    def test_sends_patch_with_verified_timestamp(self, config: Config) -> None:
        route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        verify_thought("abc-123", ThoughtMetadata(visibility=["personal"]), config)
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert "visibility_verified_by_human_at" in body
        assert body["metadata"] == {
            "visibility": ["personal"],
            "type": "observation",
            "topics": [],
        }
        assert body["updated_at"] == body["visibility_verified_by_human_at"]

    @respx.mock
    def test_raises_on_error(self, config: Config) -> None:
        respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=403
        )
        with pytest.raises(httpx.HTTPStatusError):
            verify_thought("abc", ThoughtMetadata(), config)
