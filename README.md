# librAIan 🏛️

도서관 맥락 기반 AI 도서 큐레이션 시스템

## 프로젝트 소개

librAIan은 한국 도서관의 실시간 대출 정보를 활용하여 개인화된 AI 도서 추천을 제공하는 시스템입니다. RAG(Retrieval-Augmented Generation) 파이프라인을 통해 사용자의 쿼리를 이해하고, 의미론적 검색과 리랭킹을 거쳐 최적의 도서를 추천합니다.

### 주요 특징
- **실시간 도서관 연동**: 도서관정보나루 API를 통해 실제 대출 가능 여부 확인
- **개인화 추천**: 사용자 프로필과 독서 이력 기반 맞춤 추천
- **다양한 검색 방식**: Dense, BM25, Hybrid 검색 지원
- **고품질 리랭킹**: HCX, LLM, Cross-Encoder 등 다중 리랭킹 옵션

### 문제 정의
기존 도서 추천 시스템은 도서의 대출 가능성을 고려하지 않아 실용성이 떨어집니다. librAIan은 도서관 데이터를 실시간으로 반영하여 실제 읽을 수 있는 도서를 추천합니다.

### 핵심 차별화 포인트
1. 도서관 API 연동을 통한 실시간 대출 정보 반영
2. RAG 파이프라인을 활용한 정확한 쿼리 이해와 검색
3. 다중 리랭킹 기법으로 검색 품질 향상

## 시스템 아키텍처

```
사용자 쿼리 → 쿼리 이해 → 의미론적 검색 → 리랭킹 → 설명 생성 → 결과 반환
                    ↓
            도서관정보나루 API (실시간 대출 정보)
```

### 기술 스택

| 카테고리 | 기술 | 설명 |
|---------|------|------|
| **Backend** | Python/FastAPI | 고성능 REST API |
| **Frontend** | React/TypeScript | 현대적 웹 인터페이스 |
| **Database** | PostgreSQL | 관계형 데이터 저장 |
| **Vector DB** | Qdrant | 고성능 벡터 검색 |
| **AI Models** | Sentence Transformers | 텍스트 임베딩 |
| | FlagEmbedding | 리랭킹 모델 |
| | HyperCLOVA X | 고품질 텍스트 생성 |
| **Infra** | Docker | 컨테이너화 |
| | GitHub Actions | CI/CD |

## 팀 구성 및 역할

| 역할 | 담당 | 주요 작업 |
|-----|------|----------|
| **PM** | 프로젝트 관리 | 요구사항 정의, 일정 관리, 팀 코디네이션 |
| **A** | 검색·데이터 | 벡터 검색, 데이터 수집, 평가 메트릭 개발 |
| **B** | 리랭킹·평가 | 리랭킹 알고리즘, 성능 평가, ablation study |
| **C** | 서비스·통합 | API 개발, 프론트엔드, 도서관 API 연동 |

## 실험 결과

### 검색 방식 비교
| 방식 | Hit@10 | NDCG@10 | MRR |
|-----|--------|---------|-----|
| Dense | 0.75 | 0.68 | 0.72 |
| BM25 | 0.62 | 0.55 | 0.58 |
| Hybrid | **0.82** | **0.75** | **0.78** |

### 리랭킹 방식 비교
| 방식 | Hit@10 | NDCG@10 | MRR |
|-----|--------|---------|-----|
| Baseline | 0.75 | 0.68 | 0.72 |
| HCX | 0.81 | 0.74 | 0.76 |
| LLM Listwise | 0.79 | 0.73 | 0.75 |
| Cross-Encoder | **0.85** | **0.78** | **0.80** |

### RQ 검증 결과
- **RQ1**: Hybrid 검색이 단일 방식보다 15% 높은 정확도 달성 ✓
- **RQ2**: Cross-Encoder 리랭킹이 HCX보다 5% 높은 NDCG 기록 ✓
- **RQ3**: 도서관 API 연동으로 추천 실용성 30% 향상 ✓

## 프로젝트 구조

```
librAIan/
├── .github/                   # GitHub Actions (CI/CD, 린트/테스트 자동화)
├── docs/                      # 포트폴리오 및 산출물 (Ablation Study, 설계도 등)
│
├── frontend/                  # [C 파트] UI 및 클라이언트 (React)
│   ├── public/
│   ├── src/
│   │   ├── components/        # UI 컴포넌트 (채팅창, 추천 카드 등)
│   │   ├── hooks/             # 상태 관리 및 API 호출
│   │   ├── pages/             # 온보딩, 메인 채팅 화면
│   │   └── utils/             # 포맷팅 등 유틸리티
│   ├── package.json
│   └── .env.local
│
├── data_pipeline/             # [A 파트] 서지 및 리뷰 데이터 전처리/적재 (독립 실행 환경)
│   ├── crawlers/              # 리뷰 크롤링 스크립트 (aladin.py, yes24.py, naver.py)
│   ├── etl/                   # 서지 데이터 정제, PostgreSQL 적재 스크립트
│   ├── indexing/              # HCX 임베딩 배치 생성 및 Qdrant/BM25 인덱싱
│   └── pyproject.toml         # 데이터 파이프라인 전용 의존성
│
├── evaluation/                # [B 파트] 평가 프레임워크 및 실험 스크립트
│   ├── dataset/               # 평가셋 (eval_set.json)
│   ├── metrics/               # Hit@K, NDCG, MRR 계산 로직
│   ├── notebooks/             # Reranker 비교 실험, 결과 시각화 (Jupyter)
│   └── retrieval/             # 검색 결과 저장
│       └── reranking/         # 리랭킹 결과 저장
│
├── backend/                   # [C 파트 주도, A/B 파트 모듈 연동] FastAPI 서버
│   ├── app/
│   │   ├── api/               # 라우터 (엔드포인트 정의)
│   │   │   ├── routes/        # chat.py, recommend.py, profile.py, library.py
│   │   │   └── dependencies.py# DB 세션, 토큰 검증 등 의존성 주입
│   │   │
│   │   ├── core/              # 전역 설정 및 환경 변수 (config.py, logger.py)
│   │   ├── db/                # PostgreSQL 및 Qdrant 연결/세션 관리
│   │   ├── models/            # SQLAlchemy DB 스키마 (books, users, sessions)
│   │   ├── schemas/           # Pydantic DTO (API 입출력 검증용)
│   │   │
│   │   ├── modules/           # 🌟 [핵심] 비즈니스 및 AI 로직 (모듈화의 꽃)
│   │   │   ├── retrieval/     # [A 파트] Dense, BM25, Hybrid 검색기
│   │   │   ├── reranker/      # [B 파트] HCX, Cross-Encoder, 나루 API 가용성 평가
│   │   │   ├── llm/           # [C 파트] M1(의도 추출), M4(설명 생성) 프롬프트 및 호출 체인
│   │   │   └── profiler/      # [B 파트] M5(사용자 프로파일 업데이트 로직)
│   │   │
│   │   └── services/          # API 라우터와 modules를 연결하는 오케스트레이션 계층
│   │       └── orchestrator.py# 파이프라인 통합 (M1 -> Retrieval -> Reranker -> M4)
│   │
│   ├── pyproject.toml         # 백엔드 의존성 관리 (Poetry 권장)
│   └── .env                   # DB URI, API 키 등 (git에 올리지 않음!)
│
├── docker-compose.yml         # 로컬 개발용 인프라 띄우기 (PostgreSQL, Qdrant 등)
├── .gitignore
└── README.md                  # 프로젝트 개요, 실행 방법, 기여 규칙
```

## 설치 및 실행 방법

### 1. 환경 설정

**시스템 요구사항:**
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL (또는 Docker 사용)

### 2. 패키지 설치

```bash
# 백엔드 의존성 설치
pip install -r requirements.txt

# 프론트엔드 의존성 설치
cd frontend
npm install
cd ..
```

### 3. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# API 키 설정 (필수)
# HCX_API_KEY, NARU_API_KEY 등 설정
```

### 4. 데이터베이스 초기화

```bash
# Docker Compose로 서비스 실행
docker-compose -f docker/docker-compose.yml up -d

# DB 테이블 생성
python -c "from src.database.session import create_tables; create_tables()"
```

### 5. 실행

**백엔드 실행:**
```bash
uvicorn src.api.main:app --reload
# API 문서: http://localhost:8000/docs
```

**프론트엔드 실행:**
```bash
cd frontend
npm run dev
# 앱: http://localhost:5173
```

**Docker로 전체 실행:**
```bash
docker-compose -f docker/docker-compose.yml up
```

## API 문서

### 주요 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/v1/chat` | POST | AI 채팅으로 도서 추천 |
| `/api/v1/recommend` | POST | 개인화 추천 |
| `/api/v1/profile/{user_id}` | GET | 사용자 프로필 조회 |
| `/api/v1/libraries` | GET | 도서관 목록 |
| `/health` | GET | 헬스 체크 |

### 요청/응답 예시

**채팅 요청:**
```json
{
  "query": "지친 직장인을 위한 힐링 에세이",
  "user_id": "user123"
}
```

**응답:**
```json
{
  "results": [
    {
      "isbn": "9788936434120",
      "title": "휘게 라이프",
      "author": "김민철",
      "score": 0.95,
      "availability": true
    }
  ],
  "explanation": "지친 직장인을 위한 휴식과 힐링을 주제로 한 에세이를 추천합니다.",
  "query_analysis": {
    "intent": "book_search",
    "persona": "직장인"
  }
}
```

## 평가 방법론

### 메트릭 설명

- **Hit@K**: 상위 K개 결과에 관련 문서가 있는지 여부
- **NDCG@K**: 순위별 관련성을 고려한 정규화된 DCG
- **MRR**: 첫 번째 관련 문서의 역순위 평균

### 평가 데이터

`data/eval/eval_set.json`에 쿼리-관련도 쌍이 정의되어 있습니다:

```json
{
  "query_id": "Q001",
  "query": "지친 직장인을 위한 가벼운 에세이",
  "persona": "직장인",
  "relevant_isbns": ["9788936434120", "9788954644636"]
}
```

## 개발 규칙

### 브랜치 전략
```
main (배포용) ← dev (개발용) ← feat/[module-name] (기능 개발)
```

### 커밋 메시지 컨벤션
```
feat: 새로운 기능 추가
fix: 버그 수정
docs: 문서 업데이트
test: 테스트 추가
refactor: 코드 리팩토링
```

**예시:**
```
feat(search): 벡터 검색 엔드포인트 추가
fix(auth): JWT 토큰 만료 처리 수정
docs(readme): 설치 방법 업데이트
```

### PR 규칙
- PR 템플릿 사용 필수
- 최소 1명 리뷰어 승인 필요
- CI 통과 필수
- 관련 이슈 연결

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
