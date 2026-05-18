/**
 * 프로필 페이지의 피드백 기록 한 줄
 *
 * props:
 *   feedback - {timestamp, books: [{isbn, rating}], comment}
 */
export default function FeedbackHistoryRow({ feedback }) {
  const ratedBooks = feedback.books?.filter((b) => b.rating !== null) ?? [];
  const avgRating = ratedBooks.length
    ? (ratedBooks.reduce((s, b) => s + b.rating, 0) / ratedBooks.length).toFixed(1)
    : null;

  return (
    <div className="border border-ink/10 rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-ink-muted">
          {new Date(feedback.timestamp).toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
          })}
        </span>
        {avgRating && (
          <span className="text-xs font-medium bg-accent/10 text-accent px-2 py-0.5 rounded">
            평균 {avgRating}점
          </span>
        )}
      </div>
      <p className="text-sm text-ink">
        {feedback.books?.length ?? 0}권 추천 · {ratedBooks.length}권 평가
      </p>
      {feedback.comment && (
        <p className="text-xs text-ink-muted mt-1 italic">"{feedback.comment}"</p>
      )}
    </div>
  );
}
