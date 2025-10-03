import React, { useState, useEffect } from 'react';
import { X, Volume2, Key, User } from 'lucide-react';
import { useChatContext } from '../context/ChatContext';
import type { CharacterModel } from '../types';

interface SettingsModalProps {
  onClose: () => void;
}

const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const {
    characterModel,
    setCharacterModel,
    apiKey,
    setApiKey,
    voiceEnabled,
    setVoiceEnabled,
  } = useChatContext();
  const [voiceType, setVoiceType] = useState('default');
  const [apiKeyInput, setApiKeyInput] = useState(apiKey ?? '');
  const [voicevoxUrl, setVoicevoxUrl] = useState('http://localhost:50021');
  const characterOptions: CharacterModel[] = ['rico', 'hachika'];

  useEffect(() => {
    setApiKeyInput(apiKey ?? '');
  }, [apiKey]);

  const handleSave = () => {
    const trimmed = apiKeyInput.trim();
    setApiKey(trimmed.length > 0 ? trimmed : null);
    onClose();
  };

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
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <User size={20} className="text-purple-600" />
              <h3 className="text-lg font-semibold text-purple-700">Character Settings</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {characterOptions.map(model => {
                const isActive = characterModel === model;
                const buttonClass =
                  'p-3 rounded-lg border-2 transition-all ' +
                  (isActive
                    ? 'border-purple-500 bg-purple-50'
                    : 'border-gray-200 hover:border-purple-300');
                return (
                  <button
                    key={model}
                    className={buttonClass}
                    onClick={() => setCharacterModel(model)}
                  >
                    <div className="aspect-square rounded-full bg-purple-100 mb-2 flex items-center justify-center overflow-hidden">
                      <span className="text-2xl">
                        {model === 'rico' ? '🌸' : '💙'}
                      </span>
                    </div>
                    <p className="text-sm text-center capitalize">
                      {model}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

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
                  onChange={event => setVoiceType(event.target.value)}
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
                    onChange={event => setVoicevoxUrl(event.target.value)}
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
                  checked={voiceEnabled}
                  onChange={event => setVoiceEnabled(event.target.checked)}
                />
                <label htmlFor="enable-voice" className="ml-2 block text-sm text-gray-700">
                  Enable voice responses
                </label>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Key size={20} className="text-purple-600" />
              <h3 className="text-lg font-semibold text-purple-700">API Settings</h3>
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">OpenAI API Key</label>
              <input
                type="password"
                value={apiKeyInput}
                onChange={event => setApiKeyInput(event.target.value)}
                placeholder="sk-..."
                className="w-full rounded-lg border-gray-300 shadow-sm focus:border-purple-300 focus:ring focus:ring-purple-200 focus:ring-opacity-50"
              />
              <p className="text-xs text-gray-500">
                UI から送信する際に使用する OpenAI API キーです。保存するとローカルストレージに暗号化せず保存されます。
              </p>
            </div>
          </div>

          <div className="pt-4">
            <button
              onClick={handleSave}
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
