import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { AgentSocketEvent, AgentSocketService } from '../services/agent-socket.service';
import { AgentDescriptor, AgentsService } from '../services/agents.service';

interface ChatLine {
  role: 'user' | 'agent' | 'system';
  text: string;
}

interface LifecycleLine {
  time: string;
  type: string;
  text: string;
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
  model = '';
  runtimeTarget: 'local' | 'api' = 'local';
  firstRunChoicePending = false;
  selectedAgentId = 'head-coder';
  sessionId = '';
  runtimeSwitching = false;
  apiModelsAvailable: boolean | null = null;
  apiModelsHint = '';
  agents: AgentDescriptor[] = [];
  isConnected = false;
  lines: ChatLine[] = [];
  lifecycleLines: LifecycleLine[] = [];
  private activeAssistantIndex: number | null = null;
  private readonly subscriptions = new Subscription();
  private readonly wsUrl = 'ws://localhost:8000/ws/agent';

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

    this.agentsService.getAgents().subscribe({
      next: (agents) => {
        this.agents = agents;
        if (agents.length > 0) {
          this.selectedAgentId = agents[0].id;
          this.model = agents[0].defaultModel ?? this.model;
        }
      },
      error: () => {
        this.lines.push({ role: 'system', text: 'Could not load agents list.' });
      },
    });

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
        console.info('[ws:event]', event.type, {
          stage: event.stage,
          requestId: event.request_id,
          sessionId: event.session_id,
          message: event.message,
          model: event.model,
          runtime: event.runtime,
        });
        try {
          this.applyEvent(event);
        } catch (error) {
          this.pushLifecycle('frontend_apply_error', 'applyEvent failed', {
            eventType: event.type,
            error: (error as Error).message,
          });
          this.lines.push({ role: 'system', text: `Frontend event handling failed: ${(error as Error).message}` });
        }
        this.cdr.detectChanges();
      })
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
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
      this.socketService.sendUserMessage(content, {
        agentId: this.selectedAgentId,
        model: this.model.trim() || undefined,
        sessionId: this.sessionId || undefined,
      });
      this.lines.push({ role: 'system', text: 'Agent is working...' });
      this.pushLifecycle('frontend_send', 'Message sent to websocket', {
        chars: content.length,
        agent: this.selectedAgentId,
        model: this.model.trim() || '(default)',
        sessionId: this.sessionId || '(new)',
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

  private applyEvent(event: AgentSocketEvent): void {
    this.pushLifecycle(event.type, this.describeEvent(event), {
      stage: event.stage,
      requestId: event.request_id,
      sessionId: event.session_id,
      ...(event.details ?? {}),
    }, event.ts);

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

    if (event.type === 'socket_raw') {
      this.pushLifecycle('socket_raw', event.message ?? 'socket_raw');
      return;
    }

    if (event.type === 'sequence_gap') {
      this.lines.push({
        role: 'system',
        text: `Transport warning: ${event.message ?? 'sequence gap detected'} (token/final may be incomplete).`,
      });
      this.pushLifecycle('sequence_gap', event.message ?? 'sequence gap detected', {
        seq: event.seq,
      });
      return;
    }

    if (event.type === 'error' && event.message) {
      this.pushLifecycle('frontend_error_event', 'Error event received', {
        message: event.message,
        requestId: event.request_id,
        sessionId: event.session_id,
      }, event.ts);
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
    if (this.lifecycleLines.length > 300) {
      this.lifecycleLines = this.lifecycleLines.slice(0, 300);
    }
  }
}
