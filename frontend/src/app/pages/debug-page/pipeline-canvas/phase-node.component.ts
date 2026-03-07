import { Component, EventEmitter, Input, Output } from '@angular/core';
import { PhaseDefinition, PhaseState } from '../debug.types';

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
         [attr.aria-label]="phase.label + ' — ' + state"
         [title]="tooltip"
         role="listitem"
         tabindex="0"
         (contextmenu)="onRightClick($event)">

      @if (hasBreakpoint) {
        <span class="bp-dot" title="Breakpoint" aria-label="Breakpoint aktiv"></span>
      }

      <span class="phase-icon" [class.phase-icon--completed]="state === 'completed'">
        @switch (state) {
          @case ('completed') { ✓ }
          @case ('error') { ✕ }
          @case ('skipped') { — }
          @default { {{ phase.icon }} }
        }
      </span>

      <span class="phase-separator">┊</span>

      <div class="phase-info">
        <span class="phase-label">{{ phase.label }}</span>
        <div class="phase-meta">
          @if (phase.hasLlm && llmCallCount > 0) {
            <span class="meta-badge meta-badge--llm">☁ LLM #{{ llmCallCount }}</span>
          }
          @if (toolCount > 0) {
            <span class="meta-badge meta-badge--tool">🔧 ×{{ toolCount }}</span>
          }
        </div>
      </div>

      @if (duration !== null) {
        <span class="duration-badge">{{ formatDuration(duration) }}</span>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }

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

      &:focus-visible {
        outline: 2px solid var(--c-border-focus);
        outline-offset: 2px;
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

    .phase-info {
      display: flex;
      flex-direction: column;
      min-width: 0;
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

    @media (prefers-reduced-motion: reduce) {
      .phase-node, .bp-dot, .phase-icon--completed {
        animation: none !important;
      }
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
  @Input() tooltip = '';

  @Output() breakpointToggle = new EventEmitter<void>();

  onRightClick(event: MouseEvent): void {
    event.preventDefault();
    this.breakpointToggle.emit();
  }

  formatDuration(ms: number): string {
    return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
  }
}
