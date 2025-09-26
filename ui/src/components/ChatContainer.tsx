import React, { useEffect, useRef } from 'react';
import { useChatContext } from '../context/ChatContext';
import ChatBubble from './ChatBubble';

const ChatContainer: React.FC = () => {
  const { messages, isProcessing, error } = useChatContext();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div ref={scrollRef} className="w-full max-h-[30vh] overflow-y-auto mb-4 custom-scrollbar px-2">
      {error && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          エラー: {error}
        </div>
      )}
      <div className="space-y-4 py-2">
        {messages.length === 0 ? (
          <div className="text-center text-purple-300 italic py-4">Start a conversation...</div>
        ) : (
          messages.map(message => <ChatBubble key={message.id} message={message} />)
        )}
        {isProcessing && (
          <div className="flex justify-start animate-pulse text-sm text-purple-400">RecoMate is thinking...</div>
        )}
      </div>
    </div>
  );
};

export default ChatContainer;
