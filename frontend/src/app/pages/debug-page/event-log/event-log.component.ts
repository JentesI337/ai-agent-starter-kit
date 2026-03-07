import { Component, Input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DebugEvent } from '../debug.types';

@Component({
  selector: 'app-event-log',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="event-log" role="log" aria-label="Debug Event Log">
      <div class="log-header">
        <span class="log-title">Event Log</span>
        <input class="log-filter"
               type="text"
               placeholder="Filter events…"
               [ngModel]="filterText"
               (ngModelChange)="filterText = $event"
               aria-label="Events filtern">
        <span class="log-count">{{ filteredEvents.length }} events</span>
      </div>
      <div class="log-list">
        @if (truncatedCount > 0) {
          <div class="log-truncated">{{ truncatedCount }} ältere Events ausgeblendet</div>
        }
        @for (event of visibleEvents; track $index) {
          <div class="log-entry"
               [class.log--error]="event.level === 'error'"
               [class.log--warn]="event.level === 'warn'">
            <span class="log-time">{{ formatTime(event.timestamp) }}</span>
            <span class="log-stage"
                  [class.stage--error]="event.level === 'error'">
              {{ event.stage }}
            </span>
            @if (event.details?.['phase']) {
              <span class="log-phase">{{ event.details?.['phase'] }}</span>
            }
          </div>
        }
        @if (filteredEvents.length === 0) {
          <div class="log-empty">Keine Events</div>
        }
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; flex-shrink: 0; }

    .event-log {
      max-height: 160px;
      display: flex;
      flex-direction: column;
      border-top: 1px solid var(--c-border);
      background: var(--c-bg-deep);
    }

    .log-header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 6px 16px;
      border-bottom: 1px solid var(--c-border);
      flex-shrink: 0;
    }

    .log-title {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--c-text-dim);
    }

    .log-filter {
      flex: 1;
      max-width: 240px;
      padding: 3px 8px;
      font-size: 11px;
      background: var(--c-bg);
      border: 1px solid var(--c-border);
      border-radius: var(--r-sm);
      color: var(--c-text);

      &:focus { outline: none; border-color: var(--c-border-focus); }
    }

    .log-count {
      font-size: 10px;
      color: var(--c-text-muted);
      font-variant-numeric: tabular-nums;
      margin-left: auto;
    }

    .log-list {
      flex: 1;
      overflow-y: auto;
      padding: 4px 0;
    }

    .log-entry {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 2px 16px;
      font-size: 11px;
      color: var(--c-text-dim);

      &:hover { background: var(--c-surface); }

      &.log--error { color: var(--c-red); }
      &.log--warn { color: var(--c-yellow); }
    }

    .log-time {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      color: var(--c-text-muted);
      font-variant-numeric: tabular-nums;
      flex-shrink: 0;
    }

    .log-stage {
      font-weight: 500;
      &.stage--error { color: var(--c-red); }
    }

    .log-phase {
      font-size: 10px;
      padding: 1px 6px;
      background: var(--c-surface-2);
      border-radius: var(--r-sm);
      color: var(--c-text-muted);
    }

    .log-empty {
      padding: 16px;
      text-align: center;
      color: var(--c-text-muted);
      font-size: 12px;
    }

    .log-truncated {
      padding: 4px 16px;
      text-align: center;
      color: var(--c-text-muted);
      font-size: 10px;
      border-bottom: 1px dashed var(--c-border);
    }
  `]
})
export class EventLogComponent {
  @Input() events: DebugEvent[] = [];

  private static readonly MAX_RENDERED = 500;

  filterText = '';

  get filteredEvents(): DebugEvent[] {
    let result = this.events;
    if (this.filterText) {
      const q = this.filterText.toLowerCase();
      result = result.filter(e =>
        e.stage.toLowerCase().includes(q) ||
        (e.details?.['phase'] as string)?.toLowerCase()?.includes(q)
      );
    }
    return result;
  }

  get visibleEvents(): DebugEvent[] {
    const all = this.filteredEvents;
    if (all.length <= EventLogComponent.MAX_RENDERED) return all;
    return all.slice(all.length - EventLogComponent.MAX_RENDERED);
  }

  get truncatedCount(): number {
    const all = this.filteredEvents;
    return Math.max(0, all.length - EventLogComponent.MAX_RENDERED);
  }

  formatTime(iso: string): string {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
    } catch {
      return iso;
    }
  }
}
