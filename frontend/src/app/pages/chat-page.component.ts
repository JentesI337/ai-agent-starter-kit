import { CommonModule } from '@angular/common';
import {
  AfterViewChecked,
  ChangeDetectorRef,
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  OnInit,
  ViewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { Subscription } from 'rxjs';

import { AgentSocketEvent, AgentSocketService, ToolPolicyPayload } from '../services/agent-socket.service';
import { AgentStateService, ChatLine, PolicyApprovalItem } from '../services/agent-state.service';
import { MonitoringService } from '../services/monitoring.service';
import { SecureStorageService } from '../services/secure-storage.service';
import {
  AgentDescriptor,
  AgentsService,
  MonitoringSchema,
  PresetDescriptor,
} from '../services/agents.service';

@Component({
  selector: 'app-chat-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.scss',
})
export class ChatPageComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('chatScroll') private chatScrollEl?: ElementRef<HTMLElement>;

  input = '';
  toolAllowInput = '';
  toolDenyInput = '';
  model = '';
  runtimeTarget: 'local' | 'api' = 'local';
  firstRunChoicePending = false;
  selectedAgentId = 'head-agent';
  selectedPresetId = '';

  sessionId = '';
  runtimeSwitching = false;

  apiModelsAvailable: boolean | null = null;
  apiModelsHint = '';
  isConnected = false;
  lines: ChatLine[] = [];
  availableAgents: AgentDescriptor[] = [];
  availablePresets: PresetDescriptor[] = [];

  monitoringSchema: MonitoringSchema | null = null;
  policyApprovals: PolicyApprovalItem[] = [];
  pendingClarificationQuestion = '';

  // UI state
  settingsOpen = false;
  shouldScroll = false;

  private readonly subscriptions = new Subscription();
  private readonly wsUrl = 'ws://localhost:8000/ws/agent';
  private readonly policyApprovalBusy = new Set<string>();
  private approvalPollTimer: number | null = null;
  private approvalPollInFlight = false;
  private readonly approvalPollIntervalMs = 4000;

  constructor(
    private readonly socketService: AgentSocketService,
    private readonly agentsService: AgentsService,
    private readonly agentState: AgentStateService,
    private readonly monitoringService: MonitoringService,
    private readonly cdr: ChangeDetectorRef,
    private readonly secureStorage: SecureStorageService,
    private readonly sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.socketService.connect(this.wsUrl);
    this.agentState.init();

    this.secureStorage.getItem('preferredRuntime').then(persistedRuntime => {
      if (persistedRuntime === 'local' || persistedRuntime === 'api') {
        this.runtimeTarget = persistedRuntime;
        this.firstRunChoicePending = false;
      } else {
        this.firstRunChoicePending = true;
      }
      this.cdr.markForCheck();
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
          this.secureStorage.setItem('preferredRuntime', status.runtime);
        }
      },
    });

    this.agentsService.getAgents().subscribe({
      next: (agents) => {
        this.availableAgents = agents;
        this.monitoringService.availableAgents = agents;
        const selectedExists = agents.some((agent) => agent.id === this.selectedAgentId);
        if (!selectedExists && agents.length > 0) {
          this.selectedAgentId = agents[0].id;
        }
      },
    });

    this.agentsService.getPresets().subscribe({
      next: (presets) => {
        this.availablePresets = presets;
        if (this.selectedPresetId && !presets.some((preset) => preset.id === this.selectedPresetId)) {
          this.selectedPresetId = '';
        }
      },
    });

    this.agentsService.getMonitoringSchema().subscribe({
      next: (schema) => {
        this.monitoringSchema = schema;
        this.monitoringService.monitoringSchema = schema;
      },
    });

    this.refreshPendingPolicyApprovals();

    this.subscriptions.add(
      this.agentState.chatLines$.subscribe(lines => {
        this.lines = lines;
        this.shouldScroll = true;
      }),
    );

    this.subscriptions.add(
      this.socketService.connected$.subscribe((connected) => {
        this.isConnected = connected;
      }),
    );

    this.subscriptions.add(
      this.agentState.approvals$.subscribe(approvals => {
        this.policyApprovals = approvals;
        this.ensureApprovalPolling();
        this.cdr.markForCheck();
      }),
    );

    this.subscriptions.add(
      this.agentState.clarification$.subscribe(question => {
        if (question) {
          this.pendingClarificationQuestion = question;
          this.agentState.resetActiveAssistant();
          this.agentState.pushChatLine({ role: 'agent', text: question });
          this.cdr.markForCheck();
        }
      }),
    );

    this.subscriptions.add(
      this.socketService.events$.subscribe((event) => {
        if (!event) return;
        try {
          this.applyEvent(event);
        } catch (error) {
          this.monitoringService.pushLifecycle('frontend_apply_error', 'applyEvent failed', {
            eventType: event.type,
            error: (error as Error).message,
          });
          this.agentState.pushChatLine({ role: 'system', text: `Frontend event handling failed: ${(error as Error).message}` });
        }
        this.monitoringService.refreshViews();
        this.cdr.detectChanges();
      }),
    );
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll && this.chatScrollEl) {
      const el = this.chatScrollEl.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    this.stopApprovalPolling();
  }

  get selectedAgentTools(): string[] {
    const match = this.monitoringSchema?.agents.find((item) => item.id === this.selectedAgentId);
    return match?.tools ?? [];
  }

  get selectedAgentRole(): string {
    return this.availableAgents.find(a => a.id === this.selectedAgentId)?.role ?? '';
  }

  get isAgentWorking(): boolean {
    return this.lines.length > 0 && this.lines[this.lines.length - 1].text === 'Agent is working...';
  }

  // ── Base64 image extraction ──────────────────────────

  private readonly base64ImageCache = new WeakMap<ChatLine, { text: string; images: SafeUrl[] }>();

  getLineImages(line: ChatLine): SafeUrl[] {
    const cached = this.base64ImageCache.get(line);
    if (cached && cached.text === line.text) return cached.images;
    const images: SafeUrl[] = [];
    const text = line.text || '';

    const jsonPattern = /\{"type"\s*:\s*"image"\s*,\s*"format"\s*:\s*"(\w+)"\s*,\s*"data"\s*:\s*"([A-Za-z0-9+/=\s]+)"\s*\}/g;
    let m: RegExpExecArray | null;
    while ((m = jsonPattern.exec(text)) !== null) {
      const format = m[1] || 'png';
      const data = m[2].replace(/\s/g, '');
      if (data.length > 16) {
        images.push(this.sanitizer.bypassSecurityTrustUrl(`data:image/${format};base64,${data}`));
      }
    }

    if (images.length === 0) {
      const dataUriPattern = /data:image\/(png|jpeg|jpg|gif|webp|svg\+xml);base64,([A-Za-z0-9+/=]+)/g;
      while ((m = dataUriPattern.exec(text)) !== null) {
        const data = m[2];
        if (data.length > 16) {
          images.push(this.sanitizer.bypassSecurityTrustUrl(`data:image/${m[1]};base64,${data}`));
        }
      }
    }

    this.base64ImageCache.set(line, { text: line.text, images });
    return images;
  }

  getLineText(line: ChatLine): string {
    const images = this.getLineImages(line);
    if (images.length === 0) return line.text;
    let text = line.text;
    text = text.replace(/\{"type"\s*:\s*"image"\s*,\s*"format"\s*:\s*"\w+"\s*,\s*"data"\s*:\s*"[A-Za-z0-9+/=\s]+"\s*\}/g, '');
    text = text.replace(/data:image\/[a-z+]+;base64,[A-Za-z0-9+/=]+/g, '');
    return text.trim();
  }

  // ── Actions ──────────────────────────────────────

  send(): void {
    if (this.firstRunChoicePending) {
      this.agentState.pushChatLine({ role: 'system', text: 'Please choose local or api runtime first.' });
      return;
    }

    const content = this.input.trim();
    if (!content) return;

    this.agentState.pushChatLine({ role: 'user', text: content });

    try {
      const toolPolicy = this.buildToolPolicyPayload();
      const isClarificationResponse = this.pendingClarificationQuestion.trim().length > 0;
      if (isClarificationResponse) {
        this.socketService.sendClarificationResponse(content, {
          agentId: this.selectedAgentId,
          sessionId: this.sessionId || undefined,
        });
      } else {
        this.socketService.sendUserMessage(content, {
          agentId: this.selectedAgentId,
          preset: this.selectedPresetId || undefined,
          model: this.model.trim() || undefined,
          sessionId: this.sessionId || undefined,
          toolPolicy,
        });
      }
      this.agentState.pushChatLine({ role: 'system', text: 'Agent is working...' });
      this.monitoringService.pushLifecycle('frontend_send', 'Message sent to websocket', {
        sourceType: isClarificationResponse ? 'clarification_response' : 'user_message',
        chars: content.length,
        agent: this.selectedAgentId,
        preset: this.selectedPresetId || '(none)',
        model: this.model.trim() || '(default)',
        sessionId: this.sessionId || '(new)',
        toolPolicy,
      });
      this.agentState.resetActiveAssistant();
      if (isClarificationResponse) this.pendingClarificationQuestion = '';
      this.input = '';
    } catch (error) {
      this.agentState.pushChatLine({ role: 'system', text: `Send failed: ${(error as Error).message}` });
      this.monitoringService.pushLifecycle('frontend_send_failed', 'Message send failed', {
        error: (error as Error).message,
      });
    }
  }

  spawnSubrun(): void {
    if (this.firstRunChoicePending) {
      this.agentState.pushChatLine({ role: 'system', text: 'Please choose local or api runtime first.' });
      return;
    }

    const content = this.input.trim();
    if (!content) return;

    this.agentState.pushChatLine({ role: 'user', text: `[subrun] ${content}` });

    try {
      const toolPolicy = this.buildToolPolicyPayload();
      this.socketService.sendSubrunSpawn(content, {
        agentId: this.selectedAgentId,
        preset: this.selectedPresetId || undefined,
        model: this.model.trim() || undefined,
        sessionId: this.sessionId || undefined,
        toolPolicy,
      });
      this.agentState.pushChatLine({ role: 'system', text: 'Subrun accepted and running in background...' });
      this.monitoringService.pushLifecycle('frontend_subrun_send', 'Subrun spawn sent to websocket', {
        chars: content.length,
        agent: this.selectedAgentId,
        preset: this.selectedPresetId || '(none)',
        model: this.model.trim() || '(default)',
        sessionId: this.sessionId || '(new)',
        toolPolicy,
      });
      this.input = '';
    } catch (error) {
      this.agentState.pushChatLine({ role: 'system', text: `Subrun spawn failed: ${(error as Error).message}` });
    }
  }

  switchRuntime(): void {
    if (this.runtimeSwitching) return;
    this.runtimeSwitching = true;
    this.monitoringService.pushLifecycle('frontend_switch', `Runtime switch requested: ${this.runtimeTarget}`);
    try {
      this.socketService.sendRuntimeSwitchRequest(this.runtimeTarget, this.sessionId || undefined);
    } catch (error) {
      this.runtimeSwitching = false;
      this.agentState.pushChatLine({ role: 'system', text: `Runtime switch failed: ${(error as Error).message}` });
    }
  }

  chooseInitialRuntime(target: 'local' | 'api'): void {
    this.runtimeTarget = target;
    this.secureStorage.setItem('preferredRuntime', target);
    this.firstRunChoicePending = false;
    this.switchRuntime();
  }

  resetRuntimePreference(): void {
    this.secureStorage.removeItem('preferredRuntime');
    this.firstRunChoicePending = true;
    this.runtimeSwitching = false;
    this.agentState.pushChatLine({ role: 'system', text: 'Runtime preference reset. Please choose local or api.' });
    this.monitoringService.pushLifecycle('frontend_runtime_reset', 'Runtime preference reset by user');
  }

  quickResetSession(): void {
    const previousSessionId = this.sessionId;
    this.sessionId = '';
    this.input = '';
    this.agentState.resetActiveAssistant();
    this.agentState.clearChatLines();
    this.monitoringService.resetAll();
    this.policyApprovals = [];
    this.policyApprovalBusy.clear();
    this.pendingClarificationQuestion = '';
    this.stopApprovalPolling();
    this.agentState.pushChatLine({ role: 'system', text: 'Session reset. Next message starts a fresh session.' });
    this.monitoringService.pushLifecycle('frontend_session_reset', 'Session reset by user', {
      previousSessionId: previousSessionId || '(none)',
    });
  }

  @HostListener('document:keydown.escape')
  closeSettings(): void {
    this.settingsOpen = false;
  }

  // ── Policy Approvals ──────────────────────────────

  allowPolicyApproval(item: PolicyApprovalItem): void {
    if (!item?.approvalId || this.policyApprovalBusy.has(item.approvalId)) return;
    this.sendPolicyDecision(item.approvalId, 'allow_once', item.sessionId, item.runId);
  }

  allowPolicyApprovalInline(line: ChatLine): void {
    const action = line.policyAction;
    if (!action || action.busy || action.resolved) return;
    this.sendPolicyDecision(action.approvalId, 'allow_once', action.sessionId, action.runId);
    this.updateInlinePolicyActionBusy(action.approvalId, true);
  }

  executePolicyDropdownAction(line: ChatLine): void {
    const action = line.policyAction;
    if (!action || action.busy || action.resolved || !action.dropdownAction) return;
    this.sendPolicyDecision(action.approvalId, action.dropdownAction, action.sessionId, action.runId);
    this.updateInlinePolicyActionBusy(action.approvalId, true);
  }

  hasPendingPolicyAction(line: ChatLine): boolean {
    return Boolean(line.policyAction && !line.policyAction.resolved);
  }

  isPolicyApprovalBusy(approvalId: string): boolean {
    return this.policyApprovalBusy.has(approvalId);
  }

  refreshPendingPolicyApprovals(silent = false): void {
    if (this.approvalPollInFlight) return;
    this.approvalPollInFlight = true;
    const runFilter = this.monitoringService.monitorRequestFilter.trim();
    const payload = {
      run_id: runFilter || undefined,
      session_id: this.sessionId || undefined,
      limit: 100,
    };
    this.agentsService.getPendingPolicyApprovals(payload).subscribe({
      next: (response) => {
        this.agentState.refreshApprovalsFromRecords(response.items);
        this.approvalPollInFlight = false;
        this.ensureApprovalPolling();
      },
      error: (error) => {
        this.approvalPollInFlight = false;
        if (!silent) {
          this.agentState.pushChatLine({ role: 'system', text: `Approval refresh failed: ${error?.error?.detail ?? error.message}` });
        }
      },
    });
  }

  // ── Event Processing (preserved) ──────────────────

  private applyEvent(event: AgentSocketEvent): void {
    this.monitoringService.pushLifecycle(
      event.type,
      this.describeEvent(event),
      { stage: event.stage, requestId: event.request_id, sessionId: event.session_id, ...(event.details ?? {}) },
      event.ts,
    );
    this.monitoringService.updateMonitoring(event, this.selectedAgentId);

    if (
      event.type === 'lifecycle' &&
      (event.stage === 'request_completed' || event.stage === 'request_cancelled' || (event.stage || '').startsWith('request_failed'))
    ) {
      this.pendingClarificationQuestion = '';
      this.resolveInlinePolicyActionsByRequest(event.request_id ?? '');
    }

    if (event.type === 'lifecycle' && event.stage === 'policy_approval_decision_rejected') {
      const approvalIdRaw = (event.details as { approval_id?: unknown } | undefined)?.approval_id;
      const approvalId = String(approvalIdRaw ?? '').trim();
      if (approvalId) {
        this.policyApprovalBusy.delete(approvalId);
        this.updateInlinePolicyActionBusy(approvalId, false);
      }
    }

    if (event.type === 'clarification_needed') return;

    if (event.type === 'status' && event.message) {
      if (event.session_id) this.sessionId = event.session_id;
      if (event.runtime === 'local' || event.runtime === 'api') {
        this.runtimeTarget = event.runtime;
        this.secureStorage.setItem('preferredRuntime', event.runtime);
        this.firstRunChoicePending = false;
      }
      if (event.model) this.model = event.model;
      this.agentState.pushChatLine({ role: 'system', text: event.message });
      return;
    }

    if (event.type === 'runtime_switch_progress') return;

    if (event.type === 'runtime_switch_done') {
      if (event.runtime === 'local' || event.runtime === 'api') {
        this.runtimeTarget = event.runtime;
        this.secureStorage.setItem('preferredRuntime', event.runtime);
      }
      if (event.model) this.model = event.model;
      this.runtimeSwitching = false;
      this.agentState.pushChatLine({ role: 'system', text: `Runtime active: ${event.runtime} (${event.model ?? 'model'})` });
      this.agentsService.getRuntimeStatus().subscribe({
        next: (status) => {
          this.apiModelsAvailable = status.apiModelsAvailable ?? null;
          const modelsCount = status.apiModelsCount ?? null;
          const modelsError = status.apiModelsError ?? null;
          this.apiModelsHint = modelsError ? modelsError : (modelsCount !== null ? `${modelsCount} model(s) visible` : '');
        },
      });
      return;
    }

    if (event.type === 'runtime_switch_error') {
      this.runtimeSwitching = false;
      this.agentState.pushChatLine({ role: 'system', text: `Runtime switch error: ${event.message ?? 'unknown error'}` });
      return;
    }

    if (event.type === 'subrun_status') {
      this.agentState.pushChatLine({ role: 'system', text: `Subrun status: ${String(event.status ?? event.message ?? 'unknown')}` });
      return;
    }

    if (event.type === 'subrun_announce') {
      const status = String(event.status ?? 'unknown');
      const result = String(event.result ?? event.message ?? '(not available)');
      this.agentState.pushChatLine({ role: 'agent', text: `Subrun (${status}): ${result}` });
      return;
    }

    if (event.type === 'policy_approval_required') {
      const approval = event.approval;
      const approvalId = approval?.approval_id;
      if (approvalId) {
        const displayText = String(approval?.display_text ?? event.message ?? 'Approval required.');
        this.agentState.pushChatLine({
          role: 'system',
          text: displayText,
          policyAction: {
            approvalId,
            runId: String(event.request_id ?? ''),
            sessionId: String(event.session_id ?? ''),
            tool: String(approval?.tool ?? 'unknown'),
            resource: String(approval?.resource ?? ''),
            dropdownAction: '',
            busy: false,
            resolved: false,
          },
        });
      }
      return;
    }

    if (event.type === 'policy_approval_updated') {
      const approvalId = String((event.approval as { approval_id?: string } | undefined)?.approval_id ?? '');
      if (approvalId) {
        const status = String((event.approval as { status?: string } | undefined)?.status ?? '');
        this.updateInlinePolicyActionState(approvalId, status !== 'pending');
      }
      return;
    }

    if (event.type === 'socket_raw') return;

    if (event.type === 'socket_close') {
      if (this.agentState.activeAssistantIndex !== null) {
        this.agentState.resetActiveAssistant();
        this.agentState.pushChatLine({
          role: 'system',
          text: 'Connection lost while agent was responding. Response may be incomplete. Reconnecting...',
        });
      }
      return;
    }

    if (event.type === 'sequence_gap') {
      this.agentState.pushChatLine({
        role: 'system',
        text: `Transport warning: ${event.message ?? 'sequence gap detected'} (token/final may be incomplete).`,
      });
      return;
    }

    if (event.type === 'error' && event.message) {
      this.agentState.pushChatLine({ role: 'system', text: `Error: ${event.message}` });
      this.agentState.resetActiveAssistant();
      return;
    }

    if (event.type === 'agent_step' && event.step) {
      this.agentState.pushChatLine({ role: 'system', text: `Step: ${event.step}` });
      return;
    }

    if (event.type === 'token' && event.token) {
      this.agentState.appendTokenToAssistant(event.token);
      return;
    }

    if (event.type === 'final' && event.message) {
      this.agentState.finalizeAssistantMessage(event.message);
    }
  }

  // ── Private helpers ──────────────────────────────

  private refreshAgentsAndSchema(selectAgentId?: string): void {
    this.agentsService.getAgents().subscribe({
      next: (agents) => {
        this.availableAgents = agents;
        this.monitoringService.availableAgents = agents;
        if (selectAgentId && agents.some((agent) => agent.id === selectAgentId)) {
          this.selectedAgentId = selectAgentId;
          return;
        }
        if (!agents.some((agent) => agent.id === this.selectedAgentId) && agents.length > 0) {
          this.selectedAgentId = agents[0].id;
        }
      },
    });
    this.agentsService.getMonitoringSchema().subscribe({
      next: (schema) => {
        this.monitoringSchema = schema;
        this.monitoringService.monitoringSchema = schema;
      },
    });
  }

  private buildToolPolicyPayload(): ToolPolicyPayload | undefined {
    const allow = this.parseCsvTools(this.toolAllowInput);
    const deny = this.parseCsvTools(this.toolDenyInput);
    if (allow.length === 0 && deny.length === 0) return undefined;
    return {
      allow: allow.length > 0 ? allow : undefined,
      deny: deny.length > 0 ? deny : undefined,
    };
  }

  private parseCsvTools(value: string): string[] {
    return value.split(',').map(e => e.trim()).filter(e => e.length > 0);
  }

  private describeEvent(event: AgentSocketEvent): string {
    if (event.type === 'lifecycle' && event.stage) return event.stage;
    if (event.type === 'status') return event.message ?? 'status';
    if (event.type === 'agent_step') return event.step ?? 'agent_step';
    if (event.type === 'error') return event.message ?? 'error';
    if (event.type === 'runtime_switch_progress') return `${event.step ?? 'runtime_step'} (attempt ${event.attempt ?? 1}): ${event.message ?? ''}`.trim();
    if (event.type === 'runtime_switch_done') return `runtime_switch_done -> ${event.runtime ?? 'unknown'}`;
    if (event.type === 'runtime_switch_error') return event.message ?? 'runtime_switch_error';
    if (event.type === 'subrun_status') return `subrun_status ${event.status ?? 'unknown'}`;
    if (event.type === 'subrun_announce') return `subrun_announce ${event.status ?? 'unknown'}`;
    if (event.type === 'policy_approval_required') return 'policy_approval_required';
    if (event.type === 'final') return 'final';
    if (event.type === 'token') return 'token';
    return event.type;
  }

  private sendPolicyDecision(approvalId: string, decision: 'allow_once' | 'allow_session' | 'cancel' | string, sessionId: string, runId: string): void {
    this.policyApprovalBusy.add(approvalId);
    this.updateInlinePolicyActionBusy(approvalId, true);
    try {
      this.agentState.sendApprovalDecision(approvalId, decision as 'allow_once' | 'allow_session' | 'cancel', sessionId, runId);
      const messageMap: Record<string, string> = {
        allow_once: 'Policy decision sent: Allow once.',
        allow_session: 'Policy decision sent: Allow all in this session.',
        cancel: 'Policy decision sent: Cancel.',
      };
      this.agentState.pushChatLine({ role: 'system', text: messageMap[decision] || `Policy decision sent: ${decision}` });
    } catch (error: any) {
      this.policyApprovalBusy.delete(approvalId);
      this.updateInlinePolicyActionBusy(approvalId, false);
      this.agentState.pushChatLine({ role: 'system', text: `Policy decision failed: ${error?.message ?? 'unknown error'}` });
    }
  }

  private ensureApprovalPolling(): void {
    const hasPending = this.policyApprovals.some((item) => item.status === 'pending');
    if (!hasPending) { this.stopApprovalPolling(); return; }
    if (this.approvalPollTimer !== null) return;
    this.approvalPollTimer = window.setInterval(() => {
      if (!this.isConnected) return;
      if (!this.policyApprovals.some((item) => item.status === 'pending')) { this.stopApprovalPolling(); return; }
      this.refreshPendingPolicyApprovals(true);
    }, this.approvalPollIntervalMs);
  }

  private stopApprovalPolling(): void {
    if (this.approvalPollTimer !== null) {
      window.clearInterval(this.approvalPollTimer);
      this.approvalPollTimer = null;
    }
  }

  private updateInlinePolicyActionBusy(approvalId: string, busy: boolean): void {
    this.agentState.updateChatLinesByApproval(approvalId, line => ({
      ...line,
      policyAction: line.policyAction ? { ...line.policyAction, busy } : undefined,
    }));
  }

  private updateInlinePolicyActionState(approvalId: string, resolved: boolean): void {
    if (resolved) this.policyApprovalBusy.delete(approvalId);
    this.agentState.updateChatLinesByApproval(approvalId, line => ({
      ...line,
      policyAction: line.policyAction ? { ...line.policyAction, busy: false, resolved } : undefined,
    }));
  }

  private resolveInlinePolicyActionsByRequest(requestId: string): void {
    this.agentState.resolveInlinePolicyActionsByRequest(requestId);
  }
}
