import { useState, useEffect, useCallback } from 'react';
import { checkHealth, getSessions, deleteSession, getSession } from '../../services';
import { QUICK_PROMPTS } from '../../constants/prompts';

export default function Sidebar({ userName, onRestart, onFeedback, onProfile, onLoadSession, currentSessionId }) {
  const [isHealthy, setIsHealthy] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    checkHealth()
      .then(setIsHealthy)
      .catch(() => setIsHealthy(false));
  }, []);

  const loadSessions = useCallback(() => {
    getSessions()
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);

  useEffect(() => {
    if (showHistory) loadSessions();
  }, [showHistory, loadSessions]);

  // 새 세션이 생성될 때 목록 새로고침
  useEffect(() => {
    if (currentSessionId && showHistory) loadSessions();
  }, [currentSessionId, showHistory, loadSessions]);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  };

  const handleLoad = async (sessionId) => {
    try {
      const session = await getSession(sessionId);
      onLoadSession?.(session);
      setShowHistory(false);
    } catch (e) {
      console.error('세션 불러오기 실패', e);
    }
  };

  return (
    <aside className="w-64 bg-ink text-paper flex flex-col px-7 py-9 flex-shrink-0 relative overflow-hidden sidebar-pattern">
      {/* 로고 */}
      <div className="mb-10">
        <h1 className="font-serif text-xl font-bold tracking-tight">librAIan</h1>
        <p className="text-[10px] tracking-[0.2em] uppercase text-paper/40 mt-1">AI Book Curation</p>
      </div>

      {/* 빠른 질문 */}
      <div className="mb-9">
        <p className="text-[10px] tracking-[0.2em] uppercase text-paper/35 mb-3">빠른 시작</p>
        <ul className="flex flex-col gap-1.5">
          {QUICK_PROMPTS.map((prompt) => (
            <li key={prompt}>
              <button
                onClick={() => window.dispatchEvent(new CustomEvent('quick-prompt', { detail: prompt }))}
                className="w-full text-left text-[12.5px] leading-snug text-paper/70 border border-white/10 rounded px-3.5 py-2.5 hover:bg-white/7 hover:border-white/22 hover:text-paper hover:translate-x-0.5 transition-all relative pr-6"
              >
                {prompt}
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-paper/40 text-sm">›</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* 네비게이션 */}
      <div className="mb-9">
        <p className="text-[10px] tracking-[0.2em] uppercase text-paper/35 mb-3">메뉴</p>
        <div className="flex flex-col gap-1">
          <button onClick={onRestart} className="text-left text-[12.5px] text-paper/70 px-3.5 py-2 rounded hover:bg-white/7 hover:text-paper transition-colors">
            ↺ 처음부터 다시
          </button>
          <button
            onClick={() => setShowHistory((v) => !v)}
            className={`text-left text-[12.5px] px-3.5 py-2 rounded transition-colors ${
              showHistory ? 'text-paper bg-white/10' : 'text-paper/70 hover:bg-white/7 hover:text-paper'
            }`}
          >
            ◷ 이전 대화
          </button>
          <button onClick={onFeedback} className="text-left text-[12.5px] text-paper/70 px-3.5 py-2 rounded hover:bg-white/7 hover:text-paper transition-colors">
            ✦ 피드백 남기기
          </button>
          <button onClick={onProfile} className="text-left text-[12.5px] text-paper/70 px-3.5 py-2 rounded hover:bg-white/7 hover:text-paper transition-colors">
            ◉ 내 프로필
          </button>
        </div>
      </div>

      {/* 이전 대화 목록 */}
      {showHistory && (
        <div className="mb-6 flex-1 overflow-y-auto min-h-0">
          <p className="text-[10px] tracking-[0.2em] uppercase text-paper/35 mb-2">이전 대화</p>
          {sessions.length === 0 ? (
            <p className="text-xs text-paper/30 px-1">저장된 대화가 없어요</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => handleLoad(s.id)}
                    className={`w-full text-left text-[12px] leading-snug px-3 py-2 rounded group flex items-center justify-between gap-1 transition-colors ${
                      currentSessionId === s.id
                        ? 'bg-white/15 text-paper'
                        : 'text-paper/60 hover:bg-white/7 hover:text-paper'
                    }`}
                  >
                    <span className="truncate flex-1">{s.title}</span>
                    <span
                      onClick={(e) => handleDelete(e, s.id)}
                      className="opacity-0 group-hover:opacity-100 text-paper/40 hover:text-red-400 text-xs px-1 transition-opacity flex-shrink-0"
                    >
                      ✕
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 상태 + 사용자 */}
      <div className="mt-auto border-t border-white/8 pt-5">
        {userName && (
          <p className="text-xs text-paper/50 mb-3">안녕하세요, {userName}님</p>
        )}
        <div className="flex items-center gap-2 text-xs text-paper/45">
          <span
            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              isHealthy === null
                ? 'bg-yellow-400'
                : isHealthy
                ? 'bg-green-400 shadow-[0_0_6px_#4ade80]'
                : 'bg-red-400 shadow-[0_0_6px_#ef4444]'
            }`}
          />
          {isHealthy === null ? '연결 확인 중...' : isHealthy ? 'API 연결됨' : 'API 연결 안 됨'}
        </div>
        <p className="text-[10px] text-paper/20 mt-1 break-all">localhost:8000</p>
      </div>
    </aside>
  );
}
