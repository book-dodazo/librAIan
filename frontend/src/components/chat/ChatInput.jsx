import { useState, useEffect, useRef } from 'react';

/**
 * 채팅 입력창
 *
 * props:
 *   onSend    - (text: string) => void
 *   isLoading - boolean
 */
export default function ChatInput({ onSend, isLoading }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // 사이드바 빠른 질문 이벤트 수신
  useEffect(() => {
    const handler = (e) => {
      setText(e.detail);
      textareaRef.current?.focus();
    };
    window.addEventListener('quick-prompt', handler);
    return () => window.removeEventListener('quick-prompt', handler);
  }, []);

  const handleSend = () => {
    if (!text.trim() || isLoading) return;
    onSend(text.trim());
    setText('');
  };

  const handleKeyDown = (e) => {
    // Shift+Enter: 줄바꿈, Enter: 전송
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-ink/10 bg-paper px-8 py-5 flex-shrink-0">
      <div className="flex items-end gap-3 max-w-3xl mx-auto">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="읽고 싶은 책에 대해 자유롭게 말해주세요..."
          rows={1}
          disabled={isLoading}
          className="flex-1 bg-white border border-ink/12 rounded-lg px-4 py-3 text-sm text-ink resize-none focus:outline-none focus:border-ink/30 placeholder:text-ink-muted leading-relaxed disabled:opacity-50 overflow-hidden"
          style={{ minHeight: '48px', maxHeight: '160px' }}
          onInput={(e) => {
            e.target.style.height = 'auto';
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
        />
        <button
          onClick={handleSend}
          disabled={!text.trim() || isLoading}
          className="w-12 h-12 bg-ink text-paper rounded-lg flex items-center justify-center hover:bg-ink-soft transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
        >
          {isLoading ? (
            <span className="w-4 h-4 border-2 border-paper/30 border-t-paper rounded-full animate-spin" />
          ) : (
            <span className="text-lg leading-none">↑</span>
          )}
        </button>
      </div>
      <p className="text-center text-[11px] text-ink-muted mt-2 max-w-3xl mx-auto">
        Enter로 전송 · Shift+Enter로 줄바꿈
      </p>
    </div>
  );
}
