// HTTP 요청 기반 모듈
// - Base URL, 공통 헤더, 에러 파싱을 한 곳에서 관리합니다.
// - 인증 토큰이나 공통 헤더가 필요해지면 이 파일만 수정하면 됩니다.

// 환경 변수에서 API URL을 읽음
// .env.development → 개발용, .env.production → 배포용
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

function getAuthHeader() {
  try {
    const token = JSON.parse(localStorage.getItem('token') ?? 'null');
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function request(path, options = {}) {
  const { headers, ...rest } = options;

  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
      ...headers,
    },
    ...rest,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail = errorData.detail;
    let message;
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      // Pydantic 유효성 검사 에러: [{ loc, msg, type }, ...]
      message = detail.map(d => d.msg ?? String(d)).join(', ');
    } else {
      message = `API 오류 (${response.status})`;
    }
    throw new Error(message);
  }

  return response.json();
}

export const http = {
  get:    (path)       => request(path, { method: 'GET' }),
  post:   (path, body) => request(path, { method: 'POST',   body: JSON.stringify(body) }),
  put:    (path, body) => request(path, { method: 'PUT',    body: JSON.stringify(body) }),
  patch:  (path, body) => request(path, { method: 'PATCH',  body: JSON.stringify(body) }),
  delete: (path)       => fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
  }).then((res) => { if (!res.ok) throw new Error(`API 오류 (${res.status})`); }),
};
