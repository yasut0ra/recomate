import React, {
  createContext,
  useContext,
  useMemo,
  useState,
  useCallback,
  useRef,
  useEffect,
} from 'react';
import type { ReactNode } from 'react';
import { fetchTopicStats, postChatMessage } from '../api/chatApi';
import { requestSpeechSynthesis, requestTranscription } from '../api/audioApi';
import type {
  CharacterEmotion,
  CharacterModel,
  ChatMessage,
  ChatApiResponse,
  ConversationHistoryEntry,
  TopicStatsResponse,
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
  transcribeAudio: (audio: Float32Array, sampleRate: number) => Promise<string | null>;
  isTranscribing: boolean;
  voiceEnabled: boolean;
  setVoiceEnabled: (value: boolean) => void;
  playAssistantSpeech: (text: string) => Promise<void>;
  topicStats: TopicStatsResponse | null;
  isTopicStatsLoading: boolean;
  refreshTopicStats: () => Promise<void>;
}

const API_KEY_STORAGE = 'recomate:api-key';
const VOICE_ENABLED_STORAGE = 'recomate:voice-enabled';

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
  const [characterModel, setCharacterModel] = useState<CharacterModel>('rico');
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
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [voiceEnabled, setVoiceEnabledState] = useState<boolean>(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    try {
      const stored = localStorage.getItem(VOICE_ENABLED_STORAGE);
      if (stored === null) {
        return true;
      }
      return stored === 'true';
    } catch (storageError) {
      console.warn('Failed to read voice preference from storage', storageError);
      return true;
    }
  });
  const [topicStats, setTopicStats] = useState<TopicStatsResponse | null>(null);
  const [isTopicStatsLoading, setIsTopicStatsLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const stopAudioPlayback = useCallback(() => {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
      } catch (pauseError) {
        console.warn('Failed to pause audio playback', pauseError);
      }
      audioRef.current.src = '';
      audioRef.current = null;
    }
    if (audioUrlRef.current && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
      URL.revokeObjectURL(audioUrlRef.current);
    }
    audioUrlRef.current = null;
  }, []);

  const resetConversation = useCallback(() => {
    stopAudioPlayback();
    setMessages([createInitialAssistantMessage()]);
    setCharacterEmotion('happy');
    setError(null);
  }, [stopAudioPlayback]);

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

  const setVoiceEnabled = useCallback((value: boolean) => {
    setVoiceEnabledState(value);
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(VOICE_ENABLED_STORAGE, value ? 'true' : 'false');
      } catch (storageError) {
        console.warn('Failed to persist voice preference', storageError);
      }
    }
    if (!value) {
      stopAudioPlayback();
    }
  }, [stopAudioPlayback]);

  useEffect(() => () => {
    stopAudioPlayback();
  }, [stopAudioPlayback]);

  useEffect(() => {
    if (!voiceEnabled) {
      stopAudioPlayback();
    }
  }, [voiceEnabled, stopAudioPlayback]);

  const refreshTopicStats = useCallback(async () => {
    setIsTopicStatsLoading(true);
    try {
      const stats = await fetchTopicStats();
      setTopicStats(stats);
    } catch (err) {
      console.warn('Failed to fetch topic stats', err);
    } finally {
      setIsTopicStatsLoading(false);
    }
  }, []);

  const transcribeAudio = useCallback(async (audio: Float32Array, sampleRate: number) => {
    if (audio.length === 0) {
      return null;
    }

    setError(null);
    setIsTranscribing(true);

    try {
      const response = await requestTranscription(audio, sampleRate, { apiKey });
      const transcript = response.text?.trim() ?? '';
      if (!transcript) {
        return null;
      }
      return transcript;
    } catch (err) {
      console.error('Failed to transcribe audio', err);
      let messageText = '音声の解析に失敗しました';
      if (err instanceof Error && err.message) {
        messageText = err.message;
      }
      setError(messageText);
      return null;
    } finally {
      setIsTranscribing(false);
    }
  }, [apiKey]);

  const playAssistantSpeech = useCallback(async (text: string) => {
    if (!voiceEnabled) {
      return;
    }

    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    try {
      stopAudioPlayback();
      const blob = await requestSpeechSynthesis(trimmed, { apiKey });
      if (typeof window === 'undefined' || typeof URL === 'undefined') {
        return;
      }

      const objectUrl = URL.createObjectURL(blob);
      audioUrlRef.current = objectUrl;
      const audioElement = new Audio(objectUrl);
      audioRef.current = audioElement;

      const cleanup = () => {
        audioElement.removeEventListener('ended', cleanup);
        audioElement.removeEventListener('error', cleanup);
        stopAudioPlayback();
      };

      audioElement.addEventListener('ended', cleanup);
      audioElement.addEventListener('error', cleanup);

      try {
        await audioElement.play();
      } catch (playError) {
        cleanup();
        console.warn('Failed to play synthesized audio', playError);
      }
    } catch (err) {
      console.warn('Failed to synthesise speech', err);
    }
  }, [voiceEnabled, apiKey, stopAudioPlayback]);

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

      const historyMessages = normaliseHistory(apiResponse.conversation_history);
      setMessages(prev => (historyMessages ? historyMessages : prev.concat(assistantMessage)));
      setCharacterEmotion(assistantEmotion);

      if (voiceEnabled) {
        const latestAssistant = historyMessages
          ? historyMessages.filter(message => message.sender === 'assistant').at(-1)
          : assistantMessage;
        if (latestAssistant?.text) {
          void playAssistantSpeech(latestAssistant.text);
        }
      }
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
    transcribeAudio,
    isTranscribing,
    voiceEnabled,
    setVoiceEnabled,
    playAssistantSpeech,
    topicStats,
    isTopicStatsLoading,
    refreshTopicStats,
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
    transcribeAudio,
    isTranscribing,
    voiceEnabled,
    setVoiceEnabled,
    playAssistantSpeech,
    topicStats,
    isTopicStatsLoading,
    refreshTopicStats,
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
