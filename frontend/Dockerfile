# ── Stage 1: 빌드 ────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# 의존성 먼저 복사 (레이어 캐시 활용 — 코드만 바뀌면 npm install 생략)
COPY package*.json ./
RUN npm ci

COPY . .

# VITE_API_URL은 빌드 시점에 결정됨.
# K8s/nginx 환경에서는 /api (nginx가 backend 서비스로 프록시).
# 분리 호스팅이면 빌드 시 --build-arg VITE_API_URL=https://... 로 전달.
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ── Stage 2: 서빙 ────────────────────────────────────────────
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
