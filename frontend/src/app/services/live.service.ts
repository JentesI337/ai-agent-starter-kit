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
  finishReason?: string;
  toolNames?: string[];
  iteration?: number;
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

  // Real-time thinking stream
  thinkingText = '';
  thinkingIteration = 0;
  isThinking = false;

  private nextId = 0;
  private seenToolExecs = 0;
  private readonly subs = new Subscription();
  private initialized = false;

  private static readonly FEED_STAGES = new Set([
    // Lifecycle markers
    'run_started', 'request_started', 'request_dispatched',
    'guardrails_passed', 'guardrail_check_failed', 'guardrail_check_completed',
    'memory_updated', 'context_reduced', 'context_segmented',
    'model_route_selected',
    'loop_iteration_started',
    'tool_started', 'tool_completed', 'tool_blocked', 'tool_failed',
    'tool_selection_completed', 'tool_selection_started',
    'reflection_completed', 'reflection_skipped', 'reflection_failed',
    'reply_shaping_started', 'reply_shaping_skipped', 'reply_shaping_completed',
    'verification_final',
    'runner_started', 'runner_completed',
    'request_completed', 'request_cancelled', 'request_failed',
    'llm_call_completed',
  ]);

  private static readonly PHASES: PipelinePhase[] = [
    'routing', 'guardrails', 'context', 'agent_loop',
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

    // Token events → accumulate into thinking stream
    if (event.type === 'token') {
      if (!this.isThinking) {
        this.isThinking = true;
        this.thinkingText = '';
      }
      this.thinkingText += event.token || '';
      return;
    }

    // Auto-reset on new run/request
    if (event.stage === 'run_started' || event.stage === 'request_started') {
      this.clearFeed();
    }

    // New iteration → reset thinking buffer
    if (event.stage === 'loop_iteration_started') {
      this.thinkingText = '';
      this.isThinking = true;
      this.thinkingIteration = (event.details?.['iteration'] as number) || 0;
    }

    // LLM completed → stop thinking
    if (event.stage === 'llm_call_completed') {
      this.isThinking = false;
    }

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

    // Rich lifecycle events
    if (event.stage && LiveService.FEED_STAGES.has(event.stage)) {
      const details = event.details ?? {};

      // LLM call completed → rich conversational event
      if (event.stage === 'llm_call_completed') {
        const toolNames = Array.isArray(details['tool_names']) ? (details['tool_names'] as string[]) : [];
        this.push({
          id: this.nextId++, type: 'llm_call', timestamp: ts, agent,
          status: 'completed',
          model: (details['model'] as string) || '',
          phase: 'agent_loop',
          latencyMs: (details['latency_ms'] as number) || 0,
          tokensEst: ((details['input_tokens'] as number) || 0) + ((details['output_tokens'] as number) || 0),
          finishReason: (details['finish_reason'] as string) || '',
          iteration: (details['iteration'] as number) || 0,
          toolNames,
          promptPreview: (details['prompt_preview'] as string) || '',
          systemPrompt: (details['system_prompt_preview'] as string) || '',
          userPrompt: (details['prompt_preview'] as string) || '',
          rawResponse: (details['response_text'] as string) || '',
        });
        return;
      }

      // Tool lifecycle events → enrich with tool info
      if (event.stage === 'tool_completed' || event.stage === 'tool_execution_detail') {
        // These are handled by processDebug via the debug snapshot — skip to avoid duplicates
        return;
      }

      // Route selection → enrich
      if (event.stage === 'model_route_selected') {
        this.push({
          id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
          status: 'completed', stage: event.stage,
          message: `Model: ${details['primary'] || 'default'} · Reasoning: ${details['reasoning_level'] || 'standard'}`,
        });
        return;
      }

      // Loop iteration → step
      if (event.stage === 'loop_iteration_started') {
        this.push({
          id: this.nextId++, type: 'step', timestamp: ts, agent,
          status: 'running', stage: event.stage,
          message: `Agent loop iteration ${details['iteration'] || '?'}`,
        });
        return;
      }

      // Reflection completed → rich
      if (event.stage === 'reflection_completed') {
        const score = details['score'] || details['quality_score'] || 0;
        const shouldRetry = details['should_retry'] || false;
        this.push({
          id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
          status: shouldRetry ? 'error' : 'completed', stage: event.stage,
          message: `Reflection score: ${typeof score === 'number' ? (score * 100).toFixed(0) : score}%${shouldRetry ? ' — retrying' : ''}`,
        });
        return;
      }

      // Runner completed → stats
      if (event.stage === 'runner_completed') {
        const iters = details['iterations'] || 0;
        const tools = details['total_tool_calls'] || 0;
        const elapsed = typeof details['elapsed_seconds'] === 'number' ? (details['elapsed_seconds'] as number).toFixed(1) : '?';
        this.push({
          id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
          status: 'completed', stage: event.stage,
          message: `Completed in ${elapsed}s · ${iters} iterations · ${tools} tool calls`,
        });
        return;
      }

      // Verification final
      if (event.stage === 'verification_final') {
        this.push({
          id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
          status: details['status'] === 'pass' ? 'completed' : 'error', stage: event.stage,
          message: `Verification: ${details['status'] || 'unknown'} — ${details['reason'] || ''}`,
        });
        return;
      }

      // Tool selection completed
      if (event.stage === 'tool_selection_completed') {
        this.push({
          id: this.nextId++, type: 'step', timestamp: ts, agent,
          status: 'completed', stage: event.stage,
          message: `Selected ${details['actions'] || 0} tool actions`,
        });
        return;
      }

      // Tool blocked
      if (event.stage === 'tool_blocked') {
        this.push({
          id: this.nextId++, type: 'step', timestamp: ts, agent,
          status: 'error', stage: event.stage,
          message: `Tool blocked: ${details['tool'] || 'unknown'} — ${details['reason'] || ''}`,
        });
        return;
      }

      // Memory updated
      if (event.stage === 'memory_updated') {
        this.push({
          id: this.nextId++, type: 'lifecycle', timestamp: ts, agent,
          status: 'completed', stage: event.stage,
          message: `Memory loaded · ${details['memory_items'] || '?'} items`,
        });
        return;
      }

      // Default lifecycle
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
    if (snap.toolExecutions.length < this.seenToolExecs) {
      this.seenToolExecs = 0;
    }

    // Tool executions (from tool_completed/tool_execution_detail lifecycle events)
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
    if (event.stage === 'llm_call_completed' || event.stage === 'debug_prompt_sent') lane.llmCalls++;
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
    this.seenToolExecs = 0;
    this.nextId = 0;
    this.inspectedEvent = null;
    this.thinkingText = '';
    this.thinkingIteration = 0;
    this.isThinking = false;
  }

  resetFilters(): void {
    this.filterAgent = 'all';
    this.filterStatus = 'all';
  }
}
