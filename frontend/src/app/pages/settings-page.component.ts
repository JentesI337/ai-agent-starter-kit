import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';

import { AgentsService, RuntimeStatus } from '../services/agents.service';

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

  constructor(private readonly agentsService: AgentsService) {}

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
  }
}
