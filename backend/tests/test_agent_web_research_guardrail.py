from __future__ import annotations

from app.agent import HeadAgent


def test_has_successful_web_fetch_detects_error_only_output() -> None:
    agent = HeadAgent(name="test-agent")
    tool_results = "[web_fetch] ERROR: web_fetch failed: HTTP Error 404: Not Found\n\n[web_fetch] ERROR: Tool timeout (web_fetch)"

    assert agent._has_successful_web_fetch(tool_results) is False


def test_has_successful_web_fetch_detects_success_output() -> None:
    agent = HeadAgent(name="test-agent")
    tool_results = "[web_fetch]\nsource_url: https://example.com\ncontent_type: text/html\ncontent:\nhello"

    assert agent._has_successful_web_fetch(tool_results) is True


def test_build_web_fetch_unavailable_reply_includes_error_summary() -> None:
    agent = HeadAgent(name="test-agent")
    reply = agent._build_web_fetch_unavailable_reply([
        "web_fetch failed: HTTP Error 404: Not Found",
        "Tool timeout (web_fetch) after 20.0s",
    ])

    assert "couldn't reliably fetch web sources" in reply.lower()
    assert "404" in reply
    assert "timeout" in reply.lower()
