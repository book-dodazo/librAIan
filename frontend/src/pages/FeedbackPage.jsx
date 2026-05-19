import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { BookFeedbackCard } from '../components/feedback';
import { appendFeedback } from '../utils';

export default function FeedbackPage() {
  const navigate = useNavigate();
  const { state } = useLocation();
  const results = state?.results ?? [];
  const availability = state?.availability ?? {};

  const [books, setBooks] = useState(results.map((b) => ({ ...b, _rating: null })));
  const [comment, setComment] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (isbn, field, value) => {
    setBooks((prev) => prev.map((b) => (b.isbn === isbn ? { ...b, [`_${field}`]: value } : b)));
  };

  const handleSubmit = () => {
    appendFeedback({
      timestamp: new Date().toISOString(),
      books: books.map(({ isbn, rank, score, _rating }) => ({ isbn, rank, score, rating: _rating })),
      comment,
    });
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="text-center fade-up">
          <span className="text-6xl block mb-6">🎉</span>
          <h2 className="font-serif text-2xl font-bold text-ink mb-3">감사합니다!</h2>
          <p className="text-sm text-ink-muted mb-8">피드백이 저장됐습니다. 더 좋은 추천을 위해 활용할게요.</p>
          <button
            onClick={() => navigate('/chat')}
            className="bg-ink text-paper px-6 py-3 rounded text-sm hover:bg-ink-soft transition-colors"
          >
            다시 추천받기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      <div className="max-w-xl mx-auto px-6 py-12">
        <button onClick={() => navigate('/chat')} className="text-xs text-ink-muted hover:text-ink mb-8 flex items-center gap-1 transition-colors">
          ← 채팅으로 돌아가기
        </button>
        <h1 className="font-serif text-2xl font-bold text-ink mb-2">추천 도서 피드백</h1>
        <p className="text-sm text-ink-muted mb-8">
          추천받은 도서가 마음에 드셨나요? 평가해 주시면 다음 추천이 더 정확해집니다.
        </p>

        {books.length === 0 ? (
          <div className="text-center py-16 text-ink-muted text-sm">
            <p>추천 결과가 없습니다.</p>
            <button onClick={() => navigate('/chat')} className="mt-4 text-accent underline">
              채팅 페이지로 이동
            </button>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-4 mb-8">
              {books.map((book, i) => (
                <BookFeedbackCard
                  key={book.isbn}
                  book={book}
                  availability={availability}
                  index={i}
                  onChange={handleChange}
                />
              ))}
            </div>

            <div className="mb-6">
              <label className="block text-xs font-medium text-ink-muted uppercase tracking-widest mb-2">
                추가 의견 (선택)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="원하는 책의 방향이나 개선 사항이 있으면 알려주세요."
                rows={3}
                className="w-full border border-ink/10 rounded px-4 py-3 text-sm bg-white resize-none focus:outline-none focus:border-ink/30 placeholder:text-ink-muted"
              />
            </div>

            <button
              onClick={handleSubmit}
              className="w-full bg-ink text-paper py-3 rounded text-sm font-medium hover:bg-ink-soft transition-colors"
            >
              피드백 제출
            </button>
          </>
        )}
      </div>
    </div>
  );
}
