"""Phase E cleanup script for agent.py — removes all legacy 3-phase pipeline code."""

import re

FILE = "app/agent.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# ─────────────────────────────────────────────────────
# 1. Remove legacy imports
# ─────────────────────────────────────────────────────
for imp in [
    "from app.agents.planner_agent import PlannerAgent\n",
    "from app.agents.synthesizer_agent import SynthesizerAgent\n",
    "from app.agents.tool_selector_agent import ToolSelectorAgent\n",
    "from app.contracts.schemas import PlannerInput, SynthesizerInput, ToolSelectorInput\n",
    "from app.contracts.tool_selector_runtime import ToolSelectorRuntime\n",
    "from app.services.dynamic_temperature import DynamicTemperatureResolver\n",
    "from app.services.prompt_ab_registry import PromptAbRegistry\n",
]:
    content = content.replace(imp, "")

content = content.replace(
    "from app.orchestrator.step_executors import (\n"
    "    PlannerStepExecutor,\n"
    "    SynthesizeStepExecutor,\n"
    "    ToolStepExecutor,\n"
    ")\n",
    "",
)

# ─────────────────────────────────────────────────────
# 2. Remove STEER_INTERRUPTED_MARKER constant
# ─────────────────────────────────────────────────────
content = content.replace('STEER_INTERRUPTED_MARKER = "__STEER_INTERRUPTED__"\n', "")

# ─────────────────────────────────────────────────────
# 3. Remove _HeadToolSelectorRuntime class
# ─────────────────────────────────────────────────────
content = content.replace(
    "\n"
    "class _HeadToolSelectorRuntime(ToolSelectorRuntime):\n"
    "    def __init__(self, owner: HeadAgent):\n"
    "        self._owner_ref: weakref.ReferenceType[HeadAgent] = weakref.ref(owner)\n"
    "\n"
    "    async def run_tools(\n"
    "        self,\n"
    "        *,\n"
    "        payload: ToolSelectorInput,\n"
    "        session_id: str,\n"
    "        request_id: str,\n"
    "        send_event: SendEvent,\n"
    "        model: str | None,\n"
    "        allowed_tools: set[str],\n"
    "        should_steer_interrupt: Callable[[], bool] | None = None,\n"
    "    ) -> str:\n"
    "        owner = self._owner_ref()\n"
    "        if owner is None:\n"
    '            raise RuntimeError("HeadAgent is no longer available for tool selection runtime.")\n'
    "        return await owner._execute_tools(\n"
    "            user_message=payload.user_message,\n"
    "            plan_text=payload.plan_text,\n"
    "            memory_context=payload.reduced_context,\n"
    "            session_id=session_id,\n"
    "            request_id=request_id,\n"
    "            send_event=send_event,\n"
    "            model=model,\n"
    "            allowed_tools=allowed_tools,\n"
    "            prompt_mode=payload.prompt_mode,\n"
    "            should_steer_interrupt=should_steer_interrupt,\n"
    "        )\n"
    "\n"
    "\n",
    "\n\n",
)

# ─────────────────────────────────────────────────────
# 4. Rewrite _build_sub_agents
# ─────────────────────────────────────────────────────
OLD_BUILD = (
    "    def _build_sub_agents(self) -> None:\n"
    "        temperature_resolver = DynamicTemperatureResolver(\n"
    "            base_temperature=SynthesizerAgent.constraints.temperature,\n"
    "            overrides=settings.dynamic_temperature_overrides,\n"
    "        )\n"
    "        prompt_ab_registry = PromptAbRegistry(settings.prompt_ab_registry_path)\n"
    "\n"
    "        self.planner_agent = PlannerAgent(\n"
    "            client=self.client,\n"
    "            system_prompt=self.prompt_profile.plan_prompt,\n"
    "            failure_retriever=self._failure_retriever,\n"
    "        )\n"
    "        self.tool_selector_agent = ToolSelectorAgent(runtime=_HeadToolSelectorRuntime(self))\n"
    "        self.synthesizer_agent = SynthesizerAgent(\n"
    "            client=self.client,\n"
    "            agent_name=self.name,\n"
    "            emit_lifecycle_fn=self._emit_lifecycle,\n"
    "            system_prompt=self.prompt_profile.final_prompt,\n"
    "            temperature_resolver=temperature_resolver,\n"
    "            prompt_ab_registry=prompt_ab_registry,\n"
    "        )\n"
    "        self.plan_step_executor = PlannerStepExecutor(execute_fn=self._execute_planner_step)\n"
    "        self.tool_step_executor = ToolStepExecutor(execute_fn=self._execute_tool_step)\n"
    "        self.synthesize_step_executor = SynthesizeStepExecutor(execute_fn=self._execute_synthesize_step)\n"
    "\n"
    "        # ── Continuous streaming tool loop (behind feature flag) ──\n"
    "        if settings.use_continuous_loop:\n"
    "            system_prompt = build_unified_system_prompt(\n"
    "                role=self.role,\n"
    "                plan_prompt=self.prompt_profile.plan_prompt,\n"
    "                tool_hints=self.prompt_profile.tool_selector_prompt,\n"
    "                final_instructions=self.prompt_profile.final_prompt,\n"
    "                platform_summary=self._tool_execution_manager._platform_summary,\n"
    "            )\n"
    "            self._agent_runner: AgentRunner | None = AgentRunner(\n"
    "                client=self.client,\n"
    "                memory=self.memory,\n"
    "                tool_registry=self.tool_registry,\n"
    "                tool_execution_manager=self._tool_execution_manager,\n"
    "                context_reducer=self.context_reducer,\n"
    "                system_prompt=system_prompt,\n"
    "                execute_tool_fn=self._runner_execute_tool,\n"
    "                allowed_tools_resolver=self._resolve_effective_allowed_tools,\n"
    "                guardrail_validator=self._validate_guardrails,\n"
    "                mcp_initializer=self._ensure_mcp_tools_registered,\n"
    "                ambiguity_detector=self._ambiguity_detector,\n"
    "                reflection_service=self._reflection_service,\n"
    "                emit_lifecycle_fn=self._emit_lifecycle,\n"
    "                intent_detector=self._intent,\n"
    "                reply_shaper=self._reply_shaper,\n"
    "                verification_service=self._verification,\n"
    "                reflection_feedback_store=self._reflection_feedback_store,\n"
    "                agent_name=self.name,\n"
    "                distill_fn=self._distill_session_knowledge,\n"
    "                long_term_context_fn=self._build_long_term_memory_context,\n"
    "            )\n"
    "        else:\n"
    "            self._agent_runner = None\n"
)

NEW_BUILD = (
    "    def _build_sub_agents(self) -> None:\n"
    "        system_prompt = build_unified_system_prompt(\n"
    "            role=self.role,\n"
    "            plan_prompt=self.prompt_profile.plan_prompt,\n"
    "            tool_hints=self.prompt_profile.tool_selector_prompt,\n"
    "            final_instructions=self.prompt_profile.final_prompt,\n"
    "            platform_summary=self._tool_execution_manager._platform_summary,\n"
    "        )\n"
    "        self._agent_runner = AgentRunner(\n"
    "            client=self.client,\n"
    "            memory=self.memory,\n"
    "            tool_registry=self.tool_registry,\n"
    "            tool_execution_manager=self._tool_execution_manager,\n"
    "            context_reducer=self.context_reducer,\n"
    "            system_prompt=system_prompt,\n"
    "            execute_tool_fn=self._runner_execute_tool,\n"
    "            allowed_tools_resolver=self._resolve_effective_allowed_tools,\n"
    "            guardrail_validator=self._validate_guardrails,\n"
    "            mcp_initializer=self._ensure_mcp_tools_registered,\n"
    "            ambiguity_detector=self._ambiguity_detector,\n"
    "            reflection_service=self._reflection_service,\n"
    "            emit_lifecycle_fn=self._emit_lifecycle,\n"
    "            intent_detector=self._intent,\n"
    "            reply_shaper=self._reply_shaper,\n"
    "            verification_service=self._verification,\n"
    "            reflection_feedback_store=self._reflection_feedback_store,\n"
    "            agent_name=self.name,\n"
    "            distill_fn=self._distill_session_knowledge,\n"
    "            long_term_context_fn=self._build_long_term_memory_context,\n"
    "        )\n"
)

assert OLD_BUILD in content, "_build_sub_agents old text not found"
content = content.replace(OLD_BUILD, NEW_BUILD)

# ─────────────────────────────────────────────────────
# 5. Simplify run() — remove feature flag, remove legacy fallback
# ─────────────────────────────────────────────────────
# Remove the feature flag condition and unindent the runner block
OLD_RUN_FLAG = (
    "        # ── Feature-flag: Continuous Streaming Tool Loop ──\n"
    "        if settings.use_continuous_loop and self._agent_runner is not None:\n"
    "            # S3-08: ContextVar propagation (same as legacy path)\n"
    "            send_event_token = self._active_send_event_context.set(send_event)\n"
    "            session_id_token = self._active_session_id_context.set(session_id)\n"
    "            request_id_token = self._active_request_id_context.set(request_id)\n"
    "            _runner_status = \"failed\"\n"
    "            _runner_final = \"\"\n"
    "            try:\n"
    "                _runner_final = await self._agent_runner.run(\n"
    "                    user_message=user_message,\n"
    "                    send_event=send_event,\n"
    "                    session_id=session_id,\n"
    "                    request_id=request_id,\n"
    "                    model=model,\n"
    "                    tool_policy=tool_policy,\n"
    "                    should_steer_interrupt=should_steer_interrupt,\n"
    "                )\n"
    "                _runner_status = \"completed\"\n"
    "                return _runner_final\n"
    "            except Exception as exc:\n"
    "                # S3-07: Failure logging to long-term memory\n"
    "                if self._long_term_memory is not None:\n"
    "                    with contextlib.suppress(Exception):\n"
    "                        self._long_term_memory.add_failure(\n"
    "                            FailureEntry(\n"
    "                                failure_id=request_id,\n"
    "                                task_description=user_message[:500],\n"
    "                                error_type=type(exc).__name__,\n"
    "                                root_cause=str(exc)[:500],\n"
    "                                solution=f\"Review {type(exc).__name__} handling in agent run\",\n"
    "                                prevention=f\"Add guard for {type(exc).__name__} before reaching this code path\",\n"
    "                                tags=[type(exc).__name__],\n"
    "                            )\n"
    "                        )\n"
    "                await self._emit_lifecycle(\n"
    "                    send_event,\n"
    "                    stage=\"run_error\",\n"
    "                    request_id=request_id,\n"
    "                    session_id=session_id,\n"
    "                    details={\"error\": str(exc), \"error_type\": type(exc).__name__},\n"
    "                )\n"
    "                raise\n"
    "            finally:\n"
    "                async with self._run_lock:\n"
    "                    self._active_run_count -= 1\n"
    "                # S3-05: Hook integration\n"
    "                with contextlib.suppress(Exception):\n"
    "                    await self._invoke_hooks(\n"
    "                        hook_name=\"agent_end\",\n"
    "                        send_event=send_event,\n"
    "                        request_id=request_id,\n"
    "                        session_id=session_id,\n"
    "                        payload={\n"
    "                            \"status\": _runner_status,\n"
    "                            \"error\": None if _runner_status == \"completed\" else \"runner_error\",\n"
    "                            \"final_chars\": len(_runner_final),\n"
    "                            \"model\": model or self.client.model,\n"
    "                        },\n"
    "                    )\n"
    "                self._active_request_id_context.reset(request_id_token)\n"
    "                self._active_session_id_context.reset(session_id_token)\n"
    "                self._active_send_event_context.reset(send_event_token)\n"
    "\n"
    "        # ── Legacy 3-phase pipeline ──\n"
    "        return await self._run_legacy(\n"
    "            user_message=user_message,\n"
    "            send_event=send_event,\n"
    "            session_id=session_id,\n"
    "            request_id=request_id,\n"
    "            model=model,\n"
    "            tool_policy=tool_policy,\n"
    "            prompt_mode=prompt_mode,\n"
    "            should_steer_interrupt=should_steer_interrupt,\n"
    "        )\n"
)

NEW_RUN_FLAG = (
    "        send_event_token = self._active_send_event_context.set(send_event)\n"
    "        session_id_token = self._active_session_id_context.set(session_id)\n"
    "        request_id_token = self._active_request_id_context.set(request_id)\n"
    "        _runner_status = \"failed\"\n"
    "        _runner_final = \"\"\n"
    "        try:\n"
    "            _runner_final = await self._agent_runner.run(\n"
    "                user_message=user_message,\n"
    "                send_event=send_event,\n"
    "                session_id=session_id,\n"
    "                request_id=request_id,\n"
    "                model=model,\n"
    "                tool_policy=tool_policy,\n"
    "                should_steer_interrupt=should_steer_interrupt,\n"
    "            )\n"
    "            _runner_status = \"completed\"\n"
    "            return _runner_final\n"
    "        except Exception as exc:\n"
    "            if self._long_term_memory is not None:\n"
    "                with contextlib.suppress(Exception):\n"
    "                    self._long_term_memory.add_failure(\n"
    "                        FailureEntry(\n"
    "                            failure_id=request_id,\n"
    "                            task_description=user_message[:500],\n"
    "                            error_type=type(exc).__name__,\n"
    "                            root_cause=str(exc)[:500],\n"
    "                            solution=f\"Review {type(exc).__name__} handling in agent run\",\n"
    "                            prevention=f\"Add guard for {type(exc).__name__} before reaching this code path\",\n"
    "                            tags=[type(exc).__name__],\n"
    "                        )\n"
    "                    )\n"
    "            await self._emit_lifecycle(\n"
    "                send_event,\n"
    "                stage=\"run_error\",\n"
    "                request_id=request_id,\n"
    "                session_id=session_id,\n"
    "                details={\"error\": str(exc), \"error_type\": type(exc).__name__},\n"
    "            )\n"
    "            raise\n"
    "        finally:\n"
    "            async with self._run_lock:\n"
    "                self._active_run_count -= 1\n"
    "            with contextlib.suppress(Exception):\n"
    "                await self._invoke_hooks(\n"
    "                    hook_name=\"agent_end\",\n"
    "                    send_event=send_event,\n"
    "                    request_id=request_id,\n"
    "                    session_id=session_id,\n"
    "                    payload={\n"
    "                        \"status\": _runner_status,\n"
    "                        \"error\": None if _runner_status == \"completed\" else \"runner_error\",\n"
    "                        \"final_chars\": len(_runner_final),\n"
    "                        \"model\": model or self.client.model,\n"
    "                    },\n"
    "                )\n"
    "            self._active_request_id_context.reset(request_id_token)\n"
    "            self._active_session_id_context.reset(session_id_token)\n"
    "            self._active_send_event_context.reset(send_event_token)\n"
)

assert OLD_RUN_FLAG in content, "run() feature flag block not found"
content = content.replace(OLD_RUN_FLAG, NEW_RUN_FLAG)

# ─────────────────────────────────────────────────────
# 6. Simplify configure_runtime — remove legacy agent calls
# ─────────────────────────────────────────────────────
content = content.replace(
    "            self.planner_agent.configure_runtime(base_url=base_url, model=model)\n"
    "            self.synthesizer_agent.configure_runtime(base_url=base_url, model=model)\n"
    "            if self._agent_runner is not None:\n"
    "                self._agent_runner.client = self.client\n"
    "                self._agent_runner._reflection_service = self._reflection_service\n",
    "            self._agent_runner.client = self.client\n"
    "            self._agent_runner._reflection_service = self._reflection_service\n",
)

# Fix indentation of the S3-09 block that was inside `if self._agent_runner is not None:`
content = content.replace(
    "                # S3-09: rebuild unified system prompt for new model\n"
    "                self._agent_runner.system_prompt = build_unified_system_prompt(\n"
    "                    role=self.role,\n"
    "                    plan_prompt=self.prompt_profile.plan_prompt,\n"
    "                    tool_hints=self.prompt_profile.tool_selector_prompt,\n"
    "                    final_instructions=self.prompt_profile.final_prompt,\n"
    "                    platform_summary=self._tool_execution_manager._platform_summary,\n"
    "                )\n",
    "            self._agent_runner.system_prompt = build_unified_system_prompt(\n"
    "                role=self.role,\n"
    "                plan_prompt=self.prompt_profile.plan_prompt,\n"
    "                tool_hints=self.prompt_profile.tool_selector_prompt,\n"
    "                final_instructions=self.prompt_profile.final_prompt,\n"
    "                platform_summary=self._tool_execution_manager._platform_summary,\n"
    "            )\n",
)

# ─────────────────────────────────────────────────────
# 7. Clean _refresh_long_term_memory_store — remove planner_agent refs
# ─────────────────────────────────────────────────────
content = content.replace(
    "            self._failure_retriever = None\n"
    "            # CB-2: planner_agent muss in ALLEN clear-Pfaden zurückgesetzt werden,\n"
    "            # nicht nur im Exception-Catch-Pfad.\n"
    "            if hasattr(self, \"planner_agent\"):\n"
    "                self.planner_agent._failure_retriever = None\n",
    "            self._failure_retriever = None\n",
)

content = content.replace(
    "            self._long_term_memory_db_path = configured_path\n"
    "            if hasattr(self, \"planner_agent\"):\n"
    "                self.planner_agent._failure_retriever = self._failure_retriever\n",
    "            self._long_term_memory_db_path = configured_path\n",
)

# ─────────────────────────────────────────────────────
# 8. Remove large legacy method blocks using regex
# ─────────────────────────────────────────────────────
def remove_method(content: str, signature_pattern: str, next_pattern: str) -> str:
    """Remove a method from signature to the line before next_pattern."""
    sig_match = re.search(signature_pattern, content, re.MULTILINE)
    if not sig_match:
        print(f"WARNING: Could not find pattern: {signature_pattern}")
        return content
    next_match = re.search(next_pattern, content[sig_match.start():], re.MULTILINE)
    if not next_match:
        print(f"WARNING: Could not find next pattern: {next_pattern}")
        return content
    end_pos = sig_match.start() + next_match.start()
    return content[:sig_match.start()] + content[end_pos:]


# Remove _run_legacy (from its definition to _distill_session_knowledge)
content = remove_method(
    content,
    r"^    async def _run_legacy\(",
    r"^    async def _distill_session_knowledge\(",
)

# Remove _execute_planner_step through _build_context_segments
# (from _execute_planner_step to _validate_guardrails)
content = remove_method(
    content,
    r"^    async def _execute_planner_step\(",
    r"^    def _validate_guardrails\(",
)

# Remove _plan_still_valid through _build_root_cause_replan_prompt
# (from _plan_still_valid to _detect_intent_gate)
content = remove_method(
    content,
    r"^    def _plan_still_valid\(",
    r"^    def _detect_intent_gate\(",
)

# Remove _resolve_synthesis_task_type
# (from _resolve_synthesis_task_type to _requires_implementation_evidence)
content = remove_method(
    content,
    r"^    def _resolve_synthesis_task_type\(",
    r"^    def _requires_implementation_evidence\(",
)

# ─────────────────────────────────────────────────────
# 9. Remove now-unused imports (weakref only used by _HeadToolSelectorRuntime)
# ─────────────────────────────────────────────────────
# Check if weakref is still used
if "weakref." not in content and "weakref.ref" not in content:
    content = content.replace("import weakref\n", "")

# ─────────────────────────────────────────────────────
# Write result
# ─────────────────────────────────────────────────────
with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

# Count removed lines
with open(FILE, "r", encoding="utf-8") as f:
    new_count = len(f.readlines())
print(f"Original: 3710 lines → New: {new_count} lines (removed {3710 - new_count})")
