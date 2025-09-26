export type CharacterEmotion = 'happy' | 'thinking' | 'surprised' | 'sad' | 'neutral';

export type CharacterModel = 'anime-girl' | 'anime-boy';

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

export interface TopicStat {
  topic: string;
  count: number;
  avgReward: number;
  expectedReward: number;
}
