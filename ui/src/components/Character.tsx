import React, { useMemo } from 'react';
import { useChatContext } from '../context/ChatContext';

const CHARACTER_EXPRESSIONS: Record<string, Record<string, string>> = {
  rico: {
    happy: '/characters/rico/expressions/happy.png',
    surprised: '/characters/rico/expressions/surprised.png',
    sad: '/characters/rico/expressions/sad.png',
    angry: '/characters/rico/expressions/angry.png',
    neutral: '/characters/rico/expressions/neutral.png',
  },
  hachika: {
    happy: '/characters/hachika/expressions/happy.png',
    surprised: '/characters/hachika/expressions/surprised.png',
    sad: '/characters/hachika/expressions/sad.png',
    angry: '/characters/hachika/expressions/angry.png',
    neutral: '/characters/hachika/expressions/neutral.png',
  },
};

const FALLBACK_MODEL = 'rico';

const Character: React.FC = () => {
  const { characterEmotion, characterModel } = useChatContext();

  const activeModel = useMemo(() => {
    return CHARACTER_EXPRESSIONS[characterModel] ?? CHARACTER_EXPRESSIONS[FALLBACK_MODEL];
  }, [characterModel]);

  const expressionKey = useMemo(() => {
    if (!characterEmotion) {
      return 'neutral';
    }
    if (characterEmotion === 'thinking') {
      return 'neutral';
    }
    if (activeModel[characterEmotion]) {
      return characterEmotion;
    }
    return 'neutral';
  }, [characterEmotion, activeModel]);

  const expressionSrc = activeModel[expressionKey] ?? activeModel.neutral;

  return (
    <div className="relative w-full flex justify-center my-4">
      <div className="relative w-80 h-80 animate-float">
        <div className="absolute inset-0 bg-gradient-to-b from-pink-100 to-purple-100 rounded-full opacity-30 animate-pulse-slow" />
        <div className="absolute inset-4 overflow-hidden rounded-full border-4 border-white shadow-lg">
          <img
            src={expressionSrc}
            alt={`RecoMate ${expressionKey}`}
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
