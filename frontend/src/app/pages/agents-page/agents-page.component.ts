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
  AgentDescriptor,
  AgentsService,
  CustomAgentDefinition,
  CreateCustomAgentPayload,
  MemoryOverviewResponse,
} from '../../services/agents.service';
import {
  AgentRuntimeConfig,
  ConfigService,
} from '../../services/config.service';

// ── Types ──────────────────────────────────────────

interface AgentCard {
  id: string;
  name: string;
  role: string;
  icon: string;
  category: 'core' | 'specialist' | 'industry' | 'custom';
  status: string;
  model: string;
  isCustom: boolean;
  toolCount: number;
  tools: string[];
  custom?: CustomAgentDefinition;
}

type DetailTab = 'overview' | 'config' | 'tools' | 'skills' | 'memory';

interface SkillItem {
  name: string;
  description: string;
  eligible: boolean;
  rejected_reason: string | null;
  user_invocable: boolean;
  metadata: { requires_bins: string[]; requires_env: string[]; os: string[] };
}

@Component({
  selector: 'app-agents-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agents-page.component.html',
  styleUrl: './agents-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentsPageComponent implements OnInit {

  // ── Grid state ─────────────────────────────────────
  agents: AgentCard[] = [];
  searchQuery = '';
  filterCategory: string = 'all';
  loading = true;

  // ── Detail panel ───────────────────────────────────
  selectedAgent: AgentCard | null = null;
  detailTab: DetailTab = 'overview';
  detailOpen = false;

  // ── Config ─────────────────────────────────────────
  agentConfig: AgentRuntimeConfig | null = null;
  configDraft: Record<string, unknown> = {};
  configSaving = false;
  configMessage = '';

  // ── Tools ──────────────────────────────────────────
  allTools: string[] = [];
  agentEffectiveTools: string[] = [];
  agentDenyTools: string[] = [];
  toolSearch = '';

  // ── Skills ─────────────────────────────────────────
  skills: SkillItem[] = [];
  skillsLoading = false;
  skillsMessage = '';

  // ── Memory ─────────────────────────────────────────
  memoryOverview: MemoryOverviewResponse | null = null;
  memoryLoading = false;

  // ── Create / Edit modal ────────────────────────────
  showCreateModal = false;
  editMode = false;
  createForm: CreateCustomAgentPayload = this.emptyForm();

  // ── Monitoring schema cache ────────────────────────
  private agentToolsMap = new Map<string, string[]>();

  private readonly AGENT_ICONS: Record<string, string> = {
    'head-agent': '◈', 'coder-agent': '⌨', 'review-agent': '◎',
    'researcher-agent': '◉', 'architect-agent': '◆', 'test-agent': '⬡',
    'security-agent': '⛊', 'doc-agent': '✦', 'refactor-agent': '⬢',
    'devops-agent': '▣', 'fintech-agent': '₿', 'healthtech-agent': '♥',
    'legaltech-agent': '§', 'ecommerce-agent': '◇', 'industrytech-agent': '⚙',
  };

  private readonly CATEGORIES: Record<string, 'core' | 'specialist' | 'industry'> = {
    'head-agent': 'core', 'coder-agent': 'core', 'review-agent': 'core',
    'researcher-agent': 'specialist', 'architect-agent': 'specialist',
    'test-agent': 'specialist', 'security-agent': 'specialist',
    'doc-agent': 'specialist', 'refactor-agent': 'specialist', 'devops-agent': 'specialist',
    'fintech-agent': 'industry', 'healthtech-agent': 'industry',
    'legaltech-agent': 'industry', 'ecommerce-agent': 'industry',
    'industrytech-agent': 'industry',
  };

  constructor(
    private readonly agentsService: AgentsService,
    private readonly configService: ConfigService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadAll();
  }

  // ── Data Loading ───────────────────────────────────

  private loadAll(): void {
    this.loading = true;

    // Load monitoring schema for tool counts
    this.agentsService.getMonitoringSchema().subscribe({
      next: (schema) => {
        for (const a of schema.agents) {
          this.agentToolsMap.set(a.id, a.tools);
        }
        this.loadAgents();
      },
      error: () => this.loadAgents(),
    });

    // Load tool catalog
    this.agentsService.getToolCatalog().subscribe({
      next: (res) => {
        this.allTools = res.tools ?? [];
        this.cdr.markForCheck();
      },
    });
  }

  private loadAgents(): void {
    let systemAgents: AgentDescriptor[] = [];
    let customAgents: CustomAgentDefinition[] = [];
    let loaded = 0;

    const merge = (): void => {
      if (loaded < 2) return;
      const cards: AgentCard[] = [];

      for (const a of systemAgents) {
        const tools = this.agentToolsMap.get(a.id) ?? [];
        cards.push({
          id: a.id,
          name: a.name,
          role: a.role,
          icon: this.AGENT_ICONS[a.id] ?? '◈',
          category: this.CATEGORIES[a.id] ?? 'specialist',
          status: a.status,
          model: a.defaultModel,
          isCustom: false,
          toolCount: tools.length,
          tools,
        });
      }

      for (const c of customAgents) {
        const tools = this.agentToolsMap.get(c.id) ?? [];
        cards.push({
          id: c.id,
          name: c.name,
          role: c.base_agent_id,
          icon: '★',
          category: 'custom',
          status: 'ready',
          model: '',
          isCustom: true,
          toolCount: tools.length,
          tools,
          custom: c,
        });
      }

      this.agents = cards;
      this.loading = false;
      this.cdr.markForCheck();
    };

    this.agentsService.getAgents().subscribe({
      next: (a) => { systemAgents = a; loaded++; merge(); },
      error: () => { loaded++; merge(); },
    });

    this.agentsService.getCustomAgents().subscribe({
      next: (a) => { customAgents = a; loaded++; merge(); },
      error: () => { loaded++; merge(); },
    });
  }

  // ── Filtering ──────────────────────────────────────

  get filteredAgents(): AgentCard[] {
    let list = this.agents;
    if (this.filterCategory !== 'all') {
      list = list.filter(a => a.category === this.filterCategory);
    }
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q) ||
        a.role.toLowerCase().includes(q),
      );
    }
    return list;
  }

  get categoryCounts(): Record<string, number> {
    const counts: Record<string, number> = { all: this.agents.length, core: 0, specialist: 0, industry: 0, custom: 0 };
    for (const a of this.agents) counts[a.category] = (counts[a.category] ?? 0) + 1;
    return counts;
  }

  // ── Agent Selection ────────────────────────────────

  selectAgent(agent: AgentCard): void {
    this.selectedAgent = agent;
    this.detailOpen = true;
    this.detailTab = 'overview';
    this.configMessage = '';
    this.skillsMessage = '';
    this.agentConfig = null;
    this.memoryOverview = null;

    // Load config
    this.configService.getAgentConfig(agent.id).subscribe({
      next: (res) => {
        this.agentConfig = res.config;
        this.configDraft = { ...res.config };
        this.cdr.markForCheck();
      },
      error: () => {
        this.agentConfig = null;
        this.configDraft = {};
        this.cdr.markForCheck();
      },
    });

    // Resolve effective tools
    this.agentEffectiveTools = agent.tools;
    this.agentDenyTools = [];
    this.agentsService.getToolPolicyMatrix(agent.id).subscribe({
      next: (res: any) => {
        this.agentEffectiveTools = res.effective_allow ?? res.base_tools ?? agent.tools;
        this.agentDenyTools = res.effective_deny ?? [];
        this.cdr.markForCheck();
      },
    });
  }

  closeDetail(): void {
    this.detailOpen = false;
    setTimeout(() => { this.selectedAgent = null; this.cdr.markForCheck(); }, 300);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.showCreateModal) { this.showCreateModal = false; return; }
    if (this.detailOpen) this.closeDetail();
  }

  // ── Config Tab ─────────────────────────────────────

  saveConfig(): void {
    if (!this.selectedAgent) return;
    this.configSaving = true;
    const updates = { ...this.configDraft };
    delete updates['agent_id'];
    this.configService.updateAgentConfig(this.selectedAgent.id, updates).subscribe({
      next: (res) => {
        this.configSaving = false;
        this.configMessage = `Saved ${res.changes?.length ?? 0} change(s)`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.configSaving = false;
        this.configMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  resetConfig(): void {
    if (!this.selectedAgent) return;
    this.configSaving = true;
    this.configService.resetAgentConfig(this.selectedAgent.id).subscribe({
      next: () => {
        this.configSaving = false;
        this.configMessage = 'Reset to defaults';
        this.selectAgent(this.selectedAgent!);
      },
      error: (err) => {
        this.configSaving = false;
        this.configMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Skills Tab ─────────────────────────────────────

  loadSkills(): void {
    this.detailTab = 'skills';
    if (this.skills.length > 0) return;
    this.skillsLoading = true;
    this.agentsService.getSkillsList().subscribe({
      next: (res: any) => {
        this.skills = res.items ?? [];
        this.skillsLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.skillsLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  checkSkills(): void {
    this.skillsLoading = true;
    this.agentsService.checkSkills().subscribe({
      next: (res: any) => {
        this.skillsLoading = false;
        const issues = res.issues ?? {};
        const total = Object.keys(issues.missing_env ?? {}).length +
                      Object.keys(issues.missing_bins ?? {}).length +
                      Object.keys(issues.os_mismatch ?? {}).length;
        this.skillsMessage = total > 0 ? `${total} issue(s) found` : 'All skills eligible';
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.skillsLoading = false;
        this.skillsMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  syncSkills(): void {
    this.skillsLoading = true;
    this.agentsService.syncSkills().subscribe({
      next: (res: any) => {
        this.skillsLoading = false;
        this.skillsMessage = `Synced ${res.applied_count ?? 0} skill(s)`;
        this.skills = [];
        this.loadSkills();
      },
      error: (err) => {
        this.skillsLoading = false;
        this.skillsMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Memory Tab ─────────────────────────────────────

  loadMemory(): void {
    this.detailTab = 'memory';
    this.memoryLoading = true;
    this.agentsService.getMemoryOverview({ limit_sessions: 20, include_content: false }).subscribe({
      next: (res) => {
        this.memoryOverview = res;
        this.memoryLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.memoryLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Tools Tab helpers ──────────────────────────────

  get filteredAllTools(): string[] {
    if (!this.toolSearch) return this.allTools;
    const q = this.toolSearch.toLowerCase();
    return this.allTools.filter(t => t.toLowerCase().includes(q));
  }

  isToolAllowed(tool: string): boolean {
    return this.agentEffectiveTools.includes(tool);
  }

  isToolDenied(tool: string): boolean {
    return this.agentDenyTools.includes(tool);
  }

  isToolMandatoryDeny(tool: string): boolean {
    const md = (this.agentConfig?.mandatory_deny_tools ?? []) as string[];
    return md.includes(tool);
  }

  // ── Create / Edit ──────────────────────────────────

  openCreate(): void {
    this.editMode = false;
    this.createForm = this.emptyForm();
    this.showCreateModal = true;
  }

  openClone(agent: AgentCard): void {
    this.editMode = false;
    this.createForm = {
      name: `${agent.name} (Clone)`,
      base_agent_id: agent.isCustom ? (agent.custom?.base_agent_id ?? 'head-agent') : agent.id,
      workflow_steps: agent.custom?.workflow_steps ?? [],
      tool_policy: agent.custom?.tool_policy ? { ...agent.custom.tool_policy } : undefined,
    };
    this.showCreateModal = true;
  }

  openEdit(agent: AgentCard): void {
    if (!agent.isCustom || !agent.custom) return;
    this.editMode = true;
    this.createForm = {
      id: agent.custom.id,
      name: agent.custom.name,
      description: agent.custom.description,
      base_agent_id: agent.custom.base_agent_id,
      workflow_steps: [...agent.custom.workflow_steps],
      tool_policy: agent.custom.tool_policy ? { ...agent.custom.tool_policy } : undefined,
      allow_subrun_delegation: agent.custom.allow_subrun_delegation,
    };
    this.showCreateModal = true;
  }

  submitCreate(): void {
    if (!this.createForm.name?.trim()) return;

    if (this.editMode && this.createForm.id) {
      this.agentsService.updateCustomAgent(this.createForm.id, this.createForm as any).subscribe({
        next: () => {
          this.showCreateModal = false;
          this.loadAll();
        },
        error: (err) => alert(`Update failed: ${err?.error?.detail ?? err.message}`),
      });
    } else {
      this.agentsService.createCustomAgent(this.createForm).subscribe({
        next: () => {
          this.showCreateModal = false;
          this.loadAll();
        },
        error: (err) => alert(`Create failed: ${err?.error?.detail ?? err.message}`),
      });
    }
  }

  deleteAgent(agent: AgentCard): void {
    if (!agent.isCustom) return;
    this.agentsService.deleteCustomAgent(agent.id).subscribe({
      next: () => {
        if (this.selectedAgent?.id === agent.id) this.closeDetail();
        this.loadAll();
      },
      error: (err) => alert(`Delete failed: ${err?.error?.detail ?? err.message}`),
    });
  }

  // ── Workflow steps helpers ─────────────────────────

  get workflowStepsText(): string {
    return (this.createForm.workflow_steps ?? []).join('\n');
  }

  set workflowStepsText(val: string) {
    this.createForm.workflow_steps = val.split('\n').filter(s => s.trim());
  }

  get toolAllowText(): string {
    return (this.createForm.tool_policy?.allow ?? []).join(', ');
  }

  set toolAllowText(val: string) {
    if (!this.createForm.tool_policy) this.createForm.tool_policy = {};
    this.createForm.tool_policy.allow = val.split(',').map(s => s.trim()).filter(Boolean);
  }

  get toolDenyText(): string {
    return (this.createForm.tool_policy?.deny ?? []).join(', ');
  }

  set toolDenyText(val: string) {
    if (!this.createForm.tool_policy) this.createForm.tool_policy = {};
    this.createForm.tool_policy.deny = val.split(',').map(s => s.trim()).filter(Boolean);
  }

  // ── Helpers ────────────────────────────────────────

  isBoolean(v: unknown): boolean { return v === true || v === false; }
  isNumber(v: unknown): boolean { return typeof v === 'number'; }
  isArray(v: unknown): boolean { return Array.isArray(v); }

  objectKeys(obj: Record<string, unknown>): string[] {
    return obj ? Object.keys(obj) : [];
  }

  configKeys(): string[] {
    return Object.keys(this.configDraft).filter(k => k !== 'agent_id');
  }

  formatBytes(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  private emptyForm(): CreateCustomAgentPayload {
    return {
      name: '',
      description: '',
      base_agent_id: 'head-agent',
      workflow_steps: [],
      allow_subrun_delegation: false,
      tool_policy: undefined,
    };
  }
}
