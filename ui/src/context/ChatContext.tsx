import React, { createContext, useContext, useMemo, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { postChatMessage } from '../api/chatApi';
import type {
  CharacterEmotion,
  CharacterModel,
  ChatMessage,
  ChatApiResponse,
} from '../types';

interface ChatContextType {
  messages: ChatMessage[];
  sendMessage: (text: string) => Promise<void>;
  isProcessing: boolean;
  error: string | null;
  characterEmotion: CharacterEmotion;
  setCharacterEmotion: (emotion: CharacterEmotion) => void;
  characterModel: CharacterModel;
  setCharacterModel: (model: CharacterModel) => void;
  resetConversation: () => void;
}

const createInitialAssistantMessage = (): ChatMessage => ({
  id: 'assistant-intro',
  sender: 'assistant',
  text: 'こんにちは！RecoMateです。どんなお話をしましょうか？',
  timestamp: new Date().toISOString(),
  emotion: 'happy',
});

const ChatContext = createContext<ChatContextType | undefined>(undefined);

const emotionMap: Record<string, CharacterEmotion> = {
  happy: 'happy',
  joy: 'happy',
  joyful: 'happy',
  delighted: 'happy',
  sad: 'sad',
  sorrow: 'sad',
  unhappy: 'sad',
  angry: 'surprised',
  upset: 'surprised',
  surprised: 'surprised',
  thinking: 'thinking',
  neutral: 'neutral',
};

const getRandomId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'msg-' + Math.random().toString(16).slice(2);
};

const normaliseEmotion = (emotion: ChatApiResponse['emotion']): CharacterEmotion => {
  if (!emotion) {
    return 'thinking';
  }

  if (typeof emotion === 'string') {
    const key = emotion.toLowerCase();
    return emotionMap[key] ?? 'thinking';
  }

  const primary = emotion.primary_emotions && emotion.primary_emotions[0];
  if (primary) {
    const key = primary.toLowerCase();
    return emotionMap[key] ?? 'thinking';
  }

  return 'thinking';
};

const normaliseHistory = (
  history: ChatApiResponse['conversation_history'],
): ChatMessage[] | null => {
  if (!history || history.length === 0) {
    return null;
  }

  const result: ChatMessage[] = [];

  history.forEach((entry, index) => {
    const baseTimestamp = new Date(Date.now() - (history.length - index) * 1000).toISOString();

    if (Array.isArray(entry)) {
      const userInput = entry[0];
      const response = entry[1];
      if (typeof userInput === 'string') {
        result.push({
          id: 'history-user-' + index,
          sender: 'user',
          text: userInput,
          timestamp: baseTimestamp,
        });
      }
      if (typeof response === 'string') {
        result.push({
          id: 'history-assistant-' + index,
          sender: 'assistant',
          text: response,
          timestamp: baseTimestamp,
        });
      }
      return;
    }

    if (entry && typeof entry === 'object') {
      if (typeof entry.user_input === 'string') {
        result.push({
          id: 'history-user-' + index,
          sender: 'user',
          text: entry.user_input,
          timestamp: baseTimestamp,
        });
      }
      if (typeof entry.response === 'string') {
        result.push({
          id: 'history-assistant-' + index,
          sender: 'assistant',
          text: entry.response,
          timestamp: baseTimestamp,
        });
      }
      if (!entry.user_input && entry.role && entry.content) {
        const sender = entry.role === 'assistant' ? 'assistant' : 'user';
        result.push({
          id: 'history-' + sender + '-' + index,
          sender,
          text: String(entry.content),
          timestamp: baseTimestamp,
        });
      }
    }
  });

  if (result.length === 0) {
    return null;
  }

  return result;
};

export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([createInitialAssistantMessage()]);
  const [characterEmotion, setCharacterEmotion] = useState<CharacterEmotion>('happy');
  const [characterModel, setCharacterModel] = useState<CharacterModel>('anime-girl');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetConversation = useCallback(() => {
    setMessages([createInitialAssistantMessage()]);
    setCharacterEmotion('happy');
    setError(null);
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    const userMessage: ChatMessage = {
      id: getRandomId(),
      sender: 'user',
      text: trimmed,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => prev.concat(userMessage));
    setError(null);
    setCharacterEmotion('thinking');
    setIsProcessing(true);

    try {
      const apiResponse = await postChatMessage(trimmed);
      const assistantEmotion = normaliseEmotion(apiResponse.emotion);
      const assistantMessage: ChatMessage = {
        id: getRandomId(),
        sender: 'assistant',
        text: apiResponse.response,
        timestamp: new Date().toISOString(),
        emotion: assistantEmotion,
      };

      setMessages(prev => {
        const historyMessages = normaliseHistory(apiResponse.conversation_history);
        if (historyMessages) {
          return historyMessages;
        }
        return prev.concat(assistantMessage);
      });
      setCharacterEmotion(assistantEmotion);
    } catch (err) {
      console.error('Failed to send chat message', err);
      const message = err instanceof Error ? err.message : 'メッセージの送信に失敗しました';
      setError(message);
      setCharacterEmotion('sad');
    } finally {
      setIsProcessing(false);
    }
  }, []);

  const value = useMemo(() => ({
    messages,
    sendMessage,
    isProcessing,
    error,
    characterEmotion,
    setCharacterEmotion,
    characterModel,
    setCharacterModel,
    resetConversation,
  }), [
    messages,
    sendMessage,
    isProcessing,
    error,
    characterEmotion,
    characterModel,
    resetConversation,
  ]);

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

export const useChatContext = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
};
