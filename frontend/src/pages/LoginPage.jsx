import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { saveUser, saveToken } from '../utils';
import { signup, login } from '../services/authApi';

const ONBOARDING_STEPS = [
  {
    key: 'purpose',
    question: '주로 어떤 목적으로 책을 읽으세요?',
    options: ['재미', '공부', '자기계발', '정보 수집'],
  },
  {
    key: 'reading_level',
    question: '어떤 난이도의 책을 선호하세요?',
    options: ['쉬운 책', '보통', '어려운 책'],
  },
  {
    key: 'length',
    question: '선호하는 책 길이는?',
    options: ['짧은 책', '보통', '긴 책'],
  },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState('login');
  const [step, setStep] = useState('form'); // 'form' | 'onboarding'
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [onboarding, setOnboarding] = useState({});
  const [onboardingStep, setOnboardingStep] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'signup') {
        if (!form.name.trim()) { setError('이름을 입력해주세요.'); return; }
        setStep('onboarding');
      } else {
        const res = await login(form.email, form.password);
        saveToken(res.token);
        saveUser(res.user);
        navigate('/chat');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOnboardingSelect = async (value) => {
    const key = ONBOARDING_STEPS[onboardingStep].key;
    const updated = { ...onboarding, [key]: value };
    setOnboarding(updated);

    if (onboardingStep < ONBOARDING_STEPS.length - 1) {
      setOnboardingStep((s) => s + 1);
    } else {
      setLoading(true);
      try {
        const res = await signup(form.name, form.email, form.password, updated);
        saveToken(res.token);
        saveUser(res.user);
        navigate('/chat');
      } catch (err) {
        setError(err.message);
        setStep('form');
        setOnboardingStep(0);
      } finally {
        setLoading(false);
      }
    }
  };

  if (step === 'onboarding') {
    const current = ONBOARDING_STEPS[onboardingStep];
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center px-4">
        <div className="w-full max-w-sm">
          <div className="text-center mb-10">
            <h1 className="font-serif text-4xl font-bold text-ink mb-1">책마루</h1>
            <p className="text-xs tracking-[0.2em] uppercase text-ink-muted">독서 취향 파악</p>
          </div>

          <div className="mb-2 flex gap-1">
            {ONBOARDING_STEPS.map((_, i) => (
              <div key={i} className={`h-1 flex-1 rounded ${i <= onboardingStep ? 'bg-ink' : 'bg-ink/10'}`} />
            ))}
          </div>
          <p className="text-xs text-ink-muted mb-6">{onboardingStep + 1} / {ONBOARDING_STEPS.length}</p>

          <p className="text-sm font-medium text-ink mb-4">{current.question}</p>
          <div className="flex flex-col gap-2">
            {current.options.map((opt) => (
              <button
                key={opt}
                onClick={() => handleOnboardingSelect(opt)}
                disabled={loading}
                className="w-full border border-ink/15 rounded px-4 py-3 text-sm text-left hover:border-ink/40 hover:bg-paper-2 transition-colors"
              >
                {opt}
              </button>
            ))}
          </div>

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded px-3 py-2 mt-4">{error}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <h1 className="font-serif text-4xl font-bold text-ink mb-1">책마루</h1>
          <p className="text-xs tracking-[0.2em] uppercase text-ink-muted">AI Book Curation</p>
        </div>

        <div className="flex border border-ink/10 rounded mb-6 overflow-hidden">
          {['login', 'signup'].map((tab) => (
            <button
              key={tab}
              onClick={() => { setMode(tab); setError(''); }}
              className={`flex-1 py-2.5 text-sm transition-colors ${
                mode === tab ? 'bg-ink text-paper font-medium' : 'bg-paper text-ink-muted hover:text-ink'
              }`}
            >
              {tab === 'login' ? '로그인' : '회원가입'}
            </button>
          ))}
        </div>

        <form onSubmit={handleFormSubmit} className="flex flex-col gap-3">
          {mode === 'signup' && (
            <input
              type="text"
              placeholder="이름"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full border border-ink/15 rounded px-4 py-3 text-sm bg-paper focus:outline-none focus:border-ink/40 placeholder:text-ink-muted"
            />
          )}
          <input
            type="email"
            placeholder="이메일"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="w-full border border-ink/15 rounded px-4 py-3 text-sm bg-paper focus:outline-none focus:border-ink/40 placeholder:text-ink-muted"
          />
          <input
            type="password"
            placeholder="비밀번호"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="w-full border border-ink/15 rounded px-4 py-3 text-sm bg-paper focus:outline-none focus:border-ink/40 placeholder:text-ink-muted"
          />

          {error && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded px-3 py-2">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-2 w-full bg-ink text-paper py-3 rounded text-sm font-medium hover:bg-ink-soft transition-colors disabled:opacity-50"
          >
            {loading ? '처리 중...' : mode === 'login' ? '로그인' : '다음'}
          </button>
        </form>

        <p className="text-center text-xs text-ink-muted mt-8">좋은 책이 당신을 기다리고 있습니다.</p>
      </div>
    </div>
  );
}
