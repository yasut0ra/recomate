import React from 'react';
import { useChatContext } from '../context/ChatContext';

const Character: React.FC = () => {
  const { characterEmotion, characterModel } = useChatContext();
  
  const getCharacterImage = () => {
    const characterType = characterModel === 'anime-girl' ? 'Girl' : 'Boy';
    
    switch (characterEmotion) {
      case 'happy':
        return `https://images.pexels.com/photos/7299518/pexels-photo-7299518.jpeg?auto=compress&cs=tinysrgb&w=600`;
      case 'thinking':
        return `https://images.pexels.com/photos/7299600/pexels-photo-7299600.jpeg?auto=compress&cs=tinysrgb&w=600`;
      case 'surprised':
        return `https://images.pexels.com/photos/7299605/pexels-photo-7299605.jpeg?auto=compress&cs=tinysrgb&w=600`;
      case 'sad':
        return `https://images.pexels.com/photos/7299668/pexels-photo-7299668.jpeg?auto=compress&cs=tinysrgb&w=600`;
      default:
        return `https://images.pexels.com/photos/7299518/pexels-photo-7299518.jpeg?auto=compress&cs=tinysrgb&w=600`;
    }
  };

  return (
    <div className="relative w-full flex justify-center my-4">
      <div className="relative w-80 h-80 animate-float">
        <div className="absolute inset-0 bg-gradient-to-b from-pink-100 to-purple-100 rounded-full opacity-30 animate-pulse-slow"></div>
        <div className="absolute inset-4 overflow-hidden rounded-full border-4 border-white shadow-lg">
          <img 
            src={getCharacterImage()} 
            alt="AI Character" 
            className="w-full h-full object-cover"
          />
        </div>
      </div>
    </div>
  );
};

export default Character;