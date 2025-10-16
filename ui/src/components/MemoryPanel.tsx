import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { commitMemory, searchMemories } from '../api/memoryApi';
import type { MemoryRecord } from '../types';

const DEFAULT_LIMIT = 10;

const MemoryPanel: React.FC = () => {
  const [userId, setUserId] = useState<string>('');
  const [query, setQuery] = useState<string>('');
  const [limit, setLimit] = useState<number>(DEFAULT_LIMIT);
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [episodeId, setEpisodeId] = useState<string>('');
  const [summary, setSummary] = useState<string>('');
  const [keywords, setKeywords] = useState<string>('');
  const [pinned, setPinned] = useState<boolean>(false);
  const [isCommitting, setIsCommitting] = useState<boolean>(false);
  const [commitMessage, setCommitMessage] = useState<string | null>(null);

  const effectiveLimit = useMemo(() => {
    if (!Number.isFinite(limit) || limit <= 0) {
      return DEFAULT_LIMIT;
    }
    return Math.min(limit, 100);
  }, [limit]);

  const executeSearch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const results = await searchMemories({
        query: query.trim() || undefined,
        userId: userId.trim() || undefined,
        limit: effectiveLimit,
      });
      setMemories(results);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'メモリ検索に失敗しました';
      setError(message);
      setMemories([]);
    } finally {
      setIsLoading(false);
    }
  }, [query, userId, effectiveLimit]);

  useEffect(() => {
    executeSearch().catch(() => undefined);
  }, [executeSearch]);

  const handleCommit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (!episodeId.trim()) {
        setCommitMessage('Episode ID を入力してください');
        return;
      }
      setIsCommitting(true);
      setCommitMessage(null);
      try {
        await commitMemory({
          episode_id: episodeId.trim(),
          summary: summary.trim() || undefined,
          keywords: keywords
            .split(',')
            .map((word) => word.trim())
            .filter(Boolean),
          pinned,
        });
        setCommitMessage('メモリを保存しました');
        setEpisodeId('');
        setSummary('');
        setKeywords('');
        setPinned(false);
        await executeSearch();
      } catch (err) {
        const message = err instanceof Error ? err.message : 'メモリ保存に失敗しました';
        setCommitMessage(message);
      } finally {
        setIsCommitting(false);
      }
    },
    [episodeId, summary, keywords, pinned, executeSearch],
  );

  return (
    <section className="w-full max-w-3xl mx-auto mt-8">
      <div className="bg-white border border-emerald-100 shadow-md rounded-xl p-5 space-y-6">
        <header className="space-y-1">
          <h2 className="text-xl font-semibold text-emerald-700">メモリ透明パネル</h2>
          <p className="text-sm text-emerald-500">
            バックエンドの /api/memory/* エンドポイントと連携し、保存済みのメモリを閲覧/登録できます。
          </p>
        </header>

        <form
          onSubmit={handleCommit}
          className="bg-emerald-50 border border-emerald-100 rounded-lg p-4 space-y-3"
        >
          <h3 className="text-sm font-semibold text-emerald-700">メモリ書き戻し</h3>
          <div className="grid md:grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-semibold text-emerald-600">Episode ID</span>
              <input
                type="text"
                value={episodeId}
                onChange={(event) => setEpisodeId(event.target.value)}
                placeholder="22222222-2222-2222-2222-222222222222"
                className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-emerald-600">キーワード（カンマ区切り）</span>
              <input
                type="text"
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
                placeholder="映画, 感想"
                className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
            </label>
            <label className="block md:col-span-2">
              <span className="text-xs font-semibold text-emerald-600">サマリー</span>
              <textarea
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                placeholder="エピソードのサマリー（省略可、未入力の場合は自動生成）"
                rows={3}
                className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-emerald-700">
              <input
                type="checkbox"
                checked={pinned}
                onChange={(event) => setPinned(event.target.checked)}
                className="rounded border-emerald-300 text-emerald-600 focus:ring-emerald-400"
              />
              ピン留めする
            </label>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={isCommitting}
              className="inline-flex items-center justify-center rounded-md bg-emerald-600 text-white text-sm font-medium px-4 py-2 shadow hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:opacity-60"
            >
              {isCommitting ? '保存中...' : 'メモリを保存'}
            </button>
            {commitMessage && <p className="text-sm text-emerald-600">{commitMessage}</p>}
          </div>
        </form>

        <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-4 space-y-3">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
            <div className="grid md:grid-cols-3 gap-3 w-full md:w-auto">
              <label className="block">
                <span className="text-xs font-semibold text-emerald-600">ユーザー ID</span>
                <input
                  type="text"
                  value={userId}
                  onChange={(event) => setUserId(event.target.value)}
                  placeholder="11111111-1111-1111-1111-111111111111"
                  className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </label>
              <label className="block">
                <span className="text-xs font-semibold text-emerald-600">キーワード検索</span>
                <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="映画"
                  className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </label>
              <label className="block">
                <span className="text-xs font-semibold text-emerald-600">最大取得数</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value))}
                  className="mt-1 w-full rounded-md border border-emerald-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={() => executeSearch().catch(() => undefined)}
              className="inline-flex items-center justify-center rounded-md bg-emerald-500 text-white text-sm font-medium px-4 py-2 shadow hover:bg-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-400 self-start md:self-auto"
            >
              再検索
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {isLoading && <p className="text-sm text-emerald-500">読み込み中...</p>}
          <div className="grid gap-3">
            {memories.map((memory) => (
              <article
                key={memory.id}
                className="bg-white border border-emerald-100 rounded-lg p-4 shadow-sm space-y-2"
              >
                <header className="flex items-center justify-between">
                  <div className="text-xs text-emerald-500">
                    <span className="font-semibold mr-2">Memory ID</span>
                    <span className="font-mono">{memory.id}</span>
                  </div>
                  <span className="text-xs px-3 py-1 rounded-full border border-emerald-200 text-emerald-600 bg-emerald-50">
                    {memory.pinned ? 'Pinned' : 'Normal'}
                  </span>
                </header>
                <p className="text-sm text-emerald-900 whitespace-pre-wrap leading-relaxed">{memory.summary_md}</p>
                {memory.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-2 text-xs text-emerald-600">
                    {memory.keywords.map((keyword) => (
                      <span
                        key={keyword}
                        className="inline-flex items-center px-2 py-1 rounded-full bg-emerald-100 border border-emerald-200"
                      >
                        #{keyword}
                      </span>
                    ))}
                  </div>
                )}
                <footer className="text-xs text-emerald-500 space-x-4">
                  <span>作成: {new Date(memory.created_at).toLocaleString()}</span>
                  {memory.last_ref && <span>最終参照: {new Date(memory.last_ref).toLocaleString()}</span>}
                </footer>
              </article>
            ))}
            {!isLoading && memories.length === 0 && (
              <p className="text-sm text-emerald-500">表示できるメモリがありません。</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export default MemoryPanel;
