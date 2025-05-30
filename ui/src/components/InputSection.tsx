import React, { useState, useRef } from 'react';
import { Mic, Send } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

const InputSection: React.FC = () => {
  const [message, setMessage] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { addMessage, setCharacterEmotion } = useChatContext();

  const handleSendMessage = () => {
    if (message.trim()) {
      addMessage(message, true);
      
      // Simulate AI "thinking" by changing character emotion
      setCharacterEmotion('thinking');
      
      // Simulate AI response after a delay
      setTimeout(() => {
        // Generate a simple response based on the message
        let response = "I'm not sure how to respond to that.";
        let emotion = 'happy';
        
        if (message.toLowerCase().includes('hello') || message.toLowerCase().includes('hi')) {
          response = "Hello there! How can I help you today?";
          emotion = 'happy';
        } else if (message.toLowerCase().includes('how are you')) {
          response = "I'm doing great, thank you for asking! How about you?";
          emotion = 'happy';
        } else if (message.toLowerCase().includes('sad') || message.toLowerCase().includes('unhappy')) {
          response = "I'm sorry to hear that. Would you like to talk about it?";
          emotion = 'sad';
        } else if (message.includes('?')) {
          response = "That's an interesting question! Let me think about it...";
          emotion = 'thinking';
        } else if (message.toLowerCase().includes('wow') || message.toLowerCase().includes('amazing')) {
          response = "I know, right? Pretty cool!";
          emotion = 'surprised';
        }
        
        addMessage(response, false);
        setCharacterEmotion(emotion);
      }, 1000);
      
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const toggleVoiceRecording = () => {
    // In a real app, this would use the Web Speech API
    setIsRecording(!isRecording);
    
    if (!isRecording) {
      // Simulate recording starting
      setTimeout(() => {
        setIsRecording(false);
        setMessage("I'm speaking through the microphone now");
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }, 3000);
    }
  };

  return (
    <div className="w-full mt-4 px-2">
      <div className="relative flex items-center">
        <button
          onClick={toggleVoiceRecording}
          className={`absolute left-3 p-2 rounded-full transition-all ${
            isRecording 
              ? 'bg-red-500 text-white animate-pulse' 
              : 'bg-purple-100 text-purple-600 hover:bg-purple-200'
          }`}
          aria-label={isRecording ? "Stop recording" : "Start voice recording"}
        >
          <Mic size={20} />
        </button>
        
        <input
          ref={inputRef}
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRecording ? "Listening..." : "Type a message..."}
          className="w-full py-3 pl-12 pr-12 bg-white border border-purple-200 rounded-full focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-transparent placeholder-purple-300"
          disabled={isRecording}
        />
        
        <button
          onClick={handleSendMessage}
          disabled={!message.trim() && !isRecording}
          className={`absolute right-3 p-2 rounded-full transition-colors ${
            message.trim() 
              ? 'bg-pink-500 text-white hover:bg-pink-600' 
              : 'bg-gray-200 text-gray-400'
          }`}
          aria-label="Send message"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default InputSection;