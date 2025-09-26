import React from 'react';
import { useChatContext } from '../context/ChatContext';

const emotionImages: Record<string, string> = {
  happy: 'https://images.pexels.com/photos/7299518/pexels-photo-7299518.jpeg?auto=compress&cs=tinysrgb&w=600',
  thinking: 'https://images.pexels.com/photos/7299600/pexels-photo-7299600.jpeg?auto=compress&cs=tinysrgb&w=600',
  surprised: 'https://images.pexels.com/photos/7299605/pexels-photo-7299605.jpeg?auto=compress&cs=tinysrgb&w=600',
  sad: 'https://images.pexels.com/photos/7299668/pexels-photo-7299668.jpeg?auto=compress&cs=tinysrgb&w=600',
  neutral: 'https://images.pexels.com/photos/7299600/pexels-photo-7299600.jpeg?auto=compress&cs=tinysrgb&w=600',
};

const Character: React.FC = () => {
  const { characterEmotion } = useChatContext();
  const imageUrl = emotionImages[characterEmotion] ?? emotionImages.thinking;

  return (
    <div className="relative w-full flex justify-center my-4">
      <div className="relative w-80 h-80 animate-float">
        <div className="absolute inset-0 bg-gradient-to-b from-pink-100 to-purple-100 rounded-full opacity-30 animate-pulse-slow"></div>
        <div className="absolute inset-4 overflow-hidden rounded-full border-4 border-white shadow-lg">
          <img src={imageUrl} alt="AI Character" className="w-full h-full object-cover" />
        </div>
        <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 bg-white/90 px-4 py-2 rounded-full shadow-md text-sm text-purple-700">
          現在の感情: {characterEmotion}
        </div>
      </div>
    </div>
  );
};

export default Character;
