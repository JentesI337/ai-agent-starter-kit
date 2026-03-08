import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { MonitoringService } from '../../../services/monitoring.service';

@Component({
  selector: 'app-monitoring-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './monitoring-panel.component.html',
  styleUrl: './monitoring-panel.component.scss',
})
export class MonitoringPanelComponent {
  constructor(public readonly monitoring: MonitoringService) {}
}
