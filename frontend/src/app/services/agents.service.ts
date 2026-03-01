import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

export interface RuntimeStatus {
  runtime: 'local' | 'api';
  baseUrl: string;
  model: string;
  authenticated: boolean;
  apiModelsAvailable?: boolean | null;
  apiModelsCount?: number | null;
  apiModelsError?: string | null;
}

export interface AgentDescriptor {
  id: string;
  name: string;
  role: string;
  status: string;
  defaultModel: string;
}

export interface PresetDescriptor {
  id: string;
  toolPolicy: {
    allow?: string[];
    deny?: string[];
  };
}

export interface MonitoringSchema {
  lifecycleStages: string[];
  eventTypes: string[];
  reasoningVisibility: {
    chainOfThought: string;
    observableTrace: string;
  };
  agents: Array<{
    id: string;
    name: string;
    role: string;
    tools: string[];
  }>;
}

export interface RunsAuditResponse {
  schema: 'runs.audit.v1';
  run: {
    run_id: string;
    session_id: string;
    status: string | null;
    created_at: string;
    updated_at: string;
  };
  telemetry: {
    event_count: number;
    lifecycle_count: number;
    lifecycle_stages: Record<string, number>;
    blocked_with_reason: Record<string, number>;
    tool_selection_empty_reasons: Record<string, number>;
    tool_started: number;
    tool_completed: number;
    tool_failed: number;
    tool_loop_warn: number;
    tool_loop_blocked: number;
    tool_budget_exceeded: number;
    tool_audit_summary: number;
  };
}

export interface BackendPingResult {
  ok: boolean;
  message?: string;
  [key: string]: unknown;
}

export interface AgentTestResult {
  message?: string;
  final?: string;
  [key: string]: unknown;
}

export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  base_agent_id: string;
  workflow_steps: string[];
  allow_subrun_delegation?: boolean;
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  } | null;
}

export interface CreateCustomAgentPayload {
  id?: string;
  name: string;
  description?: string;
  base_agent_id: string;
  workflow_steps: string[];
  allow_subrun_delegation?: boolean;
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
}

export interface PolicyApprovalRecord {
  approval_id: string;
  run_id: string;
  session_id: string;
  agent_name: string;
  tool: string;
  resource: string;
  display_text: string;
  status: 'pending' | 'approved' | 'expired' | string;
  decision: 'allow' | 'timeout' | null | string;
  created_at: string;
  updated_at: string;
}

export interface PolicyApprovalsPendingResponse {
  schema: 'policy.approvals.pending.v1';
  items: PolicyApprovalRecord[];
  count: number;
}

export interface PolicyApprovalsAllowResponse {
  schema: 'policy.approvals.allow.v1';
  approval: PolicyApprovalRecord;
}

@Injectable({ providedIn: 'root' })
export class AgentsService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  getRuntimeStatus() {
    return this.http.get<RuntimeStatus>(`${this.apiBase}/api/runtime/status`);
  }

  getAgents() {
    return this.http.get<AgentDescriptor[]>(`${this.apiBase}/api/agents`);
  }

  getPresets() {
    return this.http.get<PresetDescriptor[]>(`${this.apiBase}/api/presets`);
  }

  getMonitoringSchema() {
    return this.http.get<MonitoringSchema>(`${this.apiBase}/api/monitoring/schema`);
  }

  getRunAudit(runId: string) {
    return this.http.post<RunsAuditResponse>(`${this.apiBase}/api/control/runs.audit`, { run_id: runId });
  }

  testBackendPing() {
    return this.http.get<BackendPingResult>(`${this.apiBase}/api/test/ping`);
  }

  testAgentCall(message: string) {
    return this.http.post<AgentTestResult>(`${this.apiBase}/api/test/agent`, { message });
  }

  getCustomAgents() {
    return this.http.get<CustomAgentDefinition[]>(`${this.apiBase}/api/custom-agents`);
  }

  createCustomAgent(payload: CreateCustomAgentPayload) {
    return this.http.post<CustomAgentDefinition>(`${this.apiBase}/api/custom-agents`, payload);
  }

  deleteCustomAgent(agentId: string) {
    return this.http.delete<{ ok: boolean; deletedId: string }>(`${this.apiBase}/api/custom-agents/${encodeURIComponent(agentId)}`);
  }

  getPendingPolicyApprovals(payload?: { run_id?: string; session_id?: string; limit?: number }) {
    return this.http.post<PolicyApprovalsPendingResponse>(`${this.apiBase}/api/control/policy-approvals.pending`, payload ?? {});
  }

  allowPolicyApproval(approvalId: string) {
    return this.http.post<PolicyApprovalsAllowResponse>(`${this.apiBase}/api/control/policy-approvals.allow`, {
      approval_id: approvalId,
    });
  }
}
