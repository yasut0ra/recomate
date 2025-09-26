import React from 'react';
import type { ChatMessage } from '../types';

interface ChatBubbleProps {
  message: ChatMessage;
}

const ChatBubble: React.FC<ChatBubbleProps> = ({ message }) => {
  const isUser = message.sender === 'user';
  const formattedTime = new Date(message.timestamp).toLocaleTimeString('ja-JP', {
    hour: '2-digit',
    minute: '2-digit',
  });

  const containerClass = 'flex animate-fade-in ' + (isUser ? 'justify-end' : 'justify-start');
  const bubbleClass =
    'max-w-[80%] p-3 rounded-xl shadow-sm ' +
    (isUser
      ? 'bg-purple-100 text-purple-900 speech-bubble-user'
      : 'bg-pink-100 text-pink-900 speech-bubble-ai');

  return (
    <div className={containerClass}>
      <div className={bubbleClass}>
        <p className="text-xs text-purple-400 mb-1">
          {isUser ? 'あなた' : 'RecoMate'} ・ {formattedTime}
        </p>
        <p className="text-sm sm:text-base whitespace-pre-line">{message.text}</p>
        {!isUser && message.emotion && (
          <span className="mt-2 inline-block text-xs px-2 py-1 rounded-full bg-white/40 text-purple-700">
            感情: {message.emotion}
          </span>
        )}
      </div>
    </div>
  );
};

export default ChatBubble;
