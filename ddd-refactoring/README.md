# DDD Refactoring — Master-Index

> **Projekt:** AI Agent Starter Kit — DDD-Migration
> **Basis:** `DDD_STRUCTURE_PLAN.md`
> **Ziel:** `backend/app/` von ~70-Datei-Monolith-Service-Layer → saubere Domain-Driven Design Architektur
> **Gesamt-Phasen:** 25 (PHASE_00 bis PHASE_24)

---

## Dependency-Graph (Reihenfolge einhalten!)

```
PHASE_00 (Preflight)
     │
     ├─→ PHASE_01 (shared/ + contracts/)    ← Fundament — ZUERST
     │       │
     │       └─→ PHASE_02 (config/)
     │               │
     │               ├─→ PHASE_03 (policy/)
     │               ├─→ PHASE_04 (state/)
     │               └─→ PHASE_05 (llm/)
     │                       │
     │                       ├─→ PHASE_06 (mcp/media/sandbox/browser/monitoring/)
     │                       ├─→ PHASE_07 (memory/ + session/)
     │                       └─→ PHASE_08 (reasoning/ + quality/)
     │                               │
     │                               └─→ PHASE_09 (tools/ core)
     │                                       │
     │                                       ├─→ PHASE_10 (tools/ discovery + provisioning)
     │                                       └─→ PHASE_11 (tools/ implementations)
     │                                               │
     │                                               └─→ PHASE_12 (agent/)
     │                                                       │
     │                                                       └─→ PHASE_13 (orchestration/)
     │                                                               │
     │                                                               ├─→ PHASE_14 (transport/ bootstrap)
     │                                                               │       │
     │                                                               │       └─→ PHASE_15 (transport/routers/)
     │                                                               │               │
     │                                                               │               └─→ PHASE_16 (main.py slim)
     │                                                               │
     │                                                               ├─→ PHASE_17 (backend root cleanup)
     │                                                               ├─→ PHASE_18 (multi_agency/)
     │                                                               ├─→ PHASE_19 (workflows/ + skills/)
     │                                                               └─→ PHASE_20 (connectors/)
     │
     └─→ PHASE_21 (alte Dirs löschen)  ← Alle vorherigen Phasen müssen fertig sein!
             │
             └─→ PHASE_22 (Import-Verifikation)
                     │
                     └─→ PHASE_23 (Tests aktualisieren)
                             │
                             └─→ PHASE_24 (E2E Verifikation)  ← FINAL
```

---

## Phasen-Tabelle

| # | Datei | Domain/Aufgabe | Abhängigkeit | Komplexität |
|---|---|---|---|---|
| 00 | [PHASE_00_PREFLIGHT.md](./PHASE_00_PREFLIGHT.md) | Pre-Flight Assessment + Skeleton | keine | 🟢 Leicht |
| 01 | [PHASE_01_SHARED_CONTRACTS.md](./PHASE_01_SHARED_CONTRACTS.md) | `shared/` + `contracts/` Fundament | 00 | 🟡 Mittel |
| 02 | [PHASE_02_CONFIG.md](./PHASE_02_CONFIG.md) | `config/` Domain | 01 | 🟢 Leicht |
| 03 | [PHASE_03_POLICY.md](./PHASE_03_POLICY.md) | `policy/` Domain | 02 | 🟡 Mittel |
| 04 | [PHASE_04_STATE.md](./PHASE_04_STATE.md) | `state/` Domain | 02 | 🟡 Mittel |
| 05 | [PHASE_05_LLM.md](./PHASE_05_LLM.md) | `llm/` + `llm/routing/` | 02 | 🟡 Mittel |
| 06 | [PHASE_06_INFRASTRUCTURE.md](./PHASE_06_INFRASTRUCTURE.md) | `mcp/`, `media/`, `sandbox/`, `browser/`, `monitoring/` | 05 | 🟡 Mittel |
| 07 | [PHASE_07_MEMORY_SESSION.md](./PHASE_07_MEMORY_SESSION.md) | `memory/` + `session/` | 05 | 🟡 Mittel |
| 08 | [PHASE_08_REASONING_QUALITY.md](./PHASE_08_REASONING_QUALITY.md) | `reasoning/` + `quality/` | 07 | 🟡 Mittel |
| 09 | [PHASE_09_TOOLS_CORE.md](./PHASE_09_TOOLS_CORE.md) | `tools/` Kern + `registry/` + `execution/` | 08 | 🔴 Schwer |
| 10 | [PHASE_10_TOOLS_DISCOVERY_PROVISIONING.md](./PHASE_10_TOOLS_DISCOVERY_PROVISIONING.md) | `tools/discovery/` + `tools/provisioning/` | 09 | 🟡 Mittel |
| 11 | [PHASE_11_TOOLS_IMPLEMENTATIONS.md](./PHASE_11_TOOLS_IMPLEMENTATIONS.md) | `tools.py` → `tools/implementations/` (7 Dateien) | 09 | 🔴 Schwer |
| 12 | [PHASE_12_AGENT.md](./PHASE_12_AGENT.md) | `agent/` (HeadAgent + Runner Monolith-Split) | 11 | 🔴 Schwer |
| 13 | [PHASE_13_ORCHESTRATION.md](./PHASE_13_ORCHESTRATION.md) | `orchestration/` + `contracts/` Finalisierung | 12 | 🔴 Schwer |
| 14 | [PHASE_14_TRANSPORT_BOOTSTRAP.md](./PHASE_14_TRANSPORT_BOOTSTRAP.md) | `transport/` Bootstrap + WebSocket | 13 | 🔴 Schwer |
| 15 | [PHASE_15_TRANSPORT_ROUTERS.md](./PHASE_15_TRANSPORT_ROUTERS.md) | `transport/routers/` (17 Router + 12 Handler) | 14 | 🔴 Schwer |
| 16 | [PHASE_16_MAIN_SLIMDOWN.md](./PHASE_16_MAIN_SLIMDOWN.md) | `main.py` → ~50 Zeilen | 15 | 🟢 Leicht |
| 17 | [PHASE_17_BACKEND_ROOT_CLEANUP.md](./PHASE_17_BACKEND_ROOT_CLEANUP.md) | Backend-Root: `data/` Struktur | 16 | 🟢 Leicht |
| 18 | [PHASE_18_MULTI_AGENCY.md](./PHASE_18_MULTI_AGENCY.md) | `multi_agency/` Import-Bereinigung | 13 | 🟡 Mittel |
| 19 | [PHASE_19_WORKFLOWS_SKILLS.md](./PHASE_19_WORKFLOWS_SKILLS.md) | `workflows/` + `skills/` | 13 | 🟡 Mittel |
| 20 | [PHASE_20_CONNECTORS.md](./PHASE_20_CONNECTORS.md) | `connectors/` + Sicherheits-Audit | 03 | 🟡 Mittel |
| 21 | [PHASE_21_OLD_DIRS_REMOVAL.md](./PHASE_21_OLD_DIRS_REMOVAL.md) | Alte Verzeichnisse löschen | 16–20 alle | 🟡 Mittel |
| 22 | [PHASE_22_IMPORT_VERIFICATION.md](./PHASE_22_IMPORT_VERIFICATION.md) | Ruff + mypy Cleanup | 21 | 🟡 Mittel |
| 23 | [PHASE_23_TESTS_UPDATE.md](./PHASE_23_TESTS_UPDATE.md) | Test-Suite aktualisieren | 22 | 🔴 Schwer |
| 24 | [PHASE_24_E2E_VERIFICATION.md](./PHASE_24_E2E_VERIFICATION.md) | E2E Verifikation + ARCHITECTURE.md | 23 | 🟡 Mittel |

**Gesamtaufwand:** ~40–60 Stunden (über ~25 Sessions)

---

## Kritischer Pfad (Blocking-Sequenz)

Diese Phasen müssen strikt in Reihenfolge abgearbeitet werden:

```
00 → 01 → 02 → 05 → 07 → 08 → 09 → 11 → 12 → 13 → 14 → 15 → 16 → 21 → 22 → 23 → 24
```

Diese können parallel (nach ihren Voraussetzungen) laufen:
- PHASE_03 und PHASE_04: können nach PHASE_02 parallel starten
- PHASE_06: kann nach PHASE_05 gestartet werden
- PHASE_10: kann parallel zu PHASE_11 (nach PHASE_09)
- PHASE_17, PHASE_18, PHASE_19, PHASE_20: können alle nach PHASE_16 parallel laufen

---

## Quell-Dateien (Monolithen)

| Datei | Zeilen | Ziel |
|---|---|---|
| `app/agent.py` | 1769 | `app/agent/head_agent.py` (Phase 12) |
| `app/agent_runner.py` | 1667 | `app/agent/runner.py` (Phase 12) |
| `app/ws_handler.py` | 1658 | `app/transport/ws_handler.py` (Phase 14) |
| `app/tools.py` | 1209 | `app/tools/implementations/` 7 Dateien (Phase 11) |
| `app/main.py` | 1144 | `app/main.py` ~50 Zeilen (Phase 16) |
| `app/services/` | ~70 Dateien | Verteilt auf DDD-Domains (Phase 03–15) |
| `app/routers/` | 17 Dateien | `app/transport/routers/` (Phase 15) |
| `app/handlers/` | 12 Dateien | `app/transport/routers/` (Phase 15) |

---

## Status-Tracking

Kopiere diese Tabelle in dein Notizprogramm um den Fortschritt zu verfolgen:

```
[ ] PHASE_00 — Preflight
[ ] PHASE_01 — shared/ + contracts/
[ ] PHASE_02 — config/
[ ] PHASE_03 — policy/
[ ] PHASE_04 — state/
[ ] PHASE_05 — llm/
[ ] PHASE_06 — Infrastructure (mcp/media/sandbox/browser/monitoring/)
[ ] PHASE_07 — memory/ + session/
[ ] PHASE_08 — reasoning/ + quality/
[ ] PHASE_09 — tools/ core
[ ] PHASE_10 — tools/ discovery + provisioning
[ ] PHASE_11 — tools/ implementations (monolith split)
[ ] PHASE_12 — agent/ (monolith split)
[ ] PHASE_13 — orchestration/
[ ] PHASE_14 — transport/ bootstrap
[ ] PHASE_15 — transport/routers/
[ ] PHASE_16 — main.py slim-down
[ ] PHASE_17 — backend root cleanup
[ ] PHASE_18 — multi_agency/
[ ] PHASE_19 — workflows/ + skills/
[ ] PHASE_20 — connectors/
[ ] PHASE_21 — old dirs removal
[ ] PHASE_22 — import verification
[ ] PHASE_23 — tests update
[ ] PHASE_24 — E2E verification
```

---

## Wichtige Prinzipien

1. **Eine Phase = Eine Git-Session** — Nach jeder Phase committen
2. **Niemals rückwärts** — Phasen nicht überspringen oder umkehren
3. **Tests vor dem Löschen** — Immer `from app.main import app` prüfen bevor alte Dirs gelöscht werden
4. **Incremental** — App muss nach JEDER Phase startbar bleiben
5. **Backup-First** — Vor dem Löschen immer `.phase_XX_backup` erstellen

---

> **Plan-Basis:** [DDD_STRUCTURE_PLAN.md](../DDD_STRUCTURE_PLAN.md)
> **Architektur-Dokumentation:** [ARCHITECTURE.md](../ARCHITECTURE.md)
