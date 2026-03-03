from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class ToolLoopDecision:
    blocked: bool = False
    break_run: bool = False
    rejection_message: str | None = None
    lifecycle_events: list[tuple[str, dict[str, object]]] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyOverrideCandidate:
    tool: str
    resource: str


@dataclass(frozen=True)
class ActionPreparationResult:
    tool: str
    normalized_args: dict[str, object]
    error: str | None


def collect_policy_override_candidates(
    *,
    actions: list[dict],
    allowed_tools: set[str],
    normalize_tool_name,
    process_tools: set[str] | None = None,
) -> list[PolicyOverrideCandidate]:
    allowed_process_tools = process_tools or {"run_command", "spawn_subrun"}
    reviewed: set[tuple[str, str]] = set()
    candidates: list[PolicyOverrideCandidate] = []

    for action in actions:
        if not isinstance(action, dict):
            continue
        raw_tool = action.get("tool")
        if not isinstance(raw_tool, str):
            continue
        tool = normalize_tool_name(raw_tool)
        if tool not in allowed_process_tools or tool in allowed_tools:
            continue
        args = action.get("args")
        if not isinstance(args, dict):
            continue

        resource = ""
        if tool == "run_command":
            candidate = args.get("command")
            if isinstance(candidate, str):
                resource = candidate.strip()
        elif tool == "spawn_subrun":
            candidate = args.get("message")
            if isinstance(candidate, str):
                resource = candidate.strip()

        if not resource:
            continue

        key = (tool, resource)
        if key in reviewed:
            continue
        reviewed.add(key)
        candidates.append(PolicyOverrideCandidate(tool=tool, resource=resource))

    return candidates


def prepare_action_for_execution(
    *,
    action: dict,
    allowed_tools: set[str],
    normalize_tool_name,
    evaluate_action,
) -> ActionPreparationResult:
    if not isinstance(action, dict):
        return ActionPreparationResult(tool="", normalized_args={}, error="invalid action payload")

    raw_tool = action.get("tool")
    if isinstance(raw_tool, str):
        tool = normalize_tool_name(raw_tool)
    else:
        tool = ""

    raw_args = action.get("args", {})
    args = raw_args if isinstance(raw_args, dict) else {}

    evaluated_args, eval_error = evaluate_action(tool, args, allowed_tools)
    if eval_error:
        return ActionPreparationResult(tool=tool, normalized_args={}, error=eval_error)

    return ActionPreparationResult(tool=tool, normalized_args=evaluated_args, error=None)


class ToolCallGatekeeper:
    def __init__(
        self,
        *,
        warn_threshold: int,
        critical_threshold: int,
        circuit_breaker_threshold: int,
        warning_bucket_size: int,
        generic_repeat_enabled: bool,
        ping_pong_enabled: bool,
        poll_no_progress_enabled: bool,
        poll_no_progress_threshold: int,
    ):
        self.warn_threshold = max(1, int(warn_threshold))
        self.critical_threshold = max(self.warn_threshold + 1, int(critical_threshold))
        self.circuit_breaker_threshold = max(self.critical_threshold + 1, int(circuit_breaker_threshold))
        self.warning_bucket_size = max(1, int(warning_bucket_size))
        self.generic_repeat_enabled = bool(generic_repeat_enabled)
        self.ping_pong_enabled = bool(ping_pong_enabled)
        self.poll_no_progress_enabled = bool(poll_no_progress_enabled)
        self.poll_no_progress_threshold = max(2, int(poll_no_progress_threshold))

        self.signature_counts: dict[str, int] = {}
        self.signature_history: list[str] = []
        self.repeat_signature_hits = 0
        self.completed_outcomes: list[tuple[str, str]] = []
        self.warning_bucket_progress: dict[str, int] = {}

        self.loop_blocked_count = 0
        self.ping_pong_blocked_count = 0
        self.poll_no_progress_blocked_count = 0

    @staticmethod
    def build_signature(*, tool: str, args: dict) -> str:
        return json.dumps({"tool": tool, "args": args}, ensure_ascii=False, sort_keys=True)

    def before_tool_call(self, *, tool: str, signature: str, index: int) -> ToolLoopDecision:
        decision = ToolLoopDecision()

        self.signature_history.append(signature)
        if len(self.signature_history) > 12:
            self.signature_history = self.signature_history[-12:]
        if signature in self.signature_history[:-1]:
            self.repeat_signature_hits += 1

        current_count = self.signature_counts.get(signature, 0) + 1
        self.signature_counts[signature] = current_count

        if self.ping_pong_enabled:
            ping_pong_meta = self._detect_ping_pong_pattern(next_signature=signature)
            if ping_pong_meta:
                signature_a = str(ping_pong_meta.get("signature_a", ""))
                signature_b = str(ping_pong_meta.get("signature_b", ""))
                alternating_count = int(ping_pong_meta.get("alternating_count", 0))
                no_progress_evidence = bool(ping_pong_meta.get("no_progress_evidence", False))

                warning_key = self._build_ping_pong_warning_key(
                    signature_a=signature_a,
                    signature_b=signature_b,
                )
                warning_bucket = self._resolve_warning_bucket(
                    warning_key=warning_key,
                    hit_count=alternating_count,
                )
                if warning_bucket is not None:
                    decision.lifecycle_events.append(
                        (
                            "tool_loop_ping_pong_warn",
                            {
                                "tool": tool,
                                "index": index,
                                "reason_type": "ping_pong",
                                "signature_a": signature_a,
                                "signature_b": signature_b,
                                "alternating_count": alternating_count,
                                "no_progress_evidence": no_progress_evidence,
                                "warn_threshold": self.warn_threshold,
                                "warning_key": warning_key,
                                "warning_bucket_index": warning_bucket,
                                "warning_bucket_size": self.warning_bucket_size,
                            },
                        )
                    )

                if no_progress_evidence and alternating_count >= self.critical_threshold:
                    self.ping_pong_blocked_count += 1
                    self.loop_blocked_count += 1
                    decision.blocked = True
                    decision.rejection_message = "tool loop blocked (ping-pong pattern detected)"
                    decision.lifecycle_events.append(
                        (
                            "tool_loop_ping_pong_blocked",
                            {
                                "tool": tool,
                                "index": index,
                                "reason_type": "ping_pong",
                                "signature_a": signature_a,
                                "signature_b": signature_b,
                                "alternating_count": alternating_count,
                                "no_progress_evidence": True,
                                "critical_threshold": self.critical_threshold,
                            },
                        )
                    )
                    return decision

        if self.generic_repeat_enabled and current_count >= self.warn_threshold:
            warning_key = f"generic:{signature}"
            warning_bucket = self._resolve_warning_bucket(
                warning_key=warning_key,
                hit_count=current_count,
            )
            if warning_bucket is not None:
                decision.lifecycle_events.append(
                    (
                        "tool_loop_warn",
                        {
                            "tool": tool,
                            "index": index,
                            "reason_type": "generic_repeat",
                            "signature_hits": current_count,
                            "warn_threshold": self.warn_threshold,
                            "warning_key": warning_key,
                            "warning_bucket_index": warning_bucket,
                            "warning_bucket_size": self.warning_bucket_size,
                        },
                    )
                )

        if self.generic_repeat_enabled and current_count >= self.critical_threshold:
            self.loop_blocked_count += 1
            decision.blocked = True
            decision.rejection_message = (
                "tool loop blocked "
                f"(signature repeated {current_count}x, threshold {self.critical_threshold})"
            )
            decision.lifecycle_events.append(
                (
                    "tool_loop_blocked",
                    {
                        "tool": tool,
                        "index": index,
                        "reason_type": "generic_repeat",
                        "signature_hits": current_count,
                        "critical_threshold": self.critical_threshold,
                    },
                )
            )
            return decision

        if self.generic_repeat_enabled and self.repeat_signature_hits >= self.circuit_breaker_threshold:
            self.loop_blocked_count += 1
            decision.blocked = True
            decision.break_run = True
            decision.rejection_message = (
                "tool loop circuit breaker triggered "
                f"(repeat hits {self.repeat_signature_hits}, threshold {self.circuit_breaker_threshold})"
            )
            decision.lifecycle_events.append(
                (
                    "tool_loop_circuit_breaker",
                    {
                        "tool": tool,
                        "index": index,
                        "reason_type": "generic_repeat",
                        "repeat_signature_hits": self.repeat_signature_hits,
                        "circuit_breaker_threshold": self.circuit_breaker_threshold,
                    },
                )
            )
            return decision

        return decision

    def after_tool_success(self, *, tool: str, signature: str, index: int, result: str) -> ToolLoopDecision:
        decision = ToolLoopDecision()

        outcome_hash = hashlib.sha256(
            json.dumps(
                {"result": result.strip()},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.completed_outcomes.append((signature, outcome_hash))
        if len(self.completed_outcomes) > 60:
            self.completed_outcomes = self.completed_outcomes[-60:]

        if not self.poll_no_progress_enabled:
            return decision

        outcome_streak = 0
        for recorded_signature, recorded_hash in reversed(self.completed_outcomes):
            if recorded_signature != signature:
                continue
            if recorded_hash != outcome_hash:
                break
            outcome_streak += 1

        if outcome_streak >= self.poll_no_progress_threshold:
            self.poll_no_progress_blocked_count += 1
            self.loop_blocked_count += 1
            decision.blocked = True
            decision.break_run = True
            decision.rejection_message = (
                "tool loop blocked "
                f"(poll_no_progress streak {outcome_streak}/{self.poll_no_progress_threshold})"
            )
            decision.lifecycle_events.append(
                (
                    "tool_loop_poll_no_progress_blocked",
                    {
                        "tool": tool,
                        "index": index,
                        "reason_type": "poll_no_progress",
                        "outcome_streak": outcome_streak,
                        "threshold": self.poll_no_progress_threshold,
                    },
                )
            )

        return decision

    def summary_payload(self) -> dict[str, object]:
        return {
            "loop_blocked": self.loop_blocked_count,
            "loop_ping_pong_blocked": self.ping_pong_blocked_count,
            "loop_poll_no_progress_blocked": self.poll_no_progress_blocked_count,
            "loop_repeat_signature_hits": self.repeat_signature_hits,
            "loop_reason_counts": {
                "generic_repeat": max(
                    0,
                    self.loop_blocked_count - self.ping_pong_blocked_count - self.poll_no_progress_blocked_count,
                ),
                "ping_pong": self.ping_pong_blocked_count,
                "poll_no_progress": self.poll_no_progress_blocked_count,
            },
            "loop_warn_threshold": self.warn_threshold,
            "loop_critical_threshold": self.critical_threshold,
            "loop_circuit_breaker_threshold": self.circuit_breaker_threshold,
            "loop_detector_generic_repeat_enabled": self.generic_repeat_enabled,
            "loop_detector_ping_pong_enabled": self.ping_pong_enabled,
            "loop_detector_poll_no_progress_enabled": self.poll_no_progress_enabled,
            "loop_poll_no_progress_threshold": self.poll_no_progress_threshold,
            "loop_warning_bucket_size": self.warning_bucket_size,
        }

    def _resolve_warning_bucket(self, *, warning_key: str, hit_count: int) -> int | None:
        if hit_count < self.warn_threshold:
            return None
        bucket_index = ((hit_count - self.warn_threshold) // self.warning_bucket_size) + 1
        previous_bucket = self.warning_bucket_progress.get(warning_key, 0)
        if bucket_index <= previous_bucket:
            return None
        self.warning_bucket_progress[warning_key] = bucket_index
        return bucket_index

    def _detect_ping_pong_pattern(self, *, next_signature: str) -> dict[str, object] | None:
        if len(self.completed_outcomes) < 3:
            return None

        last_signature, _ = self.completed_outcomes[-1]
        other_signature: str | None = None
        for previous_signature, _ in reversed(self.completed_outcomes[:-1]):
            if previous_signature != last_signature:
                other_signature = previous_signature
                break

        if not other_signature:
            return None
        if next_signature != other_signature:
            return None

        alternating_tail: list[tuple[str, str]] = []
        expected_signature = last_signature
        for signature_value, outcome_hash in reversed(self.completed_outcomes):
            if signature_value != expected_signature:
                break
            alternating_tail.append((signature_value, outcome_hash))
            expected_signature = other_signature if expected_signature == last_signature else last_signature

        if len(alternating_tail) < 3:
            return None

        hashes_a = {
            outcome_hash
            for signature_value, outcome_hash in alternating_tail
            if signature_value == last_signature
        }
        hashes_b = {
            outcome_hash
            for signature_value, outcome_hash in alternating_tail
            if signature_value == other_signature
        }

        alternating_count = len(alternating_tail) + 1
        no_progress_evidence = bool(hashes_a and hashes_b and len(hashes_a) == 1 and len(hashes_b) == 1)

        return {
            "signature_a": last_signature,
            "signature_b": other_signature,
            "alternating_count": alternating_count,
            "no_progress_evidence": no_progress_evidence,
        }

    def _build_ping_pong_warning_key(self, *, signature_a: str, signature_b: str) -> str:
        return "pingpong:" + "|".join(sorted([signature_a, signature_b]))
