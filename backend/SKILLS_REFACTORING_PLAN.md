# Skills Refactoring Plan (Backend)

Stand: 2026-03-02

## 1) Zielsetzung

Ziel ist **kein Rewrite**, sondern ein risikoarmes Refactoring mit Strangler-Ansatz:

- Bestehende stabile Kernpfade (Orchestrator, Subrun-Lane, Runtime) bleiben intakt.
- Neue Skills-Engine wird parallel aufgebaut und schrittweise aktiviert.
- Legacy-Mechanismus (`custom_agents`) bleibt übergangsweise verfügbar.

## 2) Scope

### In Scope

- Neues Modul `app/skills/*` (Domain, Parsing, Discovery, Eligibility, Snapshot, Prompt).
- Feature-Flags für kontrollierte Aktivierung.
- Minimal-invasive Integration in `HeadAgent` vor Tool-Selection.
- Observability: neue Lifecycle-Ereignisse für Skill-Auswahl.
- Testabdeckung (Unit + Integration + E2E/Contract-Erweiterungen).

### Out of Scope (Phase 1/2)

- Vollständige Entfernung von `custom_agents` (stattdessen Hybrid-Modell: Skills-Engine + Frontend-Workflows mit platzierten `custom_agents`).
- Große Änderungen am WS/REST Contract ohne Flag.
- Persistenzwechsel (z. B. DB-Migration).

## 3) Architekturprinzipien

1. **Backward Compatibility first**
   - Bestehende API-/WS-Verträge dürfen sich ohne Flag nicht ändern.
2. **Deterministische Skill-Selektion**
   - Regelbasierte Vorauswahl + LLM-Unterstützung, nicht rein heuristisch.
3. **Deny-by-default bei Unsicherheit**
   - Unvollständige/invaliden Skill-Metadaten führen zu Nicht-Berücksichtigung.
4. **Isolation pro Run/Subrun**
   - Skill-Snapshot ist run-spezifisch; Vererbung in Subruns explizit steuern.
5. **Observability vor Rollout**
   - Skill-Events müssen vor breiter Aktivierung vorhanden sein.
6. **Hybrid statt Entweder-Oder**
   - `custom_agents` bleiben als Frontend-Workflow-Bausteine erhalten; Skills ergänzen die Agent-Intelligenz und ersetzen nicht pauschal Workflow-Platzhalter.

## 4) Besonderheiten der bestehenden Codebase (kritisch)

- Pipeline-Reihenfolge ist klar: Plan → Tool Selection/Execution → Synthese (`app/agent.py`).
- Policy-Auflösung ist geschichtet und semantisch wichtig (`deny` > `allow`) (`app/services/tool_policy_service.py`).
- Subrun-Tiefe/Kind-Limits und Sichtbarkeitslogik sind kritisch (`app/orchestrator/subrun_lane.py`).
- Dateibasierte Persistenz und Laufzeitzustand sind produktiv relevant (`state_store`, `memory_store`).
- Runtime-Switch local/api darf nicht destabilisiert werden (`runtime_manager`).

## 5) Zielarchitektur Skills-Modul

Neues Modul `app/skills`:

- `models.py`
  - `SkillDefinition`, `SkillMetadata`, `SkillEligibility`, `SkillSnapshot`.
- `parser.py`
  - Frontmatter-Parser für `SKILL.md`.
- `discovery.py`
  - Discovery aus `workspace/skills`, optional weiteren Roots.
- `eligibility.py`
  - Filterung nach OS, Env, Binärabhängigkeiten, Limits.
- `snapshot.py`
  - Run-spezifischer Snapshot mit Promptbudget und Truncation-Info.
- `prompt.py`
  - Deterministische Prompt-Komposition für verfügbare Skills.
- `service.py`
  - Fassade für Agent-Integration.

## 6) Migrationsplan (Phasen)

## Phase A – Foundation (Woche 1)

- Skills-Modul als read-only Domain aufbauen.
- Config-Flags ergänzen (default: aus).
- Unit-Tests für Parser + Eligibility + Discovery.

**Abnahme:**
- Keine Verhaltensänderung bei Default-Config.
- Tests grün, keine neuen Contracts.

## Phase B – HeadAgent Integration (Woche 2)

- Vor Tool-Selection Skill-Kontext ermitteln (Flag-gesteuert).
- Skill-Prompt in Tool-Selection-Kontext einfließen lassen.
- Lifecycle-Events hinzufügen (`skills_discovered`, `skills_truncated`, `skills_skipped_canary`).

**Abnahme:**
- Mit deaktiviertem Flag 100% Legacy-Verhalten.
- Mit aktiviertem Flag reproduzierbare Skill-Events.

## Phase C – Control Plane & Inspection (Woche 3)

- Neue read-only Endpunkte:
   - `POST /api/control/skills.list`
  - `POST /api/control/skills.preview`
   - `POST /api/control/skills.check`
- Sync-Endpunkt:
   - `POST /api/control/skills.sync` (dry-run/apply, optional `clean_target`, Guardrails)

**Abnahme:**
- Endpunkte liefern stabile Schema-Antworten.
- Kein Einfluss auf bestehende Endpunkte.

## Phase D – Rollout & Hardening (Woche 4)

- Canary-Rollout pro Agent-ID/Profil.
- Benchmark-Vergleich gegen Baseline.
- Incident-Runbook + Rollback über Flags.

**Abnahme:**
- Keine regressiven Contract-Breaks.
- Metriken und Fehlerbild im akzeptierten Rahmen.

## 7) Feature-Flags (aktuell)

- `SKILLS_ENGINE_ENABLED` (bool, default `false`)
- `SKILLS_CANARY_ENABLED` (bool, default `false`)
- `SKILLS_CANARY_AGENT_IDS` (csv, default `head-agent`)
- `SKILLS_CANARY_MODEL_PROFILES` (csv, default `*`)
- `SKILLS_MANDATORY_SELECTION` (bool, default `false`)
- `SKILLS_MAX_DISCOVERED` (int, default `150`)
- `SKILLS_MAX_PROMPT_CHARS` (int, default `30000`)
- `SKILLS_DIR` (path, default `<workspace>/skills`)

## 8) Risiken & Gegenmaßnahmen

1. **Prompt-Bloat / Token-Kosten**
   - Hard limits + Truncation + Eventing.
2. **Nicht deterministische Skill-Wahl**
   - Regelbasierte Vorfilterung + eindeutige Tie-Breaker.
3. **Subrun-Kontext driftet**
   - Snapshot-Vererbung explizit steuern, Tests für `mode=run|session`.
4. **Contract-Brüche in WS/REST**
   - Additive Events/Felder, keine breaking changes ohne Versionierung.
5. **Operativer Rollout-Risiko**
   - Staged rollout + schneller Flag-Rollback.
6. **Destruktive Sync-Operationen**
   - `skills.sync` mit `clean_target` nur mit expliziter Bestätigung für Apply (`confirm_clean_target=true`) und nur innerhalb `workspace_root`.

## 9) Teststrategie

### Unit

- Frontmatter parsing (valid/invalid).
- Discovery limits (count/size).
- Eligibility (OS/env/bin checks).
- Prompt truncation.

### Integration

- `HeadAgent.run` mit Flag off/on.
- Tool-selection Kontext enthält Skill-Hinweise nur bei Flag on.

### E2E / Contract

- WS-Run mit Skills-Flag on/off und Canary-Gating (`skills_skipped_canary`).
- Control Plane Endpunkte (`skills.list`, `skills.preview`, `skills.check`, `skills.sync`) stabil.
- `skills.sync` Guardrails und Audit-Felder validieren (`audit.started_at`, `audit.duration_ms`).

## 10) Definition of Done

- Skills-Modul produktionsreif hinter Flags.
- Keine Regressionen in bestehenden Tests/Contracts.
- Dokumentierte Rollout-/Rollback-Strategie.
- Monitoring/Lifecycle-Events aktiv und auswertbar.

## 11) Reihenfolge für konkrete Umsetzung (jetzt)

1. Plan-Datei hinzufügen ✅
2. Skills-Modul Grundgerüst + Modelle ✅
3. Config-Flags ergänzen ✅
4. HeadAgent minimal integrieren (nur Kontext-Aufbau, kein hartes Enforcement) ✅
5. Tests + Fehlerprüfung ✅
6. API-Inspection-Endpunkte (`skills.list`, `skills.preview`, `skills.check`) ✅
7. `skills.sync` (dry-run/apply + `clean_target` + Guardrails + Audit) ✅
8. Nächster Schwerpunkt: Rollout-Hardening (Canary-Aussteuerung, Benchmark/Monitoring, Runbook-Finalisierung)
