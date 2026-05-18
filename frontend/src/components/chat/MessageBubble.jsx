import ChoiceButtons from './ChoiceButtons';
import ConfirmCard from './ConfirmCard';
import BookResults from './BookResults';
import { STATUS_STYLES, STATUS_LABELS, getStatusType } from '../../constants/messageStatus';

export default function MessageBubble({ message, onSelectChoice, onConfirm }) {
  const isUser = message.role === 'user';
  const statusType = isUser ? null : getStatusType(message);

  if (isUser) {
    return (
      <div className="flex gap-3.5 flex-row-reverse self-end fade-up max-w-[720px]">
        <div className="w-8 h-8 rounded-full bg-ink flex items-center justify-center font-serif text-paper font-bold text-xs flex-shrink-0 mt-0.5">
          나
        </div>
        <div className="bubble-user bg-ink text-paper px-4 py-3 text-[14.5px] leading-relaxed max-w-[520px]">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3.5 self-start fade-up max-w-[720px]">
      <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-base flex-shrink-0 mt-0.5">
        📖
      </div>
      <div className="flex flex-col max-w-[540px]">
        {statusType && (
          <span className={`inline-flex items-center gap-1 text-[11px] tracking-wide px-2.5 py-0.5 rounded-full border font-medium mb-1.5 self-start ${STATUS_STYLES[statusType]}`}>
            {STATUS_LABELS[statusType]}
          </span>
        )}
        <div className="bubble-assistant bg-white text-ink border border-ink/10 shadow-sm px-4 py-3 text-[14.5px] leading-relaxed">
          {message.text}
          {message.isConfirmation && message.inferred_summary && (
            <ConfirmCard summary={message.inferred_summary} onConfirm={onConfirm} />
          )}
          {message.isClarification && message.choices && (
            <ChoiceButtons
              question={message.clarification_question}
              choices={message.choices}
              slots={message.pending_slots}
              onSelect={onSelectChoice}
            />
          )}
          {message.hasResults && (
            <BookResults results={message.search_results} availabilityIndex={message.availability_index} />
          )}
        </div>
      </div>
    </div>
  );
}
