---
name: legaltech-compliance
description: >
  Analyzes software for GDPR, CCPA, AI Act compliance.
  Scans OSS licenses, performs DPIAs, reviews cookie consent and data transfers.
requires_bins: []
os: any
user_invocable: true
---

# LegalTech Compliance Analysis

## When to Apply
- Any software processing personal data (PII)
- Open-source dependency license audits
- AI/ML model deployments (EU AI Act)
- Cookie consent and tracking implementations
- Cross-border data transfers (EU → US, etc.)
- Privacy policy and terms of service reviews

## Checklist

### GDPR / DSGVO Compliance
- [ ] Legal basis identified for each processing activity (Art. 6)
- [ ] Data Processing Records (Art. 30) maintained
- [ ] Privacy by Design and by Default implemented (Art. 25)
- [ ] Data Protection Impact Assessment (DPIA) for high-risk processing (Art. 35)
- [ ] Data Subject Rights implemented: access, rectification, erasure, portability
- [ ] Data breach notification process (72h to authority, Art. 33)
- [ ] DPO appointed if required (Art. 37)

### CCPA / CPRA (California)
- [ ] "Do Not Sell My Personal Information" link on website
- [ ] Opt-out mechanism for data sharing
- [ ] Consumer request handling within 45 days
- [ ] Financial incentive programs disclosed
- [ ] Service provider contracts include CCPA clauses

### EU AI Act
- [ ] AI system risk classification (Unacceptable / High / Limited / Minimal)
- [ ] High-risk AI: conformity assessment, human oversight, transparency
- [ ] AI-generated content labeled (Art. 52)
- [ ] Training data documentation and bias assessment
- [ ] Fundamental rights impact assessment for high-risk systems

### OSS License Scanning
- [ ] All dependencies scanned for license type
- [ ] Copyleft licenses (GPL, AGPL) flagged for compatibility
- [ ] License obligations documented (attribution, source disclosure)
- [ ] SBOM (Software Bill of Materials) generated
- [ ] No license-incompatible combinations (e.g., GPL + proprietary)

### Cookie Consent & ePrivacy
- [ ] Cookie banner with granular opt-in (not just "Accept All")
- [ ] No tracking cookies set before consent
- [ ] Consent stored with timestamp and scope
- [ ] Cookie policy lists all cookies with purpose and retention
- [ ] Third-party tracking pixels require separate consent

### Cross-Border Data Transfers
- [ ] Adequacy decision check (EU Commission list)
- [ ] Standard Contractual Clauses (SCCs) where needed
- [ ] Transfer Impact Assessment (TIA) documented
- [ ] Supplementary measures for non-adequate countries
- [ ] Binding Corporate Rules for intra-group transfers

## Output Format
```
## Compliance Posture
| Regulation | Status | Key Gaps |
|---|---|---|

## Findings
| # | Severity | Regulation | Article | Finding | Remediation |
|---|---|---|---|---|---|

## License Audit
| Dependency | License | Compatible | Notes |
|---|---|---|---|

## Data Protection Impact
DPIA summary and recommendations.
```
