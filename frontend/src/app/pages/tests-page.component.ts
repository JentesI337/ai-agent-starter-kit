import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { AgentsService, AgentTestResult, BackendPingResult } from '../services/agents.service';
import { OrchestratorRunResponse, OrchestratorService } from '../services/orchestrator.service';

@Component({
  selector: 'app-tests-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './tests-page.component.html',
  styleUrl: './tests-page.component.scss',
})
export class TestsPageComponent {
  pingLoading = false;
  pingError = '';
  pingResult: BackendPingResult | null = null;

  agentLoading = false;
  agentError = '';
  agentResult: AgentTestResult | null = null;

  orchestratorLoading = false;
  orchestratorError = '';
  orchestratorResult: OrchestratorRunResponse | null = null;

  constructor(
    private readonly agentsService: AgentsService,
    private readonly orchestratorService: OrchestratorService
  ) {}

  runPingTest(): void {
    this.pingLoading = true;
    this.pingError = '';
    this.pingResult = null;

    this.agentsService.testBackendPing().subscribe({
      next: (result) => {
        this.pingResult = result;
        this.pingLoading = false;
      },
      error: (error) => {
        this.pingLoading = false;
        this.pingError = (error as Error)?.message || 'Ping test failed.';
      },
    });
  }

  runAgentTest(): void {
    this.agentLoading = true;
    this.agentError = '';
    this.agentResult = null;

    this.agentsService.testAgentCall('hi').subscribe({
      next: (result) => {
        this.agentResult = result;
        this.agentLoading = false;
      },
      error: (error) => {
        this.agentLoading = false;
        this.agentError = (error as Error)?.message || 'Agent test failed.';
      },
    });
  }

  runOrchestratorTest(): void {
    this.orchestratorLoading = true;
    this.orchestratorError = '';
    this.orchestratorResult = null;

    this.orchestratorService.run('Explain what 2+2 equals.').subscribe({
      next: (result) => {
        this.orchestratorResult = result;
        this.orchestratorLoading = false;
      },
      error: (error) => {
        this.orchestratorLoading = false;
        this.orchestratorError = (error as Error)?.message || 'Orchestrator test failed.';
      },
    });
  }
}
