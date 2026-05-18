import { SLOT_LABELS } from '../../constants/slots';

/**
 * 프로필 페이지의 슬롯 한 줄 표시
 *
 * props:
 *   slotKey - 슬롯 키 (e.g. 'topic')
 *   value   - 슬롯 값 문자열
 */
export default function SlotRow({ slotKey, value }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-ink/8 last:border-0">
      <span className="text-sm text-ink-muted">{SLOT_LABELS[slotKey] ?? slotKey}</span>
      <span className="text-sm text-ink font-medium bg-paper-2 px-3 py-1 rounded-full">
        {value}
      </span>
    </div>
  );
}
