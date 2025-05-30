import React, { useEffect, useRef } from 'react';
import { useChatContext } from '../context/ChatContext';
import ChatBubble from './ChatBubble';

const ChatContainer: React.FC = () => {
  const { messages } = useChatContext();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div 
      ref={scrollRef}
      className="w-full max-h-[30vh] overflow-y-auto mb-4 custom-scrollbar px-2"
    >
      <div className="space-y-4 py-2">
        {messages.length === 0 ? (
          <div className="text-center text-purple-300 italic py-4">
            Start a conversation...
          </div>
        ) : (
          messages.map((message, index) => (
            <ChatBubble 
              key={index} 
              message={message.text} 
              isUser={message.isUser} 
            />
          ))
        )}
      </div>
    </div>
  );
};

export default ChatContainer;