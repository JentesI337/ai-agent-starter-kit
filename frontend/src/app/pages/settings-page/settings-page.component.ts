import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable, forkJoin } from 'rxjs';

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

// ── ViewState pattern ──────────────────────────────

interface ViewState<T> {
  loading: boolean;
  error: string;
  data: T;
  saving: boolean;
  message: string;
  messageType: 'ok' | 'err';
}

function emptyView<T>(data: T): ViewState<T> {
  return { loading: false, error: '', data, saving: false, message: '', messageType: 'ok' };
}

// ── Typed data shapes ──────────────────────────────

interface ConfigViewData {
  sections: SectionMeta[];
  selectedKey: string;
  values: Record<string, unknown>;
  draft: Record<string, unknown>;
  audioDeps: AudioDep[];
  audioDepsLoading: boolean;
  audioDepsInstalling: string | null;
  audioDepsMessage: string;
}

interface AgentViewData {
  agents: AgentRuntimeConfig[];
  selectedId: string;
  draft: Record<string, unknown>;
}

interface ToolViewData {
  tools: ToolRuntimeConfig[];
  selectedName: string;
  draft: Record<string, unknown>;
}

interface ExecutionViewData {
  budgetDraft: Record<string, unknown>;
  loopDraft: Record<string, unknown>;
}

interface SecurityViewData {
  patterns: SecurityPattern[];
  newPatternValue: string;
  newPatternReason: string;
}

interface DiffViewData {
  overrides: ConfigDiffResponse['overrides'] | null;
}

interface HealthViewData {
  health: ConfigHealthResponse | null;
}

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

  // ── ViewState objects ──────────────────────────────
  configView = emptyView<ConfigViewData>({
    sections: [], selectedKey: '', values: {}, draft: {},
    audioDeps: [], audioDepsLoading: false, audioDepsInstalling: null, audioDepsMessage: '',
  });

  agentView = emptyView<AgentViewData>({ agents: [], selectedId: '', draft: {} });
  toolView = emptyView<ToolViewData>({ tools: [], selectedName: '', draft: {} });
  execView = emptyView<ExecutionViewData>({ budgetDraft: {}, loopDraft: {} });
  secView = emptyView<SecurityViewData>({ patterns: [], newPatternValue: '', newPatternReason: '' });
  diffView = emptyView<DiffViewData>({ overrides: null });
  healthView = emptyView<HealthViewData>({ health: null });

  // ── Loading (initial sections load only) ───────────
  initialLoading = true;

  readonly categories: SidebarCategory[] = [
    { id: 'core',       label: 'Core & Infra',     icon: '◈', sectionKeys: ['core', 'infra'] },
    { id: 'llm',        label: 'LLM & Models',     icon: '◆', sectionKeys: ['llm', 'model_health'] },
    { id: 'pipeline',   label: 'Pipeline',         icon: '⬡', sectionKeys: ['pipeline', 'runner', 'reflection'] },
    { id: 'memory',     label: 'Memory & Session', icon: '◉', sectionKeys: ['memory', 'session'] },
    { id: 'tools_cfg',  label: 'Tool Execution',   icon: '⬢', sectionKeys: ['tool_execution', 'tool_loop'] },
    { id: 'security',   label: 'Security',         icon: '⛊', sectionKeys: ['security'] },
    { id: 'agents_cfg', label: 'Agent Names',      icon: '◎', sectionKeys: ['agent_names'] },
    { id: 'extensions', label: 'Extensions',       icon: '◇', sectionKeys: ['browser', 'repl', 'multimodal', 'vision_web', 'skills'] },
    { id: 'subruns',    label: 'Subruns',          icon: '▣', sectionKeys: ['subrun'] },
  ];

  constructor(
    private readonly configService: ConfigService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadSections();
  }

  // ── Reusable helpers ─────────────────────────────

  private loadView<T>(view: ViewState<T>, obs: Observable<unknown>, onSuccess: (res: any) => void): void {
    view.loading = true;
    view.error = '';
    view.message = '';
    this.cdr.markForCheck();
    obs.subscribe({
      next: (res) => {
        view.loading = false;
        onSuccess(res);
        this.cdr.markForCheck();
      },
      error: (err) => {
        view.loading = false;
        view.error = `Failed to load: ${err?.error?.detail ?? err.message ?? 'Unknown error'}`;
        this.cdr.markForCheck();
      },
    });
  }

  private saveView<T>(view: ViewState<T>, obs: Observable<unknown>, onSuccess: (res: any) => void): void {
    view.saving = true;
    view.message = '';
    this.cdr.markForCheck();
    obs.subscribe({
      next: (res) => {
        view.saving = false;
        view.messageType = 'ok';
        onSuccess(res);
        this.cdr.markForCheck();
      },
      error: (err) => {
        view.saving = false;
        view.messageType = 'err';
        view.message = `Error: ${err?.error?.detail ?? err.message ?? 'Unknown error'}`;
        this.cdr.markForCheck();
      },
    });
  }

  // ── Data Loading ───────────────────────────────────

  private loadSections(): void {
    this.initialLoading = true;
    this.configService.getSections().subscribe({
      next: (res) => {
        this.configView.data.sections = res.sections ?? [];
        this.initialLoading = false;
        if (this.categories.length > 0) {
          this.expandedCategories.add(this.categories[0].id);
          const firstKey = this.categories[0].sectionKeys[0];
          if (this.configView.data.sections.some(s => s.key === firstKey)) {
            this.selectSection(firstKey);
          }
        }
        this.cdr.markForCheck();
      },
      error: () => {
        this.initialLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  selectSection(key: string): void {
    this.viewMode = 'config';
    this.configView.data.selectedKey = key;
    this.loadView(this.configView, this.configService.getSection(key), (res) => {
      this.configView.data.values = { ...(res.values ?? {}) };
      this.configView.data.draft = { ...(res.values ?? {}) };
      this.autoCheckAudioDeps(res.values ?? {});
    });
  }

  loadAgentConfigs(): void {
    this.viewMode = 'agents';
    this.loadView(this.agentView, this.configService.getAgentConfigs(), (res) => {
      this.agentView.data.agents = res.agents ?? [];
      if (this.agentView.data.agents.length > 0 && !this.agentView.data.selectedId) {
        this.selectAgent(this.agentView.data.agents[0].agent_id);
      }
    });
  }

  selectAgent(agentId: string): void {
    this.agentView.data.selectedId = agentId;
    this.loadView(this.agentView, this.configService.getAgentConfig(agentId), (res) => {
      this.agentView.data.draft = { ...(res.config ?? {}) };
    });
  }

  loadToolConfigs(): void {
    this.viewMode = 'tools';
    this.loadView(this.toolView, this.configService.getToolConfigs(), (res) => {
      this.toolView.data.tools = res.tools ?? [];
      if (this.toolView.data.tools.length > 0 && !this.toolView.data.selectedName) {
        this.selectTool(this.toolView.data.tools[0].tool_name);
      }
    });
  }

  selectTool(toolName: string): void {
    this.toolView.data.selectedName = toolName;
    this.loadView(this.toolView, this.configService.getToolConfig(toolName), (res) => {
      this.toolView.data.draft = { ...(res.config ?? {}) };
    });
  }

  loadExecutionConfig(): void {
    this.viewMode = 'execution';
    this.loadView(this.execView, this.configService.getExecutionConfig(), (res) => {
      this.execView.data.budgetDraft = { ...(res.budget ?? {}), ...(res.result_processing ?? {}) };
      this.execView.data.loopDraft = { ...(res.loop_detection ?? {}) };
    });
  }

  loadSecurityView(): void {
    this.viewMode = 'security';
    this.loadView(this.secView, this.configService.getSecurityPatterns(), (res) => {
      this.secView.data.patterns = res.patterns ?? [];
    });
  }

  loadDiff(): void {
    this.viewMode = 'diff';
    this.loadView(this.diffView, this.configService.getDiff(), (res) => {
      this.diffView.data.overrides = res.overrides ?? null;
    });
  }

  loadHealth(): void {
    this.viewMode = 'health';
    this.loadView(this.healthView, this.configService.getHealth(), (res) => {
      this.healthView.data.health = res;
    });
  }

  // ── Save / Reset ──────────────────────────────────

  saveSection(): void {
    if (!this.configView.data.selectedKey) return;
    const changes: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(this.configView.data.draft)) {
      if (JSON.stringify(v) !== JSON.stringify(this.configView.data.values[k])) {
        changes[k] = v;
      }
    }
    if (Object.keys(changes).length === 0) {
      this.configView.message = 'No changes to save';
      this.configView.messageType = 'ok';
      this.cdr.markForCheck();
      return;
    }
    this.saveView(this.configView, this.configService.updateSection(this.configView.data.selectedKey, changes), (res) => {
      const count = res.changes?.length ?? 0;
      if (res.validation_errors?.length) {
        this.configView.messageType = 'err';
        this.configView.message = `Saved ${count} field(s) with warnings: ${res.validation_errors.join(', ')}`;
      } else {
        this.configView.message = `Saved ${count} field(s)`;
      }
      this.selectSection(this.configView.data.selectedKey);
    });
  }

  resetSection(): void {
    if (!this.configView.data.selectedKey) return;
    this.saveView(this.configView, this.configService.resetSection(this.configView.data.selectedKey), (res) => {
      this.configView.message = `Reset ${res.reset_fields?.length ?? 0} field(s) to defaults`;
      this.selectSection(this.configView.data.selectedKey);
    });
  }

  saveAgentConfig(): void {
    if (!this.agentView.data.selectedId) return;
    const updates = { ...this.agentView.data.draft };
    delete updates['agent_id'];
    this.saveView(this.agentView, this.configService.updateAgentConfig(this.agentView.data.selectedId, updates), (res) => {
      this.agentView.message = `Saved ${res.changes?.length ?? 0} change(s)`;
    });
  }

  resetAgentConfig(): void {
    if (!this.agentView.data.selectedId) return;
    this.saveView(this.agentView, this.configService.resetAgentConfig(this.agentView.data.selectedId), () => {
      this.agentView.message = 'Reset to defaults';
      this.selectAgent(this.agentView.data.selectedId);
    });
  }

  saveToolConfig(): void {
    if (!this.toolView.data.selectedName) return;
    const updates = { ...this.toolView.data.draft };
    delete updates['tool_name'];
    this.saveView(this.toolView, this.configService.updateToolConfig(this.toolView.data.selectedName, updates), (res) => {
      this.toolView.message = `Saved ${res.changes?.length ?? 0} change(s)`;
    });
  }

  resetToolConfig(): void {
    if (!this.toolView.data.selectedName) return;
    this.saveView(this.toolView, this.configService.resetToolConfig(this.toolView.data.selectedName), () => {
      this.toolView.message = 'Reset to defaults';
      this.selectTool(this.toolView.data.selectedName);
    });
  }

  saveExecutionConfig(): void {
    this.saveView(this.execView, forkJoin([
      this.configService.updateExecutionConfig(this.execView.data.budgetDraft),
      this.configService.updateLoopDetectionConfig(this.execView.data.loopDraft),
    ]), () => {
      this.execView.message = 'Execution config saved';
    });
  }

  addSecurityPattern(): void {
    const p = this.secView.data.newPatternValue.trim();
    const r = this.secView.data.newPatternReason.trim();
    if (!p || !r) return;
    this.saveView(this.secView, this.configService.addSecurityPattern(p, r), () => {
      this.secView.data.newPatternValue = '';
      this.secView.data.newPatternReason = '';
      this.secView.message = 'Pattern added';
      this.loadSecurityView();
    });
  }

  // ── Helpers ────────────────────────────────────────

  getSectionMeta(key: string): SectionMeta | undefined {
    return this.configView.data.sections.find(s => s.key === key);
  }

  get selectedSectionMeta(): SectionMeta | undefined {
    return this.configView.data.sections.find(s => s.key === this.configView.data.selectedKey);
  }

  get filteredFields(): SectionFieldMeta[] {
    const meta = this.selectedSectionMeta;
    if (!meta?.fields) return [];
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
          (meta.fields ?? []).some(f => f.name.toLowerCase().includes(q));
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
    this.cdr.markForCheck();
  }

  isFieldModified(field: string): boolean {
    return JSON.stringify(this.configView.data.draft[field]) !== JSON.stringify(this.configView.data.values[field]);
  }

  get modifiedFieldCount(): number {
    let count = 0;
    for (const k of Object.keys(this.configView.data.draft)) {
      if (JSON.stringify(this.configView.data.draft[k]) !== JSON.stringify(this.configView.data.values[k])) count++;
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
    return this.configView.data.draft[key];
  }

  setDraftValue(key: string, value: unknown): void {
    this.configView.data.draft = { ...this.configView.data.draft, [key]: value };
  }

  setDraftBool(key: string, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.configView.data.draft = { ...this.configView.data.draft, [key]: checked };
  }

  setDraftNumber(key: string, event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.configView.data.draft = { ...this.configView.data.draft, [key]: val === '' ? null : Number(val) };
  }

  setDraftString(key: string, event: Event): void {
    const val = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
    this.configView.data.draft = { ...this.configView.data.draft, [key]: val };
  }

  getDiffSections(): string[] {
    if (!this.diffView.data.overrides) return [];
    return Object.keys(this.diffView.data.overrides);
  }

  getDiffFields(sectionKey: string): Array<{ field: string; env: unknown; runtime: unknown }> {
    const section = this.diffView.data.overrides?.[sectionKey];
    if (!section) return [];
    return Object.entries(section).map(([field, vals]) => ({
      field,
      env: vals.env_value,
      runtime: vals.runtime_value,
    }));
  }

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj ?? {});
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
    const providerValue = String(this.configView.data.draft[dep.providerField] ?? '').toLowerCase();
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
    const val = String(this.configView.data.draft[fieldName] ?? '').toLowerCase();
    if (this.isProviderField(fieldName) && val === 'local') {
      const scope = SettingsPageComponent.PROVIDER_SCOPE_MAP[fieldName];
      this.checkAudioDeps(scope);
    } else if (this.isProviderField(fieldName)) {
      this.configView.data.audioDeps = [];
      this.configView.data.audioDepsMessage = '';
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
    this.configView.data.audioDeps = [];
    this.configView.data.audioDepsMessage = '';
  }

  checkAudioDeps(scope?: string): void {
    this.configView.data.audioDepsLoading = true;
    this.configView.data.audioDepsMessage = 'Checking dependencies...';
    this.cdr.markForCheck();
    this.configService.checkAudioDeps(scope).subscribe({
      next: (res) => {
        this.configView.data.audioDeps = res.dependencies ?? [];
        this.configView.data.audioDepsLoading = false;
        this.configView.data.audioDepsMessage = '';
        this.cdr.markForCheck();
      },
      error: () => {
        this.configView.data.audioDepsLoading = false;
        this.configView.data.audioDepsMessage = 'Failed to check dependencies';
        this.cdr.markForCheck();
      },
    });
  }

  installDep(packageName: string): void {
    this.configView.data.audioDepsInstalling = packageName;
    this.configView.data.audioDepsMessage = `Installing ${packageName}...`;
    this.cdr.markForCheck();
    this.configService.installAudioDep(packageName).subscribe({
      next: (res) => {
        this.configView.data.audioDepsInstalling = null;
        if (res.success) {
          this.configView.data.audioDepsMessage = `${packageName} installed successfully`;
          const scope = this.configView.data.audioDeps.find(d => d.name === packageName)?.purpose;
          this.checkAudioDeps(scope);
        } else {
          this.configView.data.audioDepsMessage = `Install failed: ${res.message}`;
        }
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.configView.data.audioDepsInstalling = null;
        this.configView.data.audioDepsMessage = `Install error: ${err?.error?.detail ?? err.message}`;
        this.cdr.markForCheck();
      },
    });
  }
}
