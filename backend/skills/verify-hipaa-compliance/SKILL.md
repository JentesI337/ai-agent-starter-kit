---
name: verify-hipaa-compliance
description: Verify HIPAA compliance of data flows handling Protected Health Information (PHI)
type: validation
user_invocable: true
---

## Purpose

Verify that a codebase handles Protected Health Information (PHI) in compliance with HIPAA Security Rule and Privacy Rule requirements. This skill checks for encryption, access controls, audit logging, and data handling practices.

## Checks

### CHECK-1: Encryption at Rest
- severity: critical
- grep_patterns: ["AES", "encrypt", "KMS", "ENCRYPTION_KEY", "fernet", "cryptography", "at_rest", "encrypted_field", "pgcrypto", "TDE"]
- anti_patterns: ["plaintext.*patient", "unencrypted.*health", "store.*raw.*phi", "plain_text.*medical"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml", "**/*.env.example"]
- pass_condition: At least one encryption mechanism found for data storage AND no anti-patterns in data storage code paths
- guidance: Look for database encryption configuration, field-level encryption for PHI columns, KMS or key management usage. Check ORM model definitions for encrypted field types.

### CHECK-2: Encryption in Transit
- severity: critical
- grep_patterns: ["TLS", "HTTPS", "SSL", "certificate", "ssl_context", "verify_ssl", "SECURE_SSL_REDIRECT"]
- anti_patterns: ["http://(?!localhost|127\\.0\\.0\\.1)", "allow_insecure", "verify=False", "verify_ssl=False", "NODE_TLS_REJECT_UNAUTHORIZED=0", "PYTHONHTTPSVERIFY=0"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml", "**/*.env.example", "**/*.toml"]
- pass_condition: TLS/HTTPS enforced for all external communication, no insecure transport overrides
- guidance: Check API client configurations, server startup configs, database connection strings for SSL mode. Verify that certificate validation is not disabled.

### CHECK-3: Access Controls
- severity: critical
- grep_patterns: ["role_required", "permission", "authorize", "rbac", "access_control", "@login_required", "IsAuthenticated", "has_permission", "Depends.*auth"]
- anti_patterns: ["AllowAny", "public.*patient", "no_auth.*health", "skip_auth"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: Role-based or attribute-based access controls present on endpoints handling PHI
- guidance: Check API endpoint decorators/middleware for authentication and authorization. Verify that PHI endpoints require authentication and role-based authorization.

### CHECK-4: Audit Logging
- severity: high
- grep_patterns: ["audit_log", "audit_trail", "access_log", "phi_access", "hipaa_log", "event_log", "AuditEvent", "log_access"]
- anti_patterns: ["disable.*audit", "skip.*log", "no_audit"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: Audit logging mechanism present that records who accessed what PHI and when
- guidance: Look for dedicated audit logging that captures user identity, resource accessed, timestamp, and action performed. Generic application logging does not satisfy HIPAA audit requirements.

### CHECK-5: PHI in Logs
- severity: high
- grep_patterns: ["sanitize.*log", "redact", "mask.*phi", "filter.*pii", "scrub.*sensitive"]
- anti_patterns: ["log.*patient_name", "print.*ssn", "logger.*medical_record", "console.log.*health"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: Log sanitization mechanisms present AND no raw PHI written to logs
- guidance: Check that logging configuration includes filters or formatters that redact PHI fields. Search for any logging statements that directly output patient data.

### CHECK-6: Data Retention and Disposal
- severity: medium
- grep_patterns: ["retention_policy", "data_retention", "purge", "expiry", "ttl", "delete_after", "anonymize", "de_identify"]
- anti_patterns: ["keep_forever", "no_expiry.*patient", "never_delete.*health"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml"]
- pass_condition: Data retention policies defined for PHI with automated enforcement
- guidance: HIPAA requires retention of records for 6 years from date of creation or last effective date. Check for automated purge mechanisms and retention policy configurations.
