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

export interface CustomAgentDefinition {
  id: string;
  name: string;
  description: string;
  base_agent_id: string;
  workflow_steps: string[];
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
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
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

  getCustomAgents() {
    return this.http.get<CustomAgentDefinition[]>(`${this.apiBase}/api/custom-agents`);
  }

  createCustomAgent(payload: CreateCustomAgentPayload) {
    return this.http.post<CustomAgentDefinition>(`${this.apiBase}/api/custom-agents`, payload);
  }

  deleteCustomAgent(agentId: string) {
    return this.http.delete<{ ok: boolean; deletedId: string }>(`${this.apiBase}/api/custom-agents/${encodeURIComponent(agentId)}`);
  }
}
