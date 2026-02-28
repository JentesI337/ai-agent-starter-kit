import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

export interface RuntimeStatus {
  runtime: 'local' | 'api';
  baseUrl: string;
  model: string;
  authenticated: boolean;
  apiModelsAvailable?: boolean | null;
  apiModelsCount?: number | null;
  apiModelsError?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AgentsService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  getRuntimeStatus() {
    return this.http.get<RuntimeStatus>(`${this.apiBase}/api/runtime/status`);
  }
}
