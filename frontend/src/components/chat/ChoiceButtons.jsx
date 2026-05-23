/**
 * 추가 질문 카드 + 선택지 버튼
 *
 * props:
 *   question  - 질문 텍스트
 *   choices   - [{label, value, ...}] 배열
 *   slots     - pending_slots (선택 시 useChat으로 전달)
 *   onSelect  - (choice, slots) => void
 */
export default function ChoiceButtons({ question, choices = [], slots, onSelect }) {
  return (
    <div className="mt-3 p-4 bg-sky-50 border border-sky-200 rounded-lg text-sm text-sky-900">
      <strong className="block text-[10px] tracking-widest uppercase text-sky-700 mb-2">
        추가 질문
      </strong>
      {question && <p className="mb-3 text-sky-900">{question}</p>}
      <div className="flex flex-wrap gap-2">
        {choices.map((choice, i) => (
          <button
            key={i}
            onClick={() => onSelect(choice, slots)}
            className={`border-[1.5px] rounded-full text-[12.5px] px-4 py-1.5 transition-all hover:bg-sky-100 hover:border-sky-400 ${
              choice.is_escape
                ? 'border-ink/15 text-ink-muted hover:bg-paper-2'
                : 'border-sky-200 text-sky-800 bg-white'
            }`}
          >
            {choice.label}
          </button>
        ))}
      </div>
    </div>
  );
}
