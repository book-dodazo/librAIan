import { http } from './httpClient';

/** GET /api/sessions — 내 세션 목록 */
export function getSessions() {
  return http.get('/sessions');
}

/** GET /api/sessions/:id — 세션 상세 (대화 복원용) */
export function getSession(sessionId) {
  return http.get(`/sessions/${sessionId}`);
}

/** DELETE /api/sessions/:id */
export function deleteSession(sessionId) {
  return http.delete(`/sessions/${sessionId}`);
}

/** PATCH /api/sessions/:id — 제목 수정 */
export function renameSession(sessionId, title) {
  return http.patch(`/sessions/${sessionId}`, { title });
}
