from __future__ import annotations

import json
from collections.abc import Awaitable, Callable


class ActionParser:
    def parse(self, raw: str) -> tuple[list[dict], str | None]:
        text = raw.strip()
        parsed, decode_error = self._decode_json_object(text)
        if parsed is None:
            if decode_error == "LLM JSON root is not an object.":
                return [], decode_error
            recovered_actions = self._recover_truncated_actions(text)
            if recovered_actions:
                return recovered_actions, None
            return [], "LLM JSON could not be decoded."
        # Bug 10: tolerate extra fields (e.g. "reasoning") — only extract "actions"
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
            '{"actions":[{"tool":"list_dir|read_file|write_file|run_command|code_execute|apply_patch|file_search|grep_search|list_code_usages|get_changed_files|start_background_command|get_background_output|kill_background_process|web_search|web_fetch|spawn_subrun","args":{}}]}\n'
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
        object_candidate = self._extract_first_balanced_json_object(text)
        if object_candidate is not None:
            return object_candidate[:3000]
        start = text.find("{")
        if start == -1:
            return "{}"
        return text[start : start + 3000]

    def _decode_json_object(self, text: str) -> tuple[dict | None, str | None]:
        try:
            parsed = json.loads(text)
        except Exception as exc:
            candidate = self.extract_json_candidate(text)
            if candidate != text:
                try:
                    parsed = json.loads(candidate)
                except Exception:
                    return None, str(exc)
            else:
                return None, str(exc)
        if not isinstance(parsed, dict):
            return None, "LLM JSON root is not an object."
        return parsed, None

    def _extract_first_balanced_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if in_string:
                if char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def _recover_truncated_actions(self, text: str) -> list[dict]:
        marker = '"actions"'
        marker_index = text.find(marker)
        if marker_index == -1:
            return []
        array_start = text.find("[", marker_index)
        if array_start == -1:
            return []
        index = array_start + 1
        actions: list[dict] = []
        while index < len(text):
            while index < len(text) and text[index] in " \t\r\n,":
                index += 1
            if index >= len(text):
                break
            if text[index] == "]":
                break
            if text[index] != "{":
                break
            depth = 0
            in_string = False
            escaped = False
            object_start = index
            object_end = None
            cursor = index
            while cursor < len(text):
                char = text[cursor]
                if escaped:
                    escaped = False
                    cursor += 1
                    continue
                if in_string:
                    if char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    cursor += 1
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        object_end = cursor
                        break
                cursor += 1
            if object_end is None:
                break
            object_text = text[object_start : object_end + 1]
            try:
                action = json.loads(object_text)
            except Exception:
                break
            if isinstance(action, dict):
                actions.append(action)
            index = object_end + 1
        return actions

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
