import React, { useMemo } from 'react';
import { useChatContext } from '../context/ChatContext';

const EXPRESSION_IMAGES: Record<string, string> = {
  happy: '/characters/expressions/happy.png',
  surprised: '/characters/expressions/surprised.png',
  sad: '/characters/expressions/sad.png',
  angry: '/characters/expressions/angry.png',
  neutral: '/characters/expressions/neutral.png',
};

const Character: React.FC = () => {
  const { characterEmotion } = useChatContext();

  const resolvedEmotion = useMemo(() => {
    if (!characterEmotion) {
      return 'neutral';
    }
    if (EXPRESSION_IMAGES[characterEmotion]) {
      return characterEmotion;
    }
    if (characterEmotion === 'thinking') {
      return 'neutral';
    }
    return 'neutral';
  }, [characterEmotion]);

  const expressionSrc = EXPRESSION_IMAGES[resolvedEmotion];

  return (
    <div className="relative w-full flex justify-center my-4">
      <div className="relative w-80 h-80 animate-float">
        <div className="absolute inset-0 bg-gradient-to-b from-pink-100 to-purple-100 rounded-full opacity-30 animate-pulse-slow" />
        <div className="absolute inset-4 overflow-hidden rounded-full border-4 border-white shadow-lg">
          <img
            src={expressionSrc}
            alt={`RecoMate ${resolvedEmotion}`}
            className="w-full h-full object-contain select-none"
            draggable={false}
          />
        </div>
        <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 bg-white/90 px-4 py-2 rounded-full shadow-md text-sm text-purple-700">
          現在の感情: {characterEmotion}
        </div>
      </div>
    </div>
  );
};

export default Character;
