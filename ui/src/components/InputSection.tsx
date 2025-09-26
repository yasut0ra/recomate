import React, { useState, useRef } from 'react';
import { Mic, Send } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

const InputSection: React.FC = () => {
  const [message, setMessage] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { sendMessage, isProcessing } = useChatContext();

  const handleSendMessage = async () => {
    if (!message.trim()) {
      return;
    }
    const currentMessage = message;
    setMessage('');
    try {
      await sendMessage(currentMessage);
    } catch (error) {
      console.error('Failed to send message', error);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSendMessage();
    }
  };

  const toggleVoiceRecording = () => {
    setIsRecording(previous => !previous);

    if (!isRecording) {
      setTimeout(() => {
        setIsRecording(false);
        setMessage("I'm speaking through the microphone now");
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }, 3000);
    }
  };

  const disableInput = isProcessing || isRecording;

  return (
    <div className="w-full mt-4 px-2">
      <div className="relative flex items-center">
        <button
          onClick={toggleVoiceRecording}
          className={
            'absolute left-3 p-2 rounded-full transition-all ' +
            (isRecording
              ? 'bg-red-500 text-white animate-pulse'
              : 'bg-purple-100 text-purple-600 hover:bg-purple-200')
          }
          aria-label={isRecording ? 'Stop recording' : 'Start voice recording'}
          disabled={isProcessing}
        >
          <Mic size={20} />
        </button>

        <input
          ref={inputRef}
          type="text"
          value={message}
          onChange={event => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isRecording ? 'Listening...' : 'Type a message...'}
          className="w-full py-3 pl-12 pr-12 bg-white border border-purple-200 rounded-full focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-transparent placeholder-purple-300"
          disabled={disableInput}
        />

        <button
          onClick={handleSendMessage}
          disabled={disableInput || !message.trim()}
          className={
            'absolute right-3 p-2 rounded-full transition-colors ' +
            (message.trim() && !disableInput
              ? 'bg-pink-500 text-white hover:bg-pink-600'
              : 'bg-gray-200 text-gray-400')
          }
          aria-label="Send message"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default InputSection;
