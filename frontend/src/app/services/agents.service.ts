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

  getMonitoringSchema() {
    return this.http.get<MonitoringSchema>(`${this.apiBase}/api/monitoring/schema`);
  }
}
