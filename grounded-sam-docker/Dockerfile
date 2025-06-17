# NVIDIA PyTorch 컨테이너를 베이스 이미지로 사용 (CUDA, cuDNN 포함)
FROM nvcr.io/nvidia/pytorch:23.10-py3

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 도구 설치
RUN apt-get update && apt-get install -y \
    git \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Grounding DINO 및 기타 필수 파이썬 라이브러리 설치
# VS Code Python 확장이 사용할 디버거 포함
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
RUN pip install --no-cache-dir supervision \
    "git+https://github.com/facebookresearch/segment-anything.git" \
    "git+https://github.com/IDEA-Research/GroundingDINO.git" \
    transformers \
    opencv-python \
    debugpy 

# 모델 가중치를 다운로드할 폴더 생성
RUN mkdir -p /app/weights

# Grounding DINO 가중치 다운로드
RUN wget -q https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth -P /app/weights

# SAM 가중치 다운로드 (여기서는 vit_h 모델 사용)
RUN wget -q https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth -P /app/weights

# VS Code가 연결할 수 있도록 컨테이너가 종료되지 않게 유지
CMD ["tail", "-f", "/dev/null"]