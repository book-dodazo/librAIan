# librAIn 배포 및 개발 진행 상황

## 완료된 작업

### 인프라 / 배포
- [x] EC2 서버에 Docker 설치
- [x] GitLab 저장소 생성 및 GitHub 코드 push
- [x] EC2에 GitLab Runner 설치 및 등록 (shell executor)
- [x] `.gitlab-ci.yml` 작성 (build-backend, build-frontend, deploy)
- [x] `docker-compose.yml` 작성 (backend, frontend 컨테이너)
- [x] GitLab CI/CD Variables 등록 (CLOVA_API_KEY, NARU_API_KEY 등)
- [x] GitLab Container Registry 연동 (이미지 빌드 & push)
- [x] 자동배포 파이프라인 동작 확인 (dev 브랜치 push → 자동 배포)
- [x] 백엔드 컨테이너 정상 실행 확인 (포트 8000)
- [x] 프론트엔드 컨테이너 정상 실행 확인 (포트 80)

### 백엔드
- [x] 사용자 인증 API 구현
  - `POST /api/auth/signup` - 회원가입 (온보딩 데이터 포함)
  - `POST /api/auth/login` - 로그인 (JWT 토큰 발급)
- [x] 프로필 API 구현
  - `GET /api/profile` - 프로필 조회
  - `PUT /api/profile` - 프로필 업데이트
  - `POST /api/profile/feedback` - 피드백 저장
- [x] SQLAlchemy 모델 추가 (users, user_profiles 테이블)
- [x] JWT 인증 미들웨어 추가
- [x] requirements.txt 업데이트 (sqlalchemy, passlib, python-jose, email-validator)

### 프론트엔드
- [x] `httpClient.js` - JWT 토큰 자동 헤더 추가, PUT 메서드 추가
- [x] `authApi.js` - 회원가입/로그인 API 서비스
- [x] `profileApi.js` - 프로필 API 서비스
- [x] `storage.js` - 토큰 관리 함수 추가
- [x] `LoginPage.jsx` - API 연동 + 회원가입 시 온보딩 3단계 추가
- [x] `ProfilePage.jsx` - API에서 프로필 데이터 로드

---

## 남은 작업

### 배포
- [ ] EC2 보안 그룹에서 80번 포트 오픈 요청 (서버 담당자에게)
- [ ] email-validator 추가 후 배포 확인 (현재 에러 중)
- [ ] users, user_profiles 테이블 생성 확인

### 백엔드
- [ ] `useChat.js`에서 프로필 업데이트 연동 (채팅 후 온보딩 데이터 DB 저장)
- [ ] 피드백 저장 시 `addFeedback()` API 호출 연동
- [ ] DB 연결 설정 확인 (Docker 컨테이너 → host PostgreSQL)

### 프론트엔드
- [ ] 채팅 후 온보딩 데이터 DB에 저장 (`updateProfile` 호출)
- [ ] 피드백 제출 시 DB에 저장 (`addFeedback` 호출)
- [ ] 로그인 상태 체크 (토큰 없으면 /login으로 리다이렉트)
- [ ] 앱 기능 완성 (팀원과 협의)

### 나중에 (마감 후)
- [ ] Kubernetes(EKS) 배포로 전환
- [ ] 외부 API 호출 레이어 분리 (마이크로서비스)
- [ ] HTTPS 설정

---

## 현재 아키텍처

```
브라우저
  └── EC2 :80 (nginx, frontend 컨테이너)
        └── /api/* 프록시 → :8000 (FastAPI, backend 컨테이너)
              ├── PostgreSQL (EC2 호스트, 5432)
              └── Elasticsearch (EC2 호스트, 9200)
```

## 주요 명령어

```bash
# 배포 (GitLab)
git push gitlab HEAD:dev

# 컨테이너 상태 확인
sudo docker ps

# 백엔드 로그
sudo docker logs -f librain-backend

# DB 테이블 확인
sudo -u postgres psql -d book_db -c "\dt"

# GitLab Runner 상태
sudo systemctl status gitlab-runner
```
