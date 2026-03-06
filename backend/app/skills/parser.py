from __future__ import annotations

from pathlib import Path

from app.skills.models import SkillDefinition, SkillMetadata


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

    return SkillDefinition(
        name=name,
        description=description,
        file_path=str(file_path),
        base_dir=str(file_path.parent),
        body=body,
        metadata=metadata,
        user_invocable=user_invocable,
        disable_model_invocation=disable_model_invocation,
    )
