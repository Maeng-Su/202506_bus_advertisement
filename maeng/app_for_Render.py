# app_for_Render.py
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
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# --- 폴더 설정 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
SVG_OUTPUT_FOLDER = os.path.join(BASE_DIR, 'converted_svgs')
os.makedirs(STATIC_DIR, exist_ok=True)
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

# --- 핵심 로직: AI 파일 처리 함수 (Python에서 숨김 레이어 필터링) ---
def process_ai_file(ai_path, original_filename):
    layer_results = []
    special_visuals = {}
    svg_content_string = None
    
    unique_filename = f"{uuid.uuid4()}.svg"
    svg_path = os.path.join(SVG_OUTPUT_FOLDER, unique_filename)
    
    try:
        # Inkscape 명령어는 가장 단순한 형태로 유지
        command = ["inkscape", ai_path, f"--export-filename={svg_path}"]
        subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception as e:
        raise RuntimeError(f"Inkscape conversion failed: {e}")

    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content_string = f.read()

        tree = ET.parse(svg_path)
        root = tree.getroot()
        defs = root.find('svg:defs', ns)
        all_top_level_groups = root.findall('svg:g', ns)

        # [핵심] 보이는 레이어만 필터링하는 로직
        visible_groups = []
        for g in all_top_level_groups:
            style = g.get('style', '')
            if 'display:none' not in style:
                visible_groups.append(g)

        # 필터링된 visible_groups를 기준으로 작업 수행
        ad_possible_group = None
        ad_area_group = None

        for g in visible_groups:
            label = g.get(f'{{{ns["inkscape"]}}}label') or g.get('id', '')
            if label == "Back":
                ad_possible_group = g
            elif label == "Image_01":
                ad_area_group = g

        special_visuals['ad_possible'] = create_png_from_groups([ad_possible_group], root.attrib, defs)
        special_visuals['ad_area'] = create_png_from_groups([ad_area_group], root.attrib, defs)
        special_visuals['all_view'] = create_png_from_groups([ad_possible_group, ad_area_group], root.attrib, defs)
        
        if visible_groups:
            for g_element in visible_groups:
                png_data = create_png_from_groups([g_element], root.attrib, defs)
                layer_name = g_element.get(f'{{{ns["inkscape"]}}}label') or g_element.get('id', 'Unnamed Layer')
                layer_results.append({
                    "name": layer_name,
                    "image": png_data['image'],
                    "area": png_data['area']
                })
        else:
            pixel_area = create_png_from_groups([root], root.attrib, defs)['area']
            layer_name = os.path.splitext(original_filename)[0]
            layer_results.append({"name": layer_name, "area": int(pixel_area)})
            
    except Exception as e:
        print(f"SVG processing error: {e}")
        return {"visualization": svg_content_string, "layers": [], "special_visuals": {}}
    finally:
        if os.path.exists(svg_path):
            os.remove(svg_path)
    
    return {
        "visualization": svg_content_string, 
        "layers": layer_results,
        "special_visuals": special_visuals
    }

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
    return send_from_directory(app.static_folder, 'index_for_Render.html')

# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)