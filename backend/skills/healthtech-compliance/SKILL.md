---
name: healthtech-compliance
description: >
  Analyzes health-related software for HIPAA, GDPR, MDR compliance.
  Reviews PHI/PII data flows, consent management, HL7 FHIR interfaces, and anonymization.
requires_bins: []
os: any
user_invocable: true
---

# HealthTech Compliance Analysis

## When to Apply
- Systems processing Protected Health Information (PHI) or patient data
- HL7 FHIR / DICOM interface implementations
- Clinical workflow and electronic health record (EHR) systems
- Telemedicine / remote monitoring platforms
- Medical device software (MDR / FDA 21 CFR Part 11)

## Checklist

### HIPAA (US) / GDPR (EU) Data Protection
- [ ] PHI encrypted at rest (AES-256) and in transit (TLS 1.2+)
- [ ] Minimum necessary principle: only access data needed for function
- [ ] Business Associate Agreements (BAA) with all cloud providers
- [ ] Breach notification process documented (72h GDPR, 60d HIPAA)
- [ ] Data retention and deletion policies implemented
- [ ] Right to access / right to erasure (GDPR Art. 15, 17)

### Consent Management
- [ ] Explicit, informed consent before processing health data
- [ ] Granular consent options (treatment, research, marketing)
- [ ] Consent withdrawal mechanism with audit trail
- [ ] Re-consent triggered when processing purposes change
- [ ] Consent records are immutable and timestamped

### Access Control & Audit
- [ ] Role-based access control (RBAC) with principle of least privilege
- [ ] Multi-factor authentication for clinical data access
- [ ] All PHI access logged with user, timestamp, data accessed
- [ ] Automated alerts for unusual access patterns
- [ ] Regular access reviews and recertification

### Anonymization & Pseudonymization
- [ ] De-identification follows HIPAA Safe Harbor or Expert Determination
- [ ] K-anonymity / l-diversity applied where appropriate
- [ ] Re-identification risk assessment documented
- [ ] Analytics pipelines use pseudonymized data only
- [ ] Mapping tables stored separately with restricted access

### Interoperability (HL7 FHIR / DICOM)
- [ ] FHIR resources conform to profiles (US Core, DE Basisprofil)
- [ ] SMART on FHIR for third-party app authentication
- [ ] DICOM transfer uses TLS; WADO-RS for web access
- [ ] Terminology bindings use standard code systems (SNOMED CT, LOINC, ICD-10)

## Output Format
```
## Regulatory Compliance
| Regulation | Status | Key Gaps |
|---|---|---|

## Data Protection Assessment
| # | Risk | Data Category | Finding | Recommendation |
|---|---|---|---|---|

## Clinical Workflow Impact
Patient-safety implications of findings.

## Interoperability Status
HL7 FHIR / DICOM compliance matrix.
```
