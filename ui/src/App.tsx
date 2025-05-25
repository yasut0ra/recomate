import React, { useState } from 'react';
import './App.css';

const App: React.FC = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<string[]>([]);

  const handleSend = () => {
    if (input.trim() === '') return;
    setMessages([...messages, input]);
    setInput('');
  };

  return (
    <div className="main-container">
      {/* 2Dモデル表示領域 */}
      <div className="model-area">
        {/* ここに2Dモデル（画像やCanvasなど）を表示 */}
        <div className="model-placeholder">2Dモデル表示領域</div>
      </div>

      {/* チャット・リアクション領域 */}
      <div className="chat-area">
        <div className="messages">
          {messages.map((msg, idx) => (
            <div key={idx} className="message">{msg}</div>
          ))}
        </div>
        <div className="input-area">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="メッセージを入力..."
          />
          <button onClick={handleSend}>送信</button>
        </div>
      </div>
    </div>
  );
};

export default App;