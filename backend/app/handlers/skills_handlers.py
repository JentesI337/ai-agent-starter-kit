from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from fastapi import HTTPException

from app.config import settings
from app.control_models import (
    ControlSkillsCheckRequest,
    ControlSkillsListRequest,
    ControlSkillsPreviewRequest,
    ControlSkillsSyncRequest,
)
from app.skills.discovery import discover_skills
from app.skills.eligibility import filter_eligible_skills
from app.skills.snapshot import build_skill_snapshot

logger = logging.getLogger("app.skills_handlers")


@dataclass
class SkillsHandlerDependencies:
    pass


def configure(_deps: SkillsHandlerDependencies | None = None) -> None:
    return None


def _build_skills_list(*, skills_dir: str | None = None, max_discovered: int | None = None) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, rejected = filter_eligible_skills(discovered)
    eligible_names = {item.name for item in eligible}

    items: list[dict] = []
    for skill in discovered:
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "file_path": skill.file_path,
                "base_dir": skill.base_dir,
                "user_invocable": bool(skill.user_invocable),
                "disable_model_invocation": bool(skill.disable_model_invocation),
                "metadata": {
                    "requires_bins": list(skill.metadata.requires_bins),
                    "requires_env": list(skill.metadata.requires_env),
                    "os": list(skill.metadata.os),
                },
                "eligible": skill.name in eligible_names,
                "rejected_reason": rejected.get(skill.name),
            }
        )

    return {
        "schema": "skills.list.v1",
        "count": len(items),
        "discovered_count": len(discovered),
        "eligible_count": len(eligible),
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "items": items,
    }


def _build_skills_preview(
    *,
    skills_dir: str | None = None,
    max_discovered: int | None = None,
    max_prompt_chars: int | None = None,
) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))
    resolved_max_prompt_chars = max(1000, int(max_prompt_chars or settings.skills_max_prompt_chars))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, _ = filter_eligible_skills(discovered)
    snapshot = build_skill_snapshot(
        discovered=discovered,
        eligible=eligible,
        max_prompt_chars=resolved_max_prompt_chars,
    )

    return {
        "schema": "skills.preview.v1",
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "max_prompt_chars": resolved_max_prompt_chars,
        "snapshot": {
            "discovered_count": snapshot.discovered_count,
            "eligible_count": snapshot.eligible_count,
            "selected_count": snapshot.selected_count,
            "truncated": snapshot.truncated,
            "skills": list(snapshot.skills),
            "prompt": snapshot.prompt,
        },
    }


def _build_skills_check(*, skills_dir: str | None = None, max_discovered: int | None = None) -> dict:
    resolved_skills_dir = (skills_dir or "").strip() or settings.skills_dir
    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))

    discovered = discover_skills(
        skills_root=resolved_skills_dir,
        max_discovered=resolved_max_discovered,
    )
    eligible, rejected = filter_eligible_skills(discovered)

    missing_env: dict[str, list[str]] = {}
    missing_bins: dict[str, list[str]] = {}
    os_mismatch: dict[str, list[str]] = {}

    for skill in discovered:
        reasons: list[str] = []
        reason = rejected.get(skill.name)
        if reason:
            reasons.append(reason)
        for item in reasons:
            if item.startswith("missing_env:"):
                missing_env.setdefault(skill.name, []).append(item.split(":", 1)[1])
            elif item.startswith("missing_bin:"):
                missing_bins.setdefault(skill.name, []).append(item.split(":", 1)[1])
            elif item.startswith("os_mismatch:"):
                os_mismatch.setdefault(skill.name, []).append(item.split(":", 1)[1])

    return {
        "schema": "skills.check.v1",
        "skills_dir": resolved_skills_dir,
        "max_discovered": resolved_max_discovered,
        "discovered_count": len(discovered),
        "eligible_count": len(eligible),
        "ineligible_count": max(0, len(discovered) - len(eligible)),
        "issues": {
            "missing_env": missing_env,
            "missing_bins": missing_bins,
            "os_mismatch": os_mismatch,
        },
        "rejected": rejected,
    }


def _build_skills_sync(
    *,
    source_skills_dir: str | None = None,
    target_skills_dir: str | None = None,
    max_discovered: int | None = None,
    max_sync_items: int = 200,
    apply: bool = False,
    clean_target: bool = False,
    confirm_clean_target: bool = False,
) -> dict:
    started_at = datetime.now(timezone.utc)
    started_monotonic = monotonic()
    workspace_root = Path(settings.workspace_root).resolve()

    source_raw = (source_skills_dir or "").strip() or settings.skills_dir
    source_path = Path(source_raw)
    if not source_path.is_absolute():
        source_path = (workspace_root / source_path).resolve()
    else:
        source_path = source_path.resolve()

    target_raw = (target_skills_dir or "").strip() or "skills_synced"
    target_path = Path(target_raw)
    if not target_path.is_absolute():
        target_path = (workspace_root / target_path).resolve()
    else:
        target_path = target_path.resolve()

    try:
        target_path.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="target_skills_dir must be inside workspace_root") from exc

    if source_path == target_path:
        raise HTTPException(status_code=400, detail="source_skills_dir and target_skills_dir must differ")
    if not source_path.exists() or not source_path.is_dir():
        raise HTTPException(status_code=400, detail="source_skills_dir not found or not a directory")

    resolved_max_discovered = max(1, int(max_discovered or settings.skills_max_discovered))
    resolved_max_sync_items = max(1, min(int(max_sync_items), 1000))

    if clean_target and apply and not confirm_clean_target:
        raise HTTPException(
            status_code=400,
            detail="clean_target apply requires confirm_clean_target=true",
        )

    discovered = discover_skills(
        skills_root=str(source_path),
        max_discovered=resolved_max_discovered,
    )
    eligible, _ = filter_eligible_skills(discovered)

    actions: list[dict] = []
    used_dirs: set[str] = set()
    for skill in eligible:
        base_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill.name).strip("-") or "skill"
        candidate = base_name
        suffix = 2
        while candidate.lower() in used_dirs:
            candidate = f"{base_name}-{suffix}"
            suffix += 1
        used_dirs.add(candidate.lower())

        destination = target_path / candidate
        action = "create" if not destination.exists() else "update"
        actions.append(
            {
                "skill_name": skill.name,
                "action": action,
                "source_dir": skill.base_dir,
                "target_dir": str(destination),
            }
        )
        if len(actions) >= resolved_max_sync_items:
            break

    if clean_target and target_path.exists() and target_path.is_dir() and len(actions) < resolved_max_sync_items:
        for child in sorted(target_path.iterdir(), key=lambda item: item.name.lower()):
            if len(actions) >= resolved_max_sync_items:
                break
            if not child.is_dir():
                continue
            if child.name.lower() in used_dirs:
                continue
            if not (child / "SKILL.md").exists():
                continue
            actions.append(
                {
                    "skill_name": child.name,
                    "action": "delete",
                    "source_dir": None,
                    "target_dir": str(child),
                }
            )

    planned_delete_count = sum(1 for item in actions if item["action"] == "delete")
    planned_upsert_count = len(actions) - planned_delete_count

    applied_count = 0
    applied_delete_count = 0
    if apply:
        target_path.mkdir(parents=True, exist_ok=True)
        for item in actions:
            action = str(item.get("action", ""))
            dst = Path(str(item["target_dir"]))

            if action == "delete":
                if dst.exists():
                    shutil.rmtree(dst)
                    applied_count += 1
                    applied_delete_count += 1
                continue

            src_value = item.get("source_dir")
            if src_value is None:
                continue
            src = Path(str(src_value))
            if dst.exists():
                shutil.rmtree(dst)
            try:
                shutil.copytree(src, dst, symlinks=True)
            except OSError:
                if os.name != "nt":
                    raise
                shutil.copytree(src, dst, symlinks=False)
            applied_count += 1

    duration_ms = int((monotonic() - started_monotonic) * 1000)
    logger.info(
        "skills_sync_audit mode=%s source=%s target=%s clean_target=%s planned=%s planned_upsert=%s planned_delete=%s applied=%s applied_delete=%s duration_ms=%s",
        "apply" if apply else "dry_run",
        source_path,
        target_path,
        clean_target,
        len(actions),
        planned_upsert_count,
        planned_delete_count,
        applied_count,
        applied_delete_count,
        duration_ms,
    )

    return {
        "schema": "skills.sync.v1",
        "mode": "apply" if apply else "dry_run",
        "source_skills_dir": str(source_path),
        "target_skills_dir": str(target_path),
        "clean_target": clean_target,
        "max_discovered": resolved_max_discovered,
        "max_sync_items": resolved_max_sync_items,
        "eligible_count": len(eligible),
        "planned_count": len(actions),
        "planned_upsert_count": planned_upsert_count,
        "planned_delete_count": planned_delete_count,
        "applied_count": applied_count,
        "applied_delete_count": applied_delete_count,
        "audit": {
            "started_at": started_at.isoformat(),
            "duration_ms": duration_ms,
        },
        "actions": actions,
        "guardrails": {
            "target_must_be_within_workspace": True,
            "max_sync_items_cap": 1000,
            "clean_target_requires_confirmation_for_apply": True,
            "clean_target_deletes_only_skill_dirs": True,
        },
    }


def api_control_skills_list(request_data: dict) -> dict:
    request = ControlSkillsListRequest.model_validate(request_data)
    return _build_skills_list(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
    )


def api_control_skills_preview(request_data: dict) -> dict:
    request = ControlSkillsPreviewRequest.model_validate(request_data)
    return _build_skills_preview(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
        max_prompt_chars=request.max_prompt_chars,
    )


def api_control_skills_check(request_data: dict) -> dict:
    request = ControlSkillsCheckRequest.model_validate(request_data)
    return _build_skills_check(
        skills_dir=request.skills_dir,
        max_discovered=request.max_discovered,
    )


def api_control_skills_sync(request_data: dict) -> dict:
    request = ControlSkillsSyncRequest.model_validate(request_data)
    return _build_skills_sync(
        source_skills_dir=request.source_skills_dir,
        target_skills_dir=request.target_skills_dir,
        max_discovered=request.max_discovered,
        max_sync_items=request.max_sync_items,
        apply=request.apply,
        clean_target=request.clean_target,
        confirm_clean_target=request.confirm_clean_target,
    )
