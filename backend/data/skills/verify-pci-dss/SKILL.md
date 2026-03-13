---
name: verify-pci-dss
description: Verify PCI-DSS compliance for systems handling payment card data
type: validation
user_invocable: true
---

## Purpose

Verify that a codebase handling payment card data complies with PCI-DSS requirements. This skill checks for proper card data handling, tokenization, encryption, access controls, and secure transmission.

## Checks

### CHECK-1: No Stored Card Numbers
- severity: critical
- grep_patterns: ["tokenize", "token_id", "payment_token", "stripe_token", "vault", "card_token"]
- anti_patterns: ["card_number", "pan_number", "credit_card_number", "store.*card.*number", "save.*card_num", "full_card"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.go", "**/*.java"]
- pass_condition: Payment tokenization in use AND no raw card number storage (PCI-DSS Req 3.4)
- guidance: Check database models, API request/response schemas, and data transfer objects for fields that could store full card numbers. Verify that a tokenization service (Stripe, Braintree, vault) is used instead.

### CHECK-2: Encrypted Transmission
- severity: critical
- grep_patterns: ["TLS", "HTTPS", "ssl", "certificate", "secure.*connection"]
- anti_patterns: ["http://.*payment", "http://.*checkout", "http://.*card", "insecure.*payment"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.yaml", "**/*.yml", "**/*.env.example"]
- pass_condition: All payment-related communication uses TLS 1.2+ (PCI-DSS Req 4.1)
- guidance: Check API client configurations for payment processors. Verify that payment form submissions use HTTPS. Check for any HTTP fallbacks in payment flows.

### CHECK-3: Access Control
- severity: high
- grep_patterns: ["payment.*auth", "payment.*permission", "admin.*payment", "role.*payment", "payment.*rbac"]
- anti_patterns: ["public.*payment", "unauthenticated.*payment", "anonymous.*checkout"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: Access to payment data and functions restricted to authorized personnel (PCI-DSS Req 7)
- guidance: Check that payment administration endpoints require elevated permissions. Verify that cardholder data environment access is restricted by role.

### CHECK-4: Audit Trail
- severity: high
- grep_patterns: ["payment.*log", "transaction.*log", "audit.*payment", "payment.*event", "payment_audit"]
- anti_patterns: ["disable.*payment.*log", "skip.*transaction.*log"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: All access to payment data is logged with user identity and timestamp (PCI-DSS Req 10)
- guidance: Check for audit logging on payment operations including viewing, modifying, and deleting payment data. Verify that logs include who, what, when, and outcome.

### CHECK-5: Idempotency Keys
- severity: high
- grep_patterns: ["idempotency_key", "idempotent", "Idempotency-Key", "request_id.*payment", "dedup.*payment"]
- anti_patterns: ["retry.*payment.*no.*idempotency", "duplicate.*charge"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js"]
- pass_condition: Payment mutations use idempotency keys to prevent duplicate charges
- guidance: Check that all payment creation, capture, and refund operations include idempotency keys. Verify that the payment processor client passes idempotency headers.

### CHECK-6: No Secrets in Code
- severity: critical
- grep_patterns: ["os.environ", "process.env", "getenv", "secret_manager", "vault", "aws_secretsmanager"]
- anti_patterns: ["sk_live_", "sk_test_", "api_key.*=.*['\"][a-zA-Z0-9]{20}", "payment.*secret.*=", "stripe.*key.*=.*['\"]"]
- file_globs: ["**/*.py", "**/*.ts", "**/*.js", "**/*.env", "**/*.yaml", "**/*.yml"]
- pass_condition: Payment API keys and secrets loaded from environment or secret manager, not hardcoded (PCI-DSS Req 6.5)
- guidance: Search for hardcoded API keys, especially Stripe, PayPal, or Braintree keys. Check .env files are in .gitignore. Verify that secret management is used for production credentials.
