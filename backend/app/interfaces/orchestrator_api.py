from __future__ import annotations

from app.config import settings
from app.contracts.agent_contract import AgentContract, SendEvent
from app.interfaces.request_context import RequestContext
from app.orchestrator.events import build_lifecycle_event
from app.orchestrator.pipeline_runner import PipelineRunner
from app.orchestrator.session_lane_manager import SessionLaneManager
from app.services import resolve_tool_policy
from app.state import StateStore


class OrchestratorApi:
    def __init__(self, agent: AgentContract, state_store: StateStore):
        self._runner = PipelineRunner(agent=agent, state_store=state_store)
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
                tool_policy=resolved_policy,
            )

        return await self._lane_manager.run_in_lane(
            session_id=request_context.session_id,
            on_acquired=on_lane_acquired,
            run=run_in_lane,
            on_released=on_lane_released,
        )
