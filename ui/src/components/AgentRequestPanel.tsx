import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { acknowledgeAgentRequest, generateAgentRequest } from '../api/agentApi';
import type { AgentRequestRecord } from '../types';

const KIND_LABELS: Record<string, string> = {
  memory_cleanup: 'メモリ整理のお願い',
  quiet_mode: '静かな時間の提案',
  album_asset: 'アルバム素材のお願い',
  topic_taste: '好みの共有リクエスト',
};

const AgentRequestPanel: React.FC = () => {
  const [userId, setUserId] = useState<string>('');
  const [force, setForce] = useState<boolean>(false);
  const [requests, setRequests] = useState<AgentRequestRecord[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [ackInFlight, setAckInFlight] = useState<boolean>(false);
  const [ackReason, setAckReason] = useState<string>('');

  const requestLabel = useMemo(() => {
    const current = requests[selectedIndex];
    if (!current) return null;
    return KIND_LABELS[current.kind] ?? current.kind;
  }, [requests, selectedIndex]);

  const currentRequest = requests[selectedIndex] ?? null;

  useEffect(() => {
    if (selectedIndex >= requests.length) {
      setSelectedIndex(0);
    }
  }, [requests, selectedIndex]);

  const handleGenerate = useCallback(async () => {
    if (!userId.trim()) {
      setError('ユーザーIDを入力してください');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const newRequest = await generateAgentRequest({ user_id: userId.trim(), force });
      setRequests((prev) => [newRequest, ...prev].slice(0, 10));
      setSelectedIndex(0);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'リクエスト生成に失敗しました';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [userId, force]);

  const handleAcknowledge = useCallback(
    async (accepted: boolean) => {
      const request = currentRequest;
      if (!request) {
        return;
      }
      setAckInFlight(true);
      setError(null);
      try {
        const updated = await acknowledgeAgentRequest({
          request_id: request.id,
          accepted,
          reason: ackReason.trim() || undefined,
        });
        setRequests((prev) =>
          prev.map((item) => (item.id === updated.id ? updated : item)),
        );
        setAckReason('');
      } catch (err) {
        const message = err instanceof Error ? err.message : '応答送信に失敗しました';
        setError(message);
      } finally {
        setAckInFlight(false);
      }
    },
    [currentRequest, ackReason],
  );

  return (
    <section className="w-full max-w-3xl mx-auto mt-8">
      <div className="bg-white border border-sky-100 shadow-md rounded-xl p-5 space-y-5">
        <header className="space-y-1">
          <h2 className="text-xl font-semibold text-sky-700">Agent リクエスト</h2>
          <p className="text-sm text-sky-500">
            `/api/agent/request` と `/api/agent/ack` のフローを体験できます。境界やタスクの聞き返しなど、AIからユーザーへのお願いを生成します。
          </p>
        </header>

        <div className="grid gap-3 md:grid-cols-[2fr,1fr]">
          <label className="block">
            <span className="text-xs font-semibold text-sky-600">ユーザー ID</span>
            <input
              type="text"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="11111111-1111-1111-1111-111111111111"
              className="mt-1 w-full rounded-md border border-sky-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-sky-700">
            <input
              type="checkbox"
              checked={force}
              onChange={(event) => setForce(event.target.checked)}
              className="rounded border-sky-300 text-sky-600 focus:ring-sky-400"
            />
            クールダウンを無視して生成
          </label>
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <button
            type="button"
            onClick={() => handleGenerate().catch(() => undefined)}
            disabled={isLoading}
            className="inline-flex items-center justify-center rounded-md bg-sky-600 text-white text-sm font-medium px-4 py-2 shadow hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:opacity-60"
          >
            {isLoading ? '生成中...' : 'Agent リクエスト生成'}
          </button>
          {error && <span className="text-sm text-red-500">{error}</span>}
        </div>

        {requests.length > 0 && (
          <article className="bg-sky-50 border border-sky-100 rounded-lg p-4 space-y-3">
            <header className="flex items-center justify-between">
              <div className="text-sm text-sky-700 font-semibold">
                {requestLabel}
              </div>
              <span className="text-xs px-3 py-1 rounded-full border border-sky-200 text-sky-600 bg-white">
                {currentRequest?.accepted === undefined || currentRequest?.accepted === null
                  ? '応答待ち'
                  : currentRequest?.accepted
                  ? '承諾済み'
                  : '辞退済み'}
              </span>
            </header>
            <div className="text-sm text-sky-900 space-y-2">
              <div className="text-xs text-sky-500">Request ID: {currentRequest?.id}</div>
              {currentRequest?.payload && currentRequest.payload.message && (
                <p className="whitespace-pre-wrap leading-relaxed">
                  {String(currentRequest.payload.message)}
                </p>
              )}
              <p className="text-xs text-sky-500">
                生成時刻: {currentRequest ? new Date(currentRequest.ts).toLocaleString() : ''}
              </p>
              {currentRequest?.payload && currentRequest.payload.ack_reason && (
                <p className="text-xs text-sky-500">
                  返信コメント: {String(currentRequest.payload.ack_reason)}
                </p>
              )}
            </div>

            {(currentRequest?.accepted === undefined || currentRequest?.accepted === null) && (
              <form
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  handleAcknowledge(true).catch(() => undefined);
                }}
              >
                <label className="block">
                  <span className="text-xs font-semibold text-sky-600">コメント（任意）</span>
                  <textarea
                    value={ackReason}
                    onChange={(event) => setAckReason(event.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-md border border-sky-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="submit"
                    disabled={ackInFlight}
                    className="inline-flex items-center justify-center rounded-md bg-emerald-600 text-white text-sm font-medium px-4 py-2 shadow hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:opacity-60"
                  >
                    {ackInFlight ? '送信中...' : '承諾する'}
                  </button>
                  <button
                    type="button"
                    disabled={ackInFlight}
                    onClick={() => handleAcknowledge(false).catch(() => undefined)}
                    className="inline-flex items-center justify-center rounded-md bg-rose-500 text-white text-sm font-medium px-4 py-2 shadow hover:bg-rose-600 focus:outline-none focus:ring-2 focus:ring-rose-400 disabled:opacity-60"
                  >
                    辞退する
                  </button>
                </div>
              </form>
            )}
          </article>
        )}

        {requests.length > 1 && (
          <div className="bg-sky-50 border border-sky-100 rounded-lg p-4 space-y-2">
            <h3 className="text-sm font-semibold text-sky-700">過去のリクエスト</h3>
            <ul className="grid gap-2">
              {requests.map((item, index) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedIndex(index)}
                    className={`w-full text-left px-3 py-2 rounded-md border transition ${
                      index === selectedIndex
                        ? 'border-sky-300 bg-white shadow'
                        : 'border-transparent bg-white/60 hover:bg-white'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs text-sky-500">
                      <span>
                        {new Date(item.ts).toLocaleTimeString()} · {KIND_LABELS[item.kind] ?? item.kind}
                      </span>
                      <span>
                        {item.accepted === undefined || item.accepted === null
                          ? '---'
                          : item.accepted
                          ? '承諾'
                          : '辞退'}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
};

export default AgentRequestPanel;
