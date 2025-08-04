# 1. 베이스 이미지 선택 (Python 3.9)
FROM python:3.9-slim

# 2. 시스템 패키지 업데이트 및 AppImage 실행에 필요한 라이브러리 설치
RUN apt-get update && \
    apt-get install -y wget fuse libgtk-3-0 libglib2.0-0 && \
    # 이미지 용량을 줄이기 위해 apt 캐시 삭제
    rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. Inkscape 1.3.2 AppImage 다운로드 및 실행 권한 부여
RUN wget -O inkscape.AppImage https://media.inkscape.org/dl/resources/file/inkscape-1.3.2_2023-11-25_091e20ef0f-x86_64.AppImage && \
    chmod +x inkscape.AppImage

# 5. AppImage를 'inkscape' 명령어로 실행할 수 있도록 심볼릭 링크 생성
RUN ln -s /app/inkscape.AppImage /usr/bin/inkscape

# 6. Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. 프로젝트 파일 복사
COPY . .

# 8. gunicorn으로 앱 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app_for_Render:app"]