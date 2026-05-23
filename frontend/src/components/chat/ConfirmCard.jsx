/**
 * inferred 슬롯 확인 카드
 *
 * 백엔드가 사용자 말에서 유추한 값을 확인받을 때 표시됩니다.
 * inferred_summary: [{slot, value, label}]
 *
 * props:
 *   summary  - inferred_summary 배열
 *   onConfirm - (confirmed: boolean) => void
 */
export default function ConfirmCard({ summary = [], onConfirm }) {
  return (
    <div className="mt-3 p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-900">
      <strong className="block text-[10px] tracking-widest uppercase text-yellow-700 mb-2">
        이렇게 이해했어요
      </strong>
      <ul className="mb-4 flex flex-col gap-1">
        {summary.map((item, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="text-xs text-yellow-600 bg-yellow-100 px-2 py-0.5 rounded">
              {item.label ?? item.slot}
            </span>
            <span className="font-medium">{item.value}</span>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button
          onClick={() => onConfirm(true)}
          className="flex-1 bg-yellow-500 text-white rounded py-2 text-xs font-medium hover:bg-yellow-600 transition-colors"
        >
          맞아요, 진행해 주세요
        </button>
        <button
          onClick={() => onConfirm(false)}
          className="flex-1 border border-yellow-300 text-yellow-800 rounded py-2 text-xs hover:bg-yellow-100 transition-colors"
        >
          다시 말할게요
        </button>
      </div>
    </div>
  );
}
