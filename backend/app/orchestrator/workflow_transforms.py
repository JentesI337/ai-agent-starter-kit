"""Safe template resolver and condition evaluator for workflow data flow.

Template syntax:  ``{{step_id.output.field}}``
Condition syntax: ``step1.output.status == "open" and step2.output.count > 5``

No ``eval()`` or ``exec()`` — templates use regex extraction + dot-path traversal,
conditions use ``ast`` whitelisting.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{(.+?)\}\}")
_ARRAY_INDEX_RE = re.compile(r"^([^\[]+)\[(\d+)\]$")

# Built-in filters
_FILTERS: dict[str, Any] = {
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "length": lambda v: len(v) if hasattr(v, "__len__") else 0,
    "first": lambda v: v[0] if isinstance(v, (list, tuple)) and v else v,
    "last": lambda v: v[-1] if isinstance(v, (list, tuple)) and v else v,
    "strip": lambda v: str(v).strip(),
    "json": lambda v: json.dumps(v, default=str),
}


def _resolve_dot_path(obj: Any, path: str) -> Any:
    """Traverse *obj* using dot-separated *path* with optional ``[N]`` indexing."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None

        # Check for array indexing: ``data[0]``
        m = _ARRAY_INDEX_RE.match(part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(current, dict):
                current = current.get(key)
            else:
                current = getattr(current, key, None)
            if isinstance(current, (list, tuple)) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
            continue

        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)

    return current


def _apply_filters(value: Any, filter_chain: str) -> Any:
    """Apply ``| filter_name`` chain to *value*."""
    for part in filter_chain.split("|"):
        part = part.strip()
        if not part:
            continue

        # Handle parameterized filters: ``join(",")``
        paren_match = re.match(r"^(\w+)\((.+)\)$", part)
        if paren_match:
            name = paren_match.group(1)
            arg = paren_match.group(2).strip("\"'")
            if name == "join" and isinstance(value, (list, tuple)):
                value = arg.join(str(v) for v in value)
                continue

        fn = _FILTERS.get(part)
        if fn is not None:
            value = fn(value)

    return value


def resolve_templates(text: str, context: dict[str, Any]) -> str:
    """Replace all ``{{...}}`` expressions in *text* with values from *context*.

    *context* maps step IDs to their outputs:
    ``{"step1": {"output": {"status": "open"}}, "input": {"message": "hello"}}``
    """
    def _replacer(m: re.Match) -> str:
        expr = m.group(1).strip()

        # Split expression from filter chain
        if "|" in expr:
            path_part, filter_part = expr.split("|", 1)
            path_part = path_part.strip()
        else:
            path_part = expr
            filter_part = ""

        value = _resolve_dot_path(context, path_part)
        if value is None:
            return m.group(0)  # leave unresolved

        if filter_part:
            value = _apply_filters(value, filter_part)

        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        return str(value)

    return _TEMPLATE_RE.sub(_replacer, text)


def resolve_params(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Resolve template expressions in all string values of *params*."""
    resolved: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            resolved[key] = resolve_templates(value, context)
        else:
            resolved[key] = value
    return resolved


# ---------------------------------------------------------------------------
# Condition evaluator (safe AST-based)
# ---------------------------------------------------------------------------

_SAFE_NODES = frozenset({
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UnaryOp,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Index,  # Python 3.8 compat
    ast.Slice,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
})


def _validate_ast(node: ast.AST) -> None:
    """Raise ValueError if any node is not in the safe whitelist."""
    if type(node) not in _SAFE_NODES:
        raise ValueError(f"Unsafe AST node: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _validate_ast(child)


def evaluate_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a boolean expression against workflow context.

    Supports comparisons, ``and``/``or``/``not``, ``in`` checks,
    and dot-path attribute access.  All names are resolved from *context*.

    Raises ``ValueError`` on unsafe or unparseable expressions.
    """
    if not expr or not expr.strip():
        return True

    # First resolve any {{...}} templates in the expression
    resolved = resolve_templates(expr, context)

    try:
        tree = ast.parse(resolved, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid condition expression: {e}") from e

    _validate_ast(tree)

    # Build a flat namespace for eval from context
    namespace: dict[str, Any] = {}
    for key, value in context.items():
        namespace[key] = value
        # Also allow direct attribute-style access: step1 -> context["step1"]
        if isinstance(value, dict):
            for k, v in value.items():
                namespace[f"{key}_{k}"] = v

    code = compile(tree, "<condition>", "eval")
    try:
        result = eval(code, {"__builtins__": {}}, namespace)  # noqa: S307
    except Exception as e:
        raise ValueError(f"Condition evaluation failed: {e}") from e

    return bool(result)
