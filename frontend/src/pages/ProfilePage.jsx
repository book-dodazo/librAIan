import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { FeedbackHistoryRow } from '../components/profile';
import { removeUser, removeToken } from '../utils';
import { getProfile, updateProfile } from '../services/profileApi';

// 온보딩 필드 한글 레이블
const FIELD_LABELS = {
  age                 : '나이',
  preferred_length    : '선호 분량',
  disliked_keywords   : '기피 키워드',
  frequent_libraries  : '자주 가는 도서관',
  recent_liked_books  : '최근 좋았던 책',
  preferred_categories: '선호 분야',
  // 슬롯 키
  topic               : '관심 주제',
  purpose             : '독서 목적',
  reading_level       : '독서 수준',
  mood                : '원하는 분위기',
  pages               : '선호 페이지 수',
  year                : '출판 연도',
  availability        : '대출 가능 여부',
};

// 값 → 표시용 문자열
function formatValue(value) {
  if (value === null || value === undefined || value === '' || value === 'null') return null;
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value.map((v) =>
      typeof v === 'object' && v !== null
        ? v.sub || v.main || v.title || v.name || ''
        : String(v)
    ).filter(Boolean).join(', ');
  }
  if (typeof value === 'object') return value.sub || value.main || value.title || value.name || JSON.stringify(value);
  return String(value);
}

// 편집 가능한 값인지 판별 — 복잡한 객체 배열은 읽기 전용
function isEditable(value) {
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') return false;
  return true;
}

// 편집용 문자열 → 원래 타입으로 변환
function parseEditValue(original, text) {
  if (Array.isArray(original)) {
    return text.split(',').map((s) => s.trim()).filter(Boolean);
  }
  if (text === '') return null;
  return text;
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

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

  const startEdit = () => {
    setEditData({ ...(profile?.onboarding_data ?? {}) });
    setSaveError('');
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setSaveError('');
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError('');
    try {
      await updateProfile(editData);
      setProfile((prev) => ({ ...prev, onboarding_data: editData }));
      setEditing(false);
    } catch (e) {
      setSaveError(e.message ?? '저장에 실패했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (key, text) => {
    const original = profile?.onboarding_data?.[key];
    setEditData((prev) => ({ ...prev, [key]: parseEditValue(original, text) }));
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

  // 내부 메타 키 제외
  const META_KEYS = new Set(['filled_slots', 'context', '_ui_messages']);
  const displayEntries = Object.entries(onboardingData).filter(([k]) => !META_KEYS.has(k));

  return (
    <div className="min-h-screen bg-paper">
      <div className="max-w-lg mx-auto px-6 py-12">
        <button onClick={() => navigate('/chat')} className="text-xs text-ink-muted hover:text-ink mb-8 flex items-center gap-1 transition-colors">
          ← 채팅으로 돌아가기
        </button>

        {/* 유저 정보 */}
        <div className="flex items-center gap-4 mb-10">
          <div className="w-14 h-14 rounded-full bg-ink flex items-center justify-center font-serif text-xl text-paper font-bold">
            {user.name?.[0] ?? '?'}
          </div>
          <div>
            <h1 className="font-serif text-xl font-bold text-ink">{user.name ?? '사용자'}</h1>
            <p className="text-sm text-ink-muted">{user.email}</p>
          </div>
        </div>

        {/* 독서 프로필 */}
        <section className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-medium tracking-widest uppercase text-ink-muted">나의 독서 프로필</h2>
            {!editing ? (
              <button
                onClick={startEdit}
                className="text-xs text-ink-muted border border-ink/15 rounded px-3 py-1 hover:bg-paper-2 transition-colors"
              >
                편집
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={cancelEdit}
                  className="text-xs text-ink-muted border border-ink/15 rounded px-3 py-1 hover:bg-paper-2 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="text-xs text-white bg-ink rounded px-3 py-1 hover:bg-ink/80 transition-colors disabled:opacity-50"
                >
                  {saving ? '저장 중...' : '저장'}
                </button>
              </div>
            )}
          </div>

          {saveError && (
            <p className="text-xs text-red-500 mb-2">{saveError}</p>
          )}

          <div className="bg-white border border-ink/10 rounded-lg px-5">
            {displayEntries.length === 0 ? (
              <p className="text-sm text-ink-muted py-6 text-center">
                아직 프로필이 없습니다.<br />채팅을 통해 책을 추천받으면 자동으로 쌓입니다.
              </p>
            ) : (
              displayEntries.map(([key, value]) => {
                const label = FIELD_LABELS[key] ?? key;
                const formatted = formatValue(value);
                const editable = isEditable(value);

                return (
                  <div key={key} className="flex items-center justify-between py-3 border-b border-ink/8 last:border-0 gap-3">
                    <span className="text-sm text-ink-muted flex-shrink-0">{label}</span>

                    {editing && editable ? (
                      <input
                        type="text"
                        value={formatValue(editData[key]) ?? ''}
                        onChange={(e) => handleChange(key, e.target.value)}
                        placeholder="지정 없음"
                        className="text-sm text-ink text-right bg-paper-2 border border-ink/15 rounded-lg px-3 py-1 w-48 focus:outline-none focus:border-ink/40 transition-colors"
                      />
                    ) : (
                      formatted ? (
                        <span className="text-sm text-ink font-medium bg-paper-2 px-3 py-1 rounded-full max-w-[60%] text-right truncate">
                          {formatted}
                        </span>
                      ) : (
                        <span className="text-sm text-ink-muted/40 italic">지정 없음</span>
                      )
                    )}
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* 피드백 기록 */}
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

        {/* 계정 관리 */}
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
