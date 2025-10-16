import { resolveBaseUrl } from './chatApi';
import type { AgentRequestRecord } from '../types';

interface GenerateAgentRequestBody {
  user_id: string;
  force?: boolean;
}

interface AcknowledgeAgentRequestBody {
  request_id: string;
  accepted: boolean;
  reason?: string;
}

export const generateAgentRequest = async (body: GenerateAgentRequestBody): Promise<AgentRequestRecord> => {
  const baseUrl = resolveBaseUrl();
  const response = await fetch(baseUrl + '/api/agent/request', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to generate agent request');
  }
  return (await response.json()) as AgentRequestRecord;
};

export const acknowledgeAgentRequest = async (
  body: AcknowledgeAgentRequestBody,
): Promise<AgentRequestRecord> => {
  const baseUrl = resolveBaseUrl();
  const response = await fetch(baseUrl + '/api/agent/ack', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || 'Failed to acknowledge agent request');
  }
  return (await response.json()) as AgentRequestRecord;
};
