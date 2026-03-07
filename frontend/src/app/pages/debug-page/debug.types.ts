// Re-export shared debug types from the singleton state service
export type {
  DebugState,
  PipelinePhase,
  PhaseState,
  LlmCallRecord,
  ToolExecutionRecord,
  ReflectionVerdict,
  DebugEvent,
  DebugSnapshot,
} from '../../services/agent-state.service';

// UI-only types (not shared via state service)

export interface PhaseDefinition {
  id: import('../../services/agent-state.service').PipelinePhase;
  label: string;
  icon: string;
  hasLlm: boolean;
  index: number;
}

export type InspectorTab =
  'system_prompt' | 'user_prompt' | 'llm_response' |
  'parsed_output' | 'tool_details' | 'reflection';
