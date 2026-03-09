import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  HostListener,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  WorkflowCreatePayload,
  WorkflowDefinition,
  WorkflowService,
} from '../../services/workflow.service';
import { AgentDescriptor, AgentsService } from '../../services/agents.service';

// ── Canvas node model ──────────────────────────────

interface CanvasNode {
  id: string;
  type: 'trigger' | 'step' | 'end';
  label: string;
  instruction: string;
  agentId: string;
  x: number;
  y: number;
}

type ViewMode = 'list' | 'editor';

@Component({
  selector: 'app-workflows-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './workflows-page.component.html',
  styleUrl: './workflows-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowsPageComponent implements OnInit {

  // ── View state ─────────────────────────────────────
  view: ViewMode = 'list';
  loading = true;

  // ── List view ──────────────────────────────────────
  workflows: WorkflowDefinition[] = [];
  searchQuery = '';

  // ── Editor state ───────────────────────────────────
  editId: string | null = null;
  wfName = '';
  wfDescription = '';
  wfBaseAgent = 'head-agent';
  wfToolAllow = '';
  wfToolDeny = '';
  wfSubrunDelegation = false;
  nodes: CanvasNode[] = [];
  selectedNodeId: string | null = null;
  saving = false;
  message = '';
  messageType: 'ok' | 'err' = 'ok';

  // ── Execute ────────────────────────────────────────
  executeMessage = '';
  executing = false;
  executeResult = '';

  // ── Canvas interaction ─────────────────────────────
  canvasOffsetX = 0;
  canvasOffsetY = 0;
  canvasScale = 1;
  draggingNodeId: string | null = null;
  dragStartX = 0;
  dragStartY = 0;
  nodeStartX = 0;
  nodeStartY = 0;
  isPanning = false;
  panStartX = 0;
  panStartY = 0;
  panStartOffsetX = 0;
  panStartOffsetY = 0;

  // ── Agents ─────────────────────────────────────────
  agents: AgentDescriptor[] = [];

  private nodeCounter = 0;

  readonly AGENT_ICONS: Record<string, string> = {
    'head-agent': '◈', 'coder-agent': '⌨', 'review-agent': '◎',
    'researcher-agent': '◉', 'architect-agent': '◆', 'test-agent': '⬡',
    'security-agent': '⛊', 'doc-agent': '✦', 'refactor-agent': '⬢',
    'devops-agent': '▣',
  };

  constructor(
    private readonly wfService: WorkflowService,
    private readonly agentsService: AgentsService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadWorkflows();
    this.agentsService.getAgents().subscribe({
      next: (a) => { this.agents = a; this.cdr.markForCheck(); },
    });
  }

  // ── Data Loading ───────────────────────────────────

  loadWorkflows(): void {
    this.loading = true;
    this.wfService.list().subscribe({
      next: (res) => {
        this.workflows = res.items ?? [];
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => { this.loading = false; this.cdr.markForCheck(); },
    });
  }

  get filteredWorkflows(): WorkflowDefinition[] {
    if (!this.searchQuery) return this.workflows;
    const q = this.searchQuery.toLowerCase();
    return this.workflows.filter(w =>
      w.name.toLowerCase().includes(q) ||
      w.id.toLowerCase().includes(q) ||
      (w.description ?? '').toLowerCase().includes(q),
    );
  }

  // ── Navigation ─────────────────────────────────────

  openNew(): void {
    this.editId = null;
    this.wfName = '';
    this.wfDescription = '';
    this.wfBaseAgent = 'head-agent';
    this.wfToolAllow = '';
    this.wfToolDeny = '';
    this.wfSubrunDelegation = false;
    this.nodes = [
      this.makeNode('trigger', 'Start', '', 400, 60),
      this.makeNode('end', 'End', '', 400, 200),
    ];
    this.selectedNodeId = null;
    this.message = '';
    this.executeResult = '';
    this.canvasOffsetX = 0;
    this.canvasOffsetY = 0;
    this.canvasScale = 1;
    this.view = 'editor';
  }

  openEdit(wf: WorkflowDefinition): void {
    this.editId = wf.id;
    this.wfName = wf.name;
    this.wfDescription = wf.description ?? '';
    this.wfBaseAgent = wf.base_agent_id ?? 'head-agent';
    this.wfToolAllow = (wf.tool_policy?.allow ?? []).join(', ');
    this.wfToolDeny = (wf.tool_policy?.deny ?? []).join(', ');
    this.wfSubrunDelegation = wf.allow_subrun_delegation ?? false;

    // Build canvas nodes from steps
    const steps = wf.steps ?? [];
    this.nodes = [this.makeNode('trigger', 'Start', '', 400, 60)];
    for (let i = 0; i < steps.length; i++) {
      this.nodes.push(this.makeNode('step', `Step ${i + 1}`, steps[i], 400, 60 + (i + 1) * 140));
    }
    this.nodes.push(this.makeNode('end', 'End', '', 400, 60 + (steps.length + 1) * 140));

    this.selectedNodeId = null;
    this.message = '';
    this.executeResult = '';
    this.canvasOffsetX = 0;
    this.canvasOffsetY = 0;
    this.canvasScale = 1;
    this.view = 'editor';
  }

  backToList(): void {
    this.view = 'list';
    this.loadWorkflows();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.selectedNodeId) { this.selectedNodeId = null; return; }
    if (this.view === 'editor') this.backToList();
  }

  // ── Node Management ────────────────────────────────

  private makeNode(type: CanvasNode['type'], label: string, instruction: string, x: number, y: number): CanvasNode {
    return {
      id: `node-${++this.nodeCounter}`,
      type, label, instruction,
      agentId: this.wfBaseAgent,
      x, y,
    };
  }

  get stepNodes(): CanvasNode[] {
    return this.nodes.filter(n => n.type === 'step');
  }

  get triggerNode(): CanvasNode | undefined {
    return this.nodes.find(n => n.type === 'trigger');
  }

  get endNode(): CanvasNode | undefined {
    return this.nodes.find(n => n.type === 'end');
  }

  get selectedNode(): CanvasNode | null {
    if (!this.selectedNodeId) return null;
    return this.nodes.find(n => n.id === this.selectedNodeId) ?? null;
  }

  addStepAfter(index: number): void {
    // index is the position in the ordered flow (0 = after trigger)
    const steps = this.stepNodes;
    const stepNum = steps.length + 1;
    const prevNode = index === 0 ? this.triggerNode! : steps[index - 1];
    const nextNode = index >= steps.length ? this.endNode! : steps[index];
    const y = (prevNode.y + nextNode.y) / 2;
    const x = prevNode.x;
    const newNode = this.makeNode('step', `Step ${stepNum}`, '', x, y);

    // Insert into nodes array at correct position
    const insertIdx = this.nodes.indexOf(nextNode);
    this.nodes.splice(insertIdx, 0, newNode);
    this.selectedNodeId = newNode.id;
    this.redistributeNodes();
  }

  removeNode(nodeId: string): void {
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node || node.type !== 'step') return;
    this.nodes = this.nodes.filter(n => n.id !== nodeId);
    if (this.selectedNodeId === nodeId) this.selectedNodeId = null;
    this.redistributeNodes();
  }

  private redistributeNodes(): void {
    const trigger = this.triggerNode;
    const end = this.endNode;
    const steps = this.stepNodes;
    if (!trigger || !end) return;

    trigger.y = 60;
    trigger.x = 400;
    for (let i = 0; i < steps.length; i++) {
      steps[i].y = 60 + (i + 1) * 140;
      steps[i].x = 400;
      steps[i].label = `Step ${i + 1}`;
    }
    end.y = 60 + (steps.length + 1) * 140;
    end.x = 400;
  }

  selectNode(nodeId: string): void {
    this.selectedNodeId = nodeId;
  }

  // ── Canvas Connections (SVG paths) ─────────────────

  get connections(): Array<{ x1: number; y1: number; x2: number; y2: number }> {
    const ordered = this.orderedNodes;
    const conns: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
    for (let i = 0; i < ordered.length - 1; i++) {
      conns.push({
        x1: ordered[i].x, y1: ordered[i].y + 36,
        x2: ordered[i + 1].x, y2: ordered[i + 1].y - 36,
      });
    }
    return conns;
  }

  get orderedNodes(): CanvasNode[] {
    const trigger = this.triggerNode;
    const steps = this.stepNodes;
    const end = this.endNode;
    return [trigger, ...steps, end].filter(Boolean) as CanvasNode[];
  }

  // Index of "add" buttons (between each pair)
  get addButtonPositions(): Array<{ index: number; x: number; y: number }> {
    const ordered = this.orderedNodes;
    const positions: Array<{ index: number; x: number; y: number }> = [];
    for (let i = 0; i < ordered.length - 1; i++) {
      positions.push({
        index: i, // insert step after this index (0 = after trigger)
        x: (ordered[i].x + ordered[i + 1].x) / 2,
        y: (ordered[i].y + ordered[i + 1].y) / 2,
      });
    }
    return positions;
  }

  connPath(c: { x1: number; y1: number; x2: number; y2: number }): string {
    const midY = (c.y1 + c.y2) / 2;
    return `M ${c.x1} ${c.y1} C ${c.x1} ${midY}, ${c.x2} ${midY}, ${c.x2} ${c.y2}`;
  }

  // ── Node Dragging ──────────────────────────────────

  onNodeMouseDown(event: MouseEvent, nodeId: string): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    this.draggingNodeId = nodeId;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    const node = this.nodes.find(n => n.id === nodeId)!;
    this.nodeStartX = node.x;
    this.nodeStartY = node.y;
  }

  onCanvasMouseDown(event: MouseEvent): void {
    if (event.button !== 0) return;
    this.isPanning = true;
    this.panStartX = event.clientX;
    this.panStartY = event.clientY;
    this.panStartOffsetX = this.canvasOffsetX;
    this.panStartOffsetY = this.canvasOffsetY;
  }

  @HostListener('document:mousemove', ['$event'])
  onMouseMove(event: MouseEvent): void {
    if (this.draggingNodeId) {
      const node = this.nodes.find(n => n.id === this.draggingNodeId)!;
      node.x = this.nodeStartX + (event.clientX - this.dragStartX) / this.canvasScale;
      node.y = this.nodeStartY + (event.clientY - this.dragStartY) / this.canvasScale;
      this.cdr.markForCheck();
    }
    if (this.isPanning) {
      this.canvasOffsetX = this.panStartOffsetX + (event.clientX - this.panStartX);
      this.canvasOffsetY = this.panStartOffsetY + (event.clientY - this.panStartY);
      this.cdr.markForCheck();
    }
  }

  @HostListener('document:mouseup')
  onMouseUp(): void {
    this.draggingNodeId = null;
    this.isPanning = false;
  }

  onCanvasWheel(event: WheelEvent): void {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.05 : 0.05;
    this.canvasScale = Math.max(0.4, Math.min(2, this.canvasScale + delta));
  }

  resetView(): void {
    this.canvasOffsetX = 0;
    this.canvasOffsetY = 0;
    this.canvasScale = 1;
    this.redistributeNodes();
  }

  get canvasTransform(): string {
    return `translate(${this.canvasOffsetX}px, ${this.canvasOffsetY}px) scale(${this.canvasScale})`;
  }

  // ── Save / Execute / Delete ────────────────────────

  save(): void {
    if (!this.wfName.trim()) { this.flash('Name is required', 'err'); return; }
    this.saving = true;
    const steps = this.stepNodes.map(n => n.instruction).filter(s => s.trim());
    const allow = this.parseCsv(this.wfToolAllow);
    const deny = this.parseCsv(this.wfToolDeny);
    const toolPolicy = (allow.length || deny.length)
      ? { allow: allow.length ? allow : undefined, deny: deny.length ? deny : undefined }
      : undefined;

    if (this.editId) {
      this.wfService.update({
        id: this.editId,
        name: this.wfName,
        description: this.wfDescription,
        base_agent_id: this.wfBaseAgent,
        steps,
        tool_policy: toolPolicy,
      }).subscribe({
        next: () => { this.saving = false; this.flash('Workflow updated', 'ok'); },
        error: (err) => { this.saving = false; this.flash(`Error: ${err?.error?.detail ?? err.message}`, 'err'); },
      });
    } else {
      const payload: WorkflowCreatePayload = {
        name: this.wfName,
        description: this.wfDescription,
        base_agent_id: this.wfBaseAgent,
        steps,
        tool_policy: toolPolicy,
        allow_subrun_delegation: this.wfSubrunDelegation,
      };
      this.wfService.create(payload).subscribe({
        next: (res: any) => {
          this.saving = false;
          this.editId = res.workflow?.id ?? null;
          this.flash('Workflow created', 'ok');
        },
        error: (err) => { this.saving = false; this.flash(`Error: ${err?.error?.detail ?? err.message}`, 'err'); },
      });
    }
  }

  execute(): void {
    if (!this.editId) { this.flash('Save the workflow first', 'err'); return; }
    this.executing = true;
    this.executeResult = '';
    this.wfService.execute(this.editId, this.executeMessage).subscribe({
      next: (res) => {
        this.executing = false;
        this.executeResult = `Run started: ${res.run_id ?? res.status ?? 'accepted'}`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.executing = false;
        this.executeResult = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  deleteWorkflow(wf: WorkflowDefinition, event?: MouseEvent): void {
    event?.stopPropagation();
    this.wfService.delete(wf.id).subscribe({
      next: () => this.loadWorkflows(),
      error: (err) => this.flash(`Delete failed: ${err?.error?.detail ?? err.message}`, 'err'),
    });
  }

  duplicateWorkflow(wf: WorkflowDefinition, event?: MouseEvent): void {
    event?.stopPropagation();
    this.wfService.create({
      name: `${wf.name} (Copy)`,
      description: wf.description,
      base_agent_id: wf.base_agent_id,
      steps: wf.steps,
      tool_policy: wf.tool_policy ?? undefined,
      allow_subrun_delegation: wf.allow_subrun_delegation,
    }).subscribe({
      next: () => this.loadWorkflows(),
      error: (err) => this.flash(`Duplicate failed: ${err?.error?.detail ?? err.message}`, 'err'),
    });
  }

  // ── Helpers ────────────────────────────────────────

  agentIcon(id: string): string {
    return this.AGENT_ICONS[id] ?? '◈';
  }

  private parseCsv(val: string): string[] {
    return val.split(',').map(s => s.trim()).filter(Boolean);
  }

  private flash(msg: string, type: 'ok' | 'err'): void {
    this.message = msg;
    this.messageType = type;
    this.cdr.markForCheck();
  }
}
