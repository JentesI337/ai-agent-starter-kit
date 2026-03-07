import { ChangeDetectorRef, Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';

import { AgentSocketService } from '../../../services/agent-socket.service';
import {
  AgentStateService,
  GuardrailCheck,
  McpToolsInfo,
  RequestEnvelope,
  RoutingDecision,
  ToolchainInfo,
  ToolPolicyInfo,
} from '../../../services/agent-state.service';
import { GuardrailMonitorComponent } from '../guardrail-monitor/guardrail-monitor.component';
import { RequestRoutingInspectorComponent } from '../request-routing-inspector/request-routing-inspector.component';

@Component({
  selector: 'app-debug-dashboard',
  standalone: true,
  imports: [RouterLink, RequestRoutingInspectorComponent, GuardrailMonitorComponent],
  templateUrl: './debug-dashboard.component.html',
  styleUrl: './debug-dashboard.component.scss',
})
export class DebugDashboardComponent implements OnInit, OnDestroy {
  guardrailChecks: GuardrailCheck[] = [];
  toolPolicy: ToolPolicyInfo | null = null;
  toolchainInfo: ToolchainInfo | null = null;
  mcpToolsInfo: McpToolsInfo | null = null;
  requestEnvelope: RequestEnvelope | null = null;
  routingDecision: RoutingDecision | null = null;

  private subs = new Subscription();
  private isConnected = false;

  constructor(
    private readonly socket: AgentSocketService,
    private readonly agentState: AgentStateService,
    private readonly cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.agentState.init();

    this.subs.add(
      this.agentState.debug$.subscribe(snap => {
        this.guardrailChecks = snap.guardrailChecks;
        this.toolPolicy = snap.toolPolicy;
        this.toolchainInfo = snap.toolchainInfo;
        this.mcpToolsInfo = snap.mcpToolsInfo;
        this.requestEnvelope = snap.requestEnvelope;
        this.routingDecision = snap.routingDecision;
        this.cdr.detectChanges();
      })
    );

    this.subs.add(
      this.agentState.connected$.subscribe(c => this.isConnected = c)
    );

    if (!this.isConnected) {
      this.socket.connect('ws://localhost:8000/ws/agent');
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }
}
