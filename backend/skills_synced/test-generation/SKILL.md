---
name: test-generation
description: Generiert strukturierte Unit- und Integrationstests mit Arrange-Act-Assert Pattern.
requires_bins: python
os: windows,linux,darwin
user_invocable: true
disable_model_invocation: false
---

# Test-Generierung

Generiert strukturierte Unit- und Integrationstests.

## Instructions

Beim Generieren von Tests:

1. **Analysiere die Ziel-Funktion:**
   - Input-Typen und Ranges
   - Return-Typ und mögliche Werte
   - Exceptions die geworfen werden können
   - Abhängigkeiten (was muss gemockt werden?)

2. **Test-Kategorien:**
   - **Happy Path:** Normaler Aufruf mit gültigen Inputs
   - **Edge Cases:** Leere Inputs, None, Grenzwerte, Unicode
   - **Error Cases:** Ungültige Inputs, fehlende Dependencies, Timeouts
   - **Integration:** Zusammenspiel mit echten Dependencies (sofern sicher)

3. **Test-Struktur (Arrange-Act-Assert):**
   ```python
   def test_function_scenario_expected_result():
       # Arrange
       input_data = create_test_data()
       mock_dep = Mock(spec=Dependency)

       # Act
       result = function_under_test(input_data, mock_dep)

       # Assert
       assert result == expected_value
       mock_dep.method.assert_called_once_with(expected_args)
   ```

4. **Naming-Konvention:** `test_<funktion>_<szenario>_<erwartetes_ergebnis>`

5. **Coverage-Ziel:** Mindestens 80% Branch-Coverage für die Ziel-Funktion.
