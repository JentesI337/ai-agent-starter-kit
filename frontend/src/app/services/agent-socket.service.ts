import { Injectable, NgZone } from '@angular/core';
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

  constructor(private readonly ngZone: NgZone) {}

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

    const ws = new WebSocket(url);
    this.socket = ws;

    ws.onopen = () => {
      if (this.socket !== ws) {
        return;
      }
      this.ngZone.run(() => {
        this.connectedSubject.next(true);
        this.eventsSubject.next({ type: 'socket_open', message: `Socket connected: ${url}` });
      });
    };
    ws.onclose = () => {
      if (this.socket !== ws) {
        return;
      }
      this.ngZone.run(() => {
        this.connectedSubject.next(false);
        this.eventsSubject.next({ type: 'socket_close', message: 'Socket closed.' });
        if (!this.manualDisconnect) {
          this.reconnectTimer = window.setTimeout(() => {
            this.connect(this.socketUrl);
          }, 1500);
        }
      });
    };
    ws.onerror = () => {
      if (this.socket !== ws) {
        return;
      }
      this.ngZone.run(() => {
        this.connectedSubject.next(false);
        this.eventsSubject.next({ type: 'socket_error', message: 'Socket error occurred.' });
      });
    };
    ws.onmessage = (event) => {
      if (this.socket !== ws) {
        return;
      }
      this.ngZone.run(() => {
        const rawText = typeof event.data === 'string' ? event.data : '[non-string]';
        this.eventsSubject.next({
          type: 'socket_raw',
          message: rawText.length > 240 ? `${rawText.slice(0, 240)}…` : rawText,
        });
        try {
          const data = JSON.parse(event.data) as AgentSocketEvent;
          this.eventsSubject.next(data);
        } catch {
          const preview = typeof event.data === 'string' ? event.data.slice(0, 200) : '[non-string]';
          this.eventsSubject.next({ type: 'status', message: `Invalid message from socket: ${preview}` });
        }
      });
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

  disconnect(): void {
    this.manualDisconnect = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
  }
}
