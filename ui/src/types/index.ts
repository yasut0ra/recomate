export type CharacterEmotion = 'happy' | 'thinking' | 'surprised' | 'sad' | 'neutral';

export type CharacterModel = 'rico' | 'hachika';

export type MessageSender = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  sender: MessageSender;
  text: string;
  timestamp: string;
  emotion?: CharacterEmotion;
}

export type ConversationHistoryEntry =
  | [string, string]
  | {
      user_input?: string;
      response?: string;
      text?: string;
      role?: MessageSender;
      content?: string;
      emotion?: string | { primary_emotions?: string[] };
      timestamp?: number | string;
    };

export interface ChatApiResponse {
  response: string;
  emotion?: string | { primary_emotions?: string[] };
  conversation_history?: ConversationHistoryEntry[];
}

export interface TopicMetric {
  value: number;
  count: number;
  frequency: number;
}

export interface TopicStatsResponse {
  topics: Record<string, TopicMetric>;
  subtopics: Record<string, string[]>;
  totalSelections: number;
  featureDim: number;
}

export interface TranscriptionResponse {
  text: string;
  confidence?: number;
}

export type RitualPeriod = 'morning' | 'night';

export interface RitualEvent {
  event: string;
  value: string;
}

export interface RitualResponse {
  period: RitualPeriod;
  mood: string;
  script: string;
  events: RitualEvent[];
  source: 'default' | 'custom';
}

export interface AlbumWeeklyResponse {
  week_id: string;
  user_id: string;
  highlights_json: Record<string, unknown>;
  wins_json: Record<string, unknown>;
  photos: Record<string, unknown>;
  quote_best?: string | null;
  created_at: string;
}

export interface MemoryRecord {
  id: string;
  user_id: string;
  summary_md: string;
  keywords: string[];
  pinned: boolean;
  created_at: string;
  last_ref?: string | null;
}

export interface AgentRequestRecord {
  id: string;
  user_id: string;
  kind: string;
  payload?: Record<string, unknown> | null;
  ts: string;
  accepted?: boolean | null;
}

export interface MoodStateResponse {
  user_id: string;
  state: string;
  previous_state?: string | null;
  trigger?: string | null;
  weights: Record<string, unknown>;
  history: Array<Record<string, unknown>>;
}

export interface MoodHistoryResponse {
  user_id: string;
  current_state: string;
  history: Array<Record<string, unknown>>;
}
