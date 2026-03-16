---
name: Use virtual environments for pip installs
description: Always use a virtual environment (preferably uv) for Python package installation, never install globally
type: feedback
---

Never install Python packages globally with pip. Always use a virtual environment, preferably with `uv`.

**Why:** User preference for clean, isolated Python environments.
**How to apply:** When a task needs Python dependencies, create a venv with `uv` first.
