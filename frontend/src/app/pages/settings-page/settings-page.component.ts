import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import {
  AgentRuntimeConfig,
  AudioDep,
  ConfigDiffResponse,
  ConfigHealthResponse,
  ConfigService,
  SecurityPattern,
  SectionFieldMeta,
  SectionMeta,
  ToolRuntimeConfig,
} from '../../services/config.service';

// ── Sidebar category grouping ──────────────────────

interface SidebarCategory {
  id: string;
  label: string;
  icon: string;
  sectionKeys: string[];
}

type ViewMode = 'config' | 'agents' | 'tools' | 'execution' | 'security' | 'diff' | 'health';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPageComponent implements OnInit {

  // ── Sidebar state ──────────────────────────────────
  viewMode: ViewMode = 'config';
  searchQuery = '';
  expandedCategories = new Set<string>();

  // ── Config sections ────────────────────────────────
  sections: SectionMeta[] = [];
  selectedSectionKey = '';
  sectionValues: Record<string, unknown> = {};
  sectionDraft: Record<string, unknown> = {};
  sectionSaving = false;
  sectionMessage = '';
  sectionMessageType: 'ok' | 'err' = 'ok';

  // ── Agent configs ──────────────────────────────────
  agentConfigs: AgentRuntimeConfig[] = [];
  selectedAgentId = '';
  agentDraft: Record<string, unknown> = {};
  agentSaving = false;
  agentMessage = '';

  // ── Tool configs ───────────────────────────────────
  toolConfigs: ToolRuntimeConfig[] = [];
  selectedToolName = '';
  toolDraft: Record<string, unknown> = {};
  toolSaving = false;
  toolMessage = '';

  // ── Execution config ──────────────────────────────
  executionConfig: Record<string, unknown> = {};
  executionDraft: Record<string, unknown> = {};
  loopConfig: Record<string, unknown> = {};
  loopDraft: Record<string, unknown> = {};
  executionSaving = false;
  executionMessage = '';

  // ── Security ───────────────────────────────────────
  securityPatterns: SecurityPattern[] = [];
  newPatternValue = '';
  newPatternReason = '';
  securitySaving = false;
  securityMessage = '';

  // ── Audio Dependencies ───────────────────────────────
  audioDeps: AudioDep[] = [];
  audioDepsLoading = false;
  audioDepsInstalling: string | null = null;
  audioDepsMessage = '';

  // ── Diff & Health ──────────────────────────────────
  diffData: ConfigDiffResponse | null = null;
  healthData: ConfigHealthResponse | null = null;

  // ── Loading ────────────────────────────────────────
  loading = true;

  readonly categories: SidebarCategory[] = [
    { id: 'core',       label: 'Core & Infra',     icon: '◈', sectionKeys: ['core', 'infra'] },
    { id: 'llm',        label: 'LLM & Models',     icon: '◆', sectionKeys: ['llm', 'model_health'] },
    { id: 'pipeline',   label: 'Pipeline',         icon: '⬡', sectionKeys: ['pipeline', 'runner', 'reflection'] },
    { id: 'memory',     label: 'Memory & Session',icon: '◉', sectionKeys: ['memory', 'session'] },
    { id: 'tools_cfg',  label: 'Tool Execution',   icon: '⬢', sectionKeys: ['tool_execution', 'tool_loop'] },
    { id: 'security',   label: 'Security',         icon: '⛊', sectionKeys: ['security'] },
    { id: 'agents_cfg', label: 'Agent Names',      icon: '◎', sectionKeys: ['agent_names'] },
    { id: 'prompts',    label: 'Prompts',          icon: '✦', sectionKeys: ['prompts'] },
    { id: 'extensions', label: 'Extensions',       icon: '◇', sectionKeys: ['browser', 'repl', 'multimodal', 'rag', 'vision_web', 'skills'] },
    { id: 'subruns',    label: 'Subruns',          icon: '▣', sectionKeys: ['subrun'] },
  ];

  constructor(
    private readonly configService: ConfigService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadSections();
  }

  // ── Data Loading ───────────────────────────────────

  private loadSections(): void {
    this.loading = true;
    this.configService.getSections().subscribe({
      next: (res) => {
        this.sections = res.sections;
        this.loading = false;
        // Auto-expand first category and select first section
        if (this.categories.length > 0) {
          this.expandedCategories.add(this.categories[0].id);
          const firstKey = this.categories[0].sectionKeys[0];
          if (this.sections.some(s => s.key === firstKey)) {
            this.selectSection(firstKey);
          }
        }
        this.cdr.markForCheck();
      },
      error: () => {
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  selectSection(key: string): void {
    this.viewMode = 'config';
    this.selectedSectionKey = key;
    this.sectionMessage = '';
    this.configService.getSection(key).subscribe({
      next: (res) => {
        this.sectionValues = { ...res.values };
        this.sectionDraft = { ...res.values };
        this.autoCheckAudioDeps(res.values);
        this.cdr.markForCheck();
      },
    });
  }

  loadAgentConfigs(): void {
    this.viewMode = 'agents';
    this.agentMessage = '';
    this.configService.getAgentConfigs().subscribe({
      next: (res) => {
        this.agentConfigs = res.agents;
        if (res.agents.length > 0 && !this.selectedAgentId) {
          this.selectAgent(res.agents[0].agent_id);
        }
        this.cdr.markForCheck();
      },
    });
  }

  selectAgent(agentId: string): void {
    this.selectedAgentId = agentId;
    this.agentMessage = '';
    this.configService.getAgentConfig(agentId).subscribe({
      next: (res) => {
        this.agentDraft = { ...res.config };
        this.cdr.markForCheck();
      },
    });
  }

  loadToolConfigs(): void {
    this.viewMode = 'tools';
    this.toolMessage = '';
    this.configService.getToolConfigs().subscribe({
      next: (res) => {
        this.toolConfigs = res.tools;
        if (res.tools.length > 0 && !this.selectedToolName) {
          this.selectTool(res.tools[0].tool_name);
        }
        this.cdr.markForCheck();
      },
    });
  }

  selectTool(toolName: string): void {
    this.selectedToolName = toolName;
    this.toolMessage = '';
    this.configService.getToolConfig(toolName).subscribe({
      next: (res) => {
        this.toolDraft = { ...res.config };
        this.cdr.markForCheck();
      },
    });
  }

  loadExecutionConfig(): void {
    this.viewMode = 'execution';
    this.executionMessage = '';
    this.configService.getExecutionConfig().subscribe({
      next: (res) => {
        this.executionConfig = { ...res.budget, ...res.result_processing };
        this.executionDraft = { ...this.executionConfig };
        this.loopConfig = { ...res.loop_detection };
        this.loopDraft = { ...res.loop_detection };
        this.cdr.markForCheck();
      },
    });
  }

  loadSecurityView(): void {
    this.viewMode = 'security';
    this.securityMessage = '';
    this.configService.getSecurityPatterns().subscribe({
      next: (res) => {
        this.securityPatterns = res.patterns;
        this.cdr.markForCheck();
      },
    });
  }

  loadDiff(): void {
    this.viewMode = 'diff';
    this.configService.getDiff().subscribe({
      next: (res) => {
        this.diffData = res;
        this.cdr.markForCheck();
      },
    });
  }

  loadHealth(): void {
    this.viewMode = 'health';
    this.configService.getHealth().subscribe({
      next: (res) => {
        this.healthData = res;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Save / Reset ──────────────────────────────────

  saveSection(): void {
    if (!this.selectedSectionKey) return;
    const changes: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(this.sectionDraft)) {
      if (JSON.stringify(v) !== JSON.stringify(this.sectionValues[k])) {
        changes[k] = v;
      }
    }
    if (Object.keys(changes).length === 0) {
      this.flashMessage('section', 'No changes to save', 'ok');
      return;
    }
    this.sectionSaving = true;
    this.configService.updateSection(this.selectedSectionKey, changes).subscribe({
      next: (res) => {
        this.sectionSaving = false;
        const count = res.changes?.length ?? 0;
        if (res.validation_errors?.length) {
          this.flashMessage('section', `Saved ${count} field(s) with warnings: ${res.validation_errors.join(', ')}`, 'err');
        } else {
          this.flashMessage('section', `Saved ${count} field(s)`, 'ok');
        }
        // Refresh values
        this.selectSection(this.selectedSectionKey);
      },
      error: (err) => {
        this.sectionSaving = false;
        this.flashMessage('section', `Save failed: ${err?.error?.detail ?? err.message}`, 'err');
      },
    });
  }

  resetSection(): void {
    if (!this.selectedSectionKey) return;
    this.sectionSaving = true;
    this.configService.resetSection(this.selectedSectionKey).subscribe({
      next: (res) => {
        this.sectionSaving = false;
        this.flashMessage('section', `Reset ${res.reset_fields?.length ?? 0} field(s) to defaults`, 'ok');
        this.selectSection(this.selectedSectionKey);
      },
      error: (err) => {
        this.sectionSaving = false;
        this.flashMessage('section', `Reset failed: ${err?.error?.detail ?? err.message}`, 'err');
      },
    });
  }

  saveAgentConfig(): void {
    if (!this.selectedAgentId) return;
    this.agentSaving = true;
    const updates = { ...this.agentDraft };
    delete updates['agent_id'];
    this.configService.updateAgentConfig(this.selectedAgentId, updates).subscribe({
      next: (res) => {
        this.agentSaving = false;
        this.agentMessage = `Saved ${res.changes?.length ?? 0} change(s)`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.agentSaving = false;
        this.agentMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  resetAgentConfig(): void {
    if (!this.selectedAgentId) return;
    this.agentSaving = true;
    this.configService.resetAgentConfig(this.selectedAgentId).subscribe({
      next: () => {
        this.agentSaving = false;
        this.agentMessage = 'Reset to defaults';
        this.selectAgent(this.selectedAgentId);
      },
      error: (err) => {
        this.agentSaving = false;
        this.agentMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  saveToolConfig(): void {
    if (!this.selectedToolName) return;
    this.toolSaving = true;
    const updates = { ...this.toolDraft };
    delete updates['tool_name'];
    this.configService.updateToolConfig(this.selectedToolName, updates).subscribe({
      next: (res) => {
        this.toolSaving = false;
        this.toolMessage = `Saved ${res.changes?.length ?? 0} change(s)`;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.toolSaving = false;
        this.toolMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  resetToolConfig(): void {
    if (!this.selectedToolName) return;
    this.toolSaving = true;
    this.configService.resetToolConfig(this.selectedToolName).subscribe({
      next: () => {
        this.toolSaving = false;
        this.toolMessage = 'Reset to defaults';
        this.selectTool(this.selectedToolName);
      },
      error: (err) => {
        this.toolSaving = false;
        this.toolMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  saveExecutionConfig(): void {
    this.executionSaving = true;
    this.configService.updateExecutionConfig(this.executionDraft).subscribe({
      next: () => {
        this.configService.updateLoopDetectionConfig(this.loopDraft).subscribe({
          next: () => {
            this.executionSaving = false;
            this.executionMessage = 'Execution config saved';
            this.cdr.markForCheck();
          },
          error: (err) => {
            this.executionSaving = false;
            this.executionMessage = `Loop config error: ${err?.error?.detail ?? err.message}`;
            this.cdr.markForCheck();
          },
        });
      },
      error: (err) => {
        this.executionSaving = false;
        this.executionMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  addSecurityPattern(): void {
    const p = this.newPatternValue.trim();
    const r = this.newPatternReason.trim();
    if (!p || !r) return;
    this.securitySaving = true;
    this.configService.addSecurityPattern(p, r).subscribe({
      next: () => {
        this.securitySaving = false;
        this.newPatternValue = '';
        this.newPatternReason = '';
        this.securityMessage = 'Pattern added';
        this.loadSecurityView();
      },
      error: (err) => {
        this.securitySaving = false;
        this.securityMessage = `Error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Helpers ────────────────────────────────────────

  getSectionMeta(key: string): SectionMeta | undefined {
    return this.sections.find(s => s.key === key);
  }

  get selectedSectionMeta(): SectionMeta | undefined {
    return this.sections.find(s => s.key === this.selectedSectionKey);
  }

  get filteredFields(): SectionFieldMeta[] {
    const meta = this.selectedSectionMeta;
    if (!meta) return [];
    if (!this.searchQuery) return meta.fields;
    const q = this.searchQuery.toLowerCase();
    return meta.fields.filter(f =>
      f.name.toLowerCase().includes(q) ||
      (f.description ?? '').toLowerCase().includes(q),
    );
  }

  get filteredCategories(): SidebarCategory[] {
    if (!this.searchQuery) return this.categories;
    const q = this.searchQuery.toLowerCase();
    return this.categories.filter(cat =>
      cat.label.toLowerCase().includes(q) ||
      cat.sectionKeys.some(k => {
        const meta = this.getSectionMeta(k);
        if (!meta) return false;
        return meta.label.toLowerCase().includes(q) ||
          meta.fields.some(f => f.name.toLowerCase().includes(q));
      }),
    );
  }

  sectionFieldCount(key: string): number {
    return this.getSectionMeta(key)?.field_count ?? 0;
  }

  sectionLabel(key: string): string {
    return this.getSectionMeta(key)?.label ?? key;
  }

  toggleCategory(id: string): void {
    if (this.expandedCategories.has(id)) {
      this.expandedCategories.delete(id);
    } else {
      this.expandedCategories.add(id);
    }
  }

  isFieldModified(field: string): boolean {
    return JSON.stringify(this.sectionDraft[field]) !== JSON.stringify(this.sectionValues[field]);
  }

  get modifiedFieldCount(): number {
    let count = 0;
    for (const k of Object.keys(this.sectionDraft)) {
      if (JSON.stringify(this.sectionDraft[k]) !== JSON.stringify(this.sectionValues[k])) count++;
    }
    return count;
  }

  fieldType(field: SectionFieldMeta): string {
    if (field.sensitive) return 'sensitive';
    if (field.choices && field.choices.length > 0) return 'choice';
    const t = field.type.toLowerCase();
    if (t === 'boolean' || t === 'bool') return 'boolean';
    if (t === 'integer' || t === 'int') return 'number';
    if (t === 'float' || t === 'number') return 'number';
    if (t.includes('list') || t.includes('array')) return 'list';
    return 'string';
  }

  getDraftValue(key: string): unknown {
    return this.sectionDraft[key];
  }

  setDraftValue(key: string, value: unknown): void {
    this.sectionDraft = { ...this.sectionDraft, [key]: value };
  }

  setDraftBool(key: string, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.sectionDraft = { ...this.sectionDraft, [key]: checked };
  }

  setDraftNumber(key: string, event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.sectionDraft = { ...this.sectionDraft, [key]: val === '' ? null : Number(val) };
  }

  setDraftString(key: string, event: Event): void {
    const val = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
    this.sectionDraft = { ...this.sectionDraft, [key]: val };
  }

  getDiffSections(): string[] {
    if (!this.diffData?.overrides) return [];
    return Object.keys(this.diffData.overrides);
  }

  getDiffFields(sectionKey: string): Array<{ field: string; env: unknown; runtime: unknown }> {
    const section = this.diffData?.overrides?.[sectionKey];
    if (!section) return [];
    return Object.entries(section).map(([field, vals]) => ({
      field,
      env: vals.env_value,
      runtime: vals.runtime_value,
    }));
  }

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  isBoolean(v: unknown): boolean { return v === true || v === false; }
  isNumber(v: unknown): boolean { return typeof v === 'number'; }
  isArray(v: unknown): boolean { return Array.isArray(v); }

  private readonly providerDependentFields: Record<string, { providerField: string; showFor: string[] }> = {
    'multimodal_audio_api_key':      { providerField: 'multimodal_audio_provider', showFor: ['openai'] },
    'multimodal_audio_base_url':     { providerField: 'multimodal_audio_provider', showFor: ['openai'] },
    'multimodal_audio_model':        { providerField: 'multimodal_audio_provider', showFor: ['openai'] },
    'multimodal_image_gen_api_key':  { providerField: 'multimodal_image_gen_provider', showFor: ['openai', 'stabilityai'] },
    'multimodal_image_gen_model':    { providerField: 'multimodal_image_gen_provider', showFor: ['openai', 'stabilityai'] },
    'multimodal_tts_api_key':        { providerField: 'multimodal_tts_provider', showFor: ['openai'] },
    'multimodal_tts_base_url':       { providerField: 'multimodal_tts_provider', showFor: ['openai'] },
    'multimodal_tts_model':          { providerField: 'multimodal_tts_provider', showFor: ['openai'] },
    'vision_api_key':                { providerField: 'vision_provider', showFor: ['openai', 'gemini'] },
  };

  isFieldVisible(f: SectionFieldMeta): boolean {
    const dep = this.providerDependentFields[f.name];
    if (!dep) return true;
    const providerValue = String(this.sectionDraft[dep.providerField] ?? '').toLowerCase();
    return dep.showFor.includes(providerValue);
  }

  // ── Audio dependency helpers ─────────────────────────

  private static readonly PROVIDER_FIELDS = new Set([
    'multimodal_tts_provider',
    'multimodal_audio_provider',
  ]);

  private static readonly PROVIDER_SCOPE_MAP: Record<string, string> = {
    multimodal_tts_provider: 'tts',
    multimodal_audio_provider: 'transcription',
  };

  isProviderField(name: string): boolean {
    return SettingsPageComponent.PROVIDER_FIELDS.has(name);
  }

  onFieldChange(fieldName: string, event: Event): void {
    this.setDraftString(fieldName, event);
    const val = String(this.sectionDraft[fieldName] ?? '').toLowerCase();
    if (this.isProviderField(fieldName) && val === 'local') {
      const scope = SettingsPageComponent.PROVIDER_SCOPE_MAP[fieldName];
      this.checkAudioDeps(scope);
    } else if (this.isProviderField(fieldName)) {
      // Switching away from local — clear deps
      this.audioDeps = [];
      this.audioDepsMessage = '';
    }
  }

  private autoCheckAudioDeps(values: Record<string, unknown>): void {
    for (const field of SettingsPageComponent.PROVIDER_FIELDS) {
      const val = String(values[field] ?? '').toLowerCase();
      if (val === 'local') {
        const scope = SettingsPageComponent.PROVIDER_SCOPE_MAP[field];
        this.checkAudioDeps(scope);
        return;
      }
    }
    // No local provider — clear any stale deps
    this.audioDeps = [];
    this.audioDepsMessage = '';
  }

  checkAudioDeps(scope?: string): void {
    this.audioDepsLoading = true;
    this.audioDepsMessage = 'Checking dependencies...';
    this.cdr.markForCheck();
    this.configService.checkAudioDeps(scope).subscribe({
      next: (res) => {
        this.audioDeps = res.dependencies;
        this.audioDepsLoading = false;
        this.audioDepsMessage = '';
        this.cdr.markForCheck();
      },
      error: () => {
        this.audioDepsLoading = false;
        this.audioDepsMessage = 'Failed to check dependencies';
        this.cdr.markForCheck();
      },
    });
  }

  installDep(packageName: string): void {
    this.audioDepsInstalling = packageName;
    this.audioDepsMessage = `Installing ${packageName}...`;
    this.cdr.markForCheck();
    this.configService.installAudioDep(packageName).subscribe({
      next: (res) => {
        this.audioDepsInstalling = null;
        if (res.success) {
          this.audioDepsMessage = `${packageName} installed successfully`;
          // Re-check deps to refresh status
          const scope = this.audioDeps.find(d => d.name === packageName)?.purpose;
          this.checkAudioDeps(scope);
        } else {
          this.audioDepsMessage = `Install failed: ${res.message}`;
        }
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.audioDepsInstalling = null;
        this.audioDepsMessage = `Install error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }

  private flashMessage(target: 'section', msg: string, type: 'ok' | 'err'): void {
    this.sectionMessage = msg;
    this.sectionMessageType = type;
    this.cdr.markForCheck();
  }
}
