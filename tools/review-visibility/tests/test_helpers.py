"""Tests for pure helper functions (no network, no TUI)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from main import (
    apply_tag_rules,
    get_cache_path,
    get_config,
    load_cache,
    save_cache,
    sb_headers,
    sb_url,
)

# ---------------------------------------------------------------------------
# apply_tag_rules
# ---------------------------------------------------------------------------


class TestApplyTagRules:
    def test_no_rules(self) -> None:
        assert apply_tag_rules(["sfw", "work"], []) == ["sfw", "work"]

    def test_removes_matching_tag(self) -> None:
        rules = [{"if_present": "lgbtq_identity", "remove_tag": "sfw"}]
        result = apply_tag_rules(["sfw", "lgbtq_identity"], rules)
        assert "sfw" not in result
        assert "lgbtq_identity" in result

    def test_no_match_leaves_unchanged(self) -> None:
        rules = [{"if_present": "lgbtq_identity", "remove_tag": "sfw"}]
        result = apply_tag_rules(["sfw", "work"], rules)
        assert result == ["sfw", "work"]

    def test_multiple_rules(self, sample_tag_rules: list[dict[str, str]]) -> None:
        vis = ["sfw", "romantic_or_sexual_relationship", "personal"]
        result = apply_tag_rules(vis, sample_tag_rules)
        assert "sfw" not in result
        assert "romantic_or_sexual_relationship" in result
        assert "personal" in result

    def test_empty_visibility(self) -> None:
        rules = [{"if_present": "x", "remove_tag": "y"}]
        assert apply_tag_rules([], rules) == []

    def test_does_not_mutate_input(self) -> None:
        original = ["sfw", "lgbtq_identity"]
        rules = [{"if_present": "lgbtq_identity", "remove_tag": "sfw"}]
        apply_tag_rules(original, rules)
        assert original == ["sfw", "lgbtq_identity"]

    def test_chained_removal(self) -> None:
        """Both rules fire independently."""
        rules = [
            {"if_present": "romantic_or_sexual_relationship", "remove_tag": "sfw"},
            {"if_present": "lgbtq_identity", "remove_tag": "sfw"},
        ]
        vis = ["sfw", "lgbtq_identity", "romantic_or_sexual_relationship"]
        result = apply_tag_rules(vis, rules)
        assert "sfw" not in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# sb_headers / sb_url
# ---------------------------------------------------------------------------


class TestSupabaseHelpers:
    def test_sb_headers(self, config: dict[str, str]) -> None:
        h = sb_headers(config)
        assert h["apikey"] == "test-service-role-key"
        assert h["Authorization"] == "Bearer test-service-role-key"
        assert h["Content-Type"] == "application/json"

    def test_sb_url(self, config: dict[str, str]) -> None:
        assert sb_url(config, "thoughts") == "https://test.supabase.co/rest/v1/thoughts"

    def test_sb_url_nested(self, config: dict[str, str]) -> None:
        assert (
            sb_url(config, "rpc/my_fn") == "https://test.supabase.co/rest/v1/rpc/my_fn"
        )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestCache:
    def test_load_missing_cache(self, tmp_path: Path) -> None:
        result = load_cache(tmp_path / "nonexistent.json")
        assert result == {"scanned": {}, "prompt_template_id": None}

    def test_save_and_load(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "cache.json"
        data: dict[str, Any] = {
            "scanned": {"id-1": {"visibility": ["sfw"]}},
            "prompt_template_id": "abc-123",
        }
        save_cache(data, cache_path)
        loaded = load_cache(cache_path)
        assert loaded == data

    def test_save_overwrites(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "cache.json"
        save_cache({"scanned": {}, "prompt_template_id": "v1"}, cache_path)
        save_cache({"scanned": {"x": {}}, "prompt_template_id": "v2"}, cache_path)
        loaded = load_cache(cache_path)
        assert loaded["prompt_template_id"] == "v2"
        assert "x" in loaded["scanned"]

    def test_cache_file_is_valid_json(self, tmp_path: Path) -> None:
        cache_path = tmp_path / "cache.json"
        save_cache({"scanned": {}, "prompt_template_id": None}, cache_path)
        parsed = json.loads(cache_path.read_text())
        assert "scanned" in parsed


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_get_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://my.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "my-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        cfg = get_config()
        assert cfg["supabase_url"] == "https://my.supabase.co"
        assert cfg["supabase_key"] == "my-key"
        assert cfg["openrouter_api_key"] == "or-key"
        assert cfg["openrouter_base"] == "https://openrouter.ai/api/v1"

    def test_get_config_defaults_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = get_config()
        assert cfg["supabase_url"] == ""
        assert cfg["supabase_key"] == ""

    def test_get_cache_path(self) -> None:
        p = get_cache_path()
        assert p.name == ".scan_cache.json"
