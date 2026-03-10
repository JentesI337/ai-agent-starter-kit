When analyzing health technology systems, apply these domain-specific reasoning patterns:

**Minimum Necessary Access Principle**
HIPAA's minimum necessary standard requires that access to Protected Health Information (PHI) be limited to what is needed for a specific purpose. For every code path that reads or writes PHI, ask: Does this access the minimum set of fields required? Are there broader queries that return more PHI than needed (e.g., SELECT * from patient records when only the name is needed)? Are access controls role-based and granular, or does a single "healthcare worker" role grant access to all records? Check for logging — every PHI access should be auditable with who, what, when, and why.

**De-Identification Evaluation**
When PHI is used for analytics, research, or testing, it must be de-identified per HIPAA Safe Harbor or Expert Determination methods. For Safe Harbor, verify removal of all 18 identifiers: names, geographic data smaller than state, dates (except year) related to an individual, phone/fax numbers, email addresses, SSN, medical record numbers, health plan beneficiary numbers, account numbers, certificate/license numbers, vehicle identifiers, device identifiers, URLs, IP addresses, biometric identifiers, full-face photographs, and any other unique identifying number. Check that test fixtures and seed data don't contain real patient information.

**Breach Notification Path Analysis**
HIPAA requires notification within 60 days of discovering a breach. Trace the technical controls that would detect a breach: Are there alerts for unusual PHI access patterns? Is there monitoring for bulk data exports? Are failed authentication attempts logged and alarmed? For each data store containing PHI, verify: Is access logged? Are logs sent to a tamper-resistant store? Is there an automated or semi-automated process to detect unauthorized access? The absence of breach detection capability is itself a compliance gap.

**Consent Flow Verification**
Patient consent for data sharing must be explicit, informed, and revocable. Trace consent through the system: Where is consent captured? How is it stored? Is it checked before every data sharing operation? Can it be revoked, and does revocation propagate to all downstream systems? For research data: Is there an IRB approval tracking mechanism? Are consent expiration dates enforced?

**Interoperability Standards Compliance**
For HL7 FHIR interfaces: Are resources correctly structured per the applicable FHIR profiles? Are required fields present? Are code systems (SNOMED CT, LOINC, ICD-10) used correctly? For DICOM: Are patient identifiers consistently mapped? Is data integrity maintained during format conversions? Check that interoperability endpoints enforce authentication and authorization — an unauthenticated FHIR endpoint is a PHI breach waiting to happen.