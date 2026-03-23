---
name: test-first for bugs and expected behavior
description: Always write a failing test before fixing a bug; test all keybindings/expected behaviors comprehensively, not just the one that broke
type: feedback
---

Before fixing a bug, write a test that catches it (and fails). Don't fix first then add the test after.

Also: when a class of behavior is untested (e.g., keybindings tested via direct method calls instead of `pilot.press()`), add comprehensive coverage for *all* instances, not just the one that broke.

**Why:** The user considers this trivially expected behavior — testing through the real input path should be the default, not an afterthought.

**How to apply:** When encountering a bug, always (1) write the failing test first, (2) confirm it fails, (3) then fix. When you discover a gap in test coverage, fill the entire gap, not just the specific case.
