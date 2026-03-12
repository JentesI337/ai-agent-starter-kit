"""DevOps tool mixin — git, testing, linting, dependency, debugging, and security tools.

This mixin is inherited by AgentTooling. All methods use subprocess.run
directly (same pattern as get_changed_files) to avoid the command allowlist.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.errors import ToolExecutionError
from app.services.output_parsers import (
    GIT_LOG_FORMAT_FULL,
    GIT_LOG_FORMAT_ONELINE,
    GIT_LOG_FORMAT_SHORT,
    parse_coverage_json,
    parse_eslint_json,
    parse_git_blame_porcelain,
    parse_git_log_full,
    parse_git_log_short,
    parse_go_panic,
    parse_jest_json,
    parse_mypy_json,
    parse_node_stacktrace,
    parse_npm_audit_json,
    parse_pip_audit_json,
    parse_pytest_output,
    parse_python_traceback,
    parse_ruff_json,
    parse_tsc_output,
    scan_text_for_secrets,
)
from app.tools.discovery.detector import detect_linter, detect_package_manager, detect_test_runner

# Max chars for tool output to prevent blowing up context
_MAX_OUTPUT_CHARS = 12_000


class DevOpsToolMixin:
    """Git, testing, linting, dependency, debugging, and security tools."""

    # These attributes come from AgentTooling via MRO
    workspace_root: Path
    command_timeout_seconds: int

    # ── Helpers ───────────────────────────────────────────────────────

    def _run_git(self, *args: str, allow_failure: bool = False) -> str:
        """Run ``git -C <workspace> <args>``, return stdout or raise."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.workspace_root), *args],
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
            )
        except FileNotFoundError:
            raise ToolExecutionError("'git' is not installed or not on PATH.")
        if result.returncode != 0 and not allow_failure:
            raise ToolExecutionError(
                (result.stderr or result.stdout or "git command failed").strip()[:2000]
            )
        return (result.stdout or "")

    def _run_subprocess(
        self, argv: list[str], *, cwd: str | None = None, allow_failure: bool = False,
        timeout: int | None = None, install_hint: str = "",
    ) -> tuple[str, str, int]:
        """Run a subprocess safely. Returns (stdout, stderr, returncode)."""
        run_cwd = cwd or str(self.workspace_root)
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout or self.command_timeout_seconds,
                cwd=run_cwd,
            )
        except FileNotFoundError:
            hint = f" Install with: {install_hint}" if install_hint else ""
            raise ToolExecutionError(f"'{argv[0]}' is not installed or not on PATH.{hint}")
        except subprocess.TimeoutExpired:
            raise ToolExecutionError(f"Command timed out after {timeout or self.command_timeout_seconds}s: {' '.join(argv[:3])}")
        if result.returncode != 0 and not allow_failure:
            raise ToolExecutionError(
                (result.stderr or result.stdout or f"Command failed: {' '.join(argv[:3])}").strip()[:2000]
            )
        return result.stdout or "", result.stderr or "", result.returncode

    def _truncate(self, text: str, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + f"\n\n... ({len(text) - max_chars} chars truncated) ...\n\n" + text[-half:]

    # ── Git Tools ─────────────────────────────────────────────────────

    def git_log(
        self,
        path: str | None = None,
        max_count: str | int = 20,
        author: str | None = None,
        since: str | None = None,
        format: str = "short",
    ) -> str:
        count = min(int(max_count), 100)
        fmt_map = {
            "oneline": GIT_LOG_FORMAT_ONELINE,
            "short": GIT_LOG_FORMAT_SHORT,
            "full": GIT_LOG_FORMAT_FULL,
        }
        fmt = fmt_map.get(format, GIT_LOG_FORMAT_SHORT)
        args = ["log", f"--max-count={count}", f"--format={fmt}"]
        if author:
            args.append(f"--author={author}")
        if since:
            args.append(f"--since={since}")
        if path:
            args.extend(["--", path])

        raw = self._run_git(*args)
        if not raw.strip():
            return "No commits found matching the criteria."

        if format == "oneline":
            return self._truncate(raw.strip())

        parser = parse_git_log_full if format == "full" else parse_git_log_short
        entries = parser(raw)
        if not entries:
            return raw.strip()[:_MAX_OUTPUT_CHARS]
        return json.dumps(entries, indent=2)[:_MAX_OUTPUT_CHARS]

    def git_diff(
        self,
        target: str | None = None,
        base: str | None = None,
        stat_only: str | bool = False,
    ) -> str:
        stat_only = str(stat_only).lower() in ("true", "1", "yes") if isinstance(stat_only, str) else stat_only
        args = ["diff"]
        if stat_only:
            args.append("--stat")
        if base and target:
            args.extend([base, target])
        elif target:
            args.append(target)

        raw = self._run_git(*args)
        if not raw.strip():
            return "No differences found."
        return self._truncate(raw.strip())

    def git_blame(
        self,
        path: str,
        start_line: str | int | None = None,
        end_line: str | int | None = None,
    ) -> str:
        if not path:
            raise ToolExecutionError("git_blame requires a 'path' argument.")
        args = ["blame", "--porcelain"]
        if start_line and end_line:
            args.extend(["-L", f"{start_line},{end_line}"])
        elif start_line:
            args.extend(["-L", f"{start_line},+20"])
        args.append(path)

        raw = self._run_git(*args)
        entries = parse_git_blame_porcelain(raw)
        if not entries:
            return raw.strip()[:_MAX_OUTPUT_CHARS]
        return json.dumps(entries, indent=2)[:_MAX_OUTPUT_CHARS]

    def git_show(self, ref: str, stat_only: str | bool = False) -> str:
        if not ref:
            raise ToolExecutionError("git_show requires a 'ref' argument.")
        stat_only = str(stat_only).lower() in ("true", "1", "yes") if isinstance(stat_only, str) else stat_only
        args = ["show", ref]
        if stat_only:
            args.append("--stat")

        raw = self._run_git(*args)
        return self._truncate(raw.strip())

    def git_stash(self, action: str, message: str | None = None) -> str:
        valid_actions = ("save", "pop", "list", "drop")
        if action not in valid_actions:
            raise ToolExecutionError(f"git_stash action must be one of: {', '.join(valid_actions)}")

        if action == "save":
            args = ["stash", "push"]
            if message:
                args.extend(["-m", message])
        elif action == "list":
            args = ["stash", "list"]
        elif action == "pop":
            args = ["stash", "pop"]
        elif action == "drop":
            args = ["stash", "drop"]

        raw = self._run_git(*args)
        return raw.strip() or f"git stash {action} completed."

    # ── Testing Tools ─────────────────────────────────────────────────

    def run_tests(
        self,
        runner: str = "auto",
        path: str | None = None,
        filter: str | None = None,
        verbose: str | bool = False,
    ) -> str:
        verbose = str(verbose).lower() in ("true", "1", "yes") if isinstance(verbose, str) else verbose

        if runner == "auto":
            detected = detect_test_runner(self.workspace_root)
            if not detected:
                return (
                    "Could not auto-detect test runner. Looked for: "
                    "pytest (pyproject.toml, pytest.ini), jest (package.json), go.mod, Cargo.toml. "
                    "Specify the 'runner' parameter explicitly or use run_command."
                )
            runner = detected

        if runner == "pytest":
            return self._run_pytest(path, filter, verbose)
        elif runner == "jest":
            return self._run_jest(path, filter, verbose)
        elif runner == "go":
            return self._run_go_test(path, filter, verbose)
        elif runner == "cargo":
            return self._run_cargo_test(path, filter, verbose)
        elif runner == "mocha":
            return self._run_mocha(path, filter, verbose)
        else:
            raise ToolExecutionError(f"Unknown test runner: {runner}")

    def _run_pytest(self, path: str | None, filter_pat: str | None, verbose: bool) -> str:
        argv = ["python", "-m", "pytest", "-q", "--tb=short", "--no-header"]
        if filter_pat:
            argv.extend(["-k", filter_pat])
        if verbose:
            argv.append("-v")
        if path:
            argv.append(path)

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint="pip install pytest",
        )
        raw = stdout + stderr
        parsed = parse_pytest_output(raw)
        parsed["exit_code"] = rc
        if rc != 0 and not parsed["errors"] and not parsed["raw_summary"]:
            parsed["raw_output"] = raw[:3000]
        return json.dumps(parsed, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_jest(self, path: str | None, filter_pat: str | None, verbose: bool) -> str:
        argv = ["npx", "jest", "--json", "--no-coverage"]
        if filter_pat:
            argv.extend(["--testNamePattern", filter_pat])
        if path:
            argv.append(path)

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint="npm install --save-dev jest",
        )
        parsed = parse_jest_json(stdout)
        parsed["exit_code"] = rc
        if rc != 0 and not parsed["errors"]:
            parsed["raw_output"] = (stdout + stderr)[:3000]
        return json.dumps(parsed, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_go_test(self, path: str | None, filter_pat: str | None, verbose: bool) -> str:
        argv = ["go", "test"]
        if verbose:
            argv.append("-v")
        target = path or "./..."
        argv.append(target)
        if filter_pat:
            argv.extend(["-run", filter_pat])

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint="install Go from https://go.dev",
        )
        return self._truncate(f"exit_code: {rc}\n\n{stdout}\n{stderr}".strip())

    def _run_cargo_test(self, path: str | None, filter_pat: str | None, verbose: bool) -> str:
        argv = ["cargo", "test"]
        if filter_pat:
            argv.append(filter_pat)
        if path:
            argv.extend(["--manifest-path", path])

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint="install Rust from https://rustup.rs",
        )
        return self._truncate(f"exit_code: {rc}\n\n{stdout}\n{stderr}".strip())

    def _run_mocha(self, path: str | None, filter_pat: str | None, verbose: bool) -> str:
        argv = ["npx", "mocha"]
        if filter_pat:
            argv.extend(["--grep", filter_pat])
        if path:
            argv.append(path)

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint="npm install --save-dev mocha",
        )
        return self._truncate(f"exit_code: {rc}\n\n{stdout}\n{stderr}".strip())

    # ── Linting Tools ─────────────────────────────────────────────────

    def lint_check(
        self,
        tool: str = "auto",
        path: str | None = None,
        fix: str | bool = False,
    ) -> str:
        fix = str(fix).lower() in ("true", "1", "yes") if isinstance(fix, str) else fix

        if tool == "auto":
            detected = detect_linter(self.workspace_root)
            if not detected:
                return (
                    "Could not auto-detect linter. Looked for: "
                    "ruff (ruff.toml, pyproject.toml), eslint (.eslintrc*), mypy (mypy.ini), tsc (tsconfig.json). "
                    "Specify the 'tool' parameter explicitly or use run_command."
                )
            tool = detected

        if tool == "eslint":
            return self._run_eslint(path, fix)
        elif tool == "ruff":
            return self._run_ruff(path, fix)
        elif tool in ("mypy", "pyright"):
            return self._run_mypy(path, tool)
        elif tool == "tsc":
            return self._run_tsc(path)
        elif tool == "flake8":
            return self._run_flake8(path)
        else:
            raise ToolExecutionError(f"Unknown linter: {tool}")

    def _run_eslint(self, path: str | None, fix: bool) -> str:
        argv = ["npx", "eslint", "--format", "json"]
        if fix:
            argv.append("--fix")
        argv.append(path or ".")

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60, install_hint="npm install --save-dev eslint",
        )
        diagnostics = parse_eslint_json(stdout)
        summary = {
            "tool": "eslint",
            "total_issues": len(diagnostics),
            "errors": sum(1 for d in diagnostics if d["severity"] == "error"),
            "warnings": sum(1 for d in diagnostics if d["severity"] == "warning"),
            "diagnostics": diagnostics[:50],
        }
        return json.dumps(summary, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_ruff(self, path: str | None, fix: bool) -> str:
        argv = ["ruff", "check", "--output-format", "json"]
        if fix:
            argv.append("--fix")
        argv.append(path or ".")

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60, install_hint="pip install ruff",
        )
        diagnostics = parse_ruff_json(stdout)
        summary = {
            "tool": "ruff",
            "total_issues": len(diagnostics),
            "errors": sum(1 for d in diagnostics if d["severity"] == "error"),
            "warnings": sum(1 for d in diagnostics if d["severity"] == "warning"),
            "diagnostics": diagnostics[:50],
        }
        return json.dumps(summary, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_mypy(self, path: str | None, tool_name: str = "mypy") -> str:
        argv = [tool_name]
        argv.append(path or ".")

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=120, install_hint=f"pip install {tool_name}",
        )
        diagnostics = parse_mypy_json(stdout)
        summary = {
            "tool": tool_name,
            "total_issues": len(diagnostics),
            "errors": sum(1 for d in diagnostics if d["severity"] == "error"),
            "warnings": sum(1 for d in diagnostics if d["severity"] != "error"),
            "diagnostics": diagnostics[:50],
        }
        return json.dumps(summary, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_tsc(self, path: str | None) -> str:
        argv = ["npx", "tsc", "--noEmit"]
        if path:
            argv.extend(["--project", path])

        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60, install_hint="npm install --save-dev typescript",
        )
        diagnostics = parse_tsc_output(stdout + stderr)
        summary = {
            "tool": "tsc",
            "total_issues": len(diagnostics),
            "errors": sum(1 for d in diagnostics if d["severity"] == "error"),
            "warnings": sum(1 for d in diagnostics if d["severity"] == "warning"),
            "diagnostics": diagnostics[:50],
        }
        return json.dumps(summary, indent=2)[:_MAX_OUTPUT_CHARS]

    def _run_flake8(self, path: str | None) -> str:
        argv = ["flake8", path or "."]
        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60, install_hint="pip install flake8",
        )
        # flake8 output format: file:line:col: code message
        diagnostics: list[dict[str, Any]] = []
        import re
        for line in stdout.strip().splitlines():
            m = re.match(r"^(.+?):(\d+):(\d+):\s*(\w+)\s+(.+)$", line)
            if m:
                diagnostics.append({
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "column": int(m.group(3)),
                    "severity": "error" if m.group(4).startswith("E") else "warning",
                    "message": m.group(5).strip(),
                    "rule": m.group(4),
                })
        summary = {
            "tool": "flake8",
            "total_issues": len(diagnostics),
            "errors": sum(1 for d in diagnostics if d["severity"] == "error"),
            "warnings": sum(1 for d in diagnostics if d["severity"] == "warning"),
            "diagnostics": diagnostics[:50],
        }
        return json.dumps(summary, indent=2)[:_MAX_OUTPUT_CHARS]

    # ── Coverage ──────────────────────────────────────────────────────

    def test_coverage(self, runner: str = "auto", path: str | None = None) -> str:
        if runner == "auto":
            detected = detect_test_runner(self.workspace_root)
            runner = detected or "pytest"

        if runner == "pytest":
            argv = ["python", "-m", "pytest", "--cov", "--cov-report=json", "-q", "--no-header"]
            if path:
                argv.extend(["--cov=" + path, path])
            stdout, stderr, rc = self._run_subprocess(
                argv, allow_failure=True, timeout=180,
                install_hint="pip install pytest-cov",
            )
            # coverage.py writes to coverage.json
            cov_file = self.workspace_root / "coverage.json"
            if cov_file.exists():
                try:
                    raw = cov_file.read_text(encoding="utf-8")
                    parsed = parse_coverage_json(raw)
                    parsed["exit_code"] = rc
                    return json.dumps(parsed, indent=2)[:_MAX_OUTPUT_CHARS]
                except OSError:
                    pass
            return self._truncate(f"exit_code: {rc}\n\n{stdout}\n{stderr}".strip())

        elif runner == "jest":
            argv = ["npx", "jest", "--coverage", "--coverageReporters=json-summary"]
            if path:
                argv.append(path)
            stdout, stderr, rc = self._run_subprocess(
                argv, allow_failure=True, timeout=180,
            )
            return self._truncate(f"exit_code: {rc}\n\n{stdout}\n{stderr}".strip())

        return f"Coverage not supported for runner: {runner}. Use run_command instead."

    # ── Error Parsing ─────────────────────────────────────────────────

    def parse_errors(self, error_text: str, language: str = "auto") -> str:
        if not error_text or not error_text.strip():
            raise ToolExecutionError("parse_errors requires non-empty 'error_text'.")

        if language == "auto":
            language = self._detect_error_language(error_text)

        if language == "python":
            parsed = parse_python_traceback(error_text)
        elif language == "javascript":
            parsed = parse_node_stacktrace(error_text)
        elif language == "go":
            parsed = parse_go_panic(error_text)
        else:
            # Try python first, then node
            parsed = parse_python_traceback(error_text)
            if not parsed["frames"]:
                parsed = parse_node_stacktrace(error_text)
            if not parsed["frames"]:
                return json.dumps({
                    "error_type": "unknown",
                    "message": error_text[:500],
                    "frames": [],
                    "hint": "Could not parse stack trace. Provide a 'language' hint.",
                })

        return json.dumps(parsed, indent=2)[:_MAX_OUTPUT_CHARS]

    @staticmethod
    def _detect_error_language(text: str) -> str:
        if "Traceback (most recent call last)" in text or 'File "' in text:
            return "python"
        if "    at " in text and ("(" in text or ".js:" in text or ".ts:" in text):
            return "javascript"
        if "goroutine" in text or "panic:" in text:
            return "go"
        return "auto"

    # ── Dependency Tools ──────────────────────────────────────────────

    def dependency_audit(self, manager: str = "auto", severity: str = "moderate") -> str:
        if manager == "auto":
            detected = detect_package_manager(self.workspace_root)
            if not detected:
                return (
                    "Could not detect package manager. Looked for: "
                    "package.json/package-lock.json (npm), requirements.txt/pyproject.toml (pip). "
                    "Specify the 'manager' parameter explicitly."
                )
            manager = detected

        if manager in ("npm", "yarn", "pnpm"):
            return self._npm_audit(severity)
        elif manager in ("pip", "pipenv"):
            return self._pip_audit(severity)
        else:
            return f"Audit not supported for: {manager}. Use run_command instead."

    def _npm_audit(self, severity: str) -> str:
        argv = ["npm", "audit", "--json"]
        if severity in ("high", "critical"):
            argv.extend(["--audit-level", severity])
        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60,
        )
        vulns = parse_npm_audit_json(stdout)
        if severity != "low":
            severity_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
            min_level = severity_order.get(severity, 1)
            vulns = [v for v in vulns if severity_order.get(v.get("severity", ""), 0) >= min_level]
        return json.dumps({
            "manager": "npm",
            "total_vulnerabilities": len(vulns),
            "vulnerabilities": vulns[:30],
        }, indent=2)[:_MAX_OUTPUT_CHARS]

    def _pip_audit(self, severity: str) -> str:
        argv = ["pip-audit", "--format", "json"]
        stdout, stderr, rc = self._run_subprocess(
            argv, allow_failure=True, timeout=60, install_hint="pip install pip-audit",
        )
        vulns = parse_pip_audit_json(stdout)
        return json.dumps({
            "manager": "pip",
            "total_vulnerabilities": len(vulns),
            "vulnerabilities": vulns[:30],
        }, indent=2)[:_MAX_OUTPUT_CHARS]

    def dependency_outdated(self, manager: str = "auto") -> str:
        if manager == "auto":
            detected = detect_package_manager(self.workspace_root)
            manager = detected or "npm"

        if manager in ("npm", "yarn", "pnpm"):
            argv = ["npm", "outdated", "--json"]
            stdout, stderr, rc = self._run_subprocess(argv, allow_failure=True, timeout=60)
            try:
                data = json.loads(stdout)
                packages = []
                for name, info in data.items():
                    packages.append({
                        "package": name,
                        "current": info.get("current", "?"),
                        "wanted": info.get("wanted", "?"),
                        "latest": info.get("latest", "?"),
                    })
                return json.dumps({"manager": "npm", "outdated": packages}, indent=2)[:_MAX_OUTPUT_CHARS]
            except (json.JSONDecodeError, TypeError):
                return self._truncate(stdout + stderr)

        elif manager in ("pip", "pipenv"):
            argv = ["pip", "list", "--outdated", "--format", "json"]
            stdout, stderr, rc = self._run_subprocess(argv, allow_failure=True, timeout=60)
            try:
                data = json.loads(stdout)
                packages = [
                    {"package": p["name"], "current": p["version"], "latest": p["latest_version"]}
                    for p in data
                ]
                return json.dumps({"manager": "pip", "outdated": packages}, indent=2)[:_MAX_OUTPUT_CHARS]
            except (json.JSONDecodeError, TypeError):
                return self._truncate(stdout + stderr)

        return f"Outdated check not supported for: {manager}. Use run_command instead."

    def dependency_tree(self, manager: str = "auto", package: str | None = None) -> str:
        if manager == "auto":
            detected = detect_package_manager(self.workspace_root)
            manager = detected or "npm"

        if manager in ("npm", "yarn", "pnpm"):
            argv = ["npm", "ls", "--all"]
            if package:
                argv.append(package)
            stdout, stderr, rc = self._run_subprocess(argv, allow_failure=True, timeout=60)
            return self._truncate(stdout.strip())

        elif manager in ("pip", "pipenv"):
            argv = ["pip", "show"]
            if package:
                argv.append(package)
                stdout, stderr, rc = self._run_subprocess(argv, allow_failure=True, timeout=30)
                return self._truncate(stdout.strip())
            else:
                # pipdeptree if available, else pip list
                try:
                    stdout, stderr, rc = self._run_subprocess(
                        ["pipdeptree"], allow_failure=True, timeout=30,
                    )
                    return self._truncate(stdout.strip())
                except ToolExecutionError:
                    stdout, stderr, rc = self._run_subprocess(
                        ["pip", "list"], allow_failure=True, timeout=30,
                    )
                    return self._truncate(stdout.strip())

        return f"Dependency tree not supported for: {manager}. Use run_command instead."

    # ── Security Tools ────────────────────────────────────────────────

    def secrets_scan(self, path: str | None = None, tool: str = "auto") -> str:
        scan_path = path or "."

        if tool == "auto":
            # Try gitleaks first
            try:
                stdout, stderr, rc = self._run_subprocess(
                    ["gitleaks", "detect", "--source", scan_path, "--report-format", "json", "--no-git"],
                    allow_failure=True, timeout=120,
                )
                if rc == 0:
                    return json.dumps({"tool": "gitleaks", "findings": [], "status": "clean"})
                try:
                    findings = json.loads(stdout)
                    return json.dumps({
                        "tool": "gitleaks",
                        "total_findings": len(findings),
                        "findings": findings[:20],
                    }, indent=2)[:_MAX_OUTPUT_CHARS]
                except (json.JSONDecodeError, TypeError):
                    pass
            except ToolExecutionError:
                pass  # gitleaks not installed, fall through to builtin

            tool = "builtin"

        if tool == "builtin":
            return self._builtin_secrets_scan(scan_path)
        elif tool == "gitleaks":
            stdout, stderr, rc = self._run_subprocess(
                ["gitleaks", "detect", "--source", scan_path, "--report-format", "json", "--no-git"],
                allow_failure=True, timeout=120, install_hint="brew install gitleaks",
            )
            try:
                findings = json.loads(stdout) if stdout.strip() else []
                return json.dumps({
                    "tool": "gitleaks",
                    "total_findings": len(findings),
                    "findings": findings[:20],
                }, indent=2)[:_MAX_OUTPUT_CHARS]
            except (json.JSONDecodeError, TypeError):
                return self._truncate(stdout + stderr)
        else:
            raise ToolExecutionError(f"Unknown secrets scan tool: {tool}")

    def _builtin_secrets_scan(self, scan_path: str) -> str:
        """Scan files using built-in regex patterns."""
        all_findings: list[dict[str, Any]] = []
        root = self.workspace_root / scan_path if scan_path != "." else self.workspace_root

        if root.is_file():
            files_to_scan = [root]
        else:
            files_to_scan = []
            skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs]
                for fname in filenames:
                    if fname.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".env", ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini", ".conf")):
                        files_to_scan.append(Path(dirpath) / fname)
                if len(files_to_scan) > 500:
                    break

        for fpath in files_to_scan[:500]:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")[:50_000]
                rel = str(fpath.relative_to(self.workspace_root))
                findings = scan_text_for_secrets(text, rel)
                all_findings.extend(findings)
            except OSError:
                continue
            if len(all_findings) > 50:
                break

        return json.dumps({
            "tool": "builtin_regex",
            "total_findings": len(all_findings),
            "files_scanned": len(files_to_scan),
            "findings": all_findings[:50],
        }, indent=2)[:_MAX_OUTPUT_CHARS]

    def security_check(
        self, tool: str = "auto", path: str | None = None, severity: str | None = None,
    ) -> str:
        scan_path = path or "."

        if tool == "auto":
            # Try to detect: bandit for Python, semgrep for general
            pyproject = self.workspace_root / "pyproject.toml"
            req = self.workspace_root / "requirements.txt"
            if pyproject.exists() or req.exists():
                tool = "bandit"
            else:
                tool = "semgrep"

        if tool == "bandit":
            argv = ["bandit", "-r", "-f", "json"]
            if severity:
                sev_map = {"low": "l", "medium": "m", "high": "h"}
                argv.extend(["-ll" if severity == "high" else "-l"])
            argv.append(scan_path)

            stdout, stderr, rc = self._run_subprocess(
                argv, allow_failure=True, timeout=120, install_hint="pip install bandit",
            )
            try:
                data = json.loads(stdout)
                results = data.get("results", [])
                issues = [
                    {
                        "file": r.get("filename", "?"),
                        "line": r.get("line_number", 0),
                        "severity": r.get("issue_severity", "?"),
                        "confidence": r.get("issue_confidence", "?"),
                        "message": r.get("issue_text", ""),
                        "test_id": r.get("test_id", ""),
                    }
                    for r in results[:30]
                ]
                return json.dumps({
                    "tool": "bandit",
                    "total_issues": len(results),
                    "issues": issues,
                }, indent=2)[:_MAX_OUTPUT_CHARS]
            except (json.JSONDecodeError, TypeError):
                return self._truncate(stdout + stderr)

        elif tool == "semgrep":
            argv = ["semgrep", "--json", "--config", "auto", scan_path]
            stdout, stderr, rc = self._run_subprocess(
                argv, allow_failure=True, timeout=180, install_hint="pip install semgrep",
            )
            try:
                data = json.loads(stdout)
                results = data.get("results", [])
                issues = [
                    {
                        "file": r.get("path", "?"),
                        "line": r.get("start", {}).get("line", 0),
                        "severity": r.get("extra", {}).get("severity", "?"),
                        "message": r.get("extra", {}).get("message", ""),
                        "rule": r.get("check_id", ""),
                    }
                    for r in results[:30]
                ]
                return json.dumps({
                    "tool": "semgrep",
                    "total_issues": len(results),
                    "issues": issues,
                }, indent=2)[:_MAX_OUTPUT_CHARS]
            except (json.JSONDecodeError, TypeError):
                return self._truncate(stdout + stderr)

        raise ToolExecutionError(f"Unknown security tool: {tool}")
