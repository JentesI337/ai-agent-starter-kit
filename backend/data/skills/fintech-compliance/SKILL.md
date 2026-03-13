---
name: fintech-compliance
description: >
  Analyzes financial software for PCI-DSS, PSD2, MiFID II compliance.
  Reviews payment flows, ledger designs, audit trails, and fraud detection patterns.
requires_bins: []
os: any
user_invocable: true
---

# FinTech Compliance Analysis

## When to Apply
- Payment gateway integration (Stripe, Adyen, SEPA, PayPal)
- Ledger / double-entry bookkeeping implementations
- Transaction processing with idempotency requirements
- Fraud detection and rate-limiting patterns
- Financial audit trail and logging

## Checklist

### PCI-DSS
- [ ] No raw card numbers stored in code, logs, or database
- [ ] Card data encrypted in transit (TLS 1.2+) and at rest
- [ ] Tokenization used for recurring payments
- [ ] Access to cardholder data restricted by role (Req 7)
- [ ] Audit logs for all access to payment data (Req 10)

### PSD2 / Strong Customer Authentication
- [ ] Two-factor authentication on payment initiation
- [ ] 3D Secure 2.0 integration for card payments
- [ ] Open Banking API endpoints follow Berlin Group / UK OB standards
- [ ] Consent management for third-party access (AISP/PISP)

### Transaction Integrity
- [ ] Idempotency keys on all mutation endpoints
- [ ] Double-entry: every debit has a matching credit
- [ ] Race-condition protection on balance checks (SELECT FOR UPDATE / optimistic locking)
- [ ] Retry logic with exponential backoff for payment gateway calls
- [ ] Dead-letter queue for failed transactions

### Audit Trail
- [ ] All financial operations logged with timestamp, actor, before/after state
- [ ] Logs are immutable (append-only or write-once storage)
- [ ] Retention period meets regulatory requirements (5+ years)
- [ ] Sensitive data masked in logs (card numbers, account numbers)

## Output Format
```
## Compliance Status
| Regulation | Status | Gaps |
|---|---|---|

## Findings
| # | Severity | Category | Description | Recommendation |
|---|---|---|---|---|

## Payment Flow
Transaction flow diagram with identified risks.

## Audit Trail Assessment
Logging completeness and gaps.
```
