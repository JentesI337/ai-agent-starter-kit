from __future__ import annotations

import asyncio
import gc

import pytest

from app.agents.tool_selector_agent import ToolSelectorAgent
from app.contracts.schemas import ToolSelectorInput


async def _sample_runner(
    user_message: str,
    plan_text: str,
    reduced_context: str,
    session_id: str,
    request_id: str,
    send_event,
    model: str | None,
    allowed_tools: set[str],
) -> str:
    _ = (user_message, plan_text, reduced_context, session_id, request_id, send_event, model, allowed_tools)
    return "ok"


async def _capture_allowed_runner(
    user_message: str,
    plan_text: str,
    reduced_context: str,
    session_id: str,
    request_id: str,
    send_event,
    model: str | None,
    allowed_tools: set[str],
) -> str:
    _ = (user_message, plan_text, reduced_context, session_id, request_id, send_event, model)
    return ",".join(sorted(allowed_tools))


class _BoundRunner:
    async def run(
        self,
        user_message: str,
        plan_text: str,
        reduced_context: str,
        session_id: str,
        request_id: str,
        send_event,
        model: str | None,
        allowed_tools: set[str],
    ) -> str:
        _ = (user_message, plan_text, reduced_context, session_id, request_id, send_event, model, allowed_tools)
        return "bound-ok"


def test_execute_requires_runner_when_not_configured() -> None:
    agent = ToolSelectorAgent()

    with pytest.raises(RuntimeError, match="execute_tools_fn"):
        asyncio.run(
            agent.execute(
                ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
                session_id="s1",
                request_id="r1",
                send_event=lambda _payload: None,
                model=None,
                allowed_tools={"list_dir"},
            )
        )


def test_execute_accepts_inline_runner_without_constructor_wiring() -> None:
    agent = ToolSelectorAgent()

    output = asyncio.run(
        agent.execute(
            ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
            session_id="s1",
            request_id="r1",
            send_event=lambda _payload: None,
            model=None,
            allowed_tools={"list_dir"},
            execute_tools_fn=_sample_runner,
        )
    )

    assert output.tool_results == "ok"


def test_run_uses_configured_runner() -> None:
    agent = ToolSelectorAgent()
    agent.set_execute_tools_fn(_sample_runner)

    output = asyncio.run(
        agent.run(
            '{"user_message":"u","plan_text":"p","reduced_context":"c"}',
            send_event=lambda _payload: None,
            session_id="s1",
            request_id="r1",
            model=None,
        )
    )

    assert output == '{"tool_results": "ok"}'


def test_run_applies_tool_policy_allow_and_deny() -> None:
    agent = ToolSelectorAgent()
    agent.set_execute_tools_fn(_capture_allowed_runner)

    output = asyncio.run(
        agent.run(
            '{"user_message":"u","plan_text":"p","reduced_context":"c"}',
            send_event=lambda _payload: None,
            session_id="s1",
            request_id="r1",
            model=None,
            tool_policy={"allow": ["read_file", "LIST-DIR"], "deny": ["list_dir"]},
        )
    )

    assert output == '{"tool_results": "read_file"}'


def test_run_accepts_inline_runner_without_configured_state() -> None:
    agent = ToolSelectorAgent()

    output = asyncio.run(
        agent.run(
            '{"user_message":"u","plan_text":"p","reduced_context":"c"}',
            send_event=lambda _payload: None,
            session_id="s1",
            request_id="r1",
            model=None,
            execute_tools_fn=_sample_runner,
        )
    )

    assert output == '{"tool_results": "ok"}'


async def _configured_runner(
    user_message: str,
    plan_text: str,
    reduced_context: str,
    session_id: str,
    request_id: str,
    send_event,
    model: str | None,
    allowed_tools: set[str],
) -> str:
    _ = (user_message, plan_text, reduced_context, session_id, request_id, send_event, model, allowed_tools)
    return "configured"


async def _inline_runner(
    user_message: str,
    plan_text: str,
    reduced_context: str,
    session_id: str,
    request_id: str,
    send_event,
    model: str | None,
    allowed_tools: set[str],
) -> str:
    _ = (user_message, plan_text, reduced_context, session_id, request_id, send_event, model, allowed_tools)
    return "inline"


class _Runtime:
    async def run_tools(
        self,
        *,
        payload: ToolSelectorInput,
        session_id: str,
        request_id: str,
        send_event,
        model: str | None,
        allowed_tools: set[str],
    ) -> str:
        _ = (payload, session_id, request_id, send_event, model, allowed_tools)
        return "runtime"


def test_run_prefers_inline_runner_over_configured_runner() -> None:
    agent = ToolSelectorAgent(execute_tools_fn=_configured_runner)

    output = asyncio.run(
        agent.run(
            '{"user_message":"u","plan_text":"p","reduced_context":"c"}',
            send_event=lambda _payload: None,
            session_id="s1",
            request_id="r1",
            model=None,
            execute_tools_fn=_inline_runner,
        )
    )

    assert output == '{"tool_results": "inline"}'


def test_execute_supports_constructor_runner() -> None:
    agent = ToolSelectorAgent(execute_tools_fn=_sample_runner)

    output = asyncio.run(
        agent.execute(
            ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
            session_id="s1",
            request_id="r1",
            send_event=lambda _payload: None,
            model=None,
            allowed_tools={"list_dir"},
        )
    )

    assert output.tool_results == "ok"


def test_execute_uses_runtime_when_no_runner_provided() -> None:
    agent = ToolSelectorAgent(runtime=_Runtime())

    output = asyncio.run(
        agent.execute(
            ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
            session_id="s1",
            request_id="r1",
            send_event=lambda _payload: None,
            model=None,
            allowed_tools={"list_dir"},
        )
    )

    assert output.tool_results == "runtime"


def test_execute_prefers_inline_runner_over_runtime() -> None:
    agent = ToolSelectorAgent(runtime=_Runtime())

    output = asyncio.run(
        agent.execute(
            ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
            session_id="s1",
            request_id="r1",
            send_event=lambda _payload: None,
            model=None,
            allowed_tools={"list_dir"},
            execute_tools_fn=_inline_runner,
        )
    )

    assert output.tool_results == "inline"


def test_execute_with_bound_runner_expires_when_owner_gone() -> None:
    owner = _BoundRunner()
    agent = ToolSelectorAgent(execute_tools_fn=owner.run)
    del owner
    gc.collect()

    with pytest.raises(RuntimeError, match="execute_tools_fn"):
        asyncio.run(
            agent.execute(
                ToolSelectorInput(user_message="u", plan_text="p", reduced_context="c"),
                session_id="s1",
                request_id="r1",
                send_event=lambda _payload: None,
                model=None,
                allowed_tools={"list_dir"},
            )
        )
