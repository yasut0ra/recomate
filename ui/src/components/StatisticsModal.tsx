import React from 'react';
import { X } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, BarChart, Bar, ResponsiveContainer } from 'recharts';

interface StatisticsModalProps {
  onClose: () => void;
}

const StatisticsModal: React.FC<StatisticsModalProps> = ({ onClose }) => {
  // Sample data - in a real app, this would come from your bandit algorithm
  const rewardData = [
    { name: 'Day 1', reward: 0.4, visits: 15 },
    { name: 'Day 2', reward: 0.5, visits: 22 },
    { name: 'Day 3', reward: 0.6, visits: 18 },
    { name: 'Day 4', reward: 0.55, visits: 25 },
    { name: 'Day 5', reward: 0.7, visits: 30 },
  ];

  const armData = [
    { name: 'Arm 1', pulls: 45, avgReward: 0.6 },
    { name: 'Arm 2', pulls: 35, avgReward: 0.5 },
    { name: 'Arm 3', pulls: 30, avgReward: 0.4 },
  ];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-start justify-center z-50 animate-fade-in overflow-y-auto p-4">
      <div className="bg-white rounded-xl p-6 max-w-4xl w-full mx-auto my-8 shadow-lg">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-purple-800">Recommendation Statistics</h2>
          <button 
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close statistics"
          >
            <X size={24} />
          </button>
        </div>

        <div className="space-y-8">
          {/* Cumulative Reward Over Time */}
          <div className="bg-purple-50 p-4 rounded-lg">
            <h3 className="text-lg font-semibold text-purple-700 mb-4">Reward Trend</h3>
            <div className="w-full h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rewardData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="reward" stroke="#8B5CF6" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Arm Performance */}
          <div className="bg-pink-50 p-4 rounded-lg">
            <h3 className="text-lg font-semibold text-pink-700 mb-4">Arm Performance</h3>
            <div className="w-full h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={armData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="pulls" fill="#EC4899" />
                  <Bar dataKey="avgReward" fill="#8B5CF6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Summary Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-purple-700">Total Interactions</h4>
              <p className="text-2xl font-bold text-purple-900">110</p>
            </div>
            <div className="bg-pink-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-pink-700">Average Reward</h4>
              <p className="text-2xl font-bold text-pink-900">0.55</p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <h4 className="text-sm font-medium text-purple-700">Best Performing Arm</h4>
              <p className="text-2xl font-bold text-purple-900">Arm 1</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatisticsModal;