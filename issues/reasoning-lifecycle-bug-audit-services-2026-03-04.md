# Reasoning Lifecycle Bug Audit — Supporting Services (Round 2)

**Date:** 2026-03-04  
**Scope:** 11 service files in `backend/app/services/`  
**Auditor:** automated deep review

---

## Bug 1 — Race Condition in PolicyApprovalService.create() Idempotency Check

**File:** `backend/app/services/policy_approval_service.py` Lines 42–87  
**Severity:** CRITICAL  
**Root cause:** The idempotency check and the record creation use **two separate lock acquisitions**. Between releasing the first lock (after the idempotency scan) and acquiring the second lock (for insertion), a concurrent coroutine with the exact same parameters can pass the same idempotency check and also create a new record.

```python
async def create(self, ...) -> dict:
    async with self._lock:                       # lock 1 — scan
        for existing in self._records.values():
            if (...matches...):
                return reused
    # <<< LOCK RELEASED — race window opens here >>>
    approval_id = str(uuid.uuid4())
    ...
    async with self._lock:                       # lock 2 — insert
        self._records[approval_id] = record
```

**Impact:** Two duplicate approval prompts can be shown to the user for the same tool+resource request, leading to inconsistent approval state if different decisions are made on each.

---

## Bug 2 — `allow_session` Grants Blanket Pre-Approval for ALL Tools

**File:** `backend/app/services/policy_approval_service.py` Lines 232–235 / 190–193  
**Severity:** HIGH (policy enforcement gap)  
**Root cause:** When the user selects `allow_session` for a *specific* tool+resource approval prompt, the implementation adds the session ID to `_session_allow_all`. The `is_preapproved()` method then returns `True` for **every** subsequent tool call in that session, regardless of tool name or resource.

```python
# decide() — line 232
if normalized_decision == "allow_session":
    normalized_session_id = str(record.get("session_id") or "").strip()
    if normalized_session_id:
        self._session_allow_all.add(normalized_session_id)   # blanket allow

# is_preapproved() — line 190
if normalized_session_id and normalized_session_id in self._session_allow_all:
    return True    # allows ANY tool + ANY resource
```

**Impact:** A user who approves a harmless `list_dir` call with "allow_session" unknowingly pre-approves all subsequent `run_command`, `code_execute`, etc. calls for the entire session — complete policy bypass.

---

## Bug 3 — `clear_session_overrides` Does Not Remove Persisted Session-Scoped Rules

**File:** `backend/app/services/policy_approval_service.py` Lines 196–201  
**Severity:** HIGH (policy enforcement gap)  
**Root cause:** `clear_session_overrides()` only removes the session from the in-memory `_session_allow_all` set. It does **not** remove `allow_always` rules with scope `session_tool` or `session_tool_resource` from `_allow_always_rules`, which are additionally persisted to disk.

```python
async def clear_session_overrides(self, session_id: str | None) -> None:
    ...
    async with self._lock:
        self._session_allow_all.discard(normalized_session_id)
        # BUG: _allow_always_rules entries with matching session_id are NOT removed
```

**Impact:** Session-scoped `allow_always` rules persist across server restarts (disk-backed) and remain active even after the session is supposedly cleared.

---

## Bug 4 — `wait_for_decision` Misses "cancelled" and "expired" Status in Early Return

**File:** `backend/app/services/policy_approval_service.py` Lines 262–274  
**Severity:** MEDIUM  
**Root cause:** The early-return check only covers `{"approved", "denied"}`, omitting `"cancelled"` and `"expired"`. If a record was already cancelled or previously expired, calling `wait_for_decision` will not return immediately — it falls through to `event.wait()`.

```python
async def wait_for_decision(self, approval_id: str, timeout_seconds: float) -> str | None:
    async with self._lock:
        ...
        if record.get("status") in {"approved", "denied"}:   # misses "cancelled", "expired"
            decision = str(record.get("decision") or "").strip().lower()
            return decision or None
    # falls through to event.wait() — may wait until timeout for an already-decided record
```

**Impact:** For already-cancelled/expired records, the caller blocks unnecessarily until the asyncio Event fires (which may never happen for "expired" records whose event was never set), effectively causing a timeout delay.

---

## Bug 5 — Circuit Breaker Uses Unbounded Monotonic Counter

**File:** `backend/app/services/tool_call_gatekeeper.py` Lines 139–143 / 269–286  
**Severity:** HIGH  
**Root cause:** `repeat_signature_hits` is incremented every time any signature appears again within the 12-element sliding window, but is **never decremented or reset**. Over a long-running session with many tool calls, even non-looping behavior accumulates repeat hits until the circuit breaker fires.

```python
# before_tool_call — line 139
self.signature_history.append(signature)
if len(self.signature_history) > 12:
    self.signature_history = self.signature_history[-12:]
if signature in self.signature_history[:-1]:
    self.repeat_signature_hits += 1             # monotonically increases, never reset

# circuit breaker check — line 269
if self.generic_repeat_enabled and self.repeat_signature_hits >= self.circuit_breaker_threshold:
    decision.blocked = True
    decision.break_run = True                   # kills the entire run
```

**Impact:** In long sessions with legitimate repeated tool calls (e.g., periodic `read_file` to check for changes), the circuit breaker will eventually trip even when no actual loop exists. This is a false-positive run termination.

---

## Bug 6 — `is_shell_command` False Positive on Forward/Back Slash in Text

**File:** `backend/app/services/intent_detector.py` Lines 109–112  
**Severity:** HIGH (detection failure — false positive)  
**Root cause:** The method classifies any text containing `/` or `\` as a shell command. After `extract_command()` strips the prefix, remaining text like "the TCP/IP diagnostic" or "a/b testing" is classified as a shell command.

```python
def is_shell_command(self, candidate: str) -> bool:
    ...
    if "\\" in text or "/" in text:        # too broad — matches URLs, abbreviations, paths in prose
        return True
```

**Impact:** User messages like "run the TCP/IP diagnostic tool" → extracted command "the TCP/IP diagnostic tool" → classified as shell command → `gate_action="force_tool"` with `confidence=0.95`, forcing an incorrect `run_command` execution.

---

## Bug 7 — Tool Result Context Guard Drops Preamble Text Before First Block

**File:** `backend/app/services/tool_result_context_guard.py` Lines 19–32  
**Severity:** MEDIUM (context loss)  
**Root cause:** `_split_tool_result_blocks()` starts each block at the position of a `[header]\n` match. Any text before the first match is not included in any block and is silently lost during the budget enforcement pass.

```python
def _split_tool_result_blocks(text: str) -> list[str]:
    matches = list(_TOOL_BLOCK_PATTERN.finditer(source))
    ...
    blocks: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()          # starts at the match — text before matches[0] is lost
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        blocks.append(source[start:end])
    return blocks
```

**Impact:** If tool results include a preamble (e.g., system notes, context summary) before the first `[tool_name]` header, that text is silently dropped and never reaches the LLM for final answer generation.

---

## Bug 8 — `_TOOL_BLOCK_PATTERN` Requires Trailing Newline — Misses Last Block Header

**File:** `backend/app/services/tool_result_context_guard.py` Line 8  
**Severity:** LOW  
**Root cause:** The regex `^\[[^\]\n]+\]\n` requires a `\n` after the closing `]`. If the last tool result block header is on the final line of the string without a trailing newline, it will not be matched as a block boundary.

```python
_TOOL_BLOCK_PATTERN = re.compile(r"(?ms)^\[[^\]\n]+\]\n")
#                                                     ^^ requires newline
```

**Impact:** The last tool result block may not be properly split and budget-truncated. The block's content either gets folded into the preceding block or treated as a single unblocked string.

---

## Bug 9 — `verify_tool_result` Simplistic Substring Detection Causes False Positives/Negatives

**File:** `backend/app/services/verification_service.py` Lines 122–131  
**Severity:** MEDIUM (verification bug)  
**Root cause:** Error/OK detection uses naive substring matching. The presence of `" ok"` anywhere in the result (e.g., "She looked ok" in scraped text) suppresses error detection. Conversely, `" error"` matches innocuous contexts like "no error found" or "error handling is correct".

```python
lowered = normalized_results.lower()
has_error = " error" in lowered or "[error]" in lowered
has_ok = "[ok]" in lowered or " ok" in lowered
if has_error and not has_ok:
    return VerificationResult(status="warning", reason="tool_results_error_only", ...)
```

**Impact:** (1) Tool results containing prose with " ok" anywhere mask genuine `[error]` markers. (2) Tool results discussing errors in a positive context ("error handling works correctly") produce false warnings.

---

## Bug 10 — `ActionParser.parse` Rejects Valid JSON With Extra Fields

**File:** `backend/app/services/action_parser.py` Lines 9–16  
**Severity:** MEDIUM (logic error)  
**Root cause:** If the LLM returns valid JSON with an `"actions"` key plus harmless extra fields like `"reasoning"`, the parser rejects the entire payload. Meanwhile, the truncation recovery path (`_recover_truncated_actions`) does **not** perform this check, creating an inconsistency: truncated JSON with extra keys → accepted; complete JSON with extra keys → rejected.

```python
def parse(self, raw: str) -> tuple[list[dict], str | None]:
    ...
    parsed, decode_error = self._decode_json_object(text)
    if parsed is None:
        ...
        recovered_actions = self._recover_truncated_actions(text)
        if recovered_actions:
            return recovered_actions, None           # ← no extra-field check
        ...
    if set(parsed.keys()) - {"actions"}:             # ← rejects {"actions":[...], "reasoning":"..."}
        return [], "LLM JSON root contains unsupported fields."
```

**Impact:** Valid tool-selection output is dropped, forcing an expensive repair round-trip. Truncated output with extra fields is paradoxically accepted while complete output is rejected.

---

## Bug 11 — `is_web_research_task` Substring Matching Causes False Positives

**File:** `backend/app/services/intent_detector.py` Lines 223–234  
**Severity:** MEDIUM (detection failure — false positive)  
**Root cause:** The freshness+context heuristic uses plain `in` substring matching. `"source"` matches inside "resource", "opensource", "outsource". `"current"` matches inside "concurrent".

```python
freshness_markers = ("latest", "current", "news")
web_context_markers = ("web", "online", "internet", "source", "sources")
return any(marker in text for marker in freshness_markers) and any(
    marker in text for marker in web_context_markers
)
```

**Impact:** Messages like "get the latest resource usage" or "current opensource version" are incorrectly classified as web research tasks, causing unnecessary `web_search`/`web_fetch` actions to be injected by the `ActionAugmenter`.

---

## Bug 12 — `looks_like_coding_request` Substring Matching Causes False Positives

**File:** `backend/app/services/agent_resolution.py` Lines 121–142  
**Severity:** MEDIUM (detection failure — false positive)  
**Root cause:** Keyword matching uses `in text` (substring), not word-boundary matching. Common words like `"test"`, `"fix"`, `"class"`, `"code"` appear as substrings in many non-coding contexts. This same issue also affects `infer_request_capabilities()` at lines 153–190.

```python
keyword_markers = (
    "code", "python", ..., "bug", "debug", "fix", "refactor",
    "implement", "function", "class", "api", "endpoint", "test", ...
)
if any(marker in text for marker in keyword_markers):
    return True
```

**Impact:** "contest results" (matches "test"), "classify animals" (matches "class"), "fix dinner" (matches "fix"), "python snake habitat" (matches "python") all route to `coder-agent` instead of `head-agent`.

---

## Bug 13 — `_extract_json_payload` Greedy Regex Fails With Multiple JSON Objects

**File:** `backend/app/services/reflection_service.py` Lines 119–132  
**Severity:** LOW  
**Root cause:** The fallback regex `\{[\s\S]*\}` is greedy, matching from the first `{` to the last `}` in the entire string. If the LLM output contains multiple JSON-like structures or braces in explanatory text, the extracted substring spans across them and produces invalid JSON.

```python
match = re.search(r"\{[\s\S]*\}", cleaned)     # greedy — matches first { to last }
```

**Impact:** When the LLM wraps its JSON in explanation text containing additional braces, the extraction fails and the reflection verdict defaults to `score=0.0, should_retry=True`, triggering an unnecessary retry cycle.

---

## Bug 14 — `_normalize_scope` Silently Promotes Invalid Scope to Global

**File:** `backend/app/services/policy_approval_service.py` Lines 89–93  
**Severity:** MEDIUM (policy enforcement gap)  
**Root cause:** If an invalid or misspelled scope string is provided (e.g., `"sesion_tool"` instead of `"session_tool"`), it silently defaults to `"tool_resource"` — which is a **global, non-session-scoped** rule. A typo in scope can accidentally create a permanent global allow-always rule.

```python
def _normalize_scope(self, scope: str | None) -> str:
    candidate = (scope or "tool_resource").strip().lower()
    if candidate not in ALLOW_ALWAYS_SCOPES:
        return "tool_resource"       # silent promotion to global scope
    return candidate
```

**Impact:** A rule intended only for a specific session is silently elevated to a global persistent rule, allowing the tool+resource combination for all sessions permanently.

---

## Summary

| # | Title | File | Severity |
|---|-------|------|----------|
| 1 | Race condition in `create()` idempotency check | policy_approval_service.py | CRITICAL |
| 2 | `allow_session` grants blanket pre-approval | policy_approval_service.py | HIGH |
| 3 | `clear_session_overrides` skips persisted session rules | policy_approval_service.py | HIGH |
| 4 | `wait_for_decision` misses cancelled/expired status | policy_approval_service.py | MEDIUM |
| 5 | Circuit breaker uses unbounded monotonic counter | tool_call_gatekeeper.py | HIGH |
| 6 | `is_shell_command` false positive on `/` and `\` | intent_detector.py | HIGH |
| 7 | Preamble text dropped before first tool block | tool_result_context_guard.py | MEDIUM |
| 8 | Tool block pattern misses headerless trailing newline | tool_result_context_guard.py | LOW |
| 9 | `verify_tool_result` naive error/ok substring matching | verification_service.py | MEDIUM |
| 10 | `parse()` rejects valid JSON with extra fields | action_parser.py | MEDIUM |
| 11 | `is_web_research_task` substring false positives | intent_detector.py | MEDIUM |
| 12 | `looks_like_coding_request` substring false positives | agent_resolution.py | MEDIUM |
| 13 | `_extract_json_payload` greedy regex multi-object fail | reflection_service.py | LOW |
| 14 | `_normalize_scope` silently promotes invalid scope to global | policy_approval_service.py | MEDIUM |

**Total: 14 bugs found** (1 critical, 3 high, 8 medium, 2 low)
