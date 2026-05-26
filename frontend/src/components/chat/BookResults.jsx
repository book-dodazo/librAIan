import { useNavigate } from 'react-router-dom';

/**
 * 도서 추천 결과 카드
 *
 * props:
 *   results - search_results: [{
 *     isbn, title, author, publisher,
 *     cover_url, book_intro, recommendation_reason,
 *     loan_available, has_book, final_rank, final_score
 *   }]
 *   availabilityIndex - (선택) availability_index: {isbn: {has_book, loan_available}}
 *                       book 객체 안에 이미 포함된 경우 우선 사용
 */
export default function BookResults({ results = [], availabilityIndex = {} }) {
  const navigate = useNavigate();

  if (results.length === 0) return null;

  return (
    <div className="mt-3">
      <p className="text-[10px] tracking-widest uppercase text-ink-muted mb-3">추천 도서</p>
      <div className="flex flex-col gap-3">
        {results.map((book, i) => {
          // availability: book 객체 안에 있으면 우선 사용, 없으면 availabilityIndex fallback
          const avail = availabilityIndex[book.isbn] ?? {};
          const loanAvailable = book.loan_available ?? avail.loan_available;
          const hasBook = book.has_book ?? avail.has_book;

          const available = loanAvailable === 'Y';
          const inStock  = hasBook === 'Y';
          const checked  = loanAvailable !== undefined && loanAvailable !== '-';

          return (
            <div
              key={book.isbn ?? i}
              className="bg-white border border-ink/10 rounded-xl overflow-hidden"
            >
              {/* 상단: 표지 + 기본 정보 */}
              <div className="flex gap-3 p-4">
                {/* 책 표지 */}
                {book.cover_url ? (
                  <img
                    src={book.cover_url}
                    alt={book.title}
                    className="w-16 h-22 object-cover rounded flex-shrink-0 shadow-sm"
                    style={{ height: '88px' }}
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                ) : (
                  <div className="w-16 flex-shrink-0 bg-paper-2 rounded flex items-center justify-center"
                       style={{ height: '88px' }}>
                    <span className="text-ink-muted text-xs">📚</span>
                  </div>
                )}

                {/* 제목 / 저자 / 대출 상태 */}
                <div className="flex-1 min-w-0 flex flex-col justify-between">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold text-ink leading-snug line-clamp-2">
                        {book.title || `ISBN ${book.isbn}`}
                      </p>
                      {/* 순위 뱃지 */}
                      <span className="w-5 h-5 rounded-full bg-paper-2 flex items-center justify-center text-[10px] font-bold text-ink-muted flex-shrink-0 mt-0.5">
                        {book.final_rank ?? i + 1}
                      </span>
                    </div>
                    {book.author && (
                      <p className="text-xs text-ink-muted mt-0.5 truncate">{book.author}</p>
                    )}
                    {book.publisher && (
                      <p className="text-xs text-ink-muted/70 truncate">{book.publisher}</p>
                    )}
                  </div>

                  {/* 별점 */}
                  {book.review_score != null ? (
                    <p className="text-xs text-amber-500 mt-0.5">
                      {'★'.repeat(Math.floor(book.review_score))}{'☆'.repeat(5 - Math.floor(book.review_score))}
                      <span className="text-ink-muted ml-1">{book.review_score.toFixed(1)}</span>
                    </p>
                  ) : (
                    <p className="text-xs text-ink-muted/50 mt-0.5">{'☆'.repeat(5)}<span className="ml-1">—</span></p>
                  )}

                  {/* 대출 가능 여부 */}
                  {checked ? (
                    <span
                      className={`self-start mt-1.5 text-[11px] px-2 py-0.5 rounded-full font-medium ${
                        available
                          ? 'bg-green-50 text-green-700 border border-green-100'
                          : inStock
                          ? 'bg-orange-50 text-orange-700 border border-orange-100'
                          : 'bg-paper-3 text-ink-muted border border-ink/10'
                      }`}
                    >
                      {available ? '대출 가능' : inStock ? '대출 중' : '미보유'}
                    </span>
                  ) : (
                    <span className="self-start mt-1.5 text-[11px] text-ink-muted/60">
                      대출 정보 없음
                    </span>
                  )}
                </div>
              </div>

              {/* 추천 이유 */}
              {book.recommendation_reason && (
                <div className="px-4 pb-3">
                  <div className="bg-paper-2/60 rounded-lg p-3">
                    <p className="text-[11px] font-medium text-ink-muted mb-1">추천 이유</p>
                    <p className="text-xs text-ink leading-relaxed">
                      {book.recommendation_reason}
                    </p>
                  </div>
                </div>
              )}

              {/* 독자 리뷰 */}
              <div className="px-4 pb-4">
                <div className="rounded-lg p-3 border border-ink/8 bg-white">
                  <p className="text-[11px] font-medium text-ink-muted mb-1">📝 독자 리뷰</p>
                  {book.reader_review ? (
                    <p className="text-xs text-ink-muted leading-relaxed">{book.reader_review}</p>
                  ) : (
                    <p className="text-xs text-ink-muted/50 italic">리뷰 정보 없음</p>
                  )}
                </div>
              </div>

              {/* 책 소개 (있을 경우) */}
              {book.book_intro && !book.recommendation_reason && (
                <div className="px-4 pb-4">
                  <p className="text-xs text-ink-muted leading-relaxed line-clamp-3">
                    {book.book_intro}
                  </p>
                </div>
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
