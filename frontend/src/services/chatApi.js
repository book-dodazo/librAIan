// 챗봇 관련 API 엔드포인트
// 새 엔드포인트가 생기면 이 파일에 추가합니다.

import { http } from './httpClient';

/**
 * POST /api/chat
 *
 * 멀티턴 슬롯 채우기 파이프라인 메인 엔드포인트.
 * 응답 타입(SlotChatResponse)의 주요 필드:
 *   needs_clarification  - true면 clarification_choices 렌더링
 *   is_confirmation      - true면 inferred_summary 확인 카드 렌더링
 *   ready_for_rag        - true면 search_results 표시
 *
 * @param {Object} params
 * @param {string}   params.query
 * @param {Array}    params.history
 * @param {Object}   params.context
 * @param {Object}   params.selected_choice
 * @param {Array}    params.pending_slots
 * @param {boolean}  params.confirm_inferred
 * @param {Object}   params.user_profile
 */
export function sendChatMessage(params) {
  return http.post('/chat', {
    query:            params.query,
    history:          params.history          ?? [],
    context:          params.context          ?? null,
    selected_choice:  params.selected_choice  ?? null,
    pending_slots:    params.pending_slots     ?? null,
    confirm_inferred: params.confirm_inferred  ?? null,
    user_profile:     params.user_profile      ?? null,
  });
}

/** GET /api/health — 백엔드 연결 확인 */
export async function checkHealth() {
  try {
    await http.get('/health');
    return true;
  } catch {
    return false;
  }
}
