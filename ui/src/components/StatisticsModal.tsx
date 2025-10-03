import React, { useEffect, useMemo } from 'react';
import { X } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  ResponsiveContainer,
} from 'recharts';
import { useChatContext } from '../context/ChatContext';

interface StatisticsModalProps {
  onClose: () => void;
}

const emotionScore = (emotion?: string) => {
  if (!emotion) {
    return 0.5;
  }
  if (emotion === 'happy' || emotion === 'surprised') {
    return 0.9;
  }
  if (emotion === 'sad') {
    return 0.2;
  }
  return 0.6;
};

const StatisticsModal: React.FC<StatisticsModalProps> = ({ onClose }) => {
  const { messages, topicStats, isTopicStatsLoading, refreshTopicStats } = useChatContext();

  useEffect(() => {
    void refreshTopicStats();
  }, [refreshTopicStats]);

  const assistantMessages = useMemo(
    () => messages.filter(message => message.sender === 'assistant'),
    [messages],
  );

  const rewardTrend = assistantMessages.map((message, index) => ({
    name: '応答 ' + (index + 1),
    reward: Number(emotionScore(message.emotion).toFixed(2)),
  }));

  const emotionCounts = assistantMessages.reduce<Record<string, number>>((accumulator, message) => {
    const key = message.emotion || 'unknown';
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});

  const emotionData = Object.keys(emotionCounts).map(key => ({
    emotion: key,
    count: emotionCounts[key],
  }));

  const averageScore = assistantMessages.length === 0
    ? 0
    : assistantMessages.reduce((accumulator, message) => accumulator + emotionScore(message.emotion), 0) /
      assistantMessages.length;

  const lastEmotion = assistantMessages.length === 0
    ? '---'
    : assistantMessages[assistantMessages.length - 1].emotion || 'unknown';

  const topicData = useMemo(() => {
    if (!topicStats) {
      return [];
    }
    return Object.entries(topicStats.topics).map(([topic, metrics]) => ({
      topic,
      count: metrics.count,
      frequency: Number(metrics.frequency),
      value: Number(metrics.value.toFixed(2)),
      subtopics: topicStats.subtopics[topic] ?? [],
    }));
  }, [topicStats]);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-start justify-center z-50 animate-fade-in overflow-y-auto p-4">
      <div className="bg-white rounded-xl p-6 max-w-4xl w-full mx-auto my-8 shadow-lg">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-purple-800">会話の統計</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close statistics"
          >
            <X size={24} />
          </button>
        </div>

        <div className="space-y-8">
          <div className="bg-purple-50 p-4 rounded-lg">
            <h3 className="text-lg font-semibold text-purple-700 mb-4">感情スコアの推移</h3>
            <div className="w-full h-[300px]">
              {rewardTrend.length === 0 ? (
                <div className="flex h-full items-center justify-center text-purple-300">
                  まだデータがありません
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rewardTrend} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis domain={[0, 1]} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="reward" stroke="#8B5CF6" strokeWidth={2} dot />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="bg-pink-50 p-4 rounded-lg">
            <h3 className="text-lg font-semibold text-pink-700 mb-4">感情別の回数</h3>
            <div className="w-full h-[300px]">
              {emotionData.length === 0 ? (
                <div className="flex h-full items-center justify-center text-pink-300">
                  まだデータがありません
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={emotionData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="emotion" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="count" fill="#EC4899" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-purple-700">AI応答数</h4>
              <p className="text-2xl font-bold text-purple-900">{assistantMessages.length}</p>
            </div>
            <div className="bg-pink-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-pink-700">平均感情スコア</h4>
              <p className="text-2xl font-bold text-pink-900">{averageScore.toFixed(2)}</p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-purple-700">最後の感情</h4>
              <p className="text-2xl font-bold text-purple-900">{lastEmotion}</p>
            </div>
          </div>

          <div className="bg-indigo-50 p-4 rounded-lg">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-indigo-700">トピックバンディットの統計</h3>
              <button
                type="button"
                onClick={() => {
                  void refreshTopicStats();
                }}
                disabled={isTopicStatsLoading}
                className="text-sm px-3 py-1 rounded-md border border-indigo-300 text-indigo-600 hover:bg-indigo-100 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isTopicStatsLoading ? '読み込み中...' : '再取得'}
              </button>
            </div>

            {isTopicStatsLoading ? (
              <div className="flex h-32 items-center justify-center text-indigo-300">読み込み中...</div>
            ) : topicData.length === 0 ? (
              <div className="text-sm text-indigo-300">まだトピック統計がありません</div>
            ) : (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left text-indigo-600">
                        <th className="py-2 pr-4">トピック</th>
                        <th className="py-2 pr-4">選択回数</th>
                        <th className="py-2 pr-4">頻度</th>
                        <th className="py-2 pr-4">推定価値</th>
                        <th className="py-2">サブトピック</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-indigo-100">
                      {topicData.map(item => (
                        <tr key={item.topic} className="text-indigo-900">
                          <td className="py-2 pr-4 font-medium">{item.topic}</td>
                          <td className="py-2 pr-4">{item.count}</td>
                          <td className="py-2 pr-4">{item.frequency.toFixed(2)}</td>
                          <td className="py-2 pr-4">{item.value.toFixed(2)}</td>
                          <td className="py-2">
                            {item.subtopics.length === 0 ? (
                              <span className="text-xs text-indigo-300">サブトピックなし</span>
                            ) : (
                              <div className="flex flex-wrap gap-1">
                                {item.subtopics.slice(0, 5).map(subtopic => (
                                  <span key={subtopic} className="text-xs px-2 py-1 rounded-full bg-white text-indigo-600 border border-indigo-200">
                                    {subtopic}
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-xs text-indigo-400">
                  総試行回数: {topicStats?.totalSelections ?? 0} / 特徴次元: {topicStats?.featureDim ?? 0}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatisticsModal;
