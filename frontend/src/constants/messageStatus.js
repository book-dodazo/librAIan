// 어시스턴트 메시지 상태 태그 스타일과 레이블
// MessageBubble에서 사용

export const STATUS_STYLES = {
  clarification: 'bg-sky-50 text-sky-800 border-sky-200',
  'rag-ready':   'bg-yellow-50 text-yellow-800 border-yellow-200',
  error:         'bg-red-50 text-red-800 border-red-200',
  general:       'bg-violet-50 text-violet-800 border-violet-200',
};

export const STATUS_LABELS = {
  clarification: '추가 질문',
  'rag-ready':   '추천 완료',
  error:         '오류',
  general:       '일반 응답',
};

/** message 객체를 받아 상태 타입 문자열을 반환 */
export function getStatusType(message) {
  if (message.error) return 'error';
  if (message.hasResults) return 'rag-ready';
  if (message.isClarification) return 'clarification';
  return null;
}
