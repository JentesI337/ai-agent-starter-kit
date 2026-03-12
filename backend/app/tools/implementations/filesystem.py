"""File system tool operations."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from app.errors import ToolExecutionError


class FileSystemToolMixin:
    """Mixin with file system tool implementations."""

    def list_dir(self, path: str | None = None) -> str:
        target = self._resolve_workspace_path(path or ".")
        if not target.exists() or not target.is_dir():
            raise ToolExecutionError(f"Directory not found: {target}")
        entries = sorted([item.name + ("/" if item.is_dir() else "") for item in target.iterdir()])
        return "\n".join(entries) or "(empty)"

    def read_file(self, path: str) -> str:
        target = self._resolve_workspace_path(path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"File not found: {target}")
        if target.stat().st_size > self._read_file_max_bytes:
            raise ToolExecutionError(
                f"File too large for read_file tool (max {self._read_file_max_bytes} bytes): {target}"
            )
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> str:
        if len(content) > 300_000:
            raise ToolExecutionError("Content too large for write_file tool.")
        target = self._resolve_workspace_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if encoding == "base64":
            import base64 as b64_mod
            try:
                target.write_bytes(b64_mod.b64decode(content))
            except Exception as exc:
                raise ToolExecutionError(f"Invalid base64 content: {exc}")
        else:
            target.write_text(content, encoding="utf-8")
        return f"Wrote file: {target}"

    def apply_patch(self, path: str, search: str, replace: str, replace_all: bool = False) -> str:
        if not search:
            raise ToolExecutionError("apply_patch requires non-empty 'search'.")
        target = self._resolve_workspace_path(path)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError(f"File not found: {target}")
        original = target.read_text(encoding="utf-8")
        hits = original.count(search)
        if hits == 0:
            raise ToolExecutionError("apply_patch search text not found.")
        if hits > 1 and not replace_all:
            raise ToolExecutionError("apply_patch search text is ambiguous; set replace_all=true.")

        updated = original.replace(search, replace) if replace_all else original.replace(search, replace, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Patched file: {target} (replacements={hits if replace_all else 1})"

    def file_search(self, pattern: str, max_results: int = 100) -> str:
        query = (pattern or "**/*").strip()
        cap = max(1, min(int(max_results), 500))
        matches: list[str] = []
        for candidate in self.workspace_root.rglob("*"):
            rel = candidate.relative_to(self.workspace_root).as_posix()
            if PurePosixPath(rel).match(query):
                matches.append(rel + ("/" if candidate.is_dir() else ""))
                if len(matches) >= cap:
                    break
        return "\n".join(matches) if matches else "(no matches)"

    def grep_search(
        self,
        query: str,
        include_pattern: str | None = None,
        is_regexp: bool = False,
        max_results: int = 100,
    ) -> str:
        pattern = (query or "").strip()
        if not pattern:
            raise ToolExecutionError("grep_search requires non-empty 'query'.")

        cap = max(1, min(int(max_results), 500))
        include = (include_pattern or "**/*").strip() or "**/*"

        # Auto-correct duplicated workspace directory prefix in include_pattern.
        # LLMs often send "backend/app/**" when workspace_root IS backend/.
        ws_dir_name = self.workspace_root.name
        inc_parts = Path(include).parts
        if inc_parts and inc_parts[0].lower() == ws_dir_name.lower():
            include = str(Path(*inc_parts[1:])) if len(inc_parts) > 1 else "**/*"

        matches: list[str] = []
        total_scanned_bytes = 0

        compiled = re.compile(pattern, re.IGNORECASE) if is_regexp else None
        for candidate in self.workspace_root.rglob("*"):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(self.workspace_root).as_posix()
            if not PurePosixPath(rel).match(include):
                continue
            try:
                file_size = candidate.stat().st_size
            except Exception:
                continue
            if file_size > self._grep_max_file_bytes:
                continue
            total_scanned_bytes += file_size
            if total_scanned_bytes > self._grep_max_total_scan_bytes:
                break
            try:
                text = candidate.read_text(encoding="utf-8")
            except Exception:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                hit = bool(compiled.search(line)) if compiled else (pattern.lower() in line.lower())
                if hit:
                    matches.append(f"{rel}:{idx}: {line[:280]}")
                    if len(matches) >= cap:
                        return "\n".join(matches)
        return "\n".join(matches) if matches else "(no matches)"

    def list_code_usages(self, symbol: str, include_pattern: str | None = None, max_results: int = 100) -> str:
        name = (symbol or "").strip()
        if not name:
            raise ToolExecutionError("list_code_usages requires 'symbol'.")
        escaped = re.escape(name)
        regex = rf"\b{escaped}\b"
        return self.grep_search(
            query=regex,
            include_pattern=include_pattern or "**/*.py",
            is_regexp=True,
            max_results=max_results,
        )
