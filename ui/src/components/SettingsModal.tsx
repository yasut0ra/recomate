import React, { useState } from 'react';
import { X, Volume2, Key, User } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';

interface SettingsModalProps {
  onClose: () => void;
}

const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { characterModel, setCharacterModel } = useChatContext();
  const [voiceType, setVoiceType] = useState('default');
  const [apiKey, setApiKey] = useState('');
  const [voicevoxUrl, setVoicevoxUrl] = useState('http://localhost:50021');
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-lg max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-purple-800">Settings</h2>
          <button 
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close settings"
          >
            <X size={24} />
          </button>
        </div>
        
        <div className="space-y-6">
          {/* Character Settings */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <User size={20} className="text-purple-600" />
              <h3 className="text-lg font-semibold text-purple-700">Character Settings</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {['anime-girl', 'anime-boy'].map((model) => (
                <button
                  key={model}
                  className={`p-3 rounded-lg border-2 transition-all ${
                    characterModel === model 
                      ? 'border-purple-500 bg-purple-50' 
                      : 'border-gray-200 hover:border-purple-300'
                  }`}
                  onClick={() => setCharacterModel(model)}
                >
                  <div className="aspect-square rounded-full bg-purple-100 mb-2 flex items-center justify-center overflow-hidden">
                    <span className="text-2xl">
                      {model === 'anime-girl' ? '👧' : '👦'}
                    </span>
                  </div>
                  <p className="text-sm text-center capitalize">
                    {model.replace('-', ' ')}
                  </p>
                </button>
              ))}
            </div>
          </div>
          
          {/* Voice Settings */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Volume2 size={20} className="text-purple-600" />
              <h3 className="text-lg font-semibold text-purple-700">Voice Settings</h3>
            </div>
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">Voice Type</label>
                <select
                  value={voiceType}
                  onChange={(e) => setVoiceType(e.target.value)}
                  className="w-full rounded-lg border-gray-300 shadow-sm focus:border-purple-300 focus:ring focus:ring-purple-200 focus:ring-opacity-50"
                >
                  <option value="default">Default Browser Voice</option>
                  <option value="voicevox">VOICEVOX</option>
                </select>
              </div>

              {voiceType === 'voicevox' && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700">VOICEVOX Server URL</label>
                  <input
                    type="url"
                    value={voicevoxUrl}
                    onChange={(e) => setVoicevoxUrl(e.target.value)}
                    placeholder="http://localhost:50021"
                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-purple-300 focus:ring focus:ring-purple-200 focus:ring-opacity-50"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Volume</label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  defaultValue="80"
                  className="w-full h-2 bg-purple-200 rounded-lg appearance-none cursor-pointer accent-purple-500"
                />
              </div>

              <div className="flex items-center">
                <input
                  id="enable-voice"
                  type="checkbox"
                  className="h-4 w-4 text-purple-600 rounded border-gray-300 focus:ring-purple-500"
                  defaultChecked
                />
                <label htmlFor="enable-voice" className="ml-2 block text-sm text-gray-700">
                  Enable voice responses
                </label>
              </div>
            </div>
          </div>

          {/* API Settings */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Key size={20} className="text-purple-600" />
              <h3 className="text-lg font-semibold text-purple-700">API Settings</h3>
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Enter your API key"
                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-purple-300 focus:ring focus:ring-purple-200 focus:ring-opacity-50"
              />
              <p className="text-xs text-gray-500">Required for accessing the AI service</p>
            </div>
          </div>
          
          <div className="pt-4">
            <button
              onClick={onClose}
              className="w-full py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors"
            >
              Save Settings
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;