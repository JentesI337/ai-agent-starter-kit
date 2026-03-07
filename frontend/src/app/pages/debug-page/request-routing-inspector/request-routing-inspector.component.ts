import { Component, Input } from '@angular/core';
import { RequestEnvelope, RoutingDecision, RoutingMatch } from '../debug.types';

@Component({
  selector: 'app-request-routing-inspector',
  standalone: true,
  imports: [],
  templateUrl: './request-routing-inspector.component.html',
  styleUrl: './request-routing-inspector.component.scss',
})
export class RequestRoutingInspectorComponent {
  @Input() requestEnvelope: RequestEnvelope | null = null;
  @Input() routingDecision: RoutingDecision | null = null;

  envelopeOpen = false;
  routingOpen = true;

  get summary(): string {
    if (!this.routingDecision) return '';
    const parts: string[] = [
      this.routingDecision.effectiveAgentId,
      `via ${this.routingDecision.routingMethod}`,
    ];
    if (this.requestEnvelope?.modelOverride) {
      parts.push(this.requestEnvelope.modelOverride);
    }
    if (this.requestEnvelope?.contentLength) {
      parts.push(`${this.requestEnvelope.contentLength} chars`);
    }
    return parts.join(' · ');
  }

  get sortedMatches(): RoutingMatch[] {
    if (!this.routingDecision?.routingMatches.length) return [];
    return [...this.routingDecision.routingMatches]
      .sort((a, b) => b.score - a.score);
  }

  get maxScore(): number {
    return this.sortedMatches.length ? this.sortedMatches[0].score : 1;
  }

  getBarWidth(score: number): number {
    return this.maxScore > 0 ? (score / this.maxScore) * 100 : 0;
  }

  get envelopeEntries(): { label: string; value: string | null }[] {
    const e = this.requestEnvelope;
    if (!e) return [];
    return [
      { label: 'Type',                 value: e.type },
      { label: 'Request-ID',           value: e.requestId },
      { label: 'Session-ID',           value: e.sessionId },
      { label: 'Content Length',        value: e.contentLength ? `${e.contentLength} chars` : null },
      { label: 'Agent Override',        value: e.agentOverride },
      { label: 'Model',                value: e.modelOverride },
      { label: 'Preset',               value: e.preset },
      { label: 'Prompt Mode',          value: e.promptMode },
      { label: 'Queue Mode',           value: e.queueMode },
      { label: 'Reasoning Level',      value: e.reasoningLevel },
      { label: 'Reasoning Visibility', value: e.reasoningVisibility },
    ];
  }
}
