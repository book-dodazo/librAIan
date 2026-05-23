import { RATINGS } from '../../constants/feedback';

/**
 * 피드백 페이지의 개별 도서 평가 카드
 *
 * props:
 *   book         - {isbn, rank, score, _rating}
 *   availability - availability_index 전체 객체
 *   index        - 순서 (rank 없을 때 대체)
 *   onChange     - (isbn, field, value) => void
 */
export default function BookFeedbackCard({ book, availability, index, onChange }) {
  const avail = availability?.[book.isbn];
  const isAvailable = avail?.loan_available === 'Y';

  return (
    <div className="border border-ink/10 rounded-lg p-5 bg-white">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-ink-muted bg-paper-2 px-2 py-0.5 rounded">
              #{book.rank ?? index + 1}
            </span>
            {avail && (
              <span
                className={`text-xs px-2 py-0.5 rounded font-medium ${
                  isAvailable
                    ? 'bg-green-50 text-green-700 border border-green-100'
                    : 'bg-red-50 text-red-600 border border-red-100'
                }`}
              >
                {isAvailable ? '대출 가능' : '대출 중'}
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-ink">ISBN: {book.isbn}</p>
          {book.score !== undefined && (
            <p className="text-xs text-ink-muted mt-0.5">관련도 점수: {book.score.toFixed(2)}</p>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        {RATINGS.map((r) => (
          <button
            key={r.value}
            onClick={() => onChange(book.isbn, 'rating', r.value)}
            className={`flex-1 flex flex-col items-center gap-1 py-2.5 rounded border text-xs transition-all ${
              book._rating === r.value
                ? 'border-accent bg-accent/5 text-accent font-medium'
                : 'border-ink/10 text-ink-muted hover:border-ink/25'
            }`}
          >
            <span className="text-lg">{r.emoji}</span>
            {r.label}
          </button>
        ))}
      </div>
    </div>
  );
}
