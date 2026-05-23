# ── 베이스 이미지 ─────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 (psycopg2-binary가 libpq 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 복사 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

EXPOSE 8000

# --host 0.0.0.0 필수 — 컨테이너 외부에서 접근 가능하게
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
