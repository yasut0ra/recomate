import { resolveBaseUrl } from './chatApi';
import type { RitualPeriod, RitualResponse } from '../types';

interface FetchRitualOptions {
  mood?: string;
  userId?: string;
}

export const fetchRitual = async (
  period: RitualPeriod,
  options: FetchRitualOptions = {},
): Promise<RitualResponse> => {
  const baseUrl = resolveBaseUrl();
  const params = new URLSearchParams();
  if (options.mood) {
    params.set('mood', options.mood);
  }
  if (options.userId) {
    params.set('user_id', options.userId);
  }

  const endpoint =
    baseUrl +
    (period === 'morning' ? '/api/rituals/morning' : '/api/rituals/night') +
    '?' +
    params.toString();

  const response = await fetch(endpoint, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallbackMessage = 'Ritual request failed with status ' + response.status;
    throw new Error(errorText || fallbackMessage);
  }

  return (await response.json()) as RitualResponse;
};
