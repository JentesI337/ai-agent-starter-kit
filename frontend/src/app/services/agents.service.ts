import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

export interface AgentDescriptor {
  id: string;
  name: string;
  role: string;
  status: string;
  defaultModel?: string;
}

export interface RuntimeStatus {
  runtime: 'local' | 'api';
  baseUrl: string;
  model: string;
  authenticated: boolean;
}

@Injectable({ providedIn: 'root' })
export class AgentsService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  getAgents() {
    return this.http.get<AgentDescriptor[]>(`${this.apiBase}/api/agents`);
  }

  getRuntimeStatus() {
    return this.http.get<RuntimeStatus>(`${this.apiBase}/api/runtime/status`);
  }
}
