# app.py
import os
import subprocess
import xml.etree.ElementTree as ET
import uuid
import io
import base64

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cairosvg
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

# --- 핵심 로직: AI 파일 처리 함수 ---
def process_ai_file(ai_path, original_filename):
    layer_results = []
    special_visuals = {}
    svg_content_string = None  # 이 변수는 사용하지 않으므로, 삭제하거나 None으로 유지합니다.
    
    unique_filename = f"{uuid.uuid4()}.svg"
    svg_path = os.path.join(SVG_OUTPUT_FOLDER, unique_filename)
    
    try:
        # Inkscape 명령어에서 옵션을 제거하여 단순 변환만 수행
        command = ["inkscape", ai_path, f"--export-filename={svg_path}"]
        subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception as e:
        raise RuntimeError(f"Inkscape conversion failed: {e}")

    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            # SVG를 직접 읽는 대신, 변환된 PNG로 처리하기 위해 이 부분을 수정합니다.
            # svg_content_string = f.read()
            pass # SVG 파일 내용은 더 이상 사용하지 않습니다.

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

        # --- 이 부분에 새로운 시각화 로직을 추가합니다. ---
        # 보이는 모든 레이어를 합쳐 하나의 PNG로 변환합니다.
        all_visible_layers_png = create_png_from_groups(visible_groups, root.attrib, defs)
        
        # 'visualization' 키에 이 새로운 PNG 데이터를 추가합니다.
        # 이전에는 svg_content_string을 사용했지만, 이제 PNG 데이터를 사용합니다.
        processed_data = {
            "visualization": all_visible_layers_png['image'],
            "layers": [],
            "special_visuals": {}
        }
        # ----------------------------------------------------

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
                layer_name = g_element.get(f'{{{ns["inkscape"]}}}label') or g.get('id', 'Unnamed Layer')
                layer_results.append({
                    "name": layer_name,
                    "image": png_data['image'],
                    "area": png_data['area']
                })
        else:
            # 보이는 레이어가 없을 때 전체 뷰를 보여줍니다.
            all_layers_png_data = create_png_from_groups(all_top_level_groups, root.attrib, defs)
            layer_name = os.path.splitext(original_filename)[0]
            layer_results.append({"name": layer_name, "area": all_layers_png_data['area']})

        # 반환할 데이터 구조를 업데이트합니다.
        return {
            "visualization": processed_data['visualization'], # PNG 데이터
            "layers": layer_results,
            "special_visuals": special_visuals
        }

    except Exception as e:
        print(f"SVG processing error: {e}")
        # 오류 발생 시 SVG가 아닌 PNG에 대한 placeholder를 반환하도록 수정
        return {"visualization": None, "layers": [], "special_visuals": {}}
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
    # 로컬 테스트를 위해 static 폴더를 직접 지정할 수 있습니다.
    # 실제 배포 시에는 이 부분이 app = Flask(__name__, static_folder='static'...) 설정에 의해 처리됩니다.
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    return send_from_directory(static_dir, 'index.html')


# --- 서버 실행 ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)