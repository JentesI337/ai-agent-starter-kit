import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface AgentSocketEvent {
  type: 'status' | 'agent_step' | 'token' | 'final' | 'error' | 'tool_start' | 'tool_end' | string;
  agent?: string;
  message?: string;
  step?: string;
  token?: string;
  session_id?: string;
  request_id?: string;
  stage?: string;
  ts?: string;
  details?: Record<string, unknown>;
  tool?: string;
  tool_call_id?: string;
  duration_ms?: number;
  is_error?: boolean;
  runtime?: 'local' | 'api';
  model?: string;
  base_url?: string;
  attempt?: number;
  level?: string;
  seq?: number;
  run_id?: string;
  parent_request_id?: string;
  parent_session_id?: string;
  child_session_id?: string;
  status?: string;
  result?: string;
  notes?: string;
  stats?: Record<string, unknown>;
  usage?: unknown;
  approval?: {
    approval_id?: string;
    tool?: string;
    resource?: string;
    display_text?: string;
    options?: string[];
    scope?: string;
    status?: string;
    decision?: string;
    duplicate_decision?: boolean;
  };
}

export interface ToolPolicyPayload {
  allow?: string[];
  deny?: string[];
}

interface AgentSocketEnvelope {
  seq: number;
  event: AgentSocketEvent;
}

@Injectable({ providedIn: 'root' })
export class AgentSocketService {
  private socket?: WebSocket;
  private socketUrl = '';
  private reconnectTimer: number | null = null;
  private manualDisconnect = false;
  private lastSequence: number | null = null;
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
        this.lastSequence = null;
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
          const parsed = JSON.parse(event.data) as AgentSocketEvent | AgentSocketEnvelope;
          if (this.isEnvelope(parsed)) {
            this.handleSequence(parsed.seq);
            this.eventsSubject.next({ ...parsed.event, seq: parsed.seq });
            return;
          }
          this.eventsSubject.next(parsed);
        } catch {
          const preview = typeof event.data === 'string' ? event.data.slice(0, 200) : '[non-string]';
          this.eventsSubject.next({ type: 'status', message: `Invalid message from socket: ${preview}` });
        }
      });
    };
  }

  private isEnvelope(payload: AgentSocketEvent | AgentSocketEnvelope): payload is AgentSocketEnvelope {
    return (
      typeof payload === 'object' &&
      payload !== null &&
      'seq' in payload &&
      typeof (payload as AgentSocketEnvelope).seq === 'number' &&
      'event' in payload
    );
  }

  private handleSequence(seq: number): void {
    if (this.lastSequence !== null && seq > this.lastSequence + 1) {
      this.eventsSubject.next({
        type: 'sequence_gap',
        level: 'warning',
        message: `Missing websocket events: expected seq ${this.lastSequence + 1}, got ${seq}`,
      });
    }
    this.lastSequence = seq;
  }

  sendUserMessage(
    content: string,
    options?: { agentId?: string; preset?: string; model?: string; sessionId?: string; toolPolicy?: ToolPolicyPayload }
  ): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'user_message',
        content,
        agent_id: options?.agentId,
        preset: options?.preset,
        model: options?.model,
        session_id: options?.sessionId,
        tool_policy: options?.toolPolicy,
      })
    );
  }

  sendClarificationResponse(content: string, options?: { agentId?: string; sessionId?: string }): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'clarification_response',
        content,
        agent_id: options?.agentId,
        session_id: options?.sessionId,
      })
    );
  }

  sendSubrunSpawn(
    content: string,
    options?: { agentId?: string; preset?: string; model?: string; sessionId?: string; toolPolicy?: ToolPolicyPayload }
  ): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'subrun_spawn',
        content,
        agent_id: options?.agentId,
        preset: options?.preset,
        model: options?.model,
        session_id: options?.sessionId,
        tool_policy: options?.toolPolicy,
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

  sendPolicyDecision(
    approvalId: string,
    decision: 'allow_once' | 'allow_session' | 'cancel',
    options?: { sessionId?: string; requestId?: string }
  ): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }

    this.socket.send(
      JSON.stringify({
        type: 'policy_decision',
        approval_id: approvalId,
        decision,
        session_id: options?.sessionId,
        request_id: options?.requestId,
      })
    );
  }

  sendDebugContinue(requestId: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }
    this.socket.send(JSON.stringify({ type: 'debug_continue', request_id: requestId }));
  }

  sendDebugPause(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }
    this.socket.send(JSON.stringify({ type: 'debug_pause' }));
  }

  sendDebugPlay(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }
    this.socket.send(JSON.stringify({ type: 'debug_play' }));
  }

  sendDebugSetBreakpoints(breakpoints: string[]): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Socket is not connected.');
    }
    this.socket.send(JSON.stringify({ type: 'debug_set_breakpoints', breakpoints }));
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
