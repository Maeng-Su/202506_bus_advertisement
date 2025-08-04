# 202506_bus_advertisement
버스광고 AI 솔루션

# Inkscape 버전 업그레이드
- Inkscape 0.92 버전의 명령줄 도구(CLI)는 기능이 매우 제한적입니다. 특히 SVG로 내보내는 명령어가 단 하나뿐입니다.
- 따라서 아래 명령어를 실행해서 Inkscape 버전이 1.0 이상이 되도록 해야 합니다.
   
'''
# 1. Inkscape 공식 PPA(개인 패키지 저장소)를 추가합니다.
sudo add-apt-repository ppa:inkscape.dev/stable

# 2. 패키지 목록을 업데이트합니다.
sudo apt update

# 3. 최신 버전의 Inkscape를 설치합니다. (기존 버전은 자동으로 교체됩니다)
sudo apt install inkscape

# 버전 확인
inkscape --version
'''