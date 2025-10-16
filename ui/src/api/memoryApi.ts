import { resolveBaseUrl } from './chatApi';
import type { MemoryRecord } from '../types';

interface MemorySearchParams {
  query?: string;
  userId?: string;
  limit?: number;
}

interface MemoryCommitPayload {
  episode_id: string;
  summary?: string;
  keywords?: string[];
  pinned?: boolean;
}

export const searchMemories = async ({
  query,
  userId,
  limit,
}: MemorySearchParams): Promise<MemoryRecord[]> => {
  const baseUrl = resolveBaseUrl();
  const params = new URLSearchParams();
  if (query) {
    params.set('q', query);
  }
  if (userId) {
    params.set('user_id', userId);
  }
  if (limit) {
    params.set('limit', String(limit));
  }
  const endpoint = baseUrl + '/api/memory/search?' + params.toString();
  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to search memories');
  }
  return (await response.json()) as MemoryRecord[];
};

export const commitMemory = async (payload: MemoryCommitPayload): Promise<MemoryRecord> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/memory/commit';
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to commit memory');
  }
  return (await response.json()) as MemoryRecord;
};
