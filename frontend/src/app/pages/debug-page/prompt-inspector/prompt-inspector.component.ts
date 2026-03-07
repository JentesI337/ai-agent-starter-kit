import { Component, Input } from '@angular/core';
import { JsonPipe, DecimalPipe } from '@angular/common';
import { SyntaxHighlightPipe } from '../pipes/syntax-highlight.pipe';
import {
  InspectorTab,
  LlmCallRecord,
  PipelinePhase,
  ReflectionVerdict,
  ToolExecutionRecord,
} from '../debug.types';

@Component({
  selector: 'app-prompt-inspector',
  standalone: true,
  imports: [SyntaxHighlightPipe, JsonPipe, DecimalPipe],
  templateUrl: './prompt-inspector.component.html',
  styleUrl: './prompt-inspector.component.scss',
})
export class PromptInspectorComponent {
  @Input() selectedPhase: PipelinePhase | null = null;
  @Input() llmCalls: LlmCallRecord[] = [];
  @Input() toolExecutions: ToolExecutionRecord[] = [];
  @Input() reflectionVerdict: ReflectionVerdict | null = null;

  activeTab: InspectorTab = 'system_prompt';

  readonly tabs: { id: InspectorTab; label: string }[] = [
    { id: 'system_prompt', label: 'System Prompt' },
    { id: 'user_prompt',   label: 'User Prompt' },
    { id: 'llm_response',  label: 'LLM Response' },
    { id: 'parsed_output', label: 'Parsed Output' },
    { id: 'tool_details',  label: 'Tool Details' },
    { id: 'reflection',    label: 'Reflection' },
  ];

  /** Returns all LLM calls with their content for the currently active text tab. */
  get callsForTab(): { call: LlmCallRecord; content: string }[] {
    return this.llmCalls
      .map(c => ({ call: c, content: this.extractContent(c) }))
      .filter(e => !!e.content);
  }

  private extractContent(call: LlmCallRecord): string {
    switch (this.activeTab) {
      case 'system_prompt': return call.systemPrompt;
      case 'user_prompt':   return call.userPrompt;
      case 'llm_response':  return call.rawResponse;
      case 'parsed_output': return call.parsedOutput;
      default: return '';
    }
  }

  getPhaseLabel(phase: PipelinePhase): string {
    return phase.charAt(0).toUpperCase() + phase.slice(1);
  }

  getTabLabel(tabId: InspectorTab): string {
    return this.tabs.find(t => t.id === tabId)?.label ?? tabId;
  }

  hasData(tabId: InspectorTab): boolean {
    switch (tabId) {
      case 'tool_details': return this.toolExecutions.length > 0;
      case 'reflection':   return this.reflectionVerdict !== null;
      default:             return this.llmCalls.length > 0;
    }
  }

  async copyToClipboard(text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
  }
}
