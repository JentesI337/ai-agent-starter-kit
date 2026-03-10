import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  HostListener,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { JsonPipe } from '@angular/common';
import { Subscription } from 'rxjs';

import { AgentSocketService } from '../../services/agent-socket.service';
import {
  AgentStateService,
  DebugEvent,
  DebugState,
  GuardrailCheck,
  LlmCallRecord,
  PhaseState,
  PipelinePhase,
  PolicyApprovalItem,
  ReflectionVerdict,
  RequestEnvelope,
  RoutingDecision,
  ToolExecutionRecord,
  ToolPolicyInfo,
  ToolchainInfo,
  McpToolsInfo,
} from '../../services/agent-state.service';

interface PhaseNode {
  id: PipelinePhase;
  label: string;
  short: string;
  icon: string;
  hasLlm: boolean;
}

type InspectorTab = 'system' | 'user' | 'response' | 'tools' | 'reflection' | 'overrides';

@Component({
  selector: 'app-debug-page',
  standalone: true,
  imports: [FormsModule, JsonPipe],
  templateUrl: './debug-page.component.html',
  styleUrl: './debug-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DebugPageComponent implements OnInit, OnDestroy {

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

  // Run metadata
  requestEnvelope: RequestEnvelope | null = null;
  routingDecision: RoutingDecision | null = null;
  guardrailChecks: GuardrailCheck[] = [];
  toolPolicy: ToolPolicyInfo | null = null;
  toolchainInfo: ToolchainInfo | null = null;
  mcpToolsInfo: McpToolsInfo | null = null;

  activeBreakpoints = new Set<PipelinePhase>();
  isConnected = false;
  pendingApprovals: PolicyApprovalItem[] = [];
  composerMessage = '';
  activeTab: InspectorTab = 'system';
  eventLogOpen = false;
  filterText = '';
  inspectorOpen = false;
  summaryOpen = true;

  readonly phases: PhaseNode[] = [
    { id: 'routing',        label: 'Routing',          short: 'Route',   icon: '◈', hasLlm: false },
    { id: 'guardrails',     label: 'Guardrails',       short: 'Guard',   icon: '⬡', hasLlm: false },
    { id: 'context',        label: 'Memory & Context', short: 'Context', icon: '◉', hasLlm: false },
    { id: 'agent_loop',     label: 'Agent Loop',       short: 'Agent',   icon: '⟳', hasLlm: true },
    { id: 'reflection',     label: 'Reflection',       short: 'Reflect', icon: '◎', hasLlm: true },
    { id: 'reply_shaping',  label: 'Reply Shaping',    short: 'Shape',   icon: '◇', hasLlm: false },
    { id: 'response',       label: 'Response',         short: 'Reply',   icon: '▣', hasLlm: false },
  ];

  private subs = new Subscription();

  constructor(
    private readonly socket: AgentSocketService,
    private readonly agentState: AgentStateService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.agentState.init();

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
        this.guardrailChecks = snap.guardrailChecks;
        this.toolPolicy = snap.toolPolicy;
        this.toolchainInfo = snap.toolchainInfo;
        this.mcpToolsInfo = snap.mcpToolsInfo;
        if (snap.selectedPhase && !this.inspectorOpen) this.inspectorOpen = true;
        this.cdr.markForCheck();
      }),
    );

    this.subs.add(this.agentState.connected$.subscribe(c => { this.isConnected = c; this.cdr.markForCheck(); }));
    this.subs.add(this.agentState.approvals$.subscribe(a => { this.pendingApprovals = a; this.cdr.markForCheck(); }));

    // Socket connection is handled by root App component — no connect() here
  }

  ngOnDestroy(): void { this.subs.unsubscribe(); }

  // ── Actions ──────────────────────────────────────

  onPlay(): void { this.socket.sendDebugPlay(); this.debugState = 'running'; }
  onPause(): void { this.socket.sendDebugPause(); }

  onContinue(): void {
    if (this.debugState !== 'paused' || !this.requestId) return;
    this.socket.sendDebugContinue(this.requestId);
  }

  selectPhase(phase: PipelinePhase): void {
    this.agentState.selectDebugPhase(phase);
    this.inspectorOpen = true;
    this.selectedPhase = phase;
  }

  toggleBreakpoint(phase: PipelinePhase, ev?: MouseEvent): void {
    ev?.preventDefault();
    ev?.stopPropagation();
    const next = new Set(this.activeBreakpoints);
    next.has(phase) ? next.delete(phase) : next.add(phase);
    this.activeBreakpoints = next;
    this.socket.sendDebugSetBreakpoints([...next]);
  }

  onSendMessage(): void {
    const msg = this.composerMessage.trim();
    if (!msg) return;
    this.agentState.resetDebugRun();
    this.socket.sendUserMessage(msg, {});
    this.composerMessage = '';
  }

  onApprovalDecision(item: PolicyApprovalItem, decision: 'allow_once' | 'allow_session' | 'cancel'): void {
    this.agentState.sendApprovalDecision(item.approvalId, decision, item.sessionId, item.runId);
  }

  // ── Helpers ──────────────────────────────────────

  ps(id: PipelinePhase): PhaseState { return this.phaseStates.get(id) || 'idle'; }

  get selectedNode(): PhaseNode | undefined {
    return this.phases.find(p => p.id === this.selectedPhase);
  }

  get selectedLlmCalls(): LlmCallRecord[] {
    if (!this.selectedPhase) return this.llmCalls;
    return this.llmCalls.filter(c => c.phase === this.selectedPhase);
  }

  get hasRunData(): boolean {
    return this.eventLog.length > 0 || this.debugState !== 'idle';
  }

  get totalTokens(): number {
    return this.llmCalls.reduce((sum, c) => sum + (c.tokensEst || 0), 0);
  }

  get totalLlmLatency(): number {
    return this.llmCalls.reduce((sum, c) => sum + (c.latencyMs || 0), 0);
  }

  callContent(call: LlmCallRecord): string {
    switch (this.activeTab) {
      case 'system': return call.systemPrompt;
      case 'user': return call.userPrompt;
      case 'response': return call.rawResponse;
      default: return '';
    }
  }

  llmCount(id: PipelinePhase): number {
    return this.llmCalls.filter(c => c.phase === id).length;
  }

  toolCount(id: PipelinePhase): number {
    if (id !== 'agent_loop') return 0;
    return this.toolExecutions.length;
  }

  phaseDur(id: PipelinePhase): number | null {
    const M: Record<string, [string, string]> = {
      routing: ['run_started', 'request_dispatched'],
      guardrails: ['request_dispatched', 'guardrails_passed'],
      context: ['guardrails_passed', 'loop_iteration_started'],
      agent_loop: ['loop_iteration_started', 'llm_call_completed'],
      reflection: ['reflection_completed', 'reflection_completed'],
      reply_shaping: ['reply_shaping_started', 'reply_shaping_completed'],
      response: ['reply_shaping_completed', 'request_completed'],
    };
    const p = M[id];
    if (!p) return null;
    const s = this.eventLog.find(e => e.stage === p[0]);
    const e = [...this.eventLog].reverse().find(ev => ev.stage === p[1]);
    if (!s || !e) return null;
    const ms = new Date(e.timestamp).getTime() - new Date(s.timestamp).getTime();
    return ms > 0 ? ms : null;
  }

  get filteredEvents(): DebugEvent[] {
    if (!this.filterText) return this.eventLog;
    const q = this.filterText.toLowerCase();
    return this.eventLog.filter(e =>
      e.stage.toLowerCase().includes(q) ||
      (e.details?.['phase'] as string)?.toLowerCase()?.includes(q),
    );
  }

  fmtDur(ms: number | null | undefined): string {
    if (ms == null) return '';
    return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
  }

  fmtTime(iso: string): string {
    try {
      return new Date(iso).toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      });
    } catch { return iso; }
  }

  async copyText(text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
  }

  @HostListener('document:keydown', ['$event'])
  handleKey(e: KeyboardEvent): void {
    const t = (e.target as HTMLElement).tagName;
    if (t === 'TEXTAREA' || t === 'INPUT') return;
    if (e.key === 'F5') { e.preventDefault(); this.onPlay(); }
    else if (e.key === 'F6') { e.preventDefault(); this.onPause(); }
    else if (e.key === 'F8' || e.key === ' ') { e.preventDefault(); this.onContinue(); }
    else if (e.key === 'Escape') { this.inspectorOpen = false; this.cdr.markForCheck(); }
  }
}
