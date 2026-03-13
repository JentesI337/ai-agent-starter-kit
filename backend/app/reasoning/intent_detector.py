from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from app.shared.errors import ToolExecutionError


@dataclass(frozen=True)
class IntentGateDecision:
    detected_intent: str | None
    confidence: float
    gate_action: str
    metadata: dict[str, object]

    @property
    def intent(self) -> str | None:
        return self.detected_intent

    @property
    def extracted_command(self) -> str | None:
        value = self.metadata.get("extracted_command")
        return value if isinstance(value, str) and value.strip() else None

    @property
    def missing_slots(self) -> tuple[str, ...]:
        value = self.metadata.get("missing_slots")
        if isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value if str(item).strip()]
            return tuple(items)
        return ()


class IntentDetector:
    def detect(self, user_message: str) -> IntentGateDecision:
        text = (user_message or "").strip()
        lowered = text.lower()
        if not text:
            return IntentGateDecision(
                detected_intent=None,
                confidence=0.05,
                gate_action="proceed",
                metadata={"extracted_command": None, "missing_slots": ()},
            )

        command_markers = (
            "run",
            "execute",
            "start",
            "launch",
            "führe",
            "starte",
        )
        has_explicit_command_keyword = any(
            marker in lowered
            for marker in (
                "run command",
                "execute command",
                "shell command",
                "terminal command",
                "befehl",
                "kommando",
            )
        )
        has_command_intent = bool(re.match(r"^\s*(please\s+)?(run|execute|start|launch)\b", lowered))
        has_command_intent = has_command_intent or any(lowered.startswith(f"{marker} ") for marker in command_markers)
        has_command_intent = has_command_intent or has_explicit_command_keyword
        if not has_command_intent:
            return IntentGateDecision(
                detected_intent=None,
                confidence=0.15,
                gate_action="proceed",
                metadata={"extracted_command": None, "missing_slots": ()},
            )

        # Multi-step prompts (numbered lists, multiple tasks) should NOT be
        # reduced to a single execute_command intent.  Let the LLM-based tool
        # selection handle them so all steps get appropriate tools.
        if self._is_multi_step(text):
            return IntentGateDecision(
                detected_intent=None,
                confidence=0.2,
                gate_action="proceed",
                metadata={"extracted_command": None, "missing_slots": ()},
            )

        extracted_command = self.extract_command(text)
        if extracted_command and self.is_shell_command(extracted_command):
            return IntentGateDecision(
                detected_intent="execute_command",
                confidence=0.95,
                gate_action="force_tool",
                metadata={"extracted_command": extracted_command, "missing_slots": ()},
            )

        if extracted_command and not has_explicit_command_keyword:
            return IntentGateDecision(
                detected_intent=None,
                confidence=0.2,
                gate_action="proceed",
                metadata={"extracted_command": None, "missing_slots": ()},
            )

        return IntentGateDecision(
            detected_intent="execute_command",
            confidence=0.9,
            gate_action="force_tool",
            metadata={"extracted_command": None, "missing_slots": ("command",)},
        )

    @staticmethod
    def _is_multi_step(text: str) -> bool:
        """Return True when the prompt contains multiple numbered/bulleted steps."""
        numbered = re.findall(r"(?:^|\n)\s*\d+[.)]", text)
        if len(numbered) >= 2:
            return True
        bullets = re.findall(r"(?:^|\n)\s*[-•*]\s", text)
        return len(bullets) >= 2

    def detect_intent_gate(self, user_message: str) -> IntentGateDecision:
        return self.detect(user_message)

    def is_shell_command(self, candidate: str) -> bool:
        text = (candidate or "").strip()
        if not text:
            return False

        if re.search(r"[|><=&;]", text):
            return True
        if text.startswith(("./", ".\\", "~", "..\\", "../")):
            return True

        token = text.split()[0].strip().strip("\"'").lower()
        if not token:
            return False

        common_commands = {
            "python",
            "python3",
            "py",
            "pip",
            "pip3",
            "pytest",
            "npm",
            "npx",
            "node",
            "pnpm",
            "yarn",
            "uv",
            "poetry",
            "git",
            "make",
            "cmake",
            "docker",
            "kubectl",
            "powershell",
            "pwsh",
            "bash",
            "sh",
            "cmd",
            "ls",
            "dir",
            "cat",
            "type",
            "echo",
            "grep",
            "find",
            "sed",
            "awk",
            "curl",
            "wget",
        }
        return token in common_commands

    def looks_like_shell_command(self, candidate: str) -> bool:
        return self.is_shell_command(candidate)

    def extract_command(self, user_message: str) -> str | None:
        text = (user_message or "").strip()
        if not text:
            return None

        fenced_match = re.search(r"`([^`\n]{1,400})`", text)
        if fenced_match:
            candidate = fenced_match.group(1).strip()
            if candidate:
                return candidate

        quoted_match = re.search(r'"([^"\n]{1,400})"', text)
        if quoted_match:
            candidate = quoted_match.group(1).strip()
            if candidate:
                return candidate

        lowered = text.lower()
        prefixes = (
            "run ",
            "execute ",
            "start ",
            "launch ",
            "please run ",
            "please execute ",
            "führe ",
            "starte ",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                candidate = text[len(prefix) :].strip()
                if not candidate:
                    return None
                if candidate.lower() in {"it", "this", "that", "command", "den command", "befehl"}:
                    return None
                return candidate

        command_after_colon = re.search(r"(?:command|befehl)\s*:\s*(.+)$", text, flags=re.IGNORECASE)
        if command_after_colon:
            candidate = command_after_colon.group(1).strip()
            if candidate:
                return candidate
        return None

    def extract_explicit_command(self, user_message: str) -> str | None:
        return self.extract_command(user_message)

    def is_web_research_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        explicit_markers = (
            "search on the web",
            "search the web",
            "browse the web",
            "look up",
            "web search",
            "find online",
            "google",
            "bing",
            "duckduckgo",
            "internet",
        )
        if any(marker in text for marker in explicit_markers):
            return True

        # Bug 11: use word-boundary matching to avoid false positives
        # (e.g. "current" inside "concurrent", "source" inside "resource")
        _freshness_re = re.compile(r"\b(?:latest|current|news)\b")
        _web_context_re = re.compile(r"\b(?:web|online|internet|sources?)\b")
        return bool(_freshness_re.search(text)) and bool(_web_context_re.search(text))

    def is_subrun_orchestration_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "orchestrate",
            "orchestration",
            "delegate",
            "delegation",
            "spawn subrun",
            "spawn subprocess",
            "spawn sub process",
            "parallel research",
            "multi-agent",
            "multi agent",
        )
        return any(marker in text for marker in markers)

    def is_weather_lookup_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "weather",
            "forecast",
            "temperature",
            "humidity",
            "wind",
            "precipitation",
            "wetter",
            "temperatur",
            "niederschlag",
        )
        return any(marker in text for marker in markers)

    def should_retry_web_fetch_on_404(self, error: ToolExecutionError) -> bool:
        text = str(error).lower()
        return "http error 404" in text or " 404" in text

    def should_retry_fetch(self, error: ToolExecutionError) -> bool:
        return self.should_retry_web_fetch_on_404(error)

    def has_successful_web_fetch(self, tool_results: str) -> bool:
        if not tool_results:
            return False
        success_pattern = re.compile(r"\[web_fetch\]\s*\n(?!ERROR:)", re.IGNORECASE)
        return bool(success_pattern.search(tool_results))

    def has_successful_web_search(self, tool_results: str) -> bool:
        if not tool_results:
            return False
        success_pattern = re.compile(r"\[web_search\]\s*\n(?!ERROR:)", re.IGNORECASE)
        return bool(success_pattern.search(tool_results))

    def has_successful_fetch(self, tool_results: str) -> bool:
        return self.has_successful_web_fetch(tool_results) or self.has_successful_web_search(tool_results)

    def build_web_fetch_unavailable_reply(self, web_errors: list[str]) -> str:
        lines = [
            "I couldn't reliably fetch web sources for this request, so I can't provide a grounded deep-research answer yet.",
            "",
            "What failed:",
        ]
        if web_errors:
            lines.extend(f"- {item}" for item in web_errors[:3])
        else:
            lines.append("- No successful web_fetch result was returned.")

        lines.extend(
            [
                "",
                "How to proceed:",
                "- Retry the request once (temporary upstream issues can resolve on retry).",
                "- Provide 3-5 direct source URLs and I will analyze them deeply.",
                "- If you want, I can first build a reliable source list, then run a second pass with comparative analysis.",
            ]
        )
        return "\n".join(lines).strip()

    def build_fetch_unavailable_reply(self, web_errors: list[str]) -> str:
        lines = [
            "I couldn't reliably fetch web sources for this request, so I can't provide a grounded deep-research answer yet.",
            "",
            "What failed:",
        ]
        if web_errors:
            lines.extend(f"- {item}" for item in web_errors[:3])
        else:
            lines.append("- No successful web_search/web_fetch result was returned.")

        lines.extend(
            [
                "",
                "How to proceed:",
                "- Retry the request once (temporary upstream issues can resolve on retry).",
                "- Provide 3-5 direct source URLs and I will analyze them deeply.",
                "- If you want, I can first build a reliable source list, then run a second pass with comparative analysis.",
            ]
        )
        return "\n".join(lines).strip()

    def build_web_research_url(self, user_message: str) -> str:
        text = (user_message or "").strip()
        if not text:
            return ""

        explicit_url = re.search(r"https?://\S+", text)
        if explicit_url:
            return explicit_url.group(0).rstrip(").,;:!?")

        query = text
        for prefix in (
            "can you",
            "please",
            "could you",
            "search on the web for",
            "search the web for",
            "look up",
            "find",
        ):
            if query.lower().startswith(prefix):
                query = query[len(prefix) :].strip()

        if not query:
            query = text
        return f"https://duckduckgo.com/html/?q={quote_plus(query)}"

    def build_search_url(self, user_message: str) -> str:
        return self.build_web_research_url(user_message)

    def is_file_creation_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        phrases = (
            "create a file",
            "create file",
            "create a new file",
            "build a file",
            "make a file",
            "save to file",
            "save as file",
            "write to file",
            "generate a file",
            "create an html",
            "create a css",
            "create a js",
            "create a javascript",
            "write html",
            "write css",
            "write javascript",
        )
        return any(phrase in text for phrase in phrases)
