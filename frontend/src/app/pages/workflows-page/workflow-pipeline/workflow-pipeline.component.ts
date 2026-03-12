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
  WorkflowStepEvent,
} from '../../../services/workflow-execution.service';
import {
  WorkflowService,
  WorkflowGraphDef,
} from '../../../services/workflow.service';

interface PipelineNode {
  id: string;
  type: string;
  label: string;
  status: 'pending' | 'running' | 'success' | 'error';
  durationMs?: number;
  outputPreview?: string;
  error?: string;
  outputDir?: string;
}

@Component({
  selector: 'app-workflow-pipeline',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './workflow-pipeline.component.html',
  styleUrl: './workflow-pipeline.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowPipelineComponent implements OnInit, OnDestroy {
  runId = '';
  workflowId = '';
  workflowName = '';
  status: 'running' | 'completed' | 'failed' = 'running';

  nodes: PipelineNode[] = [];
  edges: Array<{ from: string; to: string; type: string }> = [];
  stepLog: WorkflowStepEvent[] = [];

  stepsCompleted = 0;
  stepsTotal = 0;
  totalDurationMs = 0;

  private executionSub: Subscription | null = null;
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
      this.runId = params['run_id'] ?? '';
      this.workflowId = params['workflow_id'] ?? '';

      if (this.workflowId) {
        this.loadWorkflowGraph();
      }

      if (this.runId) {
        this.startStream();
      }
    });
  }

  ngOnDestroy(): void {
    this.executionSub?.unsubscribe();
    this.routeSub?.unsubscribe();
    this.execService.disconnect();
  }

  private loadWorkflowGraph(): void {
    this.wfService.get(this.workflowId).subscribe({
      next: (res) => {
        const wf = res.workflow;
        this.workflowName = wf.name;
        if (wf.workflow_graph) {
          this.buildPipelineFromGraph(wf.workflow_graph);
        } else if (wf.steps?.length) {
          this.buildPipelineFromFlatSteps(wf.steps);
        }
        this.cdr.markForCheck();
      },
    });
  }

  private buildPipelineFromGraph(graph: WorkflowGraphDef): void {
    // Add trigger node
    this.nodes = [{ id: '__trigger__', type: 'trigger', label: 'Start', status: 'success' }];
    this.edges = [];

    // Build step nodes
    const visited = new Set<string>();
    const queue = [graph.entry_step_id];
    this.edges.push({ from: '__trigger__', to: graph.entry_step_id, type: 'default' });

    while (queue.length > 0) {
      const stepId = queue.shift()!;
      if (visited.has(stepId)) continue;
      visited.add(stepId);

      const step = graph.steps.find(s => s.id === stepId);
      if (!step) continue;

      this.nodes.push({
        id: step.id,
        type: step.type,
        label: step.label || step.id,
        status: 'pending',
      });

      if (step.next_step) {
        this.edges.push({ from: step.id, to: step.next_step, type: 'default' });
        queue.push(step.next_step);
      }
      if (step.on_true) {
        this.edges.push({ from: step.id, to: step.on_true, type: 'true' });
        queue.push(step.on_true);
      }
      if (step.on_false) {
        this.edges.push({ from: step.id, to: step.on_false, type: 'false' });
        queue.push(step.on_false);
      }

      // If no outgoing edges, wire to end
      if (!step.next_step && !step.on_true && !step.on_false) {
        this.edges.push({ from: step.id, to: '__end__', type: 'default' });
      }
    }

    // Add end node
    this.nodes.push({ id: '__end__', type: 'end', label: 'End', status: 'pending' });
    this.stepsTotal = this.nodes.length - 2; // exclude trigger and end
  }

  private buildPipelineFromFlatSteps(steps: string[]): void {
    this.nodes = [{ id: '__trigger__', type: 'trigger', label: 'Start', status: 'success' }];
    this.edges = [];
    let prevId = '__trigger__';
    for (let i = 0; i < steps.length; i++) {
      const id = `step-${i}`;
      this.nodes.push({ id, type: 'agent', label: `Step ${i + 1}`, status: 'pending' });
      this.edges.push({ from: prevId, to: id, type: 'default' });
      prevId = id;
    }
    this.nodes.push({ id: '__end__', type: 'end', label: 'End', status: 'pending' });
    this.edges.push({ from: prevId, to: '__end__', type: 'default' });
    this.stepsTotal = steps.length;
  }

  private startStream(): void {
    this.executionSub?.unsubscribe();
    this.executionSub = this.execService.streamExecution(this.runId).subscribe({
      next: (event) => {
        this.stepLog.push(event);

        if (event.type === 'workflow_step_started' && event.step_id) {
          const node = this.nodes.find(n => n.id === event.step_id);
          if (node) node.status = 'running';
        } else if (event.type === 'workflow_step_completed' && event.step_id) {
          const node = this.nodes.find(n => n.id === event.step_id);
          if (node) {
            node.status = 'success';
            node.durationMs = event.duration_ms;
            node.outputPreview = event.output_preview;
          }
          this.stepsCompleted++;
        } else if (event.type === 'workflow_step_failed' && event.step_id) {
          const node = this.nodes.find(n => n.id === event.step_id);
          if (node) {
            node.status = 'error';
            node.error = event.error;
          }
        } else if (event.type === 'workflow_completed' || event.type === 'workflow_failed') {
          this.status = event.type === 'workflow_completed' ? 'completed' : 'failed';
          this.totalDurationMs = event.total_duration_ms ?? 0;
          this.stepsCompleted = event.steps_completed ?? this.stepsCompleted;
          this.stepsTotal = event.steps_total ?? this.stepsTotal;

          // Mark end node
          const endNode = this.nodes.find(n => n.id === '__end__');
          if (endNode) {
            endNode.status = this.status === 'completed' ? 'success' : 'error';
            if (event.output_dir) {
              endNode.outputDir = event.output_dir;
            }
          }
        }

        this.cdr.markForCheck();
      },
      complete: () => {
        if (this.status === 'running') this.status = 'completed';
        this.cdr.markForCheck();
      },
    });
  }

  get progressPercent(): number {
    if (this.stepsTotal === 0) return 0;
    return Math.round((this.stepsCompleted / this.stepsTotal) * 100);
  }

  get edgePaths(): Array<{
    from: string; to: string; type: string;
    path: string; midX: number; midY: number;
  }> {
    const paths: Array<{
      from: string; to: string; type: string;
      path: string; midX: number; midY: number;
    }> = [];

    for (const edge of this.edges) {
      const fromIdx = this.nodes.findIndex(n => n.id === edge.from);
      const toIdx = this.nodes.findIndex(n => n.id === edge.to);
      if (fromIdx < 0 || toIdx < 0) continue;

      const x = 200;
      const y1 = fromIdx * 120 + 36;
      const y2 = toIdx * 120 - 4;
      const midY = (y1 + y2) / 2;

      paths.push({
        from: edge.from,
        to: edge.to,
        type: edge.type,
        path: `M ${x} ${y1} C ${x} ${midY}, ${x} ${midY}, ${x} ${y2}`,
        midX: x,
        midY,
      });
    }
    return paths;
  }

  nodeIcon(type: string): string {
    return this.NODE_ICONS[type] ?? '◈';
  }

  goBack(): void {
    this.router.navigate(['/workflows']);
  }

  viewResult(): void {
    this.router.navigate(['/workflows/result'], {
      queryParams: { id: this.runId, workflow_id: this.workflowId },
    });
  }

  formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  trackByIndex(index: number): number {
    return index;
  }
}
