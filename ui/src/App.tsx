import Header from './components/Header';
import Character from './components/Character';
import ChatContainer from './components/ChatContainer';
import InputSection from './components/InputSection';
import { ChatProvider } from './context/ChatContext';
import RitualPanel from './components/RitualPanel';
import MemoryPanel from './components/MemoryPanel';
import AgentRequestPanel from './components/AgentRequestPanel';
import './App.css';

function App() {
  return (
    <ChatProvider>
      <div className="min-h-screen bg-gradient-to-b from-purple-50 to-pink-50 flex flex-col">
        <Header />
        <main className="flex-1 flex flex-col items-center justify-between p-4 max-w-3xl mx-auto w-full">
          <Character />
          <ChatContainer />
          <InputSection />
        </main>
        <RitualPanel />
        <MemoryPanel />
        <AgentRequestPanel />
      </div>
    </ChatProvider>
  );
}

export default App;
