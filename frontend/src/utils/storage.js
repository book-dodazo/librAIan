// localStorage 접근 일원화
// 키 이름을 바꾸거나 저장 구조를 바꿀 때 이 파일 하나만 수정하면 됩니다.

const KEYS = {
  USER:            'user',
  TOKEN:           'token',
  ONBOARDING:      'onboardingData',
  FEEDBACK_HISTORY: 'feedbackHistory',
};

// ── 토큰 ────────────────────────────────────────────
export function getToken() {
  try { return JSON.parse(localStorage.getItem(KEYS.TOKEN) ?? 'null'); }
  catch { return null; }
}

export function saveToken(token) {
  localStorage.setItem(KEYS.TOKEN, JSON.stringify(token));
}

export function removeToken() {
  localStorage.removeItem(KEYS.TOKEN);
}

// ── 사용자 ──────────────────────────────────────────
export function getUser() {
  try { return JSON.parse(localStorage.getItem(KEYS.USER) ?? 'null'); }
  catch { return null; }
}

export function saveUser(user) {
  localStorage.setItem(KEYS.USER, JSON.stringify(user));
}

export function removeUser() {
  localStorage.removeItem(KEYS.USER);
}

// ── 온보딩 데이터 (채워진 슬롯) ─────────────────────
export function getOnboardingData() {
  try { return JSON.parse(localStorage.getItem(KEYS.ONBOARDING) ?? '{}'); }
  catch { return {}; }
}

export function saveOnboardingData(data) {
  const existing = getOnboardingData();
  localStorage.setItem(KEYS.ONBOARDING, JSON.stringify({ ...existing, ...data }));
}

export function clearOnboardingData() {
  localStorage.removeItem(KEYS.ONBOARDING);
}

// ── 피드백 기록 ──────────────────────────────────────
export function getFeedbackHistory() {
  try { return JSON.parse(localStorage.getItem(KEYS.FEEDBACK_HISTORY) ?? '[]'); }
  catch { return []; }
}

export function appendFeedback(feedback) {
  const history = getFeedbackHistory();
  localStorage.setItem(KEYS.FEEDBACK_HISTORY, JSON.stringify([...history, feedback]));
}

export function clearFeedbackHistory() {
  localStorage.removeItem(KEYS.FEEDBACK_HISTORY);
}
