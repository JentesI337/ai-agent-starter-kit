from __future__ import annotations

from dataclasses import dataclass

from app.errors import GuardrailViolation
from app.services.request_normalization import normalize_queue_mode

REASONING_LEVEL_VALUES = ("low", "medium", "high", "ultrathink", "adaptive")
REASONING_VISIBILITY_VALUES = ("off", "summary", "stream")


@dataclass(frozen=True)
class DirectiveOverrides:
    queue_mode: str | None = None
    model: str | None = None
    reasoning_level: str | None = None
    reasoning_visibility: str | None = None


@dataclass(frozen=True)
class DirectiveParseResult:
    clean_content: str
    overrides: DirectiveOverrides
    applied: tuple[str, ...]


def normalize_reasoning_level(value: str | None, *, default: str = "medium") -> str:
    normalized_default = (default or "medium").strip().lower() or "medium"
    if normalized_default not in REASONING_LEVEL_VALUES:
        normalized_default = "medium"

    normalized = (value or "").strip().lower()
    if not normalized:
        return normalized_default
    if normalized not in REASONING_LEVEL_VALUES:
        raise GuardrailViolation(
            "Unsupported reasoning level. Allowed values: low, medium, high, ultrathink, adaptive."
        )
    return normalized


def normalize_reasoning_visibility(value: str | None, *, default: str = "off") -> str:
    normalized_default = (default or "off").strip().lower() or "off"
    if normalized_default not in REASONING_VISIBILITY_VALUES:
        normalized_default = "off"

    normalized = (value or "").strip().lower()
    if not normalized:
        return normalized_default
    if normalized not in REASONING_VISIBILITY_VALUES:
        raise GuardrailViolation(
            "Unsupported reasoning visibility. Allowed values: off, summary, stream."
        )
    return normalized


def _parse_directive(line: str, *, queue_mode_default: str) -> tuple[str, str | None, str | None]:
    source = line.strip()
    if not source.startswith("/"):
        raise GuardrailViolation("Directive lines must start with '/'.")

    command, _, raw_value = source[1:].partition(" ")
    directive = command.strip().lower()
    value = raw_value.strip() or None

    if directive == "queue":
        normalized = normalize_queue_mode(value, default=queue_mode_default)
        return "queue_mode", normalized, "/queue"

    if directive == "model":
        if not value:
            raise GuardrailViolation("Directive /model requires a non-empty value.")
        return "model", value, "/model"

    if directive == "reasoning":
        normalized = normalize_reasoning_level(value)
        return "reasoning_level", normalized, "/reasoning"

    if directive == "verbose":
        normalized_verbose = (value or "").strip().lower()
        if normalized_verbose in {"on", "summary"}:
            visibility = "summary"
        elif normalized_verbose in {"off", "none"}:
            visibility = "off"
        elif normalized_verbose == "stream":
            visibility = "stream"
        else:
            raise GuardrailViolation("Directive /verbose supports: on, off, summary, stream.")
        return "reasoning_visibility", visibility, "/verbose"

    raise GuardrailViolation(f"Unsupported directive: /{directive}")


def parse_directives_from_message(message: str, *, queue_mode_default: str = "wait") -> DirectiveParseResult:
    source = message or ""
    lines = source.splitlines()

    if not lines:
        return DirectiveParseResult(clean_content=source, overrides=DirectiveOverrides(), applied=())

    cursor = 0
    applied: list[str] = []
    values: dict[str, str] = {}
    consumed_any = False

    while cursor < len(lines):
        raw_line = lines[cursor]
        stripped = raw_line.strip()
        if not stripped:
            if consumed_any:
                cursor += 1
                continue
            break
        if not raw_line.lstrip().startswith("/"):
            break

        key, normalized_value, directive_name = _parse_directive(raw_line, queue_mode_default=queue_mode_default)
        if normalized_value is not None:
            values[key] = normalized_value
        applied.append(directive_name)
        consumed_any = True
        cursor += 1

    if not consumed_any:
        return DirectiveParseResult(clean_content=source, overrides=DirectiveOverrides(), applied=())

    remainder = "\n".join(lines[cursor:]).strip()
    if not remainder:
        raise GuardrailViolation("Directive-only message is not allowed. Provide task content after directives.")

    overrides = DirectiveOverrides(
        queue_mode=values.get("queue_mode"),
        model=values.get("model"),
        reasoning_level=values.get("reasoning_level"),
        reasoning_visibility=values.get("reasoning_visibility"),
    )
    return DirectiveParseResult(clean_content=remainder, overrides=overrides, applied=tuple(applied))
