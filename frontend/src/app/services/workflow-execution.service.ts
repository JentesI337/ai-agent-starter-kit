import { HttpClient } from '@angular/common/http';
import { Injectable, NgZone } from '@angular/core';
import { Observable, Subject } from 'rxjs';

export interface WorkflowStepEvent {
  type: string;
  step_id?: string;
  step_type?: string;
  label?: string;
  status?: string;
  output_preview?: string;
  duration_ms?: number;
  error?: string;
  total_duration_ms?: number;
  steps_completed?: number;
  steps_total?: number;
}

export interface WorkflowRunSummary {
  run_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  steps_completed: number;
  steps_total: number;
}

export interface WorkflowRunDetail {
  workflow_id: string;
  run_id: string;
  session_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  step_results: Record<string, {
    step_id: string;
    status: string;
    output?: unknown;
    error?: string;
    duration_ms: number;
  }>;
  context: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class WorkflowExecutionService {
  private readonly apiBase = 'http://localhost:8000';
  private eventSource: EventSource | null = null;
  private eventsSubject = new Subject<WorkflowStepEvent>();

  constructor(
    private readonly http: HttpClient,
    private readonly zone: NgZone,
  ) {}

  /** Subscribe to real-time step events for a workflow run via SSE. */
  streamExecution(runId: string): Observable<WorkflowStepEvent> {
    this.disconnect();
    this.eventsSubject = new Subject<WorkflowStepEvent>();

    const url = `${this.apiBase}/api/control/workflows.execute.stream?run_id=${encodeURIComponent(runId)}`;
    this.eventSource = new EventSource(url);

    const eventTypes = [
      'workflow_step_started',
      'workflow_step_completed',
      'workflow_step_failed',
      'workflow_completed',
    ];

    for (const eventType of eventTypes) {
      this.eventSource.addEventListener(eventType, (event: MessageEvent) => {
        this.zone.run(() => {
          try {
            const data = JSON.parse(event.data) as WorkflowStepEvent;
            this.eventsSubject.next(data);

            if (eventType === 'workflow_completed' || eventType === 'workflow_failed') {
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

  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  /** List past runs for a workflow. */
  listRuns(workflowId: string, limit = 20): Observable<{ items: WorkflowRunSummary[]; count: number }> {
    return this.http.post<{ items: WorkflowRunSummary[]; count: number }>(
      `${this.apiBase}/api/control/workflows.runs.list`,
      { workflow_id: workflowId, limit },
    );
  }

  /** Get full details of a specific run. */
  getRun(workflowId: string, runId: string): Observable<{ run: WorkflowRunDetail }> {
    return this.http.post<{ run: WorkflowRunDetail }>(
      `${this.apiBase}/api/control/workflows.runs.get`,
      { workflow_id: workflowId, run_id: runId },
    );
  }
}
