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
  AgentsService,
  UnifiedAgentRecord,
  MemoryOverviewResponse,
} from '../../services/agents.service';

// ── Types ──────────────────────────────────────────

type PageTab = 'agents' | 'tools' | 'skills';

interface ToolCatalogItem {
  name: string;
  description?: string;
  capabilities?: string[];
  config?: Record<string, unknown>;
}

interface AgentCard {
  id: string;
  name: string;
  role: string;
  icon: string;
  category: 'core' | 'specialist' | 'industry' | 'custom';
  status: string;
  model: string;
  description: string;
  enabled: boolean;
  origin: 'builtin' | 'custom';
  isCustom: boolean;
  toolCount: number;
  tools: string[];
  record: UnifiedAgentRecord;
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

  // ── Page-level tab ─────────────────────────────────
  pageTab: PageTab = 'agents';

  // ── Grid state ─────────────────────────────────────
  agents: AgentCard[] = [];
  searchQuery = '';
  filterCategory: string = 'all';
  loading = true;

  // ── Detail panel ───────────────────────────────────
  selectedAgent: AgentCard | null = null;
  detailTab: DetailTab = 'overview';
  detailOpen = false;

  // ── Tools Tab (page-level) ─────────────────────────
  toolsCatalog: ToolCatalogItem[] = [];
  toolsCatalogRaw: any = null;
  toolsTabLoading = false;
  toolsTabSearch = '';
  selectedToolItem: ToolCatalogItem | null = null;
  toolItemConfig: Record<string, unknown> = {};
  toolItemConfigLoading = false;
  toolItemConfigMessage = '';
  securityPatterns: any[] = [];
  securityPatternsLoading = false;
  newPatternForm = { pattern: '', action: 'deny', description: '' };

  // ── Skills Tab (page-level) ────────────────────────
  allSkillsTab: SkillItem[] = [];
  skillsTabLoading = false;
  skillsTabMessage = '';
  selectedSkillTab: SkillItem | null = null;
  skillDetailContent = '';
  skillDetailLoading = false;
  showSkillModal = false;
  skillEditMode = false;
  skillForm = { name: '', description: '', body: '', requires_bins: '', requires_env: '', os: 'windows,linux,darwin', user_invocable: true, disable_model_invocation: false };

  // ── Config (from unified record constraints) ──────
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
  editingRecord: UnifiedAgentRecord | null = null;
  createForm = this.emptyForm();

  // ── Monitoring schema cache ────────────────────────
  private agentToolsMap = new Map<string, string[]>();

  private readonly AGENT_ICONS: Record<string, string> = {
    'head-agent': '◈', 'coder-agent': '⌨', 'review-agent': '◎',
    'researcher-agent': '◉', 'architect-agent': '◆', 'test-agent': '⬡',
    'security-agent': '⛊', 'doc-agent': '✦', 'refactor-agent': '⬢',
    'devops-agent': '▣', 'fintech-agent': '₿', 'healthtech-agent': '♥',
    'legaltech-agent': '§', 'ecommerce-agent': '◇', 'industrytech-agent': '⚙',
  };

  constructor(
    private readonly agentsService: AgentsService,
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
    this.agentsService.getAgentsFromStore().subscribe({
      next: (records) => {
        const cards: AgentCard[] = records.map(r => {
          const tools = this.agentToolsMap.get(r.agentId) ?? [];
          return {
            id: r.agentId,
            name: r.displayName || r.agentId,
            role: r.role,
            icon: this.AGENT_ICONS[r.agentId] ?? (r.origin === 'custom' ? '★' : '◈'),
            category: r.category,
            status: r.enabled ? 'ready' : 'disabled',
            model: '',
            description: r.description,
            enabled: r.enabled,
            origin: r.origin,
            isCustom: r.origin === 'custom',
            toolCount: tools.length,
            tools,
            record: r,
          };
        });
        this.agents = cards;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.agents = [];
        this.loading = false;
        this.cdr.markForCheck();
      },
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
        a.role.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q),
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
    this.memoryOverview = null;

    // Build config draft from unified record constraints
    this.configDraft = { ...agent.record.constraints };

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
    if (this.showSkillModal) { this.showSkillModal = false; return; }
    if (this.detailOpen) this.closeDetail();
  }

  // ── Enable / Disable ──────────────────────────────

  toggleEnabled(agent: AgentCard, event: Event): void {
    event.stopPropagation();
    const newEnabled = !agent.enabled;
    this.agentsService.patchAgent(agent.id, { enabled: newEnabled }).subscribe({
      next: () => this.loadAll(),
      error: (err) => alert(`Toggle failed: ${err?.error?.detail ?? err.message}`),
    });
  }

  // ── Config Tab ─────────────────────────────────────

  saveConfig(): void {
    if (!this.selectedAgent) return;
    this.configSaving = true;
    this.agentsService.patchAgent(this.selectedAgent.id, { constraints: this.configDraft }).subscribe({
      next: (updated) => {
        this.configSaving = false;
        this.configMessage = 'Config saved';
        // Update the local record
        if (this.selectedAgent) {
          this.selectedAgent.record = updated;
          this.configDraft = { ...updated.constraints };
        }
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
    if (this.selectedAgent.origin !== 'builtin') return;
    this.configSaving = true;
    this.agentsService.resetAgent(this.selectedAgent.id).subscribe({
      next: (updated) => {
        this.configSaving = false;
        this.configMessage = 'Reset to factory defaults';
        if (this.selectedAgent) {
          this.selectedAgent.record = updated;
          this.configDraft = { ...updated.constraints };
        }
        this.cdr.markForCheck();
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
    return (this.selectedAgent?.record.toolPolicy.mandatory_deny ?? []).includes(tool);
  }

  // ── Create / Edit ──────────────────────────────────

  openCreate(): void {
    this.editMode = false;
    this.editingRecord = null;
    this.createForm = this.emptyForm();
    this.showCreateModal = true;
  }

  openClone(agent: AgentCard): void {
    this.editMode = false;
    this.editingRecord = null;
    const r = agent.record;
    this.createForm = {
      display_name: `${r.displayName} (Clone)`,
      description: r.description,
      base_agent_id: r.customWorkflow?.base_agent_id ?? agent.id,
      workflow_steps: r.customWorkflow?.workflow_steps ?? [],
      allow_subrun_delegation: r.customWorkflow?.allow_subrun_delegation ?? false,
      tool_allow: (r.toolPolicy.additional_allow ?? []).join(', '),
      tool_deny: (r.toolPolicy.additional_deny ?? []).join(', '),
    };
    this.showCreateModal = true;
  }

  openEdit(agent: AgentCard): void {
    this.editMode = true;
    this.editingRecord = agent.record;
    const r = agent.record;
    this.createForm = {
      display_name: r.displayName,
      description: r.description,
      base_agent_id: r.customWorkflow?.base_agent_id ?? 'head-agent',
      workflow_steps: r.customWorkflow?.workflow_steps ?? [],
      allow_subrun_delegation: r.customWorkflow?.allow_subrun_delegation ?? false,
      tool_allow: (r.toolPolicy.additional_allow ?? []).join(', '),
      tool_deny: (r.toolPolicy.additional_deny ?? []).join(', '),
    };
    this.showCreateModal = true;
  }

  submitCreate(): void {
    if (!this.createForm.display_name?.trim()) return;

    const toolAllow = this.createForm.tool_allow.split(',').map(s => s.trim()).filter(Boolean);
    const toolDeny = this.createForm.tool_deny.split(',').map(s => s.trim()).filter(Boolean);

    if (this.editMode && this.editingRecord) {
      // Patch existing agent
      const patch: Record<string, unknown> = {
        display_name: this.createForm.display_name.trim(),
        description: this.createForm.description.trim(),
        tool_policy: {
          additional_allow: toolAllow,
          additional_deny: toolDeny,
        },
      };
      if (this.editingRecord.origin === 'custom') {
        patch['custom_workflow'] = {
          base_agent_id: this.createForm.base_agent_id,
          workflow_steps: this.createForm.workflow_steps,
          allow_subrun_delegation: this.createForm.allow_subrun_delegation,
        };
      }
      this.agentsService.patchAgent(this.editingRecord.agentId, patch).subscribe({
        next: () => {
          this.showCreateModal = false;
          this.loadAll();
        },
        error: (err) => alert(`Update failed: ${err?.error?.detail ?? err.message}`),
      });
    } else {
      // Create new custom agent
      const data: Record<string, unknown> = {
        display_name: this.createForm.display_name.trim(),
        description: this.createForm.description.trim(),
        origin: 'custom',
        category: 'custom',
        tool_policy: {
          additional_allow: toolAllow,
          additional_deny: toolDeny,
        },
        custom_workflow: {
          base_agent_id: this.createForm.base_agent_id,
          workflow_steps: this.createForm.workflow_steps,
          allow_subrun_delegation: this.createForm.allow_subrun_delegation,
        },
      };
      this.agentsService.createUnifiedAgent(data).subscribe({
        next: () => {
          this.showCreateModal = false;
          this.loadAll();
        },
        error: (err) => alert(`Create failed: ${err?.error?.detail ?? err.message}`),
      });
    }
  }

  deleteAgent(agent: AgentCard): void {
    if (agent.origin === 'builtin') return;
    this.agentsService.deleteUnifiedAgent(agent.id).subscribe({
      next: () => {
        if (this.selectedAgent?.id === agent.id) this.closeDetail();
        this.loadAll();
      },
      error: (err) => alert(`Delete failed: ${err?.error?.detail ?? err.message}`),
    });
  }

  resetAgent(agent: AgentCard): void {
    if (agent.origin !== 'builtin') return;
    this.agentsService.resetAgent(agent.id).subscribe({
      next: () => this.loadAll(),
      error: (err) => alert(`Reset failed: ${err?.error?.detail ?? err.message}`),
    });
  }

  // ── Page-level tab switching ─────────────────────

  switchToTools(): void {
    this.pageTab = 'tools';
    if (this.toolsCatalog.length === 0) this.loadToolsCatalog();
  }

  switchToSkills(): void {
    this.pageTab = 'skills';
    if (this.allSkillsTab.length === 0) this.loadAllSkills();
  }

  // ── Tools Tab (page-level) methods ────────────────

  private loadToolsCatalog(): void {
    this.toolsTabLoading = true;
    this.agentsService.getToolCatalog().subscribe({
      next: (res: any) => {
        this.toolsCatalogRaw = res;
        // Tools can be strings or objects
        const rawTools = res.tools ?? [];
        this.toolsCatalog = rawTools.map((t: any) =>
          typeof t === 'string' ? { name: t } : { name: t.name ?? t, description: t.description, capabilities: t.capabilities, config: t.config }
        );
        this.toolsTabLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.toolsTabLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  get filteredToolsCatalog(): ToolCatalogItem[] {
    if (!this.toolsTabSearch) return this.toolsCatalog;
    const q = this.toolsTabSearch.toLowerCase();
    return this.toolsCatalog.filter(t => t.name.toLowerCase().includes(q) || (t.description ?? '').toLowerCase().includes(q));
  }

  selectToolItem(tool: ToolCatalogItem): void {
    this.selectedToolItem = tool;
    this.toolItemConfig = {};
    this.toolItemConfigMessage = '';
    this.toolItemConfigLoading = true;
    this.agentsService.getToolConfig(tool.name).subscribe({
      next: (res: any) => {
        this.toolItemConfig = res.config ?? res ?? {};
        this.toolItemConfigLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.toolItemConfig = {};
        this.toolItemConfigLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  saveToolConfig(): void {
    if (!this.selectedToolItem) return;
    this.agentsService.updateToolConfig(this.selectedToolItem.name, this.toolItemConfig).subscribe({
      next: () => {
        this.toolItemConfigMessage = 'Config saved';
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.toolItemConfigMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  resetToolItemConfig(): void {
    if (!this.selectedToolItem) return;
    this.agentsService.resetToolConfig(this.selectedToolItem.name).subscribe({
      next: (res: any) => {
        this.toolItemConfig = res.config ?? {};
        this.toolItemConfigMessage = 'Reset to defaults';
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.toolItemConfigMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  closeToolDetail(): void {
    this.selectedToolItem = null;
    this.toolItemConfigMessage = '';
  }

  loadSecurityPatterns(): void {
    this.securityPatternsLoading = true;
    this.agentsService.getSecurityPatterns().subscribe({
      next: (res: any) => {
        this.securityPatterns = res.patterns ?? [];
        this.securityPatternsLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.securityPatternsLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  addSecurityPattern(): void {
    if (!this.newPatternForm.pattern.trim()) return;
    this.agentsService.addSecurityPattern(this.newPatternForm).subscribe({
      next: () => {
        this.newPatternForm = { pattern: '', action: 'deny', description: '' };
        this.loadSecurityPatterns();
      },
      error: (err) => alert(`Error: ${err?.error?.detail ?? err.message}`),
    });
  }

  toolConfigKeys(): string[] {
    return Object.keys(this.toolItemConfig);
  }

  // ── Skills Tab (page-level) methods ───────────────

  private loadAllSkills(): void {
    this.skillsTabLoading = true;
    this.agentsService.getSkillsList().subscribe({
      next: (res: any) => {
        this.allSkillsTab = res.items ?? [];
        this.skillsTabLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.skillsTabLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  selectSkillTab(skill: SkillItem): void {
    this.selectedSkillTab = skill;
    this.skillDetailLoading = true;
    this.skillDetailContent = '';
    this.agentsService.getSkill(skill.name).subscribe({
      next: (res: any) => {
        this.skillDetailContent = res.body ?? res.raw ?? '';
        this.skillDetailLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.skillDetailContent = '';
        this.skillDetailLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  closeSkillDetail(): void {
    this.selectedSkillTab = null;
    this.skillDetailContent = '';
  }

  openCreateSkill(): void {
    this.skillEditMode = false;
    this.skillForm = { name: '', description: '', body: '', requires_bins: '', requires_env: '', os: 'windows,linux,darwin', user_invocable: true, disable_model_invocation: false };
    this.showSkillModal = true;
  }

  openEditSkill(skill: SkillItem): void {
    this.skillEditMode = true;
    this.skillForm = {
      name: skill.name,
      description: skill.description || '',
      body: this.skillDetailContent || '',
      requires_bins: (skill.metadata?.requires_bins ?? []).join(', '),
      requires_env: (skill.metadata?.requires_env ?? []).join(', '),
      os: (skill.metadata?.os ?? ['windows', 'linux', 'darwin']).join(','),
      user_invocable: skill.user_invocable ?? true,
      disable_model_invocation: false,
    };
    this.showSkillModal = true;
  }

  submitSkill(): void {
    if (!this.skillForm.name?.trim()) return;
    if (this.skillEditMode) {
      this.agentsService.updateSkill(this.skillForm.name, {
        description: this.skillForm.description,
        body: this.skillForm.body,
        requires_bins: this.skillForm.requires_bins,
        requires_env: this.skillForm.requires_env,
        os: this.skillForm.os,
        user_invocable: this.skillForm.user_invocable,
        disable_model_invocation: this.skillForm.disable_model_invocation,
      }).subscribe({
        next: () => {
          this.showSkillModal = false;
          this.skillsTabMessage = 'Skill updated';
          this.allSkillsTab = [];
          this.loadAllSkills();
          this.cdr.markForCheck();
        },
        error: (err) => {
          this.skillsTabMessage = `Error: ${err?.error?.detail ?? err.message}`;
          this.cdr.markForCheck();
        },
      });
    } else {
      this.agentsService.createSkill({
        name: this.skillForm.name,
        description: this.skillForm.description,
        body: this.skillForm.body,
        requires_bins: this.skillForm.requires_bins,
        requires_env: this.skillForm.requires_env,
        os: this.skillForm.os,
        user_invocable: this.skillForm.user_invocable,
        disable_model_invocation: this.skillForm.disable_model_invocation,
      }).subscribe({
        next: () => {
          this.showSkillModal = false;
          this.skillsTabMessage = 'Skill created';
          this.allSkillsTab = [];
          this.loadAllSkills();
          this.cdr.markForCheck();
        },
        error: (err) => {
          this.skillsTabMessage = `Error: ${err?.error?.detail ?? err.message}`;
          this.cdr.markForCheck();
        },
      });
    }
  }

  deleteSkillTab(skill: SkillItem): void {
    this.agentsService.deleteSkill(skill.name).subscribe({
      next: () => {
        this.skillsTabMessage = `Deleted '${skill.name}'`;
        if (this.selectedSkillTab?.name === skill.name) this.closeSkillDetail();
        this.allSkillsTab = [];
        this.loadAllSkills();
      },
      error: (err) => {
        this.skillsTabMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Form helpers ───────────────────────────────────

  get workflowStepsText(): string {
    return (this.createForm.workflow_steps ?? []).join('\n');
  }

  set workflowStepsText(val: string) {
    this.createForm.workflow_steps = val.split('\n').filter(s => s.trim());
  }

  // ── Helpers ────────────────────────────────────────

  isBoolean(v: unknown): boolean { return v === true || v === false; }
  isNumber(v: unknown): boolean { return typeof v === 'number'; }
  isArray(v: unknown): boolean { return Array.isArray(v); }

  configKeys(): string[] {
    return Object.keys(this.configDraft);
  }

  formatBytes(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  private emptyForm() {
    return {
      display_name: '',
      description: '',
      base_agent_id: 'head-agent',
      workflow_steps: [] as string[],
      allow_subrun_delegation: false,
      tool_allow: '',
      tool_deny: '',
    };
  }
}
