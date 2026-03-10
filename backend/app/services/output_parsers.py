"""Pure parsing functions for structured tool output.

Each parser takes raw stdout/stderr text and returns a Python dict or list
that can be JSON-serialised for the agent.  No state, no subprocess calls.
"""
from __future__ import annotations

import json
import re
from typing import Any


# ── Git parsers ──────────────────────────────────────────────────────

_GIT_LOG_SEP = "---GIT_LOG_ENTRY---"

GIT_LOG_FORMAT_SHORT = f"%H%n%an%n%ai%n%s%n{_GIT_LOG_SEP}"
GIT_LOG_FORMAT_ONELINE = "%h %s"
GIT_LOG_FORMAT_FULL = f"%H%n%an%n%ae%n%ai%n%B%n{_GIT_LOG_SEP}"


def parse_git_log_short(raw: str) -> list[dict[str, str]]:
    """Parse output of ``git log --format=GIT_LOG_FORMAT_SHORT``."""
    entries: list[dict[str, str]] = []
    for block in raw.split(_GIT_LOG_SEP):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 4:
            continue
        entries.append({
            "hash": lines[0].strip(),
            "author": lines[1].strip(),
            "date": lines[2].strip(),
            "message": lines[3].strip(),
        })
    return entries


def parse_git_log_full(raw: str) -> list[dict[str, str]]:
    """Parse output of ``git log --format=GIT_LOG_FORMAT_FULL``."""
    entries: list[dict[str, str]] = []
    for block in raw.split(_GIT_LOG_SEP):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 5:
            continue
        entries.append({
            "hash": lines[0].strip(),
            "author": lines[1].strip(),
            "email": lines[2].strip(),
            "date": lines[3].strip(),
            "message": "\n".join(lines[4:]).strip(),
        })
    return entries


def parse_git_blame_porcelain(raw: str) -> list[dict[str, Any]]:
    """Parse ``git blame --porcelain`` output into structured entries."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line:
            continue
        # Header line: <hash> <orig-line> <final-line> [<num-lines>]
        m = re.match(r"^([0-9a-f]{40})\s+(\d+)\s+(\d+)", line)
        if m:
            current = {
                "commit": m.group(1),
                "orig_line": int(m.group(2)),
                "final_line": int(m.group(3)),
            }
            continue
        if line.startswith("\t"):
            current["content"] = line[1:]
            # Content line marks the end of a blame entry
            entries.append(current)
            current = {}
            continue
        # Key-value metadata
        parts = line.split(" ", 1)
        key = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        if key == "author":
            current["author"] = val
        elif key == "author-time":
            current["author_time"] = val
        elif key == "summary":
            current["summary"] = val
    if current:
        entries.append(current)
    return entries


# ── Test output parsers ──────────────────────────────────────────────

def parse_pytest_output(raw: str) -> dict[str, Any]:
    """Parse pytest short output (``-q --tb=short``) into structured result."""
    result: dict[str, Any] = {
        "passed": 0, "failed": 0, "skipped": 0, "errors": [], "raw_summary": "",
    }
    lines = raw.strip().splitlines()
    # Find summary line like "5 passed, 2 failed, 1 skipped in 1.23s"
    for line in reversed(lines):
        m = re.search(r"(\d+) passed", line)
        if m:
            result["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", line)
        if m:
            result["failed"] = int(m.group(1))
        m = re.search(r"(\d+) skipped", line)
        if m:
            result["skipped"] = int(m.group(1))
        m = re.search(r"(\d+) error", line)
        if m:
            result["errors"].append({"test": "(collection)", "message": line.strip()})
        m = re.search(r"in ([\d.]+)s", line)
        if m:
            result["duration_seconds"] = float(m.group(1))
            result["raw_summary"] = line.strip()
            break

    # Extract FAILED test names and messages
    current_test = ""
    for line in lines:
        m = re.match(r"^FAILED\s+(.+?)(?:\s+-\s+(.+))?$", line)
        if m:
            result["errors"].append({
                "test": m.group(1).strip(),
                "message": (m.group(2) or "").strip(),
            })
            continue
        m = re.match(r"^(.*?)::\S+\s+FAILED", line)
        if m:
            current_test = line.strip()
        # Capture assertion errors
        if "AssertionError" in line or "assert " in line:
            if current_test:
                result["errors"].append({
                    "test": current_test,
                    "message": line.strip(),
                })
                current_test = ""
    return result


def parse_jest_json(raw: str) -> dict[str, Any]:
    """Parse jest ``--json`` output."""
    result: dict[str, Any] = {
        "passed": 0, "failed": 0, "skipped": 0, "errors": [], "raw_summary": "",
    }
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result["raw_summary"] = raw[:500]
        return result

    result["passed"] = data.get("numPassedTests", 0)
    result["failed"] = data.get("numFailedTests", 0)
    result["skipped"] = data.get("numPendingTests", 0)

    for suite in data.get("testResults", []):
        for test in suite.get("testResults", []):
            if test.get("status") == "failed":
                result["errors"].append({
                    "test": test.get("fullName", test.get("title", "?")),
                    "message": "\n".join(test.get("failureMessages", []))[:500],
                })
    return result


# ── Lint output parsers ──────────────────────────────────────────────

def parse_eslint_json(raw: str) -> list[dict[str, Any]]:
    """Parse eslint ``--format json`` output."""
    diagnostics: list[dict[str, Any]] = []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return diagnostics
    for file_entry in data:
        filepath = file_entry.get("filePath", "?")
        for msg in file_entry.get("messages", []):
            diagnostics.append({
                "file": filepath,
                "line": msg.get("line", 0),
                "column": msg.get("column", 0),
                "severity": "error" if msg.get("severity", 0) == 2 else "warning",
                "message": msg.get("message", ""),
                "rule": msg.get("ruleId", ""),
            })
    return diagnostics


def parse_ruff_json(raw: str) -> list[dict[str, Any]]:
    """Parse ruff ``--output-format json`` output."""
    diagnostics: list[dict[str, Any]] = []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return diagnostics
    for entry in data:
        loc = entry.get("location", {})
        diagnostics.append({
            "file": entry.get("filename", "?"),
            "line": loc.get("row", 0),
            "column": loc.get("column", 0),
            "severity": "error" if entry.get("fix") is None else "warning",
            "message": entry.get("message", ""),
            "rule": entry.get("code", ""),
        })
    return diagnostics


def parse_mypy_json(raw: str) -> list[dict[str, Any]]:
    """Parse mypy line-based output (file:line: severity: message)."""
    diagnostics: list[dict[str, Any]] = []
    for line in raw.strip().splitlines():
        m = re.match(r"^(.+?):(\d+):\s*(error|warning|note):\s*(.+?)(?:\s+\[(.+)\])?$", line)
        if m:
            diagnostics.append({
                "file": m.group(1),
                "line": int(m.group(2)),
                "column": 0,
                "severity": m.group(3),
                "message": m.group(4).strip(),
                "rule": m.group(5) or "",
            })
    return diagnostics


def parse_tsc_output(raw: str) -> list[dict[str, Any]]:
    """Parse TypeScript compiler output (file(line,col): error TSxxxx: message)."""
    diagnostics: list[dict[str, Any]] = []
    for line in raw.strip().splitlines():
        m = re.match(r"^(.+?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)$", line)
        if m:
            diagnostics.append({
                "file": m.group(1),
                "line": int(m.group(2)),
                "column": int(m.group(3)),
                "severity": m.group(4),
                "message": m.group(6).strip(),
                "rule": m.group(5),
            })
    return diagnostics


# ── Error / stack trace parsers ──────────────────────────────────────

def parse_python_traceback(raw: str) -> dict[str, Any]:
    """Parse a Python traceback into structured frames."""
    result: dict[str, Any] = {"error_type": "", "message": "", "frames": []}
    lines = raw.strip().splitlines()

    # Extract frames: '  File "path", line N, in func'
    for i, line in enumerate(lines):
        m = re.match(r'^\s+File "(.+?)", line (\d+)(?:, in (.+))?', line)
        if m:
            frame: dict[str, Any] = {
                "file": m.group(1),
                "line": int(m.group(2)),
                "function": m.group(3) or "",
            }
            # Next line is typically the code
            if i + 1 < len(lines) and not lines[i + 1].startswith("  File"):
                frame["code"] = lines[i + 1].strip()
            result["frames"].append(frame)

    # Last line is usually "ErrorType: message"
    for line in reversed(lines):
        line = line.strip()
        if ":" in line and not line.startswith("File") and not line.startswith("Traceback"):
            parts = line.split(":", 1)
            result["error_type"] = parts[0].strip()
            result["message"] = parts[1].strip() if len(parts) > 1 else ""
            break
    return result


def parse_node_stacktrace(raw: str) -> dict[str, Any]:
    """Parse a Node.js stack trace into structured frames."""
    result: dict[str, Any] = {"error_type": "", "message": "", "frames": []}
    lines = raw.strip().splitlines()

    # First line is usually "ErrorType: message"
    if lines:
        first = lines[0].strip()
        if ":" in first:
            parts = first.split(":", 1)
            result["error_type"] = parts[0].strip()
            result["message"] = parts[1].strip()
        else:
            result["message"] = first

    # Stack frames: "    at funcName (file:line:col)" or "    at file:line:col"
    for line in lines[1:]:
        m = re.match(r"^\s+at\s+(?:(.+?)\s+\()?(.+?):(\d+):(\d+)\)?", line)
        if m:
            result["frames"].append({
                "function": m.group(1) or "<anonymous>",
                "file": m.group(2),
                "line": int(m.group(3)),
                "column": int(m.group(4)),
            })
    return result


def parse_go_panic(raw: str) -> dict[str, Any]:
    """Parse a Go panic/stack trace."""
    result: dict[str, Any] = {"error_type": "panic", "message": "", "frames": []}
    lines = raw.strip().splitlines()

    for i, line in enumerate(lines):
        if line.startswith("panic:"):
            result["message"] = line[6:].strip()
        # Go stack frames: file:line +offset
        m = re.match(r"^\s+(.+\.go):(\d+)", line)
        if m:
            func_name = ""
            if i > 0:
                func_name = lines[i - 1].strip().split("(")[0]
            result["frames"].append({
                "file": m.group(1).strip(),
                "line": int(m.group(2)),
                "function": func_name,
            })
    return result


# ── Dependency audit parsers ─────────────────────────────────────────

def parse_npm_audit_json(raw: str) -> list[dict[str, Any]]:
    """Parse ``npm audit --json`` output."""
    vulns: list[dict[str, Any]] = []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return vulns

    # npm audit v2+ format
    for name, info in data.get("vulnerabilities", {}).items():
        vulns.append({
            "package": name,
            "severity": info.get("severity", "unknown"),
            "title": info.get("title", ""),
            "fix_available": info.get("fixAvailable", False),
            "via": [str(v) if isinstance(v, str) else v.get("title", "") for v in info.get("via", [])],
        })
    return vulns


def parse_pip_audit_json(raw: str) -> list[dict[str, Any]]:
    """Parse ``pip-audit --format json`` output."""
    vulns: list[dict[str, Any]] = []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return vulns

    for entry in data:
        for vuln in entry.get("vulns", []):
            vulns.append({
                "package": entry.get("name", "?"),
                "version": entry.get("version", "?"),
                "severity": vuln.get("fix_versions", ["unknown"])[0] if vuln.get("fix_versions") else "unknown",
                "id": vuln.get("id", ""),
                "description": vuln.get("description", "")[:200],
                "fix_versions": vuln.get("fix_versions", []),
            })
    return vulns


# ── Coverage parsers ─────────────────────────────────────────────────

def parse_coverage_json(raw: str) -> dict[str, Any]:
    """Parse coverage.py JSON report (``coverage json``)."""
    result: dict[str, Any] = {"total_percent": 0.0, "files": []}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return result

    totals = data.get("totals", {})
    result["total_percent"] = totals.get("percent_covered", 0.0)

    for filepath, info in data.get("files", {}).items():
        summary = info.get("summary", {})
        result["files"].append({
            "file": filepath,
            "percent": summary.get("percent_covered", 0.0),
            "missing_lines": info.get("missing_lines", []),
        })
    # Sort by coverage ascending (worst first)
    result["files"].sort(key=lambda f: f["percent"])
    return result


# ── Secrets scanning ─────────────────────────────────────────────────

# Built-in patterns for secrets_scan fallback
SECRETS_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)(?:aws_access_key_id|aws_secret_access_key)\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{20,}", "AWS key"),
    (r"(?i)(?:api[_-]?key|apikey)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}", "API key"),
    (r"(?i)(?:password|passwd|pwd)\s*[=:]\s*['\"]?[^\s'\"]{8,}", "Password"),
    (r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", "Private key"),
    (r"(?i)(?:secret[_-]?key|client[_-]?secret)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{10,}", "Secret key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth token"),
    (r"(?:sk-|pk-)[A-Za-z0-9]{32,}", "Stripe/OpenAI key"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT token"),
    (r"(?i)(?:connection[_-]?string|database[_-]?url)\s*[=:]\s*['\"]?[^\s'\"]{20,}", "Connection string"),
]

_COMPILED_SECRETS = [(re.compile(p), label) for p, label in SECRETS_PATTERNS]


def scan_text_for_secrets(text: str, filepath: str = "") -> list[dict[str, Any]]:
    """Scan text for hardcoded secrets using built-in regex patterns."""
    findings: list[dict[str, Any]] = []
    for line_num, line in enumerate(text.splitlines(), 1):
        for pattern, label in _COMPILED_SECRETS:
            if pattern.search(line):
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "type": label,
                    "snippet": line.strip()[:120],
                })
    return findings
