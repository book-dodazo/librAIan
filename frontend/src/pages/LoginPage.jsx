import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getUser, saveUser } from '../utils';

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (mode === 'signup') {
      if (!form.name.trim()) { setError('이름을 입력해주세요.'); return; }
      if (!form.email.trim()) { setError('이메일을 입력해주세요.'); return; }
      saveUser({ name: form.name, email: form.email });
      navigate('/chat');
    } else {
      const saved = getUser();
      if (!saved || saved.email !== form.email) {
        setError('가입된 이메일이 없습니다. 회원가입을 해주세요.');
        return;
      }
      navigate('/chat');
    }
  };

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* 로고 */}
        <div className="text-center mb-10">
          <h1 className="font-serif text-4xl font-bold text-ink mb-1">책마루</h1>
          <p className="text-xs tracking-[0.2em] uppercase text-ink-muted">AI Book Curation</p>
        </div>

        {/* 탭 */}
        <div className="flex border border-ink/10 rounded mb-6 overflow-hidden">
          {['login', 'signup'].map((tab) => (
            <button
              key={tab}
              onClick={() => { setMode(tab); setError(''); }}
              className={`flex-1 py-2.5 text-sm transition-colors ${
                mode === tab
                  ? 'bg-ink text-paper font-medium'
                  : 'bg-paper text-ink-muted hover:text-ink'
              }`}
            >
              {tab === 'login' ? '로그인' : '회원가입'}
            </button>
          ))}
        </div>

        {/* 폼 */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
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
            <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="mt-2 w-full bg-ink text-paper py-3 rounded text-sm font-medium hover:bg-ink-soft transition-colors"
          >
            {mode === 'login' ? '로그인' : '가입하기'}
          </button>
        </form>

        <p className="text-center text-xs text-ink-muted mt-8">
          좋은 책이 당신을 기다리고 있습니다.
        </p>
      </div>
    </div>
  );
}
