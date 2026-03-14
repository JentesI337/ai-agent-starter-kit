import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';

import {
  RecipeCheckpoint,
  RecipeConstraints,
  RecipeDef,
  RecipeRunSummary,
  RecipeService,
  StrictStep,
} from '../../services/recipe.service';
import {
  RecipeExecutionEvent,
  RecipeExecutionService,
} from '../../services/recipe-execution.service';

@Component({
  selector: 'app-recipes-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './recipes-page.component.html',
  styleUrls: ['./recipes-page.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecipesPageComponent implements OnInit, OnDestroy {
  // ── View state ──────────────────────────────────
  view: 'list' | 'editor' | 'execution' = 'list';
  loading = false;
  saving = false;
  message = '';
  messageType: 'ok' | 'err' = 'ok';
  searchQuery = '';

  // ── List ────────────────────────────────────────
  recipes: RecipeDef[] = [];

  // ── Editor ──────────────────────────────────────
  editId: string | null = null;
  recipeName = '';
  recipeDescription = '';
  recipeGoal = '';
  recipeMode: 'adaptive' | 'strict' = 'adaptive';
  recipeAgentId: string | null = null;

  // Constraints
  maxDuration: number | null = null;
  maxToolCalls: number | null = null;
  maxLlmTokens: number | null = null;
  toolsAllowed = '';
  toolsDenied = '';
  humanApprovalTools = '';

  // Checkpoints (adaptive)
  checkpoints: RecipeCheckpoint[] = [];

  // Steps (strict)
  strictSteps: StrictStep[] = [];

  // Triggers
  triggers: Record<string, unknown>[] = [{ type: 'manual' }];

  // Template placeholder (avoids Angular interpolation)
  toolParamsPlaceholder = '{"query": "{{input.message}}"}';


  // Runs
  editorTab: 'definition' | 'runs' = 'definition';
  runHistory: RecipeRunSummary[] = [];
  runsLoading = false;

  // Execution state
  executionRunId: string | null = null;
  executionRecipeName = '';
  executionEvents: RecipeExecutionEvent[] = [];
  executionCheckpoints: Array<{
    id: string;
    label: string;
    required: boolean;
    status: 'pending' | 'passed' | 'failed';
    explanation?: string;
  }> = [];
  executionSteps: Array<{
    id: string;
    label: string;
    tool?: string | null;
    status: 'pending' | 'running' | 'success' | 'failed';
    output_preview?: string;
    error?: string;
    duration_ms?: number;
  }> = [];
  executionMode: 'adaptive' | 'strict' = 'adaptive';
  executionStatus: 'idle' | 'running' | 'completed' | 'failed' | 'paused' = 'idle';
  executionPauseReason = '';
  executionBudget = { tokens_used: 0, tool_calls_used: 0, duration_seconds: 0 };
  executing = false;

  private subs: Subscription[] = [];

  constructor(
    private readonly recipeService: RecipeService,
    private readonly recipeExecution: RecipeExecutionService,
    private readonly cdr: ChangeDetectorRef,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loadRecipes();
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
    this.recipeExecution.disconnect();
  }

  // ── List operations ─────────────────────────────

  loadRecipes(): void {
    this.loading = true;
    this.cdr.markForCheck();
    const sub = this.recipeService.list().subscribe({
      next: res => {
        this.recipes = res.items ?? [];
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  get filteredRecipes(): RecipeDef[] {
    if (!this.searchQuery.trim()) return this.recipes;
    const q = this.searchQuery.toLowerCase();
    return this.recipes.filter(
      r => r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    );
  }

  // ── Editor operations ───────────────────────────

  openNew(): void {
    this.editId = null;
    this.recipeName = '';
    this.recipeDescription = '';
    this.recipeGoal = '';
    this.recipeMode = 'adaptive';
    this.recipeAgentId = null;
    this.maxDuration = null;
    this.maxToolCalls = null;
    this.maxLlmTokens = null;
    this.toolsAllowed = '';
    this.toolsDenied = '';
    this.humanApprovalTools = '';
    this.checkpoints = [];
    this.strictSteps = [];
    this.triggers = [{ type: 'manual' }];
    this.editorTab = 'definition';
    this.view = 'editor';
    this.cdr.markForCheck();
  }

  openEdit(recipe: RecipeDef): void {
    this.editId = recipe.id;
    this.recipeName = recipe.name;
    this.recipeDescription = recipe.description;
    this.recipeGoal = recipe.goal;
    this.recipeMode = recipe.mode;
    this.recipeAgentId = recipe.agent_id ?? null;
    this.maxDuration = recipe.constraints.max_duration_seconds ?? null;
    this.maxToolCalls = recipe.constraints.max_tool_calls ?? null;
    this.maxLlmTokens = recipe.constraints.max_llm_tokens ?? null;
    this.toolsAllowed = (recipe.constraints.tools_allowed ?? []).join(', ');
    this.toolsDenied = (recipe.constraints.tools_denied ?? []).join(', ');
    this.humanApprovalTools = (recipe.constraints.require_human_approval_before ?? []).join(', ');
    this.checkpoints = [...(recipe.checkpoints ?? [])];
    this.strictSteps = [...(recipe.strict_steps ?? [])];
    this.triggers = [...(recipe.triggers ?? [{ type: 'manual' }])];
    this.editorTab = 'definition';
    this.view = 'editor';
    this.cdr.markForCheck();
  }

  backToList(): void {
    this.view = 'list';
    this.message = '';
    this.loadRecipes();
  }

  save(): void {
    if (!this.recipeName.trim()) {
      this.showMessage('Recipe name is required', 'err');
      return;
    }

    this.saving = true;
    this.cdr.markForCheck();

    const constraints: Partial<RecipeConstraints> = {
      max_duration_seconds: this.maxDuration,
      max_tool_calls: this.maxToolCalls,
      max_llm_tokens: this.maxLlmTokens,
      tools_allowed: this.parseCommaSeparated(this.toolsAllowed),
      tools_denied: this.parseCommaSeparated(this.toolsDenied),
      require_human_approval_before: this.parseCommaSeparated(this.humanApprovalTools),
    };

    const payload: any = {
      name: this.recipeName,
      description: this.recipeDescription,
      goal: this.recipeGoal,
      mode: this.recipeMode,
      constraints,
      checkpoints: this.recipeMode === 'adaptive' ? this.checkpoints : [],
      strict_steps: this.recipeMode === 'strict' ? this.strictSteps : null,
      agent_id: this.recipeAgentId,
      triggers: this.triggers,
    };

    if (this.editId) {
      payload.id = this.editId;
      const sub = this.recipeService.update(payload).subscribe({
        next: () => {
          this.saving = false;
          this.showMessage('Recipe updated', 'ok');
          this.cdr.markForCheck();
        },
        error: err => {
          this.saving = false;
          this.showMessage(err.error?.detail ?? 'Update failed', 'err');
          this.cdr.markForCheck();
        },
      });
      this.subs.push(sub);
    } else {
      const sub = this.recipeService.create(payload).subscribe({
        next: res => {
          this.saving = false;
          this.editId = res.recipe?.id ?? null;
          this.showMessage('Recipe created', 'ok');
          this.cdr.markForCheck();
        },
        error: err => {
          this.saving = false;
          this.showMessage(err.error?.detail ?? 'Create failed', 'err');
          this.cdr.markForCheck();
        },
      });
      this.subs.push(sub);
    }
  }

  deleteRecipe(recipe: RecipeDef, event: Event): void {
    event.stopPropagation();
    const sub = this.recipeService.delete(recipe.id).subscribe({
      next: () => {
        this.recipes = this.recipes.filter(r => r.id !== recipe.id);
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  // ── Checkpoint management ───────────────────────

  addCheckpoint(): void {
    const order = this.checkpoints.length;
    this.checkpoints.push({
      id: `cp-${order + 1}`,
      label: '',
      verification: '',
      verification_mode: 'assert',
      required: true,
      order,
    });
    this.cdr.markForCheck();
  }

  removeCheckpoint(index: number): void {
    this.checkpoints.splice(index, 1);
    this.checkpoints.forEach((cp, i) => cp.order = i);
    this.cdr.markForCheck();
  }

  moveCheckpoint(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.checkpoints.length) return;
    const tmp = this.checkpoints[index];
    this.checkpoints[index] = this.checkpoints[target];
    this.checkpoints[target] = tmp;
    this.checkpoints.forEach((cp, i) => cp.order = i);
    this.cdr.markForCheck();
  }

  // ── Strict step management ──────────────────────

  addStrictStep(): void {
    const idx = this.strictSteps.length;
    this.strictSteps.push({
      id: `step-${idx + 1}`,
      label: `Step ${idx + 1}`,
      instruction: '',
      tool: null,
      tool_params: null,
      timeout_seconds: null,
      retry_count: 0,
    });
    this.cdr.markForCheck();
  }

  removeStrictStep(index: number): void {
    this.strictSteps.splice(index, 1);
    this.cdr.markForCheck();
  }

  moveStrictStep(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.strictSteps.length) return;
    const tmp = this.strictSteps[index];
    this.strictSteps[index] = this.strictSteps[target];
    this.strictSteps[target] = tmp;
    this.cdr.markForCheck();
  }

  // ── Run history ─────────────────────────────────

  switchTab(tab: 'definition' | 'runs'): void {
    this.editorTab = tab;
    if (tab === 'runs' && this.editId) {
      this.loadRunHistory();
    }
    this.cdr.markForCheck();
  }

  loadRunHistory(): void {
    if (!this.editId) return;
    this.runsLoading = true;
    this.cdr.markForCheck();
    const sub = this.recipeService.listRuns(this.editId).subscribe({
      next: res => {
        this.runHistory = res.items ?? [];
        this.runsLoading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.runsLoading = false;
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  // ── Triggers ────────────────────────────────────

  addTrigger(): void {
    this.triggers.push({ type: 'manual' });
    this.cdr.markForCheck();
  }

  removeTrigger(index: number): void {
    this.triggers.splice(index, 1);
    this.cdr.markForCheck();
  }

  // ── Execution ──────────────────────────────────

  executeRecipe(): void {
    if (!this.editId || this.executing) return;

    this.executing = true;
    this.executionRecipeName = this.recipeName;
    this.executionEvents = [];
    this.executionMode = this.recipeMode;
    this.executionCheckpoints = this.checkpoints.map(cp => ({
      id: cp.id,
      label: cp.label,
      required: cp.required,
      status: 'pending' as const,
    }));
    this.executionSteps = this.recipeMode === 'strict'
      ? this.strictSteps.map(s => ({
          id: s.id,
          label: s.label,
          tool: s.tool,
          status: 'pending' as const,
        }))
      : [];
    this.executionStatus = 'running';
    this.executionBudget = { tokens_used: 0, tool_calls_used: 0, duration_seconds: 0 };
    this.view = 'execution';
    this.cdr.markForCheck();

    const sub = this.recipeExecution.execute(this.editId).subscribe({
      next: res => {
        this.executionRunId = res.run_id;
        this.connectToStream(res.run_id);
        this.cdr.markForCheck();
      },
      error: err => {
        this.executing = false;
        this.executionStatus = 'failed';
        this.executionEvents.push({
          type: 'recipe_failed',
          error: err.error?.detail ?? 'Failed to start execution',
        });
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  private connectToStream(runId: string): void {
    const sub = this.recipeExecution.streamExecution(runId).subscribe({
      next: event => {
        this.executionEvents.push(event);

        if (event.type === 'recipe_started') {
          if (event.checkpoints) {
            this.executionCheckpoints = event.checkpoints.map(cp => ({
              id: cp.id,
              label: cp.label,
              required: cp.required,
              status: 'pending' as const,
            }));
          }
          if (event.steps) {
            this.executionMode = 'strict';
            this.executionSteps = event.steps.map(s => ({
              id: s.id,
              label: s.label,
              tool: s.tool,
              status: 'pending' as const,
            }));
          }
        }

        if (event.type === 'recipe_checkpoint_passed' || event.type === 'recipe_checkpoint_failed') {
          const cpIdx = this.executionCheckpoints.findIndex(c => c.id === event.checkpoint_id);
          if (cpIdx >= 0) {
            this.executionCheckpoints[cpIdx] = {
              ...this.executionCheckpoints[cpIdx],
              status: event.passed ? 'passed' : 'failed',
              explanation: event.explanation,
            };
          }
        }

        if (event.type === 'recipe_step_started') {
          const idx = this.executionSteps.findIndex(s => s.id === event.step_id);
          if (idx >= 0) {
            this.executionSteps[idx] = { ...this.executionSteps[idx], status: 'running' };
          }
        }

        if (event.type === 'recipe_step_completed') {
          const idx = this.executionSteps.findIndex(s => s.id === event.step_id);
          if (idx >= 0) {
            this.executionSteps[idx] = {
              ...this.executionSteps[idx],
              status: 'success',
              output_preview: event.output_preview,
              duration_ms: event.duration_ms,
            };
          }
        }

        if (event.type === 'recipe_step_failed') {
          const idx = this.executionSteps.findIndex(s => s.id === event.step_id);
          if (idx >= 0) {
            this.executionSteps[idx] = {
              ...this.executionSteps[idx],
              status: 'failed',
              error: event.error,
              duration_ms: event.duration_ms,
            };
          }
        }

        if (event.type === 'recipe_paused') {
          this.executionStatus = 'paused';
          this.executionPauseReason = (event.pause_reason as string) || 'unknown';
          this.executing = false;
        }

        if (event.type === 'recipe_resumed') {
          this.executionStatus = 'running';
          this.executionPauseReason = '';
          this.executing = true;
        }

        if (event.type === 'recipe_completed') {
          this.executionStatus = 'completed';
          this.executing = false;
          if (event.budget_used) {
            this.executionBudget = event.budget_used;
          }
        }

        if (event.type === 'recipe_failed') {
          this.executionStatus = 'failed';
          this.executing = false;
        }

        this.cdr.markForCheck();
      },
      complete: () => {
        this.executing = false;
        if (this.executionStatus === 'running') {
          this.executionStatus = 'completed';
        }
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  backFromExecution(): void {
    this.recipeExecution.disconnect();
    this.view = 'editor';
    this.executionStatus = 'idle';
    this.cdr.markForCheck();
  }

  // ── Helpers ─────────────────────────────────────

  trackById(_: number, item: { id: string }): string {
    return item.id;
  }

  trackByIndex(index: number): number {
    return index;
  }

  stringifyToolParams(step: StrictStep): string {
    if (!step.tool_params) return '';
    try {
      return JSON.stringify(step.tool_params, null, 2);
    } catch {
      return '';
    }
  }

  parseToolParams(step: StrictStep, raw: string): void {
    if (!raw.trim()) {
      step.tool_params = null;
      return;
    }
    try {
      step.tool_params = JSON.parse(raw);
    } catch {
      // keep the previous value on parse error
    }
  }

  resumeRun(): void {
    if (!this.executionRunId) return;
    const sub = this.recipeExecution.resumeRun(this.executionRunId).subscribe({
      next: () => {
        this.executionStatus = 'running';
        this.executionPauseReason = '';
        this.executing = true;
        this.cdr.markForCheck();
      },
      error: err => {
        this.showMessage(err.error?.detail ?? 'Resume failed', 'err');
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  resumeRunFromHistory(run: RecipeRunSummary): void {
    const sub = this.recipeExecution.resumeRun(run.run_id).subscribe({
      next: () => {
        this.showMessage('Run resumed', 'ok');
        this.loadRunHistory();
        this.cdr.markForCheck();
      },
      error: err => {
        this.showMessage(err.error?.detail ?? 'Resume failed', 'err');
        this.cdr.markForCheck();
      },
    });
    this.subs.push(sub);
  }

  describeCron(expr: string): string {
    if (!expr) return '';
    const patterns: Record<string, string> = {
      '* * * * *': 'Every minute',
      '*/5 * * * *': 'Every 5 minutes',
      '*/15 * * * *': 'Every 15 minutes',
      '*/30 * * * *': 'Every 30 minutes',
      '0 * * * *': 'Every hour',
      '0 */2 * * *': 'Every 2 hours',
      '0 */6 * * *': 'Every 6 hours',
      '0 */12 * * *': 'Every 12 hours',
      '0 0 * * *': 'Daily at midnight',
      '0 9 * * *': 'Daily at 9:00 AM',
      '0 9 * * 1-5': 'Weekdays at 9:00 AM',
      '0 0 * * 0': 'Weekly on Sunday',
      '0 0 * * 1': 'Weekly on Monday',
      '0 0 1 * *': 'Monthly on the 1st',
    };
    if (patterns[expr]) return patterns[expr];
    // Basic regex-based description
    const parts = expr.split(/\s+/);
    if (parts.length !== 5) return expr;
    const [min, hour, dom, mon, dow] = parts;
    const pieces: string[] = [];
    if (min !== '*' && hour !== '*') pieces.push(`At ${hour}:${min.padStart(2, '0')}`);
    else if (min.startsWith('*/')) pieces.push(`Every ${min.slice(2)} minutes`);
    else if (hour.startsWith('*/')) pieces.push(`Every ${hour.slice(2)} hours`);
    if (dow === '1-5') pieces.push('on weekdays');
    if (dom !== '*') pieces.push(`on day ${dom}`);
    return pieces.join(' ') || expr;
  }

  getNextRun(trigger: Record<string, unknown>): string {
    const next = trigger['next_run_at'] as string | undefined;
    if (!next) return 'Not scheduled';
    try {
      return new Date(next).toLocaleString();
    } catch {
      return next;
    }
  }

  private parseCommaSeparated(value: string): string[] {
    if (!value.trim()) return [];
    return value.split(',').map(s => s.trim()).filter(Boolean);
  }

  private showMessage(msg: string, type: 'ok' | 'err'): void {
    this.message = msg;
    this.messageType = type;
    setTimeout(() => {
      this.message = '';
      this.cdr.markForCheck();
    }, 3000);
  }
}
