import type { TranscriptionResponse } from '../types';
import { resolveBaseUrl } from './chatApi';

interface AudioApiOptions {
  apiKey?: string | null;
}

const buildHeaders = () => ({
  'Content-Type': 'application/json',
});

export const requestTranscription = async (
  audio: Float32Array,
  sampleRate: number,
  options?: AudioApiOptions,
): Promise<TranscriptionResponse> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/transcribe';

  const payload: Record<string, unknown> = {
    audio_data: Array.from(audio),
    sample_rate: sampleRate,
  };

  if (options) {
    payload.api_key = options.apiKey ?? null;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallback = 'Transcription request failed with status ' + response.status;
    throw new Error(errorText || fallback);
  }

  return (await response.json()) as TranscriptionResponse;
};

export const requestSpeechSynthesis = async (
  text: string,
  options?: AudioApiOptions,
): Promise<Blob> => {
  const baseUrl = resolveBaseUrl();
  const endpoint = baseUrl + '/api/text-to-speech';

  const payload: Record<string, unknown> = { text };
  if (options) {
    payload.api_key = options.apiKey ?? null;
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    const fallback = 'Text-to-speech request failed with status ' + response.status;
    throw new Error(errorText || fallback);
  }

  return await response.blob();
};
