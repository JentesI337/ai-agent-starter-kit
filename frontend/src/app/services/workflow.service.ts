import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface WorkflowStepDef {
  id: string;
  type: 'agent' | 'connector' | 'transform' | 'condition' | 'delay';
  label?: string;
  instruction?: string;
  agent_id?: string;
  connector_id?: string;
  connector_method?: string;
  connector_params?: Record<string, string>;
  transform_expr?: string;
  condition_expr?: string;
  on_true?: string;
  on_false?: string;
  next_step?: string;
  timeout_seconds?: number;
  retry_count?: number;
}

export interface WorkflowGraphDef {
  steps: WorkflowStepDef[];
  entry_step_id: string;
}

export interface WorkflowTrigger {
  type: 'manual' | 'schedule' | 'webhook' | 'chat_command';
  cron_expression?: string;
  webhook_secret?: string;
  command_name?: string;
  last_run_at?: string;
  next_run_at?: string;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  execution_mode?: 'parallel' | 'sequential';
  workflow_graph?: WorkflowGraphDef | null;
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  } | null;
  allow_subrun_delegation?: boolean;
  triggers?: WorkflowTrigger[];
}

export interface WorkflowCreatePayload {
  id?: string;
  name: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  execution_mode?: 'parallel' | 'sequential';
  workflow_graph?: WorkflowGraphDef;
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
  allow_subrun_delegation?: boolean;
  triggers?: WorkflowTrigger[];
}

export interface WorkflowUpdatePayload {
  id: string;
  name?: string;
  description?: string;
  base_agent_id?: string;
  steps?: string[];
  execution_mode?: 'parallel' | 'sequential';
  workflow_graph?: WorkflowGraphDef;
  tool_policy?: {
    allow?: string[];
    deny?: string[];
  };
  triggers?: WorkflowTrigger[];
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

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  required_connectors: string[];
  step_count: number;
}

export interface WorkflowTemplateListResponse {
  schema: string;
  items: WorkflowTemplate[];
  count: number;
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

  listTemplates(): Observable<WorkflowTemplateListResponse> {
    return this.http.post<WorkflowTemplateListResponse>(`${this.apiBase}/api/control/workflows.templates.list`, {});
  }

  instantiateTemplate(templateId: string, overrides?: Record<string, any>): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/workflows.templates.instantiate`, {
      template_id: templateId,
      overrides: overrides ?? {},
    });
  }
}
