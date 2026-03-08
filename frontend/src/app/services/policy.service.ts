import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface PolicyDefinition {
  id: string;
  name: string;
  allow?: string[];
  deny?: string[];
  also_allow?: string[];
  agents?: Record<string, { allow?: string[]; deny?: string[]; also_allow?: string[] }>;
  created_at?: string;
  updated_at?: string;
}

export interface PolicyCreatePayload {
  name: string;
  allow?: string[];
  deny?: string[];
  also_allow?: string[];
  agents?: Record<string, { allow?: string[]; deny?: string[] }>;
}

export interface PolicyListResponse {
  schema: string;
  items: PolicyDefinition[];
  count: number;
}

@Injectable({ providedIn: 'root' })
export class PolicyService {
  private readonly apiBase = 'http://localhost:8000';

  constructor(private readonly http: HttpClient) {}

  list(): Observable<PolicyListResponse> {
    return this.http.get<PolicyListResponse>(`${this.apiBase}/api/policies`);
  }

  get(id: string): Observable<PolicyDefinition> {
    return this.http.get<PolicyDefinition>(`${this.apiBase}/api/policies/${encodeURIComponent(id)}`);
  }

  create(payload: PolicyCreatePayload): Observable<PolicyDefinition> {
    return this.http.post<PolicyDefinition>(`${this.apiBase}/api/policies`, payload);
  }

  update(id: string, payload: Partial<PolicyDefinition>): Observable<PolicyDefinition> {
    return this.http.patch<PolicyDefinition>(`${this.apiBase}/api/policies/${encodeURIComponent(id)}`, payload);
  }

  delete(id: string): Observable<{ ok: boolean }> {
    return this.http.delete<{ ok: boolean }>(`${this.apiBase}/api/policies/${encodeURIComponent(id)}`);
  }
}
