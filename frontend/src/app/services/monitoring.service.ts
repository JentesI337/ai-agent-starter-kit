import { Injectable } from '@angular/core';

import { AgentSocketEvent } from './agent-socket.service';
import { AgentDescriptor, AgentsService, MonitoringSchema, RunsAuditResponse } from './agents.service';

export interface LifecycleLine {
  time: string;
  type: string;
  text: string;
}

export interface AgentActivity {
  agentId: string;
  role: string;
  currentStage: string;
  lastMessage: string;
  activeRequestId: string;
  updatedAt: string;
  events: number;
  toolEvents: number;
  errors: number;
}

export interface RequestActivity {
  requestId: string;
  sessionId: string;
  agentId: string;
  stage: string;
  status: 'running' | 'waiting_clarification' | 'completed' | 'failed' | 'cancelled';
  startedAt: string;
  updatedAt: string;
  toolEvents: number;
  error: string;
}

export interface ReasonEntry {
  key: string;
  count: number;
}

@Injectable({ providedIn: 'root' })
export class MonitoringService {
  agentActivities: AgentActivity[] = [];
  requestActivities: RequestActivity[] = [];
  lifecycleLines: LifecycleLine[] = [];
  reasoningLines: LifecycleLine[] = [];

  runAudit: RunsAuditResponse | null = null;
  runAuditLoading = false;
  runAuditError = '';
  runAuditLastRunId = '';

  monitorAgentFilter = 'all';
  monitorStatusFilter: 'all' | 'running' | 'waiting_clarification' | 'completed' | 'failed' | 'cancelled' = 'all';
  monitorRequestFilter = '';
  monitorSearch = '';

  monitoringSchema: MonitoringSchema | null = null;
  availableAgents: AgentDescriptor[] = [];

  private readonly agentActivityMap = new Map<string, AgentActivity>();
  private readonly requestActivityMap = new Map<string, RequestActivity>();

  constructor(private readonly agentsService: AgentsService) {}

  get monitoringAgentOptions(): string[] {
    const options = new Set<string>();
    for (const agent of this.availableAgents) {
      options.add(agent.id);
    }
    for (const item of this.agentActivities) {
      options.add(item.agentId);
    }
    return [...options].sort((a, b) => a.localeCompare(b));
  }

  get filteredAgentActivities(): AgentActivity[] {
    const query = this.monitorSearch.trim().toLowerCase();
    return this.agentActivities.filter((item) => {
      if (this.monitorAgentFilter !== 'all' && item.agentId !== this.monitorAgentFilter) {
        return false;
      }
      if (this.monitorRequestFilter.trim() && !item.activeRequestId.includes(this.monitorRequestFilter.trim())) {
        return false;
      }
      if (!query) {
        return true;
      }
      const haystack = `${item.agentId} ${item.role} ${item.currentStage} ${item.lastMessage}`.toLowerCase();
      return haystack.includes(query);
    });
  }

  get filteredRequestActivities(): RequestActivity[] {
    const query = this.monitorSearch.trim().toLowerCase();
    return this.requestActivities.filter((item) => {
      if (this.monitorAgentFilter !== 'all' && item.agentId !== this.monitorAgentFilter) {
        return false;
      }
      if (this.monitorStatusFilter !== 'all' && item.status !== this.monitorStatusFilter) {
        return false;
      }
      if (this.monitorRequestFilter.trim() && !item.requestId.includes(this.monitorRequestFilter.trim())) {
        return false;
      }
      if (!query) {
        return true;
      }
      const haystack = `${item.requestId} ${item.agentId} ${item.stage} ${item.error}`.toLowerCase();
      return haystack.includes(query);
    });
  }

  get filteredReasoningLines(): LifecycleLine[] {
    const query = this.monitorSearch.trim().toLowerCase();
    if (!query) {
      return this.reasoningLines;
    }
    return this.reasoningLines.filter((item) => `${item.type} ${item.text}`.toLowerCase().includes(query));
  }

  get filteredLifecycleLines(): LifecycleLine[] {
    const query = this.monitorSearch.trim().toLowerCase();
    if (!query) {
      return this.lifecycleLines;
    }
    return this.lifecycleLines.filter((item) => `${item.type} ${item.text}`.toLowerCase().includes(query));
  }

  get effectiveRunAuditId(): string {
    const explicit = this.monitorRequestFilter.trim();
    if (explicit) {
      return explicit;
    }
    return this.filteredRequestActivities[0]?.requestId ?? '';
  }

  get blockedReasonEntries(): ReasonEntry[] {
    return this.toSortedReasonEntries(this.runAudit?.telemetry.blocked_with_reason ?? {});
  }

  get emptyReasonEntries(): ReasonEntry[] {
    return this.toSortedReasonEntries(this.runAudit?.telemetry.tool_selection_empty_reasons ?? {});
  }

  get topBlockedReason(): ReasonEntry | null {
    return this.blockedReasonEntries[0] ?? null;
  }

  get topEmptyReason(): ReasonEntry | null {
    return this.emptyReasonEntries[0] ?? null;
  }

  updateMonitoring(event: AgentSocketEvent, defaultAgentId: string): void {
    const timestamp = event.ts ?? new Date().toISOString();
    const agentId = (event.agent || defaultAgentId || 'unknown').toString();
    const stage = event.stage || event.type || 'event';
    const message = event.message || event.step || stage;

    const existingAgent = this.agentActivityMap.get(agentId) ?? {
      agentId,
      role: this.resolveAgentRole(agentId),
      currentStage: stage,
      lastMessage: message,
      activeRequestId: event.request_id || '',
      updatedAt: timestamp,
      events: 0,
      toolEvents: 0,
      errors: 0,
    };

    existingAgent.role = this.resolveAgentRole(agentId);
    existingAgent.currentStage = stage;
    existingAgent.lastMessage = message;
    existingAgent.updatedAt = timestamp;
    existingAgent.events += 1;
    if (event.request_id) {
      existingAgent.activeRequestId = event.request_id;
    }
    if ((event.stage || '').startsWith('tool_')) {
      existingAgent.toolEvents += 1;
    }
    if (event.type === 'error' || (event.stage || '').startsWith('request_failed')) {
      existingAgent.errors += 1;
    }
    if (event.stage === 'request_completed' || event.stage === 'request_cancelled' || (event.stage || '').startsWith('request_failed')) {
      existingAgent.activeRequestId = '';
    }

    this.agentActivityMap.set(agentId, existingAgent);

    if (event.request_id) {
      const existingRequest = this.requestActivityMap.get(event.request_id) ?? {
        requestId: event.request_id,
        sessionId: event.session_id || '',
        agentId,
        stage,
        status: 'running' as const,
        startedAt: timestamp,
        updatedAt: timestamp,
        toolEvents: 0,
        error: '',
      };

      existingRequest.agentId = agentId;
      existingRequest.sessionId = event.session_id || existingRequest.sessionId;
      existingRequest.stage = stage;
      existingRequest.updatedAt = timestamp;
      if ((event.stage || '').startsWith('tool_')) {
        existingRequest.toolEvents += 1;
      }
      if (event.stage === 'request_completed') {
        existingRequest.status = 'completed';
      }
      if (event.stage === 'request_cancelled') {
        existingRequest.status = 'cancelled';
      }
      if (event.stage === 'clarification_waiting_response') {
        existingRequest.status = 'waiting_clarification';
      }
      if ((event.stage || '').startsWith('request_failed') || event.type === 'error') {
        existingRequest.status = 'failed';
        existingRequest.error = event.message || existingRequest.error;
      }

      this.requestActivityMap.set(event.request_id, existingRequest);

      if (event.stage === 'request_completed' || event.stage === 'request_cancelled' || (event.stage || '').startsWith('request_failed')) {
        this.fetchRunAudit(event.request_id, true);
      }
    }

    if (
      event.type === 'agent_step' ||
      event.type === 'lifecycle' ||
      (event.type === 'status' && Boolean(event.message))
    ) {
      this.reasoningLines.unshift({
        time: new Date(timestamp).toLocaleTimeString(),
        type: event.type,
        text: `${agentId}: ${message}`,
      });
      if (this.reasoningLines.length > 400) {
        this.reasoningLines = this.reasoningLines.slice(0, 400);
      }
    }
  }

  pushLifecycle(type: string, text: string, details?: Record<string, unknown>, ts?: string): void {
    const time = ts ? new Date(ts).toLocaleTimeString() : new Date().toLocaleTimeString();
    const detailText = details ? ` ${JSON.stringify(details)}` : '';
    this.lifecycleLines.unshift({
      time,
      type,
      text: `${text}${detailText}`,
    });
    if (this.lifecycleLines.length > 500) {
      this.lifecycleLines = this.lifecycleLines.slice(0, 500);
    }
  }

  refreshViews(): void {
    this.agentActivities = [...this.agentActivityMap.values()].sort((a, b) =>
      b.updatedAt.localeCompare(a.updatedAt)
    );
    this.requestActivities = [...this.requestActivityMap.values()]
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, 200);
  }

  resetFilters(): void {
    this.monitorAgentFilter = 'all';
    this.monitorStatusFilter = 'all';
    this.monitorRequestFilter = '';
    this.monitorSearch = '';
  }

  resetAll(): void {
    this.lifecycleLines = [];
    this.reasoningLines = [];
    this.agentActivityMap.clear();
    this.requestActivityMap.clear();
    this.agentActivities = [];
    this.requestActivities = [];
    this.runAudit = null;
    this.runAuditError = '';
    this.runAuditLastRunId = '';
    this.runAuditLoading = false;
    this.resetFilters();
  }

  refreshRunAudit(): void {
    const runId = this.effectiveRunAuditId;
    if (!runId) {
      this.runAuditError = 'No request ID available yet.';
      this.runAudit = null;
      this.runAuditLastRunId = '';
      return;
    }
    this.fetchRunAudit(runId);
  }

  private resolveAgentRole(agentId: string): string {
    const fromSchema = this.monitoringSchema?.agents.find((item) => item.id === agentId);
    if (fromSchema) {
      return fromSchema.role;
    }
    const fromAgents = this.availableAgents.find((item) => item.id === agentId);
    return fromAgents?.role ?? 'agent';
  }

  private fetchRunAudit(runId: string, silent = false): void {
    if (!runId) {
      return;
    }
    if (this.runAuditLoading && this.runAuditLastRunId === runId) {
      return;
    }
    this.runAuditLoading = true;
    this.runAuditError = '';
    this.runAuditLastRunId = runId;

    this.agentsService.getRunAudit(runId).subscribe({
      next: (payload) => {
        this.runAudit = payload;
        this.runAuditLoading = false;
      },
      error: (error) => {
        this.runAuditLoading = false;
        this.runAudit = null;
        this.runAuditError = error?.error?.detail ?? error?.message ?? 'Failed to load run audit.';
      },
    });
  }

  private toSortedReasonEntries(source: Record<string, number>): ReasonEntry[] {
    return Object.entries(source)
      .filter((entry) => Number.isFinite(entry[1]) && entry[1] > 0)
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => {
        if (b.count !== a.count) {
          return b.count - a.count;
        }
        return a.key.localeCompare(b.key);
      });
  }
}
