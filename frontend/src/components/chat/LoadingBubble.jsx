export default function LoadingBubble() {
  return (
    <div className="flex gap-3.5 self-start fade-up">
      <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-base flex-shrink-0 mt-0.5">
        📖
      </div>
      <div className="bubble-assistant bg-white border border-ink/10 shadow-sm px-4 py-3">
        <span className="inline-flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 bg-ink-muted rounded-full animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}
