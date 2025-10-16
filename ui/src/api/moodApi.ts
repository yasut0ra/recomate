import { resolveBaseUrl } from './chatApi';
import type { MoodHistoryResponse, MoodStateResponse } from '../types';

interface MoodTransitionBody {
  user_id: string;
  trigger?: string;
}

export const requestMoodTransition = async (body: MoodTransitionBody): Promise<MoodStateResponse> => {
  const baseUrl = resolveBaseUrl();
  const response = await fetch(baseUrl + '/api/mood/transition', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to transition mood');
  }
  return (await response.json()) as MoodStateResponse;
};

export const fetchMoodHistory = async (userId: string, limit = 10): Promise<MoodHistoryResponse> => {
  const baseUrl = resolveBaseUrl();
  const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
  const response = await fetch(baseUrl + '/api/mood/history?' + params.toString(), {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to fetch mood history');
  }
  return (await response.json()) as MoodHistoryResponse;
};
