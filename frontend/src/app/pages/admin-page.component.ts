import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import {
  AgentsService,
  AgentDescriptor,
  CustomAgentDefinition,
  CreateCustomAgentPayload,
  MonitoringSchema,
  RuntimeFeatureFlags,
  PresetDescriptor,
} from '../services/agents.service';
import { WorkflowService, WorkflowDefinition, WorkflowCreatePayload, WorkflowUpdatePayload } from '../services/workflow.service';
import { PolicyService, PolicyDefinition, PolicyCreatePayload } from '../services/policy.service';
import { ToolPolicyPayload } from '../services/agent-socket.service';

type AdminTab = 'agents' | 'workflows' | 'policies' | 'tools' | 'skills' | 'settings';
type CustomVisionMode = 'inherit' | 'allow' | 'deny';

@Component({
  selector: 'app-admin-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-page.component.html',
  styleUrl: './admin-page.component.scss',
})
export class AdminPageComponent implements OnInit, OnDestroy {
  activeTab: AdminTab = 'agents';

  // --- Agents ---
  systemAgents: AgentDescriptor[] = [];
  customAgents: CustomAgentDefinition[] = [];
  monitoringSchema: MonitoringSchema | null = null;
  editingAgentId: string | null = null;
  editAgent: Partial<CustomAgentDefinition> = {};
  newAgentName = '';
  newAgentId = '';
  newAgentDescription = '';
  newAgentBase = 'head-agent';
  newWorkflowText = '';
  newToolAllowInput = '';
  newToolDenyInput = '';
  newVisionMode: CustomVisionMode = 'inherit';
  agentBusy = false;

  // --- Workflows ---
  workflows: WorkflowDefinition[] = [];
  editingWorkflowId: string | null = null;
  editWorkflow: Partial<WorkflowDefinition> = {};
  newWfName = '';
  newWfDescription = '';
  newWfBaseAgent = 'head-agent';
  newWfStepsText = '';
  newWfToolAllow = '';
  newWfToolDeny = '';
  workflowBusy = false;
  workflowRunResult: string | null = null;

  // --- Policies ---
  policies: PolicyDefinition[] = [];
  editingPolicyId: string | null = null;
  editPolicy: Partial<PolicyDefinition> = {};
  newPolicyName = '';
  newPolicyAllow = '';
  newPolicyDeny = '';
  newPolicyAlsoAllow = '';
  policyBusy = false;

  // --- Tools ---
  toolCatalog: any[] = [];
  toolStats: any = null;
  toolProfiles: any[] = [];
  toolGlobalPolicy: any = null;
  selectedTool: any = null;

  // --- Skills ---
  skillsList: any[] = [];
  skillsBusy = false;
  selectedSkill: any = null;
  skillPreview: any = null;
  skillCheckResult: any = null;

  // --- Settings ---
  runtimeFeatures: RuntimeFeatureFlags = {
    long_term_memory_enabled: true,
    session_distillation_enabled: true,
    failure_journal_enabled: true,
    vision_enabled: false,
  };
  runtimeLtmDbPath = '';
  settingsBusy = false;
  settingsStatus = '';
  presets: PresetDescriptor[] = [];

  private readonly subs = new Subscription();

  constructor(
    private readonly agentsService: AgentsService,
    private readonly workflowService: WorkflowService,
    private readonly policyService: PolicyService,
    private readonly cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadAgents();
    this.loadWorkflows();
    this.loadPolicies();
    this.loadSettings();
    this.loadToolCatalog();
    this.loadSkills();
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  // ─── Tab ─────────────────────────────────────────────
  switchTab(tab: AdminTab): void {
    this.activeTab = tab;
  }

  // ─── Agents ──────────────────────────────────────────
  private loadAgents(): void {
    this.agentsService.getAgents().subscribe({
      next: agents => { this.systemAgents = agents; },
    });
    this.agentsService.getCustomAgents().subscribe({
      next: items => { this.customAgents = items; },
    });
    this.agentsService.getMonitoringSchema().subscribe({
      next: schema => { this.monitoringSchema = schema; },
    });
  }

  createAgent(): void {
    const name = this.newAgentName.trim();
    if (!name || this.agentBusy) return;

    const steps = this.newWorkflowText.split('\n').map(s => s.trim()).filter(s => s.length > 0);
    const allow = this.parseCsv(this.newToolAllowInput);
    const deny = this.parseCsv(this.newToolDenyInput);

    if (this.newVisionMode === 'allow' && !allow.includes('analyze_image')) allow.push('analyze_image');
    if (this.newVisionMode === 'deny' && !deny.includes('analyze_image')) deny.push('analyze_image');

    const payload: CreateCustomAgentPayload = {
      id: this.newAgentId.trim() || undefined,
      name,
      description: this.newAgentDescription.trim(),
      base_agent_id: this.newAgentBase,
      workflow_steps: steps,
    };
    const tp: ToolPolicyPayload = {
      allow: allow.length > 0 ? allow : undefined,
      deny: deny.length > 0 ? deny : undefined,
    };
    if ((tp.allow?.length ?? 0) > 0 || (tp.deny?.length ?? 0) > 0) {
      payload.tool_policy = tp;
    }

    this.agentBusy = true;
    this.agentsService.createCustomAgent(payload).subscribe({
      next: () => {
        this.resetAgentForm();
        this.loadAgents();
        this.agentBusy = false;
      },
      error: () => { this.agentBusy = false; },
    });
  }

  deleteAgent(agentId: string): void {
    if (!agentId || this.agentBusy) return;
    this.agentBusy = true;
    this.agentsService.deleteCustomAgent(agentId).subscribe({
      next: () => {
        this.loadAgents();
        this.agentBusy = false;
        if (this.editingAgentId === agentId) this.cancelAgentEdit();
      },
      error: () => { this.agentBusy = false; },
    });
  }

  startAgentEdit(agent: CustomAgentDefinition): void {
    this.editingAgentId = agent.id;
    this.editAgent = {
      ...agent,
      workflow_steps: [...agent.workflow_steps],
    };
  }

  cancelAgentEdit(): void {
    this.editingAgentId = null;
    this.editAgent = {};
  }

  saveAgentEdit(): void {
    if (!this.editingAgentId || this.agentBusy) return;
    this.agentBusy = true;
    this.agentsService.updateCustomAgent(this.editingAgentId, this.editAgent).subscribe({
      next: () => {
        this.cancelAgentEdit();
        this.loadAgents();
        this.agentBusy = false;
      },
      error: () => { this.agentBusy = false; },
    });
  }

  cloneAgent(agent: CustomAgentDefinition): void {
    this.newAgentName = `${agent.name} (Copy)`;
    this.newAgentId = '';
    this.newAgentDescription = agent.description;
    this.newAgentBase = agent.base_agent_id;
    this.newWorkflowText = agent.workflow_steps.join('\n');
    this.newToolAllowInput = agent.tool_policy?.allow?.join(', ') ?? '';
    this.newToolDenyInput = agent.tool_policy?.deny?.join(', ') ?? '';
  }

  get editWorkflowStepsText(): string {
    return this.editAgent.workflow_steps?.join('\n') ?? '';
  }
  set editWorkflowStepsText(value: string) {
    this.editAgent.workflow_steps = value.split('\n').map(s => s.trim()).filter(s => s.length > 0);
  }

  private resetAgentForm(): void {
    this.newAgentName = '';
    this.newAgentId = '';
    this.newAgentDescription = '';
    this.newAgentBase = 'head-agent';
    this.newWorkflowText = '';
    this.newToolAllowInput = '';
    this.newToolDenyInput = '';
    this.newVisionMode = 'inherit';
  }

  // ─── Workflows ───────────────────────────────────────
  private loadWorkflows(): void {
    this.workflowService.list().subscribe({
      next: res => { this.workflows = res.items ?? []; },
    });
  }

  createWorkflow(): void {
    const name = this.newWfName.trim();
    if (!name || this.workflowBusy) return;

    const steps = this.newWfStepsText.split('\n').map(s => s.trim()).filter(s => s.length > 0);
    const allow = this.parseCsv(this.newWfToolAllow);
    const deny = this.parseCsv(this.newWfToolDeny);

    const payload: WorkflowCreatePayload = {
      name,
      description: this.newWfDescription.trim(),
      base_agent_id: this.newWfBaseAgent,
      steps,
    };
    if (allow.length > 0 || deny.length > 0) {
      payload.tool_policy = {
        allow: allow.length > 0 ? allow : undefined,
        deny: deny.length > 0 ? deny : undefined,
      };
    }

    this.workflowBusy = true;
    this.workflowService.create(payload).subscribe({
      next: () => {
        this.resetWorkflowForm();
        this.loadWorkflows();
        this.workflowBusy = false;
      },
      error: () => { this.workflowBusy = false; },
    });
  }

  startWorkflowEdit(wf: WorkflowDefinition): void {
    this.editingWorkflowId = wf.id;
    this.editWorkflow = { ...wf, steps: [...(wf.steps ?? [])] };
  }

  cancelWorkflowEdit(): void {
    this.editingWorkflowId = null;
    this.editWorkflow = {};
  }

  saveWorkflowEdit(): void {
    if (!this.editingWorkflowId || this.workflowBusy) return;
    this.workflowBusy = true;
    const payload: WorkflowUpdatePayload = {
      id: this.editingWorkflowId,
      name: this.editWorkflow.name,
      description: this.editWorkflow.description,
      base_agent_id: this.editWorkflow.base_agent_id,
      steps: this.editWorkflow.steps,
    };
    this.workflowService.update(payload).subscribe({
      next: () => {
        this.cancelWorkflowEdit();
        this.loadWorkflows();
        this.workflowBusy = false;
      },
      error: () => { this.workflowBusy = false; },
    });
  }

  deleteWorkflow(id: string): void {
    if (!id || this.workflowBusy) return;
    this.workflowBusy = true;
    this.workflowService.delete(id).subscribe({
      next: () => {
        this.loadWorkflows();
        this.workflowBusy = false;
        if (this.editingWorkflowId === id) this.cancelWorkflowEdit();
      },
      error: () => { this.workflowBusy = false; },
    });
  }

  executeWorkflow(id: string): void {
    if (!id || this.workflowBusy) return;
    this.workflowBusy = true;
    this.workflowRunResult = null;
    this.workflowService.execute(id).subscribe({
      next: res => {
        this.workflowRunResult = `Workflow started. Run: ${res.run_id ?? '(unknown)'}`;
        this.workflowBusy = false;
      },
      error: (err) => {
        this.workflowRunResult = `Execute failed: ${err?.error?.detail ?? err.message}`;
        this.workflowBusy = false;
      },
    });
  }

  get editWfStepsText(): string {
    return this.editWorkflow.steps?.join('\n') ?? '';
  }
  set editWfStepsText(value: string) {
    this.editWorkflow.steps = value.split('\n').map(s => s.trim()).filter(s => s.length > 0);
  }

  private resetWorkflowForm(): void {
    this.newWfName = '';
    this.newWfDescription = '';
    this.newWfBaseAgent = 'head-agent';
    this.newWfStepsText = '';
    this.newWfToolAllow = '';
    this.newWfToolDeny = '';
  }

  // ─── Policies ────────────────────────────────────────
  private loadPolicies(): void {
    this.policyService.list().subscribe({
      next: res => { this.policies = res.items ?? []; },
    });
  }

  createPolicy(): void {
    const name = this.newPolicyName.trim();
    if (!name || this.policyBusy) return;

    const payload: PolicyCreatePayload = {
      name,
      allow: this.parseCsv(this.newPolicyAllow),
      deny: this.parseCsv(this.newPolicyDeny),
      also_allow: this.parseCsv(this.newPolicyAlsoAllow),
    };

    this.policyBusy = true;
    this.policyService.create(payload).subscribe({
      next: () => {
        this.resetPolicyForm();
        this.loadPolicies();
        this.policyBusy = false;
      },
      error: () => { this.policyBusy = false; },
    });
  }

  startPolicyEdit(policy: PolicyDefinition): void {
    this.editingPolicyId = policy.id;
    this.editPolicy = { ...policy };
  }

  cancelPolicyEdit(): void {
    this.editingPolicyId = null;
    this.editPolicy = {};
  }

  savePolicyEdit(): void {
    if (!this.editingPolicyId || this.policyBusy) return;
    this.policyBusy = true;
    this.policyService.update(this.editingPolicyId, this.editPolicy).subscribe({
      next: () => {
        this.cancelPolicyEdit();
        this.loadPolicies();
        this.policyBusy = false;
      },
      error: () => { this.policyBusy = false; },
    });
  }

  deletePolicy(id: string): void {
    if (!id || this.policyBusy) return;
    this.policyBusy = true;
    this.policyService.delete(id).subscribe({
      next: () => {
        this.loadPolicies();
        this.policyBusy = false;
        if (this.editingPolicyId === id) this.cancelPolicyEdit();
      },
      error: () => { this.policyBusy = false; },
    });
  }

  private resetPolicyForm(): void {
    this.newPolicyName = '';
    this.newPolicyAllow = '';
    this.newPolicyDeny = '';
    this.newPolicyAlsoAllow = '';
  }

  // ─── Tools ───────────────────────────────────────────
  private loadToolCatalog(): void {
    this.agentsService.getToolCatalog().subscribe({
      next: res => {
        this.toolCatalog = res.tools ?? [];
        this.toolGlobalPolicy = res.globalPolicy ?? null;
      },
    });
    this.agentsService.getToolStats().subscribe({
      next: res => { this.toolStats = res; },
      error: () => { this.toolStats = null; },
    });
    this.agentsService.getToolProfiles().subscribe({
      next: res => { this.toolProfiles = res.profiles ?? []; },
      error: () => { this.toolProfiles = []; },
    });
  }

  selectTool(tool: any): void {
    this.selectedTool = this.selectedTool === tool ? null : tool;
  }

  getToolTelemetry(toolName: string): any {
    return this.toolStats?.tools?.[toolName] ?? null;
  }

  // ─── Skills ──────────────────────────────────────────
  private loadSkills(): void {
    this.agentsService.getSkillsList().subscribe({
      next: res => { this.skillsList = res.items ?? []; },
      error: () => { this.skillsList = []; },
    });
  }

  selectSkill(skill: any): void {
    this.selectedSkill = this.selectedSkill === skill ? null : skill;
  }

  loadSkillPreview(): void {
    this.agentsService.getSkillPreview().subscribe({
      next: res => { this.skillPreview = res.snapshot ?? null; },
      error: () => { this.skillPreview = null; },
    });
  }

  checkSkills(): void {
    this.skillsBusy = true;
    this.agentsService.checkSkills().subscribe({
      next: res => {
        this.skillCheckResult = res;
        this.skillsBusy = false;
      },
      error: () => {
        this.skillCheckResult = null;
        this.skillsBusy = false;
      },
    });
  }

  syncSkills(): void {
    if (this.skillsBusy) return;
    this.skillsBusy = true;
    this.agentsService.syncSkills().subscribe({
      next: () => {
        this.loadSkills();
        this.skillsBusy = false;
      },
      error: () => { this.skillsBusy = false; },
    });
  }

  // ─── Settings ────────────────────────────────────────
  private loadSettings(): void {
    this.agentsService.getRuntimeFeatures().subscribe({
      next: res => {
        this.runtimeFeatures = { ...this.runtimeFeatures, ...res.featureFlags };
        if (typeof res.longTermMemoryDbPath === 'string') {
          this.runtimeLtmDbPath = res.longTermMemoryDbPath;
        }
      },
    });
    this.agentsService.getPresets().subscribe({
      next: presets => { this.presets = presets; },
    });
  }

  saveSettings(): void {
    if (this.settingsBusy) return;
    this.settingsBusy = true;
    this.settingsStatus = '';
    this.agentsService.updateRuntimeFeatures(this.runtimeFeatures, this.runtimeLtmDbPath.trim() || undefined).subscribe({
      next: res => {
        this.runtimeFeatures = { ...this.runtimeFeatures, ...res.featureFlags };
        this.settingsBusy = false;
        this.settingsStatus = res.persisted === false ? 'Updated in runtime (not persisted to .env)' : 'Saved and persisted to .env';
      },
      error: err => {
        this.settingsBusy = false;
        this.settingsStatus = `Save failed: ${err?.error?.detail ?? err.message}`;
      },
    });
  }

  // ─── Util ────────────────────────────────────────────
  private parseCsv(value: string): string[] {
    return value.split(',').map(s => s.trim()).filter(s => s.length > 0);
  }
}
