import { Component, EventEmitter, Input, Output } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { PhaseNodeComponent } from './phase-node.component';
import {
  DebugEvent,
  LlmCallRecord,
  PhaseDefinition,
  PhaseState,
  PipelinePhase,
  ToolExecutionRecord,
} from '../debug.types';

@Component({
  selector: 'app-pipeline-canvas',
  standalone: true,
  imports: [PhaseNodeComponent, SlicePipe],
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

  readonly phases: PhaseDefinition[] = [
    { id: 'routing',        label: 'Routing',            icon: '🔀', hasLlm: false, index: 0 },
    { id: 'guardrails',     label: 'Guardrails',         icon: '🛡',  hasLlm: false, index: 1 },
    { id: 'context',        label: 'Memory & Context',   icon: '🧠', hasLlm: false, index: 2 },
    { id: 'planning',       label: 'Planning',           icon: '📋', hasLlm: true,  index: 3 },
    { id: 'tool_selection', label: 'Tool Loop',          icon: '🔧', hasLlm: true,  index: 4 },
    { id: 'synthesis',      label: 'Synthesis',          icon: '✨', hasLlm: true,  index: 5 },
    { id: 'reflection',     label: 'Reflection',         icon: '🔍', hasLlm: true,  index: 6 },
    { id: 'reply_shaping',  label: 'Reply Shaping',      icon: '✂',  hasLlm: false, index: 7 },
    { id: 'response',       label: 'Response + Distill', icon: '📤', hasLlm: false, index: 8 },
  ];

  get agentTokenY(): number {
    if (!this.currentPhase) return 0;
    const def = this.phases.find(p => p.id === this.currentPhase);
    return def ? def.index * 76 : 0;
  }

  get agentAtLlm(): boolean {
    if (!this.currentPhase) return false;
    const def = this.phases.find(p => p.id === this.currentPhase);
    return !!def?.hasLlm && this.isLlmActive(this.currentPhase);
  }

  isLlmActive(phase: PipelinePhase): boolean {
    return this.llmCalls.some(c => c.phase === phase && !c.rawResponse);
  }

  isLlmCompleted(phase: PipelinePhase): boolean {
    return this.llmCalls.some(c => c.phase === phase && !!c.rawResponse);
  }

  isEdgeActive(phase: PhaseDefinition): boolean {
    const nextPhase = this.phases[phase.index + 1];
    if (!nextPhase) return false;
    const state = this.phaseStates.get(nextPhase.id);
    return state === 'active';
  }

  isEdgeCompleted(phase: PhaseDefinition): boolean {
    const state = this.phaseStates.get(phase.id);
    return state === 'completed';
  }

  getEdgeEvents(phaseId: PipelinePhase): DebugEvent[] {
    return this.eventLog
      .filter(e => e.details?.['phase'] === phaseId)
      .slice(-2);
  }

  getPhaseDuration(phaseId: PipelinePhase): number | null {
    const events = this.eventLog.filter(e => e.details?.['phase'] === phaseId);
    if (events.length < 2) return null;
    const start = new Date(events[0].timestamp).getTime();
    const end = new Date(events[events.length - 1].timestamp).getTime();
    return end - start || null;
  }

  getLlmCallCount(phaseId: PipelinePhase): number {
    return this.llmCalls.filter(c => c.phase === phaseId).length;
  }

  getLlmCallNumber(phaseId: PipelinePhase): number {
    return this.getLlmCallCount(phaseId) || 1;
  }

  getLlmLatency(phaseId: PipelinePhase): number | null {
    const call = this.llmCalls.find(c => c.phase === phaseId && c.latencyMs > 0);
    return call?.latencyMs ?? null;
  }
}
