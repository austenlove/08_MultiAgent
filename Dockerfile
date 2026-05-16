# [/Dockerfile] - 루트 디렉토리에 생성
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 백엔드와 프론트엔드 의존성을 한꺼번에 설치
COPY backend/requirements.txt ./backend_req.txt
COPY frontend/requirements.txt ./frontend_req.txt
RUN pip install --no-cache-dir -r backend_req.txt -r frontend_req.txt

# 전체 프로젝트 코드 복사
COPY . .

EXPOSE 8501

# 통합형 Streamlit 앱 실행
CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
