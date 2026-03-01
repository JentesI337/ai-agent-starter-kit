import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { AgentSocketEvent, AgentSocketService, ToolPolicyPayload } from '../services/agent-socket.service';
import { AgentDescriptor, AgentsService, MonitoringSchema } from '../services/agents.service';

interface ChatLine {
  role: 'user' | 'agent' | 'system';
  text: string;
}

interface LifecycleLine {
  time: string;
  type: string;
  text: string;
}

interface AgentActivity {
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

interface RequestActivity {
  requestId: string;
  sessionId: string;
  agentId: string;
  stage: string;
  status: 'running' | 'completed' | 'failed';
  startedAt: string;
  updatedAt: string;
  toolEvents: number;
  error: string;
}

@Component({
  selector: 'app-chat-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.scss',
})
export class ChatPageComponent implements OnInit, OnDestroy {
  input = '';
  toolAllowInput = '';
  toolDenyInput = '';
  model = '';
  runtimeTarget: 'local' | 'api' = 'local';
  firstRunChoicePending = false;
  selectedAgentId = 'head-agent';
  sessionId = '';
  runtimeSwitching = false;
  apiModelsAvailable: boolean | null = null;
  apiModelsHint = '';
  isConnected = false;
  lines: ChatLine[] = [];
  lifecycleLines: LifecycleLine[] = [];
  reasoningLines: LifecycleLine[] = [];
  availableAgents: AgentDescriptor[] = [];
  monitoringSchema: MonitoringSchema | null = null;
  agentActivities: AgentActivity[] = [];
  requestActivities: RequestActivity[] = [];
  monitorAgentFilter = 'all';
  monitorStatusFilter: 'all' | 'running' | 'completed' | 'failed' = 'all';
  monitorRequestFilter = '';
  monitorSearch = '';

  private activeAssistantIndex: number | null = null;
  private readonly subscriptions = new Subscription();
  private readonly wsUrl = 'ws://localhost:8000/ws/agent';
  private readonly agentActivityMap = new Map<string, AgentActivity>();
  private readonly requestActivityMap = new Map<string, RequestActivity>();

  constructor(
    private readonly socketService: AgentSocketService,
    private readonly agentsService: AgentsService,
    private readonly cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.socketService.connect(this.wsUrl);

    const persistedRuntime = localStorage.getItem('preferredRuntime');
    if (persistedRuntime === 'local' || persistedRuntime === 'api') {
      this.runtimeTarget = persistedRuntime;
      this.firstRunChoicePending = false;
    } else {
      this.firstRunChoicePending = true;
    }

    this.agentsService.getRuntimeStatus().subscribe({
      next: (status) => {
        if (!this.firstRunChoicePending) {
          this.runtimeTarget = status.runtime;
        }
        this.model = status.model || this.model;
        this.apiModelsAvailable = status.apiModelsAvailable ?? null;
        const modelsCount = status.apiModelsCount ?? null;
        const modelsError = status.apiModelsError ?? null;
        if (modelsError) {
          this.apiModelsHint = modelsError;
        } else if (modelsCount !== null) {
          this.apiModelsHint = `${modelsCount} model(s) visible`;
        } else {
          this.apiModelsHint = '';
        }
        if (!this.firstRunChoicePending) {
          localStorage.setItem('preferredRuntime', status.runtime);
        }
      },
    });

    this.agentsService.getAgents().subscribe({
      next: (agents) => {
        this.availableAgents = agents;
        const selectedExists = agents.some((agent) => agent.id === this.selectedAgentId);
        if (!selectedExists && agents.length > 0) {
          this.selectedAgentId = agents[0].id;
        }
      },
    });

    this.agentsService.getMonitoringSchema().subscribe({
      next: (schema) => {
        this.monitoringSchema = schema;
      },
    });

    this.subscriptions.add(
      this.socketService.connected$.subscribe((connected) => {
        this.isConnected = connected;
      })
    );

    this.subscriptions.add(
      this.socketService.events$.subscribe((event) => {
        if (!event) {
          return;
        }
        try {
          this.applyEvent(event);
        } catch (error) {
          this.pushLifecycle('frontend_apply_error', 'applyEvent failed', {
            eventType: event.type,
            error: (error as Error).message,
          });
          this.lines.push({ role: 'system', text: `Frontend event handling failed: ${(error as Error).message}` });
        }
        this.refreshMonitoringViews();
        this.cdr.detectChanges();
      })
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  get selectedAgentTools(): string[] {
    const match = this.monitoringSchema?.agents.find((item) => item.id === this.selectedAgentId);
    return match?.tools ?? [];
  }

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

  resetMonitoringFilters(): void {
    this.monitorAgentFilter = 'all';
    this.monitorStatusFilter = 'all';
    this.monitorRequestFilter = '';
    this.monitorSearch = '';
  }

  send(): void {
    if (this.firstRunChoicePending) {
      this.lines.push({ role: 'system', text: 'Please choose local or api runtime first.' });
      return;
    }

    const content = this.input.trim();
    if (!content) {
      return;
    }

    this.lines.push({ role: 'user', text: content });

    try {
      const toolPolicy = this.buildToolPolicyPayload();
      this.socketService.sendUserMessage(content, {
        agentId: this.selectedAgentId,
        model: this.model.trim() || undefined,
        sessionId: this.sessionId || undefined,
        toolPolicy,
      });
      this.lines.push({ role: 'system', text: 'Agent is working...' });
      this.pushLifecycle('frontend_send', 'Message sent to websocket', {
        chars: content.length,
        agent: this.selectedAgentId,
        model: this.model.trim() || '(default)',
        sessionId: this.sessionId || '(new)',
        toolPolicy,
      });
      this.activeAssistantIndex = null;
      this.input = '';
    } catch (error) {
      this.lines.push({ role: 'system', text: `Send failed: ${(error as Error).message}` });
      this.pushLifecycle('frontend_send_failed', 'Message send failed', {
        error: (error as Error).message,
      });
    }
  }

  spawnSubrun(): void {
    if (this.firstRunChoicePending) {
      this.lines.push({ role: 'system', text: 'Please choose local or api runtime first.' });
      return;
    }

    const content = this.input.trim();
    if (!content) {
      return;
    }

    this.lines.push({ role: 'user', text: `[subrun] ${content}` });

    try {
      const toolPolicy = this.buildToolPolicyPayload();
      this.socketService.sendSubrunSpawn(content, {
        agentId: this.selectedAgentId,
        model: this.model.trim() || undefined,
        sessionId: this.sessionId || undefined,
        toolPolicy,
      });
      this.lines.push({ role: 'system', text: 'Subrun accepted and running in background...' });
      this.pushLifecycle('frontend_subrun_send', 'Subrun spawn sent to websocket', {
        chars: content.length,
        agent: this.selectedAgentId,
        model: this.model.trim() || '(default)',
        sessionId: this.sessionId || '(new)',
        toolPolicy,
      });
      this.input = '';
    } catch (error) {
      this.lines.push({ role: 'system', text: `Subrun spawn failed: ${(error as Error).message}` });
      this.pushLifecycle('frontend_subrun_send_failed', 'Subrun spawn failed', {
        error: (error as Error).message,
      });
    }
  }

  switchRuntime(): void {
    if (this.runtimeSwitching) {
      return;
    }
    this.runtimeSwitching = true;
    this.pushLifecycle('frontend_switch', `Runtime switch requested: ${this.runtimeTarget}`);

    try {
      this.socketService.sendRuntimeSwitchRequest(this.runtimeTarget, this.sessionId || undefined);
    } catch (error) {
      this.runtimeSwitching = false;
      this.lines.push({ role: 'system', text: `Runtime switch failed: ${(error as Error).message}` });
    }
  }

  chooseInitialRuntime(target: 'local' | 'api'): void {
    this.runtimeTarget = target;
    localStorage.setItem('preferredRuntime', target);
    this.firstRunChoicePending = false;
    this.switchRuntime();
  }

  resetRuntimePreference(): void {
    localStorage.removeItem('preferredRuntime');
    this.firstRunChoicePending = true;
    this.runtimeSwitching = false;
    this.lines.push({ role: 'system', text: 'Runtime preference reset. Please choose local or api.' });
    this.pushLifecycle('frontend_runtime_reset', 'Runtime preference reset by user');
  }

  quickResetSession(): void {
    const previousSessionId = this.sessionId;
    this.sessionId = '';
    this.input = '';
    this.activeAssistantIndex = null;
    this.lines = [];
    this.lifecycleLines = [];
    this.reasoningLines = [];
    this.agentActivityMap.clear();
    this.requestActivityMap.clear();
    this.agentActivities = [];
    this.requestActivities = [];
    this.resetMonitoringFilters();

    this.lines.push({ role: 'system', text: 'Session reset complete. Next message starts a fresh session.' });
    this.pushLifecycle('frontend_session_reset', 'Session reset by user', {
      previousSessionId: previousSessionId || '(none)',
      nextSessionId: '(new)',
    });
  }

  private applyEvent(event: AgentSocketEvent): void {
    this.pushLifecycle(
      event.type,
      this.describeEvent(event),
      {
        stage: event.stage,
        requestId: event.request_id,
        sessionId: event.session_id,
        ...(event.details ?? {}),
      },
      event.ts
    );

    this.updateMonitoring(event);

    if (event.type === 'status' && event.message) {
      if (event.session_id) {
        this.sessionId = event.session_id;
      }
      if (event.runtime === 'local' || event.runtime === 'api') {
        this.runtimeTarget = event.runtime;
        localStorage.setItem('preferredRuntime', event.runtime);
        this.firstRunChoicePending = false;
      }
      if (event.model) {
        this.model = event.model;
      }
      this.lines.push({ role: 'system', text: event.message });
      return;
    }

    if (event.type === 'runtime_switch_progress') {
      return;
    }

    if (event.type === 'runtime_switch_done') {
      if (event.runtime === 'local' || event.runtime === 'api') {
        this.runtimeTarget = event.runtime;
        localStorage.setItem('preferredRuntime', event.runtime);
      }
      if (event.model) {
        this.model = event.model;
      }
      this.runtimeSwitching = false;
      this.lines.push({ role: 'system', text: `Runtime active: ${event.runtime} (${event.model ?? 'model'})` });
      this.agentsService.getRuntimeStatus().subscribe({
        next: (status) => {
          this.apiModelsAvailable = status.apiModelsAvailable ?? null;
          const modelsCount = status.apiModelsCount ?? null;
          const modelsError = status.apiModelsError ?? null;
          if (modelsError) {
            this.apiModelsHint = modelsError;
          } else if (modelsCount !== null) {
            this.apiModelsHint = `${modelsCount} model(s) visible`;
          } else {
            this.apiModelsHint = '';
          }
        },
      });
      return;
    }

    if (event.type === 'runtime_switch_error') {
      this.runtimeSwitching = false;
      this.lines.push({ role: 'system', text: `Runtime switch error: ${event.message ?? 'unknown error'}` });
      return;
    }

    if (event.type === 'subrun_status') {
      const status = event.status ?? event.message ?? 'unknown';
      this.lines.push({ role: 'system', text: `Subrun status: ${String(status)}` });
      return;
    }

    if (event.type === 'subrun_announce') {
      const status = String(event.status ?? 'unknown');
      const result = String(event.result ?? event.message ?? '(not available)');
      this.lines.push({ role: 'agent', text: `Subrun (${status}): ${result}` });
      return;
    }

    if (event.type === 'socket_raw') {
      return;
    }

    if (event.type === 'sequence_gap') {
      this.lines.push({
        role: 'system',
        text: `Transport warning: ${event.message ?? 'sequence gap detected'} (token/final may be incomplete).`,
      });
      return;
    }

    if (event.type === 'error' && event.message) {
      this.lines.push({ role: 'system', text: `Error: ${event.message}` });
      this.activeAssistantIndex = null;
      return;
    }

    if (event.type === 'agent_step' && event.step) {
      this.lines.push({ role: 'system', text: `Step: ${event.step}` });
      return;
    }

    if (event.type === 'token' && event.token) {
      if (this.activeAssistantIndex === null) {
        this.lines.push({ role: 'agent', text: '' });
        this.activeAssistantIndex = this.lines.length - 1;
      }
      this.lines[this.activeAssistantIndex].text += event.token;
      return;
    }

    if (event.type === 'final' && event.message) {
      if (this.activeAssistantIndex === null) {
        this.lines.push({ role: 'agent', text: event.message });
      }
      this.activeAssistantIndex = null;
    }
  }

  private updateMonitoring(event: AgentSocketEvent): void {
    const timestamp = event.ts ?? new Date().toISOString();
    const agentId = (event.agent || this.selectedAgentId || 'unknown').toString();
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
    if (event.stage === 'request_completed' || (event.stage || '').startsWith('request_failed')) {
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
      if ((event.stage || '').startsWith('request_failed') || event.type === 'error') {
        existingRequest.status = 'failed';
        existingRequest.error = event.message || existingRequest.error;
      }

      this.requestActivityMap.set(event.request_id, existingRequest);
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

  private resolveAgentRole(agentId: string): string {
    const fromSchema = this.monitoringSchema?.agents.find((item) => item.id === agentId);
    if (fromSchema) {
      return fromSchema.role;
    }
    const fromAgents = this.availableAgents.find((item) => item.id === agentId);
    return fromAgents?.role ?? 'agent';
  }

  private refreshMonitoringViews(): void {
    this.agentActivities = [...this.agentActivityMap.values()].sort((a, b) =>
      b.updatedAt.localeCompare(a.updatedAt)
    );
    this.requestActivities = [...this.requestActivityMap.values()]
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      .slice(0, 200);
  }

  private buildToolPolicyPayload(): ToolPolicyPayload | undefined {
    const allow = this.parseCsvTools(this.toolAllowInput);
    const deny = this.parseCsvTools(this.toolDenyInput);
    if (allow.length === 0 && deny.length === 0) {
      return undefined;
    }
    return {
      allow: allow.length > 0 ? allow : undefined,
      deny: deny.length > 0 ? deny : undefined,
    };
  }

  private parseCsvTools(value: string): string[] {
    return value
      .split(',')
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
  }

  private describeEvent(event: AgentSocketEvent): string {
    if (event.type === 'lifecycle' && event.stage) {
      return event.stage;
    }
    if (event.type === 'status') {
      return event.message ?? 'status';
    }
    if (event.type === 'agent_step') {
      return event.step ?? 'agent_step';
    }
    if (event.type === 'error') {
      return event.message ?? 'error';
    }
    if (event.type === 'runtime_switch_progress') {
      return `${event.step ?? 'runtime_step'} (attempt ${event.attempt ?? 1}): ${event.message ?? ''}`.trim();
    }
    if (event.type === 'runtime_switch_done') {
      return `runtime_switch_done -> ${event.runtime ?? 'unknown'}`;
    }
    if (event.type === 'runtime_switch_error') {
      return event.message ?? 'runtime_switch_error';
    }
    if (event.type === 'subrun_status') {
      return `subrun_status ${event.status ?? 'unknown'}`;
    }
    if (event.type === 'subrun_announce') {
      return `subrun_announce ${event.status ?? 'unknown'}`;
    }
    if (event.type === 'final') {
      return 'final';
    }
    if (event.type === 'token') {
      return 'token';
    }
    return event.type;
  }

  private pushLifecycle(type: string, text: string, details?: Record<string, unknown>, ts?: string): void {
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
}
