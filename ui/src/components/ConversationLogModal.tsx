import React from 'react';
import { X, Clock, MessageSquare, ThumbsUp, Trash2 } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

interface ConversationLogModalProps {
  onClose: () => void;
}

const formatDate = (value: string) => {
  try {
    return new Intl.DateTimeFormat('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch (error) {
    return value;
  }
};

const ConversationLogModal: React.FC<ConversationLogModalProps> = ({ onClose }) => {
  const { messages, resetConversation } = useChatContext();

  const totalMessages = messages.length;
  const userMessages = messages.filter(message => message.sender === 'user').length;
  const assistantMessages = totalMessages - userMessages;
  const positiveResponses = messages.filter(
    message => message.sender === 'assistant' && (message.emotion === 'happy' || message.emotion === 'surprised'),
  ).length;
  const positivityRate = totalMessages === 0 ? 0 : Math.round((positiveResponses / Math.max(assistantMessages, 1)) * 100);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-white rounded-xl p-6 max-w-4xl w-full mx-4 shadow-lg max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-purple-800">会話ログ</h2>
          <div className="flex gap-2">
            <button
              onClick={resetConversation}
              className="text-red-400 hover:text-red-600 transition-colors p-2 rounded-full hover:bg-red-50"
              aria-label="Clear conversation"
            >
              <Trash2 size={20} />
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
              aria-label="Close log"
            >
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-purple-50 p-4 rounded-lg flex items-center gap-3">
            <MessageSquare className="text-purple-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-purple-700">総メッセージ数</h3>
              <p className="text-2xl font-bold text-purple-900">{totalMessages}</p>
            </div>
          </div>
          <div className="bg-pink-50 p-4 rounded-lg flex items-center gap-3">
            <Clock className="text-pink-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-pink-700">ユーザー発言</h3>
              <p className="text-2xl font-bold text-pink-900">{userMessages}</p>
            </div>
          </div>
          <div className="bg-purple-50 p-4 rounded-lg flex items-center gap-3">
            <ThumbsUp className="text-purple-600" size={24} />
            <div>
              <h3 className="text-sm font-medium text-purple-700">ポジティブ率</h3>
              <p className="text-2xl font-bold text-purple-900">{positivityRate}%</p>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="space-y-4">
            {messages.map(message => (
              <div
                key={message.id}
                className={
                  'p-4 rounded-lg ' +
                  (message.sender === 'user'
                    ? 'bg-purple-50 border-l-4 border-purple-400'
                    : 'bg-pink-50 border-l-4 border-pink-400')
                }
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-medium text-sm">{message.sender === 'user' ? 'ユーザー' : 'AI'}</span>
                  <span className="text-xs text-gray-500">{formatDate(message.timestamp)}</span>
                </div>
                <p className="text-gray-800 whitespace-pre-line">{message.text}</p>
                {message.sender === 'assistant' && message.emotion && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs px-2 py-1 rounded-full bg-pink-100 text-pink-700">
                      感情: {message.emotion}
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
