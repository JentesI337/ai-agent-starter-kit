from __future__ import annotations

import re
from pathlib import Path

from app.skills.models import SkillDefinition, SkillMetadata, ValidationCheck


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    text = raw.lstrip("\ufeff")
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---", 4)
    if end == -1:
        return {}, text

    block = text[4:end].strip()
    body = text[end + 4 :].lstrip("\n")

    data: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip().lower()] = value.strip().strip('"').strip("'")
    return data, body


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    items = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(items)


def _parse_list_field(value: str) -> tuple[str, ...]:
    """Parse a YAML-style list field: ``["a", "b"]`` or ``a, b``."""
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1]
        items = [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]
        return tuple(items)
    return _split_csv(stripped)


def _parse_checks_section(body: str) -> tuple[ValidationCheck, ...]:
    """Parse ``### CHECK-<id>: <title>`` blocks from the body of a validation skill."""
    pattern = re.compile(r"^### CHECK-(\S+):\s*(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    if not matches:
        return ()

    checks: list[ValidationCheck] = []
    for i, m in enumerate(matches):
        check_id = m.group(1)
        title = m.group(2).strip()
        # Extract block text until next CHECK header or end of body
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[start:end]

        fields: dict[str, str] = {}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("- ") and ":" in line:
                key, val = line[2:].split(":", 1)
                fields[key.strip().lower()] = val.strip()

        checks.append(ValidationCheck(
            check_id=check_id,
            title=title,
            severity=fields.get("severity", "medium").lower(),
            grep_patterns=_parse_list_field(fields.get("grep_patterns", "")),
            anti_patterns=_parse_list_field(fields.get("anti_patterns", "")),
            file_globs=_parse_list_field(fields.get("file_globs", "")),
            pass_condition=fields.get("pass_condition", ""),
            guidance=fields.get("guidance", ""),
        ))
    return tuple(checks)


def parse_skill_markdown(file_path: Path) -> SkillDefinition:
    raw = file_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(raw)
    name = frontmatter.get("name") or file_path.parent.name
    description = frontmatter.get("description") or ""

    metadata = SkillMetadata(
        requires_bins=_split_csv(frontmatter.get("requires_bins")),
        requires_env=_split_csv(frontmatter.get("requires_env")),
        os=_split_csv(frontmatter.get("os")),
    )

    user_invocable = frontmatter.get("user_invocable", "true").lower() not in {"false", "0", "no"}
    disable_model_invocation = frontmatter.get("disable_model_invocation", "false").lower() in {
        "true",
        "1",
        "yes",
    }

    skill_type = frontmatter.get("type", "reference").lower()
    checks = _parse_checks_section(body) if skill_type == "validation" else ()

    return SkillDefinition(
        name=name,
        description=description,
        file_path=str(file_path),
        base_dir=str(file_path.parent),
        body=body,
        metadata=metadata,
        user_invocable=user_invocable,
        disable_model_invocation=disable_model_invocation,
        skill_type=skill_type,
        checks=checks,
    )
