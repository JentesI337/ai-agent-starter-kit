---
name: git-workflow
description: Strukturiert Git-Operationen in einen sicheren Workflow mit Conventional Commits und Branch-Strategie.
requires_bins: git
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# Git Workflow

Strukturiert Git-Operationen in einen sicheren Workflow.

## Instructions

Wenn der Benutzer eine Git-Operation anfordert, folge diesem Workflow:

1. **Status prüfen:** `git status` ausführen und analysieren
2. **Branch-Strategie:**
   - Feature: `feature/<ticket>-<beschreibung>`
   - Bugfix: `fix/<ticket>-<beschreibung>`
   - Hotfix: `hotfix/<beschreibung>`
   - Kein Push auf `main` ohne explizite Freigabe
3. **Commit-Konvention:** Conventional Commits verwenden
   - `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
4. **Sicherheitsregeln:**
   - Vor `git reset --hard` oder `git push --force` immer nachfragen
   - Vor Merge immer `git diff` zeigen
   - `.gitignore` prüfen vor erstem Commit

### Beispiel

Input: "Erstelle einen Feature-Branch für das Login-Feature"
Output:
```bash
git checkout -b feature/login-implementation
git status
```
