# Recovery Alert Profiles (Session 6 — Slice 3)

Stand: 02.03.2026

## Ziel
Kalibrierbare Startprofile für Recovery-Alerts, damit Teams je Umgebung kontrolliert zwischen Sensitivität und Rauscharmut wählen können.

## Nutzung
- Quellevent: model_recovery_summary
- Mapping-Referenz: monitoring/RECOVERY_TELEMETRY_MAPPING.md
- Runbook-Referenz: RECOVERY_RUNBOOK.md

## Profile

### conservative (Default für frische Rollouts)
- hard_failure_rate_threshold: 0.08
- hard_failure_window_minutes: 15
- disabled_dominance_threshold: 0.80
- disabled_dominance_window_minutes: 30
- attempts_p95_threshold: 3.0
- attempts_window_minutes: 15
- context_overflow_spike_multiplier_vs_24h: 2.5

### balanced (Default für stabile Stages)
- hard_failure_rate_threshold: 0.05
- hard_failure_window_minutes: 15
- disabled_dominance_threshold: 0.70
- disabled_dominance_window_minutes: 30
- attempts_p95_threshold: 2.0
- attempts_window_minutes: 15
- context_overflow_spike_multiplier_vs_24h: 2.0

### aggressive (nur mit reifer Baseline)
- hard_failure_rate_threshold: 0.03
- hard_failure_window_minutes: 10
- disabled_dominance_threshold: 0.60
- disabled_dominance_window_minutes: 20
- attempts_p95_threshold: 1.8
- attempts_window_minutes: 10
- context_overflow_spike_multiplier_vs_24h: 1.5

## Auswahlregel
1. Neue Umgebung: conservative
2. Nach 7-14 Tagen stabilen Metriken: balanced
3. Nur bei geringer Alert-Noise und guter Baseline-Qualität: aggressive

## Change-Protokoll (Minimum)
- gewähltes Profil
- Datum/Uhrzeit Umstellung
- erwartete Wirkung
- Beobachtungsfenster (mind. 48h)
- Ergebnis und ggf. Rollback-Entscheidung
