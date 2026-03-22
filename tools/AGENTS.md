Prioritize type safety. Use the static analysis tools to catch mistakes.
Do not use dict as a substitute for a class. Prefer `dataclass` or `NamedTuple`.
Parse JSON into [`JsonValue`](json_value.md) rather than `dict[str, Any]`
Avoid `Any` and `type: ignore`.
