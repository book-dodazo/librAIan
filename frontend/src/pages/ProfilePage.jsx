import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { SlotRow, FeedbackHistoryRow } from '../components/profile';
import { removeUser, removeToken } from '../utils';
import { getProfile } from '../services/profileApi';

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false));
  }, [navigate]);

  const handleLogout = () => {
    removeUser();
    removeToken();
    navigate('/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <p className="text-sm text-ink-muted">불러오는 중...</p>
      </div>
    );
  }

  const user = profile?.user ?? {};
  const onboardingData = profile?.onboarding_data ?? {};
  const feedbackHistory = profile?.feedback_history ?? [];

  return (
    <div className="min-h-screen bg-paper">
      <div className="max-w-lg mx-auto px-6 py-12">
        <button onClick={() => navigate('/chat')} className="text-xs text-ink-muted hover:text-ink mb-8 flex items-center gap-1 transition-colors">
          ← 채팅으로 돌아가기
        </button>

        <div className="flex items-center gap-4 mb-10">
          <div className="w-14 h-14 rounded-full bg-ink flex items-center justify-center font-serif text-xl text-paper font-bold">
            {user.name?.[0] ?? '?'}
          </div>
          <div>
            <h1 className="font-serif text-xl font-bold text-ink">{user.name ?? '사용자'}</h1>
            <p className="text-sm text-ink-muted">{user.email}</p>
          </div>
        </div>

        <section className="mb-10">
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">나의 독서 프로필</h2>
          <div className="bg-white border border-ink/10 rounded-lg px-5">
            {Object.keys(onboardingData).length > 0 ? (
              Object.entries(onboardingData).map(([key, value]) => (
                <SlotRow key={key} slotKey={key} value={value} />
              ))
            ) : (
              <p className="text-sm text-ink-muted py-6 text-center">
                아직 프로필이 없습니다.<br />채팅을 통해 책을 추천받으면 자동으로 쌓입니다.
              </p>
            )}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">피드백 기록</h2>
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

        <section>
          <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted mb-4">계정 관리</h2>
          <div className="flex flex-col gap-2">
            <button onClick={handleLogout} className="text-sm text-ink-muted border border-ink/10 rounded py-2.5 hover:bg-paper-2 transition-colors">
              로그아웃
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
