import { Component, EventEmitter, Input, Output } from '@angular/core';
import { UpperCasePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DebugState, PipelinePhase } from '../debug.types';

@Component({
  selector: 'app-debug-toolbar',
  standalone: true,
  imports: [FormsModule, UpperCasePipe],
  template: `
    <div class="toolbar" role="toolbar" aria-label="Debug Controls">

      <!-- Transport Controls -->
      <div class="toolbar-group">
        <button class="ctrl-btn"
                [disabled]="state === 'running'"
                [class.ctrl--active]="state === 'idle' || state === 'completed'"
                (click)="play.emit()"
                title="Play (F5)"
                aria-label="Play">
          ▶
        </button>
        <button class="ctrl-btn"
                [disabled]="state !== 'running'"
                (click)="pause.emit()"
                title="Pause (F6)"
                aria-label="Pause">
          ⏸
        </button>
        <button class="ctrl-btn ctrl-btn--continue"
                [disabled]="state !== 'paused'"
                (click)="continueRun.emit()"
                title="Continue (F8 / Space)"
                aria-label="Continue">
          ⏭
        </button>
      </div>

      <!-- Separator -->
      <div class="toolbar-sep"></div>

      <!-- Breakpoint Manager -->
      <div class="toolbar-group">
        <div class="bp-manager">
          <button class="bp-toggle" (click)="bpDropdownOpen = !bpDropdownOpen" aria-label="Breakpoints verwalten">
            🔴 BP ({{ breakpoints.size }})
          </button>
          @if (bpDropdownOpen) {
            <div class="bp-dropdown">
              @for (phase of allPhases; track phase) {
                <label class="bp-option">
                  <input type="checkbox"
                         [checked]="breakpoints.has(phase)"
                         (change)="toggleBreakpoint(phase)">
                  <span>{{ phase }}</span>
                </label>
              }
            </div>
          }
        </div>
      </div>

      <div class="toolbar-sep"></div>

      <!-- Session ID -->
      <div class="toolbar-group">
        <label class="toolbar-label">Session</label>
        <input class="toolbar-input"
               type="text"
               placeholder="session-id"
               [ngModel]="sessionId"
               (ngModelChange)="sessionId = $event">
      </div>

      <!-- Spacer -->
      <div class="toolbar-spacer"></div>

      <!-- Status Pill -->
      <div class="status-pill"
           [class.status--connected]="connected"
           [class.status--disconnected]="!connected">
        <span class="status-dot"></span>
        {{ connected ? 'Connected' : 'Disconnected' }}
      </div>

      <!-- State Badge -->
      <div class="state-badge"
           [class.state--idle]="state === 'idle'"
           [class.state--running]="state === 'running'"
           [class.state--paused]="state === 'paused'"
           [class.state--completed]="state === 'completed'"
           [class.state--error]="state === 'error'">
        {{ state | uppercase }}
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; flex-shrink: 0; }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: var(--c-bg-tab);
      border-bottom: 1px solid var(--c-border);
      z-index: var(--z-toolbar);
    }

    .toolbar-group {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .toolbar-sep {
      width: 1px;
      height: 22px;
      background: var(--c-border-hi);
      margin: 0 4px;
    }

    .toolbar-spacer { flex: 1; }

    .ctrl-btn {
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      background: var(--c-btn);
      border: 1px solid var(--c-btn-border);
      border-radius: var(--r-sm);
      color: var(--c-btn-text);
      font-size: 14px;
      cursor: pointer;
      transition: all var(--t-fast);

      &:hover:not(:disabled) {
        background: var(--c-btn-hover);
        border-color: var(--c-btn-hover-border);
      }

      &:focus-visible {
        outline: 2px solid var(--c-border-focus);
        outline-offset: 2px;
      }

      &:disabled {
        opacity: 0.35;
        cursor: not-allowed;
      }

      &.ctrl--active {
        color: var(--c-accent);
      }

      &.ctrl-btn--continue {
        background: var(--c-accent-dim);
        border-color: var(--c-accent-border);
        color: var(--c-accent);

        &:disabled { background: var(--c-btn); border-color: var(--c-btn-border); color: var(--c-btn-text); }
      }
    }

    .bp-manager { position: relative; }

    .bp-toggle {
      padding: 4px 10px;
      font-size: 11px;
      background: var(--c-btn);
      border: 1px solid var(--c-btn-border);
      border-radius: var(--r-sm);
      color: var(--c-text);
      cursor: pointer;

      &:hover { border-color: var(--c-btn-hover-border); }
      &:focus-visible { outline: 2px solid var(--c-border-focus); outline-offset: 2px; }
    }

    .bp-dropdown {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      min-width: 180px;
      background: var(--c-bg-window);
      border: 1px solid var(--c-border-hi);
      border-radius: var(--r-md);
      padding: 8px;
      box-shadow: var(--shadow-md);
      z-index: var(--z-overlay);
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .bp-option {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 6px;
      font-size: 11px;
      color: var(--c-text);
      cursor: pointer;
      border-radius: var(--r-sm);

      &:hover { background: var(--c-surface-2); }

      input[type="checkbox"] { accent-color: var(--c-bp-dot); }
    }

    .toolbar-label {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--c-text-muted);
    }

    .toolbar-input {
      width: 140px;
      padding: 4px 8px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      background: var(--c-bg);
      border: 1px solid var(--c-border);
      border-radius: var(--r-sm);
      color: var(--c-text);

      &:focus {
        outline: none;
        border-color: var(--c-border-focus);
      }
    }

    .status-pill {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 500;
      letter-spacing: 0.3px;
      border-radius: var(--r-full);

      &.status--connected {
        background: var(--c-green-dim);
        color: var(--c-green);
      }

      &.status--disconnected {
        background: var(--c-red-dim);
        color: var(--c-red);
      }
    }

    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }

    .state-badge {
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.5px;
      border-radius: var(--r-sm);
      border: 1px solid transparent;

      &.state--idle { color: var(--c-text-muted); background: var(--c-surface); }
      &.state--running { color: var(--c-accent); background: var(--c-accent-dim); border-color: var(--c-accent-border); }
      &.state--paused { color: var(--c-amber); background: rgba(255, 179, 71, 0.12); border-color: rgba(255, 179, 71, 0.35); }
      &.state--completed { color: var(--c-accent); background: var(--c-accent-dim); }
      &.state--error { color: var(--c-red); background: var(--c-red-dim); border-color: var(--c-red); }
    }
  `]
})
export class DebugToolbarComponent {
  @Input() state: DebugState = 'idle';
  @Input() currentPhase: PipelinePhase | null = null;
  @Input() breakpoints = new Set<PipelinePhase>();
  @Input() connected = false;

  @Output() play = new EventEmitter<void>();
  @Output() pause = new EventEmitter<void>();
  @Output() continueRun = new EventEmitter<void>();
  @Output() breakpointsChange = new EventEmitter<Set<PipelinePhase>>();

  sessionId = '';
  bpDropdownOpen = false;

  readonly allPhases: PipelinePhase[] = [
    'routing', 'guardrails', 'context', 'agent_loop',
    'reflection', 'reply_shaping', 'response',
  ];

  toggleBreakpoint(phase: PipelinePhase): void {
    const next = new Set(this.breakpoints);
    if (next.has(phase)) {
      next.delete(phase);
    } else {
      next.add(phase);
    }
    this.breakpointsChange.emit(next);
  }
}
