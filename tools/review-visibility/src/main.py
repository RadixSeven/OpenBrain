"""
Visibility Review TUI — review and verify LLM-assigned visibility tags on thoughts.

Env vars needed: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENROUTER_API_KEY
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Static,
    TextArea,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ALL_VISIBILITY_LABELS = [
    "sfw",
    "personal",
    "work",
    "technical",
    "health",
    "financial",
    "romantic_or_sexual_relationship",
    "religion",
    "family_relationship",
    "other_relationship",
    "lgbtq_identity",
    "activism",
]


def get_config() -> dict[str, str]:
    """Return current config from environment."""
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_key": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        "openrouter_api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        "openrouter_base": "https://openrouter.ai/api/v1",
    }


def get_cache_path() -> Path:
    """Return path for scan cache file."""
    return Path(__file__).resolve().parent.parent / ".scan_cache.json"


# ---------------------------------------------------------------------------
# Supabase / OpenRouter helpers
# ---------------------------------------------------------------------------


def sb_headers(config: dict[str, str]) -> dict[str, str]:
    """Build Supabase REST headers."""
    key = config["supabase_key"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def sb_url(config: dict[str, str], path: str) -> str:
    """Build Supabase REST URL."""
    return f"{config['supabase_url']}/rest/v1/{path}"


def sb_rpc(
    config: dict[str, str],
    fn: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Call a Supabase RPC function."""
    r = httpx.post(
        f"{config['supabase_url']}/rest/v1/rpc/{fn}",
        headers=sb_headers(config),
        json=params or {},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_all_thoughts(config: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch all thoughts with their metadata."""
    thoughts: list[dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        r = httpx.get(
            sb_url(config, "thoughts"),
            headers={
                **sb_headers(config),
                "Range": f"{offset}-{offset + limit - 1}",
                "Prefer": "count=exact",
            },
            params={
                "select": (
                    "id,content,metadata,"
                    "visibility_verified_by_human_at,created_at,submitted_by"
                ),
                "order": "created_at.desc",
            },
            timeout=30,
        )
        r.raise_for_status()
        batch: list[dict[str, Any]] = r.json()
        if not batch:
            break
        thoughts.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return thoughts


def get_current_prompt(config: dict[str, str]) -> dict[str, Any]:
    """Fetch current categorization prompt from DB."""
    result = sb_rpc(config, "get_current_prompt", {"p_type": "categorization"})
    if isinstance(result, list) and result:
        return result[0]  # type: ignore[no-any-return]
    return result  # type: ignore[no-any-return]


def fetch_tag_rules(config: dict[str, str]) -> list[dict[str, str]]:
    """Fetch active tag rules."""
    r = httpx.get(
        sb_url(config, "tag_rules"),
        headers=sb_headers(config),
        params={"select": "if_present,remove_tag", "active": "eq.true"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


def apply_tag_rules(
    visibility: list[str],
    rules: list[dict[str, str]],
) -> list[str]:
    """Apply deterministic tag removal rules to a visibility list."""
    result = list(visibility)
    for rule in rules:
        if rule["if_present"] in result:
            result = [t for t in result if t != rule["remove_tag"]]
    return result


def reclassify_thought(
    content: str,
    prompt_text: str,
    model: str,
    config: dict[str, str],
) -> dict[str, Any]:
    """Re-run the categorization prompt on a thought."""
    r = httpx.post(
        f"{config['openrouter_base']}/chat/completions",
        headers={
            "Authorization": f"Bearer {config['openrouter_api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": content},
            ],
        },
        timeout=60,
    )
    r.raise_for_status()
    d: dict[str, Any] = r.json()
    try:
        return json.loads(d["choices"][0]["message"]["content"])  # type: ignore[no-any-return]
    except (KeyError, json.JSONDecodeError):
        return {
            "visibility": ["uncategorized"],
            "type": "observation",
            "topics": ["uncategorized"],
        }


def update_thought_metadata(
    thought_id: str,
    metadata: dict[str, Any],
    config: dict[str, str],
) -> None:
    """Update the metadata column for a thought."""
    r = httpx.patch(
        sb_url(config, "thoughts"),
        headers={**sb_headers(config), "Prefer": "return=minimal"},
        params={"id": f"eq.{thought_id}"},
        json={
            "metadata": metadata,
            "updated_at": datetime.now(UTC).isoformat(),
        },
        timeout=30,
    )
    r.raise_for_status()


def verify_thought(
    thought_id: str,
    metadata: dict[str, Any],
    config: dict[str, str],
) -> None:
    """Update metadata and set visibility_verified_by_human_at."""
    now = datetime.now(UTC).isoformat()
    r = httpx.patch(
        sb_url(config, "thoughts"),
        headers={**sb_headers(config), "Prefer": "return=minimal"},
        params={"id": f"eq.{thought_id}"},
        json={
            "metadata": metadata,
            "updated_at": now,
            "visibility_verified_by_human_at": now,
        },
        timeout=30,
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Cache helpers — allow resuming scans
# ---------------------------------------------------------------------------


def load_cache(cache_path: Path) -> dict[str, Any]:
    """Load scan cache from disk."""
    if cache_path.exists():
        return json.loads(cache_path.read_text())  # type: ignore[no-any-return]
    return {"scanned": {}, "prompt_template_id": None}


def save_cache(cache: dict[str, Any], cache_path: Path) -> None:
    """Persist scan cache to disk."""
    cache_path.write_text(json.dumps(cache, indent=2, default=str))


# ---------------------------------------------------------------------------
# TUI Screens
# ---------------------------------------------------------------------------


class ReviewScreen(ModalScreen[str | None]):
    """Review a single thought's visibility tags."""

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    CSS = """
    ReviewScreen {
        align: center middle;
    }
    #review-dialog {
        width: 90%;
        height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #thought-content {
        height: auto;
        max-height: 8;
        margin-bottom: 1;
        background: $boost;
        padding: 1;
    }
    #vis-columns {
        height: auto;
        margin-bottom: 1;
    }
    .vis-col {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    .vis-heading {
        text-style: bold;
        margin-bottom: 1;
    }
    #edit-area {
        height: 5;
        margin-bottom: 1;
    }
    #button-row {
        height: 3;
        align: center middle;
    }
    #button-row Button {
        margin: 0 2;
    }
    """

    def __init__(
        self,
        thought: dict[str, Any],
        new_meta: dict[str, Any],
        tag_rules: list[dict[str, str]],
        config: dict[str, str],
    ) -> None:
        super().__init__()
        self.thought = thought
        self.new_meta = new_meta
        self.tag_rules = tag_rules
        self.config = config

    def compose(self) -> ComposeResult:
        old_vis = sorted(self.thought.get("metadata", {}).get("visibility", []))
        new_vis_raw = sorted(self.new_meta.get("visibility", []))
        new_vis = sorted(apply_tag_rules(new_vis_raw, self.tag_rules))

        created = str(self.thought.get("created_at", ""))[:19]
        verified = self.thought.get("visibility_verified_by_human_at")
        verified_str = str(verified)[:19] if verified else "never"

        with Vertical(id="review-dialog"):
            yield Label(
                f"[b]Thought[/b] ({created})  verified: {verified_str}",
                markup=True,
            )
            yield Static(str(self.thought.get("content", "")), id="thought-content")

            with Horizontal(id="vis-columns"):
                with Vertical(classes="vis-col"):
                    yield Label(
                        "[b]Current visibility[/b]",
                        classes="vis-heading",
                        markup=True,
                    )
                    yield Static(
                        "\n".join(f"  \u2022 {t}" for t in old_vis) or "  (none)"
                    )
                with Vertical(classes="vis-col"):
                    yield Label(
                        "[b]LLM re-classification[/b]",
                        classes="vis-heading",
                        markup=True,
                    )
                    yield Static(
                        "\n".join(f"  \u2022 {t}" for t in sorted(new_vis))
                        or "  (none)"
                    )

            yield Label(
                "[b]Edit visibility[/b] (comma-separated):",
                markup=True,
            )
            yield TextArea(
                ", ".join(sorted(new_vis)),
                id="edit-area",
            )
            yield Label(
                f"[dim]Valid: {', '.join(ALL_VISIBILITY_LABELS)}[/dim]",
                markup=True,
            )
            with Horizontal(id="button-row"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Save + Verify", id="btn-verify", variant="success")
                yield Button("Skip", id="btn-skip")
                yield Button("Cancel", id="btn-cancel", variant="error")

    def _parse_visibility(self) -> list[str]:
        raw = self.query_one("#edit-area", TextArea).text
        tags: list[str] = []
        for part in raw.replace("\n", ",").split(","):
            t = part.strip().lower()
            if t:
                tags.append(t)
        return sorted(set(tags))

    def _build_updated_metadata(self) -> dict[str, Any]:
        vis = self._parse_visibility()
        meta: dict[str, Any] = dict(self.thought.get("metadata", {}))
        meta["visibility"] = vis
        return meta

    @on(Button.Pressed, "#btn-save")
    def on_save(self) -> None:
        meta = self._build_updated_metadata()
        update_thought_metadata(self.thought["id"], meta, self.config)
        self.dismiss("saved")

    @on(Button.Pressed, "#btn-verify")
    def on_verify(self) -> None:
        meta = self._build_updated_metadata()
        verify_thought(self.thought["id"], meta, self.config)
        self.dismiss("verified")

    @on(Button.Pressed, "#btn-skip")
    def on_skip(self) -> None:
        self.dismiss("skipped")

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class VisibilityReviewApp(App[None]):
    """Main TUI for reviewing visibility tags."""

    TITLE = "Open Brain \u2014 Visibility Review"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("s", "scan", "Scan for diffs"),
        Binding("enter", "review_selected", "Review"),
        Binding("a", "review_all", "Review all diffs"),
        Binding("r", "refresh", "Refresh list"),
        Binding("c", "clear_cache", "Clear cache"),
    ]

    CSS = """
    #status-bar {
        height: 3;
        padding: 0 2;
        background: $boost;
        dock: top;
    }
    #main-table {
        height: 1fr;
    }
    """

    def __init__(self, config: dict[str, str] | None = None) -> None:
        super().__init__()
        self.config = config or get_config()
        self.cache_path = get_cache_path()
        self.thoughts: list[dict[str, Any]] = []
        self.cache: dict[str, Any] = load_cache(self.cache_path)
        self.prompt_info: dict[str, Any] = {}
        self.tag_rules: list[dict[str, str]] = []
        self.scan_results: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Loading thoughts\u2026", id="status-bar")
        yield DataTable(id="main-table")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()

    @work(thread=True)
    def _load_data(self) -> None:
        """Fetch thoughts and prompt from DB."""
        status = self.query_one("#status-bar", Label)
        try:
            self.call_from_thread(status.update, "Fetching thoughts and prompt\u2026")
            self.thoughts = fetch_all_thoughts(self.config)
            self.prompt_info = get_current_prompt(self.config)
            try:
                self.tag_rules = fetch_tag_rules(self.config)
            except httpx.HTTPStatusError:
                self.tag_rules = []

            # Load cached scan results if prompt matches
            if self.cache.get("prompt_template_id") == self.prompt_info.get(
                "prompt_template_id"
            ):
                self.scan_results = self.cache.get("scanned", {})
            else:
                self.scan_results = {}

            self.call_from_thread(self._populate_table)
            n = len(self.thoughts)
            cached = len(self.scan_results)
            model = self.prompt_info.get("model_string", "?")
            self.call_from_thread(
                status.update,
                f"{n} thoughts | {cached} cached scans | model: {model}"
                " | [s]can [enter]review [a]ll [q]uit",
            )
        except Exception as exc:
            self.call_from_thread(status.update, f"Error: {exc}")

    def _populate_table(self) -> None:
        table = self.query_one("#main-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Created", "Content", "Current Vis", "New Vis", "Status")
        table.cursor_type = "row"

        for t in self.thoughts:
            tid: str = t["id"]
            meta: dict[str, Any] = t.get("metadata", {})
            old_vis = sorted(meta.get("visibility", []))
            created = str(t.get("created_at", ""))[:10]
            content_raw = str(t.get("content", ""))
            content = (
                (content_raw[:80] + "\u2026") if len(content_raw) > 80 else content_raw
            )
            verified = t.get("visibility_verified_by_human_at")

            new_vis: list[str] = []
            if tid in self.scan_results:
                new_vis_raw = sorted(self.scan_results[tid].get("visibility", []))
                new_vis = sorted(apply_tag_rules(new_vis_raw, self.tag_rules))
                row_status = "match" if old_vis == new_vis else "DIFF"
            elif verified:
                row_status = "verified"
            else:
                row_status = "\u2014"

            new_vis_str = ", ".join(new_vis) if tid in self.scan_results else "\u2014"
            table.add_row(
                created,
                content,
                ", ".join(old_vis),
                new_vis_str,
                row_status,
                key=tid,
            )

    def _get_selected_thought(self) -> dict[str, Any] | None:
        table = self.query_one("#main-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            try:
                key = list(table.rows.keys())[table.cursor_row]
                tid = str(key.value)
                return next((t for t in self.thoughts if t["id"] == tid), None)
            except (IndexError, StopIteration):
                return None
        return None

    def action_scan(self) -> None:
        self._run_scan()

    @work(thread=True)
    def _run_scan(self) -> None:
        status = self.query_one("#status-bar", Label)
        prompt_text: str = self.prompt_info.get("prompt_template_text", "")
        model: str = self.prompt_info.get("model_string", "")
        prompt_id: str = self.prompt_info.get("prompt_template_id", "")

        total = len(self.thoughts)
        scanned = 0
        errors = 0

        for i, t in enumerate(self.thoughts):
            tid: str = t["id"]
            if tid in self.scan_results:
                scanned += 1
                continue

            self.call_from_thread(
                status.update,
                f"Scanning {i + 1}/{total} \u2014 {scanned} cached,"
                f" {errors} errors\u2026",
            )
            try:
                new_meta = reclassify_thought(
                    t["content"], prompt_text, model, self.config
                )
                self.scan_results[tid] = new_meta
                scanned += 1

                if scanned % 5 == 0:
                    self.cache["scanned"] = self.scan_results
                    self.cache["prompt_template_id"] = prompt_id
                    save_cache(self.cache, self.cache_path)
                    self.call_from_thread(self._populate_table)
            except Exception:
                errors += 1

        self.cache["scanned"] = self.scan_results
        self.cache["prompt_template_id"] = prompt_id
        save_cache(self.cache, self.cache_path)

        diffs = 0
        for t in self.thoughts:
            tid = t["id"]
            if tid in self.scan_results:
                old_vis = sorted(t.get("metadata", {}).get("visibility", []))
                new_vis = sorted(
                    apply_tag_rules(
                        self.scan_results[tid].get("visibility", []),
                        self.tag_rules,
                    )
                )
                if old_vis != new_vis:
                    diffs += 1

        self.call_from_thread(self._populate_table)
        self.call_from_thread(
            status.update,
            f"Scan done: {scanned} scanned, {diffs} diffs,"
            f" {errors} errors | [enter]review [a]ll [q]uit",
        )

    def action_review_selected(self) -> None:
        thought = self._get_selected_thought()
        if not thought:
            return
        tid: str = thought["id"]
        new_meta = self.scan_results.get(tid)
        if not new_meta:
            self._scan_and_review(thought)
            return
        self.push_screen(
            ReviewScreen(thought, new_meta, self.tag_rules, self.config),
            callback=self._on_review_done,
        )

    @work(thread=True)
    def _scan_and_review(self, thought: dict[str, Any]) -> None:
        status = self.query_one("#status-bar", Label)
        self.call_from_thread(status.update, "Classifying thought\u2026")
        try:
            new_meta = reclassify_thought(
                thought["content"],
                self.prompt_info.get("prompt_template_text", ""),
                self.prompt_info.get("model_string", ""),
                self.config,
            )
            self.scan_results[thought["id"]] = new_meta
            self.cache["scanned"] = self.scan_results
            self.cache["prompt_template_id"] = self.prompt_info.get(
                "prompt_template_id", ""
            )
            save_cache(self.cache, self.cache_path)
            self.call_from_thread(self._populate_table)
            self.call_from_thread(
                self.push_screen,
                ReviewScreen(thought, new_meta, self.tag_rules, self.config),
                self._on_review_done,
            )
        except Exception as exc:
            self.call_from_thread(status.update, f"Error: {exc}")

    def _on_review_done(self, result: str | None) -> None:
        if result in ("saved", "verified"):
            thought = self._get_selected_thought()
            if thought and thought["id"] in self.scan_results:
                del self.scan_results[thought["id"]]
                self.cache["scanned"] = self.scan_results
                save_cache(self.cache, self.cache_path)
            self._populate_table()
            status = self.query_one("#status-bar", Label)
            status.update(f"Thought {result}. | [enter]review [a]ll [s]can [q]uit")

    def action_review_all(self) -> None:
        """Review all thoughts that have diffs, one by one."""
        self._review_next_diff()

    def _review_next_diff(self) -> None:
        for t in self.thoughts:
            tid: str = t["id"]
            if tid in self.scan_results:
                old_vis = sorted(t.get("metadata", {}).get("visibility", []))
                new_vis = sorted(
                    apply_tag_rules(
                        self.scan_results[tid].get("visibility", []),
                        self.tag_rules,
                    )
                )
                if old_vis != new_vis:
                    self.push_screen(
                        ReviewScreen(
                            t,
                            self.scan_results[tid],
                            self.tag_rules,
                            self.config,
                        ),
                        callback=self._on_review_all_done,
                    )
                    return
        status = self.query_one("#status-bar", Label)
        status.update("No more diffs to review!")

    def _on_review_all_done(self, result: str | None) -> None:
        self._on_review_done(result)
        if result is not None:
            self._review_next_diff()

    def action_refresh(self) -> None:
        self._load_data()

    def action_clear_cache(self) -> None:
        self.scan_results = {}
        self.cache = {"scanned": {}, "prompt_template_id": None}
        save_cache(self.cache, self.cache_path)
        self._populate_table()
        status = self.query_one("#status-bar", Label)
        status.update("Cache cleared.")


def main() -> None:
    """Entry point: validate config and launch TUI."""
    config = get_config()
    missing = []
    if not config["supabase_url"]:
        missing.append("SUPABASE_URL")
    if not config["supabase_key"]:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not config["openrouter_api_key"]:
        missing.append("OPENROUTER_API_KEY")
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Export them before running this tool.")
        sys.exit(1)

    app = VisibilityReviewApp(config)
    app.run()


if __name__ == "__main__":
    main()
