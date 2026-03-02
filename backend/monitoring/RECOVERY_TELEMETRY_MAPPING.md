# Recovery Telemetry Mapping (Session 5)

Stand: 02.03.2026

## Ziel
Diese Zuordnung beschreibt, welche Felder aus `model_recovery_summary` für Dashboard und Alerts genutzt werden.

## Event-Quelle
- Event: `model_recovery_summary`
- Feldpfad: `details`

## Pflichtfelder für Monitoring
- `attempts`
- `max_attempts`
- `failures_total`
- `final_outcome`
- `final_model`
- `final_reason`
- `reason_counts`
- `branch_counts`
- `strategy_counts`
- `signal_priority_applied_vs_not_applied`
- `strategy_feedback_applied_vs_not_applied`
- `persistent_priority_applied_vs_not_applied`
- `signal_priority_not_applied_breakdown`
- `strategy_feedback_not_applied_breakdown`
- `persistent_priority_not_applied_breakdown`

## Dashboard-Mapping

### 1) Recovery Health
- Erfolgsquote: Anteil `final_outcome == success`
- Retry-Intensität: Mittelwert `attempts`
- Hard-Failure-Rate: Anteil `final_outcome == failure`

### 2) Reason & Branch Distribution
- Top Reasons: `reason_counts`
- Branch-Mix: `branch_counts`
- Strategy-Mix: `strategy_counts`

### 3) Priority Decision Quality
- Signal Applied Quote: `signal_priority_applied_vs_not_applied.applied / (applied + not_applied)`
- Feedback Applied Quote: `strategy_feedback_applied_vs_not_applied.applied / (applied + not_applied)`
- Persistent Applied Quote: `persistent_priority_applied_vs_not_applied.applied / (applied + not_applied)`

### 4) Not-Applied Root Causes
- Signal: `signal_priority_not_applied_breakdown.{disabled,not_applicable,no_reorder}`
- Feedback: `strategy_feedback_not_applied_breakdown.{disabled,not_applicable,no_reorder}`
- Persistent: `persistent_priority_not_applied_breakdown.{disabled,not_applicable,no_reorder}`

## Alert-Vorschläge (Startwerte)
- A1: Hard-Failure-Rate > 5% über 15 Minuten
- A2: `reason_counts.context_overflow` starker Anstieg ggü. 24h-Baseline
- A3: `*_not_applied_breakdown.disabled` dominiert über 70% über 30 Minuten
- A4: `attempts` p95 steigt > 2 bei stabilem Traffic

## Alert-Kalibrierung (profile-basiert)
- Verfügbare Startprofile sind in `monitoring/RECOVERY_ALERT_PROFILES.md` dokumentiert:
	- `conservative`
	- `balanced`
	- `aggressive`
- Empfehlung:
	1. Start mit `conservative`
	2. Nach stabiler Baseline auf `balanced`
	3. `aggressive` nur bei dauerhaft geringer Alert-Noise

## Hinweise
- Start mit konservativen Schwellen; nach 1-2 Wochen produktivem Traffic feinjustieren.
- Alerts immer mit `final_reason` + `branch_counts` korrelieren, um False Positives zu reduzieren.
- Jede Schwellenanpassung mit Datum, Profilwahl und Beobachtungsfenster (mind. 48h) protokollieren.
