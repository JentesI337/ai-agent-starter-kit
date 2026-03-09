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
    { id: 'agent_loop',     label: 'Agent Loop',         icon: '🔄', hasLlm: true,  index: 3 },
    { id: 'reflection',     label: 'Reflection',         icon: '🔍', hasLlm: true,  index: 4 },
    { id: 'reply_shaping',  label: 'Reply Shaping',      icon: '✂',  hasLlm: false, index: 5 },
    { id: 'response',       label: 'Response + Distill', icon: '📤', hasLlm: false, index: 6 },
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

  private static readonly PHASE_EVENTS: Record<string, [string, string]> = {
    routing:        ['run_started',             'guardrails_passed'],
    guardrails:     ['run_started',             'guardrails_passed'],
    context:        ['memory_updated',          'planning_started'],
    agent_loop:     ['planning_started',        'reflection_completed'],
    reflection:     ['reflection_completed',    'reflection_completed'],
    reply_shaping:  ['reply_shaping_started',   'reply_shaping_completed'],
    response:       ['reply_shaping_completed', 'run_completed'],
  };

  getEdgeEvents(phaseId: PipelinePhase): DebugEvent[] {
    return this.eventLog
      .filter(e => e.details?.['phase'] === phaseId)
      .slice(-2);
  }

  getPhaseDuration(phaseId: PipelinePhase): number | null {
    const pair = PipelineCanvasComponent.PHASE_EVENTS[phaseId];
    if (!pair) return null;
    const [startStage, endStage] = pair;
    if (startStage === endStage) return null;
    const startEvt = this.eventLog.find(e => e.stage === startStage);
    const endEvt = [...this.eventLog].reverse().find(e => e.stage === endStage);
    if (!startEvt || !endEvt) return null;
    const ms = new Date(endEvt.timestamp).getTime() - new Date(startEvt.timestamp).getTime();
    return ms > 0 ? ms : null;
  }

  getPhaseTooltip(phaseId: PipelinePhase): string {
    const pair = PipelineCanvasComponent.PHASE_EVENTS[phaseId];
    if (!pair) return '';
    const [startStage, endStage] = pair;
    const startEvt = this.eventLog.find(e => e.stage === startStage);
    const endEvt = [...this.eventLog].reverse().find(e => e.stage === endStage);
    const parts: string[] = [];
    if (startEvt) parts.push('Start: ' + startEvt.timestamp);
    if (endEvt && endEvt !== startEvt) parts.push('End: ' + endEvt.timestamp);
    const dur = this.getPhaseDuration(phaseId);
    if (dur !== null) parts.push('Dauer: ' + (dur < 1000 ? dur + 'ms' : (dur / 1000).toFixed(1) + 's'));
    const llm = this.getLlmCallCount(phaseId);
    if (llm > 0) parts.push('LLM Calls: ' + llm);
    return parts.join('\n');
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
