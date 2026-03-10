When analyzing financial software, apply these domain-specific reasoning patterns:

**Double-Entry Invariant Verification**
Every financial transaction must maintain the fundamental accounting equation: Assets = Liabilities + Equity. For every mutation that touches monetary values, verify: Is there a corresponding counter-entry? Can the system ever reach a state where debits and credits don't balance? Check for partial failures — what happens if the debit succeeds but the credit fails? The absence of database transactions wrapping both sides of a ledger entry is a critical defect. Look for any code path that modifies a balance without a corresponding audit trail entry.

**Idempotency Proof**
Every payment mutation, transfer, or state change must be idempotent — repeating the same request must produce the same result without duplicate effects. For each mutating endpoint, verify: Is there an idempotency key? Is it checked before processing? What happens if the same request arrives twice within the processing window (race condition)? Is the idempotency key stored durably before the side effect executes? A non-idempotent payment endpoint will inevitably cause double-charges in production.

**Reconciliation Thinking**
Financial systems must be independently verifiable. For every data flow involving money, ask: Can an auditor reconstruct the complete history from the audit log alone? Are there two independent records that should agree (e.g., transaction log vs. account balance)? Is there a reconciliation process that detects drift? Discrepancies between derived state (current balance) and source-of-truth events (transaction history) indicate data integrity issues.

**Regulatory Traceability**
For each operation touching financial data, identify the applicable regulation (PCI-DSS for card data, PSD2 for payment services, SOX for financial reporting, AML/KYC for identity). Verify that the code satisfies the specific requirement — not "we do encryption" but "PCI-DSS Req 3.4: stored card numbers are rendered unreadable using strong cryptography with key management." Regulatory compliance is not a checkbox — it requires verifiable evidence in the code.

**Fraud Detection Gaps**
Analyze transaction flows for missing safety controls: Are there rate limits on high-value operations? Are there velocity checks (too many transactions in a short window)? Is there anomaly detection for unusual patterns (large transfers to new accounts, transactions outside normal hours)? Are transaction amount thresholds enforced at the API layer, not just the UI? Check for race conditions in balance checks — a TOCTOU (time-of-check-to-time-of-use) bug in a balance check can allow overdrafts.