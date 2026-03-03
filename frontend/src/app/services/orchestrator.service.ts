import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

export interface OrchestratorPlan {
  steps: string[];
  [key: string]: unknown;
}

export interface OrchestratorChange {
  action: string;
  path: string;
  [key: string]: unknown;
}

export interface OrchestratorCoderResult {
  reasoning?: string;
  changes?: OrchestratorChange[];
  [key: string]: unknown;
}

export interface OrchestratorIssue {
  severity: string;
  message: string;
  [key: string]: unknown;
}

export interface OrchestratorReview {
  approved: boolean;
  confidence_score: number;
  issues?: OrchestratorIssue[];
  [key: string]: unknown;
}

export interface GraphSummary {
  [key: string]: unknown;
}

export interface OrchestratorRunResult {
  plan?: OrchestratorPlan;
  results?: OrchestratorCoderResult[];
  review?: OrchestratorReview;
  graph_summary?: GraphSummary;
  [key: string]: unknown;
}

export interface OrchestratorRunResponse {
  result: OrchestratorRunResult;
  [key: string]: unknown;
}

export interface ModelCapabilityProfile {
  model_id: string;
  tier: string;
  max_context: number;
  reasoning_depth: number;
  reflection_passes: number;
  combine_steps: boolean;
  temperature: number;
  cost_per_1k_tokens: number;
  [key: string]: unknown;
}

export interface OrchestratorModelsResponse {
  models: ModelCapabilityProfile[];
  [key: string]: unknown;
}

export interface OrchestratorStateStore {
  total_tasks: number;
  by_status: Record<string, number>;
  timestamp: string;
  [key: string]: unknown;
}

export interface OrchestratorTaskGraph {
  total: number;
  is_complete: boolean;
  by_status: Record<string, number>;
  ready: string[];
  blocked: string[];
  [key: string]: unknown;
}

export interface OrchestratorStateResponse {
  store: OrchestratorStateStore;
  graph?: OrchestratorTaskGraph;
  [key: string]: unknown;
}

@Injectable({ providedIn: 'root' })
export class OrchestratorService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  run(message: string) {
    return this.http.post<OrchestratorRunResponse>(`${this.apiBase}/api/orchestrator/run`, { message });
  }

  getState() {
    return this.http.get<OrchestratorStateResponse>(`${this.apiBase}/api/orchestrator/state`);
  }

  getModels() {
    return this.http.get<OrchestratorModelsResponse>(`${this.apiBase}/api/orchestrator/models`);
  }
}
