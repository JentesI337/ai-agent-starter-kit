from __future__ import annotations

import asyncio

from app.services.action_parser import ActionParser


class _FakeChat:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[tuple[str, str, str | None]] = []

    async def __call__(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        self.calls.append((system_prompt, user_prompt, model))
        return self.response


def test_parse_accepts_actions_object() -> None:
    parser = ActionParser()

    actions, error = parser.parse('{"actions":[{"tool":"read_file","args":{"path":"README.md"}}]}')

    assert error is None
    assert actions and actions[0]["tool"] == "read_file"


def test_parse_rejects_non_object_root() -> None:
    parser = ActionParser()

    actions, error = parser.parse('[{"tool":"read_file"}]')

    assert actions == []
    assert error == "LLM JSON root is not an object."


def test_extract_json_candidate_falls_back_for_non_json_text() -> None:
    parser = ActionParser()

    result = parser.extract_json_candidate("tool=>read_file args=>{}")

    assert result == "{}"


def test_repair_calls_complete_chat_with_repair_prompt() -> None:
    parser = ActionParser()
    fake = _FakeChat('{"actions":[]}')

    repaired = asyncio.run(
        parser.repair(
            raw="broken output",
            model="x-model",
            complete_chat=fake,
            system_prompt="repair-system",
        )
    )

    assert repaired == '{"actions":[]}'
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "repair-system"
    assert fake.calls[0][2] == "x-model"
