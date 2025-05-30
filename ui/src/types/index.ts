// Message types
export interface Message {
    id: string;
    text: string;
    isUser: boolean;
    timestamp: Date;
  }
  
  // Character emotion types
  export type CharacterEmotion = 'happy' | 'thinking' | 'surprised' | 'sad';
  
  // Settings types
  export interface Settings {
    voiceEnabled: boolean;
    voiceVolume: number;
    characterModel: string;
    themeColor: string;
  }