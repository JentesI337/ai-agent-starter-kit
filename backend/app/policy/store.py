from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class PolicyDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    also_allow: list[str] = Field(default_factory=list)
    agents: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class PolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    also_allow: list[str] = Field(default_factory=list)
    agents: dict[str, dict[str, list[str]]] = Field(default_factory=dict)


class PolicyStore:
    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[PolicyDefinition]:
        items: list[PolicyDefinition] = []
        for file_path in sorted(self.persist_dir.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                items.append(PolicyDefinition.model_validate(payload))
            except Exception:
                continue
        return items

    def get(self, policy_id: str) -> PolicyDefinition | None:
        target = self._normalize_id(policy_id)
        if not target:
            return None
        file_path = self.persist_dir / f"{target}.json"
        if not file_path.exists():
            return None
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            return PolicyDefinition.model_validate(payload)
        except Exception:
            return None

    def create(self, request: PolicyCreateRequest) -> PolicyDefinition:
        now = datetime.now(UTC).isoformat()
        policy_id = self._normalize_id(request.name) or f"policy-{uuid.uuid4().hex[:8]}"
        # ensure unique
        if (self.persist_dir / f"{policy_id}.json").exists():
            policy_id = f"{policy_id}-{uuid.uuid4().hex[:6]}"

        definition = PolicyDefinition(
            id=policy_id,
            name=request.name.strip(),
            allow=[s.strip() for s in request.allow if s.strip()],
            deny=[s.strip() for s in request.deny if s.strip()],
            also_allow=[s.strip() for s in request.also_allow if s.strip()],
            agents=request.agents,
            created_at=now,
            updated_at=now,
        )
        file_path = self.persist_dir / f"{definition.id}.json"
        file_path.write_text(
            json.dumps(definition.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return definition

    def update(self, policy_id: str, patch: dict) -> PolicyDefinition | None:
        existing = self.get(policy_id)
        if existing is None:
            return None
        merged = existing.model_dump()
        for key, value in patch.items():
            if key in merged and key not in ("id", "created_at"):
                merged[key] = value
        merged["updated_at"] = datetime.now(UTC).isoformat()
        definition = PolicyDefinition.model_validate(merged)
        file_path = self.persist_dir / f"{definition.id}.json"
        file_path.write_text(
            json.dumps(definition.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return definition

    def delete(self, policy_id: str) -> bool:
        target = self._normalize_id(policy_id)
        if not target:
            return False
        file_path = self.persist_dir / f"{target}.json"
        if not file_path.exists():
            return False
        file_path.unlink(missing_ok=True)
        return True

    def _normalize_id(self, raw: str) -> str:
        candidate = (raw or "").strip().lower()
        candidate = re.sub(r"[^a-z0-9_-]+", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate[:80]
