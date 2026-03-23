---
name: pre-commit usage
description: How to run pre-commit in this repo — stage files, set XDG_CACHE_HOME, then run `pre-commit`
type: feedback
---

Run pre-commit as: `git add file1 file2 && XDG_CACHE_HOME="$(git rev-parse --show-toplevel)/.cache/" pre-commit`

**Why:** The repo contains code that doesn't yet conform to the linting/formatting standard. Using `--all-files` or similar flags causes noisy diffs and distraction from unrelated files. Only check the files you actually changed.
**How to apply:** Always use this exact command pattern. Do NOT pass `--all-files`, `--files`, or other flags. Also check `tools/AGENTS.md` for full coding standards.
