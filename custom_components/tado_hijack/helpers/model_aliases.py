"""Turn mashumaro field names into the aliases from_dict expects.

tadoasync models decode API aliases (``COOL``, ``fanLevel``) and
``to_dict()`` writes the Python names. One pass covers a stored payload
and a fresh ``to_dict()``, including values that are already aliased.
"""

from __future__ import annotations

import dataclasses
import typing
from typing import Any


def _dataclass_of(annotation: Any) -> type | None:
    """Return the dataclass inside an annotation, including Optional."""
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return annotation
    for arg in typing.get_args(annotation):
        if (found := _dataclass_of(arg)) is not None:
            return found
    return None


def with_api_aliases(data: Any, cls: type) -> Any:
    """Rename field names to mashumaro aliases, recursively."""
    if not isinstance(data, dict) or not dataclasses.is_dataclass(cls):
        return data
    hints = typing.get_type_hints(cls)
    out: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        alias = field.metadata.get("alias") or field.name
        if alias in data:
            raw = data[alias]
        elif field.name in data:
            raw = data[field.name]
        else:
            continue
        nested = _dataclass_of(hints.get(field.name))
        out[alias] = with_api_aliases(raw, nested) if nested else raw
    return out
