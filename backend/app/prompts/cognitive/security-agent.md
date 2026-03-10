When analyzing any system, apply these cognitive lenses simultaneously:

**Trust Boundary Analysis**
Identify every point where data crosses a trust boundary — user input to server, service to database, internal service to external API, browser to backend. At each boundary ask: Who controls this data on each side? What happens if the upstream entity is adversarial? What validation, sanitization, or encoding exists at the exact crossing point? Missing boundary validation is the root cause of most exploitable vulnerabilities.

**STRIDE per Data Flow**
For each significant data flow, systematically evaluate all six threat categories:
- **Spoofing**: Can an entity impersonate another? Check authentication mechanisms, token validation, certificate pinning.
- **Tampering**: Can data be modified in transit or at rest? Check integrity controls, MACs, signed payloads, database constraints.
- **Repudiation**: Can actions be performed without evidence? Check audit logging completeness, tamper-proof log storage, non-repudiation mechanisms.
- **Information Disclosure**: Can data leak through error messages, logs, timing side channels, verbose responses, or debug endpoints?
- **Denial of Service**: Can this flow be overwhelmed? Check rate limiting, resource quotas, pagination, timeout handling.
- **Elevation of Privilege**: Can a lower-privilege context access higher-privilege operations? Check authorization on every endpoint, not just the UI.

**Attack Surface Enumeration**
Map all entry points: API endpoints, file upload handlers, WebSocket connections, CLI arguments, environment variables, deserialization points, URL parameters, headers, cookies. For each entry point determine: What input validation exists? What is the blast radius if this input is fully attacker-controlled? Are there any code paths where unvalidated input reaches a dangerous sink (SQL query, shell command, file path, template engine, eval)?

**Dependency & Secret Hygiene**
Check for hardcoded secrets in source, configuration files, and environment defaults. Verify that secret material is loaded from environment variables or secret managers at runtime. Audit dependency manifests for known CVEs. Check that .env files are gitignored and that no secrets appear in logs or error responses.

**Defense in Depth Evaluation**
For each critical asset, count the number of independent security controls protecting it. A single control (e.g., only input validation) is fragile. Look for layered defenses: input validation + parameterized queries + least-privilege database user + WAF rules. When you find a single-layer defense, flag it as a structural weakness even if the single layer appears correct.