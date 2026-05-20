import { useState, useEffect, useRef } from 'react';
import { searchBooks, searchLibraries, getCategories } from '../services/onboardingApi';

const STEPS = ['books', 'categories', 'length', 'keywords', 'age', 'libraries'];

const STEP_TITLES = {
  books:      '최근 좋았던 책이 있나요?',
  categories: '관심 있는 분야를 선택하세요',
  length:     '선호하는 책 분량이 있나요?',
  keywords:   '잘 안 읽게 되는 책은?',
  age:        '나이대를 알려주세요',
  libraries:  '자주 가는 도서관이 있나요?',
};

const STEP_HINTS = {
  books:      '최대 3권, 건너뛰어도 됩니다',
  categories: '최대 3개 선택',
  length:     '없으면 건너뛰어도 됩니다',
  keywords:   '해당하는 것을 모두 선택하세요',
  age:        '건너뛰어도 됩니다',
  libraries:  '지역명이나 도서관명으로 검색, 최대 2개',
};

const DISLIKED_KEYWORDS = [
  { key: 'adventurous', label: '모험적인' },
  { key: 'challenging', label: '어렵고 복잡한' },
  { key: 'dark',        label: '어둡고 우울한' },
  { key: 'emotional',   label: '감정적으로 힘든' },
  { key: 'funny',       label: '가볍고 웃긴' },
  { key: 'hopeful',     label: '희망적인' },
  { key: 'informative', label: '정보 위주의' },
  { key: 'inspiring',   label: '교훈적인' },
  { key: 'lighthearted',label: '가볍고 발랄한' },
  { key: 'mysterious',  label: '미스터리한' },
  { key: 'reflective',  label: '성찰적인' },
  { key: 'relaxing',    label: '여유로운' },
  { key: 'sad',         label: '슬픈' },
  { key: 'tense',       label: '긴장감 있는' },
];

const AGE_OPTIONS = [
  { label: '10대', value: 15 },
  { label: '20대', value: 25 },
  { label: '30대', value: 35 },
  { label: '40대', value: 45 },
  { label: '50대', value: 55 },
  { label: '60대 이상', value: 65 },
];

const LENGTH_OPERATORS = [
  { key: 'lte', label: '이하' },
  { key: 'gte', label: '이상' },
  { key: 'around', label: '내외' },
];

export default function OnboardingFlow({ onComplete, loading }) {
  const [stepIndex, setStepIndex] = useState(0);

  // Step 1: books
  const [bookQuery, setBookQuery]       = useState('');
  const [bookResults, setBookResults]   = useState([]);
  const [bookSearching, setBookSearching] = useState(false);
  const [selectedBooks, setSelectedBooks] = useState([]);

  // Step 2: categories
  const [categoryTree, setCategoryTree] = useState({});
  const [activeMain, setActiveMain]     = useState('');
  const [selectedCats, setSelectedCats] = useState([]); // [{main, sub}]

  // Step 3: length
  const [lengthPages, setLengthPages] = useState('');
  const [lengthOp, setLengthOp]       = useState('lte');
  const [noLength, setNoLength]       = useState(false);

  // Step 4: keywords
  const [selectedKws, setSelectedKws] = useState([]);

  // Step 5: age
  const [selectedAge, setSelectedAge] = useState(null);

  // Step 6: libraries
  const [libQuery, setLibQuery]           = useState('');
  const [libResults, setLibResults]       = useState([]);
  const [libSearching, setLibSearching]   = useState(false);
  const [selectedLibs, setSelectedLibs]   = useState([]);

  useEffect(() => {
    getCategories()
      .then(data => {
        setCategoryTree(data);
        setActiveMain(Object.keys(data)[0] || '');
      })
      .catch(() => {});
  }, []);

  const bookTimer = useRef(null);
  useEffect(() => {
    if (!bookQuery.trim()) { setBookResults([]); return; }
    clearTimeout(bookTimer.current);
    bookTimer.current = setTimeout(async () => {
      setBookSearching(true);
      try { setBookResults(await searchBooks(bookQuery)); }
      catch { setBookResults([]); }
      finally { setBookSearching(false); }
    }, 400);
    return () => clearTimeout(bookTimer.current);
  }, [bookQuery]);

  const libTimer = useRef(null);
  useEffect(() => {
    if (!libQuery.trim()) { setLibResults([]); return; }
    clearTimeout(libTimer.current);
    libTimer.current = setTimeout(async () => {
      setLibSearching(true);
      try { setLibResults(await searchLibraries(libQuery)); }
      catch { setLibResults([]); }
      finally { setLibSearching(false); }
    }, 500);
    return () => clearTimeout(libTimer.current);
  }, [libQuery]);

  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;

  const handleNext = () => {
    if (!isLast) { setStepIndex(s => s + 1); return; }
    const preferred_length =
      noLength || !lengthPages.trim()
        ? ''
        : `${lengthPages.trim()}p ${LENGTH_OPERATORS.find(o => o.key === lengthOp)?.label ?? '이하'}`;
    onComplete({
      recent_liked_books:   selectedBooks,
      preferred_categories: selectedCats,
      preferred_length,
      disliked_keywords:    selectedKws,
      age:                  selectedAge,
      frequent_libraries:   selectedLibs.map(l => l.name),
    });
  };

  const Progress = () => (
    <div className="mb-8">
      <div className="flex gap-1 mb-2">
        {STEPS.map((_, i) => (
          <div key={i} className={`h-1 flex-1 rounded transition-colors ${i <= stepIndex ? 'bg-ink' : 'bg-ink/10'}`} />
        ))}
      </div>
      <p className="text-xs text-ink-muted">{stepIndex + 1} / {STEPS.length}</p>
    </div>
  );

  const Header = () => (
    <div className="mb-5">
      <h2 className="text-sm font-medium text-ink mb-1">{STEP_TITLES[step]}</h2>
      <p className="text-xs text-ink-muted">{STEP_HINTS[step]}</p>
    </div>
  );

  const NextBtn = ({ label = '다음', disabled = false }) => (
    <button
      onClick={handleNext}
      disabled={disabled || loading}
      className="flex-1 bg-ink text-paper py-2.5 rounded text-sm font-medium hover:bg-ink-soft transition-colors disabled:opacity-40"
    >
      {loading ? '처리 중...' : label}
    </button>
  );

  const SkipBtn = ({ label = '건너뛰기' }) => (
    <button
      onClick={handleNext}
      disabled={loading}
      className="flex-1 border border-ink/10 text-ink-muted py-2.5 rounded text-sm hover:bg-paper-2 transition-colors"
    >
      {label}
    </button>
  );

  // ── Step 1: books ────────────────────────────────────────────
  if (step === 'books') {
    const addBook = (book) => {
      if (!selectedBooks.find(b => b.title === book.title)) {
        setSelectedBooks(p => [...p, book]);
      }
      setBookQuery('');
      setBookResults([]);
    };
    const removeBook = (i) => setSelectedBooks(p => p.filter((_, j) => j !== i));

    return (
      <div className="w-full max-w-sm">
        <Progress />
        <Header />

        {selectedBooks.length < 3 && (
          <div className="relative mb-3">
            <input
              type="text"
              value={bookQuery}
              onChange={e => setBookQuery(e.target.value)}
              placeholder="책 제목으로 검색"
              className="w-full border border-ink/15 rounded px-4 py-2.5 text-sm bg-paper focus:outline-none focus:border-ink/40 placeholder:text-ink-muted"
            />
            {(bookResults.length > 0 || bookSearching) && (
              <div className="absolute z-10 w-full bg-white border border-ink/10 rounded mt-1 shadow-sm max-h-48 overflow-y-auto">
                {bookSearching
                  ? <p className="text-xs text-ink-muted px-3 py-2">검색 중...</p>
                  : bookResults.map((book, i) => (
                    <button key={i} onClick={() => addBook(book)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-paper-2 border-b border-ink/5 last:border-0">
                      <span className="font-medium text-ink">{book.title}</span>
                      {book.author && <span className="text-ink-muted text-xs ml-2">{book.author}</span>}
                    </button>
                  ))
                }
              </div>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2 mb-6">
          {selectedBooks.map((book, i) => (
            <div key={i} className="flex items-center justify-between border border-ink/10 rounded px-3 py-2 bg-white">
              <div>
                <p className="text-sm text-ink">{book.title}</p>
                {book.author && <p className="text-xs text-ink-muted">{book.author}</p>}
              </div>
              <button onClick={() => removeBook(i)} className="text-ink-muted hover:text-ink text-xs ml-3">✕</button>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          {selectedBooks.length === 0 ? <SkipBtn /> : <NextBtn />}
        </div>
      </div>
    );
  }

  // ── Step 2: categories ───────────────────────────────────────
  if (step === 'categories') {
    const mainList = Object.keys(categoryTree);
    const subs = categoryTree[activeMain] || [];

    const toggleSub = (sub) => {
      const exists = selectedCats.find(c => c.main === activeMain && c.sub === sub);
      if (exists) {
        setSelectedCats(p => p.filter(c => !(c.main === activeMain && c.sub === sub)));
      } else if (selectedCats.length < 3) {
        setSelectedCats(p => [...p, { main: activeMain, sub }]);
      }
    };

    return (
      <div className="w-full max-w-sm">
        <Progress />
        <div className="mb-4">
          <h2 className="text-sm font-medium text-ink mb-1">{STEP_TITLES[step]}</h2>
          <p className="text-xs text-ink-muted">
            최대 3개 선택&nbsp;<span className="text-ink">({selectedCats.length}/3)</span>
          </p>
        </div>

        {/* 대분류 탭 */}
        <div className="flex gap-1.5 overflow-x-auto pb-2 mb-3">
          {mainList.map(main => (
            <button key={main} onClick={() => setActiveMain(main)}
              className={`flex-none text-xs px-3 py-1.5 rounded-full border whitespace-nowrap transition-colors ${
                activeMain === main
                  ? 'bg-ink text-paper border-ink'
                  : 'border-ink/15 text-ink-muted hover:border-ink/40'
              }`}>
              {main}
            </button>
          ))}
        </div>

        {/* 중분류 그리드 */}
        <div className="grid grid-cols-2 gap-1.5 mb-3 max-h-52 overflow-y-auto">
          {subs.map(sub => {
            const isSelected = !!selectedCats.find(c => c.main === activeMain && c.sub === sub);
            const maxReached = !isSelected && selectedCats.length >= 3;
            return (
              <button key={sub} onClick={() => toggleSub(sub)} disabled={maxReached}
                className={`text-xs px-3 py-2 rounded border text-left transition-colors ${
                  isSelected
                    ? 'bg-ink text-paper border-ink'
                    : maxReached
                    ? 'border-ink/10 text-ink/25 cursor-not-allowed'
                    : 'border-ink/15 text-ink hover:border-ink/40'
                }`}>
                {sub}
              </button>
            );
          })}
        </div>

        {/* 선택된 카테고리 칩 */}
        {selectedCats.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {selectedCats.map((c, i) => (
              <span key={i} className="flex items-center gap-1 text-xs bg-ink/5 border border-ink/10 rounded-full px-2.5 py-1">
                <span className="text-ink-muted">{c.main} ·</span> {c.sub}
                <button onClick={() => setSelectedCats(p => p.filter((_, j) => j !== i))}
                  className="text-ink-muted hover:text-ink ml-0.5">✕</button>
              </span>
            ))}
          </div>
        )}

        <NextBtn disabled={selectedCats.length === 0} />
      </div>
    );
  }

  // ── Step 3: length ───────────────────────────────────────────
  if (step === 'length') {
    return (
      <div className="w-full max-w-sm">
        <Progress />
        <Header />

        <label className="flex items-center gap-2 text-sm text-ink mb-5 cursor-pointer select-none">
          <input type="checkbox" checked={noLength} onChange={e => setNoLength(e.target.checked)}
            className="accent-ink w-4 h-4" />
          제한 없음
        </label>

        {!noLength && (
          <div className="flex items-center gap-2 mb-6">
            <input
              type="number"
              value={lengthPages}
              onChange={e => setLengthPages(e.target.value)}
              placeholder="페이지 수"
              min="1"
              className="flex-1 border border-ink/15 rounded px-3 py-2.5 text-sm bg-paper focus:outline-none focus:border-ink/40"
            />
            <span className="text-sm text-ink-muted shrink-0">p</span>
            <div className="flex border border-ink/15 rounded overflow-hidden shrink-0">
              {LENGTH_OPERATORS.map(op => (
                <button key={op.key} onClick={() => setLengthOp(op.key)}
                  className={`px-3 py-2.5 text-xs transition-colors ${
                    lengthOp === op.key ? 'bg-ink text-paper' : 'text-ink-muted hover:bg-paper-2'
                  }`}>
                  {op.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <NextBtn />
      </div>
    );
  }

  // ── Step 4: keywords ─────────────────────────────────────────
  if (step === 'keywords') {
    const toggleKw = (key) => setSelectedKws(p =>
      p.includes(key) ? p.filter(k => k !== key) : [...p, key]
    );

    return (
      <div className="w-full max-w-sm">
        <Progress />
        <Header />

        <div className="grid grid-cols-2 gap-2 mb-6">
          {DISLIKED_KEYWORDS.map(({ key, label }) => (
            <button key={key} onClick={() => toggleKw(key)}
              className={`text-xs px-3 py-2.5 rounded border text-left transition-colors ${
                selectedKws.includes(key)
                  ? 'bg-ink text-paper border-ink'
                  : 'border-ink/15 text-ink hover:border-ink/40'
              }`}>
              {label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          {selectedKws.length === 0 ? <SkipBtn /> : <NextBtn />}
        </div>
      </div>
    );
  }

  // ── Step 5: age ──────────────────────────────────────────────
  if (step === 'age') {
    return (
      <div className="w-full max-w-sm">
        <Progress />
        <Header />

        <div className="grid grid-cols-3 gap-2 mb-6">
          {AGE_OPTIONS.map(({ label, value }) => (
            <button key={value} onClick={() => setSelectedAge(selectedAge === value ? null : value)}
              className={`py-3 rounded border text-sm transition-colors ${
                selectedAge === value
                  ? 'bg-ink text-paper border-ink'
                  : 'border-ink/15 text-ink hover:border-ink/40'
              }`}>
              {label}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          {selectedAge == null ? <SkipBtn /> : <NextBtn />}
        </div>
      </div>
    );
  }

  // ── Step 6: libraries ────────────────────────────────────────
  if (step === 'libraries') {
    const addLib = (lib) => {
      if (!selectedLibs.find(l => l.name === lib.name)) {
        setSelectedLibs(p => [...p, lib]);
      }
      setLibQuery('');
      setLibResults([]);
    };
    const removeLib = (i) => setSelectedLibs(p => p.filter((_, j) => j !== i));

    return (
      <div className="w-full max-w-sm">
        <Progress />
        <Header />

        {selectedLibs.length < 2 && (
          <div className="relative mb-3">
            <input
              type="text"
              value={libQuery}
              onChange={e => setLibQuery(e.target.value)}
              placeholder="마포, 성북구립, 국립중앙..."
              className="w-full border border-ink/15 rounded px-4 py-2.5 text-sm bg-paper focus:outline-none focus:border-ink/40 placeholder:text-ink-muted"
            />
            {(libResults.length > 0 || libSearching) && (
              <div className="absolute z-10 w-full bg-white border border-ink/10 rounded mt-1 shadow-sm max-h-48 overflow-y-auto">
                {libSearching
                  ? <p className="text-xs text-ink-muted px-3 py-2">검색 중...</p>
                  : libResults.map((lib, i) => (
                    <button key={i} onClick={() => addLib(lib)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-paper-2 border-b border-ink/5 last:border-0">
                      <p className="font-medium text-ink">{lib.name}</p>
                      {lib.address && <p className="text-xs text-ink-muted">{lib.address}</p>}
                    </button>
                  ))
                }
              </div>
            )}
          </div>
        )}

        <div className="flex flex-col gap-2 mb-6">
          {selectedLibs.map((lib, i) => (
            <div key={i} className="flex items-center justify-between border border-ink/10 rounded px-3 py-2 bg-white">
              <div>
                <p className="text-sm text-ink">{lib.name}</p>
                {lib.address && <p className="text-xs text-ink-muted">{lib.address}</p>}
              </div>
              <button onClick={() => removeLib(i)} className="text-ink-muted hover:text-ink text-xs ml-3">✕</button>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          {selectedLibs.length === 0 ? <SkipBtn label="완료 (건너뛰기)" /> : <NextBtn label="완료" />}
        </div>
      </div>
    );
  }

  return null;
}
