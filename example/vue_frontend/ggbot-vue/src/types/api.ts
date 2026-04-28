export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface Session {
  id: string;
  title: string;
  created_at: number;
}

export type EventType =
  | "assistant_delta"
  | "assistant_final"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "turn_update"
  | "turn_complete"
  | "status"
  | "error"
  | "provider_error"
  | "session_update"
  | "doc_build_stage"
  | "permission_request"
  | "permission_response";

export interface GGEvent {
  type: 'event';
  event_type: EventType;
  data: any;
  timestamp: number;
}

export interface CompleteEvent {
  type: 'complete';
  data: {
    session_id: string;
    final_response: string;
    success: boolean;
  };
}

export interface ErrorEvent {
  type: 'error';
  data: {
    error: string;
  };
}

export type StreamEvent = GGEvent | CompleteEvent | ErrorEvent;
