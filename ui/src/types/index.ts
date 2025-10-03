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
