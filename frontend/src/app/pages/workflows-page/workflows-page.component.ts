import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  HostListener,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  WorkflowCreatePayload,
  WorkflowDefinition,
  WorkflowGraphDef,
  WorkflowService,
  WorkflowStepDef,
  WorkflowTemplate,
} from '../../services/workflow.service';
import { AgentDescriptor, AgentsService } from '../../services/agents.service';
import {
  WorkflowExecutionService,
  WorkflowRunSummary,
  WorkflowStepEvent,
} from '../../services/workflow-execution.service';

// ── Canvas node model ──────────────────────────────

interface CanvasNode {
  id: string;
  type: 'trigger' | 'step' | 'connector' | 'condition' | 'transform' | 'delay' | 'end';
  label: string;
  instruction: string;
  agentId: string;
  connectorId?: string;
  connectorMethod?: string;
  connectorParams?: Record<string, string>;
  transformExpr?: string;
  conditionExpr?: string;
  timeoutSeconds?: number;
  retryCount?: number;
  x: number;
  y: number;
}

interface CanvasEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  type: 'default' | 'true' | 'false';
}

interface PaletteItem {
  type: CanvasNode['type'];
  icon: string;
  label: string;
  desc: string;
}

interface TriggerConfig {
  type: 'manual' | 'schedule' | 'webhook' | 'chat_command';
  cron_expression?: string;
  webhook_secret?: string;
  command_name?: string;
  last_run_at?: string;
  next_run_at?: string;
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
export class WorkflowsPageComponent implements OnInit, OnDestroy {

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
  wfExecutionMode: 'parallel' | 'sequential' = 'parallel';
  nodes: CanvasNode[] = [];
  edges: CanvasEdge[] = [];
  selectedNodeId: string | null = null;
  saving = false;
  message = '';
  messageType: 'ok' | 'err' = 'ok';

  // ── Execute ────────────────────────────────────────
  executeMessage = '';
  executing = false;
  executeResult = '';

  // ── Execution Monitor ──────────────────────────────
  monitorActive = false;
  monitorRunId: string | null = null;
  stepLog: WorkflowStepEvent[] = [];
  nodeStatuses: Record<string, 'pending' | 'running' | 'success' | 'error'> = {};
  monitorProgress = '';
  private executionSub: Subscription | null = null;

  // ── Templates ─────────────────────────────────────
  listTab: 'workflows' | 'templates' = 'workflows';
  templates: WorkflowTemplate[] = [];
  templatesLoading = false;

  // ── Triggers ──────────────────────────────────────
  wfTriggers: TriggerConfig[] = [{ type: 'manual' }];

  // ── Run History ────────────────────────────────────
  editorTab: 'canvas' | 'runs' = 'canvas';
  runHistory: WorkflowRunSummary[] = [];
  runsLoading = false;

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

  // ── Edge drawing ───────────────────────────────────
  drawingEdge = false;
  drawingFromId: string | null = null;
  drawingEdgeType: 'default' | 'true' | 'false' = 'default';
  drawingMouseX = 0;
  drawingMouseY = 0;

  // ── Agents ─────────────────────────────────────────
  agents: AgentDescriptor[] = [];

  private nodeCounter = 0;
  private edgeCounter = 0;
  private agentsSub: Subscription | null = null;

  // ── Node palette ───────────────────────────────────
  readonly paletteItems: PaletteItem[] = [
    { type: 'step',      icon: '◈', label: 'Agent Step',  desc: 'Run an AI agent' },
    { type: 'connector', icon: '⟐', label: 'Connector',   desc: 'Call an external API' },
    { type: 'condition', icon: '◇', label: 'Condition',    desc: 'Branch on expression' },
    { type: 'transform', icon: '⟗', label: 'Transform',   desc: 'Transform data' },
    { type: 'delay',     icon: '◔', label: 'Delay',        desc: 'Wait before next step' },
  ];

  readonly AGENT_ICONS: Record<string, string> = {
    'head-agent': '◈', 'coder-agent': '⌨', 'review-agent': '◎',
    'researcher-agent': '◉', 'architect-agent': '◆', 'test-agent': '⬡',
    'security-agent': '⛊', 'doc-agent': '✦', 'refactor-agent': '⬢',
    'devops-agent': '▣',
  };

  readonly NODE_ICONS: Record<string, string> = {
    'trigger': '▶', 'end': '■', 'step': '◈', 'connector': '⟐',
    'condition': '◇', 'transform': '⟗', 'delay': '◔',
  };

  constructor(
    private readonly wfService: WorkflowService,
    private readonly agentsService: AgentsService,
    private readonly execService: WorkflowExecutionService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnDestroy(): void {
    this.executionSub?.unsubscribe();
    this.agentsSub?.unsubscribe();
    this.execService.disconnect();
  }

  ngOnInit(): void {
    this.loadWorkflows();
    this.agentsSub = this.agentsService.getAgents().subscribe({
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
    this.wfExecutionMode = 'parallel';
    this.wfTriggers = [{ type: 'manual' }];
    this.nodeCounter = 0;
    this.edgeCounter = 0;
    const trigger = this.makeNode('trigger', 'Start', '', 400, 60);
    const end = this.makeNode('end', 'End', '', 400, 200);
    this.nodes = [trigger, end];
    this.edges = [{ id: `edge-${++this.edgeCounter}`, from: trigger.id, to: end.id, type: 'default' }];
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
    this.wfExecutionMode = wf.execution_mode ?? 'parallel';
    this.wfTriggers = (wf as any).triggers?.length
      ? (wf as any).triggers.map((t: any) => ({ ...t }))
      : [{ type: 'manual' as const }];
    this.nodeCounter = 0;
    this.edgeCounter = 0;

    if (wf.workflow_graph && wf.execution_mode === 'sequential') {
      this.loadFromGraph(wf.workflow_graph);
    } else {
      // Build canvas nodes from flat steps
      const steps = wf.steps ?? [];
      const trigger = this.makeNode('trigger', 'Start', '', 400, 60);
      this.nodes = [trigger];
      this.edges = [];
      let prevId = trigger.id;
      for (let i = 0; i < steps.length; i++) {
        const step = this.makeNode('step', `Step ${i + 1}`, steps[i], 400, 60 + (i + 1) * 140);
        this.nodes.push(step);
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: prevId, to: step.id, type: 'default' });
        prevId = step.id;
      }
      const end = this.makeNode('end', 'End', '', 400, 60 + (steps.length + 1) * 140);
      this.nodes.push(end);
      this.edges.push({ id: `edge-${++this.edgeCounter}`, from: prevId, to: end.id, type: 'default' });
    }

    this.selectedNodeId = null;
    this.message = '';
    this.executeResult = '';
    this.canvasOffsetX = 0;
    this.canvasOffsetY = 0;
    this.canvasScale = 1;
    this.view = 'editor';
  }

  private loadFromGraph(graph: WorkflowGraphDef): void {
    const trigger = this.makeNode('trigger', 'Start', '', 400, 60);
    this.nodes = [trigger];
    this.edges = [];

    const stepMap = new Map<string, CanvasNode>();
    for (let i = 0; i < graph.steps.length; i++) {
      const sd = graph.steps[i];
      const canvasType = sd.type === 'agent' ? 'step' : sd.type;
      const node = this.makeNode(
        canvasType as CanvasNode['type'],
        sd.label || sd.id,
        sd.instruction || '',
        400,
        60 + (i + 1) * 140,
      );
      node.id = sd.id; // preserve original IDs
      node.connectorId = sd.connector_id;
      node.connectorMethod = sd.connector_method;
      node.connectorParams = sd.connector_params as Record<string, string>;
      node.transformExpr = sd.transform_expr;
      node.conditionExpr = sd.condition_expr;
      node.timeoutSeconds = sd.timeout_seconds;
      node.retryCount = sd.retry_count;
      node.agentId = sd.agent_id || this.wfBaseAgent;
      stepMap.set(sd.id, node);
      this.nodes.push(node);
    }

    const end = this.makeNode('end', 'End', '', 400, 60 + (graph.steps.length + 1) * 140);
    this.nodes.push(end);

    // Wire trigger to entry
    if (graph.entry_step_id && stepMap.has(graph.entry_step_id)) {
      this.edges.push({ id: `edge-${++this.edgeCounter}`, from: trigger.id, to: graph.entry_step_id, type: 'default' });
    }

    // Wire step edges
    for (const sd of graph.steps) {
      if (sd.next_step) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: sd.id, to: sd.next_step, type: 'default' });
      }
      if (sd.on_true) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: sd.id, to: sd.on_true, label: 'true', type: 'true' });
      }
      if (sd.on_false) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: sd.id, to: sd.on_false, label: 'false', type: 'false' });
      }
      // If no outgoing edge, wire to end
      if (!sd.next_step && !sd.on_true && !sd.on_false) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: sd.id, to: end.id, type: 'default' });
      }
    }
  }

  backToList(): void {
    this.view = 'list';
    this.loadWorkflows();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.drawingEdge) { this.drawingEdge = false; this.drawingFromId = null; return; }
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
    return this.nodes.filter(n => !['trigger', 'end'].includes(n.type));
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

  addNodeFromPalette(type: CanvasNode['type']): void {
    const existingNodes = this.stepNodes;
    const y = existingNodes.length > 0
      ? Math.max(...existingNodes.map(n => n.y)) + 140
      : 200;

    const label = this.paletteItems.find(p => p.type === type)?.label ?? type;
    const node = this.makeNode(type, label, '', 400, y);
    if (type === 'delay') {
      node.timeoutSeconds = 5;
    }

    // Insert before end node
    const endIdx = this.nodes.findIndex(n => n.type === 'end');
    if (endIdx >= 0) {
      this.nodes.splice(endIdx, 0, node);
    } else {
      this.nodes.push(node);
    }

    // Auto-wire: connect to end node, and connect from last step if possible
    const end = this.endNode;
    if (end) {
      // Remove any existing edge to end from the previous last node
      const prevEdgeIdx = this.edges.findIndex(e => e.to === end.id);
      let prevNodeId: string | null = null;
      if (prevEdgeIdx >= 0) {
        prevNodeId = this.edges[prevEdgeIdx].from;
        this.edges.splice(prevEdgeIdx, 1);
      }
      // Wire previous -> new node -> end
      if (prevNodeId) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: prevNodeId, to: node.id, type: 'default' });
      }
      this.edges.push({ id: `edge-${++this.edgeCounter}`, from: node.id, to: end.id, type: 'default' });

      // Move end node down
      end.y = node.y + 140;
    }

    this.selectedNodeId = node.id;
    this.cdr.markForCheck();
  }

  addStepAfter(index: number): void {
    const ordered = this.orderedNodes;
    if (index < 0 || index >= ordered.length - 1) return;
    const prevNode = ordered[index];
    const nextNode = ordered[index + 1];
    const y = (prevNode.y + nextNode.y) / 2;
    const newNode = this.makeNode('step', `Step`, '', prevNode.x, y);

    const insertIdx = this.nodes.indexOf(nextNode);
    this.nodes.splice(insertIdx, 0, newNode);

    // Update edges: remove prev->next, add prev->new and new->next
    const edgeIdx = this.edges.findIndex(e => e.from === prevNode.id && e.to === nextNode.id);
    if (edgeIdx >= 0) {
      this.edges.splice(edgeIdx, 1);
    }
    this.edges.push({ id: `edge-${++this.edgeCounter}`, from: prevNode.id, to: newNode.id, type: 'default' });
    this.edges.push({ id: `edge-${++this.edgeCounter}`, from: newNode.id, to: nextNode.id, type: 'default' });

    this.selectedNodeId = newNode.id;
    this.cdr.markForCheck();
  }

  removeNode(nodeId: string): void {
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node || node.type === 'trigger' || node.type === 'end') return;

    // Find incoming and outgoing edges
    const incoming = this.edges.filter(e => e.to === nodeId);
    const outgoing = this.edges.filter(e => e.from === nodeId);

    // Remove all edges involving this node
    this.edges = this.edges.filter(e => e.from !== nodeId && e.to !== nodeId);

    // Re-wire: each incoming source -> each outgoing target
    for (const inc of incoming) {
      for (const out of outgoing) {
        this.edges.push({ id: `edge-${++this.edgeCounter}`, from: inc.from, to: out.to, type: 'default' });
      }
    }

    this.nodes = this.nodes.filter(n => n.id !== nodeId);
    if (this.selectedNodeId === nodeId) this.selectedNodeId = null;
    this.cdr.markForCheck();
  }

  removeEdge(edgeId: string): void {
    this.edges = this.edges.filter(e => e.id !== edgeId);
    this.cdr.markForCheck();
  }

  selectNode(nodeId: string): void {
    this.selectedNodeId = nodeId;
  }

  // ── Edge Drawing ───────────────────────────────────

  startEdge(nodeId: string, edgeType: 'default' | 'true' | 'false' = 'default'): void {
    this.drawingEdge = true;
    this.drawingFromId = nodeId;
    this.drawingEdgeType = edgeType;
  }

  completeEdge(targetNodeId: string): void {
    if (!this.drawingEdge || !this.drawingFromId || this.drawingFromId === targetNodeId) {
      this.drawingEdge = false;
      this.drawingFromId = null;
      return;
    }

    // Don't create duplicate edges
    const exists = this.edges.some(e => e.from === this.drawingFromId && e.to === targetNodeId);
    if (!exists) {
      this.edges.push({
        id: `edge-${++this.edgeCounter}`,
        from: this.drawingFromId,
        to: targetNodeId,
        label: this.drawingEdgeType !== 'default' ? this.drawingEdgeType : undefined,
        type: this.drawingEdgeType,
      });
    }

    this.drawingEdge = false;
    this.drawingFromId = null;
    this.cdr.markForCheck();
  }

  // ── Canvas Connections (SVG paths) ─────────────────

  get edgePaths(): Array<{
    edge: CanvasEdge;
    path: string;
    midX: number; midY: number;
    x1: number; y1: number;
    x2: number; y2: number;
  }> {
    const paths: Array<{
      edge: CanvasEdge; path: string;
      midX: number; midY: number;
      x1: number; y1: number; x2: number; y2: number;
    }> = [];
    for (const edge of this.edges) {
      const from = this.nodes.find(n => n.id === edge.from);
      const to = this.nodes.find(n => n.id === edge.to);
      if (!from || !to) continue;
      const x1 = from.x;
      const y1 = from.y + 36;
      const x2 = to.x;
      const y2 = to.y - 36;
      const midY = (y1 + y2) / 2;
      paths.push({
        edge,
        path: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
        midX: (x1 + x2) / 2,
        midY,
        x1, y1, x2, y2,
      });
    }
    return paths;
  }

  get orderedNodes(): CanvasNode[] {
    // BFS from trigger node following edges
    const trigger = this.triggerNode;
    if (!trigger) return this.nodes;

    const visited = new Set<string>();
    const ordered: CanvasNode[] = [];
    const queue = [trigger.id];

    while (queue.length > 0) {
      const id = queue.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);
      const node = this.nodes.find(n => n.id === id);
      if (node) ordered.push(node);
      for (const edge of this.edges) {
        if (edge.from === id && !visited.has(edge.to)) {
          queue.push(edge.to);
        }
      }
    }

    // Add any unvisited nodes
    for (const node of this.nodes) {
      if (!visited.has(node.id)) ordered.push(node);
    }

    return ordered;
  }

  get addButtonPositions(): Array<{ index: number; x: number; y: number }> {
    const ordered = this.orderedNodes;
    const positions: Array<{ index: number; x: number; y: number }> = [];
    for (let i = 0; i < ordered.length - 1; i++) {
      // Only show between directly connected nodes
      const hasEdge = this.edges.some(e => e.from === ordered[i].id && e.to === ordered[i + 1].id);
      if (hasEdge) {
        positions.push({
          index: i,
          x: (ordered[i].x + ordered[i + 1].x) / 2,
          y: (ordered[i].y + ordered[i + 1].y) / 2,
        });
      }
    }
    return positions;
  }

  // ── Node Dragging ──────────────────────────────────

  onNodeMouseDown(event: MouseEvent, nodeId: string): void {
    if (event.button !== 0) return;
    event.stopPropagation();

    if (this.drawingEdge) {
      this.completeEdge(nodeId);
      return;
    }

    this.draggingNodeId = nodeId;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    const node = this.nodes.find(n => n.id === nodeId)!;
    this.nodeStartX = node.x;
    this.nodeStartY = node.y;
  }

  onCanvasMouseDown(event: MouseEvent): void {
    if (event.button !== 0) return;
    if (this.drawingEdge) {
      this.drawingEdge = false;
      this.drawingFromId = null;
      return;
    }
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
    if (this.drawingEdge) {
      this.drawingMouseX = event.clientX;
      this.drawingMouseY = event.clientY;
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
  }

  get canvasTransform(): string {
    return `translate(${this.canvasOffsetX}px, ${this.canvasOffsetY}px) scale(${this.canvasScale})`;
  }

  nodeIcon(node: CanvasNode): string {
    if (node.type === 'step') return this.agentIcon(node.agentId);
    return this.NODE_ICONS[node.type] ?? '◈';
  }

  // ── Save / Execute / Delete ────────────────────────

  save(): void {
    if (!this.wfName.trim()) { this.flash('Name is required', 'err'); return; }
    this.saving = true;

    const allow = this.parseCsv(this.wfToolAllow);
    const deny = this.parseCsv(this.wfToolDeny);
    const toolPolicy = (allow.length || deny.length)
      ? { allow: allow.length ? allow : undefined, deny: deny.length ? deny : undefined }
      : undefined;

    // Build flat steps (backward compat) from agent step nodes
    const steps = this.stepNodes
      .filter(n => n.type === 'step')
      .map(n => n.instruction)
      .filter(s => s.trim());

    // Build workflow graph for sequential mode
    let workflowGraph: WorkflowGraphDef | undefined;
    if (this.wfExecutionMode === 'sequential') {
      workflowGraph = this.buildWorkflowGraph();
    }

    // Filter out pure "manual" triggers with no extra config
    const triggers = this.wfTriggers.filter(t => t.type !== 'manual' || this.wfTriggers.length === 1);

    if (this.editId) {
      this.wfService.update({
        id: this.editId,
        name: this.wfName,
        description: this.wfDescription,
        base_agent_id: this.wfBaseAgent,
        steps,
        execution_mode: this.wfExecutionMode,
        workflow_graph: workflowGraph,
        tool_policy: toolPolicy,
        triggers,
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
        execution_mode: this.wfExecutionMode,
        workflow_graph: workflowGraph,
        tool_policy: toolPolicy,
        allow_subrun_delegation: this.wfSubrunDelegation,
        triggers,
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

  private buildWorkflowGraph(): WorkflowGraphDef {
    const stepDefs: WorkflowStepDef[] = [];
    const trigger = this.triggerNode;

    for (const node of this.nodes) {
      if (node.type === 'trigger' || node.type === 'end') continue;

      const outgoing = this.edges.filter(e => e.from === node.id);
      const defaultEdge = outgoing.find(e => e.type === 'default');
      const trueEdge = outgoing.find(e => e.type === 'true');
      const falseEdge = outgoing.find(e => e.type === 'false');

      // Don't set next_step to end node
      const endId = this.endNode?.id;
      const nextStep = defaultEdge && defaultEdge.to !== endId ? defaultEdge.to : undefined;
      const onTrue = trueEdge && trueEdge.to !== endId ? trueEdge.to : undefined;
      const onFalse = falseEdge && falseEdge.to !== endId ? falseEdge.to : undefined;

      stepDefs.push({
        id: node.id,
        type: (node.type === 'step' ? 'agent' : node.type) as WorkflowStepDef['type'],
        label: node.label,
        instruction: node.instruction,
        agent_id: node.type === 'step' ? node.agentId : undefined,
        connector_id: node.connectorId,
        connector_method: node.connectorMethod,
        connector_params: node.connectorParams,
        transform_expr: node.transformExpr,
        condition_expr: node.conditionExpr,
        next_step: nextStep,
        on_true: onTrue,
        on_false: onFalse,
        timeout_seconds: node.timeoutSeconds ?? 120,
        retry_count: node.retryCount ?? 0,
      });
    }

    // Entry step = first node connected from trigger
    let entryStepId = stepDefs[0]?.id ?? '';
    if (trigger) {
      const triggerEdge = this.edges.find(e => e.from === trigger.id);
      if (triggerEdge) entryStepId = triggerEdge.to;
    }

    return { steps: stepDefs, entry_step_id: entryStepId };
  }

  execute(): void {
    if (!this.editId) { this.flash('Save the workflow first', 'err'); return; }
    this.executing = true;
    this.executeResult = '';
    this.stepLog = [];
    this.nodeStatuses = {};
    this.monitorProgress = '';

    this.wfService.execute(this.editId, this.executeMessage).subscribe({
      next: (res: any) => {
        const runId = res.runId ?? res.run_id;
        this.executeResult = `Run started: ${runId ?? res.status ?? 'accepted'}`;

        // For sequential workflows, start the execution monitor
        if (runId && this.wfExecutionMode === 'sequential') {
          this.monitorRunId = runId;
          this.monitorActive = true;
          this.startExecutionMonitor(runId);
        } else {
          this.executing = false;
        }
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.executing = false;
        this.executeResult = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  private startExecutionMonitor(runId: string): void {
    this.executionSub?.unsubscribe();
    this.executionSub = this.execService.streamExecution(runId).subscribe({
      next: (event) => {
        this.stepLog.push(event);

        if (event.type === 'workflow_step_started' && event.step_id) {
          this.nodeStatuses[event.step_id] = 'running';
          this.monitorProgress = `Running "${event.label ?? event.step_id}"`;
        } else if (event.type === 'workflow_step_completed' && event.step_id) {
          this.nodeStatuses[event.step_id] = 'success';
        } else if (event.type === 'workflow_step_failed' && event.step_id) {
          this.nodeStatuses[event.step_id] = 'error';
        } else if (event.type === 'workflow_completed') {
          this.executing = false;
          this.monitorProgress = `Completed — ${event.steps_completed}/${event.steps_total} steps`;
        }
        this.cdr.markForCheck();
      },
      complete: () => {
        this.executing = false;
        this.monitorActive = false;
        this.cdr.markForCheck();
      },
    });
  }

  stopMonitor(): void {
    this.executionSub?.unsubscribe();
    this.execService.disconnect();
    this.monitorActive = false;
    this.executing = false;
    this.cdr.markForCheck();
  }

  nodeStatus(nodeId: string): string {
    return this.nodeStatuses[nodeId] ?? 'pending';
  }

  // ── Run History ────────────────────────────────────

  loadRunHistory(): void {
    if (!this.editId) return;
    this.runsLoading = true;
    this.execService.listRuns(this.editId).subscribe({
      next: (res) => {
        this.runHistory = res.items ?? [];
        this.runsLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.runsLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  switchTab(tab: 'canvas' | 'runs'): void {
    this.editorTab = tab;
    if (tab === 'runs') this.loadRunHistory();
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
      execution_mode: wf.execution_mode,
      workflow_graph: wf.workflow_graph ?? undefined,
      tool_policy: wf.tool_policy ?? undefined,
      allow_subrun_delegation: wf.allow_subrun_delegation,
    }).subscribe({
      next: () => this.loadWorkflows(),
      error: (err) => this.flash(`Duplicate failed: ${err?.error?.detail ?? err.message}`, 'err'),
    });
  }

  // ── Templates ──────────────────────────────────────

  switchListTab(tab: 'workflows' | 'templates'): void {
    this.listTab = tab;
    if (tab === 'templates' && this.templates.length === 0) {
      this.loadTemplates();
    }
  }

  loadTemplates(): void {
    this.templatesLoading = true;
    this.wfService.listTemplates().subscribe({
      next: (res) => {
        this.templates = res.items ?? [];
        this.templatesLoading = false;
        this.cdr.markForCheck();
      },
      error: () => { this.templatesLoading = false; this.cdr.markForCheck(); },
    });
  }

  instantiateTemplate(template: WorkflowTemplate): void {
    this.wfService.instantiateTemplate(template.id).subscribe({
      next: () => {
        this.flash(`Workflow "${template.name}" created from template`, 'ok');
        this.listTab = 'workflows';
        this.loadWorkflows();
      },
      error: (err) => this.flash(`Error: ${err?.error?.detail ?? err.message}`, 'err'),
    });
  }

  templateCategoryIcon(cat: string): string {
    const icons: Record<string, string> = {
      'development': '⌨',
      'project-management': '◎',
      'reporting': '✦',
      'content': '◈',
    };
    return icons[cat] ?? '⬡';
  }

  // ── Trigger Management ─────────────────────────────

  addTrigger(): void {
    this.wfTriggers.push({ type: 'manual' });
    this.cdr.markForCheck();
  }

  removeTrigger(index: number): void {
    if (this.wfTriggers.length <= 1) return;
    this.wfTriggers.splice(index, 1);
    this.cdr.markForCheck();
  }

  generateWebhookSecret(trigger: TriggerConfig): void {
    const arr = new Uint8Array(24);
    crypto.getRandomValues(arr);
    trigger.webhook_secret = Array.from(arr, b => b.toString(16).padStart(2, '0')).join('');
    this.cdr.markForCheck();
  }

  webhookUrl(workflowId: string | null): string {
    if (!workflowId) return '';
    const base = window.location.origin;
    return `${base}/api/webhooks/${workflowId}`;
  }

  cronHumanReadable(expr: string | undefined): string {
    if (!expr) return '';
    // Simple heuristics for common patterns
    const parts = expr.trim().split(/\s+/);
    if (parts.length !== 5) return expr;
    const [min, hour, dom, mon, dow] = parts;
    if (min === '0' && hour !== '*' && dom === '*' && mon === '*' && dow === '1-5') return `Weekdays at ${hour}:00`;
    if (min === '0' && hour !== '*' && dom === '*' && mon === '*' && dow === '*') return `Daily at ${hour}:00`;
    if (min === '*/5' && hour === '*') return 'Every 5 minutes';
    if (min === '*/15' && hour === '*') return 'Every 15 minutes';
    if (min === '0' && hour === '*/1') return 'Every hour';
    if (min === '0' && hour === '0' && dom === '*' && mon === '*' && dow === '1') return 'Weekly on Monday';
    return expr;
  }

  // ── Helpers ────────────────────────────────────────

  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(
      () => this.flash('Copied to clipboard', 'ok'),
      () => this.flash('Copy failed', 'err'),
    );
  }

  agentIcon(id: string): string {
    return this.AGENT_ICONS[id] ?? '◈';
  }

  trackById(_index: number, item: { id: string }): string {
    return item.id;
  }

  trackByIndex(index: number): number {
    return index;
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
