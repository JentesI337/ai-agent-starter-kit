---
name: verify-owasp-top10
description: Verify codebase against OWASP Top 10 2021 vulnerability categories
type: validation
user_invocable: true
---

## Purpose

Check a codebase for common vulnerability patterns from the OWASP Top 10 (2021 edition). This skill scans for injection, broken authentication, sensitive data exposure, and other critical web application security risks.

## Checks

### CHECK-1: SQL Injection (A03:2021)
- severity: critical
- grep_patterns: ["parameterized", "prepared_statement", "sqlalchemy", "ORM", "placeholder", "bind_param", "sequelize", "prisma"]
- anti_patterns: ["f\".*SELECT", "f\".*INSERT", "f\".*UPDATE", "f\".*DELETE", "\\.format\\(.*SELECT", "\\+.*SELECT", "string concat.*query", "execute\\(.*%s.*%"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.go", "**/*.java", "**/*.php"]
- pass_condition: Database queries use parameterized statements or ORM, no string interpolation in SQL
- guidance: Search for raw SQL construction using string formatting (f-strings, .format(), concatenation). Verify that all database interactions use parameterized queries or an ORM layer.

### CHECK-2: Cross-Site Scripting / XSS (A03:2021)
- severity: high
- grep_patterns: ["escape", "sanitize", "DOMPurify", "bleach", "html.escape", "markupsafe", "CSP", "Content-Security-Policy"]
- anti_patterns: ["innerHTML.*=", "dangerouslySetInnerHTML", "v-html", "\\|safe", "\\|raw", "noescape", "mark_safe.*user"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.jsx", "**/*.tsx", "**/*.vue", "**/*.html"]
- pass_condition: Output encoding/escaping in place AND no unsafe HTML rendering of user input
- guidance: Check template rendering for unescaped user input. Look for React's dangerouslySetInnerHTML, Vue's v-html, Django's |safe filter, and Jinja2's |safe on user-controlled data. Verify Content-Security-Policy headers are set.

### CHECK-3: Broken Authentication (A07:2021)
- severity: critical
- grep_patterns: ["bcrypt", "argon2", "scrypt", "pbkdf2", "password_hash", "jwt.*verify", "token.*verify", "session.*secure"]
- anti_patterns: ["md5.*password", "sha1.*password", "sha256.*password(?!.*salt)", "plaintext.*password", "base64.*password", "password.*=.*password"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.go", "**/*.java"]
- pass_condition: Passwords hashed with modern algorithms (bcrypt/argon2/scrypt), no weak hashing
- guidance: Check user authentication code for password hashing algorithms. MD5, SHA1, and unsalted SHA256 are not acceptable for password storage. Verify that JWTs are properly verified with correct algorithms.

### CHECK-4: Sensitive Data Exposure (A02:2021)
- severity: high
- grep_patterns: ["HSTS", "Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "secure.*cookie", "httponly"]
- anti_patterns: ["debug=True.*production", "DEBUG.*=.*True", "stack_trace.*response", "verbose.*error.*user", "password.*response"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml"]
- pass_condition: Security headers configured, debug mode disabled in production, no sensitive data in responses
- guidance: Check for security headers (HSTS, X-Content-Type-Options, X-Frame-Options). Verify debug mode is off in production. Check that error responses don't leak stack traces or internal details.

### CHECK-5: Server-Side Request Forgery / SSRF (A10:2021)
- severity: high
- grep_patterns: ["url.*whitelist", "url.*allowlist", "validate.*url", "urlparse", "is_safe_url", "ssrf.*protect"]
- anti_patterns: ["requests.get\\(.*user", "fetch\\(.*user", "urllib.*open\\(.*user", "http.*request\\(.*input"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.go"]
- pass_condition: User-supplied URLs are validated against an allowlist before server-side requests
- guidance: Search for HTTP client calls that accept user-controlled URLs. Verify that URL validation includes scheme checking (no file://, gopher://), hostname allowlisting, and private IP range blocking.

### CHECK-6: Security Misconfiguration (A05:2021)
- severity: medium
- grep_patterns: ["helmet", "security_middleware", "cors.*origin", "rate_limit", "csrf", "CSRF_PROTECT"]
- anti_patterns: ["CORS.*\\*", "Access-Control-Allow-Origin.*\\*", "allow_all_origins", "csrf.*disabled", "csrf.*exempt.*all"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml"]
- pass_condition: Security middleware configured (CORS, CSRF, rate limiting), no overly permissive settings
- guidance: Check for CORS misconfiguration (wildcard origins), disabled CSRF protection, missing rate limiting. Verify that default credentials and example configurations are not deployed.

### CHECK-7: Insecure Dependencies (A06:2021)
- severity: medium
- grep_patterns: ["safety", "snyk", "npm audit", "dependabot", "renovate", "pip-audit", "trivy"]
- anti_patterns: ["npm audit.*--force", "safety.*ignore", "vulnerability.*ignore"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml", "**/*.toml", "**/Dockerfile"]
- pass_condition: Dependency vulnerability scanning configured in CI/CD pipeline
- guidance: Check for dependency scanning tools in CI configuration (GitHub Actions, GitLab CI). Verify that known vulnerability databases are checked during builds. Look for lock files (package-lock.json, poetry.lock) to ensure reproducible builds.
