# app_for_Render_v0.2.py
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
# Render 배포 환경에 맞게 static 폴더를 지정합니다.
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# --- 폴더 설정 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Render는 임시 파일 시스템을 사용하므로, 실행 위치를 기준으로 경로를 설정합니다.
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
SVG_OUTPUT_FOLDER = os.path.join(BASE_DIR, 'converted_svgs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SVG_OUTPUT_FOLDER, exist_ok=True)

# --- SVG 네임스페이스 ---
ns = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape'
}

# --- 헬퍼 함수: SVG 그룹으로 PNG 생성 ---
def create_png_from_groups(groups, root_attrib, defs):
    if not any(g is not None for g in groups):
        return {"image": None, "area": 0}
    
    temp_svg_filename = f"{uuid.uuid4()}.svg"
    temp_png_filename = f"{uuid.uuid4()}.png"
    temp_svg_path = os.path.join(SVG_OUTPUT_FOLDER, temp_svg_filename)
    temp_png_path = os.path.join(SVG_OUTPUT_FOLDER, temp_png_filename)

    try:
        new_root = ET.Element('svg', attrib=root_attrib)
        if defs is not None:
            new_root.append(defs)
        for group in groups:
            if group is not None:
                new_root.append(group)
        
        svg_string = ET.tostring(new_root, encoding='unicode')
        
        with open(temp_svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_string)

        # Inkscape CLI를 사용하여 PNG로 변환합니다.
        command = [
            "inkscape",
            temp_svg_path,
            "--export-type=png",
            f"--export-filename={temp_png_path}"
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        with open(temp_png_path, 'rb') as f:
            png_bytes = f.read()

        img_rgba = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
        img_array = np.array(img_rgba)
        
        alpha_channel = img_array[:, :, 3]
        pixel_area = np.sum(alpha_channel > 0)
        
        base64_image = base64.b64encode(png_bytes).decode('utf-8')
        
        return {"image": base64_image, "area": int(pixel_area)}

    finally:
        if os.path.exists(temp_svg_path):
            os.remove(temp_svg_path)
        if os.path.exists(temp_png_path):
            os.remove(temp_png_path)

# --- 핵심 로직: AI 파일 처리 함수 (최신 로직 적용) ---
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

        # 보이는 레이어만 필터링
        visible_groups = [g for g in all_top_level_groups if 'display:none' not in g.get('style', '')]

        # 전체 시각화를 위한 PNG 생성
        all_visible_layers_png = create_png_from_groups(visible_groups, root.attrib, defs)
        
        # 각 레이어를 개별적으로 처리
        layer_results = []
        if visible_groups:
            for g_element in visible_groups:
                png_data = create_png_from_groups([g_element], root.attrib, defs)
                layer_name = g_element.get(f'{{{ns["inkscape"]}}}label') or g_element.get('id', 'Unnamed Layer')
                layer_results.append({
                    "name": layer_name,
                    "image": png_data['image'],
                    "area": png_data['area']
                })
        else: # 보이는 그룹이 없을 경우 예외 처리
            all_layers_png_data = create_png_from_groups(all_top_level_groups, root.attrib, defs)
            layer_name = os.path.splitext(original_filename)[0]
            layer_results.append({
                "name": layer_name, 
                "image": all_layers_png_data['image'],
                "area": all_layers_png_data['area']
            })

        # 최종 데이터 반환 (special_visuals 제거, 클라이언트 중심 구조)
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
    # Render에서 서비스할 메인 HTML 파일명을 정확히 지정합니다.
    return send_from_directory(app.static_folder, 'index_for_Render.html')

# --- 서버 실행 ---
if __name__ == '__main__':
    # Render와 같은 배포 환경을 위해 host를 '0.0.0.0'으로 설정합니다.
    app.run(host='0.0.0.0', port=5000, debug=True)