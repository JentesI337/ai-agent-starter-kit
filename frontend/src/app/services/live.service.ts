import { Injectable, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';

import { AgentSocketEvent } from './agent-socket.service';
import {
  AgentStateService,
  DebugSnapshot,
  PipelinePhase,
  PhaseState,
} from './agent-state.service';

// ── Types ─────────────────────────────────────────────

export interface LiveEvent {
  id: number;
  type: 'llm_call' | 'tool_call' | 'step' | 'lifecycle' | 'error';
  timestamp: string;
  agent: string;
  status: 'running' | 'completed' | 'error';
  // LLM
  model?: string;
  phase?: string;
  promptPreview?: string;
  tokensEst?: number;
  latencyMs?: number;
  systemPrompt?: string;
  userPrompt?: string;
  rawResponse?: string;
  // Tool
  tool?: string;
  argsPreview?: string;
  resultPreview?: string;
  durationMs?: number;
  exitCode?: number;
  blocked?: boolean;
  // Lifecycle / step
  stage?: string;
  message?: string;
}

export interface AgentLane {
  agentId: string;
  currentStage: string;
  lastMessage: string;
  events: number;
  toolCalls: number;
  llmCalls: number;
  errors: number;
  active: boolean;
  updatedAt: string;
}

// ── Service ───────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class LiveService implements OnDestroy {
  feed: LiveEvent[] = [];
  agents = new Map<string, AgentLane>();
  agentList: AgentLane[] = [];

  paused = false;
  bufferedCount = 0;
  private pauseBuffer: LiveEvent[] = [];

  filterAgent = 'all';
  filterStatus: 'all' | 'running' | 'completed' | 'error' = 'all';

  inspectedEvent: LiveEvent | null = null;

  // Pipeline phase state (from debug$)
  phaseStates = new Map<PipelinePhase, PhaseState>();
  currentPhase: PipelinePhase | null = null;
  debugState = 'idle';

  private nextId = 0;
  private seenLlmCalls = 0;
  private seenToolExecs = 0;
  private readonly llmEventIds = new Map<number, number>();
  private readonly subs = new Subscription();
  private initialized = false;

  private static readonly FEED_STAGES = new Set([
    'run_started', 'request_started', 'request_dispatched',
    'guardrails_passed', 'guardrail_check_failed',
    'request_completed', 'request_cancelled', 'request_failed',
  ]);

  private static readonly PHASES: PipelinePhase[] = [
    'routing', 'guardrails', 'context', 'planning',
    'tool_selection', 'tool_execution', 'synthesis',
    'reflection', 'reply_shaping', 'response',
  ];

  get pipelinePhases(): PipelinePhase[] {
    return LiveService.PHASES;
  }

  get filteredFeed(): LiveEvent[] {
    return this.feed.filter(e => {
      if (this.filterAgent !== 'all' && e.agent !== this.filterAgent) return false;
      if (this.filterStatus !== 'all' && e.status !== this.filterStatus) return false;
      return true;
    });
  }

  get agentOptions(): string[] {
    return [...this.agents.keys()].sort();
  }

  constructor(private readonly agentState: AgentStateService) {}

  init(): void {
    if (this.initialized) return;
    this.initialized = true;

    this.subs.add(
      this.agentState.event$.subscribe(ev => { if (ev) this.processEvent(ev); })
    );
    this.subs.add(
      this.agentState.debug$.subscribe(snap => this.processDebug(snap))
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  // ── Event processing ────────────────────────────────

  private processEvent(event: AgentSocketEvent): void {
    const agent = event.agent || 'system';
    const ts = event.ts || new Date().toISOString();

    // Skip high-volume noise
    if (event.type === 'token') return;

    // Update lane for non-system agents
    if (agent && agent !== 'system') {
      this.updateLane(agent, event);
    }

    // Skip non-feed event types
    if (event.type === 'status' || event.type === 'final') return;

    if (event.type === 'error') {
      this.push({
        id: this.nextId++, type: 'error', timestamp: ts, agent,
        status: 'error', message: event.message || 'Unknown error',
      });
      return;
    }

    if (event.type === 'agent_step') {
      this.push({
        id: this.nextId++, type: 'step', timestamp: ts, agent,
        status: 'completed', stage: event.stage || 'step',
        message: event.step || event.message || '',
      });
      return;
    }

    if (event.stage && LiveService.FEED_STAGES.has(event.stage)) {
      this.push({
        id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
        status: 'completed', stage: event.stage,
        message: event.message || event.stage,
      });
    }
  }

  private processDebug(snap: DebugSnapshot): void {
    this.phaseStates = new Map(snap.phaseStates);
    this.currentPhase = snap.currentPhase;
    this.debugState = snap.debugState;

    // Reset on new run
    if (snap.llmCalls.length < this.seenLlmCalls) {
      this.seenLlmCalls = 0;
      this.llmEventIds.clear();
    }
    if (snap.toolExecutions.length < this.seenToolExecs) {
      this.seenToolExecs = 0;
    }

    // New LLM calls
    for (let i = this.seenLlmCalls; i < snap.llmCalls.length; i++) {
      const c = snap.llmCalls[i];
      const id = this.nextId++;
      this.llmEventIds.set(i, id);
      this.push({
        id, type: 'llm_call', timestamp: c.timestamp || new Date().toISOString(),
        agent: 'agent', model: c.model, phase: c.phase,
        promptPreview: (c.userPrompt || '').slice(0, 200),
        tokensEst: c.tokensEst, latencyMs: c.latencyMs,
        systemPrompt: c.systemPrompt, userPrompt: c.userPrompt,
        rawResponse: c.rawResponse,
        status: c.rawResponse ? 'completed' : 'running',
      });
    }
    this.seenLlmCalls = snap.llmCalls.length;

    // Update running LLM calls with response
    for (const [idx, eventId] of this.llmEventIds) {
      if (idx >= snap.llmCalls.length) continue;
      const c = snap.llmCalls[idx];
      if (!c.rawResponse) continue;
      const fi = this.feed.findIndex(e => e.id === eventId && e.status === 'running');
      if (fi >= 0) {
        this.feed[fi] = {
          ...this.feed[fi],
          rawResponse: c.rawResponse,
          latencyMs: c.latencyMs,
          tokensEst: c.tokensEst,
          status: 'completed',
        };
      }
    }

    // New tool executions
    for (let i = this.seenToolExecs; i < snap.toolExecutions.length; i++) {
      const t = snap.toolExecutions[i];
      this.push({
        id: this.nextId++, type: 'tool_call',
        timestamp: t.timestamp || new Date().toISOString(),
        agent: 'agent', tool: t.tool,
        argsPreview: JSON.stringify(t.args || {}).slice(0, 100),
        resultPreview: t.resultPreview,
        durationMs: t.durationMs, exitCode: t.exitCode,
        blocked: t.blocked,
        status: t.blocked ? 'error' : 'completed',
      });
    }
    this.seenToolExecs = snap.toolExecutions.length;
  }

  // ── Feed management ─────────────────────────────────

  private push(event: LiveEvent): void {
    if (this.paused) {
      this.pauseBuffer.push(event);
      this.bufferedCount = this.pauseBuffer.length;
      return;
    }
    this.feed.unshift(event);
    if (this.feed.length > 500) this.feed.length = 500;
  }

  private updateLane(agentId: string, event: AgentSocketEvent): void {
    const lane = this.agents.get(agentId) ?? {
      agentId, currentStage: '', lastMessage: '',
      events: 0, toolCalls: 0, llmCalls: 0, errors: 0,
      active: true, updatedAt: new Date().toISOString(),
    };

    lane.events++;
    lane.currentStage = event.stage || event.type || lane.currentStage;
    lane.lastMessage = event.message || event.step || lane.lastMessage;
    lane.updatedAt = event.ts || new Date().toISOString();

    if ((event.stage || '').startsWith('tool_')) lane.toolCalls++;
    if (event.stage === 'debug_prompt_sent') lane.llmCalls++;
    if (event.type === 'error') lane.errors++;

    lane.active =
      event.stage !== 'request_completed' &&
      event.stage !== 'request_cancelled' &&
      !(event.stage || '').startsWith('request_failed');

    this.agents.set(agentId, lane);
    this.agentList = [...this.agents.values()]
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  // ── Public API ──────────────────────────────────────

  pause(): void {
    this.paused = true;
  }

  resume(): void {
    this.paused = false;
    for (const e of this.pauseBuffer) this.feed.unshift(e);
    this.pauseBuffer = [];
    this.bufferedCount = 0;
    if (this.feed.length > 500) this.feed.length = 500;
  }

  inspect(event: LiveEvent | null): void {
    this.inspectedEvent = this.inspectedEvent === event ? null : event;
  }

  clearFeed(): void {
    this.feed = [];
    this.pauseBuffer = [];
    this.bufferedCount = 0;
    this.agents.clear();
    this.agentList = [];
    this.seenLlmCalls = 0;
    this.seenToolExecs = 0;
    this.llmEventIds.clear();
    this.nextId = 0;
    this.inspectedEvent = null;
  }

  resetFilters(): void {
    this.filterAgent = 'all';
    this.filterStatus = 'all';
  }
}
