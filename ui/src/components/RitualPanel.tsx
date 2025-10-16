import React, { useCallback, useEffect, useMemo, useState } from 'react';
import type { RitualPeriod, RitualResponse } from '../types';
import { fetchRitual } from '../api/ritualApi';
import Live2DPanel from './Live2DPanel';

const PERIOD_LABELS: Record<RitualPeriod, string> = {
  morning: '朝のリチュアル',
  night: '夜のリチュアル',
};

const DEFAULT_MOODS = ['穏やか', '陽気', '哲学', 'ツン', '心配'];

const RitualPanel: React.FC = () => {
  const [period, setPeriod] = useState<RitualPeriod>('morning');
  const [mood, setMood] = useState<string>('穏やか');
  const [userId, setUserId] = useState<string>('');
  const [data, setData] = useState<RitualResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const moodOptions = useMemo(() => {
    if (period === 'morning') {
      return DEFAULT_MOODS.slice(0, 3);
    }
    return ['穏やか', 'ツン', '心配'];
  }, [period]);

  const selectedMood = useMemo(() => {
    if (moodOptions.includes(mood)) {
      return mood;
    }
    return moodOptions[0];
  }, [mood, moodOptions]);

  const loadRitual = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchRitual(period, {
        mood: selectedMood,
        userId: userId.trim() || undefined,
      });
      setData(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'リチュアルの取得に失敗しました';
      setError(message);
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [period, selectedMood, userId]);

  useEffect(() => {
    loadRitual().catch(() => {
      // エラーは loadRitual 内で処理済み。
    });
  }, [loadRitual]);

  return (
    <section className="w-full max-w-3xl mx-auto mt-8">
      <div className="bg-white shadow-md border border-purple-100 rounded-xl p-5">
        <header className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-2 mb-4">
          <div>
            <h2 className="text-xl font-semibold text-purple-700">リチュアルプレビュー</h2>
            <p className="text-sm text-purple-500">
              朝・夜のスクリプトと Live2D イベントをプレビューします。カスタム YAML を登録すると自動で反映されます。
            </p>
          </div>
          <div className="flex gap-2">
            {(['morning', 'night'] as RitualPeriod[]).map((value) => (
              <button
                key={value}
                type="button"
                className={`px-4 py-2 rounded-full text-sm font-medium transition ${
                  period === value
                    ? 'bg-purple-600 text-white shadow'
                    : 'bg-purple-50 text-purple-600 hover:bg-purple-100'
                }`}
                onClick={() => setPeriod(value)}
              >
                {PERIOD_LABELS[value]}
              </button>
            ))}
          </div>
        </header>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-3">
            <label className="block">
              <span className="text-xs font-semibold text-purple-600">ムード</span>
              <select
                className="mt-1 w-full rounded-md border border-purple-200 bg-purple-50 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                value={selectedMood}
                onChange={(event) => setMood(event.target.value)}
              >
                {moodOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-purple-600">ユーザー ID（任意）</span>
              <input
                type="text"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="11111111-1111-1111-1111-111111111111"
                className="mt-1 w-full rounded-md border border-purple-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </label>
            <button
              type="button"
              onClick={() => loadRitual().catch(() => undefined)}
              className="inline-flex items-center justify-center rounded-md bg-purple-600 text-white text-sm font-medium px-4 py-2 shadow hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              最新のスクリプトを取得
            </button>
            {error && <p className="text-sm text-red-500">{error}</p>}
            {isLoading && <p className="text-sm text-purple-500">ロード中...</p>}
            {data && !isLoading && (
              <article className="bg-purple-50 border border-purple-100 rounded-lg p-4 space-y-3">
                <header className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-purple-700">
                    {PERIOD_LABELS[data.period]}（{data.mood}）
                  </h3>
                  <span className="text-xs text-purple-500 bg-white border border-purple-200 rounded-full px-3 py-1">
                    {data.source === 'custom' ? 'カスタムスクリプト' : 'デフォルトスクリプト'}
                  </span>
                </header>
                <p className="text-sm text-purple-900 whitespace-pre-wrap leading-relaxed">{data.script}</p>
              </article>
            )}
          </div>
          <Live2DPanel events={data?.events} statusLabel={data ? PERIOD_LABELS[data.period] : undefined} />
        </div>
      </div>
    </section>
  );
};

export default RitualPanel;
