User: The orchestrator selects a model based on task requirements, never by hardcoded model name.

Capability Router
The orchestrator routes tasks using:

task_complexity — simple / moderate / complex
context_size — token count of required input
confidence_score — output from previous agent pass
budget_threshold — cost ceiling per task
Tier	Model Size	Handles
Small	7B–14B	Basic coding, simple planning, minor fixes
Mid	32B–70B	Combined steps, one reflection pass, dep. graphs
High	70B+ / GPT-4	Architecture design, security audits, deep refactors
📋 Refactoring Phases
Phase 1 — Foundation (Cheap Model Architecture)
Goal: Stability over intelligence.

 Define strict agent contracts for all existing agents
 Extract state management out of prompts and model calls
 Build the external state store with task graph support
 Implement context reducer with token budget enforcement
 Remove all reflection loops from current flows
 Enforce JSON-only outputs across all agents
 Write input/output validation layer per agent
Exit criteria:

All agents have explicit schemas
No agent reads from another agent's memory
State is fully external and queryable
Phase 2 — Stability Milestone
Goal: Prove the foundation holds under real workloads.

 Complete multi-step coding tasks end-to-end reliably
 Handle agent errors via structured retry logic (no silent failures)
 Summarize and rehydrate state across task interruptions
 Run all flows under strict token limits without degradation
Exit criteria:

Zero unhandled state corruption cases
Retry logic tested for all failure modes
System operates fully on cheap 7B–14B models
Phase 3 — Gradual Scaling
Goal: Introduce model tiers without changing agent logic.

 Implement the capability router in the orchestrator
 Register model capability profiles for each available model
 Add routing rules per task type and complexity score
 Enable mid-tier features (combined steps, one reflection pass)
 Enable high-tier features (multi-pass reflection, long context)
 Test that switching model tiers produces no architectural change
Exit criteria:

Orchestrator routes tasks dynamically by profile
No agent contract changes required when upgrading model tiers
High-tier model runs are an enhancement — not a rewrite
✅ Expected Outcomes
Area	Before	After
Scalability	Breaks under model/task upgrades	Upgrade is a config change
Reliability	Silent failures, state corruption	Structured retries, clean state rehydration
State Management	Mixed into prompts and model memory	Fully external, orchestrator-owned
Model Flexibility	Hardcoded to specific model	Model-agnostic via capability profiles
Agent Design	Monolithic, implicit dependencies	Strict contracts, no hidden assumptions
Cost Control	Unpredictable (reflection loops)	Budget-aware routing per task
🚫 What To Avoid
Don't	Do Instead
Monolithic super agents	Single-responsibility agent contracts
Long chat history as memory	External state store with summaries
Hardcoding GPT-4 behaviors	Capability profiles + routing
Reflection loops in early phases	Linear, deterministic flows first
Mixing state logic into prompts	Keep prompts clean, state in orchestrator
📁 Suggested File Structure


/orchestrator
  /agents
    planner.py
    coder.py
    reviewer.py
  /state
    store.py
    task_graph.py
    context_reducer.py
    snapshots.py
  /routing
    capability_router.py
    model_profiles.json
  /contracts
    schemas.py
    validators.py
  orchestrator.py
/config
  models.json
  routing_rules.json

GitHub Copilot: 

  

Created 13 todos

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/agent.py#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/models.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/config.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/llm_client.py#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/tools.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/memory.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/errors.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/runtime_manager.py#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/agent.py#100-100) Zeilen 100 bis 300 lesen

Gutes Grundverständnis der Codebasis. Jetzt implementiere ich das gesamte Orchestrator-System. 

Starting: *Create orchestrator directory structure* (2/13)

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/__init__.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/contracts/__init__.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/__init__.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/routing/__init__.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/agents/__init__.py) wurde erstellt

Starting: *Implement agent contracts & schemas* (3/13)

Jetzt implementiere ich die Kernkomponenten. Ich starte mit den Contracts/Schemas, dann State, Routing und schließlich den Orchestrator selbst. 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/contracts/schemas.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/contracts/validators.py) wurde erstellt

Starting: *Implement external state store* (4/13)

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/store.py) wurde erstellt

Starting: *Implement task graph* (5/13)

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/task_graph.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/context_reducer.py) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/snapshots.py) wurde erstellt

Starting: *Implement model profiles & config* (8/13)

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/config/models.json) wurde erstellt

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/config/routing_rules.json) wurde erstellt

Starting: *Implement capability router* (9/13)

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/routing/capability_router.py) wurde erstellt

Starting: *Implement orchestrator core* (10/13)

Jetzt die Agent-Implementierungen und den Orchestrator-Core: 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/agents/planner.py) wurde erstellt

 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/agents/coder.py) wurde erstellt

 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/agents/reviewer.py) wurde erstellt

Completed: *Implement agent implementations* (11/13)

Jetzt der Orchestrator-Core — das Herzstück, das alles verbindet: 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/orchestrator.py) wurde erstellt

Starting: *Integrate with existing backend* (12/13)

Jetzt integriere ich den Orchestrator in die bestehende main.py: 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py#30-30) Zeilen 30 bis 200 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py#200-200) Zeilen 200 bis 512 lesen

Jetzt integriere ich den Orchestrator in die main.py. Ich füge neue API-Endpunkte hinzu, ohne die bestehende Funktionalität zu ändern: 

5 Zeilen durch 7 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py) ersetzen


```

```


2 Zeilen durch 16 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py) ersetzen


```

```
Now add the orchestrator API endpoints before the WebSocket handler:  

13 Zeilen durch 79 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/main.py) ersetzen


```

```


Starting: *Validate with tests* (13/13)

Nun erstelle ich die Tests:   

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/tests/test_orchestrator.py) wurde erstellt

Jetzt führe ich die Tests aus:   

Ran terminal command: Set-Location "C:\Users\wisni\code\git\ai-agent-starter-kit\backend"; .\.venv\Scripts\python -m pytest tests/test_orchestrator.py -v 2>&1 | Select-Object -Last 80
Completed with input: Set-Location "C:\Users\wisni\code\git\ai-agent-starter-kit\backend"; .\.venv\Scripts\python -m pytest tests/test_orchestrator.py -v 2>&1 | Select-Object -Last 80

3 Tests fehlgeschlagen. Ich korrigiere die Logik im Context Reducer (Truncation-Schwelle) und den Budget-Constraint im Router:  

15 Zeilen durch 37 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/state/context_reducer.py), [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/orchestrator/routing/capability_router.py) ersetzen


```

```

```

```
Jetzt korrigiere ich die Tests — der "budget_drops_low_priority" Test muss mit einem kleineren Content arbeiten, damit bei Budget 100 tatsächlich etwas gedroppt wird (200 chars = 50 tokens, 2×50 = 100 = genau Budget). Ich erhöhe die Content-Größe:   

9 Zeilen durch 9 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/tests/test_orchestrator.py) ersetzen


```

```


Ran terminal command: .\.venv\Scripts\python -m pytest tests/test_orchestrator.py -v 2>&1 | Select-Object -Last 60

**59 Tests bestanden, 0 fehlgeschlagen.** Jetzt noch sicherstellen, dass die bestehenden Tests weiterhin funktionieren:  

Ran terminal command: .\.venv\Scripts\python -m pytest tests/ -v --ignore=tests/test_backend_e2e.py 2>&1 | Select-Object -Last 20

Completed: *Validate with tests* (13/13)

**Alle 75 Tests bestanden** (59 Orchestrator + 16 bestehende).

Hier ist die Zusammenfassung des implementierten Systems:

---

### Implementierte Struktur

```
backend/
  app/orchestrator/
    orchestrator.py          ← Orchestrator-Core
    contracts/
      schemas.py             ← Agent Contracts, Schemas, Enums
      validators.py          ← Input/Output-Validierung pro Agent
    state/
      store.py               ← Externer State Store (thread-safe, JSON-Persistenz)
      task_graph.py           ← DAG mit Dependency-Tracking & Zykluserkennung
      context_reducer.py      ← Token-Budget-Enforcement & Prioritäts-Ranking
      snapshots.py            ← State-Checkpoints für Rehydrierung
    routing/
      capability_router.py    ← Modell-Routing nach Task-Anforderungen
    agents/
      planner.py              ← Planner Agent (Zerlegung in Schritte)
      coder.py                ← Coder Agent (Implementierung pro Schritt)
      reviewer.py             ← Reviewer Agent (Review mit Confidence-Score)
  config/
    models.json               ← 9 Modell-Profile (Small/Mid/High)
    routing_rules.json        ← Routing-Regeln nach Komplexität/Budget
  tests/
    test_orchestrator.py      ← 59 Tests
```

### Kernprinzipien umgesetzt

| Anforderung | Status |
|---|---|
| Modellauswahl nach Task-Anforderungen, nie hardcoded | Capability Router mit Tier-Routing |
| State extern, orchestrator-owned | `StateStore` + `TaskGraph` |
| Strict Agent Contracts | `AgentContract` mit validiertem Input/Output |
| JSON-only Outputs | Alle Agents geben strukturiertes JSON zurück |
| Context Reducer mit Token-Budget | Prioritäts-basierte Reduktion |
| Structured Retry Logic | Pro-Task Retries mit max_retries |
| Snapshot/Rehydrierung | `SnapshotManager` mit Checkpoint-Text |
| Budget-aware Routing | Downgrade auf günstigere Tiers bei Budget-Limits |
| Bestehende Funktionalität erhalten | Neue `/api/orchestrator/*` Endpunkte, WebSocket unverändert |

Made changes.

User: can you now change my frontend to match the backend? Only the mvp needs to be there so the refactoring carryes over to the frontend



GitHub Copilot: 

  

Created 4 todos

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services/agents.service.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services/agent-socket.service.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/app.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/app.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/app.routes.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts#1-1) Zeilen 1 bis 200 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts#200-200) Zeilen 200 bis 354 lesen

Now let me also check the styling files and the app config:      

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/app.config.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/app.scss) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.scss#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.scss) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.scss) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.scss) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.scss#100-100) Zeilen 100 bis 191 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/styles.scss) lesen

Starting: *Update services for orchestrator API* (2/4)

Guter Überblick. Ich werde das Frontend als MVP aktualisieren, damit es die neuen Orchestrator-Endpunkte widerspiegelt: Orchestrator-Service, aktualisierte Agents-Seite mit Contracts, Settings-Seite mit Model-Profiles/Routing und Chat-/Tests-Seite mit Orchestrator-Support. 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services/orchestrator.service.ts) wurde erstellt

Starting: *Update UI components* (3/4)

Now I'll update the Agents page to show orchestrator agents with their contracts, the Settings page to display model profiles, the Tests page to include orchestrator tests, and the Chat page to support orchestrator mode.      

32 Zeilen durch 104 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.ts) ersetzen


```

```


15 Zeilen durch 70 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.html) ersetzen


```

```


12 Zeilen durch 132 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/agents-page.component.scss) ersetzen


```

```
Now update the Settings page to show model routing info and orchestrator state:        

32 Zeilen durch 70 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.ts) ersetzen


```

```
Summarized conversation history

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.html) lesen

19 Zeilen durch 59 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.html) ersetzen


```

```


[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.scss) lesen

45 Zeilen durch 102 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.scss) ersetzen


```

```
Now update the Tests page:   

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.ts) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.scss) lesen

Starting: *Update tests page* (4/6)

47 Zeilen durch 97 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.ts), [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.html) ersetzen


```

```

```

```


8 Zeilen durch 25 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.scss) ersetzen


```

```


Starting: *Update chat page* (5/6)

Now the most complex part — the chat page. Let me read the current state:  

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.html) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts#100-100) Zeilen 100 bis 354 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.scss) lesen

Now I'll update the chat page to add an orchestrator mode toggle alongside the existing WebSocket chat: 

17 Zeilen durch 21 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts) ersetzen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts#1-1) Zeilen 1 bis 20 lesen

20 Zeilen durch 23 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts) ersetzen


```

```
Now add orchestrator fields and inject the service: 

23 Zeilen durch 27 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts) ersetzen


```

```
Now add the orchestrator send logic after the existing `send()` method:  

2 Zeilen durch 7 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts) ersetzen


```

```
Now add the `sendOrchestrator()` method. Let me find a good insertion point — right before `switchRuntime()`: 

1 Zeilen durch 57 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts) ersetzen


```

```
Now update the chat page template with the mode toggle and orchestrator-specific UI: 

62 Zeilen durch 80 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.html) ersetzen


```

```
Now add the mode toggle and orchestrator styling to the SCSS: 

2 Zeilen durch 33 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.scss) ersetzen


```

```


Starting: *Validate frontend build* (6/6)

Now let me validate the build: 

Ran terminal command: cd c:\Users\wisni\code\git\ai-agent-starter-kit\frontend; npx ng build 2>&1
Completed with input: cd c:\Users\wisni\code\git\ai-agent-starter-kit\frontend; npx ng build 2>&1

[](file:///c%3A/Users/wisni/AppData/Roaming/Code/User/workspaceStorage/0a68a4ace35d3c09a83eb0b0437cfef5/GitHub.copilot-chat/chat-session-resources/c01bfee8-fadd-4008-9fa1-1743d30ea3ea/toolu_vrtx_0112v8268cyiQAzcokBd163b__vscode-1772280527579/content.txt#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/AppData/Roaming/Code/User/workspaceStorage/0a68a4ace35d3c09a83eb0b0437cfef5/GitHub.copilot-chat/chat-session-resources/c01bfee8-fadd-4008-9fa1-1743d30ea3ea/toolu_vrtx_0112v8268cyiQAzcokBd163b__vscode-1772280527579/content.txt#100-100) Zeilen 100 bis 212 lesen

The type definitions in `orchestrator.service.ts` don't match what I'm using. Let me check the actual types: 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services/orchestrator.service.ts#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/services/orchestrator.service.ts#100-100) Zeilen 100 bis 128 lesen

Now I see the actual types. The issues are:
1. `OrchestratorRunResult` has `results` (not `coder`), `graph_summary` (not `graph`)
2. `ReviewerOutput` has `issues`, `confidence_score`, `reasoning` (not `comments`, `confidence`)
3. `OrchestratorStateResponse.store` has `total_tasks`, `by_status` (not `total_entries`, `active_tasks`, `status_counts`)
4. `GraphSummary` has `total`, `by_status`, `ready`, `blocked`, `is_complete` (not `total_nodes`, `completed_nodes`, etc.)

Let me fix all these mismatches: 

50 Zeilen durch 65 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/chat-page.component.ts), [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/settings-page.component.html), [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/frontend/src/app/pages/tests-page.component.html) ersetzen


```

```

```

```

```

```


Ran terminal command: npx ng build 2>&1

Build successful — zero errors. 

Completed: *Validate frontend build* (6/6)

Frontend-Refactoring abgeschlossen. Build ist fehlerfrei. Hier eine Zusammenfassung der Änderungen:

**Neuer Service:**
- orchestrator.service.ts — Typdefinitionen + API-Aufrufe für `/api/orchestrator/run`, `/models`, `/state`

**Chat-Seite** (chat-page.component.ts, .html, .scss):
- **Legacy/Orchestrator-Toggle** im Header — wechselt zwischen WebSocket-Modus und HTTP-Orchestrator
- Orchestrator-Modus sendet an `POST /api/orchestrator/run` und zeigt Plan-Steps, Coder-Changes und Review-Ergebnis (approved/rejected + confidence + issues) im Chat-Verlauf
- Legacy-Controls (Runtime, Agent, Model) werden nur im Legacy-Modus angezeigt

**Agents-Seite** (aus vorheriger Session):
- Orchestrator-Agents (Planner/Coder/Reviewer) mit Contracts und Constraints
- Model Capability Profiles Tabelle (Tier, Context, Reasoning, Cost)
- Legacy-Agents bleiben erhalten

**Settings-Seite** (settings-page.component.ts, .html):
- State Store Übersicht (Tasks, Status-Verteilung, Timestamp)
- Task Graph Status (Total, Ready/Blocked Tasks, Completion)
- Refresh-Button für Live-Updates

**Tests-Seite** (tests-page.component.ts, .html):
- Dritte Test-Karte „Orchestrator" — führt die vollständige Plan→Code→Review-Pipeline aus und zeigt alle Ergebnisse als JSON

Made changes.

User: bisher wurde aktuell zum entwickeln die minimax-m2:cloud api aufgerufen weil diese über das ollama pro abo buchbar ist

ergänze die startups für windows und linux um beim startup zu entscheiden, ob mein ein lokales llama benutzen möchte, oder die api mit ollama login und pro plan 

WICHTIG: startup arbeitet nicht mit api keys

GitHub Copilot: 

    

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#1-1) Zeilen 1 bis 100 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-test.ps1) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-test.sh) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#100-100) Zeilen 100 bis 250 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#250-250) Zeilen 250 bis 502 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/test-dev.ps1) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/test-dev.sh) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/clean-dev.ps1#1-1) Zeilen 1 bis 60 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/clean-dev.sh#1-1) Zeilen 1 bis 60 lesen

Now let me check how the backend reads runtime config to understand the full picture:  

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/config.py) lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/app/runtime_manager.py#1-1) Zeilen 1 bis 80 lesen

Nach Text `\.env\.example` (`**/backend/**`) gesucht, 12 Ergebnisse

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/backend/.env.example) lesen

Created 3 todos

Beide Startup-Skripte haben bereits die Grundstruktur für local/api-Wahl. Ich verbessere jetzt:
1. Klarere Menüführung mit Beschreibungen (kein API-Key, nur `ollama signin`)
2. Lokale Modellauswahl (mehrere Größen)
3. Login-Status-Anzeige vor API-Modus
4. Bessere Fehlermeldungen

Zuerst die Änderungen an start-dev.ps1: 

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1#20-20) Zeilen 20 bis 50 lesen

Now let me read the execution section at the bottom of the PS1 to see exact line numbers:  

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1#395-395) Zeilen 395 bis 480 lesen

Now I have the full picture. Let me also read the `Ensure-CloudLogin` function and lines around it to get exact context for edits:   

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1#195-195) Zeilen 195 bis 240 lesen

Now I'll apply the improvements. The key changes are:

1. **`Resolve-RuntimeMode`** → descriptive menu with model sizes, no-API-key hint
2. **New `Resolve-LocalModel`** function → choose between small/mid/large local models
3. **Login status display** → show `ollama whoami` result before API mode proceeds
4. **Execution section** → integrate local model selection, clear messaging    

14 Zeilen durch 46 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1) ersetzen


```

```
Now improve `Ensure-CloudLogin` to show login status clearly:   

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1#175-175) Zeilen 175 bis 215 lesen

9 Zeilen durch 9 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1) ersetzen


```

```
Now update the execution section to use local model selection and better messaging:    

34 Zeilen durch 39 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.ps1) ersetzen


```

```


Starting: *Verbessern start-dev.sh* (2/3)

Jetzt das Linux-Skript mit denselben Verbesserungen:    

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#28-28) Zeilen 28 bis 45 lesen

16 Zeilen durch 51 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh) ersetzen


```

```
Now update the `ensure_cloud_login` header in the bash script:     

1 Zeilen durch 1 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh) ersetzen


```

```
Now update the execution section of the bash script:     

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#450-450) Zeilen 450 bis 502 lesen

[](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh#500-500) Zeilen 500 bis 537 lesen

36 Zeilen durch 35 Zeilen in [](file:///c%3A/Users/wisni/code/git/ai-agent-starter-kit/start-dev.sh) ersetzen


```

```


Starting: *Konsistenz prüfen* (3/3)

Jetzt verifizieren, dass beide Skripte konsistent sind:  

Ran terminal command: cd c:\Users\wisni\code\git\ai-agent-starter-kit; Select-String -Path start-dev.ps1 -Pattern "minimax|API_MODEL|LOCAL_MODEL|ollama signin|api.key|api_key" | Format-Table -Property LineNumber,Line -AutoSize

Ran terminal command: Select-String -Path start-dev.sh -Pattern "minimax|API_MODEL|LOCAL_MODEL|ollama signin|api.key|api_key" | Format-Table -Property LineNumber,Line -AutoSize

Beide Skripte sind konsistent. Lassen wir noch schnell die Syntax des PS1-Skripts prüfen:   

Ran terminal command: [System.Management.Automation.PSParser]::Tokenize((Get-Content -Path .\start-dev.ps1 -Raw), [ref]$null) | Out-Null; if ($?) { "PS1 syntax OK" } else { "PS1 syntax ERROR" }

Ran terminal command: bash -n start-dev.sh 2>&1; if ($LASTEXITCODE -eq 0) { "SH syntax OK" } else { "SH syntax ERROR" }

Kein WSL verfügbar — die bash-Syntax-Prüfung kann nicht lokal laufen, aber die Änderungen folgen exakt den bestehenden Patterns im Skript. 

Completed: *Konsistenz prüfen* (3/3)

Beide Startup-Skripte sind aktualisiert. Hier die Zusammenfassung:

**Änderungen in start-dev.ps1 und start-dev.sh:**

1. **Verbesserte Runtime-Auswahl** (`Resolve-RuntimeMode` / `resolve_runtime_mode`):
   - Klare Beschreibung beider Modi mit Boxen-Layout
   - LOCAL: erklärt GPU-VRAM-Bedarf, kein Internet nach Pull
   - API: erklärt Ollama Pro Plan + `ollama signin`
   - Expliziter Hinweis: **"No API keys needed"**

2. **Neue lokale Modellauswahl** (`Resolve-LocalModel` / `resolve_local_model`):
   - 4 Optionen mit VRAM-Angaben:
     - `llama3.2:3b` (~2 GB, small)
     - `llama3.1:8b` (~5 GB, balanced)
     - `qwen2.5-coder:32b` (~18 GB, strong coder)
     - `llama3.3:70b-instruct-q4_K_M` (~40 GB, best quality)
   - Zeigt aktuell konfiguriertes Modell an
   - Wird in `.env` als `LOCAL_MODEL` gespeichert

3. **Cloud-Login-Text** angepasst:
   - `"Checking Ollama Pro login (no API key - uses 'ollama signin')"`
   - Statt dem generischen "Checking Ollama Cloud login"

4. **Execution-Section** vereinfacht:
   - Local: ruft `Resolve-LocalModel` auf, speichert Wahl in `.env`
   - API: setzt `minimax-m2:cloud`, zeigt `(Ollama Pro)` an
   - Keine redundante Doppel-Variable mehr

Made changes.