import React from 'react';
import { X, Clock, MessageSquare, ThumbsUp } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

interface ConversationLogModalProps {
  onClose: () => void;
}

const ConversationLogModal: React.FC<ConversationLogModalProps> = ({ onClose }) => {
  const { messages } = useChatContext();

  const formatDate = (date: Date) => {
    return new Intl.DateTimeFormat('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-white rounded-xl p-6 max-w-4xl w-full mx-4 shadow-lg max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-purple-800">会話ログ</h2>
          <button 
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close log"
          >
            <X size={24} />
          </button>
        </div>

        {/* Statistics Summary */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-purple-50 p-4 rounded-lg flex items-center gap-3">
            <MessageSquare className="text-purple-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-purple-700">総メッセージ数</h3>
              <p className="text-2xl font-bold text-purple-900">{messages.length}</p>
            </div>
          </div>
          <div className="bg-pink-50 p-4 rounded-lg flex items-center gap-3">
            <Clock className="text-pink-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-pink-700">平均応答時間</h3>
              <p className="text-2xl font-bold text-pink-900">2.3秒</p>
            </div>
          </div>
          <div className="bg-purple-50 p-4 rounded-lg flex items-center gap-3">
            <ThumbsUp className="text-purple-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-purple-700">ポジティブ率</h3>
              <p className="text-2xl font-bold text-purple-900">85%</p>
            </div>
          </div>
        </div>

        {/* Conversation Log */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="space-y-4">
            {messages.map((message, index) => (
              <div 
                key={index}
                className={`p-4 rounded-lg ${
                  message.isUser 
                    ? 'bg-purple-50 border-l-4 border-purple-400' 
                    : 'bg-pink-50 border-l-4 border-pink-400'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-medium text-sm">
                    {message.isUser ? 'ユーザー' : 'AI'}
                  </span>
                  <span className="text-xs text-gray-500">
                    {formatDate(new Date())}
                  </span>
                </div>
                <p className="text-gray-800">{message.text}</p>
                {!message.isUser && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs px-2 py-1 rounded-full bg-pink-100 text-pink-700">
                      感情: 幸せ
                    </span>
                    <span className="text-xs px-2 py-1 rounded-full bg-purple-100 text-purple-700">
                      信頼度: 95%
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConversationLogModal;