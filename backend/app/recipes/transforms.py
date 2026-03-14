"""Safe template resolver and condition evaluator for workflow data flow.

Template syntax:  ``{{step_id.output.field}}``
Condition syntax: ``step1.output.status == "open" and step2.output.count > 5``

Templates use regex extraction + dot-path traversal.
Conditions use a recursive AST interpreter over a whitelisted set of node types —
no ``eval()`` or ``exec()`` is used.
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
    "first": lambda v: v[0] if isinstance(v, (list, tuple, str)) and v else v,
    "last": lambda v: v[-1] if isinstance(v, (list, tuple, str)) and v else v,
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
            current = current.get(key) if isinstance(current, dict) else getattr(current, key, None)
            if isinstance(current, (list, tuple)) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
            continue

        current = current.get(part) if isinstance(current, dict) else getattr(current, part, None)

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


def _interpret(node: ast.AST, namespace: dict[str, Any]) -> Any:
    """Recursively interpret a whitelisted AST node against *namespace*."""
    if isinstance(node, ast.Expression):
        return _interpret(node.body, namespace)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        # SEC: block dunder name access to prevent sandbox escape
        if node.id.startswith('_'):
            raise ValueError(f"Access to private/dunder names not allowed: {node.id}")
        if node.id in namespace:
            return namespace[node.id]
        raise ValueError(f"Unknown name: {node.id}")
    if isinstance(node, ast.Attribute):
        # SEC: block dunder/private attribute access to prevent sandbox escape
        if node.attr.startswith('_'):
            raise ValueError(f"Access to private/dunder attributes not allowed: {node.attr}")
        obj = _interpret(node.value, namespace)
        if isinstance(obj, dict):
            return obj.get(node.attr)
        return getattr(obj, node.attr, None)
    if isinstance(node, ast.Subscript):
        obj = _interpret(node.value, namespace)
        slc = node.slice
        # Python 3.8 wraps in ast.Index
        if isinstance(slc, ast.Index):
            slc = slc.value  # type: ignore[attr-defined]
        idx = _interpret(slc, namespace)
        if isinstance(obj, dict):
            return obj.get(idx)
        if isinstance(obj, (list, tuple)):
            return obj[idx] if isinstance(idx, int) and 0 <= idx < len(obj) else None
        return None
    if isinstance(node, ast.UnaryOp):
        operand = _interpret(node.operand, namespace)
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = _interpret(v, namespace)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for v in node.values:
                result = _interpret(v, namespace)
                if result:
                    return result
            return result
        raise ValueError(f"Unsupported bool op: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _interpret(node.left, namespace)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _interpret(comparator, namespace)
            if isinstance(op, ast.Eq):
                if left != right:
                    return False
            elif isinstance(op, ast.NotEq):
                if left == right:
                    return False
            elif isinstance(op, ast.Lt):
                if not (left < right):
                    return False
            elif isinstance(op, ast.LtE):
                if not (left <= right):
                    return False
            elif isinstance(op, ast.Gt):
                if not (left > right):
                    return False
            elif isinstance(op, ast.GtE):
                if not (left >= right):
                    return False
            elif isinstance(op, ast.In):
                if left not in right:
                    return False
            elif isinstance(op, ast.NotIn):
                if left in right:
                    return False
            elif isinstance(op, ast.Is):
                if left is not right:
                    return False
            elif isinstance(op, ast.IsNot):
                if left is right:
                    return False
            else:
                raise ValueError(f"Unsupported comparison: {type(op).__name__}")
            left = right
        return True
    if isinstance(node, ast.BinOp):
        left = _interpret(node.left, namespace)
        right = _interpret(node.right, namespace)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
    raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def evaluate_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a boolean expression against workflow context.

    Supports comparisons, ``and``/``or``/``not``, ``in`` checks,
    and dot-path attribute access.  All names are resolved from *context*.

    Uses a recursive AST interpreter — no ``eval()`` or ``exec()``.

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

    # Build a flat namespace from context
    namespace: dict[str, Any] = {}
    for key, value in context.items():
        namespace[key] = value
        if isinstance(value, dict):
            for k, v in value.items():
                namespace[f"{key}_{k}"] = v

    try:
        result = _interpret(tree, namespace)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Condition evaluation failed: {e}") from e

    return bool(result)
