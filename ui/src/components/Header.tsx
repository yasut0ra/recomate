import React, { useState } from 'react';
import { Settings, BarChart2, History } from 'lucide-react';
import SettingsModal from './SettingsModal';
import StatisticsModal from './StatisticsModal';
import ConversationLogModal from './ConversationLogModal';

const Header: React.FC = () => {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isStatsOpen, setIsStatsOpen] = useState(false);
  const [isLogOpen, setIsLogOpen] = useState(false);

  return (
    <header className="w-full py-4 px-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-600 to-pink-500 bg-clip-text text-transparent">
          RecoMate
        </h1>
        <div className="flex gap-2">
          <button 
            className="text-purple-400 hover:text-purple-600 transition-colors p-2 rounded-full hover:bg-purple-100"
            onClick={() => setIsLogOpen(true)}
            aria-label="Conversation Log"
          >
            <History size={24} />
          </button>
          <button 
            className="text-purple-400 hover:text-purple-600 transition-colors p-2 rounded-full hover:bg-purple-100"
            onClick={() => setIsStatsOpen(true)}
            aria-label="Statistics"
          >
            <BarChart2 size={24} />
          </button>
          <button 
            className="text-purple-400 hover:text-purple-600 transition-colors p-2 rounded-full hover:bg-purple-100"
            onClick={() => setIsSettingsOpen(true)}
            aria-label="Settings"
          >
            <Settings size={24} />
          </button>
        </div>
      </div>

      {isSettingsOpen && (
        <SettingsModal onClose={() => setIsSettingsOpen(false)} />
      )}
      {isStatsOpen && (
        <StatisticsModal onClose={() => setIsStatsOpen(false)} />
      )}
      {isLogOpen && (
        <ConversationLogModal onClose={() => setIsLogOpen(false)} />
      )}
    </header>
  );
};

export default Header;