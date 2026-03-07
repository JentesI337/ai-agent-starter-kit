import {
  ChangeDetectorRef,
  Component,
  HostListener,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { Subscription } from 'rxjs';

import { FormsModule } from '@angular/forms';

import { AgentSocketService } from '../../services/agent-socket.service';
import { AgentStateService, PolicyApprovalItem, RequestEnvelope, RoutingDecision } from '../../services/agent-state.service';
import { DebugToolbarComponent } from './debug-toolbar/debug-toolbar.component';
import { PipelineCanvasComponent } from './pipeline-canvas/pipeline-canvas.component';
import { PromptInspectorComponent } from './prompt-inspector/prompt-inspector.component';
import { EventLogComponent } from './event-log/event-log.component';
import { RequestRoutingInspectorComponent } from './request-routing-inspector/request-routing-inspector.component';
import {
  DebugEvent,
  DebugState,
  LlmCallRecord,
  PhaseState,
  PipelinePhase,
  ReflectionVerdict,
  ToolExecutionRecord,
} from './debug.types';

@Component({
  selector: 'app-debug-page',
  standalone: true,
  imports: [
    FormsModule,
    DebugToolbarComponent,
    PipelineCanvasComponent,
    PromptInspectorComponent,
    EventLogComponent,
    RequestRoutingInspectorComponent,
  ],
  templateUrl: './debug-page.component.html',
  styleUrl: './debug-page.component.scss',
})
export class DebugPageComponent implements OnInit, OnDestroy {
  // ── Projected from AgentStateService.debug$ ──────────────
  debugState: DebugState = 'idle';
  currentPhase: PipelinePhase | null = null;
  pausedAtPhase: PipelinePhase | null = null;
  phaseStates = new Map<PipelinePhase, PhaseState>();
  llmCalls: LlmCallRecord[] = [];
  toolExecutions: ToolExecutionRecord[] = [];
  reflectionVerdict: ReflectionVerdict | null = null;
  selectedPhase: PipelinePhase | null = null;
  eventLog: DebugEvent[] = [];
  requestId: string | null = null;
  totalDurationMs = 0;
  requestEnvelope: RequestEnvelope | null = null;
  routingDecision: RoutingDecision | null = null;

  // ── Local UI state ───────────────────────────────────────
  activeBreakpoints = new Set<PipelinePhase>();
  isConnected = false;
  pendingApprovals: PolicyApprovalItem[] = [];
  composerMessage = '';
  selectedAgent = '';
  selectedModel = '';

  private subs = new Subscription();

  constructor(
    private readonly socket: AgentSocketService,
    private readonly agentState: AgentStateService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.agentState.init();

    // Project shared debug snapshot → local template fields
    this.subs.add(
      this.agentState.debug$.subscribe(snap => {
        this.debugState = snap.debugState;
        this.currentPhase = snap.currentPhase;
        this.pausedAtPhase = snap.pausedAtPhase;
        this.phaseStates = snap.phaseStates;
        this.llmCalls = snap.llmCalls;
        this.toolExecutions = snap.toolExecutions;
        this.reflectionVerdict = snap.reflectionVerdict;
        this.selectedPhase = snap.selectedPhase;
        this.eventLog = snap.eventLog;
        this.requestId = snap.requestId;
        this.totalDurationMs = snap.totalDurationMs;
        this.requestEnvelope = snap.requestEnvelope;
        this.routingDecision = snap.routingDecision;
        this.cdr.detectChanges();
      })
    );

    this.subs.add(
      this.agentState.connected$.subscribe(c => this.isConnected = c)
    );
    this.subs.add(
      this.agentState.approvals$.subscribe(approvals => {
        this.pendingApprovals = approvals;
      })
    );

    if (!this.isConnected) {
      this.socket.connect('ws://localhost:8000/ws/agent');
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  // ── Actions ──────────────────────────────────────────────────

  onPlay(): void {
    this.socket.sendDebugPlay();
    this.debugState = 'running';
  }

  onPause(): void {
    this.socket.sendDebugPause();
  }

  onContinue(): void {
    if (this.debugState !== 'paused' || !this.requestId) return;
    this.socket.sendDebugContinue(this.requestId);
  }

  onBreakpointsChange(bps: Set<PipelinePhase>): void {
    this.activeBreakpoints = bps;
    this.socket.sendDebugSetBreakpoints([...bps]);
  }

  onBreakpointToggle(phase: PipelinePhase): void {
    const next = new Set(this.activeBreakpoints);
    if (next.has(phase)) {
      next.delete(phase);
    } else {
      next.add(phase);
    }
    this.onBreakpointsChange(next);
  }

  onPhaseClick(phase: PipelinePhase): void {
    this.agentState.selectDebugPhase(phase);
  }

  onSendMessage(message: string): void {
    if (!message.trim()) return;
    this.agentState.resetDebugRun();
    this.socket.sendUserMessage(message, {
      agentId: this.selectedAgent || undefined,
      model: this.selectedModel || undefined,
    });
    this.composerMessage = '';
  }

  getPhaseIndex(phase: PipelinePhase | null): number {
    if (!phase) return 0;
    const phases: PipelinePhase[] = [
      'routing', 'guardrails', 'context', 'planning',
      'tool_selection', 'synthesis', 'reflection', 'reply_shaping', 'response',
    ];
    return phases.indexOf(phase) + 1;
  }

  // ── Keyboard Shortcuts ───────────────────────────────────────

  @HostListener('document:keydown', ['$event'])
  handleKeyboard(event: KeyboardEvent): void {
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
      case ' ':
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

  // ── Approvals ────────────────────────────────────────────────

  onApprovalDecision(item: PolicyApprovalItem, decision: 'allow_once' | 'allow_session' | 'cancel'): void {
    this.agentState.sendApprovalDecision(item.approvalId, decision, item.sessionId, item.runId);
  }

}
