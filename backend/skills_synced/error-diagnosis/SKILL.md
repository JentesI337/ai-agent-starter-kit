---
name: error-diagnosis
description: Systematische Fehlerdiagnose für Laufzeitfehler mit Hypothesenbildung und Verifikation.
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# Error-Diagnose

Systematische Fehlerdiagnose für Laufzeitfehler.

## Instructions

Bei der Diagnose von Fehlern:

1. **Fehlermeldung analysieren:**
   - Exception-Typ identifizieren
   - Traceback vollständig lesen (von unten nach oben)
   - Den auslösenden Frame identifizieren (nicht den Propagations-Frame)

2. **Kontext sammeln:**
   - Relevante Datei lesen (`read_file` am Frame-Standort)
   - Abhängigkeiten der fehlerhaften Funktion prüfen
   - Konfiguration prüfen (`.env`, `config.py`)

3. **Hypothesen bilden (max. 3):**
   - Wahrscheinlichste Ursache zuerst
   - Jede Hypothese mit einer Prüfmethode

4. **Systematisch verifizieren:**
   - Eine Hypothese nach der anderen prüfen
   - Nicht raten — belegen durch Code-Lektüre oder Ausführung

5. **Fix vorschlagen:**
   - Minimaler, gezielter Fix (nicht überengineeren)
   - Erklären warum der Fix funktioniert
   - Test für den Fix vorschlagen

### Beispiel

Input: "ModuleNotFoundError: No module named 'requests'"
Diagnose:
1. Fehlender Import → `pip install requests` oder in `requirements.txt` ergänzen
2. VirtualEnv nicht aktiviert → `source .venv/bin/activate`
3. Falsche Python-Version → `python --version` prüfen
