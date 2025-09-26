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

export interface ChatApiResponse {
  response: string;
  emotion?: string | { primary_emotions?: string[] };
  conversation_history?: Array<
    | [string, string]
    | {
        user_input?: string;
        response?: string;
        text?: string;
        role?: MessageSender;
        content?: string;
      }
  >;
}

export interface TopicStat {
  topic: string;
  count: number;
  avgReward: number;
  expectedReward: number;
}
