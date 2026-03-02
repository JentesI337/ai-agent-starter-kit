from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote_plus

from app.errors import ToolExecutionError


@dataclass(frozen=True)
class IntentGateDecision:
    intent: str | None
    confidence: str
    extracted_command: str | None
    missing_slots: tuple[str, ...]


class IntentDetector:
    def detect_intent_gate(self, user_message: str) -> IntentGateDecision:
        text = (user_message or "").strip()
        lowered = text.lower()
        if not text:
            return IntentGateDecision(intent=None, confidence="low", extracted_command=None, missing_slots=())

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
            return IntentGateDecision(intent=None, confidence="low", extracted_command=None, missing_slots=())

        extracted_command = self.extract_explicit_command(text)
        if extracted_command and self.looks_like_shell_command(extracted_command):
            return IntentGateDecision(
                intent="execute_command",
                confidence="high",
                extracted_command=extracted_command,
                missing_slots=(),
            )

        if extracted_command and not has_explicit_command_keyword:
            return IntentGateDecision(intent=None, confidence="low", extracted_command=None, missing_slots=())

        return IntentGateDecision(
            intent="execute_command",
            confidence="high",
            extracted_command=None,
            missing_slots=("command",),
        )

    def looks_like_shell_command(self, candidate: str) -> bool:
        text = (candidate or "").strip()
        if not text:
            return False

        if re.search(r"[|><=&;]", text):
            return True
        if text.startswith(("./", ".\\", "/", "~", "..\\", "../")):
            return True
        if "\\" in text or "/" in text:
            return True

        token = text.split()[0].strip().strip('"\'').lower()
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

    def extract_explicit_command(self, user_message: str) -> str | None:
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

    def is_web_research_task(self, user_message: str) -> bool:
        text = (user_message or "").lower()
        markers = (
            "search on the web",
            "search the web",
            "browse the web",
            "look up",
            "latest",
            "current",
            "news",
            "google",
            "bing",
            "duckduckgo",
            "find online",
            "web search",
            "internet",
        )
        return any(marker in text for marker in markers)

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

    def has_successful_web_fetch(self, tool_results: str) -> bool:
        if not tool_results:
            return False
        success_pattern = re.compile(r"\[web_fetch\]\s*\n(?!ERROR:)", re.IGNORECASE)
        return bool(success_pattern.search(tool_results))

    def build_web_fetch_unavailable_reply(self, web_errors: list[str]) -> str:
        lines = [
            "I couldn't reliably fetch web sources for this request, so I can't provide a grounded deep-research answer yet.",
            "",
            "What failed:",
        ]
        if web_errors:
            for item in web_errors[:3]:
                lines.append(f"- {item}")
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
