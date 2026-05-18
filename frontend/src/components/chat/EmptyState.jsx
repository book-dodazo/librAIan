export default function EmptyState() {
  return (
    <div className="m-auto text-center max-w-xs fade-up">
      <span className="text-5xl block mb-5">📚</span>
      <h2 className="font-serif text-2xl font-bold text-ink mb-3">어떤 책을 찾고 계신가요?</h2>
      <p className="text-sm text-ink-muted leading-relaxed">
        읽고 싶은 책의 주제, 분위기, 목적을 자유롭게 말해주세요.
        <br />
        맞춤 도서를 찾아드립니다.
      </p>
    </div>
  );
}
