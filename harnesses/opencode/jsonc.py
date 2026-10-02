"""Conservative concrete-syntax edits: preserve supported syntax or refuse."""

from __future__ import annotations

import json

import json5
import json5kit
from json5kit.nodes import Json5Comma, Json5Newline, Json5Object, Json5Whitespace

from harness_sync.errors import HarnessSyncError
from harness_sync.merge import MISSING, merge_fields


def parse(data):
    try:
        result = json5.loads((data or b"{}").decode(), allow_duplicate_keys=False)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise HarnessSyncError("Invalid native JSON/JSONC/JSON5 configuration") from None


def edit(current, baseline, changes):
    expected = merge_fields(
        parse(current), parse(baseline) if baseline is not None else None, changes
    )
    try:
        tree = json5kit.parse((current or b"{}").decode())
        for keys, desired in changes.items():
            node = tree.value
            for key in keys[:-1]:
                index = next(
                    (i for i, item in enumerate(node.keys) if item.value.value == key), None
                )
                if index is None:
                    if desired is MISSING:
                        node = None
                        break
                    assign(node, key, {})
                    index = len(node.keys) - 1
                node = node.values[index]
                if not isinstance(node, Json5Object):
                    raise ValueError
            if node is not None:
                assign(node, keys[-1], desired)
        rendered = tree.to_source().encode()
        if parse(rendered) != expected:
            raise ValueError
        return rendered
    except Exception as exc:
        if isinstance(exc, HarnessSyncError):
            raise
        raise HarnessSyncError("Native syntax cannot be edited while preserving comments") from None


def assign(node, key, desired):
    index = next((i for i, item in enumerate(node.keys) if item.value.value == key), None)
    if desired is MISSING:
        if index is not None:
            trivia = [
                item
                for item in node.values[index].trailing_trivia_nodes
                if not isinstance(item, Json5Comma)
            ]
            del node.keys[index]
            del node.values[index]
            if index:
                node.values[index - 1].trailing_trivia_nodes.extend(trivia)
            else:
                node.leading_trivia_nodes.extend(trivia)
        return
    replacement = json5kit.parse(json.dumps({key: desired}, ensure_ascii=False, indent=2)).value
    value = replacement.values[0]
    if index is not None:
        value.trailing_trivia_nodes = node.values[index].trailing_trivia_nodes
        node.values[index] = value
        return
    if node.values and not any(
        isinstance(item, Json5Comma) for item in node.values[-1].trailing_trivia_nodes
    ):
        node.values[-1].trailing_trivia_nodes.insert(0, Json5Comma())
    value.trailing_trivia_nodes = [Json5Comma(), Json5Newline(), Json5Whitespace("  ")]
    node.keys.append(replacement.keys[0])
    node.values.append(value)
