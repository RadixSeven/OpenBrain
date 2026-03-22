```python
"""Type definitions for JSON data structures.
JSON has a well-defined structure that should be properly typed rather than
using Any. This module provides type aliases for JSON values.
"""
# JSON value types (recursive definition)
# A JSON value can be:
# - null (None)
# - boolean (bool)
# - number (int or float)
# - string (str)
# - array (list of JSON values)
# - object (dict with string keys and JSON values)                                                                                  
type JsonValue = None | bool | int | float | str | list[JsonValue] | JsonObject
type JsonObject = dict[str, JsonValue]                                         
```
