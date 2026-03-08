import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  } | null;
  allow_subrun_delegation?: boolean;
}

export interface WorkflowCreatePayload {
  id?: string;
  name: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
  allow_subrun_delegation?: boolean;
}

export interface WorkflowUpdatePayload {
  id: string;
  name?: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
}

export interface WorkflowListResponse {
  schema: string;
  items: WorkflowDefinition[];
  count: number;
}

export interface WorkflowGetResponse {
  schema: string;
  workflow: WorkflowDefinition;
}

export interface WorkflowExecuteResponse {
  schema: string;
  run_id?: string;
  status?: string;
  [key: string]: unknown;
}

@Injectable({ providedIn: 'root' })
export class WorkflowService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  list(): Observable<WorkflowListResponse> {
    return this.http.post<WorkflowListResponse>(`${this.apiBase}/api/control/workflows.list`, {});
  }

  get(id: string): Observable<WorkflowGetResponse> {
    return this.http.post<WorkflowGetResponse>(`${this.apiBase}/api/control/workflows.get`, { id });
  }

  create(payload: WorkflowCreatePayload): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/workflows.create`, payload);
  }

  update(payload: WorkflowUpdatePayload): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/workflows.update`, payload);
  }

  delete(id: string): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/workflows.delete`, { id });
  }

  execute(id: string, message?: string): Observable<WorkflowExecuteResponse> {
    return this.http.post<WorkflowExecuteResponse>(`${this.apiBase}/api/control/workflows.execute`, {
      id,
      message: message ?? '',
    });
  }
}
