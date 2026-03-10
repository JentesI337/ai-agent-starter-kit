## Validation Skill Execution Protocol

When you read a SKILL.md file with `type: validation`, follow this procedure:

### For each CHECK in the skill:

1. **Search for positive patterns**: Run `grep_search` with each `grep_patterns` entry across the specified `file_globs`. Record which files and lines match.

2. **Search for anti-patterns**: Run `grep_search` with each `anti_patterns` entry across the same `file_globs`. Anti-pattern matches indicate potential violations.

3. **Evaluate the pass condition**: Based on the combined results from steps 1 and 2, determine the check status:
   - **PASS**: Positive patterns found AND no anti-patterns found (or anti-patterns are clearly in non-relevant context).
   - **FAIL**: Anti-patterns found in relevant code paths, OR required positive patterns are completely absent.
   - **WARNING**: Inconclusive — some positive patterns found but anti-patterns also present, or coverage is unclear.
   - **N/A**: The check is not applicable to this codebase (e.g., checking for card data handling in a system that doesn't process payments).

4. **Record evidence**: For each finding, note the specific file path and line number.

5. **Read the guidance field** for additional context on how to interpret results.

### Output format

Present results as a structured table:

| Check | Severity | Status | Evidence | Recommendation |
|-------|----------|--------|----------|----------------|
| CHECK-1: Title | critical | FAIL | `path/file.py:42` — unencrypted PHI storage | Encrypt PHI at rest using AES-256 |
| CHECK-2: Title | high | PASS | `config/tls.yaml:3` — TLS 1.3 configured | — |

### Summary

After the table, provide:
- **Overall assessment**: How many checks passed/failed/warned
- **Critical findings**: Any FAIL with severity "critical" requires immediate attention
- **Recommended actions**: Prioritized list of remediation steps