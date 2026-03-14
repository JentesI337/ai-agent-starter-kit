import { HttpClient } from '@angular/common/http';
import { Injectable, NgZone } from '@angular/core';
import { Observable, Subject } from 'rxjs';

export interface RecipeExecutionEvent {
  type:
    | 'recipe_started'
    | 'recipe_checkpoint_passed'
    | 'recipe_checkpoint_failed'
    | 'recipe_step_started'
    | 'recipe_step_completed'
    | 'recipe_step_failed'
    | 'recipe_completed'
    | 'recipe_failed'
    | 'recipe_paused'
    | 'recipe_resumed';
  run_id?: string;
  recipe_id?: string;
  recipe_name?: string;
  checkpoint_id?: string;
  label?: string;
  passed?: boolean;
  explanation?: string;
  status?: string;
  error?: string;
  checkpoints?: Array<{ id: string; label: string; required: boolean }>;
  steps?: Array<{ id: string; label: string; tool?: string }>;
  checkpoints_reached?: Record<string, unknown>;
  budget_used?: { tokens_used: number; tool_calls_used: number; duration_seconds: number };
  agent_response_preview?: string;
  step_id?: string;
  tool?: string;
  output_preview?: string;
  duration_ms?: number;
  retry_attempts?: number;
  pause_reason?: string;
  [key: string]: unknown;
}

@Injectable({ providedIn: 'root' })
export class RecipeExecutionService {
  private readonly apiBase = 'http://localhost:8000';
  private eventSource: EventSource | null = null;
  private eventsSubject = new Subject<RecipeExecutionEvent>();

  constructor(
    private readonly http: HttpClient,
    private readonly zone: NgZone,
  ) {}

  /** Start recipe execution. Returns the run info. */
  execute(recipeId: string, message?: string): Observable<{ schema: string; status: string; recipe_id: string; run_id: string }> {
    return this.http.post<{ schema: string; status: string; recipe_id: string; run_id: string }>(
      `${this.apiBase}/api/control/recipes.execute`,
      { recipe_id: recipeId, message: message || '' },
    );
  }

  /** Subscribe to real-time execution events via SSE. */
  streamExecution(runId: string): Observable<RecipeExecutionEvent> {
    this.disconnect();
    this.eventsSubject = new Subject<RecipeExecutionEvent>();

    const url = `${this.apiBase}/api/control/recipes.execute.stream?run_id=${encodeURIComponent(runId)}`;
    this.eventSource = new EventSource(url);

    const eventTypes = [
      'recipe_started',
      'recipe_checkpoint_passed',
      'recipe_checkpoint_failed',
      'recipe_step_started',
      'recipe_step_completed',
      'recipe_step_failed',
      'recipe_completed',
      'recipe_failed',
      'recipe_paused',
      'recipe_resumed',
    ];

    for (const eventType of eventTypes) {
      this.eventSource.addEventListener(eventType, (event: MessageEvent) => {
        this.zone.run(() => {
          try {
            const data = JSON.parse(event.data) as RecipeExecutionEvent;
            this.eventsSubject.next(data);

            if (eventType === 'recipe_completed' || eventType === 'recipe_failed') {
              this.eventsSubject.complete();
              this.disconnect();
            }
          } catch {
            // ignore parse errors
          }
        });
      });
    }

    this.eventSource.onerror = () => {
      this.zone.run(() => {
        this.eventsSubject.complete();
        this.disconnect();
      });
    };

    return this.eventsSubject.asObservable();
  }

  /** Resume a paused recipe run. */
  resumeRun(runId: string, resumeData?: Record<string, unknown>): Observable<{ status: string; run_id: string }> {
    return this.http.post<{ status: string; run_id: string }>(
      `${this.apiBase}/api/control/recipes.runs.resume`,
      { run_id: runId, resume_data: resumeData },
    );
  }

  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
