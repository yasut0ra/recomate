import React, { createContext, useContext, useMemo, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { postChatMessage } from '../api/chatApi';
import type {
  CharacterEmotion,
  CharacterModel,
  ChatMessage,
  ChatApiResponse,
  ConversationHistoryEntry,
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
  apiKey: string | null;
  setApiKey: (key: string | null) => void;
}

const API_KEY_STORAGE = 'recomate:api-key';

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

const resolveTimestamp = (raw: ConversationHistoryEntry | undefined, index: number, total: number): string => {
  if (raw && !Array.isArray(raw) && typeof raw === 'object' && 'timestamp' in raw) {
    const { timestamp } = raw as { timestamp?: unknown };
    if (typeof timestamp === 'number' && Number.isFinite(timestamp)) {
      return new Date(timestamp * 1000).toISOString();
    }
    if (typeof timestamp === 'string') {
      const parsed = new Date(timestamp);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed.toISOString();
      }
    }
  }
  const offsetSeconds = Math.max(total - index, 1);
  return new Date(Date.now() - offsetSeconds * 1000).toISOString();
};

const normaliseHistory = (
  history: ChatApiResponse['conversation_history'],
): ChatMessage[] | null => {
  if (!history || history.length === 0) {
    return null;
  }

  const result: ChatMessage[] = [];

  history.forEach((entry, index) => {
    const timestamp = resolveTimestamp(entry as ConversationHistoryEntry, index, history.length);

    if (Array.isArray(entry)) {
      const userInput = entry[0];
      const response = entry[1];
      if (typeof userInput === 'string') {
        result.push({
          id: 'history-user-' + index,
          sender: 'user',
          text: userInput,
          timestamp,
        });
      }
      if (typeof response === 'string') {
        result.push({
          id: 'history-assistant-' + index,
          sender: 'assistant',
          text: response,
          timestamp,
        });
      }
      return;
    }

    if (entry && typeof entry === 'object') {
      const entryObject = entry as Extract<ConversationHistoryEntry, Record<string, unknown>>;
      const emotion = 'emotion' in entryObject ? normaliseEmotion(entryObject.emotion as ChatApiResponse['emotion']) : undefined;

      if (typeof entryObject.user_input === 'string') {
        result.push({
          id: 'history-user-' + index,
          sender: 'user',
          text: entryObject.user_input,
          timestamp,
        });
      }
      if (typeof entryObject.response === 'string') {
        result.push({
          id: 'history-assistant-' + index,
          sender: 'assistant',
          text: entryObject.response,
          timestamp,
          emotion,
        });
      }
      if (!entryObject.user_input && entryObject.role && entryObject.content) {
        const sender = entryObject.role === 'assistant' ? 'assistant' : 'user';
        result.push({
          id: 'history-' + sender + '-' + index,
          sender,
          text: String(entryObject.content),
          timestamp,
          emotion: sender === 'assistant' ? emotion : undefined,
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
  const [apiKey, setApiKeyState] = useState<string | null>(() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return localStorage.getItem(API_KEY_STORAGE);
    } catch (storageError) {
      console.warn('Failed to read API key from storage', storageError);
      return null;
    }
  });

  const resetConversation = useCallback(() => {
    setMessages([createInitialAssistantMessage()]);
    setCharacterEmotion('happy');
    setError(null);
  }, []);

  const setApiKey = useCallback((key: string | null) => {
    setApiKeyState(key);
    if (typeof window === 'undefined') {
      return;
    }
    try {
      if (key && key.length > 0) {
        localStorage.setItem(API_KEY_STORAGE, key);
      } else {
        localStorage.removeItem(API_KEY_STORAGE);
      }
    } catch (storageError) {
      console.warn('Failed to persist API key', storageError);
    }
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
      const apiResponse = await postChatMessage(trimmed, { apiKey });
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
      let messageText = 'メッセージの送信に失敗しました';
      if (err instanceof Error) {
        messageText = err.message === 'Failed to fetch'
          ? 'APIサーバーに接続できませんでした。サーバーが起動しているか、設定したURLが正しいか確認してください。'
          : err.message;
      }
      setError(messageText);
      setCharacterEmotion('sad');
    } finally {
      setIsProcessing(false);
    }
  }, [apiKey]);

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
    apiKey,
    setApiKey,
  }), [
    messages,
    sendMessage,
    isProcessing,
    error,
    characterEmotion,
    characterModel,
    resetConversation,
    apiKey,
    setApiKey,
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
