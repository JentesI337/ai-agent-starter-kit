from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings
from app.contracts.agent_contract import AgentContract, SendEvent
from app.contracts.request_context import RequestContext
from app.orchestration.events import build_lifecycle_event
from app.orchestration.pipeline_runner import PipelineRunner
from app.orchestration.session_lane_manager import SessionLaneManager
from app.state import StateStore
from app.tools.provisioning.policy_service import resolve_tool_policy

if TYPE_CHECKING:
    from app.llm.health_tracker import ModelHealthTracker
    from app.policy.circuit_breaker import CircuitBreakerRegistry


class OrchestratorApi:
    def __init__(
        self,
        agent: AgentContract,
        state_store: StateStore,
        health_tracker: ModelHealthTracker | None = None,
        circuit_breaker: CircuitBreakerRegistry | None = None,
    ):
        self._runner = PipelineRunner(
            agent=agent,
            state_store=state_store,
            health_tracker=health_tracker,
            circuit_breaker=circuit_breaker,
        )
        self._lane_manager = SessionLaneManager(
            global_max_concurrent=settings.session_lane_global_max_concurrent,
        )

    async def run_user_message(
        self,
        *,
        user_message: str,
        send_event: SendEvent,
        request_context: RequestContext,
    ) -> str:
        await send_event(
            build_lifecycle_event(
                request_id=request_context.request_id,
                session_id=request_context.session_id,
                stage="queued",
                details={},
                agent=self._runner.agent.name,
            )
        )

        async def on_lane_acquired(details: dict) -> None:
            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="lane_acquired",
                    details=details,
                    agent=self._runner.agent.name,
                )
            )

        async def on_lane_released(details: dict) -> None:
            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="lane_released",
                    details=details,
                    agent=self._runner.agent.name,
                )
            )

        async def run_in_lane() -> str:
            resolved_policy_result = resolve_tool_policy(
                preset=request_context.preset,
                provider=request_context.runtime,
                model=request_context.model,
                request_policy=request_context.tool_policy,
                also_allow=request_context.also_allow,
                agent_id=request_context.agent_id,
                depth=request_context.depth,
                orchestrator_agent_ids=request_context.orchestrator_agent_ids,
            )
            resolved_policy = resolved_policy_result.get("merged_policy")
            applied_preset = resolved_policy_result.get("applied_preset")

            explain = resolved_policy_result.get("explain") or {}
            layers = explain.get("layers") if isinstance(explain, dict) else []
            warnings = explain.get("warnings") if isinstance(explain, dict) else []
            depth_layer: dict | None = None
            if isinstance(layers, list):
                for layer in layers:
                    if isinstance(layer, dict) and layer.get("layer") == "agent_depth":
                        depth_layer = layer
                        break

            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="tool_policy_decision",
                    details={
                        "preset": applied_preset,
                        "requested": request_context.tool_policy or {},
                        "resolved": resolved_policy or {},
                        "agent_id": request_context.agent_id,
                        "depth": request_context.depth,
                        "provider": request_context.runtime,
                        "model": request_context.model,
                        "warnings": warnings if isinstance(warnings, list) else [],
                    },
                    agent=self._runner.agent.name,
                )
            )

            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="tool_policy_layers_logged",
                    details={
                        "layers": layers if isinstance(layers, list) else [],
                        "warnings": warnings if isinstance(warnings, list) else [],
                        "also_allow": (explain.get("also_allow") if isinstance(explain, dict) else []) or [],
                    },
                    agent=self._runner.agent.name,
                )
            )

            await send_event(
                build_lifecycle_event(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    stage="agent_depth_policy_applied",
                    details={
                        "agent_id": request_context.agent_id,
                        "depth": request_context.depth,
                        "provider": request_context.runtime,
                        "model": request_context.model,
                        "requested": request_context.tool_policy or {},
                        "resolved": resolved_policy or {},
                        "depth_layer": depth_layer or {},
                    },
                    agent=self._runner.agent.name,
                )
            )

            return await self._runner.run(
                user_message=user_message,
                send_event=send_event,
                session_id=request_context.session_id,
                request_id=request_context.request_id,
                runtime=request_context.runtime,
                model=request_context.model,
                reasoning_level=request_context.reasoning_level,
                tool_policy=resolved_policy,
                prompt_mode=request_context.prompt_mode,
                should_steer_interrupt=request_context.should_steer_interrupt,
            )

        return await self._lane_manager.run_in_lane(
            session_id=request_context.session_id,
            on_acquired=on_lane_acquired,
            run=run_in_lane,
            on_released=on_lane_released,
        )
