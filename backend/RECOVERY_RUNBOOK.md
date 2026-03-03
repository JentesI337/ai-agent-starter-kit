# Recovery Runbook (Session 5)

Stand: 02.03.2026

## Ziel
Schnelle Diagnose und Handlungsempfehlungen für Recovery-Telemetrie im laufenden Betrieb.

## Primäre Quelle
- Lifecycle-Event: `model_recovery_summary`
- Mapping: `monitoring/RECOVERY_TELEMETRY_MAPPING.md`
- Alert-Profile: `monitoring/RECOVERY_ALERT_PROFILES.md`

## Diagnose-Matrix

### Bucket: `disabled`
- Bedeutung: Priorisierungsmechanismus wurde per Konfiguration nicht angewendet.
- Typische Ursachen:
  - Feature-Flag deaktiviert
  - Runtime-/Umgebungsprofil ohne Aktivierung
- Maßnahmen:
  1. Konfig-Flags prüfen (`signal_priority_enabled`, `strategy_feedback_enabled`, `persistent_priority_enabled`)
  2. Erwartete Profile/Runtime validieren
  3. Nach Aktivierung Trend auf `applied_vs_not_applied` beobachten

### Bucket: `not_applicable`
- Bedeutung: Mechanismus war für den konkreten Reason/Pfad nicht relevant.
- Typische Ursachen:
  - Recovery-Reason außerhalb des unterstützten Pfades
  - Eventuell erwartbares Verhalten bei gemischtem Fehlerprofil
- Maßnahmen:
  1. `reason_counts` und `final_reason` vergleichen
  2. Prüfen, ob Not-Applicable domänenseitig plausibel ist
  3. Nur bei unerwarteter Häufung Alarm-Schwellen anpassen

### Bucket: `no_reorder`
- Bedeutung: Priorisierung war aktiv, aber Reihenfolge war bereits optimal.
- Typische Ursachen:
  - Heuristik entscheidet korrekt gegen Reorder
  - Vorherige Schritte haben bereits optimale Reihenfolge erzeugt
- Maßnahmen:
  1. Nicht automatisch als Fehler werten
  2. Mit `final_outcome` korrelieren (wenn Erfolg stabil, meist unkritisch)
  3. Nur bei gleichzeitiger Hard-Failure-Spitze tiefer analysieren

## Eskalationsregeln (empfohlen)
1. Erst Alarm bei Kombinationssignal:
   - steigende Hard-Failure-Rate
   - plus signifikanter Shift in `reason_counts` oder `branch_counts`
2. Einzelne Bucket-Ausschläge ohne Outcome-Verschlechterung nicht sofort eskalieren.

## Alert-Tuning-Protokoll (Session 6)
1. Baseline erfassen
  - Mindestens 7 Tage Metrikverlauf sammeln (`final_outcome`, `attempts`, `reason_counts`, `*_not_applied_breakdown`).
2. Profil wählen
  - Start: `conservative`, danach stufenweise `balanced`.
3. Canary-Rollout
  - Schwellen zuerst auf Teiltraffic oder begrenzten Scope anwenden.
4. Beobachtung
  - 48 Stunden Alert-Noise, Präzision und verpasste Incidents beobachten.
5. Nachjustierung
  - Nur eine Variable pro Iteration ändern (z. B. `hard_failure_rate_threshold`).
6. Dokumentation
  - Datum, alte/neue Schwellen, Erwartung, Ergebnis, nächste Maßnahme dokumentieren.

## Post-Change Checkliste
1. Gezielte Tests ausführen (Recovery-Suites)
2. Event-Payload auf Pflichtfelder prüfen
3. Dashboard-Verlauf 30-60 Minuten beobachten
4. Gewähltes Alert-Profil + Kalibrierungsstand im Team-Log festhalten
