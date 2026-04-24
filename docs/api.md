# API 문서

## 개요

librAIan의 REST API 명세를 설명합니다. FastAPI 기반으로 자동 생성된 OpenAPI 문서를 기본으로 하며, 여기서는 주요 엔드포인트의 상세 설명을 제공합니다.

## 기본 정보

- **Base URL**: `http://localhost:8000`
- **API Version**: v1
- **인증**: JWT 토큰 (선택)
- **포맷**: JSON

## 엔드포인트

### 채팅 API

#### POST /api/v1/chat
AI와 채팅하여 도서 추천을 받습니다.

**요청 본문**:
```json
{
  "query": "string",           // 필수: 검색 쿼리
  "user_id": "string",         // 선택: 사용자 ID
  "preferences": {             // 선택: 사용자 선호도
    "genres": ["string"],
    "authors": ["string"]
  }
}
```

**응답**:
```json
{
  "results": [
    {
      "isbn": "string",
      "title": "string",
      "author": "string",
      "description": "string",
      "score": 0.0,
      "availability": true
    }
  ],
  "explanation": "string",
  "query_analysis": {
    "intent": "string",
    "entities": ["string"],
    "processed_query": "string"
  }
}
```

**에러 응답**:
```json
{
  "detail": "string"
}
```

### 추천 API

#### POST /api/v1/recommend
사용자 프로필 기반 개인화 추천을 받습니다.

**요청 본문**:
```json
{
  "user_id": "string",         // 필수: 사용자 ID
  "limit": 10                  // 선택: 추천 개수
}
```

**응답**:
```json
{
  "results": [...],            // BookResult 배열
  "explanation": "string"
}
```

### 프로필 API

#### GET /api/v1/profile/{user_id}
사용자 프로필을 조회합니다.

**파라미터**:
- `user_id` (path): 사용자 ID

**응답**:
```json
{
  "user_id": "string",
  "preferences": {
    "favorite_genres": ["string"],
    "reading_level": "string"
  },
  "reading_history": ["string"]  // ISBN 배열
}
```

#### PUT /api/v1/profile/{user_id}
사용자 프로필을 업데이트합니다.

**요청 본문**:
```json
{
  "user_id": "string",
  "preferences": {
    "favorite_genres": ["string"]
  },
  "reading_history": ["string"]
}
```

### 도서관 API

#### GET /api/v1/libraries
연동된 도서관 목록을 조회합니다.

**응답**:
```json
[
  {
    "library_code": "string",
    "name": "string",
    "location": "string"
  }
]
```

#### GET /api/v1/libraries/{library_code}/availability/{isbn}
특정 도서의 대출 가능 여부를 확인합니다.

**파라미터**:
- `library_code` (path): 도서관 코드
- `isbn` (path): ISBN

**응답**:
```json
{
  "available": true,
  "due_date": "2024-01-01",
  "location": "string"
}
```

### 헬스 체크

#### GET /health
서비스 상태를 확인합니다.

**응답**:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## 데이터 모델

### BookResult
```typescript
interface BookResult {
  isbn: string;
  title: string;
  author: string;
  description?: string;
  score: number;
  availability?: boolean;
}
```

### QueryRequest
```typescript
interface QueryRequest {
  query: string;
  user_id?: string;
  preferences?: {
    genres?: string[];
    authors?: string[];
    [key: string]: any;
  };
}
```

### UserProfile
```typescript
interface UserProfile {
  user_id: string;
  preferences: {
    [key: string]: any;
  };
  reading_history: string[];
}
```

## 에러 코드

| 코드 | 설명 |
|-----|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 |
| 404 | 리소스 없음 |
| 422 | 검증 오류 |
| 500 | 서버 오류 |

## 사용 예시

### Python 클라이언트
```python
import requests

# 채팅 API 호출
response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "query": "힐링 에세이 추천해줘",
        "user_id": "user123"
    }
)

results = response.json()
print(results["results"][0]["title"])
```

### JavaScript 클라이언트
```javascript
// 채팅 API 호출
const response = await fetch('/api/v1/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query: '힐링 에세이 추천해줘',
    user_id: 'user123'
  })
});

const data = await response.json();
console.log(data.results[0].title);
```

## 제한 사항

- **요청 빈도**: 분당 100회 제한
- **결과 개수**: 최대 20개
- **쿼리 길이**: 최대 500자
- **응답 시간**: 평균 2초 이내

## 버전 관리

- **v1**: 현재 버전
- API 변경 시 새로운 버전(v2) 추가 예정
- 이전 버전은 6개월간 유지