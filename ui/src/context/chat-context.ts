import { createContext } from 'react';
import type {
  CharacterEmotion,
  CharacterModel,
  ChatMessage,
  TopicStatsResponse,
} from '../types';

export interface ChatContextType {
  messages: ChatMessage[];
  sendMessage: (text: string) => Promise<void>;
  isProcessing: boolean;
  error: string | null;
  characterEmotion: CharacterEmotion;
  setCharacterEmotion: (emotion: CharacterEmotion) => void;
  characterModel: CharacterModel;
  setCharacterModel: (model: CharacterModel) => void;
  resetConversation: () => void;
  apiKey: string | null;
  setApiKey: (key: string | null) => void;
  transcribeAudio: (audio: Float32Array, sampleRate: number) => Promise<string | null>;
  isTranscribing: boolean;
  voiceEnabled: boolean;
  setVoiceEnabled: (value: boolean) => void;
  playAssistantSpeech: (text: string) => Promise<void>;
  topicStats: TopicStatsResponse | null;
  isTopicStatsLoading: boolean;
  refreshTopicStats: () => Promise<void>;
}

export const ChatContext = createContext<ChatContextType | undefined>(undefined);
