"""Tests for TUI screens using Textual's async test harness."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import respx
from main import ReviewScreen, ThoughtDetailScreen, VisibilityReviewApp
from models import Config, Thought, ThoughtMetadata
from textual.widgets import DataTable, Label, Static, TextArea

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CONFIG = Config(
    supabase_url="https://test.supabase.co",
    supabase_key="test-key",
    openrouter_api_key="test-or-key",
)

FAKE_THOUGHTS_JSON = [
    {
        "id": "id-1",
        "content": "Test thought one",
        "metadata": {"visibility": ["sfw"], "type": "observation", "topics": []},
        "visibility_verified_by_human_at": None,
        "created_at": "2026-03-16T12:00:00Z",
        "submitted_by": "user",
    },
    {
        "id": "id-2",
        "content": "Private thought",
        "metadata": {
            "visibility": ["personal"],
            "type": "observation",
            "topics": [],
        },
        "visibility_verified_by_human_at": "2026-03-15T10:00:00Z",
        "created_at": "2026-03-15T10:00:00Z",
        "submitted_by": "user",
    },
]

FAKE_PROMPT_JSON = {
    "prompt_template_text": "Classify this thought.",
    "model_string": "openai/gpt-5.2",
    "prompt_template_id": "prompt-abc",
}


def _mock_routes() -> None:
    """Set up respx routes for the standard app load sequence."""
    respx.get("https://test.supabase.co/rest/v1/thoughts").respond(
        json=FAKE_THOUGHTS_JSON
    )
    respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
        json=[FAKE_PROMPT_JSON]
    )
    respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(json=[])


def _status_text(app: VisibilityReviewApp) -> str:
    """Get the text content of the status bar label."""
    return str(app.query_one("#status-bar", Label).content)


def _thought(
    *,
    id: str = "t-1",
    content: str = "test",
    visibility: list[str] | None = None,
    type: str = "observation",
    topics: list[str] | None = None,
    verified_at: str | None = None,
    created_at: str = "2026-03-16T12:00:00Z",
) -> Thought:
    """Build a Thought for tests."""
    return Thought(
        id=id,
        content=content,
        metadata=ThoughtMetadata(
            visibility=visibility or ["sfw"],
            type=type,
            topics=topics or [],
        ),
        visibility_verified_by_human_at=verified_at,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# VisibilityReviewApp tests
# ---------------------------------------------------------------------------


class TestVisibilityReviewApp:
    @respx.mock
    async def test_app_loads_and_populates_table(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            assert table.row_count == 2

    @respx.mock
    async def test_status_bar_shows_count(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert "2 thoughts" in _status_text(app)

    @respx.mock
    async def test_clear_cache_action(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["sfw"]),
            }
            app.action_clear_cache()
            assert app.scan_results == {}
            assert "Cache cleared" in _status_text(app)

    @respx.mock
    async def test_table_shows_verified_status(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            rows = list(table.rows.keys())
            assert len(rows) == 2

    @respx.mock
    async def test_table_shows_diff_status_when_scanned(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["personal"]),
            }
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            row_data = table.get_row_at(0)
            assert row_data[-1] == "DIFF"

    @respx.mock
    async def test_table_shows_match_status_when_same(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["sfw"]),
            }
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            row_data = table.get_row_at(0)
            assert row_data[-1] == "match"

    @respx.mock
    async def test_get_selected_thought(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            thought = app._get_selected_thought()
            # cursor defaults to row 0 => id-1
            assert thought is not None
            assert thought.id == "id-1"

    @respx.mock
    async def test_get_selected_thought_index_error_returns_none(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            # Force cursor beyond the actual row count to trigger IndexError
            with patch.object(
                type(table),
                "cursor_row",
                new_callable=lambda: property(lambda self: 999),
            ):
                assert app._get_selected_thought() is None

    @respx.mock
    async def test_review_selected_no_selection_no_crash(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.thoughts = []
            app._populate_table()
            app.action_review_selected()  # should not raise

    @respx.mock
    async def test_review_next_diff_no_diffs(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app._review_next_diff()
            assert "No more diffs" in _status_text(app)

    @respx.mock
    async def test_on_review_done_saved(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Inject scan result for id-1 (cursor defaults to row 0)
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["work"]),
            }
            app._on_review_done("saved")
            assert "saved" in _status_text(app)
            assert "id-1" not in app.scan_results

    @respx.mock
    async def test_on_review_done_none_does_nothing(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app._on_review_done(None)
            # Should not crash; status not updated to "saved"

    @respx.mock
    async def test_load_data_error_handling(self) -> None:
        """If fetch fails, status bar shows error."""
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(status_code=500)
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[FAKE_PROMPT_JSON]
        )
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(json=[])
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert "Error" in _status_text(app)

    @respx.mock
    async def test_review_next_diff_opens_screen(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Inject diff for id-1
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["personal"]),
            }
            app._review_next_diff()
            await pilot.pause()
            # Should have pushed a ReviewScreen
            assert len(app.screen_stack) > 1

    @respx.mock
    async def test_action_review_all(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # No diffs — should just update status
            app.action_review_all()
            assert "No more diffs" in _status_text(app)

    @respx.mock
    async def test_on_review_all_done_continues(self) -> None:
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["work"]),
            }
            # _on_review_all_done with non-None result continues
            app._on_review_all_done("skipped")
            # id-1 not saved/verified, so scan_results untouched
            # but _review_next_diff was called

    @respx.mock
    async def test_load_data_tag_rules_error_falls_back(self) -> None:
        """When tag_rules fetch returns an HTTP error, tag_rules defaults to []."""
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(
            json=FAKE_THOUGHTS_JSON
        )
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[FAKE_PROMPT_JSON]
        )
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(status_code=404)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.tag_rules == []
            assert "2 thoughts" in _status_text(app)

    @respx.mock
    async def test_load_data_cache_match_populates_scan_results(
        self, tmp_path: Path
    ) -> None:
        """When cache prompt_template_id matches, scan_results loaded from cache."""
        _mock_routes()
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "prompt_template_id": "prompt-abc",
            "scanned": {
                "id-1": {
                    "visibility": ["work"],
                    "type": "observation",
                    "topics": [],
                }
            },
        }
        cache_file.write_text(json.dumps(cache_data))

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = cache_file
        from main import load_cache

        app.cache = load_cache(cache_file)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "id-1" in app.scan_results
            assert app.scan_results["id-1"].visibility == ["work"]
            assert "1 cached" in _status_text(app)

    @respx.mock
    async def test_load_data_cache_mismatch_clears_scan_results(
        self, tmp_path: Path
    ) -> None:
        """When cache prompt_template_id differs, scan_results reset to empty."""
        _mock_routes()
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "prompt_template_id": "old-prompt-id",
            "scanned": {
                "id-1": {
                    "visibility": ["work"],
                    "type": "observation",
                    "topics": [],
                }
            },
        }
        cache_file.write_text(json.dumps(cache_data))

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = cache_file
        from main import load_cache

        app.cache = load_cache(cache_file)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.scan_results == {}
            assert "0 cached" in _status_text(app)

    @respx.mock
    async def test_run_scan_scans_all_thoughts(self, tmp_path: Path) -> None:
        """_run_scan classifies all thoughts and saves cache."""
        _mock_routes()
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["sfw"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_scan()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "id-1" in app.scan_results
            assert "id-2" in app.scan_results
            assert app.scan_results["id-1"].visibility == ["sfw"]
            assert "Scan done" in _status_text(app)
            # Cache file written
            assert app.cache_path.exists()
            cache = json.loads(app.cache_path.read_text())
            assert cache["prompt_template_id"] == "prompt-abc"

    @respx.mock
    async def test_run_scan_skips_already_scanned(self, tmp_path: Path) -> None:
        """_run_scan skips thoughts already in scan_results."""
        _mock_routes()
        or_route = respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["personal"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Pre-populate both as scanned
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["sfw"]),
                "id-2": ThoughtMetadata(visibility=["personal"]),
            }
            app.action_scan()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # No OpenRouter calls should have been made
            assert or_route.call_count == 0
            assert "Scan done" in _status_text(app)

    @respx.mock
    async def test_run_scan_handles_errors(self, tmp_path: Path) -> None:
        """_run_scan counts errors for failed reclassifications."""
        _mock_routes()
        # Make OpenRouter return errors
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            status_code=500
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_scan()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "2 errors" in _status_text(app)

    @respx.mock
    async def test_run_scan_saves_cache_periodically(self, tmp_path: Path) -> None:
        """_run_scan saves cache every 5 scans."""
        # Create 6 thoughts so we cross the modulo-5 boundary
        thoughts = [
            {
                "id": f"id-{i}",
                "content": f"Thought {i}",
                "metadata": {
                    "visibility": ["sfw"],
                    "type": "observation",
                    "topics": [],
                },
                "visibility_verified_by_human_at": None,
                "created_at": "2026-03-16T12:00:00Z",
                "submitted_by": "user",
            }
            for i in range(6)
        ]
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(json=thoughts)
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[FAKE_PROMPT_JSON]
        )
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(json=[])
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["sfw"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_scan()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert len(app.scan_results) == 6
            # Cache should exist (written at modulo-5 AND at end)
            assert app.cache_path.exists()
            cache = json.loads(app.cache_path.read_text())
            assert len(cache["scanned"]) == 6

    @respx.mock
    async def test_run_scan_counts_diffs(self, tmp_path: Path) -> None:
        """_run_scan status shows correct diff count."""
        _mock_routes()
        # Return different visibility than what id-1 has (sfw)
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["personal"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_scan()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # id-1 has sfw, scan gives personal => DIFF
            # id-2 has personal, scan gives personal => match
            assert "1 diffs" in _status_text(app)

    @respx.mock
    async def test_action_review_selected_with_scan_result(self) -> None:
        """When thought is already scanned, pushes ThoughtDetailScreen."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["work"]),
            }
            app.action_review_selected()
            await pilot.pause()
            assert len(app.screen_stack) > 1
            assert isinstance(app.screen_stack[-1], ThoughtDetailScreen)

    @respx.mock
    async def test_action_review_selected_without_scan_shows_detail(self) -> None:
        """When thought not scanned, pushes ThoughtDetailScreen (no scan yet)."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # No scan results — should still show detail screen
            app.action_review_selected()
            await pilot.pause()

            assert len(app.screen_stack) > 1
            assert isinstance(app.screen_stack[-1], ThoughtDetailScreen)

    @respx.mock
    async def test_scan_and_review_error_shows_status(self, tmp_path: Path) -> None:
        """When _scan_and_review fails, status shows error."""
        _mock_routes()
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            status_code=500
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Simulate what happens when detail screen returns "review"
            # on an unscanned thought: _on_detail_done triggers _scan_and_review
            app._on_detail_done("review")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "Error" in _status_text(app)

    @respx.mock
    async def test_scan_and_review_saves_cache(self, tmp_path: Path) -> None:
        """_scan_and_review saves result to cache."""
        _mock_routes()
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["sfw"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Simulate detail->review flow on unscanned thought
            app._on_detail_done("review")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.cache_path.exists()
            cache = json.loads(app.cache_path.read_text())
            assert "id-1" in cache["scanned"]

    @respx.mock
    async def test_action_refresh(self) -> None:
        """action_refresh re-runs _load_data."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Mutate state then refresh
            app.thoughts = []
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            assert table.row_count == 0

            app.action_refresh()
            await app.workers.wait_for_complete()
            await pilot.pause()

            table = app.query_one("#main-table", DataTable)
            assert table.row_count == 2


# ---------------------------------------------------------------------------
# ReviewScreen tests
# ---------------------------------------------------------------------------


class TestReviewScreen:
    async def test_compose_renders(self) -> None:
        thought = _thought(content="Hello world")
        new_meta = ThoughtMetadata(visibility=["sfw", "work"])
        screen = ReviewScreen(thought, new_meta, [], FAKE_CONFIG)

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                edit = screen.query_one("#edit-area", TextArea)
                assert "sfw" in edit.text
                assert "work" in edit.text

    async def test_parse_visibility(self) -> None:
        thought = _thought()
        screen = ReviewScreen(
            thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                edit = screen.query_one("#edit-area", TextArea)
                edit.clear()
                edit.insert("personal, work, sfw")
                result = screen._parse_visibility()
                assert result == ["personal", "sfw", "work"]

    async def test_parse_visibility_deduplicates(self) -> None:
        thought = _thought()
        screen = ReviewScreen(
            thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                edit = screen.query_one("#edit-area", TextArea)
                edit.clear()
                edit.insert("sfw, sfw, work")
                result = screen._parse_visibility()
                assert result == ["sfw", "work"]

    async def test_parse_visibility_handles_newlines(self) -> None:
        thought = _thought()
        screen = ReviewScreen(
            thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                edit = screen.query_one("#edit-area", TextArea)
                edit.clear()
                edit.insert("personal\nwork")
                result = screen._parse_visibility()
                assert result == ["personal", "work"]

    async def test_build_updated_metadata(self) -> None:
        thought = _thought(
            visibility=["sfw"],
            type="observation",
            topics=["test"],
        )
        screen = ReviewScreen(
            thought, ThoughtMetadata(visibility=["personal"]), [], FAKE_CONFIG
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                meta = screen._build_updated_metadata()
                assert meta.type == "observation"
                assert meta.topics == ["test"]
                assert isinstance(meta.visibility, list)

    @respx.mock
    async def test_skip_dismisses(self) -> None:
        thought = _thought()
        _mock_routes()
        results: list[str | None] = []

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            def capture(result: str | None) -> None:
                results.append(result)

            screen = ReviewScreen(
                thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
            )
            app.push_screen(screen, callback=capture)
            await pilot.pause()
            await pilot.click("#btn-skip")
            await pilot.pause()
            assert results == ["skipped"]

    @respx.mock
    async def test_cancel_dismisses_none(self) -> None:
        thought = _thought()
        _mock_routes()
        results: list[str | None] = []

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            def capture(result: str | None) -> None:
                results.append(result)

            screen = ReviewScreen(
                thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
            )
            app.push_screen(screen, callback=capture)
            await pilot.pause()
            await pilot.click("#btn-cancel")
            await pilot.pause()
            assert results == [None]

    @respx.mock
    async def test_save_calls_api(self) -> None:
        thought = _thought(id="t-save", content="save test")
        _mock_routes()
        patch_route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        results: list[str | None] = []

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            def capture(result: str | None) -> None:
                results.append(result)

            screen = ReviewScreen(
                thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
            )
            app.push_screen(screen, callback=capture)
            await pilot.pause()
            await pilot.click("#btn-save")
            await pilot.pause()
            assert results == ["saved"]
            assert patch_route.called

    @respx.mock
    async def test_verify_calls_api_with_timestamp(self) -> None:
        thought = _thought(
            id="t-verify", content="verify test", visibility=["personal"]
        )
        _mock_routes()
        patch_route = respx.patch("https://test.supabase.co/rest/v1/thoughts").respond(
            status_code=204
        )
        results: list[str | None] = []

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            def capture(result: str | None) -> None:
                results.append(result)

            screen = ReviewScreen(
                thought,
                ThoughtMetadata(visibility=["personal"]),
                [],
                FAKE_CONFIG,
            )
            app.push_screen(screen, callback=capture)
            await pilot.pause()
            await pilot.click("#btn-verify")
            await pilot.pause()
            assert results == ["verified"]
            assert patch_route.called
            body = json.loads(patch_route.calls[0].request.content)
            assert "visibility_verified_by_human_at" in body

    async def test_verified_thought_shows_timestamp(self) -> None:
        thought = _thought(
            content="already verified",
            verified_at="2026-03-15T10:00:00Z",
        )
        screen = ReviewScreen(
            thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                labels = screen.query(Label)
                header_text = str(labels.first().content)
                assert "2026-03-15" in header_text

    async def test_compose_with_tag_rules_applied(self) -> None:
        """New visibility in edit area should have tag rules applied."""
        from models import TagRule

        thought = _thought()
        rules = [TagRule(if_present="lgbtq_identity", remove_tag="sfw")]
        new_meta = ThoughtMetadata(visibility=["sfw", "lgbtq_identity"])
        screen = ReviewScreen(thought, new_meta, rules, FAKE_CONFIG)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                edit = screen.query_one("#edit-area", TextArea)
                # Tag rules should have removed "sfw"
                assert "sfw" not in edit.text
                assert "lgbtq_identity" in edit.text


# ---------------------------------------------------------------------------
# ThoughtDetailScreen tests
# ---------------------------------------------------------------------------


class TestThoughtDetailScreen:
    async def test_detail_renders_full_content(self) -> None:
        """Detail screen shows the full thought content without truncation."""
        long_content = "A" * 200
        thought = _thought(content=long_content)
        screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                static = screen.query_one("#detail-content", Static)
                assert str(static.content) == long_content

    async def test_detail_close_dismisses_none(self) -> None:
        """Clicking Close dismisses with None."""
        thought = _thought()
        results: list[str | None] = []
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:

                def capture(result: str | None) -> None:
                    results.append(result)

                screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
                app.push_screen(screen, callback=capture)
                await pilot.pause()
                await pilot.click("#btn-close")
                await pilot.pause()
                assert results == [None]

    async def test_detail_review_dismisses_review(self) -> None:
        """Clicking Review dismisses with 'review'."""
        thought = _thought()
        results: list[str | None] = []
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:

                def capture(result: str | None) -> None:
                    results.append(result)

                screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
                app.push_screen(screen, callback=capture)
                await pilot.pause()
                await pilot.click("#btn-review")
                await pilot.pause()
                assert results == ["review"]

    async def test_detail_shows_metadata(self) -> None:
        """Detail screen shows created date, type, and visibility."""
        thought = _thought(
            content="test",
            visibility=["sfw", "work"],
            type="question",
            topics=["coding"],
            created_at="2026-03-16T12:00:00Z",
        )
        screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                header = str(screen.query_one("#detail-header", Label).content)
                assert "2026-03-16" in header
                assert "question" in header
                meta = str(screen.query_one("#detail-meta", Static).content)
                assert "coding" in meta
                assert "sfw" in meta

    async def test_detail_unscanned_shows_no_new_vis(self) -> None:
        """When new_meta is None, detail screen omits new visibility line."""
        thought = _thought()
        screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                meta = str(screen.query_one("#detail-meta", Static).content)
                assert "New visibility" not in meta

    async def test_detail_scanned_shows_new_vis_and_diff(self) -> None:
        """When new_meta is provided, detail screen shows new vis and diff status."""
        thought = _thought(visibility=["sfw"])
        new_meta = ThoughtMetadata(visibility=["personal"])
        screen = ThoughtDetailScreen(thought, new_meta, [], FAKE_CONFIG)
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:
                app.push_screen(screen)
                await pilot.pause()
                meta = str(screen.query_one("#detail-meta", Static).content)
                assert "New visibility" in meta
                assert "personal" in meta
                assert "DIFF" in meta


# ---------------------------------------------------------------------------
# Table newline collapsing tests
# ---------------------------------------------------------------------------


class TestTableNewlineCollapsing:
    @respx.mock
    async def test_table_collapses_newlines(self) -> None:
        """Content with newlines should be collapsed to spaces in table."""
        thoughts_json = [
            {
                "id": "id-nl",
                "content": "line one\nline two\nline three",
                "metadata": {
                    "visibility": ["sfw"],
                    "type": "observation",
                    "topics": [],
                },
                "visibility_verified_by_human_at": None,
                "created_at": "2026-03-16T12:00:00Z",
                "submitted_by": "user",
            },
        ]
        respx.get("https://test.supabase.co/rest/v1/thoughts").respond(
            json=thoughts_json
        )
        respx.post("https://test.supabase.co/rest/v1/rpc/get_current_prompt").respond(
            json=[FAKE_PROMPT_JSON]
        )
        respx.get("https://test.supabase.co/rest/v1/tag_rules").respond(json=[])

        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            row = table.get_row_at(0)
            content_cell = row[1]
            assert "\n" not in str(content_cell)
            assert "line one line two line three" in str(content_cell)

    @respx.mock
    async def test_resize_repopulates_table(self) -> None:
        """Resizing the terminal re-truncates content column."""
        _mock_routes()
        # Use a thought long enough to be truncated at narrow width
        long_content = "word " * 40  # 200 chars
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.thoughts[0] = _thought(id="id-1", content=long_content)
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            wide_content = str(table.get_row_at(0)[1])

            await pilot.resize_terminal(60, 40)
            await pilot.pause()
            narrow_content = str(table.get_row_at(0)[1])

            assert len(narrow_content) < len(wide_content)


# ---------------------------------------------------------------------------
# Column width / render tests
# ---------------------------------------------------------------------------


class TestColumnWidths:
    @respx.mock
    async def test_all_columns_visible_at_width_120(self) -> None:
        """At width=120, all 5 column headers should be present."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            labels = [col.label.plain for col in table.columns.values()]
            assert labels == ["Created", "Content", "Current Vis", "New Vis", "Status"]

    @respx.mock
    async def test_all_columns_visible_at_width_80(self) -> None:
        """At width=80, all 5 column headers should be present."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(80, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            labels = [col.label.plain for col in table.columns.values()]
            assert labels == ["Created", "Content", "Current Vis", "New Vis", "Status"]

    @respx.mock
    async def test_columns_fit_within_terminal_width(self) -> None:
        """Sum of all column widths should not exceed terminal width."""
        _mock_routes()
        for term_width in (80, 100, 120, 200):
            app = VisibilityReviewApp(config=FAKE_CONFIG)
            async with app.run_test(size=(term_width, 40)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                table = app.query_one("#main-table", DataTable)
                total = sum(
                    col.width for col in table.columns.values() if col.width is not None
                )
                assert total <= term_width, (
                    f"columns total {total} > terminal {term_width}"
                )

    @respx.mock
    async def test_resize_adjusts_column_widths(self) -> None:
        """After resize, column widths change and still fit."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            wide_widths = [
                col.width for col in table.columns.values() if col.width is not None
            ]

            await pilot.resize_terminal(80, 40)
            await pilot.pause()
            narrow_widths = [
                col.width for col in table.columns.values() if col.width is not None
            ]

            assert narrow_widths != wide_widths
            assert sum(narrow_widths) <= 80

    @respx.mock
    async def test_content_truncated_to_column_width(self) -> None:
        """Content cell string length should not exceed content column width."""
        _mock_routes()
        long_content = "a" * 300
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(80, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.thoughts[0] = _thought(id="id-1", content=long_content)
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            content_col_width = list(table.columns.values())[1].width
            content_cell = str(table.get_row_at(0)[1])
            assert len(content_cell) <= content_col_width + 1  # +1 for ellipsis char

    @respx.mock
    async def test_visibility_truncated_to_column_width(self) -> None:
        """Long visibility strings should be truncated to vis column width."""
        _mock_routes()
        long_vis = [
            "family_relationship",
            "romantic_or_sexual_relationship",
            "personal",
            "lgbtq_identity",
        ]
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(80, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.thoughts[0] = _thought(id="id-1", visibility=long_vis)
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            vis_col_width = list(table.columns.values())[2].width
            vis_cell = str(table.get_row_at(0)[2])
            assert len(vis_cell) <= vis_col_width
            assert vis_cell.endswith("\u2026")


# ---------------------------------------------------------------------------
# Keybinding integration tests (pilot.press)
# ---------------------------------------------------------------------------


class TestKeybindings:
    """All tests use pilot.press() to exercise the real input path."""

    @respx.mock
    async def test_enter_key_opens_detail_screen(self) -> None:
        """Pressing enter opens ThoughtDetailScreen for selected row."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(app.screen_stack) > 1
            assert isinstance(app.screen_stack[-1], ThoughtDetailScreen)

    @respx.mock
    async def test_s_key_triggers_scan(self, tmp_path: Path) -> None:
        """Pressing s triggers a scan."""
        _mock_routes()
        respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "visibility": ["sfw"],
                                    "type": "observation",
                                    "topics": [],
                                }
                            )
                        }
                    }
                ]
            }
        )
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        app.cache_path = tmp_path / "cache.json"
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "Scan done" in _status_text(app)

    @respx.mock
    async def test_a_key_reviews_all_diffs(self) -> None:
        """Pressing a with no diffs shows 'No more diffs'."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert "No more diffs" in _status_text(app)

    @respx.mock
    async def test_r_key_refreshes(self) -> None:
        """Pressing r re-fetches data."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            # Clear thoughts, then press r to refresh
            app.thoughts = []
            app._populate_table()
            table = app.query_one("#main-table", DataTable)
            assert table.row_count == 0

            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#main-table", DataTable)
            assert table.row_count == 2

    @respx.mock
    async def test_c_key_clears_cache(self) -> None:
        """Pressing c clears scan results and shows 'Cache cleared'."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.scan_results = {
                "id-1": ThoughtMetadata(visibility=["sfw"]),
            }
            await pilot.press("c")
            await pilot.pause()
            assert app.scan_results == {}
            assert "Cache cleared" in _status_text(app)

    @respx.mock
    async def test_q_key_quits(self) -> None:
        """Pressing q exits the app."""
        _mock_routes()
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    @respx.mock
    async def test_escape_dismisses_review_screen(self) -> None:
        """Pressing escape on ReviewScreen dismisses with None."""
        _mock_routes()
        results: list[str | None] = []
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            def capture(result: str | None) -> None:
                results.append(result)

            thought = _thought()
            screen = ReviewScreen(
                thought, ThoughtMetadata(visibility=["sfw"]), [], FAKE_CONFIG
            )
            app.push_screen(screen, callback=capture)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert results == [None]

    async def test_escape_dismisses_detail_screen(self) -> None:
        """Pressing escape on ThoughtDetailScreen dismisses with None."""
        results: list[str | None] = []
        app = VisibilityReviewApp(config=FAKE_CONFIG)
        with patch.object(app, "_load_data"):
            async with app.run_test(size=(120, 40)) as pilot:

                def capture(result: str | None) -> None:
                    results.append(result)

                thought = _thought()
                screen = ThoughtDetailScreen(thought, None, [], FAKE_CONFIG)
                app.push_screen(screen, callback=capture)
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert results == [None]
