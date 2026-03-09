import { CommonModule } from '@angular/common';
import {
  AfterViewChecked,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  ViewChild,
} from '@angular/core';
import { Subscription } from 'rxjs';

import { AgentSocketService } from '../services/agent-socket.service';
import { AgentStateService, PipelinePhase, PhaseState } from '../services/agent-state.service';
import { LiveService, LiveEvent } from '../services/live.service';

/** Grouped representation: one "thought bubble" containing related events. */
interface ThoughtGroup {
  id: number;
  phase: string;
  phaseLabel: string;
  phaseIcon: string;
  agent: string;
  timestamp: string;
  events: LiveEvent[];
  status: 'active' | 'completed' | 'error';
  collapsed: boolean;
  animateIn: boolean;
}

@Component({
  selector: 'app-live-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './live-page.component.html',
  styleUrl: './live-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LivePageComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('thoughtStream') private thoughtStream?: ElementRef<HTMLElement>;

  groups: ThoughtGroup[] = [];
  activePhase: PipelinePhase | null = null;
  phaseStates = new Map<PipelinePhase, PhaseState>();
  phases: PipelinePhase[] = [
    'routing', 'guardrails', 'context', 'agent_loop',
    'reflection', 'reply_shaping', 'response',
  ];
  isConnected = false;
  isEmpty = true;
  expandedEventId: number | null = null;

  private readonly subs = new Subscription();
  private lastFeedLen = 0;
  private shouldScroll = false;
  private groupIdCounter = 0;
  private lastPhase = '';

  constructor(
    readonly live: LiveService,
    readonly agentState: AgentStateService,
    private readonly socket: AgentSocketService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.socket.connect('ws://localhost:8000/ws/agent');
    this.agentState.init();
    this.live.init();

    this.subs.add(
      this.agentState.connected$.subscribe(c => {
        this.isConnected = c;
        this.cdr.markForCheck();
      }),
    );

    this.subs.add(
      this.agentState.debug$.subscribe(snap => {
        this.phaseStates = new Map(snap.phaseStates);
        this.activePhase = snap.currentPhase;
        this.cdr.markForCheck();
      }),
    );

    // Poll live feed for changes
    this.subs.add(
      this.agentState.event$.subscribe(ev => {
        if (ev?.type === 'token') {
          // Throttle token updates — mark for check but don't rebuild groups
          this.shouldScroll = true;
          this.cdr.markForCheck();
          return;
        }
        this.rebuildGroups();
        this.cdr.markForCheck();
      }),
    );
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll && this.thoughtStream) {
      const el = this.thoughtStream.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  // ── Group building ──────────────────────────────────

  private rebuildGroups(): void {
    const feed = this.live.feed;
    // Detect feed reset (e.g. new run started)
    if (feed.length < this.lastFeedLen) {
      this.lastFeedLen = 0;
      this.groupIdCounter = 0;
    }
    if (feed.length === this.lastFeedLen) return;

    // Build from newest→oldest feed (feed is reverse-chronological)
    const chronological = [...feed].reverse();
    const groups: ThoughtGroup[] = [];
    let current: ThoughtGroup | null = null;

    for (const ev of chronological) {
      const phase = this.eventPhase(ev);

      // Start new group on phase change, agent change, or lifecycle boundary
      if (
        !current ||
        current.phase !== phase ||
        current.agent !== (ev.agent || 'system') ||
        ev.type === 'lifecycle'
      ) {
        if (current) groups.push(current);
        current = {
          id: this.groupIdCounter++,
          phase,
          phaseLabel: this.phaseDisplayLabel(phase),
          phaseIcon: this.phaseIconFor(phase),
          agent: ev.agent || 'system',
          timestamp: ev.timestamp,
          events: [],
          status: 'completed',
          collapsed: false,
          animateIn: true,
        };
      }
      current.events.push(ev);

      // Update group status
      if (ev.status === 'running') current.status = 'active';
      if (ev.status === 'error') current.status = 'error';
    }
    if (current) groups.push(current);

    this.groups = groups;
    this.isEmpty = groups.length === 0;
    this.lastFeedLen = feed.length;
    this.shouldScroll = true;

    // Remove animation flag after a tick
    setTimeout(() => {
      for (const g of this.groups) g.animateIn = false;
      this.cdr.markForCheck();
    }, 600);
  }

  // ── Helpers ─────────────────────────────────────────

  private eventPhase(ev: LiveEvent): string {
    if (ev.type === 'llm_call') return 'llm_call_completed';
    if (ev.type === 'tool_call') return 'agent_loop';
    if (ev.type === 'error') return 'error';
    if (ev.type === 'lifecycle') return ev.stage || 'lifecycle';
    // Steps like loop_iteration_started, tool_selection_completed
    return ev.stage || 'step';
  }

  phaseDisplayLabel(phase: string): string {
    const map: Record<string, string> = {
      routing: 'Routing',
      guardrails: 'Guardrails',
      context: 'Building Context',
      agent_loop: 'Agent Loop',
      reflection: 'Reflecting',
      reply_shaping: 'Shaping Reply',
      response: 'Responding',
      inference: 'Thinking',
      run_started: 'Run Started',
      runner_started: 'Runner Initialized',
      request_dispatched: 'Request Dispatched',
      request_completed: 'Completed',
      request_cancelled: 'Cancelled',
      request_failed: 'Failed',
      guardrails_passed: 'Guardrails Passed',
      guardrail_check_failed: 'Guardrail Failed',
      guardrail_check_completed: 'Guardrails Checked',
      memory_updated: 'Memory Loaded',
      context_reduced: 'Context Compressed',
      context_segmented: 'Context Segmented',
      model_route_selected: 'Model Selected',
      loop_iteration_started: 'Agent Iteration',
      llm_call_completed: 'LLM Inference',
      tool_started: 'Tool Executing',
      tool_completed: 'Tool Done',
      tool_blocked: 'Tool Blocked',
      tool_failed: 'Tool Failed',
      tool_selection_started: 'Selecting Tools',
      tool_selection_completed: 'Tools Selected',
      reflection_completed: 'Reflection',
      reflection_skipped: 'Reflection Skipped',
      reflection_failed: 'Reflection Failed',
      reply_shaping_started: 'Shaping Reply',
      reply_shaping_completed: 'Reply Shaped',
      verification_final: 'Verification',
      runner_completed: 'Run Complete',
      error: 'Error',
      step: 'Processing',
    };
    return map[phase] || phase.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  phaseIconFor(phase: string): string {
    const map: Record<string, string> = {
      routing: '◈',
      guardrails: '⬡',
      context: '◉',
      agent_loop: '⟳',
      reflection: '◎',
      reply_shaping: '◇',
      response: '▣',
      inference: '⟐',
      run_started: '▶',
      runner_started: '▶',
      request_dispatched: '→',
      request_completed: '✓',
      request_cancelled: '■',
      request_failed: '✕',
      guardrails_passed: '✓',
      guardrail_check_failed: '✕',
      guardrail_check_completed: '⬡',
      memory_updated: '◫',
      context_reduced: '◫',
      context_segmented: '◫',
      model_route_selected: '⬢',
      loop_iteration_started: '⟳',
      llm_call_completed: '⟐',
      tool_started: '⚡',
      tool_completed: '⚡',
      tool_blocked: '⛊',
      tool_failed: '✕',
      tool_selection_started: '⬡',
      tool_selection_completed: '⬡',
      reflection_completed: '◎',
      reflection_skipped: '◎',
      reflection_failed: '◎',
      reply_shaping_started: '◇',
      reply_shaping_completed: '◇',
      verification_final: '✓',
      runner_completed: '✓',
      error: '⚠',
      step: '·',
    };
    return map[phase] || '·';
  }

  phaseBarState(phase: PipelinePhase): string {
    return this.phaseStates.get(phase) || 'idle';
  }

  phaseBarLabel(phase: PipelinePhase): string {
    const map: Record<string, string> = {
      routing: 'Route',
      guardrails: 'Guard',
      context: 'Context',
      agent_loop: 'Agent',
      reflection: 'Reflect',
      reply_shaping: 'Shape',
      response: 'Reply',
    };
    return map[phase] || phase;
  }

  toggleGroup(group: ThoughtGroup): void {
    group.collapsed = !group.collapsed;
  }

  toggleEventDetail(eventId: number): void {
    this.expandedEventId = this.expandedEventId === eventId ? null : eventId;
  }

  formatTime(ts: string): string {
    if (!ts) return '';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  formatDuration(ms: number | undefined): string {
    if (ms === undefined || ms === null) return '';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  trackGroup(_: number, g: ThoughtGroup): number {
    return g.id;
  }

  trackEvent(_: number, ev: LiveEvent): number {
    return ev.id;
  }

  clearAll(): void {
    this.live.clearFeed();
    this.groups = [];
    this.isEmpty = true;
    this.lastFeedLen = 0;
    this.groupIdCounter = 0;
    this.expandedEventId = null;
  }
}
