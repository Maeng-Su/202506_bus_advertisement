# 도커 빌드
docker build -t grounded-sam-vscode:latest .

# 도커 실행
docker run --gpus all --name gsam-dev -d --rm -v $(pwd):/app grounded-sam-vscode:latest

# 100메가 이하 파일만 add
find . -type f -size -100M -print0 | xargs -0 git add