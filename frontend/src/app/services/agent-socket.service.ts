import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface AgentSocketEvent {
  type: 'status' | 'agent_step' | 'token' | 'final' | 'error' | string;
  agent?: string;
  message?: string;
  step?: string;
  token?: string;
  session_id?: string;
  request_id?: string;
  stage?: string;
  ts?: string;
  details?: Record<string, unknown>;
  runtime?: 'local' | 'api';
  model?: string;
  base_url?: string;
  auth_url?: string;
  attempt?: number;
  level?: string;
}

@Injectable({ providedIn: 'root' })
export class AgentSocketService {
  private socket?: WebSocket;
  private socketUrl = '';
  private reconnectTimer: number | null = null;
  private manualDisconnect = false;
  private readonly eventsSubject = new BehaviorSubject<AgentSocketEvent | null>(null);
  private readonly connectedSubject = new BehaviorSubject<boolean>(false);

  events$ = this.eventsSubject.asObservable();
  connected$ = this.connectedSubject.asObservable();

  connect(url: string): void {
    this.socketUrl = url;
    this.manualDisconnect = false;

    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.socket = new WebSocket(url);

    this.socket.onopen = () => this.connectedSubject.next(true);
    this.socket.onclose = () => {
      this.connectedSubject.next(false);
      if (!this.manualDisconnect) {
        this.reconnectTimer = window.setTimeout(() => {
          this.connect(this.socketUrl);
        }, 1500);
      }
    };
    this.socket.onerror = () => this.connectedSubject.next(false);
    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as AgentSocketEvent;
        this.eventsSubject.next(data);
      } catch {
        this.eventsSubject.next({ type: 'status', message: 'Invalid message from socket.' });
      }
    };
  }

  sendUserMessage(content: string, options?: { agentId?: string; model?: string; sessionId?: string }): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'user_message',
        content,
        agent_id: options?.agentId,
        model: options?.model,
        session_id: options?.sessionId,
      })
    );
  }

  sendRuntimeSwitchRequest(runtimeTarget: 'local' | 'api', sessionId?: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'runtime_switch_request',
        runtime_target: runtimeTarget,
        session_id: sessionId,
      })
    );
  }

  sendRuntimeAuthComplete(options?: { sessionId?: string; apiKey?: string }): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'runtime_auth_complete',
        session_id: options?.sessionId,
        api_key: options?.apiKey,
      })
    );
  }

  disconnect(): void {
    this.manualDisconnect = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
  }
}
