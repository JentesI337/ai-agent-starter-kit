import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AgentStateService } from './services/agent-state.service';
import { AgentSocketService } from './services/agent-socket.service';

@Component({
  selector: 'app-root',
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  constructor(
    readonly agentState: AgentStateService,
    private readonly socket: AgentSocketService,
  ) {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.socket.connect(`${wsProto}//${window.location.host}/ws/agent`);
    this.agentState.init();
  }
}
