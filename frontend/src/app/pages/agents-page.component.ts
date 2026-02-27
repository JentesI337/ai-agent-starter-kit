import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';

import { AgentDescriptor, AgentsService } from '../services/agents.service';

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

  constructor(private readonly agentsService: AgentsService) {}

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
  }
}
