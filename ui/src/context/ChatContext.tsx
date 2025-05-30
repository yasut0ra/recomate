import React, { createContext, useContext, useState } from 'react';
import type { ReactNode } from 'react';

// Types
type CharacterEmotion = 'happy' | 'thinking' | 'surprised' | 'sad';
type CharacterModel = 'anime-girl' | 'anime-boy';

interface Message {
  text: string;
  isUser: boolean;
}

interface ChatContextType {
  messages: Message[];
  addMessage: (text: string, isUser: boolean) => void;
  characterEmotion: CharacterEmotion;
  setCharacterEmotion: (emotion: CharacterEmotion) => void;
  characterModel: CharacterModel;
  setCharacterModel: (model: CharacterModel) => void;
}

// Create context
const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Context provider
export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [messages, setMessages] = useState<Message[]>([
    { text: "Hello! I'm your AI assistant. How can I help you today?", isUser: false }
  ]);
  const [characterEmotion, setCharacterEmotion] = useState<CharacterEmotion>('happy');
  const [characterModel, setCharacterModel] = useState<CharacterModel>('anime-girl');

  const addMessage = (text: string, isUser: boolean) => {
    setMessages(prev => [...prev, { text, isUser }]);
  };

  return (
    <ChatContext.Provider 
      value={{ 
        messages, 
        addMessage, 
        characterEmotion, 
        setCharacterEmotion,
        characterModel,
        setCharacterModel
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

// Custom hook to use the chat context
export const useChatContext = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
};