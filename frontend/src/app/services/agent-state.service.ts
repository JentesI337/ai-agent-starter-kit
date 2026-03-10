import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';

import { AgentSocketEvent, AgentSocketService } from './agent-socket.service';
import { PolicyApprovalRecord } from './agents.service';

// ── Shared types ──────────────────────────────────────────────

export type RunStatus = 'idle' | 'running' | 'waiting_clarification' | 'completed' | 'failed';

export interface PolicyApprovalItem {
  approvalId: string;
  runId: string;
  sessionId: string;
  agentName: string;
  tool: string;
  resource: string;
  displayText: string;
  options: string[];
  selectedOption: string;
  status: 'pending' | 'approved' | 'expired' | 'denied' | 'cancelled';
  createdAt: string;
  updatedAt: string;
}

export interface ActiveRun {
  requestId: string;
  sessionId: string;
  agentId: string;
  status: RunStatus;
  startedAt: string;
}

export interface LifecycleEntry {
  time: string;
  type: string;
  text: string;
  details?: Record<string, unknown>;
}

// ── Debug types (kept here so they persist across route changes) ──

export type DebugState = 'idle' | 'running' | 'paused' | 'completed' | 'error';
export type PipelinePhase =
  | 'routing' | 'guardrails' | 'context' | 'agent_loop'
  | 'reflection' | 'reply_shaping' | 'response';
export type PhaseState = 'idle' | 'active' | 'paused' | 'completed' | 'error' | 'skipped';

export interface LlmCallRecord {
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

export interface ToolExecutionRecord {
  tool: string;
  args: Record<string, unknown>;
  resultPreview: string;
  durationMs: number;
  exitCode: number;
  blocked: boolean;
  timestamp: string;
}

export interface ReflectionVerdict {
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

export interface DebugEvent {
  stage: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  details?: Record<string, unknown>;
}

export interface RequestEnvelope {
  type: string;
  contentLength: number;
  agentOverride: string | null;
  modelOverride: string | null;
  preset: string | null;
  promptMode: string | null;
  queueMode: string | null;
  reasoningLevel: string | null;
  reasoningVisibility: string | null;
  sessionId: string | null;
  requestId: string | null;
}

export interface RoutingMatch {
  agentId: string;
  score: number;
  matchedCapabilities: string[];
}

export interface RoutingDecision {
  requestedAgentId: string;
  effectiveAgentId: string;
  routingReason: string | null;
  routingMethod: 'explicit' | 'preset' | 'capability_matching' | 'default';
  routingCapabilities: string[];
  routingMatches: RoutingMatch[];
}

export interface GuardrailCheck {
  name: string;
  passed: boolean;
  actualValue: string | number;
  limit?: string | number;
  reason?: string;
}

export interface ToolPolicyInfo {
  policyType: string;
  allowedTools: string[];
  deniedTools: string[];
}

export interface ToolchainInfo {
  toolCount: number;
  issues: number;
}

export interface McpToolsInfo {
  toolCount: number;
  error?: string;
}

export interface DebugSnapshot {
  debugState: DebugState;
  currentPhase: PipelinePhase | null;
  pausedAtPhase: PipelinePhase | null;
  phaseStates: Map<PipelinePhase, PhaseState>;
  llmCalls: LlmCallRecord[];
  toolExecutions: ToolExecutionRecord[];
  reflectionVerdict: ReflectionVerdict | null;
  selectedPhase: PipelinePhase | null;
  eventLog: DebugEvent[];
  requestId: string | null;
  runStartTime: number | null;
  totalDurationMs: number;
  requestEnvelope: RequestEnvelope | null;
  routingDecision: RoutingDecision | null;
  guardrailChecks: GuardrailCheck[];
  toolPolicy: ToolPolicyInfo | null;
  toolchainInfo: ToolchainInfo | null;
  mcpToolsInfo: McpToolsInfo | null;
}

// ── Chat types (kept here so they persist across route changes) ──

export interface ChatLine {
  role: 'user' | 'agent' | 'system';
  text: string;
  policyAction?: {
    approvalId: string;
    runId: string;
    sessionId: string;
    tool: string;
    resource: string;
    dropdownAction: '' | 'cancel' | 'allow_session';
    busy: boolean;
    resolved: boolean;
  };
}

// ── Service ───────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class AgentStateService implements OnDestroy {

  // ── Connection ────────────────────────────────────────
  private readonly _connected = new BehaviorSubject<boolean>(false);
  readonly connected$ = this._connected.asObservable();

  // ── Active Run ────────────────────────────────────────
  private readonly _activeRun = new BehaviorSubject<ActiveRun | null>(null);
  readonly activeRun$ = this._activeRun.asObservable();

  // ── Lifecycle stream (all processed events) ───────────
  private readonly _lifecycle = new BehaviorSubject<LifecycleEntry | null>(null);
  readonly lifecycle$ = this._lifecycle.asObservable();

  // ── Policy Approvals ──────────────────────────────────
  private readonly _approvals = new BehaviorSubject<PolicyApprovalItem[]>([]);
  readonly approvals$ = this._approvals.asObservable();

  // ── Debug state (persists across page switches) ───────
  private readonly _debug = new BehaviorSubject<DebugSnapshot>({
    debugState: 'idle',
    currentPhase: null,
    pausedAtPhase: null,
    phaseStates: new Map(),
    llmCalls: [],
    toolExecutions: [],
    reflectionVerdict: null,
    selectedPhase: null,
    eventLog: [],
    requestId: null,
    runStartTime: null,
    totalDurationMs: 0,
    requestEnvelope: null,
    routingDecision: null,
    guardrailChecks: [],
    toolPolicy: null,
    toolchainInfo: null,
    mcpToolsInfo: null,
  });
  readonly debug$ = this._debug.asObservable();

  // ── Clarification ─────────────────────────────────────
  private readonly _clarification = new BehaviorSubject<string | null>(null);
  readonly clarification$ = this._clarification.asObservable();

  // ── Chat lines (persist across route changes) ────────
  private readonly _chatLines = new BehaviorSubject<ChatLine[]>([]);
  readonly chatLines$ = this._chatLines.asObservable();

  // ── Lifecycle lines (persist across route changes) ────
  private readonly _lifecycleLines = new BehaviorSubject<LifecycleEntry[]>([]);
  readonly lifecycleLines$ = this._lifecycleLines.asObservable();

  // ── Active assistant index for token streaming ────────
  private _activeAssistantIndex: number | null = null;

  // ── Raw event passthrough (for page-specific logic) ───
  private readonly _event = new BehaviorSubject<AgentSocketEvent | null>(null);
  readonly event$ = this._event.asObservable();

  // ── Session tracking ──────────────────────────────────
  private _sessionId = '';
  get sessionId(): string { return this._sessionId; }

  private readonly subs = new Subscription();
  private initialized = false;

  constructor(private readonly socket: AgentSocketService) {}

  /**
   * Bind to socket streams. Called once by the first component that bootstraps
   * the connection (typically app-level or chat-page). Idempotent.
   */
  init(): void {
    if (this.initialized) return;
    this.initialized = true;

    this.subs.add(
      this.socket.connected$.subscribe(c => this._connected.next(c))
    );

    this.subs.add(
      this.socket.events$.subscribe(event => {
        if (!event) return;
        this.processEvent(event);
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  // ── Public helpers ────────────────────────────────────

  get approvals(): PolicyApprovalItem[] {
    return this._approvals.value;
  }

  get activeRun(): ActiveRun | null {
    return this._activeRun.value;
  }

  get connected(): boolean {
    return this._connected.value;
  }

  setSessionId(id: string): void {
    this._sessionId = id;
  }

  // ── Chat line mutations ───────────────────────────────

  get chatLines(): ChatLine[] {
    return this._chatLines.value;
  }

  get activeAssistantIndex(): number | null {
    return this._activeAssistantIndex;
  }

  pushChatLine(line: ChatLine): void {
    this._chatLines.next([...this._chatLines.value, line]);
  }

  appendTokenToAssistant(token: string): void {
    const lines = [...this._chatLines.value];
    if (this._activeAssistantIndex === null) {
      lines.push({ role: 'agent', text: '' });
      this._activeAssistantIndex = lines.length - 1;
    }
    lines[this._activeAssistantIndex] = {
      ...lines[this._activeAssistantIndex],
      text: lines[this._activeAssistantIndex].text + token,
    };
    this._chatLines.next(lines);
  }

  finalizeAssistantMessage(message: string): void {
    const lines = [...this._chatLines.value];
    // Remove "Agent is working..." placeholder
    const workingIdx = lines.findIndex(l => l.role === 'system' && l.text === 'Agent is working...');
    if (workingIdx >= 0) lines.splice(workingIdx, 1);

    if (this._activeAssistantIndex !== null) {
      // Tokens were streaming — update with final message if provided
      const idx = workingIdx >= 0 && workingIdx < this._activeAssistantIndex
        ? this._activeAssistantIndex - 1
        : this._activeAssistantIndex;
      if (message && idx >= 0 && idx < lines.length) {
        lines[idx] = { ...lines[idx], text: message };
      }
      this._chatLines.next(lines);
    } else {
      // No streaming happened — push the final message directly
      if (message) {
        lines.push({ role: 'agent', text: message });
      }
      this._chatLines.next(lines);
    }
    this._activeAssistantIndex = null;
  }

  resetActiveAssistant(): void {
    if (this._activeAssistantIndex !== null) {
      const lines = this._chatLines.value;
      const partial = lines[this._activeAssistantIndex]?.text ?? '';
      if (!partial.trim()) {
        const updated = [...lines];
        updated.splice(this._activeAssistantIndex, 1);
        this._chatLines.next(updated);
      }
      this._activeAssistantIndex = null;
    }
  }

  updateChatLineInPlace(index: number, mutator: (line: ChatLine) => ChatLine): void {
    const lines = [...this._chatLines.value];
    if (index >= 0 && index < lines.length) {
      lines[index] = mutator(lines[index]);
      this._chatLines.next(lines);
    }
  }

  updateChatLinesByApproval(approvalId: string, mutator: (line: ChatLine) => ChatLine): void {
    const lines = this._chatLines.value;
    let changed = false;
    const updated = lines.map(line => {
      if (line.policyAction?.approvalId === approvalId) {
        changed = true;
        return mutator(line);
      }
      return line;
    });
    if (changed) {
      this._chatLines.next(updated);
    }
  }

  resolveInlinePolicyActionsByRequest(requestId: string): void {
    if (!requestId) return;
    const lines = this._chatLines.value;
    let changed = false;
    const updated = lines.map(line => {
      if (line.policyAction?.runId === requestId && !line.policyAction.resolved) {
        changed = true;
        return { ...line, policyAction: { ...line.policyAction, resolved: true, busy: false } };
      }
      return line;
    });
    if (changed) {
      this._chatLines.next(updated);
    }
  }

  clearChatLines(): void {
    this._chatLines.next([]);
    this._activeAssistantIndex = null;
  }

  pushLifecycleLine(entry: LifecycleEntry): void {
    const list = [entry, ...this._lifecycleLines.value];
    this._lifecycleLines.next(list.length > 500 ? list.slice(0, 500) : list);
  }

  clearLifecycleLines(): void {
    this._lifecycleLines.next([]);
  }

  // ── Approval mutations ────────────────────────────────

  sendApprovalDecision(
    approvalId: string,
    decision: 'allow_once' | 'allow_session' | 'cancel',
    sessionId: string,
    runId: string
  ): void {
    this.socket.sendPolicyDecision(approvalId, decision, { sessionId, requestId: runId });
  }

  updateApprovalSelection(approvalId: string, option: string): void {
    const list = this._approvals.value.map(a =>
      a.approvalId === approvalId ? { ...a, selectedOption: option } : a
    );
    this._approvals.next(list);
  }

  refreshApprovalsFromRecords(records: PolicyApprovalRecord[]): void {
    this._approvals.next(records.map(r => this.mapRecord(r)));
  }

  // ── Event processing ─────────────────────────────────

  private processEvent(event: AgentSocketEvent): void {
    // Always forward the raw event for page-specific consumers
    this._event.next(event);

    // Track session id
    if (event.session_id) {
      this._sessionId = event.session_id;
    }

    const ts = event.ts ?? new Date().toISOString();

    // ── Run lifecycle ───────────────────────────────────

    if (event.type === 'lifecycle') {
      const stage = event.stage ?? '';

      this._lifecycle.next({
        time: ts,
        type: stage || event.type,
        text: this.describeEvent(event),
        details: event.details,
      });

      // Run tracking
      if (stage === 'request_started' || stage === 'run_started') {
        this._activeRun.next({
          requestId: event.request_id ?? '',
          sessionId: event.session_id ?? this._sessionId,
          agentId: event.agent ?? '',
          status: 'running',
          startedAt: ts,
        });
        this._clarification.next(null);
      }

      if (stage === 'request_completed' || stage === 'run_completed') {
        const run = this._activeRun.value;
        if (run) {
          this._activeRun.next({ ...run, status: 'completed' });
        }
        this.resolveApprovalsByRequest(event.request_id ?? '');
      }

      if (stage === 'request_cancelled' || (stage ?? '').startsWith('request_failed')) {
        const run = this._activeRun.value;
        if (run) {
          this._activeRun.next({ ...run, status: 'failed' });
        }
        this.resolveApprovalsByRequest(event.request_id ?? '');
      }

      if (stage === 'policy_approval_decision_rejected') {
        const approvalId = String((event.details as Record<string, unknown> | undefined)?.['approval_id'] ?? '').trim();
        if (approvalId) {
          this.setApprovalBusy(approvalId, false);
        }
      }
    }

    // ── Clarification ───────────────────────────────────

    if (event.type === 'clarification_needed') {
      this._clarification.next(event.message ?? 'Could you clarify your request?');
      const run = this._activeRun.value;
      if (run) {
        this._activeRun.next({ ...run, status: 'waiting_clarification' });
      }
    }

    // ── Policy approvals ────────────────────────────────

    if (event.type === 'policy_approval_required') {
      this.handleApprovalRequired(event);
    }

    if (event.type === 'policy_approval_updated') {
      this.handleApprovalUpdated(event);
    }

    // ── Debug pipeline state ────────────────────────────
    this.applyDebugEvent(event);
  }

  // ── Approval event handlers ───────────────────────────

  private handleApprovalRequired(event: AgentSocketEvent): void {
    const approval = event.approval;
    const approvalId = approval?.approval_id;
    if (!approvalId) return;

    const options = (approval?.options ?? ['allow_once']).map(o => String(o).toLowerCase());
    const selectedOption = options.includes('allow_once') ? 'allow_once' : options[0] || 'allow_once';
    const displayText = String(approval?.display_text ?? event.message ?? 'Approval required.');

    const item: PolicyApprovalItem = {
      approvalId,
      runId: String(event.request_id ?? ''),
      sessionId: String(event.session_id ?? ''),
      agentName: String(event.agent ?? ''),
      tool: String(approval?.tool ?? 'unknown'),
      resource: String(approval?.resource ?? ''),
      displayText,
      options,
      selectedOption,
      status: 'pending',
      createdAt: event.ts ?? new Date().toISOString(),
      updatedAt: event.ts ?? new Date().toISOString(),
    };

    const list = [...this._approvals.value];
    const idx = list.findIndex(a => a.approvalId === approvalId);
    if (idx >= 0) {
      list[idx] = item;
    } else {
      list.unshift(item);
    }
    this._approvals.next(list);
  }

  private handleApprovalUpdated(event: AgentSocketEvent): void {
    const approval = event.approval as PolicyApprovalRecord | undefined;
    const approvalId = String(approval?.approval_id ?? '');
    if (!approvalId) return;

    const updated = this.mapRecord(approval!);
    const list = [...this._approvals.value];
    const idx = list.findIndex(a => a.approvalId === approvalId);
    if (idx >= 0) {
      list[idx] = { ...updated, options: list[idx].options, selectedOption: list[idx].selectedOption };
    } else {
      list.unshift(updated);
    }
    this._approvals.next(list);
  }

  private resolveApprovalsByRequest(requestId: string): void {
    if (!requestId) return;
    const list = this._approvals.value.map(a =>
      a.runId === requestId && a.status === 'pending' ? { ...a, status: 'cancelled' as const } : a
    );
    this._approvals.next(list);
  }

  private setApprovalBusy(approvalId: string, _busy: boolean): void {
    // busy state is view-layer concern; this just ensures the pending flag is not stale
    const list = this._approvals.value;
    const idx = list.findIndex(a => a.approvalId === approvalId);
    if (idx >= 0 && list[idx].status !== 'pending') {
      return; // already resolved
    }
  }

  // ── Mapping ───────────────────────────────────────────

  private mapRecord(record: PolicyApprovalRecord): PolicyApprovalItem {
    const raw = String(record.status ?? 'pending').toLowerCase();
    const status: PolicyApprovalItem['status'] =
      raw === 'approved' ? 'approved'
        : raw === 'expired' ? 'expired'
          : raw === 'denied' ? 'denied'
            : raw === 'cancelled' ? 'cancelled'
              : 'pending';

    return {
      approvalId: String(record.approval_id),
      runId: String(record.run_id ?? ''),
      sessionId: String(record.session_id ?? ''),
      agentName: String(record.agent_name ?? 'agent'),
      tool: String(record.tool ?? 'unknown'),
      resource: String(record.resource ?? ''),
      displayText: String(record.display_text ?? 'Approval required.'),
      options: ['allow_once', 'allow_session', 'cancel'],
      selectedOption: 'allow_once',
      status,
      createdAt: String(record.created_at ?? new Date().toISOString()),
      updatedAt: String(record.updated_at ?? new Date().toISOString()),
    };
  }

  private describeEvent(event: AgentSocketEvent): string {
    if (event.message) return event.message;
    if (event.stage) return event.stage;
    return event.type;
  }

  // ── Debug pipeline ────────────────────────────────────

  get debugSnapshot(): DebugSnapshot {
    return this._debug.value;
  }

  selectDebugPhase(phase: PipelinePhase): void {
    this.patchDebug({ selectedPhase: phase });
  }

  resetDebugRun(): void {
    this._debug.next({
      debugState: 'idle',
      currentPhase: null,
      pausedAtPhase: null,
      phaseStates: new Map(),
      llmCalls: [],
      toolExecutions: [],
      reflectionVerdict: null,
      selectedPhase: null,
      eventLog: [],
      requestId: null,
      runStartTime: null,
      totalDurationMs: 0,
      requestEnvelope: null,
      routingDecision: null,
      guardrailChecks: [],
      toolPolicy: null,
      toolchainInfo: null,
      mcpToolsInfo: null,
    });
  }

  private patchDebug(partial: Partial<DebugSnapshot>): void {
    this._debug.next({ ...this._debug.value, ...partial });
  }

  private applyDebugEvent(event: AgentSocketEvent): void {
    const d = this._debug.value;

    // Always log to event log
    const newLog: DebugEvent = {
      stage: event.stage ?? event.type,
      timestamp: event.ts ?? new Date().toISOString(),
      level: event.type === 'error' ? 'error' : 'info',
      details: event as unknown as Record<string, unknown>,
    };
    const eventLog = [...d.eventLog, newLog];

    // Track request_id
    const requestId = event.request_id ?? d.requestId;

    // ── Policy approval events ──────────────────────────
    if (event.type === 'policy_approval_required') {
      this._debug.next({
        ...d,
        eventLog, requestId,
        debugState: 'paused',
        pausedAtPhase: d.currentPhase,
        phaseStates: d.currentPhase
          ? new Map(d.phaseStates).set(d.currentPhase, 'paused')
          : d.phaseStates,
      });
      return;
    }
    if (event.type === 'policy_approval_updated') {
      const status = String((event.approval as { status?: string } | undefined)?.status ?? '');
      if (status !== 'pending' && d.debugState === 'paused') {
        this._debug.next({
          ...d,
          eventLog, requestId,
          debugState: 'running',
          pausedAtPhase: null,
          phaseStates: d.pausedAtPhase
            ? new Map(d.phaseStates).set(d.pausedAtPhase, 'active')
            : d.phaseStates,
        });
      } else {
        this.patchDebug({ eventLog, requestId });
      }
      return;
    }

    // ── Stage-based routing (lifecycle events) ──────────
    const stage = event.stage;
    const details = event.details ?? {};
    let next: Partial<DebugSnapshot> = { eventLog, requestId };

    switch (stage) {
      case 'run_started':
      case 'request_started':
        next = {
          ...next,
          debugState: 'running',
          runStartTime: Date.now(),
          ...this.activatePhasePartial(d, 'routing'),
        };
        break;

      case 'request_dispatched': {
        const routingReason = (details['routing_reason'] as string) ?? null;
        const requestedId = (details['requested_agent_id'] as string) ?? '';
        const effectiveId = (details['effective_agent_id'] as string) ?? '';

        let routingMethod: RoutingDecision['routingMethod'] = 'default';
        if (routingReason?.endsWith('_intent') || routingReason === 'capability_match') {
          routingMethod = 'capability_matching';
        } else if (routingReason?.startsWith('preset_')) {
          routingMethod = 'preset';
        } else if (requestedId && requestedId !== effectiveId && !routingReason) {
          routingMethod = 'explicit';
        }

        const rawMatches = Array.isArray(details['routing_matches'])
          ? details['routing_matches'] as Array<Record<string, unknown>>
          : [];

        next = {
          ...next,
          requestEnvelope: {
            type: 'user_message',
            contentLength: Number(details['content_length'] ?? 0),
            agentOverride: requestedId || null,
            modelOverride: (details['model'] as string) || null,
            preset: (details['preset'] as string) || null,
            promptMode: (details['prompt_mode'] as string) || null,
            queueMode: (details['queue_mode'] as string) || null,
            reasoningLevel: (details['reasoning_level'] as string) || null,
            reasoningVisibility: (details['reasoning_visibility'] as string) || null,
            sessionId: event.session_id ?? d.requestId,
            requestId: requestId,
          },
          routingDecision: {
            requestedAgentId: requestedId,
            effectiveAgentId: effectiveId,
            routingReason,
            routingMethod,
            routingCapabilities: Array.isArray(details['routing_capabilities'])
              ? (details['routing_capabilities'] as string[])
              : [],
            routingMatches: rawMatches.map(m => ({
              agentId: String(m['agent_id'] ?? ''),
              score: Number(m['score'] ?? 0),
              matchedCapabilities: Array.isArray(m['matched_capabilities'])
                ? (m['matched_capabilities'] as string[]).map(String)
                : [],
            })),
          },
        };
        break;
      }

      case 'guardrail_check_completed': {
        const rawChecks = Array.isArray(details['checks']) ? details['checks'] as Record<string, unknown>[] : [];
        next = {
          ...next,
          guardrailChecks: rawChecks.map(c => ({
            name: String(c['name'] ?? ''),
            passed: Boolean(c['passed']),
            actualValue: c['actual_value'] as string | number ?? '',
            limit: c['limit'] as string | number | undefined,
            reason: c['reason'] as string | undefined,
          })),
        };
        break;
      }

      case 'guardrails_passed':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates)
            .set('routing', 'completed')
            .set('guardrails', 'completed'),
        };
        break;

      case 'tool_policy_resolved': {
        const allowed = Array.isArray(details['allowed']) ? (details['allowed'] as string[]) : [];
        const denied = Array.isArray(details['requested_deny']) ? (details['requested_deny'] as string[]) : [];
        const policyType = String(details['policy_type'] ?? details['resolution_method'] ?? 'default');
        next = {
          ...next,
          toolPolicy: { policyType, allowedTools: allowed, deniedTools: denied },
        };
        break;
      }

      case 'toolchain_checked': {
        const toolCount = Number(details['tool_count'] ?? details['total'] ?? 0);
        const issues = Number(details['issues'] ?? details['issue_count'] ?? 0);
        next = {
          ...next,
          toolchainInfo: { toolCount, issues },
        };
        break;
      }

      case 'mcp_tools_initialized':
        next = {
          ...next,
          mcpToolsInfo: { toolCount: Number(details['tool_count'] ?? 0) },
        };
        break;

      case 'mcp_tools_failed':
        next = {
          ...next,
          mcpToolsInfo: { toolCount: 0, error: String(details['error'] ?? 'unknown') },
        };
        break;

      case 'memory_updated':
      case 'context_segmented':
      case 'context_reduced':
        next = { ...next, ...this.activatePhasePartial(d, 'context') };
        break;

      case 'planning_started':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates).set('context', 'completed'),
          ...this.activatePhasePartial(d, 'agent_loop'),
        };
        break;

      case 'planning_completed':
        next = { ...next, ...this.activatePhasePartial(d, 'agent_loop') };
        break;

      case 'debug_prompt_sent':
        next = {
          ...next,
          ...this.activatePhasePartial(d, (details['phase'] as PipelinePhase) ?? d.currentPhase ?? 'agent_loop'),
          llmCalls: [...d.llmCalls, {
            phase: (details['phase'] as PipelinePhase) ?? d.currentPhase ?? 'agent_loop',
            systemPrompt: (details['system_prompt'] as string) ?? '',
            userPrompt: (details['user_prompt'] as string) ?? '',
            rawResponse: '',
            parsedOutput: '',
            model: (details['model'] as string) ?? '',
            temperature: (details['temperature'] as number) ?? 0,
            latencyMs: 0,
            tokensEst: (details['tokens_est'] as number) ?? 0,
            timestamp: new Date().toISOString(),
          }],
        };
        break;

      case 'debug_llm_response': {
        const phase = (details['phase'] as PipelinePhase) ?? d.currentPhase;
        const idx = d.llmCalls.findIndex(c => c.phase === phase && !c.rawResponse);
        if (idx >= 0) {
          const updated = [...d.llmCalls];
          updated[idx] = {
            ...updated[idx],
            rawResponse: (details['raw_response'] as string) ?? '',
            parsedOutput: (details['parsed_output'] as string) ?? '',
            latencyMs: (details['latency_ms'] as number) ?? 0,
          };
          next = { ...next, llmCalls: updated };
        }
        break;
      }

      case 'debug_breakpoint_hit': {
        const bp = details['phase'] as PipelinePhase;
        next = {
          ...next,
          debugState: 'paused',
          pausedAtPhase: bp,
          phaseStates: bp ? new Map(d.phaseStates).set(bp, 'paused') : d.phaseStates,
        };
        break;
      }

      case 'llm_call_completed': {
        const llmDetails = details;
        const newCall: LlmCallRecord = {
          phase: (llmDetails['phase'] as PipelinePhase) ?? d.currentPhase ?? 'agent_loop',
          systemPrompt: (llmDetails['system_prompt_preview'] as string) ?? '',
          userPrompt: (llmDetails['prompt_preview'] as string) ?? '',
          rawResponse: (llmDetails['response_text'] as string) ?? '',
          parsedOutput: '',
          model: (llmDetails['model'] as string) ?? '',
          temperature: 0,
          latencyMs: (llmDetails['latency_ms'] as number) ?? 0,
          tokensEst: ((llmDetails['input_tokens'] as number) ?? 0) + ((llmDetails['output_tokens'] as number) ?? 0),
          timestamp: event.ts ?? new Date().toISOString(),
        };
        next = {
          ...next,
          ...this.activatePhasePartial(d, 'agent_loop'),
          llmCalls: [...d.llmCalls, newCall],
        };
        break;
      }

      case 'loop_iteration_started':
        next = { ...next, ...this.activatePhasePartial(d, 'agent_loop') };
        break;

      case 'tool_started':
        next = { ...next, ...this.activatePhasePartial(d, 'agent_loop') };
        break;

      case 'tool_execution_detail':
      case 'tool_completed':
        next = {
          ...next,
          ...this.activatePhasePartial(d, 'agent_loop'),
          toolExecutions: [...d.toolExecutions, {
            tool: (details['tool'] as string) ?? '',
            args: (details['args'] as Record<string, unknown>) ?? {},
            resultPreview: (details['resultPreview'] as string) ?? (details['result_chars'] ? `[${details['result_chars']} chars]` : ''),
            durationMs: (details['durationMs'] as number) ?? (details['duration_ms'] as number) ?? 0,
            exitCode: (details['exitCode'] as number) ?? (details['status'] === 'ok' ? 0 : 1),
            blocked: (details['blocked'] as boolean) ?? false,
            timestamp: (details['timestamp'] as string) ?? new Date().toISOString(),
          }],
        };
        break;

      case 'synthesis_started':
        next = {
          ...next,
          ...this.activatePhasePartial(d, 'agent_loop'),
        };
        break;

      case 'reflection_completed':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates).set('agent_loop', 'completed').set('reflection', 'completed'),
          reflectionVerdict: this.mapReflectionVerdict(details),
        };
        break;

      case 'reflection_skipped':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates).set('agent_loop', 'completed').set('reflection', 'skipped'),
        };
        break;

      case 'reflection_failed':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates)
            .set('agent_loop', 'completed')
            .set('reflection', 'error'),
        };
        break;

      case 'reply_shaping_started':
        next = { ...next, ...this.activatePhasePartial(d, 'reply_shaping') };
        break;

      case 'reply_shaping_skipped':
        next = {
          ...next,
          phaseStates: new Map(d.phaseStates)
            .set('reply_shaping', 'skipped')
            .set('response', 'active'),
          currentPhase: 'response' as PipelinePhase,
        };
        break;

      case 'reply_shaping_completed':
        next = {
          ...next,
          currentPhase: 'response' as PipelinePhase,
          phaseStates: new Map(d.phaseStates)
            .set('reply_shaping', 'completed')
            .set('response', 'active'),
        };
        break;

      case 'run_completed':
      case 'request_completed':
        next = {
          ...next,
          currentPhase: null,
          phaseStates: new Map(d.phaseStates).set('response', 'completed'),
          debugState: 'completed',
          totalDurationMs: Date.now() - (d.runStartTime ?? Date.now()),
        };
        break;

      case 'run_error':
        next = {
          ...next,
          debugState: 'error',
          phaseStates: d.currentPhase
            ? new Map(d.phaseStates).set(d.currentPhase, 'error')
            : d.phaseStates,
        };
        break;
    }

    this._debug.next({ ...d, ...next });
  }

  private activatePhasePartial(d: DebugSnapshot, phase: PipelinePhase): Partial<DebugSnapshot> {
    return {
      currentPhase: phase,
      selectedPhase: phase,
      phaseStates: new Map(d.phaseStates).set(phase, 'active'),
    };
  }

  private mapReflectionVerdict(details: Record<string, unknown>): ReflectionVerdict {
    return {
      goalAlignment: Number(details['goal_alignment'] ?? details['goalAlignment'] ?? 0),
      completeness: Number(details['completeness'] ?? 0),
      factualGrounding: Number(details['factual_grounding'] ?? details['factualGrounding'] ?? 0),
      score: Number(details['score'] ?? 0),
      shouldRetry: Boolean(details['should_retry'] ?? details['shouldRetry'] ?? false),
      hardFactualFail: Boolean(details['hard_factual_fail'] ?? details['hardFactualFail'] ?? false),
      issues: Array.isArray(details['issues']) ? details['issues'].map(String) : [],
      suggestedFix: details['suggested_fix'] != null ? String(details['suggested_fix']) : null,
      threshold: Number(details['threshold'] ?? 0.6),
    };
  }
}
