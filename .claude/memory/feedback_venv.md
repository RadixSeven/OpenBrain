---
name: Use virtual environments for pip installs
description: Always use a virtual environment (preferably uv) for Python package installation, never install globally. Use project-local UV cache.
type: feedback
---

Never install Python packages globally with pip. Always use a virtual environment, preferably with `uv`.

**Why:** User preference for clean, isolated Python environments. Global caches cause sandbox permission issues.
**How to apply:** When a task needs Python dependencies, create a venv with `uv` first. Set `UV_CACHE_DIR` to a project-local path (e.g. `.uv-cache`) to avoid sandbox permission issues with global cache directories.
