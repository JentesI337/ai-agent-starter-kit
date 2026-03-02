from __future__ import annotations

import json
from collections.abc import Awaitable, Callable


class ActionParser:
    def parse(self, raw: str) -> tuple[list[dict], str | None]:
        text = raw.strip()
        try:
            parsed = json.loads(text)
        except Exception:
            return [], "LLM JSON could not be decoded."
        if not isinstance(parsed, dict):
            return [], "LLM JSON root is not an object."
        if set(parsed.keys()) - {"actions"}:
            return [], "LLM JSON root contains unsupported fields."
        actions = parsed.get("actions", [])
        if not isinstance(actions, list):
            return [], "LLM JSON field 'actions' is not a list."
        return actions, None

    async def repair(
        self,
        *,
        raw: str,
        model: str | None,
        complete_chat: Callable[[str, str, str | None], Awaitable[str]],
        system_prompt: str,
    ) -> str:
        raw_block = self.extract_json_candidate(raw)
        repair_prompt = (
            "Convert the following tool-selection output into strict JSON only.\n"
            "Output schema:\n"
            '{"actions":[{"tool":"list_dir|read_file|write_file|run_command|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_fetch|spawn_subrun","args":{}}]}\n'
            "Rules:\n"
            "- Output only one JSON object.\n"
            "- No markdown and no explanations.\n"
            "- Map legacy tool names to allowed names if obvious (e.g. CreateFile -> write_file).\n"
            '- If uncertain, return {"actions":[]}.\n\n'
            "Broken output block (do not add reasoning):\n"
            f"{raw_block}"
        )
        return await complete_chat(system_prompt, repair_prompt, model)

    def extract_json_candidate(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return "{}"
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return "{}"
        return text[start : end + 1][:3000]

    def validate(
        self,
        actions: list[dict],
        allowed_tools: set[str],
        *,
        normalize_tool_name: Callable[[str], str] | None = None,
    ) -> list[dict]:
        validated: list[dict] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            tool_name = action.get("tool")
            args = action.get("args", {})
            if not isinstance(tool_name, str):
                continue
            normalized = normalize_tool_name(tool_name) if normalize_tool_name else tool_name
            if normalized not in allowed_tools:
                continue
            if not isinstance(args, dict):
                continue
            validated.append({"tool": normalized, "args": args})
        return validated
