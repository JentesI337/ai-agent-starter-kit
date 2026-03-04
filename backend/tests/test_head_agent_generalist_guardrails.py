from __future__ import annotations

from pathlib import Path


BLOCKED_TOKENS = (
    "head-coder",
    "headcodingagent",
    "headcoderagentadapter",
    "head coding agent foundation",
    "switch to a coding-capable profile",
    "head agent delegated this request to",
)


def _iter_guarded_files(repo_root: Path) -> list[Path]:
    guarded: list[Path] = [
        repo_root / "README.md",
        repo_root / "backend" / "README.md",
        repo_root / "backend" / "monitoring" / "eval_golden_suite.json",
    ]

    app_files = (repo_root / "backend" / "app").rglob("*.py")
    test_files = (repo_root / "backend" / "tests").rglob("test_*.py")

    guarded.extend(app_files)
    guarded.extend(test_files)
    return [path for path in guarded if path.exists() and path.is_file()]


def test_head_agent_generalist_wording_guardrails() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    self_path = Path(__file__).resolve()
    violations: list[str] = []

    for file_path in _iter_guarded_files(repo_root):
        if file_path.resolve() == self_path:
            continue
        text = file_path.read_text(encoding="utf-8").lower()
        for token in BLOCKED_TOKENS:
            if token in text:
                rel = file_path.relative_to(repo_root).as_posix()
                violations.append(f"{rel} -> '{token}'")

    assert not violations, "Legacy head/coder framing found:\n" + "\n".join(sorted(violations))