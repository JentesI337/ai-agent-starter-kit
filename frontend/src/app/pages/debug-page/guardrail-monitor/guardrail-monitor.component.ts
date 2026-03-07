import { Component, Input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { GuardrailCheck, McpToolsInfo, ToolchainInfo, ToolPolicyInfo } from '../debug.types';

@Component({
  selector: 'app-guardrail-monitor',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './guardrail-monitor.component.html',
  styleUrl: './guardrail-monitor.component.scss',
})
export class GuardrailMonitorComponent {
  @Input() guardrailChecks: GuardrailCheck[] = [];
  @Input() toolPolicy: ToolPolicyInfo | null = null;
  @Input() toolchainInfo: ToolchainInfo | null = null;
  @Input() mcpToolsInfo: McpToolsInfo | null = null;

  guardrailsOpen = true;
  initOpen = true;

  get passedCount(): number {
    return this.guardrailChecks.filter(c => c.passed).length;
  }

  get totalCount(): number {
    return this.guardrailChecks.length;
  }

  get allPassed(): boolean {
    return this.totalCount > 0 && this.passedCount === this.totalCount;
  }

  get summaryBadge(): string {
    if (this.totalCount === 0) return '';
    return `${this.passedCount}/${this.totalCount}`;
  }

  getProgressPercent(check: GuardrailCheck): number | null {
    if (typeof check.actualValue !== 'number' || typeof check.limit !== 'number') return null;
    if (check.limit <= 0) return null;
    return Math.min((check.actualValue / check.limit) * 100, 100);
  }

  getDisplayValue(check: GuardrailCheck): string {
    if (check.name === 'session_id_charset') {
      return `${check.limit} ${check.passed ? '✓' : '✕'}`;
    }
    if (typeof check.actualValue === 'number' && typeof check.limit === 'number') {
      return `${check.actualValue} / ${check.limit}`;
    }
    if (typeof check.actualValue === 'number') {
      return `${check.actualValue} chars`;
    }
    return String(check.actualValue);
  }

  getCheckLabel(check: GuardrailCheck): string {
    const labels: Record<string, string> = {
      'message_not_empty': 'Message not empty',
      'message_length': 'Message length',
      'session_id_length': 'Session-ID length',
      'session_id_charset': 'Session-ID charset',
      'model_name_length': 'Model name length',
    };
    return labels[check.name] ?? check.name;
  }
}
