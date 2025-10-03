import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Mic, Send } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

const SUPPORTED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/ogg;codecs=opus',
  'audio/webm',
];

const chooseMimeType = () => {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return undefined;
  }
  return SUPPORTED_MIME_TYPES.find(type => MediaRecorder.isTypeSupported(type));
};

const InputSection: React.FC = () => {
  const [message, setMessage] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const {
    sendMessage,
    isProcessing,
    transcribeAudio,
    isTranscribing,
  } = useChatContext();

  const stopStream = useCallback(() => {
    const stream = mediaStreamRef.current;
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const handleRecordingStop = useCallback(async () => {
    if (mountedRef.current) {
      setIsRecording(false);
    }
    const recorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;
    stopStream();

    if (!chunksRef.current.length) {
      return;
    }

    const blob = new Blob(chunksRef.current, { type: recorder?.mimeType || 'audio/webm' });
    chunksRef.current = [];

    try {
      const arrayBuffer = await blob.arrayBuffer();
      let audioContext = audioContextRef.current;
      if (!audioContext) {
        audioContext = new AudioContext();
        audioContextRef.current = audioContext;
      }
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
      const channelData = audioBuffer.getChannelData(0);
      const transcript = await transcribeAudio(new Float32Array(channelData), audioBuffer.sampleRate);
      if (transcript) {
        setMessage(transcript);
        inputRef.current?.focus();
      }
    } catch (error) {
      console.error('Failed to process recorded audio', error);
    }
  }, [stopStream, transcribeAudio]);

  const startRecording = useCallback(async () => {
    if (isProcessing || isTranscribing || isRecording) {
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.warn('Browser does not support audio recording');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const mimeType = chooseMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        void handleRecordingStop();
      };

      recorder.start();
      setIsRecording(true);
      setMessage('');
    } catch (error) {
      console.error('Failed to access the microphone', error);
      stopStream();
    }
  }, [handleRecordingStop, isProcessing, isRecording, isTranscribing, stopStream]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      stopStream();
      setIsRecording(false);
    }
  }, [stopStream]);

  const toggleVoiceRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      void startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  const handleSendMessage = useCallback(async () => {
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
  }, [message, sendMessage]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSendMessage();
    }
  }, [handleSendMessage]);

  useEffect(() => () => {
    mountedRef.current = false;
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch (error) {
        console.warn('Failed to stop recorder during cleanup', error);
      }
    }
    stopStream();
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
  }, [stopStream]);

  const disableInput = isProcessing || isRecording || isTranscribing;

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
          disabled={isProcessing || isTranscribing}
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
      {(isRecording || isTranscribing) && (
        <div className="mt-2 text-xs text-purple-400">
          {isRecording ? '録音中...' : '音声を解析しています...'}
        </div>
      )}
    </div>
  );
};

export default InputSection;
