import { useState, useEffect, useCallback } from 'react';
import { checkHealth, getSessions, deleteSession, getSession } from '../../services';

export default function Sidebar({ userName, isGuest = false, onRestart, onFeedback, onProfile, onLoadSession, currentSessionId }) {
  const [isHealthy, setIsHealthy] = useState(null);
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    checkHealth().then(setIsHealthy).catch(() => setIsHealthy(false));
  }, []);

  const loadSessions = useCallback(() => {
    if (isGuest) return;
    getSessions().then(setSessions).catch(() => setSessions([]));
  }, [isGuest]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (currentSessionId) loadSessions();
  }, [currentSessionId, loadSessions]);

  const handleLoad = async (sessionId) => {
    try {
      const session = await getSession(sessionId);
      onLoadSession?.(session);
    } catch (e) {
      console.error('세션 불러오기 실패', e);
    }
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    await deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
  };

  // 날짜 그룹화
  const groupByDate = (sessions) => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today - 86400000);
    const weekAgo = new Date(today - 7 * 86400000);

    const groups = { '오늘': [], '어제': [], '이번 주': [], '이전': [] };
    sessions.forEach((s) => {
      const d = new Date(s.updated_at);
      if (d >= today) groups['오늘'].push(s);
      else if (d >= yesterday) groups['어제'].push(s);
      else if (d >= weekAgo) groups['이번 주'].push(s);
      else groups['이전'].push(s);
    });
    return groups;
  };

  const groups = groupByDate(sessions);

  return (
    <aside className="w-64 bg-ink text-paper flex flex-col flex-shrink-0 relative overflow-hidden sidebar-pattern h-screen">
      {/* 상단: 로고 + 새 대화 */}
      <div className="px-4 pt-6 pb-3 flex-shrink-0">
        <div className="mb-4 px-3">
          <h1 className="font-serif text-lg font-bold tracking-tight">librAIan</h1>
          <p className="text-[10px] tracking-[0.2em] uppercase text-paper/40 mt-0.5">AI Book Curation</p>
        </div>
        <button
          onClick={onRestart}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-white/15 text-[12.5px] text-paper/80 hover:bg-white/8 hover:text-paper hover:border-white/25 transition-all"
        >
          <span className="text-base leading-none">＋</span>
          새 대화 시작
        </button>
      </div>

      {/* 세션 목록 or 게스트 안내 */}
      <div className="flex-1 overflow-y-auto px-4 pb-2">
        {isGuest ? (
          <div className="mx-1 mt-3 rounded-lg border border-white/10 bg-white/5 px-4 py-4">
            <p className="text-xs text-paper/60 leading-relaxed mb-3">
              로그인하면 대화 기록이 저장되고 이어서 볼 수 있어요
            </p>
            <button
              onClick={onProfile}
              className="w-full text-xs text-paper/80 border border-white/20 rounded-lg py-2 hover:bg-white/10 transition-colors"
            >
              로그인 / 회원가입
            </button>
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-xs text-paper/25 px-3 py-4">아직 저장된 대화가 없어요</p>
        ) : (
          Object.entries(groups).map(([label, items]) =>
            items.length === 0 ? null : (
              <div key={label} className="mb-4">
                <p className="text-[10px] tracking-[0.15em] uppercase text-paper/30 px-3 mb-1">{label}</p>
                <ul className="flex flex-col gap-0.5">
                  {items.map((s) => (
                    <li key={s.id}>
                      <button
                        onClick={() => handleLoad(s.id)}
                        className={`w-full text-left text-[12.5px] leading-snug px-3 py-2 rounded-lg group flex items-center gap-1 transition-colors ${
                          currentSessionId === s.id
                            ? 'bg-white/12 text-paper'
                            : 'text-paper/60 hover:bg-white/7 hover:text-paper/90'
                        }`}
                      >
                        <span className="truncate flex-1">{s.title}</span>
                        <span
                          onClick={(e) => handleDelete(e, s.id)}
                          className="opacity-0 group-hover:opacity-100 text-paper/30 hover:text-red-400 text-xs flex-shrink-0 px-0.5 transition-all"
                          title="삭제"
                        >
                          ✕
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )
          )
        )}
      </div>

      {/* 하단: 메뉴 + 상태 */}
      <div className="flex-shrink-0 px-4 pt-2 pb-5 border-t border-white/8">
        <div className="flex flex-col gap-0.5 mb-4">
          <button onClick={onFeedback} className="text-left text-[12.5px] text-paper/60 px-3 py-2 rounded-lg hover:bg-white/7 hover:text-paper transition-colors">
            ✦ 피드백 남기기
          </button>
          {!isGuest && (
            <button onClick={onProfile} className="text-left text-[12.5px] text-paper/60 px-3 py-2 rounded-lg hover:bg-white/7 hover:text-paper transition-colors">
              ◉ 내 프로필
            </button>
          )}
        </div>
        {userName && (
          <p className="text-xs text-paper/40 px-3 mb-2">안녕하세요, {userName}님</p>
        )}
        <div className="flex items-center gap-2 text-xs text-paper/35 px-3">
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            isHealthy === null ? 'bg-yellow-400' : isHealthy ? 'bg-green-400 shadow-[0_0_6px_#4ade80]' : 'bg-red-400'
          }`} />
          {isHealthy === null ? '연결 확인 중...' : isHealthy ? 'API 연결됨' : 'API 연결 안 됨'}
        </div>
      </div>
    </aside>
  );
}
