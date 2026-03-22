You are not done with a change until all tests pass and all pre-commit checks pass on the modified files.
Prioritize type safety. Use the static analysis tools to catch mistakes.
Do not use dict as a substitute for a class. Prefer `dataclass` or `NamedTuple`.
Parse JSON into [`JsonValue`](json_value.md) rather than `dict[str, Any]`
Avoid `Any` and `type: ignore`.
Test everything including UI and defensive code. If behavior is not tested, we can't rely on it working.
If code is hard to test, then it's hard to maintain. So, if code is very complicated to test,
it probably needs to be refactored.
