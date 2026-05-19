import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SlotRow, FeedbackHistoryRow } from '../components/profile';
import { getUser, removeUser, getOnboardingData, clearOnboardingData, getFeedbackHistory, clearFeedbackHistory } from '../utils';

export default function ProfilePage() {
  const navigate = useNavigate();
  const user = getUser() ?? {};
  const onboardingData = getOnboardingData();
  const feedbackHistory = getFeedbackHistory();

  const filledSlots = onboardingData.filled_slots ?? [];
  const context = onboardingData.context ?? {};

  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const handleLogout = () => {
    removeUser();
    navigate('/login');
  };

  const handleClearData = () => {
    clearOnboardingData();
    clearFeedbackHistory();
    setShowClearConfirm(false);
    window.location.reload();
  };

  const slotValues = Object.entries(context)
    .filter(([key, val]) => filledSlots.includes(key) && val?.value)
    .map(([key, val]) => ({ key, value: val.value }));

  return (
    <div className="min-h-screen bg-paper">
      <div className="max-w-lg mx-auto px-6 py-12">
        <button onClick={() => navigate('/chat')} className="text-xs text-ink-muted hover:text-ink mb-8 flex items-center gap-1 transition-colors">
          ← 채팅으로 돌아가기
        </button>

        {/* 사용자 정보 */}
        <div className="flex items-center gap-4 mb-10">
          <div className="w-14 h-14 rounded-full bg-ink flex items-center justify-center font-serif text-xl text-paper font-bold">
            {user.name?.[0] ?? '?'}
          </div>
          <div>
            <h1 className="font-serif text-xl font-bold text-ink">{user.name ?? '사용자'}</h1>
            <p className="text-sm text-ink-muted">{user.email}</p>
          </div>
        </div>

        {/* 온보딩 데이터 */}
        <section className="mb-10">
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">
            나의 독서 프로필
          </h2>
          <div className="bg-white border border-ink/10 rounded-lg px-5">
            {slotValues.length > 0 ? (
              slotValues.map(({ key, value }) => (
                <SlotRow key={key} slotKey={key} value={String(value)} />
              ))
            ) : (
              <p className="text-sm text-ink-muted py-6 text-center">
                아직 프로필이 없습니다.
                <br />
                채팅을 통해 책을 추천받으면 자동으로 쌓입니다.
              </p>
            )}
          </div>
          {filledSlots.length > 0 && (
            <p className="text-xs text-ink-muted mt-2">채워진 항목: {filledSlots.join(', ')}</p>
          )}
        </section>

        {/* 피드백 히스토리 */}
        <section className="mb-10">
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">
            피드백 기록
          </h2>
          {feedbackHistory.length > 0 ? (
            <div className="flex flex-col gap-3">
              {[...feedbackHistory].reverse().map((fb, i) => (
                <FeedbackHistoryRow key={i} feedback={fb} />
              ))}
            </div>
          ) : (
            <div className="bg-white border border-ink/10 rounded-lg px-5 py-6 text-center">
              <p className="text-sm text-ink-muted">피드백 기록이 없습니다.</p>
            </div>
          )}
        </section>

        {/* 계정 관리 */}
        <section>
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">
            계정 관리
          </h2>
          <div className="flex flex-col gap-2">
            {showClearConfirm ? (
              <div className="border border-red-100 bg-red-50 rounded-lg p-4">
                <p className="text-sm text-red-700 mb-3">프로필과 피드백 기록이 모두 삭제됩니다. 계속할까요?</p>
                <div className="flex gap-2">
                  <button onClick={handleClearData} className="flex-1 bg-red-600 text-white py-2 rounded text-sm hover:bg-red-700 transition-colors">삭제</button>
                  <button onClick={() => setShowClearConfirm(false)} className="flex-1 border border-ink/15 py-2 rounded text-sm text-ink-muted hover:text-ink transition-colors">취소</button>
                </div>
              </div>
            ) : (
              <button onClick={() => setShowClearConfirm(true)} className="text-sm text-ink-muted border border-ink/10 rounded py-2.5 hover:border-red-200 hover:text-red-600 transition-colors">
                프로필 데이터 초기화
              </button>
            )}
            <button onClick={handleLogout} className="text-sm text-ink-muted border border-ink/10 rounded py-2.5 hover:bg-paper-2 transition-colors">
              로그아웃
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
