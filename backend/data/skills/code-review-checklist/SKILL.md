---
name: code-review-checklist
description: Systematische Code-Review nach Industry-Best-Practices mit strukturierter Checkliste.
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# Code Review Checklist

Systematische Code-Review nach Industry-Best-Practices.

## Instructions

Prüfe Code systematisch anhand dieser Checkliste:

### Korrektheit
- [ ] Logik implementiert die Anforderung
- [ ] Edge Cases behandelt (null, leer, Grenzwerte)
- [ ] Error Handling vollständig (try/except mit spezifischen Exceptions)

### Sicherheit
- [ ] Keine Hardcoded Secrets
- [ ] Input-Validierung vorhanden
- [ ] SQL-Injection/XSS-Schutz (wenn relevant)

### Wartbarkeit
- [ ] Funktions-/Variablennamen sind self-documenting
- [ ] Keine Magic Numbers (Konstanten extrahiert)
- [ ] Single Responsibility Principle eingehalten
- [ ] Duplizierten Code extrahiert

### Performance
- [ ] Keine N+1-Queries
- [ ] Keine unnötigen Schleifen über große Datenmengen
- [ ] Caching erwogen (wenn sinnvoll)

### Tests
- [ ] Happy Path getestet
- [ ] Error Cases getestet
- [ ] Edge Cases getestet

Bewerte jeden Punkt mit ✅/⚠️/❌ und liefere eine Zusammenfassung.
