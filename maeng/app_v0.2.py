# app.py
import os
import subprocess
import xml.etree.ElementTree as ET
import uuid
import io
import base64

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import numpy as np
from PIL import Image
from werkzeug.utils import secure_filename

# --- Flask 앱 설정 ---
app = Flask(__name__)
CORS(app)

# --- 폴더 설정 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
SVG_OUTPUT_FOLDER = os.path.join(BASE_DIR, 'converted_svgs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SVG_OUTPUT_FOLDER, exist_ok=True)

# --- SVG 네임스페이스 ---
ns = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape'
}

# --- 헬퍼 함수: SVG 그룹으로 PNG 생성 (Inkscape 직접 사용 버전) ---
def create_png_from_groups(groups, root_attrib, defs):
    if not any(g is not None for g in groups):
        return {"image": None, "area": 0}
    
    # 1. 임시 SVG 파일 생성을 위한 준비
    temp_svg_filename = f"{uuid.uuid4()}.svg"
    temp_png_filename = f"{uuid.uuid4()}.png"
    temp_svg_path = os.path.join(SVG_OUTPUT_FOLDER, temp_svg_filename)
    temp_png_path = os.path.join(SVG_OUTPUT_FOLDER, temp_png_filename)

    try:
        # 2. 새로운 SVG 파일 내용 생성
        new_root = ET.Element('svg', attrib=root_attrib)
        if defs is not None:
            new_root.append(defs)
        for group in groups:
            if group is not None:
                new_root.append(group)
        
        svg_string = ET.tostring(new_root, encoding='unicode')
        
        # 3. 임시 SVG 파일을 디스크에 저장
        with open(temp_svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_string)

        # 4. Inkscape를 직접 사용해 SVG를 PNG로 변환
        # WSL 환경에서 Inkscape 경로를 지정해야 할 수 있습니다. e.g., ["/usr/bin/inkscape", ...]
        # 또는 PATH에 등록되어 있다면 "inkscape"만으로도 동작합니다.
        command = [
            "inkscape",
            temp_svg_path,
            "--export-type=png",
            f"--export-filename={temp_png_path}"
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        # 5. 생성된 PNG 파일을 읽고 면적 계산
        with open(temp_png_path, 'rb') as f:
            png_bytes = f.read()

        img_rgba = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
        img_array = np.array(img_rgba)
        
        alpha_channel = img_array[:, :, 3]
        pixel_area = np.sum(alpha_channel > 0)
        
        base64_image = base64.b64encode(png_bytes).decode('utf-8')
        
        return {"image": base64_image, "area": int(pixel_area)}

    finally:
        # 6. 작업이 끝나면 임시 파일 정리
        if os.path.exists(temp_svg_path):
            os.remove(temp_svg_path)
        if os.path.exists(temp_png_path):
            os.remove(temp_png_path)

# --- 핵심 로직: AI 파일 처리 함수 (단순화된 버전) ---
def process_ai_file(ai_path, original_filename):
    unique_filename = f"{uuid.uuid4()}.svg"
    svg_path = os.path.join(SVG_OUTPUT_FOLDER, unique_filename)
    
    try:
        # 1. Inkscape를 사용해 AI를 SVG로 변환
        command = ["inkscape", ai_path, f"--export-filename={svg_path}"]
        subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception as e:
        raise RuntimeError(f"Inkscape conversion failed: {e}")

    try:
        # 2. SVG 파일 파싱 및 처리
        tree = ET.parse(svg_path)
        root = tree.getroot()
        defs = root.find('svg:defs', ns)
        all_top_level_groups = root.findall('svg:g', ns)

        # [핵심] 보이는 레이어만 필터링
        visible_groups = [g for g in all_top_level_groups if 'display:none' not in g.get('style', '')]

        # 전체 시각화를 위한 PNG 생성
        all_visible_layers_png = create_png_from_groups(visible_groups, root.attrib, defs)
        
        # 각 레이어를 개별적으로 처리
        layer_results = []
        if visible_groups:
            for g_element in visible_groups:
                png_data = create_png_from_groups([g_element], root.attrib, defs)
                layer_name = g_element.get(f'{{{ns["inkscape"]}}}label') or g.get('id', 'Unnamed Layer')
                layer_results.append({
                    "name": layer_name,
                    "image": png_data['image'],
                    "area": png_data['area']
                })
        else: # 보이는 그룹이 없을 경우의 예외 처리
            all_layers_png_data = create_png_from_groups(all_top_level_groups, root.attrib, defs)
            layer_name = os.path.splitext(original_filename)[0]
            layer_results.append({
                "name": layer_name, 
                "image": all_layers_png_data['image'],
                "area": all_layers_png_data['area']
            })

        # 최종 데이터 반환 (special_visuals 제거)
        return {
            "visualization": all_visible_layers_png['image'],
            "layers": layer_results,
        }

    except Exception as e:
        print(f"SVG processing error: {e}")
        return {"visualization": None, "layers": []}
    finally:
        if os.path.exists(svg_path):
            os.remove(svg_path)

# --- API 엔드포인트 ---
@app.route('/api/calculate', methods=['POST'])
def calculate_endpoint():
    if 'aiFile' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['aiFile']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400

    if file and file.filename.endswith('.ai'):
        filename = secure_filename(file.filename)
        ai_save_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{filename}")
        try:
            file.save(ai_save_path)
            processed_data = process_ai_file(ai_save_path, filename)
            return jsonify(processed_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            if os.path.exists(ai_save_path):
                os.remove(ai_save_path)
    
    return jsonify({"error": "Invalid file type"}), 400
    
# --- 웹페이지 제공 엔드포인트 ---
@app.route('/')
def serve_index():
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    return send_from_directory(static_dir, 'index.html')


# --- 서버 실행 ---
if __name__ == '__main__':
    # 사용자의 개발 환경을 고려하여 WSL 내부에서 실행 시 외부 접근이 가능하도록 '0.0.0.0'으로 설정
    app.run(host='0.0.0.0', port=5000, debug=True)