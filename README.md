# librAIan 🏛️

도서관 맥락 기반 AI 도서 큐레이션 시스템


## 프로젝트 구조

```
ai-book-curation/
├── .github/                # GitHub Actions, PR 템플릿
├── data_pipeline/         # [A 파트] 서지 및 리뷰 데이터 전처리, 적재, 인덱싱
├── evaluation/            # [B 파트] 실험 프레임워크, 메트릭, 평가 데이터
├── backend/               # [C 파트 주도] FastAPI 서버 및 모듈 통합
├── frontend/              # [C 파트] 사용자 인터페이스
├── experiments/           # 추가: 실험 노트북 및 RQ 검증 자료
├── docs/                  # 프로젝트 설계 문서 및 아키텍처
├── docker-compose.yml     # 로컬 개발 인프라 구성
└── .gitignore             # 무시할 파일 목록
```

## 폴더 설명

- **.github/**: CI/CD 워크플로우와 PR 템플릿.
- **data_pipeline/**: 크롤러, ETL, 임베딩/인덱싱 배치.
- **evaluation/**: 평가셋, 메트릭 로직, 리랭커 비교 실험.
- **backend/**: FastAPI API 서버, 서비스 오케스트레이션, DB/AI 모듈 통합.
- **frontend/**: React 기반 UI 클라이언트.
- **experiments/**: Jupyter 노트북, 실험 기록, 결과 시각화.
- **docs/**: 아키텍처, 평가 방법, API 문서.

## 설치 및 실행

### 1. 환경 준비
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 2. 백엔드 설치
```bash
cd backend
pip install -r ../requirements.txt
```

### 3. 프론트엔드 설치
```bash
cd frontend
npm install
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
# 필요한 키 입력
```

### 5. Docker로 서비스 실행
```bash
docker-compose up -d
```

## 개발 규칙

### 브랜치 전략
- `main`: 배포 가능한 안정 버전
- `dev`: 일상 개발 통합 브랜치
- `feat/[module-name]`: 새로운 기능 개발
- `fix/[module-name]`: 버그 수정
- `docs/[module-name]`: 문서 변경
- `test/[module-name]`: 테스트 추가/수정

### 커밋 메시지 규칙
- 형식: `[type] scope: summary`
- type: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
- scope: 변경 대상 모듈 또는 컴포넌트
- summary: 한 줄 요약

예시:
```bash
git commit -m "feat(chat): 채팅 서비스 오케스트레이션 추가"
git commit -m "fix(api): 라이브러리 대출 가능 조회 오류 수정"
git commit -m "docs(readme): 프로젝트 구조 설명 업데이트"
```

### PR 규칙
- 항상 `dev` 브랜치로 PR 발행
- PR 제목은 간결하고 목적이 분명하게 작성
- 변경 내용 요약, 테스트 방법, 관련 이슈 명시
- 최소 1명 이상 리뷰 승인 필요
- CI 통과 후 머지

### 기타
- `.env` 파일은 절대 커밋하지 않습니다.
- 루트 `docker-compose.yml`로 로컬 인프라를 실행합니다.

