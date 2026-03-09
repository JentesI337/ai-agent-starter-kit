import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';

// ── Architecture data model ────────────────────────

interface ArchNode {
  id: string;
  label: string;
  sub: string;
  icon: string;
  x: number;
  y: number;
  layer: 'entry' | 'orchestration' | 'pipeline' | 'agent' | 'tools' | 'infra';
  detail: string[];
  pulse?: boolean;
}

interface ArchEdge {
  from: string;
  to: string;
  label?: string;
  animated?: boolean;
}

interface PipelinePhase {
  id: string;
  label: string;
  icon: string;
  color: string;
  desc: string;
}

@Component({
  selector: 'app-architecture-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './architecture-page.component.html',
  styleUrl: './architecture-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ArchitecturePageComponent implements OnInit, OnDestroy {

  hoveredNode: ArchNode | null = null;
  selectedLayer: string | null = null;
  tick = 0;
  private tickInterval: any;

  // ── Pipeline phases (the reasoning engine) ────────

  readonly phases: PipelinePhase[] = [
    { id: 'routing',        label: 'Model Routing',     icon: '⟐', color: '#3794ff', desc: 'Selects primary + fallback LLM models based on health and capability' },
    { id: 'guardrails',     label: 'Guardrails',        icon: '⛊', color: '#ff5555', desc: 'Content safety, input validation, policy enforcement' },
    { id: 'context',        label: 'Context Assembly',   icon: '◫', color: '#e5b200', desc: 'Memory retrieval, session history, prompt composition' },
    { id: 'agent_loop',     label: 'Agent Loop',         icon: '⟳', color: '#00cc7a', desc: 'Continuous LLM + tool execution cycle — the agent decides when to use tools and when to answer' },
    { id: 'reflection',     label: 'Reflection',         icon: '◎', color: '#e5b200', desc: 'Factual grounding checks, verification, quality scoring' },
    { id: 'reply_shaping',  label: 'Reply Shaping',      icon: '✦', color: '#3794ff', desc: 'Format adaptation, tone matching, final polish' },
    { id: 'response',       label: 'Response',           icon: '▶', color: '#00cc7a', desc: 'Stream back to client via WebSocket events' },
  ];

  // ── Architecture nodes ────────────────────────────

  readonly nodes: ArchNode[] = [
    // Entry layer — y: 8, 18
    { id: 'ws',       label: 'WebSocket',       sub: 'ws_handler.py',          icon: '⚡', x: 50, y: 8, layer: 'entry',
      detail: ['Bidirectional event streaming', 'Session management', 'Rate limiting', 'Envelope parsing'] },
    { id: 'rest',     label: 'REST API',        sub: 'FastAPI routers',        icon: '⇌',  x: 50, y: 18, layer: 'entry',
      detail: ['Control plane endpoints', 'CRUD operations', 'SSE streaming', 'OpenAPI documented'], pulse: true },

    // Orchestration layer — y: 30
    { id: 'orch',     label: 'Orchestrator',    sub: 'orchestrator_api.py',    icon: '◈', x: 50, y: 30, layer: 'orchestration',
      detail: ['Request context building', 'Tool policy resolution', 'Session lane management', 'Event lifecycle coordination'], pulse: true },
    { id: 'lane',     label: 'Session Lanes',   sub: 'session_lane_mgr.py',    icon: '≡',  x: 20, y: 30, layer: 'orchestration',
      detail: ['Concurrency throttling', 'Per-session queuing', 'Inbox deferral', 'Global lane limits'] },
    { id: 'policy',   label: 'Policy Engine',   sub: 'tool_policy_service.py', icon: '⛊', x: 80, y: 30, layer: 'orchestration',
      detail: ['3-layer policy merge', 'Preset + Request + Depth', 'Approval workflows', 'Mandatory deny enforcement'] },

    // Pipeline layer — y: 44
    { id: 'pipeline', label: 'Pipeline Runner', sub: 'pipeline_runner.py',     icon: '⟐', x: 50, y: 44, layer: 'pipeline',
      detail: ['Adaptive model routing', 'Recovery strategies', 'Context overflow handling', 'Task status tracking'], pulse: true },

    // Agent layer — y: 58
    { id: 'agent',    label: 'Agent Runner',    sub: 'agent.py',               icon: '◉', x: 50, y: 58, layer: 'agent',
      detail: ['Continuous tool loop', 'System prompt composition', 'Streaming token output', '15 specialized adapters'], pulse: true },
    { id: 'llm',      label: 'LLM Client',      sub: 'llm_client.py',          icon: '⬢', x: 20, y: 58, layer: 'agent',
      detail: ['Multi-provider support', 'Token counting', 'Model switching', 'Streaming responses'] },
    { id: 'memory',   label: 'Memory Store',    sub: 'memory.py',              icon: '◫', x: 80, y: 58, layer: 'agent',
      detail: ['Session history (deque)', 'JSON-L persistence', 'Hashed session IDs', 'Self-healing repair'] },

    // Tools layer — y: 72
    { id: 'toolreg',  label: 'Tool Registry',   sub: 'tool_registry.py',       icon: '⬡', x: 30, y: 72, layer: 'tools',
      detail: ['30+ tool definitions', 'ToolSpec with schemas', 'Feature-gated availability', 'Multi-provider formats'] },
    { id: 'toolexec', label: 'Tool Executor',   sub: 'tool_execution_mgr.py',  icon: '▣', x: 70, y: 72, layer: 'tools',
      detail: ['Budget enforcement (call + time)', 'Loop detection (3 patterns)', 'Circuit breaker integration', 'Telemetry collection'] },

    // Infra layer — y: 86
    { id: 'state',    label: 'State Store',     sub: 'state_store.py',         icon: '▤', x: 20, y: 86, layer: 'infra',
      detail: ['SQLite persistence', 'Run records + events', 'Task graph tracking', 'Snapshot archival'] },
    { id: 'config',   label: 'Config Service',  sub: 'config_service.py',      icon: '⚙', x: 50, y: 86, layer: 'infra',
      detail: ['20 config sections', '3-layer overrides', '.env → JSON → memory', 'Change subscriptions'] },
    { id: 'ltm',      label: 'Long-Term Memory',sub: 'long_term_memory.py',    icon: '⧫', x: 80, y: 86, layer: 'infra',
      detail: ['Failure history', 'Vector similarity search', 'Learning loop integration', 'Persistent embeddings'] },
  ];

  readonly edges: ArchEdge[] = [
    { from: 'ws',       to: 'orch',     label: 'events',    animated: true },
    { from: 'rest',     to: 'orch',     label: 'requests',  animated: true },
    { from: 'lane',     to: 'orch',     label: 'lanes' },
    { from: 'policy',   to: 'orch',     label: 'policies' },
    { from: 'orch',     to: 'pipeline', label: 'run',        animated: true },
    { from: 'pipeline', to: 'agent',    label: 'execute',    animated: true },
    { from: 'llm',      to: 'agent',    label: 'tokens' },
    { from: 'memory',   to: 'agent',    label: 'context' },
    { from: 'agent',    to: 'toolreg',  label: 'select' },
    { from: 'agent',    to: 'toolexec', label: 'execute',    animated: true },
    { from: 'agent',    to: 'state',    label: 'persist' },
    { from: 'agent',    to: 'ltm',      label: 'learn' },
    { from: 'config',   to: 'pipeline', label: 'config' },
    { from: 'config',   to: 'agent',    label: 'config' },
  ];

  // ── Agent roster ──────────────────────────────────

  readonly agentRoster = [
    { id: 'head',       name: 'Head Agent',       icon: '◈', category: 'core' },
    { id: 'coder',      name: 'Coder',            icon: '⌨', category: 'core' },
    { id: 'review',     name: 'Reviewer',         icon: '◎', category: 'core' },
    { id: 'researcher', name: 'Researcher',       icon: '◉', category: 'specialist' },
    { id: 'architect',  name: 'Architect',        icon: '◆', category: 'specialist' },
    { id: 'test',       name: 'Test Agent',       icon: '⬡', category: 'specialist' },
    { id: 'security',   name: 'Security',         icon: '⛊', category: 'specialist' },
    { id: 'doc',        name: 'Documentation',    icon: '✦', category: 'specialist' },
    { id: 'refactor',   name: 'Refactorer',       icon: '⬢', category: 'specialist' },
    { id: 'devops',     name: 'DevOps',           icon: '▣', category: 'specialist' },
    { id: 'fintech',    name: 'FinTech',          icon: '◇', category: 'industry' },
    { id: 'health',     name: 'HealthTech',       icon: '♡', category: 'industry' },
    { id: 'legal',      name: 'LegalTech',        icon: '§', category: 'industry' },
    { id: 'ecommerce',  name: 'E-Commerce',       icon: '◻', category: 'industry' },
    { id: 'industry',   name: 'IndustryTech',     icon: '⚙', category: 'industry' },
  ];

  // ── Tool groups ───────────────────────────────────

  readonly toolGroups = [
    { name: 'Filesystem',  tools: ['list_dir', 'read_file', 'write_file', 'apply_patch', 'file_search', 'grep_search'], icon: '📁' },
    { name: 'Commands',    tools: ['run_command', 'start_background', 'get_background', 'kill_background'], icon: '⌨' },
    { name: 'Web',         tools: ['web_search', 'web_fetch', 'http_request'], icon: '🌐' },
    { name: 'Browser',     tools: ['browser_navigate', 'browser_click', 'browser_type', 'browser_screenshot'], icon: '🖥' },
    { name: 'Code',        tools: ['code_execute', 'code_reset'], icon: '⚡' },
    { name: 'RAG',         tools: ['rag_index', 'rag_query'], icon: '🔍' },
    { name: 'Agent',       tools: ['spawn_subrun', 'create_workflow', 'analyze_image'], icon: '🤖' },
  ];

  readonly layers = [
    { id: 'entry',         label: 'Entry',         color: '#3794ff' },
    { id: 'orchestration', label: 'Orchestration',  color: '#e5b200' },
    { id: 'pipeline',      label: 'Pipeline',       color: '#00cc7a' },
    { id: 'agent',         label: 'Agent',          color: '#ffb347' },
    { id: 'tools',         label: 'Tools',          color: '#ff5555' },
    { id: 'infra',         label: 'Infrastructure', color: '#9b59b6' },
  ];

  ngOnInit(): void {
    this.tickInterval = setInterval(() => this.tick++, 100);
  }

  ngOnDestroy(): void {
    clearInterval(this.tickInterval);
  }

  layerColor(layer: string): string {
    return this.layers.find(l => l.id === layer)?.color ?? '#666';
  }

  getNode(id: string): ArchNode | undefined {
    return this.nodes.find(n => n.id === id);
  }

  edgePath(e: ArchEdge): string {
    const from = this.getNode(e.from);
    const to = this.getNode(e.to);
    if (!from || !to) return '';
    const x1 = from.x, y1 = from.y + 2.5;
    const x2 = to.x, y2 = to.y - 2.5;
    const midY = (y1 + y2) / 2;
    return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
  }

  filterLayer(layerId: string): void {
    this.selectedLayer = this.selectedLayer === layerId ? null : layerId;
  }

  isNodeVisible(node: ArchNode): boolean {
    return !this.selectedLayer || node.layer === this.selectedLayer;
  }

  isEdgeVisible(edge: ArchEdge): boolean {
    if (!this.selectedLayer) return true;
    const from = this.getNode(edge.from);
    const to = this.getNode(edge.to);
    return (from?.layer === this.selectedLayer || to?.layer === this.selectedLayer) ?? false;
  }

  categoryColor(cat: string): string {
    return cat === 'core' ? '#00cc7a' : cat === 'specialist' ? '#3794ff' : '#e5b200';
  }
}
