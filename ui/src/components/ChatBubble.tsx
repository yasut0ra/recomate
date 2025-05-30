import React from 'react';

interface ChatBubbleProps {
  message: string;
  isUser: boolean;
}

const ChatBubble: React.FC<ChatBubbleProps> = ({ message, isUser }) => {
  return (
    <div 
      className={`flex animate-fade-in ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div 
        className={`max-w-[80%] p-3 rounded-xl shadow-sm ${
          isUser 
            ? 'bg-purple-100 text-purple-900 speech-bubble-user' 
            : 'bg-pink-100 text-pink-900 speech-bubble-ai'
        }`}
      >
        <p className="text-sm sm:text-base">{message}</p>
      </div>
    </div>
  );
};

export default ChatBubble;