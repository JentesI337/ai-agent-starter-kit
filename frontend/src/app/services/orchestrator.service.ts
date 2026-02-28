import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

// --- Contracts / Schemas ---

export type TaskComplexity = 'simple' | 'moderate' | 'complex';
export type ModelTier = 'small' | 'mid' | 'high';
export type TaskStatus = 'pending' | 'active' | 'completed' | 'failed' | 'blocked';
export type AgentRole = 'planner' | 'coder' | 'reviewer';

export interface ModelCapabilityProfile {
  model_id: string;
  tier: ModelTier;
  max_context: number;
  reasoning_depth: number;
  reflection_passes: number;
  combine_steps: boolean;
  temperature: number;
  cost_per_1k_tokens: number;
}

export interface PlanStep {
  step_id: number;
  description: string;
  tool: string | null;
  tool_args: Record<string, unknown>;
  depends_on: number[];
}

export interface PlannerOutput {
  steps: PlanStep[];
  estimated_complexity: TaskComplexity;
  reasoning: string;
}

export interface FileChange {
  path: string;
  action: string;
  content: string;
}

export interface CoderOutput {
  changes: FileChange[];
  commands: string[];
  reasoning: string;
  success: boolean;
  error: string | null;
}

export interface ReviewIssue {
  severity: 'info' | 'warning' | 'error';
  file: string | null;
  message: string;
}

export interface ReviewerOutput {
  approved: boolean;
  issues: ReviewIssue[];
  confidence_score: number;
  reasoning: string;
}

export interface GraphSummary {
  total: number;
  by_status: Record<string, number>;
  ready: string[];
  blocked: string[];
  is_complete: boolean;
}

export interface OrchestratorRunResult {
  request_id: string;
  plan: PlannerOutput;
  results: CoderOutput[];
  review: ReviewerOutput | null;
  graph_summary: GraphSummary;
  success: boolean;
}

export interface OrchestratorRunResponse {
  ok: boolean;
  runtime: string;
  sessionId: string;
  requestId: string;
  result: OrchestratorRunResult;
  eventCount: number;
}

export interface OrchestratorModelsResponse {
  models: ModelCapabilityProfile[];
  count: number;
}

export interface OrchestratorStateResponse {
  store: {
    total_tasks: number;
    by_status: Record<string, number>;
    timestamp: string;
  };
  graph: GraphSummary;
}

@Injectable({ providedIn: 'root' })
export class OrchestratorService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  run(message: string, model?: string, sessionId?: string) {
    return this.http.post<OrchestratorRunResponse>(
      `${this.apiBase}/api/orchestrator/run`,
      { message, model: model || undefined, session_id: sessionId || undefined }
    );
  }

  getModels() {
    return this.http.get<OrchestratorModelsResponse>(
      `${this.apiBase}/api/orchestrator/models`
    );
  }

  getState() {
    return this.http.get<OrchestratorStateResponse>(
      `${this.apiBase}/api/orchestrator/state`
    );
  }
}
