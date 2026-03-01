import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';

import { AgentsService, RuntimeStatus } from '../services/agents.service';
import {
  GraphSummary,
  OrchestratorService,
  OrchestratorStateResponse,
} from '../services/orchestrator.service';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.scss',
})
export class SettingsPageComponent implements OnInit {
  status: RuntimeStatus | null = null;
  loading = true;
  loadError = '';

  orchestratorState: OrchestratorStateResponse | null = null;
  orchestratorLoading = true;

  constructor(
    private readonly agentsService: AgentsService,
    private readonly orchestratorService: OrchestratorService
  ) {}

  ngOnInit(): void {
    this.agentsService.getRuntimeStatus().subscribe({
      next: (status) => {
        this.status = status;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.loadError = (error as Error)?.message || 'Failed to load runtime settings.';
      },
    });

    this.orchestratorService.getState().subscribe({
      next: (state) => {
        this.orchestratorState = state;
        this.orchestratorLoading = false;
      },
      error: () => {
        this.orchestratorLoading = false;
      },
    });
  }

  refreshOrchestratorState(): void {
    this.orchestratorLoading = true;
    this.orchestratorService.getState().subscribe({
      next: (state) => {
        this.orchestratorState = state;
        this.orchestratorLoading = false;
      },
      error: () => {
        this.orchestratorLoading = false;
      },
    });
  }

  statusEntries(obj: Record<string, number>): { key: string; value: number }[] {
    return Object.entries(obj).map(([key, value]) => ({ key, value }));
  }
}
