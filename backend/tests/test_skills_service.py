from __future__ import annotations

from app.skills.models import SkillSnapshot
from app.skills.service import SkillsRuntimeConfig, SkillsService


def test_skills_service_returns_empty_snapshot_when_disabled() -> None:
    service = SkillsService(
        SkillsRuntimeConfig(
            enabled=False,
            skills_dir="skills",
            max_discovered=10,
            max_prompt_chars=5000,
        )
    )

    snapshot = service.build_snapshot()

    assert snapshot.prompt == ""
    assert snapshot.discovered_count == 0
    assert snapshot.skills == ()


def test_skills_service_snapshot_cache_uses_ttl(monkeypatch) -> None:
    service = SkillsService(
        SkillsRuntimeConfig(
            enabled=True,
            skills_dir="skills",
            max_discovered=10,
            max_prompt_chars=5000,
            snapshot_cache_ttl_seconds=60,
            snapshot_cache_use_mtime=False,
        )
    )

    calls = {"discover": 0}

    def fake_discover(*, skills_root: str, max_discovered: int):
        _ = (skills_root, max_discovered)
        calls["discover"] += 1
        return [object()]

    def fake_filter(discovered):
        _ = discovered
        return [object()], {}

    def fake_snapshot(*, discovered, eligible, max_prompt_chars: int):
        _ = (discovered, eligible, max_prompt_chars)
        return SkillSnapshot(
            prompt="skills-preview",
            skills=(),
            discovered_count=1,
            eligible_count=1,
            selected_count=1,
            truncated=False,
        )

    monkeypatch.setattr("app.skills.service.discover_skills", fake_discover)
    monkeypatch.setattr("app.skills.service.filter_eligible_skills", fake_filter)
    monkeypatch.setattr("app.skills.service.build_skill_snapshot", fake_snapshot)

    first = service.build_snapshot()
    second = service.build_snapshot()

    assert first.prompt == "skills-preview"
    assert second.prompt == "skills-preview"
    assert calls["discover"] == 1


def test_skills_service_fresh_ttl_cache_skips_signature_scan(monkeypatch) -> None:
    service = SkillsService(
        SkillsRuntimeConfig(
            enabled=True,
            skills_dir="skills",
            max_discovered=10,
            max_prompt_chars=5000,
            snapshot_cache_ttl_seconds=60,
            snapshot_cache_use_mtime=True,
        )
    )

    calls = {"discover": 0, "signature": 0}

    def fake_signature() -> str:
        calls["signature"] += 1
        return "sig-1"

    def fake_discover(*, skills_root: str, max_discovered: int):
        _ = (skills_root, max_discovered)
        calls["discover"] += 1
        return [object()]

    def fake_filter(discovered):
        _ = discovered
        return [object()], {}

    def fake_snapshot(*, discovered, eligible, max_prompt_chars: int):
        _ = (discovered, eligible, max_prompt_chars)
        return SkillSnapshot(
            prompt="skills-preview",
            skills=(),
            discovered_count=1,
            eligible_count=1,
            selected_count=1,
            truncated=False,
        )

    monkeypatch.setattr(service, "_build_mtime_signature", fake_signature)
    monkeypatch.setattr("app.skills.service.discover_skills", fake_discover)
    monkeypatch.setattr("app.skills.service.filter_eligible_skills", fake_filter)
    monkeypatch.setattr("app.skills.service.build_skill_snapshot", fake_snapshot)

    service.build_snapshot()
    service.build_snapshot()

    assert calls["discover"] == 1
    assert calls["signature"] == 1


def test_skills_service_snapshot_cache_invalidates_on_signature_change(monkeypatch) -> None:
    service = SkillsService(
        SkillsRuntimeConfig(
            enabled=True,
            skills_dir="skills",
            max_discovered=10,
            max_prompt_chars=5000,
            snapshot_cache_ttl_seconds=1,
            snapshot_cache_use_mtime=True,
        )
    )

    calls = {"discover": 0}
    signatures = iter(["sig-a", "sig-b"])

    def fake_discover(*, skills_root: str, max_discovered: int):
        _ = (skills_root, max_discovered)
        calls["discover"] += 1
        return [object()]

    def fake_filter(discovered):
        _ = discovered
        return [object()], {}

    def fake_snapshot(*, discovered, eligible, max_prompt_chars: int):
        _ = (discovered, eligible, max_prompt_chars)
        return SkillSnapshot(
            prompt="skills-preview",
            skills=(),
            discovered_count=1,
            eligible_count=1,
            selected_count=1,
            truncated=False,
        )

    monotonic_values = iter([0.0, 2.0, 2.1])

    def fake_monotonic() -> float:
        try:
            return next(monotonic_values)
        except StopIteration:
            return 2.1

    monkeypatch.setattr(service, "_build_mtime_signature", lambda: next(signatures))
    monkeypatch.setattr("app.skills.service.monotonic", fake_monotonic)
    monkeypatch.setattr("app.skills.service.discover_skills", fake_discover)
    monkeypatch.setattr("app.skills.service.filter_eligible_skills", fake_filter)
    monkeypatch.setattr("app.skills.service.build_skill_snapshot", fake_snapshot)

    service.build_snapshot()
    service.build_snapshot()

    assert calls["discover"] == 2
