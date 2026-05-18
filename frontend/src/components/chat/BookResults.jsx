import { useNavigate } from 'react-router-dom';

/**
 * 도서 추천 결과 카드
 *
 * props:
 *   results         - search_results: [{rank, isbn, score}]
 *   availabilityIndex - availability_index: {isbn: {has_book, loan_available}}
 */
export default function BookResults({ results = [], availabilityIndex = {} }) {
  const navigate = useNavigate();

  if (results.length === 0) return null;

  return (
    <div className="mt-3">
      <p className="text-[10px] tracking-widest uppercase text-ink-muted mb-3">추천 도서</p>
      <div className="flex flex-col gap-2">
        {results.map((book, i) => {
          const avail = availabilityIndex[book.isbn];
          const available = avail?.loan_available === 'Y';
          const hasBook = avail?.has_book === 'Y';

          return (
            <div
              key={book.isbn ?? i}
              className="bg-white border border-ink/10 rounded-lg px-4 py-3 flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="w-7 h-7 rounded bg-paper-2 flex items-center justify-center text-xs font-bold text-ink-muted flex-shrink-0">
                  {book.rank ?? i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink truncate">
                    {/* ISBN으로 실제 책 제목을 가져오려면 도서 API 연동 필요 */}
                    ISBN {book.isbn}
                  </p>
                  {book.score !== undefined && (
                    <p className="text-xs text-ink-muted">관련도 {book.score.toFixed(2)}</p>
                  )}
                </div>
              </div>

              {avail ? (
                <span
                  className={`text-[11px] px-2.5 py-1 rounded-full font-medium flex-shrink-0 ${
                    available
                      ? 'bg-green-50 text-green-700 border border-green-100'
                      : hasBook
                      ? 'bg-orange-50 text-orange-700 border border-orange-100'
                      : 'bg-paper-3 text-ink-muted'
                  }`}
                >
                  {available ? '대출 가능' : hasBook ? '대출 중' : '미보유'}
                </span>
              ) : (
                <span className="text-[11px] text-ink-muted flex-shrink-0">확인 중</span>
              )}
            </div>
          );
        })}
      </div>

      {/* 피드백 버튼 */}
      <button
        onClick={() => navigate('/feedback', { state: { results, availability: availabilityIndex } })}
        className="mt-3 w-full text-xs text-ink-muted border border-ink/10 rounded py-2.5 hover:bg-paper-2 transition-colors"
      >
        이 추천에 대한 피드백 남기기 →
      </button>
    </div>
  );
}
