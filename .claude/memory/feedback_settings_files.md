---
name: settings.json vs settings.local.json
description: Use settings.json for project-wide config shared via git; settings.local.json for config specific to this local repo copy
type: feedback
---

Use `.claude/settings.json` for configuration that all copies of the repository should share (committed to git, travels with the project). Use `.claude/settings.local.json` for configuration specific to this particular local copy of the repo (e.g., machine-specific paths, local overrides).

**Why:** The project may be cloned on multiple machines or checked out in multiple directories. settings.json ensures consistent behavior everywhere; settings.local.json handles local differences.

**How to apply:** When adding a setting, ask: should every copy of this repo have this? If yes → settings.json. If it's specific to this local copy → settings.local.json.
