import { SLOT_DEFS } from '../../constants/slots';

export default function SlotStatusBar({ filledSlots = [] }) {
  return (
    <div className="flex items-center gap-2 px-8 py-2 border-b border-ink/8 bg-paper-2 min-h-9 flex-wrap flex-shrink-0">
      <span className="text-[10px] tracking-widest uppercase text-ink-muted mr-1">슬롯</span>
      {SLOT_DEFS.map(({ key, label }) => (
        <span
          key={key}
          className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium ${
            filledSlots.includes(key)
              ? 'bg-accent text-white'
              : 'bg-paper-3 text-ink-muted'
          }`}
        >
          {label}
        </span>
      ))}
    </div>
  );
}
