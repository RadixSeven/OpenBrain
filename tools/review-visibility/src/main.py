"""
Visibility Review TUI — review and verify LLM-assigned visibility tags on thoughts.

Env vars needed: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENROUTER_API_KEY
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
from models import (
    Config,
    JsonValue,
    PromptInfo,
    ScanCache,
    TagRule,
    Thought,
    ThoughtMetadata,
)
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
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


def get_config() -> Config:
    """Return current config from environment."""
    return Config(
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )


def get_cache_path() -> Path:
    """Return path for scan cache file."""
    return Path(__file__).resolve().parent.parent / ".scan_cache.json"


# ---------------------------------------------------------------------------
# Parsing helpers — confine unsafe JSON→domain conversion
# ---------------------------------------------------------------------------


def _parse_metadata(raw: JsonValue) -> ThoughtMetadata:
    """Parse a JSON value into ThoughtMetadata."""
    if not isinstance(raw, dict):
        return ThoughtMetadata()
    return ThoughtMetadata(
        visibility=_str_list(raw.get("visibility")),
        type=str(raw.get("type", "observation")),
        topics=_str_list(raw.get("topics")),
    )


def _str_list(val: JsonValue) -> list[str]:
    """Extract a list of strings from a JSON value."""
    if not isinstance(val, list):
        return []
    return [str(item) for item in val if isinstance(item, str)]


def _parse_thought(raw: JsonValue) -> Thought:
    """Parse a JSON value into a Thought."""
    if not isinstance(raw, dict):
        msg = f"Expected dict for thought, got {type(raw).__name__}"
        raise ValueError(msg)
    return Thought(
        id=str(raw.get("id", "")),
        content=str(raw.get("content", "")),
        metadata=_parse_metadata(raw.get("metadata")),
        visibility_verified_by_human_at=_opt_str(
            raw.get("visibility_verified_by_human_at")
        ),
        created_at=str(raw.get("created_at", "")),
        submitted_by=str(raw.get("submitted_by", "")),
    )


def _opt_str(val: JsonValue) -> str | None:
    """Convert a JSON value to an optional string."""
    if val is None:
        return None
    return str(val)


def _parse_prompt_info(raw: JsonValue) -> PromptInfo:
    """Parse a JSON value into PromptInfo."""
    if not isinstance(raw, dict):
        return PromptInfo()
    return PromptInfo(
        prompt_template_text=str(raw.get("prompt_template_text", "")),
        model_string=str(raw.get("model_string", "")),
        prompt_template_id=str(raw.get("prompt_template_id", "")),
    )


def _parse_tag_rule(raw: JsonValue) -> TagRule:
    """Parse a JSON value into a TagRule."""
    if not isinstance(raw, dict):
        msg = f"Expected dict for tag rule, got {type(raw).__name__}"
        raise ValueError(msg)
    return TagRule(
        if_present=str(raw.get("if_present", "")),
        remove_tag=str(raw.get("remove_tag", "")),
    )


def _parse_scan_cache(raw: JsonValue) -> ScanCache:
    """Parse a JSON value into a ScanCache."""
    if not isinstance(raw, dict):
        return ScanCache()
    scanned_raw = raw.get("scanned")
    scanned: dict[str, ThoughtMetadata] = {}
    if isinstance(scanned_raw, dict):
        for k, v in scanned_raw.items():
            scanned[k] = _parse_metadata(v)
    pid = raw.get("prompt_template_id")
    return ScanCache(
        scanned=scanned,
        prompt_template_id=str(pid) if pid is not None else None,
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _metadata_to_dict(meta: ThoughtMetadata) -> dict[str, JsonValue]:
    """Convert ThoughtMetadata to a JSON-compatible dict."""
    return asdict(meta)


# ---------------------------------------------------------------------------
# Supabase / OpenRouter helpers
# ---------------------------------------------------------------------------


def sb_headers(config: Config) -> dict[str, str]:
    """Build Supabase REST headers."""
    return {
        "apikey": config.supabase_key,
        "Authorization": f"Bearer {config.supabase_key}",
        "Content-Type": "application/json",
    }


def sb_url(config: Config, path: str) -> str:
    """Build Supabase REST URL."""
    return f"{config.supabase_url}/rest/v1/{path}"


def sb_rpc(
    config: Config,
    fn: str,
    params: dict[str, str] | None = None,
) -> JsonValue:
    """Call a Supabase RPC function."""
    r = httpx.post(
        f"{config.supabase_url}/rest/v1/rpc/{fn}",
        headers=sb_headers(config),
        json=params or {},
        timeout=30,
    )
    r.raise_for_status()
    return cast(JsonValue, r.json())


def fetch_all_thoughts(config: Config) -> list[Thought]:
    """Fetch all thoughts with their metadata."""
    thoughts: list[Thought] = []
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
        batch: list[JsonValue] = r.json()
        if not batch:
            break
        thoughts.extend(_parse_thought(item) for item in batch)
        if len(batch) < limit:
            break
        offset += limit
    return thoughts


def get_current_prompt(config: Config) -> PromptInfo:
    """Fetch current categorization prompt from DB."""
    result = sb_rpc(config, "get_current_prompt", {"p_type": "categorization"})
    if isinstance(result, list) and result:
        return _parse_prompt_info(result[0])
    return _parse_prompt_info(result)


def fetch_tag_rules(config: Config) -> list[TagRule]:
    """Fetch active tag rules."""
    r = httpx.get(
        sb_url(config, "tag_rules"),
        headers=sb_headers(config),
        params={"select": "if_present,remove_tag", "active": "eq.true"},
        timeout=30,
    )
    r.raise_for_status()
    raw: list[JsonValue] = r.json()
    return [_parse_tag_rule(item) for item in raw]


def apply_tag_rules(
    visibility: list[str],
    rules: list[TagRule],
) -> list[str]:
    """Apply deterministic tag removal rules to a visibility list."""
    result = list(visibility)
    for rule in rules:
        if rule.if_present in result:
            result = [t for t in result if t != rule.remove_tag]
    return result


def reclassify_thought(
    content: str,
    prompt_text: str,
    model: str,
    config: Config,
) -> ThoughtMetadata:
    """Re-run the categorization prompt on a thought."""
    r = httpx.post(
        f"{config.openrouter_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.openrouter_api_key}",
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
    d: JsonValue = r.json()
    try:
        if not isinstance(d, dict):
            raise KeyError  # noqa: TRY301
        choices = d["choices"]
        if not isinstance(choices, list) or not choices:
            raise KeyError  # noqa: TRY301
        first = choices[0]
        if not isinstance(first, dict):
            raise KeyError  # noqa: TRY301
        msg = first["message"]
        if not isinstance(msg, dict):
            raise KeyError  # noqa: TRY301
        text = msg["content"]
        if not isinstance(text, str):
            raise KeyError  # noqa: TRY301
        return _parse_metadata(json.loads(text))
    except (KeyError, json.JSONDecodeError):
        return ThoughtMetadata(
            visibility=["uncategorized"],
            type="observation",
            topics=["uncategorized"],
        )


def update_thought_metadata(
    thought_id: str,
    metadata: ThoughtMetadata,
    config: Config,
) -> None:
    """Update the metadata column for a thought."""
    r = httpx.patch(
        sb_url(config, "thoughts"),
        headers={**sb_headers(config), "Prefer": "return=minimal"},
        params={"id": f"eq.{thought_id}"},
        json={
            "metadata": _metadata_to_dict(metadata),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        timeout=30,
    )
    r.raise_for_status()


def verify_thought(
    thought_id: str,
    metadata: ThoughtMetadata,
    config: Config,
) -> None:
    """Update metadata and set visibility_verified_by_human_at."""
    now = datetime.now(UTC).isoformat()
    r = httpx.patch(
        sb_url(config, "thoughts"),
        headers={**sb_headers(config), "Prefer": "return=minimal"},
        params={"id": f"eq.{thought_id}"},
        json={
            "metadata": _metadata_to_dict(metadata),
            "updated_at": now,
            "visibility_verified_by_human_at": now,
        },
        timeout=30,
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Cache helpers — allow resuming scans
# ---------------------------------------------------------------------------


def load_cache(cache_path: Path) -> ScanCache:
    """Load scan cache from disk."""
    if cache_path.exists():
        return _parse_scan_cache(json.loads(cache_path.read_text()))
    return ScanCache()


def save_cache(cache: ScanCache, cache_path: Path) -> None:
    """Persist scan cache to disk."""
    data = {
        "scanned": {k: asdict(v) for k, v in cache.scanned.items()},
        "prompt_template_id": cache.prompt_template_id,
    }
    cache_path.write_text(json.dumps(data, indent=2, default=str))


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
        thought: Thought,
        new_meta: ThoughtMetadata,
        tag_rules: list[TagRule],
        config: Config,
    ) -> None:
        super().__init__()
        self.thought = thought
        self.new_meta = new_meta
        self.tag_rules = tag_rules
        self.config = config

    def compose(self) -> ComposeResult:
        old_vis = sorted(self.thought.metadata.visibility)
        new_vis_raw = sorted(self.new_meta.visibility)
        new_vis = sorted(apply_tag_rules(new_vis_raw, self.tag_rules))

        created = self.thought.created_at[:19]
        verified = self.thought.visibility_verified_by_human_at
        verified_str = verified[:19] if verified else "never"

        with Vertical(id="review-dialog"):
            yield Label(
                f"[b]Thought[/b] ({created})  verified: {verified_str}",
                markup=True,
            )
            yield Static(self.thought.content, id="thought-content")

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

    def _build_updated_metadata(self) -> ThoughtMetadata:
        vis = self._parse_visibility()
        meta = ThoughtMetadata(
            visibility=vis,
            type=self.thought.metadata.type,
            topics=list(self.thought.metadata.topics),
        )
        return meta

    @on(Button.Pressed, "#btn-save")
    def on_save(self) -> None:
        meta = self._build_updated_metadata()
        update_thought_metadata(self.thought.id, meta, self.config)
        self.dismiss("saved")

    @on(Button.Pressed, "#btn-verify")
    def on_verify(self) -> None:
        meta = self._build_updated_metadata()
        verify_thought(self.thought.id, meta, self.config)
        self.dismiss("verified")

    @on(Button.Pressed, "#btn-skip")
    def on_skip(self) -> None:
        self.dismiss("skipped")

    @on(Button.Pressed, "#btn-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class ThoughtDetailScreen(ModalScreen[str | None]):
    """Read-focused detail view for a single thought."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    CSS = """
    ThoughtDetailScreen {
        align: center middle;
    }
    #detail-dialog {
        width: 90%;
        height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #detail-header {
        height: auto;
        margin-bottom: 1;
    }
    #detail-meta {
        height: auto;
        margin-bottom: 1;
        background: $boost;
        padding: 1;
    }
    #detail-content-scroll {
        height: 1fr;
        margin-bottom: 1;
    }
    #detail-content {
        height: auto;
        padding: 1;
    }
    #detail-buttons {
        height: 3;
        align: center middle;
    }
    #detail-buttons Button {
        margin: 0 2;
    }
    """

    def __init__(
        self,
        thought: Thought,
        new_meta: ThoughtMetadata | None,
        tag_rules: list[TagRule],
        config: Config,
    ) -> None:
        super().__init__()
        self.thought = thought
        self.new_meta = new_meta
        self.tag_rules = tag_rules
        self.config = config

    def compose(self) -> ComposeResult:
        old_vis = sorted(self.thought.metadata.visibility)
        created = self.thought.created_at[:19]
        verified = self.thought.visibility_verified_by_human_at
        verified_str = verified[:19] if verified else "never"
        thought_type = self.thought.metadata.type
        submitted = self.thought.submitted_by or "unknown"
        topics = ", ".join(self.thought.metadata.topics) or "(none)"

        with Vertical(id="detail-dialog"):
            yield Label(
                f"[b]Created:[/b] {created}  [b]Type:[/b] {thought_type}"
                f"  [b]By:[/b] {submitted}  [b]Verified:[/b] {verified_str}",
                id="detail-header",
                markup=True,
            )

            meta_lines = [
                f"[b]Topics:[/b] {topics}",
                f"[b]Current visibility:[/b] {', '.join(old_vis) or '(none)'}",
            ]
            if self.new_meta is not None:
                new_vis = sorted(
                    apply_tag_rules(sorted(self.new_meta.visibility), self.tag_rules)
                )
                diff_status = "match" if old_vis == new_vis else "DIFF"
                meta_lines.append(
                    f"[b]New visibility:[/b] {', '.join(new_vis) or '(none)'}"
                    f"  [{diff_status}]"
                )

            yield Static(
                "\n".join(meta_lines),
                id="detail-meta",
                markup=True,
            )

            with VerticalScroll(id="detail-content-scroll"):
                yield Static(self.thought.content, id="detail-content")

            with Horizontal(id="detail-buttons"):
                yield Button("Review", id="btn-review", variant="primary")
                yield Button("Close", id="btn-close")

    @on(Button.Pressed, "#btn-review")
    def on_review(self) -> None:
        self.dismiss("review")

    @on(Button.Pressed, "#btn-close")
    def action_close(self) -> None:
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

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self.config = config or get_config()
        self.cache_path = get_cache_path()
        self.thoughts: list[Thought] = []
        self.cache: ScanCache = load_cache(self.cache_path)
        self.prompt_info: PromptInfo = PromptInfo()
        self.tag_rules: list[TagRule] = []
        self.scan_results: dict[str, ThoughtMetadata] = {}

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
            if self.cache.prompt_template_id == self.prompt_info.prompt_template_id:
                self.scan_results = dict(self.cache.scanned)
            else:
                self.scan_results = {}

            self.call_from_thread(self._populate_table)
            n = len(self.thoughts)
            cached = len(self.scan_results)
            model = self.prompt_info.model_string or "?"
            self.call_from_thread(
                status.update,
                f"{n} thoughts | {cached} cached scans | model: {model}"
                " | [s]can [enter]review [a]ll [q]uit",
            )
        except Exception as exc:
            self.call_from_thread(status.update, f"Error: {exc}")

    def _populate_table(self, *, width_override: int | None = None) -> None:
        table = self.query_one("#main-table", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"

        width = width_override if width_override is not None else self.size.width
        # Fixed-width columns: Created(10) + Status(8) + cell padding (2*5) + separators
        fixed = 10 + 8 + 10 + 6  # = 34
        remaining = max(0, width - fixed)
        # Split remaining: Content ~50%, Current Vis and New Vis ~25% each
        content_w = max(20, remaining * 50 // 100)
        vis_w = max(10, remaining * 25 // 100)

        table.add_column("Created", width=10)
        table.add_column("Content", width=content_w)
        table.add_column("Current Vis", width=vis_w)
        table.add_column("New Vis", width=vis_w)
        table.add_column("Status", width=8)

        content_max = content_w

        for t in self.thoughts:
            old_vis = sorted(t.metadata.visibility)
            created = t.created_at[:10]
            flat = " ".join(t.content.split())
            content = (
                (flat[:content_max] + "\u2026") if len(flat) > content_max else flat
            )

            new_vis: list[str] = []
            if t.id in self.scan_results:
                new_vis_raw = sorted(self.scan_results[t.id].visibility)
                new_vis = sorted(apply_tag_rules(new_vis_raw, self.tag_rules))
                row_status = "match" if old_vis == new_vis else "DIFF"
            elif t.visibility_verified_by_human_at:
                row_status = "verified"
            else:
                row_status = "\u2014"

            old_vis_str = ", ".join(old_vis)
            if len(old_vis_str) > vis_w:
                old_vis_str = old_vis_str[: vis_w - 1] + "\u2026"

            new_vis_str = ", ".join(new_vis) if t.id in self.scan_results else "\u2014"
            if len(new_vis_str) > vis_w:
                new_vis_str = new_vis_str[: vis_w - 1] + "\u2026"

            table.add_row(
                created,
                content,
                old_vis_str,
                new_vis_str,
                row_status,
                key=t.id,
            )

    def _get_selected_thought(self) -> Thought | None:
        table = self.query_one("#main-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            try:
                key = list(table.rows.keys())[table.cursor_row]
                tid = str(key.value)
                return next((t for t in self.thoughts if t.id == tid), None)
            except (IndexError, StopIteration):
                return None
        return None

    def action_scan(self) -> None:
        self._run_scan()

    @work(thread=True)
    def _run_scan(self) -> None:
        status = self.query_one("#status-bar", Label)
        prompt_text = self.prompt_info.prompt_template_text
        model = self.prompt_info.model_string
        prompt_id = self.prompt_info.prompt_template_id

        total = len(self.thoughts)
        scanned = 0
        errors = 0

        for i, t in enumerate(self.thoughts):
            if t.id in self.scan_results:
                scanned += 1
                continue

            self.call_from_thread(
                status.update,
                f"Scanning {i + 1}/{total} \u2014 {scanned} cached,"
                f" {errors} errors\u2026",
            )
            try:
                new_meta = reclassify_thought(
                    t.content, prompt_text, model, self.config
                )
                self.scan_results[t.id] = new_meta
                scanned += 1

                if scanned % 5 == 0:
                    self.cache.scanned = self.scan_results
                    self.cache.prompt_template_id = prompt_id
                    save_cache(self.cache, self.cache_path)
                    self.call_from_thread(self._populate_table)
            except Exception:
                errors += 1

        self.cache.scanned = self.scan_results
        self.cache.prompt_template_id = prompt_id
        save_cache(self.cache, self.cache_path)

        diffs = 0
        for t in self.thoughts:
            if t.id in self.scan_results:
                old_vis = sorted(t.metadata.visibility)
                new_vis = sorted(
                    apply_tag_rules(
                        self.scan_results[t.id].visibility,
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
        new_meta = self.scan_results.get(thought.id)
        self.push_screen(
            ThoughtDetailScreen(thought, new_meta, self.tag_rules, self.config),
            callback=self._on_detail_done,
        )

    def _on_detail_done(self, result: str | None) -> None:
        if result != "review":
            return
        thought = self._get_selected_thought()
        if not thought:
            return
        new_meta = self.scan_results.get(thought.id)
        if not new_meta:
            self._scan_and_review(thought)
            return
        self.push_screen(
            ReviewScreen(thought, new_meta, self.tag_rules, self.config),
            callback=self._on_review_done,
        )

    @work(thread=True)
    def _scan_and_review(self, thought: Thought) -> None:
        status = self.query_one("#status-bar", Label)
        self.call_from_thread(status.update, "Classifying thought\u2026")
        try:
            new_meta = reclassify_thought(
                thought.content,
                self.prompt_info.prompt_template_text,
                self.prompt_info.model_string,
                self.config,
            )
            self.scan_results[thought.id] = new_meta
            self.cache.scanned = self.scan_results
            self.cache.prompt_template_id = self.prompt_info.prompt_template_id
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
            if thought and thought.id in self.scan_results:
                del self.scan_results[thought.id]
                self.cache.scanned = self.scan_results
                save_cache(self.cache, self.cache_path)
            self._populate_table()
            status = self.query_one("#status-bar", Label)
            status.update(f"Thought {result}. | [enter]review [a]ll [s]can [q]uit")

    def action_review_all(self) -> None:
        """Review all thoughts that have diffs, one by one."""
        self._review_next_diff()

    def _review_next_diff(self) -> None:
        for t in self.thoughts:
            if t.id in self.scan_results:
                old_vis = sorted(t.metadata.visibility)
                new_vis = sorted(
                    apply_tag_rules(
                        self.scan_results[t.id].visibility,
                        self.tag_rules,
                    )
                )
                if old_vis != new_vis:
                    self.push_screen(
                        ReviewScreen(
                            t,
                            self.scan_results[t.id],
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

    def on_resize(self, event: events.Resize) -> None:
        if self.thoughts:
            self._populate_table(width_override=event.size.width)

    def action_refresh(self) -> None:
        self._load_data()

    def action_clear_cache(self) -> None:
        self.scan_results = {}
        self.cache = ScanCache()
        save_cache(self.cache, self.cache_path)
        self._populate_table()
        status = self.query_one("#status-bar", Label)
        status.update("Cache cleared.")


def main() -> None:
    """Entry point: validate config and launch TUI."""
    config = get_config()
    missing = []
    if not config.supabase_url:
        missing.append("SUPABASE_URL")
    if not config.supabase_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not config.openrouter_api_key:
        missing.append("OPENROUTER_API_KEY")
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Export them before running this tool.")
        sys.exit(1)

    app = VisibilityReviewApp(config)
    app.run()


if __name__ == "__main__":
    main()
