import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AgentSocketService } from '../services/agent-socket.service';
import { AgentStateService, PipelinePhase } from '../services/agent-state.service';
import { LiveService, LiveEvent } from '../services/live.service';

@Component({
  selector: 'app-live-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './live-page.component.html',
  styleUrl: './live-page.component.scss',
})
export class LivePageComponent implements OnInit {
  private explicitPause = false;

  constructor(
    readonly live: LiveService,
    readonly agentState: AgentStateService,
    private readonly socket: AgentSocketService,
  ) {}

  ngOnInit(): void {
    this.socket.connect('ws://localhost:8000/ws/agent');
    this.agentState.init();
    this.live.init();
  }

  trackEvent(_index: number, event: LiveEvent): number {
    return event.id;
  }

  formatTime(ts: string): string {
    if (!ts) return '—';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString('de-DE', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  }

  phaseLabel(phase: PipelinePhase): string {
    const labels: Record<string, string> = {
      routing: 'Route', guardrails: 'Guards', context: 'Ctx',
      planning: 'Plan', tool_selection: 'Select', tool_execution: 'Exec',
      synthesis: 'Synth', reflection: 'Reflect', reply_shaping: 'Shape',
      response: 'Reply',
    };
    return labels[phase] || phase;
  }

  phaseClass(phase: PipelinePhase): string {
    return `phase-${this.live.phaseStates.get(phase) || 'idle'}`;
  }

  togglePause(): void {
    if (this.live.paused) {
      this.live.resume();
      this.explicitPause = false;
    } else {
      this.live.pause();
      this.explicitPause = true;
    }
  }

  onFeedScroll(el: HTMLElement): void {
    if (this.explicitPause) return;
    if (el.scrollTop > 30 && !this.live.paused) {
      this.live.pause();
    } else if (el.scrollTop < 5 && this.live.paused) {
      this.live.resume();
    }
  }

  stageIcon(stage: string): string {
    if (stage.includes('started') || stage === 'run_started') return '▶';
    if (stage.includes('completed')) return '✓';
    if (stage.includes('failed') || stage.includes('error')) return '✕';
    if (stage.includes('dispatched')) return '→';
    if (stage.includes('passed')) return '✓';
    if (stage.includes('cancelled')) return '■';
    return '·';
  }
}
