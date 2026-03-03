from __future__ import annotations

from app.services.prompt_kernel_builder import PromptKernelBuilder


def test_prompt_kernel_builder_produces_stable_hash_for_same_input() -> None:
    builder = PromptKernelBuilder()
    kernel_a = builder.build(
        prompt_type="planning",
        prompt_mode="full",
        sections={"instructions": "do x", "task": "implement y"},
    )
    kernel_b = builder.build(
        prompt_type="planning",
        prompt_mode="full",
        sections={"task": "implement y", "instructions": "do x"},
    )

    assert kernel_a.prompt_hash == kernel_b.prompt_hash
    assert kernel_a.kernel_version == "prompt-kernel.v1.1"
    assert kernel_a.section_fingerprints == kernel_b.section_fingerprints


def test_prompt_kernel_builder_truncates_in_minimal_mode() -> None:
    builder = PromptKernelBuilder()
    long_text = "a" * 2500
    kernel = builder.build(
        prompt_type="tool_selection",
        prompt_mode="minimal",
        sections={"memory": long_text, "task": "t"},
    )

    assert "chars truncated for minimal mode" in kernel.rendered
    assert "[prompt_mode=minimal]" in kernel.rendered


def test_prompt_kernel_builder_marks_subagent_scope() -> None:
    builder = PromptKernelBuilder()
    kernel = builder.build(
        prompt_type="synthesis",
        prompt_mode="subagent",
        sections={"task": "finish delegated step"},
    )

    assert "[delegation_scope=child_subrun]" in kernel.rendered


def test_prompt_kernel_builder_orders_sections_by_contract() -> None:
    builder = PromptKernelBuilder()
    kernel = builder.build(
        prompt_type="synthesis",
        prompt_mode="full",
        sections={
            "task": "task",
            "tools": "tools",
            "context": "context",
            "policy": "policy",
            "system": "system",
            "skills": "skills",
            "zzz_extra": "extra",
        },
    )

    order = [
        kernel.rendered.index("## system"),
        kernel.rendered.index("## policy"),
        kernel.rendered.index("## context"),
        kernel.rendered.index("## skills"),
        kernel.rendered.index("## tools"),
        kernel.rendered.index("## task"),
        kernel.rendered.index("## zzz_extra"),
    ]
    assert order == sorted(order)


def test_prompt_kernel_builder_section_fingerprint_changes_only_for_changed_section() -> None:
    builder = PromptKernelBuilder()
    base = builder.build(
        prompt_type="planning",
        prompt_mode="full",
        sections={
            "system": "rules",
            "context": "ctx-a",
            "task": "task-a",
        },
    )
    changed = builder.build(
        prompt_type="planning",
        prompt_mode="full",
        sections={
            "system": "rules",
            "context": "ctx-b",
            "task": "task-a",
        },
    )

    assert base.section_fingerprints["system"] == changed.section_fingerprints["system"]
    assert base.section_fingerprints["task"] == changed.section_fingerprints["task"]
    assert base.section_fingerprints["context"] != changed.section_fingerprints["context"]
