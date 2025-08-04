# 1. 베이스 이미지를 Ubuntu 22.04(Jammy) 기반으로 변경
FROM python:3.9-slim-jammy

# 2. Inkscape 최신 안정 버전을 PPA를 통해 설치
RUN apt-get update && \
    apt-get install -y software-properties-common gnupg && \
    add-apt-repository ppa:inkscape.dev/stable && \
    apt-get update && \
    apt-get install -y inkscape && \
    # 이미지 용량을 줄이기 위해 apt 캐시 삭제
    rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 프로젝트 파일 복사
COPY . .

# 6. gunicorn으로 앱 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app_for_Render:app"]