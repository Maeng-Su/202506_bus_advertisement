# 1. 베이스 이미지를 공식 Ubuntu 22.04(Jammy)로 지정
FROM ubuntu:jammy

# 2. 시스템 패키지 업데이트 및 Python 3.9 와 Inkscape 설치
RUN apt-get update && \
    # DEBIAN_FRONTEND=noninteractive: 설치 중 질문이 나오는 것을 방지
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    software-properties-common \
    gnupg \
    && \
    # Python 3.9 설치를 위한 deadsnakes PPA 추가
    add-apt-repository ppa:deadsnakes/ppa && \
    # Inkscape 최신 버전을 위한 PPA 추가
    add-apt-repository ppa:inkscape.dev/stable && \
    # 저장소 목록 다시 업데이트
    apt-get update && \
    # Python 3.9, pip, Inkscape 설치
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.9 \
    python3-pip \
    inkscape \
    && \
    # 이미지 용량을 줄이기 위해 apt 캐시 삭제
    rm -rf /var/lib/apt/lists/*

# 3. python3.9를 기본 python 명령어로 사용하도록 심볼릭 링크 생성
RUN ln -s /usr/bin/python3.9 /usr/bin/python

# 4. 작업 디렉토리 설정
WORKDIR /app

# 5. Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 프로젝트 파일 복사
COPY . .

# 7. gunicorn으로 앱 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app_for_Render:app"]