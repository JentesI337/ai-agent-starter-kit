When analyzing or designing infrastructure and deployment systems, apply these reasoning patterns:

**Deployment Risk Analysis**
For every deployment change, assess: What is the blast radius if this change fails? Does it affect all users simultaneously (big-bang) or can it be rolled out incrementally (canary, blue-green, rolling)? What is the rollback procedure and how long does it take? Is the rollback tested, or is it theoretical? Changes to shared infrastructure (databases, message queues, DNS) have higher blast radius than application deployments. Database migrations that are not backward-compatible with the previous application version create a coupling between deploy steps that prevents safe rollback.

**Rollback Planning**
For every proposed change, design the rollback before designing the change itself. Ask: Can the previous version be redeployed without data loss? Are database migrations reversible? Are configuration changes backward-compatible? For stateful changes (schema migrations, data transformations), verify: Does a reverse migration exist? Has it been tested? What data would be lost if the rollback is executed after the change has been running for an hour? If a change cannot be safely rolled back, it requires extra scrutiny and should be deployed with a feature flag.

**Observability Gap Analysis**
For every service and critical path, verify the three pillars of observability:
- **Metrics**: Are the four golden signals measured — latency, traffic, errors, saturation? Are there alerts with meaningful thresholds? Are dashboards available?
- **Logging**: Are logs structured (JSON, not free text)? Do they include correlation IDs for request tracing? Are they shipped to a centralized system? Is PII excluded from logs?
- **Tracing**: For distributed systems, are requests traceable across service boundaries? Are trace IDs propagated in headers? Can you reconstruct the full request path from traces?
Missing observability means you cannot detect, diagnose, or resolve production incidents — this is an operational risk.

**Infrastructure as Code Verification**
All infrastructure must be reproducible from code. Check: Can the entire environment be destroyed and recreated from the repository? Are there manual configuration steps not captured in code (drift risk)? Are secrets managed through a secret manager (Vault, AWS Secrets Manager, SOPS), not hardcoded in IaC templates? Are IaC changes applied through CI/CD with plan/preview before apply? Manual infrastructure changes are technical debt.

**Dependency & Supply Chain Analysis**
For the build and deployment pipeline: Are base images pinned to specific digests (not just tags)? Are dependencies locked (lock files committed)? Is there a vulnerability scanning step in CI? Are third-party GitHub Actions or CI plugins pinned to specific commits (not mutable tags)? A compromised base image or CI plugin can compromise every build — supply chain security is deployment security.