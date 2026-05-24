import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import useChat from '../hooks/useChat';
import { getUser } from '../utils';
import { Sidebar } from '../components/layout';
import { SlotStatusBar, MessageBubble, ChatInput, EmptyState, LoadingBubble } from '../components/chat';

export default function ChatPage() {
  const navigate = useNavigate();
  const messagesEndRef = useRef(null);
  const { messages, filledSlots, isLoading, sessionId, sendMessage, selectChoice, confirmInferred, resetChat, loadSession } = useChat();

  const user = getUser(); // null이면 게스트
  const isGuest = !user;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const lastResultMsg = [...messages].reverse().find((m) => m.hasResults);

  return (
    <div className="flex h-screen overflow-hidden bg-paper font-sans">
      <Sidebar
        userName={user?.name}
        isGuest={isGuest}
        onRestart={resetChat}
        onFeedback={() =>
          navigate('/feedback', { state: { results: lastResultMsg?.search_results, availability: lastResultMsg?.availability_index } })
        }
        onProfile={() => isGuest ? navigate('/login') : navigate('/profile')}
        onLoadSession={loadSession}
        currentSessionId={sessionId}
      />

      <div className="flex flex-col flex-1 overflow-hidden">
        <div className="flex items-center justify-between px-8 py-5 border-b border-ink/10 bg-paper flex-shrink-0">
          <h1 className="font-serif text-base text-ink-soft">AI 도서 큐레이션</h1>
          <span className="text-xs tracking-widest uppercase px-3 py-1 border border-ink/10 rounded-full text-ink-muted">
            librAIan
          </span>
        </div>

        <SlotStatusBar filledSlots={filledSlots} />

        <div className="flex-1 overflow-y-auto px-8 py-8 flex flex-col gap-6">
          {messages.length === 0 && !isLoading && <EmptyState />}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} onSelectChoice={selectChoice} onConfirm={confirmInferred} />
          ))}
          {isLoading && <LoadingBubble />}
          <div ref={messagesEndRef} />
        </div>

        <ChatInput onSend={sendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
}
