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
