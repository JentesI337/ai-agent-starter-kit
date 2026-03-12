import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { Subscription } from 'rxjs';

import {
  WorkflowExecutionService,
  WorkflowRunDetail,
} from '../../../services/workflow-execution.service';
import {
  WorkflowService,
  WorkflowGraphDef,
} from '../../../services/workflow.service';

interface ResultNode {
  id: string;
  type: string;
  label: string;
  status: 'pending' | 'success' | 'error' | 'skipped';
  durationMs?: number;
}

@Component({
  selector: 'app-workflow-result',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './workflow-result.component.html',
  styleUrl: './workflow-result.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowResultComponent implements OnInit, OnDestroy {
  runId = '';
  workflowId = '';
  workflowName = '';
  loading = true;

  run: WorkflowRunDetail | null = null;
  nodes: ResultNode[] = [];
  stepResults: Array<{
    stepId: string;
    status: string;
    durationMs: number;
    output: unknown;
    error?: string;
  }> = [];
  expandedSteps = new Set<string>();

  private routeSub: Subscription | null = null;

  readonly NODE_ICONS: Record<string, string> = {
    trigger: '▶', end: '■', agent: '◈', step: '◈', connector: '⟐',
    condition: '◇', transform: '⟗', delay: '◔',
  };

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly execService: WorkflowExecutionService,
    private readonly wfService: WorkflowService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.routeSub = this.route.queryParams.subscribe(params => {
      this.runId = params['id'] ?? '';
      this.workflowId = params['workflow_id'] ?? '';

      if (this.workflowId && this.runId) {
        this.loadData();
      }
    });
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
  }

  private loadData(): void {
    this.loading = true;

    // Load run details
    this.execService.getRun(this.workflowId, this.runId).subscribe({
      next: (res) => {
        this.run = res.run;
        this.stepResults = Object.values(res.run.step_results).map(sr => ({
          stepId: sr.step_id,
          status: sr.status,
          durationMs: sr.duration_ms,
          output: sr.output,
          error: sr.error,
        }));
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.loading = false;
        this.cdr.markForCheck();
      },
    });

    // Load workflow graph for pipeline visualization
    this.wfService.get(this.workflowId).subscribe({
      next: (res) => {
        const wf = res.workflow;
        this.workflowName = wf.name;
        if (wf.workflow_graph) {
          this.buildNodesFromGraph(wf.workflow_graph);
        }
        this.cdr.markForCheck();
      },
    });
  }

  private buildNodesFromGraph(graph: WorkflowGraphDef): void {
    this.nodes = [{ id: '__trigger__', type: 'trigger', label: 'Start', status: 'success' }];

    const visited = new Set<string>();
    const queue = [graph.entry_step_id];

    while (queue.length > 0) {
      const stepId = queue.shift()!;
      if (visited.has(stepId)) continue;
      visited.add(stepId);

      const step = graph.steps.find(s => s.id === stepId);
      if (!step) continue;

      // Get status from run results when available
      const result = this.run?.step_results[step.id];
      const status = result
        ? (result.status === 'success' ? 'success' : 'error') as ResultNode['status']
        : 'pending';

      this.nodes.push({
        id: step.id,
        type: step.type,
        label: step.label || step.id,
        status,
        durationMs: result?.duration_ms,
      });

      if (step.next_step) queue.push(step.next_step);
      if (step.on_true) queue.push(step.on_true);
      if (step.on_false) queue.push(step.on_false);
    }

    this.nodes.push({
      id: '__end__',
      type: 'end',
      label: 'End',
      status: this.run?.status === 'completed' ? 'success' : 'error',
    });
  }

  get totalDuration(): number {
    return this.stepResults.reduce((sum, sr) => sum + sr.durationMs, 0);
  }

  get statusBadgeClass(): string {
    if (!this.run) return '';
    switch (this.run.status) {
      case 'completed': return 'badge-success';
      case 'failed': return 'badge-error';
      default: return 'badge-running';
    }
  }

  toggleExpand(stepId: string): void {
    if (this.expandedSteps.has(stepId)) {
      this.expandedSteps.delete(stepId);
    } else {
      this.expandedSteps.add(stepId);
    }
    this.cdr.markForCheck();
  }

  isExpanded(stepId: string): boolean {
    return this.expandedSteps.has(stepId);
  }

  formatJson(value: unknown): string {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  nodeIcon(type: string): string {
    return this.NODE_ICONS[type] ?? '◈';
  }

  goBack(): void {
    this.router.navigate(['/workflows']);
  }

  trackByIndex(index: number): number {
    return index;
  }
}
