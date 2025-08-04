# app.py
import os
import subprocess
import xml.etree.ElementTree as ET
import uuid
import io
import base64

from flask import Flask, request, jsonify, send_from_directory # send_from_directory 추가
from flask_cors import CORS
import cairosvg
import numpy as np
from PIL import Image
from werkzeug.utils import secure_filename

# --- Flask 앱 설정 ---
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# --- 폴더 설정 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# [수정] index.html이 위치할 static 폴더를 생성
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

# --- 헬퍼 함수: SVG 그룹으로 PNG 생성 ---
def create_png_from_groups(groups, root_attrib, defs):
    if not any(g is not None for g in groups): # 유효한 그룹이 하나도 없으면 처리 중단
        return {"image": None, "area": 0}
    
    new_root = ET.Element('svg', attrib=root_attrib)
    if defs is not None:
        new_root.append(defs)
    for group in groups:
        if group is not None:
            new_root.append(group)
            
    svg_string = ET.tostring(new_root, encoding='unicode')
    png_bytes = cairosvg.svg2png(bytestring=svg_string.encode('utf-8'))
    
    img_rgba = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    img_array = np.array(img_rgba)
    
    alpha_channel = img_array[:, :, 3]
    pixel_area = np.sum(alpha_channel > 0)
    
    base64_image = base64.b64encode(png_bytes).decode('utf-8')
    
    return {"image": base64_image, "area": int(pixel_area)}

# --- 핵심 로직: AI 파일 처리 함수 ---
def process_ai_file(ai_path, original_filename):
    layer_results = []
    special_visuals = {}
    svg_content_string = None
    
    unique_filename = f"{uuid.uuid4()}.svg"
    svg_path = os.path.join(SVG_OUTPUT_FOLDER, unique_filename)
    
    try:
        # [수정] 더 안정적인 Action 기반의 명령어로 변경
        actions = f"export-ignore-hidden:true; export-filename:{svg_path}; export-do;"
        command = ["inkscape", f"--actions={actions}", ai_path]
        subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception as e:
        raise RuntimeError(f"Inkscape conversion failed: {e}")

    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            svg_content_string = f.read()

        tree = ET.parse(svg_path)
        root = tree.getroot()
        defs = root.find('svg:defs', ns)
        top_level_groups = root.findall('svg:g', ns)

        # [수정] 특정 레이어 그룹 찾기 ("Back" 과 "Image_01")
        ad_possible_group = None # 버스 광고 가능 면적 (Back)
        ad_area_group = None     # 광고 면적 (Image_01)

        for g in top_level_groups:
            label = g.get(f'{{{ns["inkscape"]}}}label') or g.get('id', '')
            if label == "Back":
                ad_possible_group = g
            elif label == "Image_01":
                ad_area_group = g

        # 특별 시각화 데이터 생성
        special_visuals['ad_possible'] = create_png_from_groups([ad_possible_group], root.attrib, defs)
        special_visuals['ad_area'] = create_png_from_groups([ad_area_group], root.attrib, defs)
        special_visuals['all_view'] = create_png_from_groups([ad_possible_group, ad_area_group], root.attrib, defs)
        
        # 전체 동적 레이어 목록 생성
        if top_level_groups:
            for g_element in top_level_groups:
                # [수정] PNG 이미지와 면적을 함께 생성
                png_data = create_png_from_groups([g_element], root.attrib, defs)
                layer_name = g_element.get(f'{{{ns["inkscape"]}}}label') or g_element.get('id', 'Unnamed Layer')
                
                # [수정] 결과에 이름(name), 이미지(image), 면적(area)을 모두 포함
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

# --- [추가] 웹페이지 제공 엔드포인트 ---
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index_for_Render.html')

# --- 서버 실행 ---
if __name__ == '__main__':
    # 디버그 모드에서는 host와 port를 지정할 수 있지만, gunicorn이 이걸 무시함
    app.run()