# Debug Feature Roadmap — Teil 2: Frontend Components & Implementation Steps

> Detaillierte Implementierungs-Roadmap für den Pipeline Debugger.
> Companion-Dokument: `DEBUG-FEATURE-ROADMAP-1.md` (Design System, UX & Backend)

---

## Inhaltsverzeichnis

6. [Component-Architektur](#6-component-architektur)
7. [State Machine & Data Flow](#7-state-machine--data-flow)
8. [Implementierungs-Phasen (Step-by-Step)](#8-implementierungs-phasen)
9. [Datei-Manifest](#9-datei-manifest)
10. [Test-Strategie Frontend](#10-test-strategie-frontend)
11. [Abnahme-Checkliste](#11-abnahme-checkliste)

---

## 6. Component-Architektur

### 6.1 Component-Tree

```
DebugPageComponent (standalone, route: /debug)
│
├── DebugToolbarComponent (inline template)
│   ├── Play / Pause / Continue Buttons
│   ├── Breakpoint-Manager Dropdown
│   ├── Session-ID Input
│   ├── Agent-Selector
│   ├── Model-Selector
│   └── Connection-Status Pill
│
├── PipelineCanvasComponent
│   ├── PhaseNodeComponent (×9, eine pro Pipeline-Phase)
│   │   ├── Phase-Icon + Label
│   │   ├── Status-Indicator (idle/active/done/error/paused/skipped)
│   │   ├── Breakpoint-Marker (roter Dot)
│   │   ├── Duration-Badge
│   │   └── LLM-Interaction-Badge (Cloud-Icon)
│   │
│   ├── AgentTokenComponent (animierter Avatar)
│   │   └── Position berechnet aus aktiver Phase-Index
│   │
│   ├── EdgeConnectors (CSS pseudo-elements)
│   │   └── Event-Pills auf Kanten
│   │
│   └── LlmBranchNodes (×4, für Planning/Tool/Synthesis/Reflection)
│       ├── Cloud-Icon
│       ├── Call-Nummer (#1, #2, ...)
│       └── Status (idle/active/completed)
│
├── PromptInspectorComponent
│   ├── Tab-Bar (6 Tabs)
│   │   ├── System Prompt
│   │   ├── User Prompt
│   │   ├── LLM Response
│   │   ├── Parsed Output
│   │   ├── Tool Details
│   │   └── Reflection Score
│   │
│   ├── PromptDisplayComponent (wiederverwendbar)
│   │   ├── Header (Label + Char-Count + Token-Est + Copy-Button)
│   │   └── Code-Block mit Syntax-Highlighting
│   │
│   ├── ToolDetailsComponent
│   │   └── Tabelle: Tool | Args | Result | Duration | Status
│   │
│   └── ReflectionScoreCardComponent
│       ├── Score-Bars (Goal-Alignment, Completeness, Factual-Grounding)
│       ├── Verdict (Pass/Retry)
│       └── Threshold-Anzeige
│
├── EventLogComponent (inline template)
│   ├── Filter-Input
│   └── Scrollbare Event-Liste mit Timestamps
│
├── PauseBannerComponent (inline template)
│   ├── Phase-Label
│   ├── Continue-Button (F8 / Space)
│   └── Progress-Info (Phase X von Y)
│
└── DebugComposerComponent (inline template)
    ├── Message-Textarea
    ├── Send-Button
    └── Optional: Agent/Model-Inline-Overrides
```

### 6.2 Component-Spezifikationen

#### DebugPageComponent — Host & State Machine

```typescript
@Component({
  selector: 'app-debug-page',
  standalone: true,
  imports: [
    DebugToolbarComponent,
    PipelineCanvasComponent,
    PromptInspectorComponent,
    EventLogComponent,
    PauseBannerComponent,
    DebugComposerComponent,
  ],
  templateUrl: './debug-page.component.html',
  styleUrl:    './debug-page.component.scss',
})
export class DebugPageComponent implements OnInit, OnDestroy {
  // State Machine
  debugState: DebugState = 'idle';
  currentPhase: PipelinePhase | null = null;
  pausedAtPhase: PipelinePhase | null = null;

  // Phase-Status Map
  phaseStates = new Map<PipelinePhase, PhaseState>();

  // Breakpoints
  activeBreakpoints = new Set<PipelinePhase>();

  // Inspector-Daten
  llmCalls: LlmCallRecord[] = [];
  toolExecutions: ToolExecutionRecord[] = [];
  reflectionVerdict: ReflectionVerdict | null = null;
  selectedPhase: PipelinePhase | null = null;

  // Event-Log
  eventLog: DebugEvent[] = [];

  // Timing
  requestId: string | null = null;
  runStartTime: number | null = null;
  totalDurationMs = 0;

  // Subscriptions
  private subs = new Subscription();
}
```

**Template-Layout:**

```html
<!-- debug-page.component.html -->
<div class="debug-page" [class.debug--paused]="debugState === 'paused'">

  <app-debug-toolbar
    [state]="debugState"
    [currentPhase]="currentPhase"
    [breakpoints]="activeBreakpoints"
    [connected]="isConnected"
    (play)="onPlay()"
    (pause)="onPause()"
    (continue)="onContinue()"
    (breakpointsChange)="onBreakpointsChange($event)"
    (agentChange)="selectedAgent = $event"
    (modelChange)="selectedModel = $event">
  </app-debug-toolbar>

  <div class="debug-workspace">

    <app-pipeline-canvas
      [phaseStates]="phaseStates"
      [currentPhase]="currentPhase"
      [activeBreakpoints]="activeBreakpoints"
      [llmCalls]="llmCalls"
      [toolExecutions]="toolExecutions"
      [eventLog]="eventLog"
      (phaseClick)="onPhaseClick($event)"
      (breakpointToggle)="onBreakpointToggle($event)">
    </app-pipeline-canvas>

    <app-prompt-inspector
      [selectedPhase]="selectedPhase"
      [llmCalls]="llmCalls"
      [toolExecutions]="toolExecutions"
      [reflectionVerdict]="reflectionVerdict">
    </app-prompt-inspector>

  </div>

  @if (debugState === 'paused') {
    <app-pause-banner
      [pausedAtPhase]="pausedAtPhase"
      [phaseIndex]="getPhaseIndex(pausedAtPhase)"
      [totalPhases]="9"
      [llmCallCount]="llmCalls.length"
      [durationMs]="totalDurationMs"
      (continue)="onContinue()">
    </app-pause-banner>
  }

  <app-event-log
    [events]="eventLog">
  </app-event-log>

  <app-debug-composer
    [disabled]="debugState === 'running'"
    (send)="onSendMessage($event)">
  </app-debug-composer>

</div>
```

**Styling der Debug-Seite:**

```scss
// debug-page.component.scss
:host {
  display: block;
  height: calc(100vh - 52px);  // minus top-nav
  overflow: hidden;
}

.debug-page {
  display: grid;
  grid-template-rows: auto 1fr auto auto auto;
  // toolbar | workspace | pause-banner(optional) | event-log | composer
  height: 100%;
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 204, 122, 0.03), transparent 70%),
    radial-gradient(ellipse 60% 40% at 80% 100%, rgba(55, 148, 255, 0.02), transparent 60%),
    var(--c-bg);

  // Subtiler Scanline-Effekt für "Code-Matrix"-Feeling
  &::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0, 204, 122, 0.006) 2px,
      rgba(0, 204, 122, 0.006) 4px
    );
    pointer-events: none;
    z-index: 0;
  }
}

.debug-workspace {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: rgba(0, 204, 122, 0.04);  // Subtile Gap-Line
  overflow: hidden;
  min-height: 0;  // Flex-Shrink erlauben
}

// Responsive
@media (max-width: 1024px) {
  .debug-workspace {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 1fr;
  }
}
```

#### PipelineCanvasComponent

```typescript
@Component({
  selector: 'app-pipeline-canvas',
  standalone: true,
  imports: [PhaseNodeComponent],
  templateUrl: './pipeline-canvas.component.html',
  styleUrl: './pipeline-canvas.component.scss',
})
export class PipelineCanvasComponent {
  @Input() phaseStates!: Map<PipelinePhase, PhaseState>;
  @Input() currentPhase: PipelinePhase | null = null;
  @Input() activeBreakpoints!: Set<PipelinePhase>;
  @Input() llmCalls: LlmCallRecord[] = [];
  @Input() toolExecutions: ToolExecutionRecord[] = [];
  @Input() eventLog: DebugEvent[] = [];

  @Output() phaseClick = new EventEmitter<PipelinePhase>();
  @Output() breakpointToggle = new EventEmitter<PipelinePhase>();

  // Pipeline-Phasen-Definition
  readonly phases: PhaseDefinition[] = [
    { id: 'routing',        label: 'Routing',        icon: '🔀', hasLlm: false, index: 0 },
    { id: 'guardrails',     label: 'Guardrails',     icon: '🛡',  hasLlm: false, index: 1 },
    { id: 'context',        label: 'Memory & Context', icon: '🧠', hasLlm: false, index: 2 },
    { id: 'planning',       label: 'Planning',       icon: '📋', hasLlm: true,  index: 3 },
    { id: 'tool_selection',  label: 'Tool Loop',      icon: '🔧', hasLlm: true,  index: 4 },
    { id: 'synthesis',      label: 'Synthesis',      icon: '✨', hasLlm: true,  index: 5 },
    { id: 'reflection',     label: 'Reflection',     icon: '🔍', hasLlm: true,  index: 6 },
    { id: 'reply_shaping',  label: 'Reply Shaping',  icon: '✂',  hasLlm: false, index: 7 },
    { id: 'response',       label: 'Response + Distill', icon: '📤', hasLlm: false, index: 8 },
  ];

  // Agent-Token Position (Y-Offset berechnet aus Phase-Index)
  get agentTokenY(): number {
    if (!this.currentPhase) return 0;
    const def = this.phases.find(p => p.id === this.currentPhase);
    return def ? def.index * 76 : 0;  // 76px pro Phase-Slot
  }

  get agentAtLlm(): boolean {
    if (!this.currentPhase) return false;
    const def = this.phases.find(p => p.id === this.currentPhase);
    return !!def?.hasLlm && this.isLlmActive(this.currentPhase);
  }

  isLlmActive(phase: PipelinePhase): boolean {
    return this.llmCalls.some(c => c.phase === phase && !c.rawResponse);
  }
}
```

**Canvas Template:**

```html
<!-- pipeline-canvas.component.html -->
<div class="pipeline-canvas">

  <!-- Agent Token -->
  <div class="agent-token"
       [class.at-llm]="agentAtLlm"
       [class.paused]="phaseStates.get(currentPhase!) === 'paused'"
       [style.transform]="'translateY(' + agentTokenY + 'px)'">
  </div>

  <!-- Phase Nodes + Edges -->
  @for (phase of phases; track phase.id) {
    <div class="phase-row">

      <!-- Verbindungslinie zur nächsten Phase -->
      @if (!$last) {
        <div class="edge-line"
             [class.edge--active]="isEdgeActive(phase)"
             [class.edge--completed]="isEdgeCompleted(phase)">
          <!-- Event Pills auf der Kante -->
          @for (event of getEdgeEvents(phase.id); track event.timestamp) {
            <span class="event-pill"
                  [class.pill--error]="event.level === 'error'"
                  [title]="event.stage + ' — ' + event.timestamp">
              {{ event.stage | slice:0:22 }}
            </span>
          }
        </div>
      }

      <!-- Phase Node -->
      <app-phase-node
        [phase]="phase"
        [state]="phaseStates.get(phase.id) ?? 'idle'"
        [isActive]="currentPhase === phase.id"
        [hasBreakpoint]="activeBreakpoints.has(phase.id)"
        [duration]="getPhaseDuration(phase.id)"
        [llmCallCount]="getLlmCallCount(phase.id)"
        [toolCount]="phase.id === 'tool_selection' ? toolExecutions.length : 0"
        (click)="phaseClick.emit(phase.id)"
        (breakpointToggle)="breakpointToggle.emit(phase.id)">
      </app-phase-node>

      <!-- LLM Branch Node (nur für Phasen mit LLM) -->
      @if (phase.hasLlm) {
        <div class="llm-branch">
          <div class="llm-connector"></div>
          <div class="llm-node"
               [class.llm--active]="isLlmActive(phase.id)"
               [class.llm--completed]="isLlmCompleted(phase.id)">
            <span class="llm-icon">☁</span>
            <span class="llm-label">LLM #{{ getLlmCallNumber(phase.id) }}</span>
            @if (getLlmLatency(phase.id); as latency) {
              <span class="llm-latency">{{ latency }}ms</span>
            }
          </div>
        </div>
      }

    </div>
  }

</div>
```

**Canvas SCSS:**

```scss
// pipeline-canvas.component.scss
:host {
  display: block;
  padding: 24px;
  overflow-y: auto;
  background: var(--c-bg-window);
  position: relative;
}

.pipeline-canvas {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
  padding-left: 48px;  // Platz für Agent-Token
}

.phase-row {
  display: flex;
  align-items: center;
  gap: 16px;
  position: relative;
}

.edge-line {
  position: absolute;
  left: 10px;  // Mitte des Phase-Icon
  top: 100%;
  width: 2px;
  height: 16px;
  background: var(--c-border-hi);
  transition: background var(--t);

  &.edge--active {
    background: repeating-linear-gradient(
      180deg,
      var(--c-accent) 0px,
      var(--c-accent) 4px,
      transparent 4px,
      transparent 8px
    );
    background-size: 2px 8px;
    animation: data-flow 600ms linear infinite;
  }

  &.edge--completed {
    background: var(--c-accent);
  }
}

.llm-branch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;

  .llm-connector {
    width: 40px;
    height: 2px;
    background: var(--c-blue-border);
    position: relative;

    // Pfeilspitze
    &::after {
      content: '▶';
      position: absolute;
      right: -2px;
      top: -7px;
      font-size: 8px;
      color: var(--c-blue-border);
    }
  }
}

.llm-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(55, 148, 255, 0.06);
  border: 1px solid var(--c-blue-border);
  border-radius: var(--r-md);
  font-size: 11px;
  color: var(--c-blue);
  white-space: nowrap;
  transition: all var(--t);

  &.llm--active {
    animation: llm-pulse 1.5s ease-in-out infinite;
  }

  &.llm--completed {
    border-color: var(--c-accent-border);
    color: var(--c-accent);

    .llm-icon::after { content: '✓'; }
  }

  .llm-latency {
    font-size: 10px;
    opacity: 0.7;
    font-variant-numeric: tabular-nums;
  }
}

// Agent Token Positionierung
.agent-token {
  position: absolute;
  left: 0;
  top: 12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--c-accent);
  box-shadow:
    0 0 12px var(--c-accent-dim),
    0 0 30px rgba(0, 204, 122, 0.10);
  transition: transform 600ms cubic-bezier(0.34, 1.56, 0.64, 1);
  z-index: var(--z-token);
  display: grid;
  place-items: center;
  font-size: 18px;

  &::after { content: '⚡'; }

  &.at-llm {
    background: var(--c-blue);
    box-shadow: 0 0 20px var(--c-blue-glow);
    animation: llm-thinking 1.5s ease-in-out infinite;
    &::after { content: '☁'; }
  }

  &.paused {
    animation: token-breathe 2s ease-in-out infinite;
    &::after { content: '⏸'; font-size: 14px; }
  }
}

@keyframes data-flow {
  100% { background-position: 0 20px; }
}
```

#### PhaseNodeComponent (Inline Template)

```typescript
@Component({
  selector: 'app-phase-node',
  standalone: true,
  template: `
    <div class="phase-node"
         [class.phase--idle]="state === 'idle'"
         [class.phase--active]="state === 'active'"
         [class.phase--paused]="state === 'paused'"
         [class.phase--completed]="state === 'completed'"
         [class.phase--error]="state === 'error'"
         [class.phase--skipped]="state === 'skipped'"
         (contextmenu)="onRightClick($event)">

      <!-- Breakpoint Dot -->
      @if (hasBreakpoint) {
        <span class="bp-dot" title="Breakpoint"></span>
      }

      <!-- Status Icon -->
      <span class="phase-icon" [class.phase-icon--completed]="state === 'completed'">
        @switch (state) {
          @case ('completed') { ✓ }
          @case ('error') { ✕ }
          @case ('skipped') { — }
          @default { {{ phase.icon }} }
        }
      </span>

      <!-- Separator -->
      <span class="phase-separator">┊</span>

      <!-- Label + Meta -->
      <div class="phase-info">
        <span class="phase-label">{{ phase.label }}</span>
        <div class="phase-meta">
          @if (phase.hasLlm && llmCallCount > 0) {
            <span class="meta-badge meta-badge--llm">
              ☁ LLM #{{ llmCallCount }}
            </span>
          }
          @if (toolCount > 0) {
            <span class="meta-badge meta-badge--tool">
              🔧 ×{{ toolCount }}
            </span>
          }
        </div>
      </div>

      <!-- Duration Badge -->
      @if (duration !== null) {
        <span class="duration-badge">{{ formatDuration(duration) }}</span>
      }
    </div>
  `,
  styles: [`
    .phase-node {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      background: var(--c-surface);
      border: 1.5px solid var(--c-phase-idle);
      border-radius: var(--r-md);
      cursor: pointer;
      transition: border-color var(--t), box-shadow var(--t), background var(--t);
      position: relative;
      min-width: 220px;

      &:hover {
        border-color: var(--c-border-hi);
        background: var(--c-surface-2);
      }

      &.phase--active {
        border-color: var(--c-phase-active);
        animation: phase-pulse 2s ease-in-out infinite;
      }

      &.phase--completed {
        border-color: var(--c-phase-completed);
      }

      &.phase--paused {
        border-color: var(--c-phase-paused);
        background: rgba(255, 179, 71, 0.05);
      }

      &.phase--error {
        border-color: var(--c-phase-error);
        animation: error-shake 400ms ease-in-out;
      }

      &.phase--skipped {
        border-style: dashed;
        opacity: 0.5;
      }
    }

    .bp-dot {
      position: absolute;
      top: -5px;
      left: -5px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--c-bp-dot);
      animation: bp-throb 1.8s ease-in-out infinite;
    }

    .phase-icon {
      width: 22px;
      height: 22px;
      display: grid;
      place-items: center;
      font-size: 14px;
      flex-shrink: 0;
    }

    .phase-icon--completed {
      animation: check-bounce 400ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
      color: var(--c-accent);
    }

    .phase-separator {
      color: var(--c-border-hi);
      font-size: 16px;
    }

    .phase-label {
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.4px;
      text-transform: uppercase;
      color: var(--c-text);
    }

    .phase-meta {
      display: flex;
      gap: 6px;
      margin-top: 2px;
    }

    .meta-badge {
      font-size: 10px;
      color: var(--c-text-dim);

      &.meta-badge--llm { color: var(--c-blue); }
      &.meta-badge--tool { color: var(--c-yellow); }
    }

    .duration-badge {
      margin-left: auto;
      font-size: 10px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      color: var(--c-text-dim);
      padding: 2px 6px;
      background: var(--c-surface-2);
      border-radius: var(--r-sm);
    }

    @keyframes phase-pulse {
      0%, 100% { box-shadow: 0 0 0 0 var(--c-accent-dim); }
      50% { box-shadow: 0 0 24px 6px var(--c-accent-dim); }
    }

    @keyframes check-bounce {
      0% { transform: scale(0); }
      60% { transform: scale(1.3); }
      100% { transform: scale(1); }
    }

    @keyframes error-shake {
      0%, 100% { transform: translateX(0); }
      25% { transform: translateX(-4px); }
      75% { transform: translateX(4px); }
    }

    @keyframes bp-throb {
      0%, 100% { transform: scale(1); box-shadow: 0 0 4px var(--c-bp-glow); }
      50% { transform: scale(1.4); box-shadow: 0 0 14px var(--c-bp-glow); }
    }
  `]
})
export class PhaseNodeComponent {
  @Input() phase!: PhaseDefinition;
  @Input() state: PhaseState = 'idle';
  @Input() isActive = false;
  @Input() hasBreakpoint = false;
  @Input() duration: number | null = null;
  @Input() llmCallCount = 0;
  @Input() toolCount = 0;

  @Output() breakpointToggle = new EventEmitter<void>();

  onRightClick(event: MouseEvent): void {
    event.preventDefault();
    this.breakpointToggle.emit();
  }

  formatDuration(ms: number): string {
    return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
  }
}
```

#### PromptInspectorComponent

```typescript
@Component({
  selector: 'app-prompt-inspector',
  standalone: true,
  imports: [SyntaxHighlightPipe],
  templateUrl: './prompt-inspector.component.html',
  styleUrl: './prompt-inspector.component.scss',
})
export class PromptInspectorComponent {
  @Input() selectedPhase: PipelinePhase | null = null;
  @Input() llmCalls: LlmCallRecord[] = [];
  @Input() toolExecutions: ToolExecutionRecord[] = [];
  @Input() reflectionVerdict: ReflectionVerdict | null = null;

  activeTab: InspectorTab = 'system_prompt';

  readonly tabs: { id: InspectorTab; label: string }[] = [
    { id: 'system_prompt', label: 'System Prompt' },
    { id: 'user_prompt',   label: 'User Prompt' },
    { id: 'llm_response',  label: 'LLM Response' },
    { id: 'parsed_output', label: 'Parsed Output' },
    { id: 'tool_details',  label: 'Tool Details' },
    { id: 'reflection',    label: 'Reflection' },
  ];

  get selectedCall(): LlmCallRecord | undefined {
    return this.llmCalls.find(c => c.phase === this.selectedPhase)
        ?? this.llmCalls[this.llmCalls.length - 1];
  }

  get tabContent(): string {
    const call = this.selectedCall;
    if (!call) return '(keine Daten)';
    switch (this.activeTab) {
      case 'system_prompt': return call.systemPrompt;
      case 'user_prompt':   return call.userPrompt;
      case 'llm_response':  return call.rawResponse;
      case 'parsed_output': return call.parsedOutput;
      default: return '';
    }
  }

  hasData(tabId: InspectorTab): boolean {
    switch (tabId) {
      case 'tool_details': return this.toolExecutions.length > 0;
      case 'reflection': return this.reflectionVerdict !== null;
      default: return !!this.selectedCall;
    }
  }

  async copyToClipboard(text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
  }
}

type InspectorTab =
  'system_prompt' | 'user_prompt' | 'llm_response' |
  'parsed_output' | 'tool_details' | 'reflection';
```

**Inspector Template:**

```html
<!-- prompt-inspector.component.html -->
<div class="inspector">

  <!-- Tab Bar -->
  <div class="inspector-tabs">
    @for (tab of tabs; track tab.id) {
      <button class="tab"
              [class.tab--active]="activeTab === tab.id"
              [class.tab--has-data]="hasData(tab.id)"
              (click)="activeTab = tab.id">
        {{ tab.label }}
      </button>
    }
  </div>

  <!-- Tab Content -->
  <div class="inspector-content">

    @switch (activeTab) {

      @case ('tool_details') {
        <div class="tool-table">
          <div class="tool-header">
            <span>Tool</span>
            <span>Args</span>
            <span>Result</span>
            <span>Duration</span>
            <span>Status</span>
          </div>
          @for (tool of toolExecutions; track tool.timestamp) {
            <div class="tool-row" [class.tool-row--blocked]="tool.blocked">
              <span class="tool-name">{{ tool.tool }}</span>
              <pre class="tool-args">{{ tool.args | json }}</pre>
              <pre class="tool-result">{{ tool.resultPreview }}</pre>
              <span class="tool-duration">{{ tool.durationMs }}ms</span>
              <span class="tool-status">
                @if (tool.blocked) { 🚫 Blocked }
                @else if (tool.exitCode === 0) { ✓ OK }
                @else { ✕ Error ({{ tool.exitCode }}) }
              </span>
            </div>
          }
        </div>
      }

      @case ('reflection') {
        @if (reflectionVerdict; as v) {
          <div class="reflection-card">
            <!-- Goal Alignment -->
            <div class="score-row">
              <span class="score-label">Goal Alignment</span>
              <div class="score-bar">
                <div class="score-fill"
                     [style.width.%]="v.goalAlignment * 100"
                     [class.score--good]="v.goalAlignment >= 0.6"
                     [class.score--warn]="v.goalAlignment >= 0.4 && v.goalAlignment < 0.6"
                     [class.score--bad]="v.goalAlignment < 0.4">
                </div>
              </div>
              <span class="score-value">{{ v.goalAlignment.toFixed(2) }}</span>
            </div>
            <!-- Completeness -->
            <div class="score-row">
              <span class="score-label">Completeness</span>
              <div class="score-bar">
                <div class="score-fill"
                     [style.width.%]="v.completeness * 100"
                     [class.score--good]="v.completeness >= 0.6"
                     [class.score--warn]="v.completeness >= 0.4 && v.completeness < 0.6"
                     [class.score--bad]="v.completeness < 0.4">
                </div>
              </div>
              <span class="score-value">{{ v.completeness.toFixed(2) }}</span>
            </div>
            <!-- Factual Grounding -->
            <div class="score-row">
              <span class="score-label">Factual Grounding</span>
              <div class="score-bar">
                <div class="score-fill"
                     [style.width.%]="v.factualGrounding * 100"
                     [class.score--good]="v.factualGrounding >= 0.6"
                     [class.score--warn]="v.factualGrounding >= 0.4 && v.factualGrounding < 0.6"
                     [class.score--bad]="v.factualGrounding < 0.4">
                </div>
              </div>
              <span class="score-value">{{ v.factualGrounding.toFixed(2) }}</span>
            </div>

            <!-- Verdict -->
            <div class="verdict-row">
              <span class="verdict"
                    [class.verdict--retry]="v.shouldRetry"
                    [class.verdict--pass]="!v.shouldRetry">
                {{ v.shouldRetry ? '⟳ Retry triggered' : '✓ Accepted' }}
              </span>
              <span class="threshold-info">
                Threshold: {{ v.threshold.toFixed(2) }} ·
                Score: {{ v.score.toFixed(2) }}
              </span>
            </div>

            @if (v.issues.length > 0) {
              <div class="issues">
                <span class="issues-label">Issues:</span>
                @for (issue of v.issues; track $index) {
                  <span class="issue-pill">{{ issue }}</span>
                }
              </div>
            }
          </div>
        } @else {
          <div class="empty-state">Reflection nicht ausgeführt oder noch ausstehend</div>
        }
      }

      @default {
        <!-- Prompt/Response Display -->
        <div class="prompt-display">
          <div class="prompt-header">
            <span class="prompt-label">{{ getTabLabel(activeTab) }}</span>
            @if (tabContent) {
              <span class="prompt-meta">
                {{ tabContent.length | number }} chars
              </span>
              <button class="copy-btn" (click)="copyToClipboard(tabContent)">
                ⎘ Copy
              </button>
            }
          </div>
          @if (tabContent) {
            <pre class="prompt-content"><code [innerHTML]="tabContent | syntaxHighlight"></code></pre>
          } @else {
            <div class="empty-state">Keine Daten für diese Phase</div>
          }
        </div>
      }

    }

  </div>
</div>
```

**Inspector SCSS:**

```scss
// prompt-inspector.component.scss
:host {
  display: flex;
  flex-direction: column;
  background: var(--c-inspector-bg);
  overflow: hidden;
}

.inspector-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--c-inspector-border);
  padding: 0 12px;
  overflow-x: auto;
  flex-shrink: 0;

  &::-webkit-scrollbar { display: none; }
}

.tab {
  padding: 10px 14px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.3px;
  color: var(--c-text-dim);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--t), border-color var(--t);
  white-space: nowrap;

  &:hover { color: var(--c-text); }

  &.tab--active {
    color: var(--c-accent);
    border-bottom-color: var(--c-accent);
  }

  &.tab--has-data::after {
    content: '';
    display: inline-block;
    width: 5px;
    height: 5px;
    background: var(--c-accent);
    border-radius: 50%;
    margin-left: 6px;
    vertical-align: middle;
  }
}

.inspector-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.prompt-display {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.prompt-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-accent);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.prompt-meta {
  font-size: 11px;
  color: var(--c-text-muted);
  font-variant-numeric: tabular-nums;
}

.copy-btn {
  margin-left: auto;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--c-text-dim);
  background: var(--c-btn);
  border: 1px solid var(--c-btn-border);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: all var(--t-fast);

  &:hover {
    color: var(--c-text);
    border-color: var(--c-btn-hover-border);
  }
}

.prompt-content {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.65;
  color: var(--c-text);
  background: var(--c-code-bg);
  padding: 16px;
  border-radius: var(--r-md);
  border: 1px solid var(--c-border);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  tab-size: 2;
  margin: 0;
}

// Reflection Score Card
.reflection-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  background: var(--c-surface);
  border-radius: var(--r-lg);
  border: 1px solid var(--c-border);
}

.score-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--c-text-dim);
  width: 140px;
  flex-shrink: 0;
}

.score-bar {
  flex: 1;
  height: 8px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: var(--r-full);
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: var(--r-full);
  animation: bar-fill 800ms ease-out forwards;

  &.score--good { background: var(--c-accent); }
  &.score--warn { background: var(--c-yellow); }
  &.score--bad  { background: var(--c-red); }
}

.score-value {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--c-text);
  width: 36px;
  text-align: right;
}

.verdict-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--c-border);
}

.verdict {
  font-size: 13px;
  font-weight: 600;

  &.verdict--pass { color: var(--c-accent); }
  &.verdict--retry { color: var(--c-yellow); }
}

.threshold-info {
  font-size: 11px;
  color: var(--c-text-muted);
}

.issues {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.issues-label {
  font-size: 11px;
  color: var(--c-text-dim);
}

.issue-pill {
  padding: 2px 8px;
  font-size: 10px;
  background: var(--c-red-dim);
  color: var(--c-red);
  border-radius: var(--r-full);
}

// Tool Table
.tool-table {
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  overflow: hidden;
}

.tool-header, .tool-row {
  display: grid;
  grid-template-columns: 100px 1fr 1fr 70px 80px;
  gap: 8px;
  padding: 8px 12px;
  font-size: 11px;
}

.tool-header {
  background: var(--c-surface-2);
  font-weight: 600;
  color: var(--c-text-dim);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.tool-row {
  border-top: 1px solid var(--c-border);
  color: var(--c-text);

  &.tool-row--blocked { opacity: 0.5; }
}

.tool-name {
  color: var(--c-accent);
  font-weight: 500;
}

.tool-args, .tool-result {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
}

.tool-duration {
  font-variant-numeric: tabular-nums;
  color: var(--c-text-dim);
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 120px;
  color: var(--c-text-muted);
  font-size: 13px;
}

@keyframes bar-fill {
  from { width: 0; }
}
```

#### SyntaxHighlightPipe

```typescript
// pipes/syntax-highlight.pipe.ts
import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'syntaxHighlight', standalone: true })
export class SyntaxHighlightPipe implements PipeTransform {
  // Alle Regex-Rules mit den neuen Farben
  private rules: [RegExp, string][] = [
    // Markdown Headers → Accent Green
    [/^(#{1,6}\s.+)$/gm, '<span style="color:rgb(0,204,122);font-weight:600">$1</span>'],
    // JSON Keys → Blue
    [/"([^"]+)"\s*:/g, '<span style="color:rgb(55,148,255)">"$1"</span>:'],
    // Strings → Yellow
    [/"([^"]*)"(?!\s*:)/g, '<span style="color:rgb(229,178,0)">"$1"</span>'],
    // Numbers → Cyan
    [/\b(\d+\.?\d*)\b/g, '<span style="color:rgb(86,216,216)">$1</span>'],
    // Booleans → Accent
    [/\b(true|false|null|None)\b/g, '<span style="color:rgb(0,204,122)">$1</span>'],
    // CLASSIFY: / Step / TOOL / WHAT / WHY → Bold
    [/\b(CLASSIFY|Step|TOOL|WHAT|WHY|DEPENDS_ON|FALLBACK)\b/g,
      '<span style="color:rgb(212,212,212);font-weight:600">$1</span>'],
    // Error/Warning keywords → Red
    [/\b(error|Error|ERROR|fail|FAIL|exception|Exception)\b/g,
      '<span style="color:#ff5555">$1</span>'],
  ];

  transform(value: string): string {
    if (!value) return '';
    // Erst HTML-Entities escapen (gegen Injection)
    let escaped = value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    // Dann Rules anwenden
    for (const [regex, replacement] of this.rules) {
      escaped = escaped.replace(regex, replacement);
    }
    return escaped;
  }
}
```

---

## 7. State Machine & Data Flow

### 7.1 State-Übergänge

```
                ┌──────────────┐
       ┌───────▶│     IDLE     │◀──────────────┐
       │        │  Kein Run    │               │
       │        └──────┬───────┘               │
       │               │ sendMessage()         │
       │               ▼                       │
       │        ┌──────────────┐               │
       │   ┌───▶│   RUNNING    │───┐           │
       │   │    │  Pipeline    │   │           │
       │   │    │  aktiv       │   │           │
       │   │    └──────┬───────┘   │           │
       │   │           │           │           │
       │   │    Pause  │  Breakpoint            │
       │   │    gedrückt│  erreicht             │
       │   │           ▼           ▼           │
       │   │    ┌──────────────┐               │
       │   │    │    PAUSED    │               │
       │   │    │  Wartet auf  │               │
       │   │    │  Continue    │               │
       │   │    └──────┬───────┘               │
       │   │           │                       │
       │   │    Continue gedrückt              │
       │   └───────────┘                       │
       │                                       │
       │        ┌──────────────┐               │
       │        │  COMPLETED   │───────────────┘
       │        │  Run fertig  │  auto-reset 2s
       │        └──────────────┘
       │
       │        ┌──────────────┐
       └────────│    ERROR     │
                │  Run fehler  │
                └──────────────┘
```

### 7.2 TypeScript Interfaces

```typescript
// Alle Types in einer types.ts Datei

type DebugState = 'idle' | 'running' | 'paused' | 'completed' | 'error';

type PipelinePhase =
  | 'routing' | 'guardrails' | 'context' | 'planning'
  | 'tool_selection' | 'tool_execution' | 'synthesis'
  | 'reflection' | 'reply_shaping' | 'response';

type PhaseState = 'idle' | 'active' | 'paused' | 'completed' | 'error' | 'skipped';

interface PhaseDefinition {
  id: PipelinePhase;
  label: string;
  icon: string;
  hasLlm: boolean;
  index: number;
}

interface LlmCallRecord {
  phase: PipelinePhase;
  systemPrompt: string;
  userPrompt: string;
  rawResponse: string;
  parsedOutput: string;
  model: string;
  temperature: number;
  latencyMs: number;
  tokensEst: number;
  timestamp: string;
}

interface ToolExecutionRecord {
  tool: string;
  args: Record<string, unknown>;
  resultPreview: string;
  durationMs: number;
  exitCode: number;
  blocked: boolean;
  timestamp: string;
}

interface ReflectionVerdict {
  goalAlignment: number;
  completeness: number;
  factualGrounding: number;
  score: number;
  shouldRetry: boolean;
  hardFactualFail: boolean;
  issues: string[];
  suggestedFix: string | null;
  threshold: number;
}

interface DebugEvent {
  stage: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  details?: Record<string, unknown>;
}
```

### 7.3 Event-Routing in DebugPageComponent

```typescript
private applyDebugEvent(event: AgentSocketEvent): void {
  // Immer loggen
  this.eventLog.push({
    stage: event.stage ?? event.type,
    timestamp: event.ts ?? new Date().toISOString(),
    level: event.type === 'error' ? 'error' : 'info',
    details: event as any,
  });

  // Nach Stage routen
  const stage = event.stage;
  switch (stage) {
    case 'run_started':
      this.debugState = 'running';
      this.runStartTime = Date.now();
      this.activatePhase('routing');
      break;

    case 'guardrails_passed':
      this.completePhase('routing');
      this.completePhase('guardrails');
      break;

    case 'memory_updated':
    case 'context_segmented':
      this.activatePhase('context');
      break;

    case 'planning_started':
      this.completePhase('context');
      this.activatePhase('planning');
      break;

    case 'planning_completed':
      this.completePhase('planning');
      break;

    case 'debug_prompt_sent':
      this.recordPromptSent(event.details);
      break;

    case 'debug_llm_response':
      this.recordLlmResponse(event.details);
      break;

    case 'debug_post_processed':
      this.recordPostProcessed(event.details);
      break;

    case 'debug_breakpoint_hit':
      this.debugState = 'paused';
      this.pausedAtPhase = event.details?.phase as PipelinePhase;
      this.phaseStates.set(this.pausedAtPhase, 'paused');
      break;

    case 'tool_execution_detail':
      this.activatePhase('tool_execution');
      this.toolExecutions.push(event.details as ToolExecutionRecord);
      break;

    case 'reflection_completed':
      this.reflectionVerdict = event.details as ReflectionVerdict;
      this.completePhase('reflection');
      break;

    case 'reflection_skipped':
      this.phaseStates.set('reflection', 'skipped');
      break;

    case 'reply_shaping_completed':
      this.completePhase('reply_shaping');
      break;

    case 'run_completed':
      this.completePhase('response');
      this.debugState = 'completed';
      this.totalDurationMs = Date.now() - (this.runStartTime ?? Date.now());
      break;
  }
}

private activatePhase(phase: PipelinePhase): void {
  this.currentPhase = phase;
  this.phaseStates.set(phase, 'active');
  this.selectedPhase = phase;
}

private completePhase(phase: PipelinePhase): void {
  this.phaseStates.set(phase, 'completed');
}
```

### 7.4 Keyboard Shortcuts

```typescript
@HostListener('document:keydown', ['$event'])
handleKeyboard(event: KeyboardEvent): void {
  // Nicht auslösen wenn User im Input tippt
  const target = event.target as HTMLElement;
  if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') return;

  switch (event.key) {
    case 'F5':
      event.preventDefault();
      this.onPlay();
      break;
    case 'F6':
      event.preventDefault();
      this.onPause();
      break;
    case 'F8':
    case ' ':  // Space
      event.preventDefault();
      this.onContinue();
      break;
    case 'F9':
      event.preventDefault();
      if (this.currentPhase) {
        this.onBreakpointToggle(this.currentPhase);
      }
      break;
  }
}
```

---

## 8. Implementierungs-Phasen (Step-by-Step)

### Phase 1 — Color-Schema Migration (App-weit)

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 1.1 | `:root` Block in `styles.scss` komplett ersetzen mit neuem Schema | `frontend/src/styles.scss` | ~80 |
| 1.2 | `app.scss` — Alle `--c-gold*` → `--c-accent*`, BGs aktualisieren | `frontend/src/app/app.scss` | ~30 |
| 1.3 | `chat-page.component.scss` — Farb-Referenzen migrieren | `frontend/src/app/pages/chat-page.component.scss` | ~40 |
| 1.4 | `memory-page.component.scss` — Farb-Referenzen migrieren | `frontend/src/app/pages/memory-page.component.scss` | ~20 |
| 1.5 | Visueller Test: Alle Seiten durchklicken, Screenshots vergleichen | Manual | — |

**Checkpoint:** App sieht mit neuem Schema konsistent aus, keine gebrochenen Farben.

---

### Phase 2 — Backend Debug-Infrastruktur

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 2.1 | `debug_mode` Setting in `config.py` sicherstellen | `backend/app/config.py` | ~3 |
| 2.2 | Debug-Attribute in `agent.py` `__init__` hinzufügen | `backend/app/agent.py` | ~5 |
| 2.3 | `_debug_checkpoint()` Methode implementieren | `backend/app/agent.py` | ~20 |
| 2.4 | Debug-Gate in `_emit_lifecycle()` hinzufügen | `backend/app/agent.py` | ~3 |
| 2.5 | 7× `_debug_checkpoint()` Calls in `run()` einfügen | `backend/app/agent.py` | ~14 |
| 2.6 | `debug_prompt_sent` + `debug_llm_response` an 6 Call-Sites | Diverse Sub-Agents | ~60 |
| 2.7 | `send_event` durch PlannerStepExecutor + SynthesizeStepExecutor threading | `orchestrator/step_executors.py` | ~30 |
| 2.8 | Neue Message-Types in `ws_handler.py` dispatchen | `backend/app/ws_handler.py` | ~20 |
| 2.9 | `breakpoints` Field in `WsInboundEnvelope` | `backend/app/models.py` | ~2 |
| 2.10 | Unit-Tests für Debug-Checkpoint + Gates | `backend/tests/test_debug_checkpoint.py` | ~100 |

**Checkpoint:** `DEBUG_MODE=true` + Breakpoints funktionieren über WS.

---

### Phase 3 — Frontend Scaffolding

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 3.1 | Route `/debug` in `app.routes.ts` registrieren | `frontend/src/app/app.routes.ts` | ~3 |
| 3.2 | Debug-Link in `app.html` Navigation hinzufügen | `frontend/src/app/app.html` | ~5 |
| 3.3 | `DebugPageComponent` anlegen (Shell mit Grid-Layout) | `frontend/src/app/pages/debug-page/` | ~80 |
| 3.4 | Types-Datei mit allen Interfaces | `frontend/src/app/pages/debug-page/debug.types.ts` | ~80 |
| 3.5 | `AgentSocketService` Extensions (+4 Methoden) | `frontend/src/app/services/agent-socket.service.ts` | ~25 |

**Checkpoint:** `/debug` Route lädt, leere Shell mit Toolbar sichtbar.

---

### Phase 4 — Pipeline Canvas

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 4.1 | `PipelineCanvasComponent` mit Phase-Rendering + Edges | `pipeline-canvas/` | ~200 |
| 4.2 | `PhaseNodeComponent` mit allen 6 States | `pipeline-canvas/` | ~150 |
| 4.3 | Agent-Token Animation (CSS transitions) | In Canvas SCSS | ~40 |
| 4.4 | LLM-Branch-Nodes mit Cloud-Icons | In Canvas Template | ~30 |
| 4.5 | Event-Pills auf Kanten | In Canvas Template | ~20 |
| 4.6 | Responsive Grid (Tablet/Mobile Breakpoints) | In Canvas SCSS | ~30 |

**Checkpoint:** Alle 9 Phasen sichtbar, Agent-Token animiert bei manueller State-Änderung.

---

### Phase 5 — Prompt Inspector

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 5.1 | `PromptInspectorComponent` mit 6 Tabs | `prompt-inspector/` | ~200 |
| 5.2 | `SyntaxHighlightPipe` (regex-basiert) | `pipes/syntax-highlight.pipe.ts` | ~50 |
| 5.3 | Reflection Score Card (Score-Bars, Verdict) | In Inspector Template | ~60 |
| 5.4 | Tool-Details Tabelle | In Inspector Template | ~40 |
| 5.5 | Copy-to-Clipboard Funktion | In Inspector TS | ~10 |

**Checkpoint:** Inspector zeigt Daten korrekt an, Tabs wechseln, Syntax-Highlighting funktioniert.

---

### Phase 6 — Debug Controls & State Machine

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 6.1 | `DebugToolbarComponent` (Play/Pause/Continue/Breakpoints) | `debug-toolbar/` | ~80 |
| 6.2 | State Machine in `DebugPageComponent` | `debug-page.component.ts` | ~120 |
| 6.3 | WebSocket Event-Routing (`applyDebugEvent`) | `debug-page.component.ts` | ~100 |
| 6.4 | Keyboard Shortcuts (F5/F6/F8/F9/Space) | `debug-page.component.ts` | ~30 |
| 6.5 | `PauseBannerComponent` (Continue-Banner bei Pause) | `debug-page.component.ts` (inline) | ~40 |
| 6.6 | `DebugComposerComponent` (Message-Input) | `debug-page.component.ts` (inline) | ~30 |

**Checkpoint:** End-to-End: Nachricht senden → Phasen animieren → Breakpoint pausiert → Continue funktioniert.

---

### Phase 7 — Event-Log & Polish

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 7.1 | `EventLogComponent` (filterbarer Event-Stream) | `event-log/` | ~60 |
| 7.2 | Duration-Badges auf Phase-Nodes | Canvas Updates | ~15 |
| 7.3 | `prefers-reduced-motion` Support | Global SCSS | ~10 |
| 7.4 | Edge-Cases: WS-Disconnect während Debug, Error-State | Component Logic | ~30 |
| 7.5 | Mobile-Responsive Final-Polish | SCSS Breakpoints | ~20 |

**Checkpoint:** Feature vollständig, responsive, accessible.

---

### Phase 8 — Testing

| # | Task | Datei | LOC |
|---|------|-------|-----|
| 8.1 | Frontend Unit Tests (Component + Pipe) | `*.spec.ts` | ~200 |
| 8.2 | Backend Integration Tests | `test_debug_integration.py` | ~150 |
| 8.3 | Manueller E2E-Walkthrough mit echtem LLM | Manual | — |

---

### Zusammenfassung LOC-Schätzung

| Phase | Beschreibung | Geschätzte LOC |
|-------|-------------|---------------|
| 1 | Color-Schema Migration | ~170 |
| 2 | Backend Debug-Infrastruktur | ~257 |
| 3 | Frontend Scaffolding | ~193 |
| 4 | Pipeline Canvas | ~470 |
| 5 | Prompt Inspector | ~360 |
| 6 | Debug Controls & State Machine | ~400 |
| 7 | Event-Log & Polish | ~135 |
| 8 | Testing | ~350 |
| **Gesamt** | | **~2335** |

---

## 9. Datei-Manifest

### Neue Dateien

```
frontend/src/app/pages/debug-page/
├── debug-page.component.ts            # Host-Component + State Machine
├── debug-page.component.html          # Layout Template
├── debug-page.component.scss          # Seiten-Layout + Debug-BG
├── debug.types.ts                     # Alle TypeScript Interfaces
│
├── pipeline-canvas/
│   ├── pipeline-canvas.component.ts   # Canvas Grid + Agent Token
│   ├── pipeline-canvas.component.html # Phase-Nodes + Edges + LLM-Branches
│   ├── pipeline-canvas.component.scss # Animations, Keyframes, Grid
│   └── phase-node.component.ts        # Einzel-Node (Inline Template)
│
├── prompt-inspector/
│   ├── prompt-inspector.component.ts  # Tabbed Panel
│   ├── prompt-inspector.component.html # Tabs + Content
│   └── prompt-inspector.component.scss # Inspector Styling
│
├── debug-toolbar/
│   └── debug-toolbar.component.ts     # Toolbar (Inline Template)
│
├── event-log/
│   └── event-log.component.ts         # Event Stream (Inline Template)
│
└── pipes/
    └── syntax-highlight.pipe.ts       # Regex Syntax Highlighting

backend/tests/
├── test_debug_checkpoint.py           # Unit Tests
└── test_debug_integration.py          # Integration Tests
```

### Modifizierte Dateien

```
frontend/src/styles.scss                        # Neues :root Color Schema
frontend/src/app/app.scss                       # Nav-Farben aktualisieren
frontend/src/app/app.html                       # Debug-Link in Nav
frontend/src/app/app.routes.ts                  # /debug Route
frontend/src/app/pages/chat-page.component.scss # Farb-Migration
frontend/src/app/pages/memory-page.component.scss # Farb-Migration
frontend/src/app/services/agent-socket.service.ts # +4 Debug-Methoden

backend/app/agent.py                            # Checkpoints + Debug Events
backend/app/ws_handler.py                       # Debug Message Handling
backend/app/models.py                           # breakpoints Field
backend/app/config.py                           # debug_mode Setting
backend/app/orchestrator/step_executors.py      # send_event Threading
backend/app/agents/planner_agent.py             # debug_prompt_sent Emission
backend/app/agents/tool_selector_agent.py       # debug_prompt_sent Emission
backend/app/agents/synthesizer_agent.py         # debug_prompt_sent Emission
backend/app/services/reflection_service.py      # debug_prompt_sent Emission
```

---

## 10. Test-Strategie Frontend

### 10.1 Unit Tests (Vitest)

```typescript
// debug-page.component.spec.ts
describe('DebugPageComponent', () => {
  it('should create', () => { ... });
  it('should start in idle state', () => { ... });
  it('should transition to running on sendMessage', () => { ... });
  it('should transition to paused on breakpoint_hit', () => { ... });
  it('should show pause banner when paused', () => { ... });
  it('should send debug_continue on Continue click', () => { ... });
  it('should send debug_continue on F8 key', () => { ... });
  it('should NOT capture F8 when composer focused', () => { ... });
  it('should toggle breakpoint on phase node right-click', () => { ... });
  it('should display system prompt in inspector', () => { ... });
  it('should display raw LLM response', () => { ... });
  it('should show reflection scores with correct colors', () => { ... });
  it('should display tool execution details', () => { ... });
  it('should transition to completed on run_completed', () => { ... });
  it('should auto-reset to idle after completion', () => { ... });
});

// pipeline-canvas.component.spec.ts
describe('PipelineCanvasComponent', () => {
  it('should render all 9 phase nodes', () => { ... });
  it('should position agent token at active phase', () => { ... });
  it('should show LLM branch nodes for phases with LLM', () => { ... });
  it('should display event pills on edges', () => { ... });
  it('should show breakpoint dot when set', () => { ... });
  it('should show duration badge when completed', () => { ... });
});

// prompt-inspector.component.spec.ts
describe('PromptInspectorComponent', () => {
  it('should switch tabs', () => { ... });
  it('should show green dot for tabs with data', () => { ... });
  it('should highlight syntax in prompt content', () => { ... });
  it('should copy content to clipboard', () => { ... });
  it('should render reflection score bars', () => { ... });
  it('should render tool details table', () => { ... });
});

// syntax-highlight.pipe.spec.ts
describe('SyntaxHighlightPipe', () => {
  it('should escape HTML entities', () => { ... });
  it('should highlight markdown headers', () => { ... });
  it('should highlight JSON keys', () => { ... });
  it('should highlight numbers', () => { ... });
  it('should highlight error keywords', () => { ... });
  it('should handle empty input', () => { ... });
});
```

### 10.2 Integration Test Scenario

```
1. Navigiere zu /debug
2. Setze Breakpoint auf "Planning"
3. Sende Nachricht "Hello"
4. ✓ Agent-Token bewegt sich zu Routing → Guardrails → Context
5. ✓ Bei Planning: Pause-Banner erscheint
6. ✓ Inspector zeigt System-Prompt
7. Drücke F8 (Continue)
8. ✓ Pipeline läuft weiter zu Tool Loop → Synthesis → Reflection
9. ✓ Reflection Score Card zeigt Werte
10. ✓ State wird "completed"
11. ✓ Alle Events im Event-Log sichtbar
```

---

## 11. Abnahme-Checkliste

### Funktional

- [ ] `/debug` Route navigierbar
- [ ] Debug-Link in Nav sichtbar und aktiv-markiert
- [ ] 9 Phase-Nodes im Canvas
- [ ] Agent-Token Animation (smooth, 600ms overshoot)
- [ ] LLM-Branch-Nodes für Planning/Tool/Synthesis/Reflection
- [ ] Play/Pause/Continue Buttons funktionieren
- [ ] Breakpoints setzen (Klick + F9)
- [ ] Continue-Banner bei Pause
- [ ] F5/F6/F8/Space Shortcuts
- [ ] System-Prompt im Inspector
- [ ] User-Prompt im Inspector
- [ ] Raw LLM Response im Inspector
- [ ] Parsed-Output im Inspector
- [ ] Tool-Details Tabelle
- [ ] Reflection Score Card
- [ ] Event-Log Filtering
- [ ] Debug-Composer sendet Nachricht
- [ ] Shared WebSocket (kein zweiter Connect)
- [ ] Copy-to-Clipboard funktioniert

### Visuell

- [ ] Neues Farbschema konsistent auf allen Seiten
- [ ] Glasmorphic Panels mit Blur
- [ ] AI-Style Glow-Effekte
- [ ] Phase-Pulse Animation
- [ ] LLM-Thinking Animation (Cloud-Glow)
- [ ] Data-Flow Animation auf Edges
- [ ] Breakpoint Throb-Animation
- [ ] Check-Bounce bei Phase-Completion
- [ ] Error-Shake bei Phase-Error
- [ ] Score-Bar Fill-Animation
- [ ] Scanline-Effekt auf Debug-Page

### Responsive

- [ ] Desktop (> 1024px): 2-Spalten Workspace
- [ ] Tablet (768–1024px): gestackte Panels
- [ ] Mobile (< 768px): vertikaler Canvas
- [ ] `prefers-reduced-motion` deaktiviert alle Animationen

### Performance

- [ ] ≤ 6 gleichzeitige CSS-Animationen
- [ ] Keine DOM-Leaks (Subscription-Cleanup)
- [ ] Event-Log virtualisiert ab > 500 Events
- [ ] Canvas rendert < 50 DOM-Nodes

### Sicherheit

- [ ] Debug-Events nur bei `DEBUG_MODE=true` emittiert
- [ ] Breakpoint-Namen gegen Whitelist validiert
- [ ] `SyntaxHighlightPipe` escaped HTML vor Highlighting
- [ ] Kein Prompt-Leaking in Produktion

### Accessibility

- [ ] Keyboard-navigierbar (Tab + Arrow Keys)
- [ ] Focus-Visible auf allen Buttons
- [ ] Screen-Reader: Phase-Status als ARIA-Labels
- [ ] Reduced-Motion unterstützt
