import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchMoodHistory, requestMoodTransition } from '../api/moodApi';
import type { MoodHistoryResponse, MoodStateResponse } from '../types';

const TRIGGERS = [
  { value: 'greet', label: '挨拶する' },
  { value: 'success', label: '成功を共有' },
  { value: 'relax', label: '落ち着きたい' },
  { value: 'concern', label: '心配ごと' },
  { value: 'tease', label: 'ちょっとツン' },
  { value: 'philosophy', label: '哲学モード' },
  { value: 'mischief', label: 'いたずら心' },
  { value: '', label: 'ランダム' },
];

const MoodPanel: React.FC = () => {
  const [userId, setUserId] = useState<string>('');
  const [trigger, setTrigger] = useState<string>('');
  const [history, setHistory] = useState<MoodHistoryResponse | null>(null);
  const [lastTransition, setLastTransition] = useState<MoodStateResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const hasUserId = useMemo(() => userId.trim().length > 0, [userId]);

  const loadHistory = useCallback(async () => {
    if (!hasUserId) {
      setHistory(null);
      return;
    }
    try {
      const data = await fetchMoodHistory(userId.trim());
      setHistory(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'ムード履歴の取得に失敗しました';
      setError(message);
    }
  }, [hasUserId, userId]);

  useEffect(() => {
    loadHistory().catch(() => undefined);
  }, [loadHistory]);

  const handleTransition = useCallback(async () => {
    if (!hasUserId) {
      setError('ユーザーIDを入力してください');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const response = await requestMoodTransition({
        user_id: userId.trim(),
        trigger: trigger || undefined,
      });
      setLastTransition(response);
      await loadHistory();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'ムード遷移に失敗しました';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [hasUserId, userId, trigger, loadHistory]);

  return (
    <section className="w-full max-w-3xl mx-auto mt-8">
      <div className="bg-white border border-orange-100 shadow-md rounded-xl p-5 space-y-5">
        <header className="space-y-1">
          <h2 className="text-xl font-semibold text-orange-700">ムードマシン</h2>
          <p className="text-sm text-orange-500">
            `/api/mood/transition` と `/api/mood/history` を使って現在のムードと過去推移を確認できます。
          </p>
        </header>

        <div className="grid md:grid-cols-[2fr,1fr] gap-3">
          <label className="block">
            <span className="text-xs font-semibold text-orange-600">ユーザー ID</span>
            <input
              type="text"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="11111111-1111-1111-1111-111111111111"
              className="mt-1 w-full rounded-md border border-orange-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-orange-600">トリガー</span>
            <select
              value={trigger}
              onChange={(event) => setTrigger(event.target.value)}
              className="mt-1 w-full rounded-md border border-orange-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              {TRIGGERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <button
            type="button"
            onClick={() => handleTransition().catch(() => undefined)}
            disabled={isLoading}
            className="inline-flex items-center justify-center rounded-md bg-orange-600 text-white text-sm font-medium px-4 py-2 shadow hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-orange-400 disabled:opacity-60"
          >
            {isLoading ? '遷移中...' : 'ムードを遷移'}
          </button>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded-md bg-orange-100 text-orange-700 text-sm font-medium px-4 py-2 border border-orange-200 hover:bg-orange-200"
            onClick={() => loadHistory().catch(() => undefined)}
          >
            履歴を更新
          </button>
          {error && <span className="text-sm text-red-500">{error}</span>}
        </div>

        {lastTransition && (
          <article className="bg-orange-50 border border-orange-100 rounded-lg p-4 space-y-2">
            <header className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-orange-700">直近のムード遷移</h3>
              <span className="text-xs text-orange-500">
                {new Date(lastTransition.history[0]?.ts ?? Date.now()).toLocaleString()}
              </span>
            </header>
            <p className="text-sm text-orange-900">
              {lastTransition.previous_state ?? '---'} → {lastTransition.state}
              {lastTransition.trigger ? `（トリガー: ${lastTransition.trigger}）` : ''}
            </p>
            <div className="text-xs text-orange-600">
              {Object.entries(lastTransition.weights || {}).map(([key, value]) => (
                <span key={key} className="inline-flex items-center mr-3">
                  <span className="font-semibold mr-1">{key}</span>
                  <span>{String(value)}</span>
                </span>
              ))}
            </div>
          </article>
        )}

        {history && (
          <div className="bg-orange-50 border border-orange-100 rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold text-orange-700">履歴（最新 {history.history.length} 件）</h3>
            <p className="text-sm text-orange-600">現在のムード: {history.current_state}</p>
            <ul className="space-y-2">
              {history.history.map((item, index) => (
                <li key={index} className="bg-white border border-orange-100 rounded-md px-3 py-2 shadow-sm">
                  <div className="flex justify-between text-xs text-orange-500">
                    <span>{item.state}</span>
                    <span>{item.ts ? new Date(item.ts as string).toLocaleString() : ''}</span>
                  </div>
                  {item.trigger && <p className="text-xs text-orange-600">トリガー: {item.trigger}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
};

export default MoodPanel;
