import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';

import { AgentDescriptor, AgentsService } from '../services/agents.service';
import {
  ModelCapabilityProfile,
  OrchestratorService,
} from '../services/orchestrator.service';

interface OrchestratorAgent {
  role: string;
  description: string;
  constraints: {
    max_context_tokens: number;
    temperature: number;
    max_reflection_passes: number;
    max_output_tokens: number;
    timeout_seconds: number;
  };
}

@Component({
  selector: 'app-agents-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agents-page.component.html',
  styleUrl: './agents-page.component.scss',
})
export class AgentsPageComponent implements OnInit {
  agents: AgentDescriptor[] = [];
  loading = true;
  error = '';

  orchestratorAgents: OrchestratorAgent[] = [
    {
      role: 'planner',
      description: 'Decomposes user requests into structured, executable plan steps.',
      constraints: {
        max_context_tokens: 4000,
        temperature: 0.3,
        max_reflection_passes: 0,
        max_output_tokens: 2048,
        timeout_seconds: 60,
      },
    },
    {
      role: 'coder',
      description: 'Executes a single plan step by generating file changes and/or shell commands.',
      constraints: {
        max_context_tokens: 6000,
        temperature: 0.2,
        max_reflection_passes: 0,
        max_output_tokens: 4096,
        timeout_seconds: 90,
      },
    },
    {
      role: 'reviewer',
      description: 'Reviews coder output against the original plan. Provides confidence score and issues.',
      constraints: {
        max_context_tokens: 6000,
        temperature: 0.2,
        max_reflection_passes: 0,
        max_output_tokens: 2048,
        timeout_seconds: 60,
      },
    },
  ];

  models: ModelCapabilityProfile[] = [];
  modelsLoading = true;

  constructor(
    private readonly agentsService: AgentsService,
    private readonly orchestratorService: OrchestratorService
  ) {}

  ngOnInit(): void {
    this.agentsService.getAgents().subscribe({
      next: (result) => {
        this.agents = result;
        this.loading = false;
      },
      error: () => {
        this.error = 'Could not load agents from backend.';
        this.loading = false;
      },
    });

    this.orchestratorService.getModels().subscribe({
      next: (res) => {
        this.models = res.models;
        this.modelsLoading = false;
      },
      error: () => {
        this.modelsLoading = false;
      },
    });
  }

  tierClass(tier: string): string {
    return `tier-${tier}`;
  }
}
