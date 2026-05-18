// HTTP 요청 기반 모듈
// - Base URL, 공통 헤더, 에러 파싱을 한 곳에서 관리합니다.
// - 인증 토큰이나 공통 헤더가 필요해지면 이 파일만 수정하면 됩니다.

// 환경 변수에서 API URL을 읽음
// .env.development → 개발용, .env.production → 배포용
const BASE_URL = import.meta.env.VITE_API_URL ?? '/api';

async function request(path, options = {}) {
  const { headers, ...rest } = options;

  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    ...rest,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail ?? `API 오류 (${response.status})`);
  }

  return response.json();
}

export const http = {
  get:  (path)        => request(path, { method: 'GET' }),
  post: (path, body)  => request(path, { method: 'POST', body: JSON.stringify(body) }),
};
