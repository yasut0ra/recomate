import React from 'react';
import type { RitualEvent } from '../types';

const LABEL_MAP: Record<string, string> = {
  face: '表情',
  eye: '目',
  mouth: '口',
  gesture: 'ジェスチャー',
};

interface Live2DPanelProps {
  events?: RitualEvent[];
  statusLabel?: string;
}

const Live2DPanel: React.FC<Live2DPanelProps> = ({ events, statusLabel }) => {
  const hasEvents = !!events && events.length > 0;

  return (
    <section className="mt-4 w-full bg-white/80 border border-purple-100 rounded-lg shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-purple-700">Live2D イベント</h3>
        <span className="text-xs text-purple-500 bg-purple-50 border border-purple-200 rounded-full px-3 py-1">
          {statusLabel ?? (hasEvents ? '最新スクリプトに同期済み' : 'イベント未取得')}
        </span>
      </div>
      {hasEvents ? (
        <ul className="space-y-2">
          {events!.map((event, index) => (
            <li
              key={event.event + '-' + index}
              className="flex items-center justify-between bg-purple-50 border border-purple-100 rounded-md px-3 py-2"
            >
              <div className="text-sm">
                <span className="font-medium text-purple-700">
                  {LABEL_MAP[event.event] ?? event.event}
                </span>
                <span className="mx-2 text-purple-300">→</span>
                <span className="text-purple-900">{event.value}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-purple-500">イベントが見つかりませんでした。</p>
      )}
    </section>
  );
};

export default Live2DPanel;
