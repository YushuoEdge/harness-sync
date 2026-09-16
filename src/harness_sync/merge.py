"""Three-way owned-field conflict checking independent of a native file format.

Adapters parse/serialize with format-preserving native libraries and pass leaf paths.
Missing desired values remove owned fields; unrelated fields remain unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .errors import ConflictError

MISSING = object()


def get_field(document: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = document
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return MISSING
        value = value[key]
    return value


def merge_fields(
    current: dict[str, Any],
    baseline: Mapping[str, Any] | None,
    changes: Mapping[tuple[str, ...], Any],
) -> dict[str, Any]:
    result = deepcopy(current)
    paths = list(changes)
    if any(not path for path in paths):
        raise ConflictError("Empty owned-field path")
    if any(a != b and b[: len(a)] == a for a in paths for b in paths):
        raise ConflictError("Overlapping owned-field paths")
    for path, desired in changes.items():
        actual = get_field(current, path)
        previous = get_field(baseline, path) if baseline is not None else MISSING
        if baseline is not None and actual != previous and actual != desired:
            raise ConflictError("A managed native field was edited outside harness-sync")
        node = result
        for key in path[:-1]:
            if key not in node:
                if desired is MISSING:
                    break
                node[key] = {}
            if not isinstance(node[key], dict):
                raise ConflictError("Cannot merge through a non-table native setting")
            node = node[key]
        else:
            if desired is MISSING:
                node.pop(path[-1], None)
            else:
                node[path[-1]] = deepcopy(desired)
    return result
