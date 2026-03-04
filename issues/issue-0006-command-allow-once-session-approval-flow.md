# Command Allowlist Runtime Approval (Once/Session) für blockierte `run_command`-Aufrufe

## Meta
- ID: issue-0006
- Status: open
- Priorität: critical
- Owner: unassigned
- Erstellt: 2026-03-04
- Zuletzt aktualisiert: 2026-03-04

## Kontext
Aktuell schlägt ein geplanter Tool-Call wie `run_command` bei Policy-Block (z. B. `ng`, `code`) fehl, und der Lauf endet mit Fehler-/Replan-Signalen ohne nutzerseitigen, kontrollierten Freigabe-Mechanismus im laufenden Chat.

Beispiel:
- `Error: Tool error (run_command): Command 'ng' is not allowed by command allowlist. Set COMMAND_ALLOWLIST_EXTRA to permit it in development.`

Ziel ist ein **sicherer Human-Approval-Flow** direkt neben der Fehlermeldung:
1. Primäraktion: **Allow** (nur diesen einen blockierten Command, genau einmal)
2. Dropdown-Aktion: **Cancel** (Command-Ausführung abbrechen, Run sauber terminieren)
3. Dropdown-Aktion: **Allow all in this Session** (alle Commands in dieser Session erlauben)

Dabei darf **keine versteckte Chain-of-Thought** exponiert werden; nur Observable Events/Entscheidungen wie bisher.

## Scope
- Frontend: Agent Control & Monitoring + Chat-UI Event-Rendering für interaktive Policy-Entscheidung.
- Backend: Laufzeit-Policy-Override für einzelne Requests/Session mit auditierbaren Lifecycle-Events.
- Nicht im Scope: persistente globale Whitelist-Änderung über Session-Ende hinaus.

## UX-Spezifikation
Bei Event/Fehler `tool_blocked` für `run_command`:
- Zeige im Chat direkt beim Fehler eine Action-Gruppe:
  - Button: `Allow`
  - Dropdown-Menü:
    - `Cancel`
    - `Allow all in this Session`

Interaktionen:
- **Allow**
  - erzeugt eine explizite Approval-Aktion für genau den blockierten Command (inkl. normalisierter Command-Signatur)
  - setzt nur einen **single-use token**
  - Agent fährt denselben Run fort und führt den blockierten Schritt **genau einmal** aus
  - derselbe Command ist danach ohne erneute Freigabe wieder blockiert
- **Cancel**
  - stoppt den wartenden Tool-Schritt
  - Run endet mit sauberem Abschlussstatus (kein Hanging, keine Endlosschleife)
  - UI zeigt klar „abgebrochen durch Benutzer“
- **Allow all in this Session**
  - setzt Session-Override für Command-Allowlist-Prüfung
  - gilt für alle folgenden passenden `run_command`-Versuche in derselben Session
  - wird bei Session-Ende/Reset sicher verworfen

## Technische Anforderungen (bulletproof / rock solid)
1. Deterministischer State-Machine-Flow
   - Neue explizite Zustände: `awaiting_user_policy_decision`, `policy_decision_received`, `policy_decision_applied`.
   - Keine stillen impliziten Replan-Loops nach Block ohne User-Entscheidung.

2. Eindeutige Korrelation
   - Jede Policy-Entscheidung trägt `requestId`, `sessionId`, `toolCallId`, `decisionId`.
   - Entscheidungen dürfen nur auf den aktuell wartenden blockierten Tool-Call angewandt werden.

3. Idempotenz & Race-Safety
   - Doppelklick/Retry auf UI-Aktion darf nicht zu Doppel-Ausführung führen.
   - Nur erste valide Entscheidung gewinnt; spätere Duplikate werden als `decision_ignored_duplicate` geloggt.

4. Single-Use-Härtung für `Allow`
   - Token ist an Command-Signatur + Tool-Call gebunden.
   - Gültigkeit endet nach erstem erfolgreichen Match oder Run-Termination.

5. Session-Override-Härtung
   - `Allow all in this Session` ist strikt an `sessionId` gebunden.
   - Keine Vererbung auf andere Sessions, Agenten oder Prozess-Neustarts.

6. Clean Abort bei `Cancel`
   - Einheitlicher terminaler Lifecycle-Stage (z. B. `request_cancelled_by_user`) mit `request_completed`-Semantik.
   - Ressourcenfreigabe garantiert (Lane, Wait-States, Terminal-Waits).

7. Auditierbarkeit
   - Neue Lifecycle-/Audit-Events:
     - `policy_approval_requested`
     - `policy_approval_decision`
     - `policy_override_applied_once`
     - `policy_override_applied_session`
     - `policy_approval_cancelled`
   - Run Audit Snapshot muss Entscheidungen inkl. Timestamp und Actor (`user`) enthalten.

8. Security
   - Default bleibt deny.
   - Kein stilles Auto-Allow nach Replan.
   - Keine Erweiterung von `COMMAND_ALLOWLIST_EXTRA` durch UI-Entscheidung.

## API-/Event-Vertrag (Vorschlag)
Request vom Frontend an Backend (WS):
- `type: "policy_decision"`
- `requestId`, `sessionId`, `toolCallId`, `decisionId`
- `decision`: `allow_once | allow_session | cancel`
- optional: `command_signature`

Backend-Lifecycle-Events:
- Ausgabe eines wartbaren Zustands bei Block (`policy_approval_requested`)
- Fortsetzung/Abbruch ausschließlich nach validierter `policy_decision`

## Akzeptanzkriterien
- [ ] Bei blockiertem `run_command` erscheint im Chat sofort `Allow` + Dropdown mit `Cancel` und `Allow all in this Session`.
- [ ] `Allow` erlaubt den geblockten Command genau einmal; zweiter identischer Versuch ohne neue Freigabe wird wieder geblockt.
- [ ] `Cancel` beendet den Run sauber ohne Zombie-States, ohne unendliche Replan-Schleife.
- [ ] `Allow all in this Session` erlaubt nachfolgende Commands in derselben Session; neue Session startet wieder deny-by-default.
- [ ] Doppelte/verspätete Klicks sind idempotent und erzeugen keine Mehrfachausführung.
- [ ] Audit/Lifecycle zeigt alle Entscheidungsereignisse vollständig und korreliert.
- [ ] Existing E2E-Tests bleiben grün; neue Tests decken neue Flows vollständig ab.

## Testplan (mindestens)
1. E2E: blockierter Command -> `allow_once` -> exakt eine Ausführung -> erneuter Block.
2. E2E: blockierter Command -> `cancel` -> sauberer terminaler Status + keine Hänger.
3. E2E: blockierter Command -> `allow_session` -> mehrere verschiedene Commands erlaubt in Session.
4. E2E: Session-Neustart -> vorherige `allow_session` wirkungslos.
5. Concurrency: doppelte `policy_decision`-Nachrichten -> genau eine wirksam.
6. Recovery: WS reconnect während `awaiting_user_policy_decision` -> Zustand korrekt wiederhergestellt.
7. Security: keine Mutation globaler Allowlist durch UI-Flow.

## Umsetzungsskizze
1. Backend
   - Policy-Decision-Contract im WS-Handler ergänzen.
   - Runtime/Orchestrator um wartenden Approval-State erweitern.
   - Override-Speicher (`once-token`, `session-override`) mit TTL/Run-Lifecycle koppeln.
   - Lifecycle-Events und Audit-Snapshot erweitern.

2. Frontend
   - Rendering für `policy_approval_requested` in Chat-Event-Karte.
   - Action-Button + Dropdown hinzufügen.
   - Action-Dispatch mit Korrelation-IDs, Disabled-State nach Klick, Retry-safe.

3. Verifikation
   - Neue Backend-E2E-Tests + ggf. Frontend-Komponententests.
   - Regression auf bestehende `tool_selection_empty`/Replan-Tests.

## Risiken
- Race Conditions zwischen Replan-Loop und User-Entscheidung.
- Unklare Status-Semantik zwischen `cancelled` und `completed`.
- UI zeigt veraltete Action-Controls nach Run-Termination.

## Notizen
- Diese Funktion ist sicherheitsrelevant. Merge nur mit grünem E2E-Set und explizitem Review auf Policy-Invarianten.
- Empfehlung: Feature-Flag `interactive_policy_approval` für kontrollierten Rollout.
