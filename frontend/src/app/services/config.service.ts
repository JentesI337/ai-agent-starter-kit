import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

// ── Config Sections ────────────────────────────────

export interface SectionFieldMeta {
  name: string;
  type: string;
  default: unknown;
  description?: string;
  sensitive?: boolean;
  current_value?: unknown;
}

export interface SectionMeta {
  key: string;
  label: string;
  field_count: number;
  fields: SectionFieldMeta[];
}

export interface ConfigSectionsResponse {
  schema: string;
  sections: SectionMeta[];
}

export interface ConfigGetResponse {
  schema: string;
  sectionKey: string;
  values: Record<string, unknown>;
}

export interface ConfigUpdateResponse {
  schema: string;
  sectionKey: string;
  changes: Array<{
    field: string;
    previous_value: unknown;
    new_value: unknown;
    persisted: boolean;
  }>;
  validation_errors?: string[];
}

export interface ConfigDiffResponse {
  schema: string;
  overrides: Record<string, Record<string, { env_value: unknown; runtime_value: unknown }>>;
}

export interface ConfigResetResponse {
  schema: string;
  sectionKey: string;
  reset_fields: string[];
}

// ── Agent Configs ──────────────────────────────────

export interface AgentRuntimeConfig {
  agent_id: string;
  temperature: number;
  reflection_passes: number;
  reasoning_depth: number;
  max_context: number | null;
  combine_steps: boolean;
  read_only: boolean;
  mandatory_deny_tools: string[];
  additional_deny_tools: string[];
  additional_allow_tools: string[];
  [key: string]: unknown;
}

export interface AgentConfigListResponse {
  schema: string;
  agents: AgentRuntimeConfig[];
}

export interface AgentConfigGetResponse {
  schema: string;
  config: AgentRuntimeConfig;
}

export interface AgentConfigUpdateResponse {
  schema: string;
  agentId: string;
  changes: Array<{ field: string; previous_value: unknown; new_value: unknown }>;
}

// ── Tool Configs ───────────────────────────────────

export interface ToolRuntimeConfig {
  tool_name: string;
  enabled: boolean;
  timeout_seconds: number;
  retries: number;
  [key: string]: unknown;
}

export interface ToolConfigListResponse {
  schema: string;
  tools: ToolRuntimeConfig[];
}

export interface ToolConfigGetResponse {
  schema: string;
  config: ToolRuntimeConfig;
}

export interface ToolConfigUpdateResponse {
  schema: string;
  toolName: string;
  changes: Array<{ field: string; previous_value: unknown; new_value: unknown }>;
}

// ── Security Patterns ──────────────────────────────

export interface SecurityPattern {
  pattern: string;
  reason: string;
  builtin: boolean;
}

export interface SecurityPatternsResponse {
  schema: string;
  patterns: SecurityPattern[];
}

// ── Execution Config ───────────────────────────────

export interface ExecutionConfigResponse {
  schema: string;
  budget: Record<string, unknown>;
  result_processing: Record<string, unknown>;
  loop_detection: Record<string, unknown>;
}

export interface LoopDetectionConfigResponse {
  schema: string;
  config: Record<string, unknown>;
}

// ── Config Health ──────────────────────────────────

export interface ConfigHealthResponse {
  schema: string;
  status: string;
  sections_loaded: number;
  override_count: number;
  errors: string[];
}

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private readonly api = 'http://localhost:8000/api/control';

  constructor(private readonly http: HttpClient) {}

  // ── Config Sections ────────────────────────────────

  getSections(): Observable<ConfigSectionsResponse> {
    return this.http.post<ConfigSectionsResponse>(`${this.api}/config.sections`, {});
  }

  getSection(sectionKey: string): Observable<ConfigGetResponse> {
    return this.http.post<ConfigGetResponse>(`${this.api}/config.get`, { sectionKey });
  }

  updateSection(sectionKey: string, updates: Record<string, unknown>): Observable<ConfigUpdateResponse> {
    return this.http.post<ConfigUpdateResponse>(`${this.api}/config.update`, { sectionKey, updates });
  }

  resetSection(sectionKey: string): Observable<ConfigResetResponse> {
    return this.http.post<ConfigResetResponse>(`${this.api}/config.reset`, { sectionKey });
  }

  getDiff(): Observable<ConfigDiffResponse> {
    return this.http.post<ConfigDiffResponse>(`${this.api}/config.diff`, {});
  }

  getHealth(): Observable<ConfigHealthResponse> {
    return this.http.post<ConfigHealthResponse>(`${this.api}/config.health`, {});
  }

  // ── Agent Configs ──────────────────────────────────

  getAgentConfigs(): Observable<AgentConfigListResponse> {
    return this.http.post<AgentConfigListResponse>(`${this.api}/agents.config.list`, {});
  }

  getAgentConfig(agentId: string): Observable<AgentConfigGetResponse> {
    return this.http.post<AgentConfigGetResponse>(`${this.api}/agents.config.get`, { agentId });
  }

  updateAgentConfig(agentId: string, updates: Record<string, unknown>): Observable<AgentConfigUpdateResponse> {
    return this.http.post<AgentConfigUpdateResponse>(`${this.api}/agents.config.update`, { agentId, updates });
  }

  resetAgentConfig(agentId: string): Observable<{ schema: string }> {
    return this.http.post<{ schema: string }>(`${this.api}/agents.config.reset`, { agentId });
  }

  // ── Tool Configs ───────────────────────────────────

  getToolConfigs(): Observable<ToolConfigListResponse> {
    return this.http.post<ToolConfigListResponse>(`${this.api}/tools.config.list`, {});
  }

  getToolConfig(toolName: string): Observable<ToolConfigGetResponse> {
    return this.http.post<ToolConfigGetResponse>(`${this.api}/tools.config.get`, { toolName });
  }

  updateToolConfig(toolName: string, updates: Record<string, unknown>): Observable<ToolConfigUpdateResponse> {
    return this.http.post<ToolConfigUpdateResponse>(`${this.api}/tools.config.update`, { toolName, updates });
  }

  resetToolConfig(toolName: string): Observable<{ schema: string }> {
    return this.http.post<{ schema: string }>(`${this.api}/tools.config.reset`, { toolName });
  }

  // ── Security Patterns ──────────────────────────────

  getSecurityPatterns(): Observable<SecurityPatternsResponse> {
    return this.http.post<SecurityPatternsResponse>(`${this.api}/tools.security.patterns`, {});
  }

  addSecurityPattern(pattern: string, reason: string): Observable<{ schema: string }> {
    return this.http.post<{ schema: string }>(`${this.api}/tools.security.update`, { pattern, reason });
  }

  // ── Execution Config ───────────────────────────────

  getExecutionConfig(): Observable<ExecutionConfigResponse> {
    return this.http.post<ExecutionConfigResponse>(`${this.api}/execution.config.get`, {});
  }

  updateExecutionConfig(updates: Record<string, unknown>): Observable<{ schema: string }> {
    return this.http.post<{ schema: string }>(`${this.api}/execution.config.update`, updates);
  }

  getLoopDetectionConfig(): Observable<LoopDetectionConfigResponse> {
    return this.http.post<LoopDetectionConfigResponse>(`${this.api}/execution.loop-detection.get`, {});
  }

  updateLoopDetectionConfig(updates: Record<string, unknown>): Observable<{ schema: string }> {
    return this.http.post<{ schema: string }>(`${this.api}/execution.loop-detection.update`, { updates });
  }
}
