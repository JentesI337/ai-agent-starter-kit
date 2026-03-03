eil 1: Stochastisches Modell, deterministische Ausführung (der Kern-Pattern-Mix)
 behandelt das LLM nicht als “App”, sondern als stochastische Entscheidungs-Engine, die in einen harten, deterministischen Laufzeit-Loop eingebettet ist. Dieser Agent Loop ist “die Wahrheit”: Intake, Kontextbau, Model-Inference, Tool-Ausführung, Streaming, Abschluss. Wichtig ist: pro Session ist ein Run serialisiert (eine “Lane”), damit Tool-Races und Session-Inkonsistenzen nicht passieren. Das ist ein simples, aber extrem starkes Reliability-Pattern, weil es aus probabilistischem Denken reproduzierbare Systemzustände macht.

Dazu kommt Queueing als bewusstes Steuerungssystem: neue Nachrichten können gesammelt, als Follow-up verarbeitet oder in den laufenden Run “gesteuert” werden. In “steer” wird nach jedem Tool-Call geprüft, ob neue User-Inputs da sind; dann werden restliche geplante Tool-Calls abgebrochen und der neue Input wird in die nächste Assistant-Antwort injiziert. Das ist ein sehr starkes Pattern gegen “Agent läuft in die falsche Richtung und macht weiter Schaden”, und es verbessert Reasoning, weil der Agent nicht blind seinen alten Plan runterbetet.

Teil 2: Context Engineering statt “Prompt-Magie”
 baut jedes Mal einen eigenen System Prompt, kompakt und in festen Sektionen. Dadurch ist das Reasoning nicht vom Zufall abhängig, ob der Nutzer irgendwann mal “wie er sein soll” gesagt hat, sondern es gibt eine stabile, wiederholbare “Kernel”-Instruktion pro Run. Gleichzeitig ist der Prompt modular: für Subagents gibt es “promptMode minimal”, das bewusst Sektionen weglässt, um Kontext klein zu halten und Spezialisten nicht mit “globalem Ballast” zu vergiften. Das ist ein klassisches Pattern aus verteilten Systemen: kleine, fokussierte Worker-Prozesse statt ein monolithischer Brain-Blob.

Ganz entscheidend für starkes Reasoning ist, dass  Kontextkosten sichtbar macht. /context list und /context detail zeigen, wie viel Token in System Prompt, Workspace-Injection, Skill-Metadaten und vor allem Tool-Schemas stecken. Viele Agent-Setups scheitern, weil niemand merkt, dass “Tool JSON” massiv Kontext frisst.  macht das explizit und damit optimierbar (z.B. Tools/Skills reduzieren, Bootstrap Files kurz halten, große Tools aus dem Default rausnehmen).

Teil 3: Skills als “Lazy-Loaded Know-how” (ein sehr unterschätztes Reasoning-Pattern)
 injiziert nicht stumpf komplette Skill-Instruktionen in jeden Prompt. Stattdessen kommt nur eine kompakte Skills-Liste (Name, Description, Location) rein, und das Modell soll bei Bedarf per read das SKILL.md nachladen. Das ist ein Lazy-Loading-Pattern für Prompts: Basis-Kontext bleibt klein, aber der Agent kann sich gezielt “die Bedienungsanleitung” eines Tools holen, wenn er sie wirklich braucht. Das verbessert Reasoning praktisch doppelt: weniger Kontextdruck und weniger Halluzinationen über Tool-Details, weil “read the manual” als normaler Schritt im Loop verankert ist.

Teil 4: Tools als typed Functions + “Action-Space Shaping”
 setzt stark auf “first-class agent tools” (typed, kein Shell-Glue als Default). Tool-Definitionen sind JSON-Schema-Funktionen (auch bei Plugins), und es gibt Allow/Deny, Tool-Profile (minimal/coding/messaging/full) und provider-spezifische Tool-Policies. Das ist ein Pattern aus Control/Robotics: du machst den Aktionsraum kleiner und sauberer, damit das Policy-Netz (LLM) bessere Entscheidungen trifft. Je weniger unnötige Tools und je klarer die Schemas, desto höher die Erfolgsrate beim Tool-Use.

Zusätzlich sieht man im Pi-Integration-Design sehr klar die Tool-Pipeline als eigenes System: Base Tools, dann -Replacements (bash wird z.B. durch exec/process ersetzt), dann -Tools (browser/canvas/sessions/cron/), dann Channel-spezifische Tools, dann Policy-Filtering (profil/provider/agent/group/sandbox), dann Schema-Normalisierung für Provider-Quirks, plus AbortSignal-Wrapping. Das ist extrem “production”: Reasoning kann nur so gut sein wie die Zuverlässigkeit der Actions, und hier wird Actions-Handling wirklich als Pipeline-Produkt behandelt, nicht als Nebenfeature.

Teil 5: Loop Guardrails gegen “Agent hängt fest”
 hat Tool-loop detection als optionales Guardrail: es erkennt wiederholte Tool-Call-Muster ohne Fortschritt (z.B. Polling ohne Ergebnis, wiederholte Fehler). Das ist ein klassisches Anti-Stall-Pattern in Agent-Systemen: du verhinderst, dass das LLM in eine lokale Schleife fällt, die es selbst nicht erkennt. Für Reasoning ist das wichtig, weil viele “Agent wirkt dumm”-Momente genau diese Loops sind.

Teil 6: Hooks/Interceptors als “Reasoning Middleware”
Der Agent Loop hat definierte Hook Points: before_model_resolve (deterministisch Provider/Model überschreiben), before_prompt_build (prependContext/systemPrompt injizieren), before_tool_call/after_tool_call (Tool-Params/Resultate abfangen), tool_result_persist (Tool-Resultate vor Persist/Transcript transformieren), und diverse Message- und Session-Hooks. Das ist ein sehr starkes Architekturpattern, weil du Reasoning-Qualität oft nicht durch “besser prompten” bekommst, sondern durch Middleware: z.B. Tool-Args normalisieren, gefährliche Calls blocken, Ergebnisse komprimieren, kontext-relevante Hinweise injizieren, oder Subagent-Aufgaben nach Schema umschreiben.

Teil 7: Multi-Agent als echte Arbeitsteilung (nicht nur “spawn mal”)
s Multi-Agent-Konzept ist nicht nur “mehrere Chats”, sondern echte Isolierung: separater Workspace, separater agentDir, separate Sessions, separate Credentials. Das ist für Reasoning wichtig, weil du Spezialisten baust, die nicht ständig mit Fremdkontext kollidieren. Routing läuft über Bindings.

Dazu kommen Koordinations-Tools: sessions_spawn kann Subagent-Runs in isolierten Sessions starten und Ergebnisse zurück-announce’n; agent-to-agent Messaging hat sogar eine begrenzte Ping-Pong-Loop mit klaren Stop-Tokens. Das ist ein “structured delegation” Pattern: ein Agent delegiert, bekommt Ergebnis, kann nachfragen, aber in einem begrenzten Rahmen, damit es nicht entgleist.

Und als “Pro-Level”-Pattern: ACP Agents erlauben, externe Coding-Harnesses (Pi, Claude Code, Codex, Gemini CLI etc.) als eigene Laufzeit anzusprechen. Das ist quasi “polyglot agent runtimes”: du nutzt für bestimmte Aufgaben den besten Executor, ohne dein Haupt-Reasoning zu zerreißen.

Teil 8: Operator Controls, die das Reasoning wirklich steuerbar machen
 trennt “User-Text” von “Steuerbefehlen”: Direktiven wie /think, /verbose, /reasoning, /model, /queue werden vom Gateway verarbeitet und vor dem Modell aus der Nachricht gestripped. Das ist ein sauberes Out-of-Band-Control-Pattern: du kannst das Reasoning beeinflussen (Budget, Sichtbarkeit, Queue-Verhalten), ohne den Prompt mit Meta-Anweisungen zu verschmutzen.

Thinking Levels sind dabei nicht nur UI-Spielerei: du hast definierte Level bis hin zu “ultrathink”/“adaptive” (providerabhängig), mit klarer Resolution Order (inline, session override, global default). Dazu Reasoning visibility (on/off/stream) getrennt vom eigentlichen Final-Output. Das ist ein starkes Pattern, weil du “mehr Denken” und “mehr Transparenz” unabhängig voneinander kontrollieren kannst.

Teil 9: “Predictability by Schema” (macht Reasoning indirekt massiv besser)
 validiert Config strikt gegen Schema; unknown keys oder falsche Typen stoppen den Gateway-Start. Das ist kein Reasoning-Feature, aber es verhindert Drift und Ghost-Bugs (“warum hat der Agent heute andere Tools/Policies?”). Für Agent-Reasoning zählt Vorhersagbarkeit der Umgebung extrem.
