import type { ChatApiResponse, ChatFeedbackResponse, TopicStatsResponse } from '../types';

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8000';

export const resolveBaseUrl = () => {
  const fromEnv = import.meta.env?.VITE_API_BASE_URL as string | undefined;
  const trimmed = fromEnv?.trim();
  if (!trimmed) {
    return DEFAULT_BASE_URL;
  }
  return trimmed.replace(/\/$/, '');
};

interface PostChatOptions {
  apiKey?: string | null;
  userId?: string | null;
}

export const postChatMessage = async (message: string, options?: PostChatOptions): Promise<ChatApiResponse> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/chat';

  const payload: Record<string, unknown> = { text: message };
  if (options?.apiKey) {
    payload.api_key = options.apiKey;
  }
  if (options?.userId) {
    payload.user_id = options.userId;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallbackMessage = 'Chat API request failed with status ' + response.status;
    throw new Error(errorText || fallbackMessage);
  }

  return (await response.json()) as ChatApiResponse;
};

export const postChatFeedback = async (
  turnId: string,
  like: boolean,
  options?: { userId?: string | null },
): Promise<ChatFeedbackResponse> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/chat/feedback';

  const payload: Record<string, unknown> = { turn_id: turnId, like };
  if (options?.userId) {
    payload.user_id = options.userId;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallbackMessage = 'Chat feedback request failed with status ' + response.status;
    throw new Error(errorText || fallbackMessage);
  }

  return (await response.json()) as ChatFeedbackResponse;
};

export const fetchTopicStats = async (): Promise<TopicStatsResponse> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/topics/stats';

  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallbackMessage = 'Topic stats request failed with status ' + response.status;
    throw new Error(errorText || fallbackMessage);
  }

  return (await response.json()) as TopicStatsResponse;
};
