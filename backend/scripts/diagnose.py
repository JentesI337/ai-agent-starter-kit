"""diagnose.py – Quick runtime diagnostic for AI Agent Starter Kit.

Run against a live backend to verify:
  1. REST health endpoints
  2. WebSocket connectivity + initial handshake
  3. Smoke-test message through the full pipeline
  4. Lifecycle event completeness
  5. Tool telemetry & feature flags

Usage:
    python scripts/diagnose.py                     # defaults: localhost:8000
    python scripts/diagnose.py --base-url http://localhost:8000
    python scripts/diagnose.py --prompt "Explain quicksort"
    python scripts/diagnose.py --timeout 60
    python scripts/diagnose.py --verbose            # print every event
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import httpx
except ImportError:
    sys.exit("ERROR: httpx not installed. Run: pip install httpx")

try:
    import websockets
except ImportError:
    sys.exit("ERROR: websockets not installed. Run: pip install websockets")


# ── Colour helpers (Windows terminal compatible) ────────────────────
def _green(t: str) -> str:
    return f"\033[92m{t}\033[0m"


def _red(t: str) -> str:
    return f"\033[91m{t}\033[0m"


def _yellow(t: str) -> str:
    return f"\033[93m{t}\033[0m"


def _cyan(t: str) -> str:
    return f"\033[96m{t}\033[0m"


def _dim(t: str) -> str:
    return f"\033[90m{t}\033[0m"


def _bold(t: str) -> str:
    return f"\033[1m{t}\033[0m"


# ── Result container ────────────────────────────────────────────────
@dataclass
class DiagResult:
    check: str
    passed: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


EXPECTED_PIPELINE_STAGES = [
    "request_received",
    "run_started",
    "guardrails_passed",
    "planning_completed",
    "request_completed",
]


# ── Check 1: REST health ───────────────────────────────────────────
async def check_health(base_url: str) -> DiagResult:
    url = f"{base_url}/api/runtime/status"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return DiagResult("REST /api/runtime/status", False, f"HTTP {r.status_code}")
        data = r.json()
        model = data.get("model", "?")
        runtime = data.get("runtime", "?")
        auth = data.get("authenticated", False)
        return DiagResult(
            "REST /api/runtime/status",
            True,
            f"runtime={runtime}  model={model}  auth={auth}",
            data,
        )
    except Exception as exc:
        return DiagResult("REST /api/runtime/status", False, f"Connection failed: {exc}")


# ── Check 2: Feature flags ─────────────────────────────────────────
async def check_features(base_url: str) -> DiagResult:
    url = f"{base_url}/api/runtime/features"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return DiagResult("REST /api/runtime/features", False, f"HTTP {r.status_code}")
        data = r.json()
        flags = {k: v for k, v in data.items() if isinstance(v, bool)}
        summary = "  ".join(f"{k}={'ON' if v else 'off'}" for k, v in flags.items())
        return DiagResult("REST /api/runtime/features", True, summary, data)
    except Exception as exc:
        return DiagResult("REST /api/runtime/features", False, str(exc))


# ── Check 3: Tool telemetry ────────────────────────────────────────
async def check_telemetry(base_url: str) -> DiagResult:
    url = f"{base_url}/api/tools/stats"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return DiagResult("REST /api/debug/tool-telemetry", False, f"HTTP {r.status_code}")
        data = r.json()
        tool_count = len(data.get("tools", data.get("per_tool", {})))
        session_entries = len(data.get("trace", data.get("session_trace", [])))
        return DiagResult(
            "REST /api/tools/stats",
            True,
            f"tools_tracked={tool_count}  session_trace_entries={session_entries}",
            data,
        )
    except Exception as exc:
        return DiagResult("REST /api/tools/stats", False, str(exc))


# ── Check 4: WebSocket smoke test ──────────────────────────────────
async def check_websocket_pipeline(
    base_url: str,
    prompt: str,
    timeout_sec: float,
    verbose: bool,
) -> DiagResult:
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url.rstrip('/')}/ws/agent"

    events: list[dict[str, Any]] = []
    lifecycle_stages: list[str] = []
    errors: list[str] = []
    final_text = ""
    token_chunks: list[str] = []
    first_event_ms: int | None = None
    first_token_ms: int | None = None
    completed = False

    started = time.perf_counter()

    try:
        async with websockets.connect(ws_url, max_size=2**24) as ws:
            # Wait for initial status event
            try:
                init_raw = await asyncio.wait_for(ws.recv(), timeout=8)
                init_evt = json.loads(init_raw)
                if verbose:
                    print(_dim(f"  ← init: {json.dumps(init_evt, ensure_ascii=False)[:200]}"))
            except asyncio.TimeoutError:
                return DiagResult("WebSocket Pipeline", False, "No initial status event within 8s")

            # Send test message (fully automated, no user input needed)
            payload = {
                "type": "user_message",
                "content": prompt,
                "agent_id": "head-agent",
            }
            await ws.send(json.dumps(payload, ensure_ascii=False))
            if verbose:
                print(_dim(f"  → [AUTO] Gesendet an Backend: \"{prompt[:80]}\" — warte auf Antwort ..."))

            # Collect events
            while not completed:
                elapsed = time.perf_counter() - started
                remaining = timeout_sec - elapsed
                if remaining <= 0:
                    break

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    break
                except websockets.exceptions.ConnectionClosed:
                    break

                now_ms = int((time.perf_counter() - started) * 1000)

                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event = envelope.get("event") if isinstance(envelope, dict) else None
                if not isinstance(event, dict):
                    continue

                event_type = event.get("type", "unknown")
                events.append(event)

                if first_event_ms is None:
                    first_event_ms = now_ms

                # Auto-approve policy approval requests so tool commands
                # are not blocked during automated diagnosis.
                if event_type == "policy_approval_required":
                    approval = event.get("approval") or {}
                    approval_id = approval.get("approval_id", "")
                    if approval_id:
                        decision_msg = json.dumps({
                            "type": "policy_decision",
                            "approval_id": approval_id,
                            "decision": "allow_once",
                        })
                        await ws.send(decision_msg)
                        if verbose:
                            print(_yellow(f"  → [{now_ms:>6}ms] AUTO-APPROVE: {approval.get('display_text', approval_id)[:100]}"))

                if event_type == "lifecycle":
                    stage = event.get("stage", "")
                    lifecycle_stages.append(stage)
                    if verbose:
                        details = event.get("details", {})
                        detail_str = f"  details={json.dumps(details, ensure_ascii=False)[:120]}" if details else ""
                        print(_dim(f"  ← [{now_ms:>6}ms] lifecycle: {stage}{detail_str}"))
                    if stage in ("request_completed", "request_failed", "request_failed_llm",
                                 "request_failed_guardrail", "request_failed_toolchain",
                                 "request_cancelled"):
                        completed = True

                elif event_type == "token":
                    chunk = event.get("content", event.get("token", ""))
                    token_chunks.append(str(chunk))
                    if first_token_ms is None:
                        first_token_ms = now_ms

                elif event_type == "final":
                    final_text = str(event.get("message", ""))
                    if verbose:
                        print(_dim(f"  ← [{now_ms:>6}ms] final: {final_text[:120]}..."))

                elif event_type == "error":
                    err_msg = str(event.get("message", ""))
                    errors.append(err_msg)
                    if verbose:
                        print(_red(f"  ← [{now_ms:>6}ms] ERROR: {err_msg[:200]}"))

                elif event_type == "status":
                    if verbose:
                        print(_dim(f"  ← [{now_ms:>6}ms] status: {event.get('message', '')[:120]}"))

                elif verbose:
                    print(_dim(f"  ← [{now_ms:>6}ms] {event_type}: {json.dumps(event, ensure_ascii=False)[:150]}"))

    except Exception as exc:
        return DiagResult("WebSocket Pipeline", False, f"Connection failed: {exc}")

    duration_ms = int((time.perf_counter() - started) * 1000)

    # Build response text from final or tokens
    response_text = final_text or "".join(token_chunks)

    # Evaluate pipeline completeness
    missing_stages = [s for s in EXPECTED_PIPELINE_STAGES if s not in lifecycle_stages]
    failure_stages = [s for s in lifecycle_stages if "failed" in s]

    passed = (
        completed
        and not failure_stages
        and not missing_stages
        and len(response_text) > 10
        and not errors
    )

    # Build detail summary
    lines = []
    lines.append(f"duration={duration_ms}ms  events={len(events)}  tokens={len(token_chunks)}")
    if first_event_ms is not None:
        lines.append(f"first_event={first_event_ms}ms  first_token={first_token_ms or '-'}ms")
    lines.append(f"response_length={len(response_text)} chars")
    lines.append(f"stages_hit: {' → '.join(lifecycle_stages)}")

    if missing_stages:
        lines.append(_red(f"MISSING stages: {', '.join(missing_stages)}"))
    if failure_stages:
        lines.append(_red(f"FAILURE stages: {', '.join(failure_stages)}"))
    if errors:
        for e in errors:
            lines.append(_red(f"ERROR: {e[:200]}"))

    return DiagResult(
        "WebSocket Pipeline",
        passed,
        "\n    ".join(lines),
        {
            "duration_ms": duration_ms,
            "event_count": len(events),
            "lifecycle_stages": lifecycle_stages,
            "missing_stages": missing_stages,
            "failure_stages": failure_stages,
            "errors": errors,
            "response_length": len(response_text),
            "response_preview": response_text[:300],
            "first_event_ms": first_event_ms,
            "first_token_ms": first_token_ms,
        },
    )


# ── Runner ──────────────────────────────────────────────────────────
async def run_diagnostics(
    base_url: str,
    prompt: str,
    timeout_sec: float,
    verbose: bool,
) -> list[DiagResult]:
    results: list[DiagResult] = []

    print(_bold("\n━━━ AI Agent Starter Kit — Diagnostic ━━━\n"))

    # Phase 1: REST checks (parallel)
    print(_cyan("▸ Phase 1: REST Endpoints"))
    health, features, telemetry = await asyncio.gather(
        check_health(base_url),
        check_features(base_url),
        check_telemetry(base_url),
    )

    for r in (health, features, telemetry):
        results.append(r)
        icon = _green("✓") if r.passed else _red("✗")
        print(f"  {icon} {r.check}: {r.detail}")

    if not health.passed:
        print(_red("\n  ⚠ Backend not reachable — skipping WebSocket test."))
        return results

    # Phase 2: WebSocket smoke test
    print()
    print(_cyan(f"▸ Phase 2: WebSocket Pipeline"))
    print(_dim(f"  Test-Prompt: \"{prompt[:80]}\" (wird automatisch an Backend gesendet)"))
    print(_dim(f"  ⏳ Warte auf Backend-Antwort (Timeout: {timeout_sec:.0f}s) ..."))
    ws_result = await check_websocket_pipeline(base_url, prompt, timeout_sec, verbose)
    results.append(ws_result)
    icon = _green("✓") if ws_result.passed else _red("✗")
    print(f"  {icon} {ws_result.check}:")
    print(f"    {ws_result.detail}")

    if ws_result.data.get("response_preview"):
        preview = ws_result.data["response_preview"]
        print(f"\n  {_dim('Response preview:')}")
        # Word-wrap preview at ~100 chars
        for i in range(0, len(preview), 100):
            print(f"    {_dim(preview[i:i+100])}")

    # Summary
    print()
    print(_bold("━━━ Summary ━━━"))
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    if failed == 0:
        print(_green(f"  ALL {total} CHECKS PASSED"))
    else:
        print(_red(f"  {failed}/{total} CHECKS FAILED"))
        for r in results:
            if not r.passed:
                print(_red(f"    ✗ {r.check}: {r.detail[:200]}"))

    print()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick runtime diagnostic")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--prompt", default="Sag mir in einem Satz was 2+2 ist.", help="Test prompt")
    parser.add_argument("--timeout", type=float, default=90, help="WebSocket timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Print every event")
    args = parser.parse_args()

    results = asyncio.run(run_diagnostics(args.base_url, args.prompt, args.timeout, args.verbose))

    # Exit code: 0 if all passed, 1 if any failed
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
