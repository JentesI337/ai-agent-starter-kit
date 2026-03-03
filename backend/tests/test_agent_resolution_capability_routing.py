from __future__ import annotations

from app.services.agent_resolution import capability_route_agent, infer_request_capabilities


def test_infer_request_capabilities_for_review_preset() -> None:
    capabilities = infer_request_capabilities(message="please inspect this diff", preset="review")

    assert "review_analysis" in capabilities
    assert "security_review" in capabilities


def test_capability_route_agent_prefers_coder_for_coding_request() -> None:
    agent_registry = {
        "head-agent": object(),
        "coder-agent": object(),
        "review-agent": object(),
    }

    selected_agent, reason, required_capabilities, ranked = capability_route_agent(
        requested_agent_id="head-agent",
        message="implement endpoint and fix failing pytest",
        preset=None,
        primary_agent_id="head-agent",
        agent_registry=agent_registry,
    )

    assert selected_agent == "coder-agent"
    assert reason == "coding_intent"
    assert "code_reasoning" in required_capabilities
    assert ranked


def test_capability_route_agent_honors_explicit_non_primary_request() -> None:
    agent_registry = {
        "head-agent": object(),
        "coder-agent": object(),
        "review-agent": object(),
    }

    selected_agent, reason, required_capabilities, ranked = capability_route_agent(
        requested_agent_id="review-agent",
        message="build a new service",
        preset=None,
        primary_agent_id="head-agent",
        agent_registry=agent_registry,
    )

    assert selected_agent == "review-agent"
    assert reason is None
    assert "general_reasoning" in required_capabilities
    assert ranked == []
