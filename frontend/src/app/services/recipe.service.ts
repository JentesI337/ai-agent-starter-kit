import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

export interface RecipeCheckpoint {
  id: string;
  label: string;
  verification: string;
  verification_mode: 'assert' | 'agent';
  required: boolean;
  order: number;
}

export interface RecipeConstraints {
  max_duration_seconds?: number | null;
  max_tool_calls?: number | null;
  max_llm_tokens?: number | null;
  tools_allowed?: string[] | null;
  tools_denied?: string[] | null;
  require_human_approval_before: string[];
}

export interface StrictStep {
  id: string;
  label: string;
  instruction: string;
  tool?: string | null;
  tool_params?: Record<string, unknown> | null;
  timeout_seconds?: number | null;
  retry_count: number;
}

export interface RecipeDef {
  id: string;
  name: string;
  description: string;
  goal: string;
  mode: 'adaptive' | 'strict';
  constraints: RecipeConstraints;
  checkpoints: RecipeCheckpoint[];
  strict_steps?: StrictStep[] | null;
  agent_id?: string | null;
  triggers: Record<string, unknown>[];
  checkpoint_count: number;
  step_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RecipeCreatePayload {
  id?: string;
  name: string;
  description?: string;
  goal?: string;
  mode?: 'adaptive' | 'strict';
  constraints?: Partial<RecipeConstraints>;
  checkpoints?: Partial<RecipeCheckpoint>[];
  strict_steps?: Partial<StrictStep>[];
  agent_id?: string;
  triggers?: Record<string, unknown>[];
}

export interface RecipeUpdatePayload {
  id: string;
  name?: string;
  description?: string;
  goal?: string;
  mode?: 'adaptive' | 'strict';
  constraints?: Partial<RecipeConstraints>;
  checkpoints?: Partial<RecipeCheckpoint>[];
  strict_steps?: Partial<StrictStep>[];
  agent_id?: string;
  triggers?: Record<string, unknown>[];
}

export interface RecipeListResponse {
  schema: string;
  items: RecipeDef[];
  count: number;
}

export interface RecipeGetResponse {
  schema: string;
  recipe: RecipeDef;
}

export interface BudgetSnapshot {
  tokens_used: number;
  tool_calls_used: number;
  duration_seconds: number;
}

export interface RecipeRunSummary {
  run_id: string;
  status: string;
  mode: string;
  started_at: string;
  completed_at?: string;
  budget_used: BudgetSnapshot;
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

@Injectable({ providedIn: 'root' })
export class RecipeService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  list(): Observable<RecipeListResponse> {
    return this.http.post<RecipeListResponse>(`${this.apiBase}/api/control/recipes.list`, {});
  }

  get(id: string): Observable<RecipeGetResponse> {
    return this.http.post<RecipeGetResponse>(`${this.apiBase}/api/control/recipes.get`, { recipe_id: id });
  }

  create(payload: RecipeCreatePayload): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/recipes.create`, payload);
  }

  update(payload: RecipeUpdatePayload): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/recipes.update`, payload);
  }

  delete(id: string): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/recipes.delete`, { recipe_id: id });
  }

  validate(payload: Partial<RecipeCreatePayload>): Observable<any> {
    return this.http.post(`${this.apiBase}/api/control/recipes.validate`, payload);
  }

  listRuns(recipeId: string, limit = 20): Observable<{ items: RecipeRunSummary[]; count: number }> {
    return this.http.post<{ items: RecipeRunSummary[]; count: number }>(
      `${this.apiBase}/api/control/recipes.runs.list`,
      { recipe_id: recipeId, limit },
    );
  }

  getRun(recipeId: string, runId: string): Observable<any> {
    return this.http.post(
      `${this.apiBase}/api/control/recipes.runs.get`,
      { recipe_id: recipeId, run_id: runId },
    );
  }

  executeRecipe(recipeId: string, message?: string): Observable<{ status: string; recipe_id: string; run_id: string }> {
    return this.http.post<{ status: string; recipe_id: string; run_id: string }>(
      `${this.apiBase}/api/control/recipes.execute`,
      { recipe_id: recipeId, message: message ?? '' },
    );
  }

  resumeRun(runId: string, resumeData?: Record<string, unknown>): Observable<{ status: string; run_id: string }> {
    return this.http.post<{ status: string; run_id: string }>(
      `${this.apiBase}/api/control/recipes.runs.resume`,
      { run_id: runId, resume_data: resumeData },
    );
  }
}
