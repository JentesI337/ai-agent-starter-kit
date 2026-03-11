import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  Input,
  OnChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';

export interface PlanProgressStep {
  index: number;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
}

@Component({
  selector: 'app-plan-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './plan-progress.component.html',
  styleUrls: ['./plan-progress.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlanProgressComponent implements OnChanges {
  @Input() steps: PlanProgressStep[] = [];

  isCollapsed = false;
  allDone = false;
  completedCount = 0;

  constructor(private cdr: ChangeDetectorRef) {}

  ngOnChanges(): void {
    this.completedCount = this.steps.filter(s => s.status === 'completed').length;
    this.allDone =
      this.steps.length > 0 &&
      this.steps.every(s => s.status === 'completed' || s.status === 'failed');

    if (this.allDone && !this.isCollapsed) {
      setTimeout(() => {
        this.isCollapsed = true;
        this.cdr.markForCheck();
      }, 2000);
    }
  }

  toggleCollapse(): void {
    this.isCollapsed = !this.isCollapsed;
  }

  trackStep(index: number): number {
    return index;
  }
}
