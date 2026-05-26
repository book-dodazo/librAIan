import { SLOT_LABELS } from '../../constants/slots';

/**
 * 값 포맷팅 — null/빈값 → "지정 없음", 배열/객체 → 읽기 좋은 문자열
 */
function formatValue(value) {
  if (value === null || value === undefined || value === '' || value === 'null' || value === 'undefined') {
    return null; // → "지정 없음" 처리
  }

  // 배열
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value
      .map((v) => {
        if (typeof v === 'object' && v !== null) {
          return v.sub || v.main || v.title || v.name || JSON.stringify(v);
        }
        return String(v);
      })
      .join(', ');
  }

  // 객체
  if (typeof value === 'object') {
    return value.sub || value.main || value.title || value.name || JSON.stringify(value);
  }

  const str = String(value);
  if (str === 'null' || str === 'undefined' || str === '') return null;
  return str;
}

export default function SlotRow({ slotKey, value }) {
  const formatted = formatValue(value);
  const isEmpty = formatted === null;

  return (
    <div className="flex items-center justify-between py-3 border-b border-ink/8 last:border-0">
      <span className="text-sm text-ink-muted">{SLOT_LABELS[slotKey] ?? slotKey}</span>
      {isEmpty ? (
        <span className="text-sm text-ink-muted/40 italic">지정 없음</span>
      ) : (
        <span className="text-sm text-ink font-medium bg-paper-2 px-3 py-1 rounded-full max-w-[60%] text-right truncate">
          {formatted}
        </span>
      )}
    </div>
  );
}
