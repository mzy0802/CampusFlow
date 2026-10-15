"""Qwen cloud counting; originals are sent without client-side resizing."""
import os, json, base64, urllib.request, urllib.error, importlib.util, math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def config():
    values = {}
    for filename in ('百炼.env', '.env'):
        path = ROOT / filename
        if path.exists():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                if sep and not key.strip().startswith('#'):
                    values[key.strip()] = value.strip().strip('\"\'')
    values.update(os.environ)
    return values

def readiness():
    c = config()
    ready = bool(c.get('DASHSCOPE_API_KEY') or c.get('LLM_API_KEY')) and importlib.util.find_spec('cv2') is not None
    return {'ready': ready, 'model': c.get('QWEN_VISION_MODEL', 'qwen3-vl-plus'),
            'provider': 'qwen', 'inference_mode': 'cloud_visual_count',
            'message': 'Qwen 配置就绪（实际连通性以任务结果为准）' if ready else '请配置百炼 API 密钥并安装 OpenCV。',
            'max_video_frames': 12}

PROMPT = '''Count visible real people and two-wheeled vehicles in this photo. Include parked and ridden vehicles. Exclude cars, reflections, signs and completely hidden objects. Count each vehicle once. Inspect near and distant rows carefully. Return only JSON with nonnegative integer fields bicycle, powered_two_wheeler, uncertain_type, total, person. total must equal bicycle + powered_two_wheeler + uncertain_type. Use uncertain_type for visible two-wheelers whose type is unclear. Give your best visual count, not a range. Also return a short note. No markdown.'''

def parse_counts(content):
    text = content.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    obj = json.loads(text)
    for field in ('bicycle', 'powered_two_wheeler', 'uncertain_type', 'total', 'person'):
        if type(obj.get(field)) is not int or not 0 <= obj[field] <= 100000:
            raise ValueError('Qwen 返回的计数格式无效，请重试。')
    if obj['total'] != obj['bicycle'] + obj['powered_two_wheeler'] + obj['uncertain_type']:
        raise ValueError('Qwen 返回的分项与总数不一致，请重试。')
    return obj

class VisionEngine:
    def count(self, raw, mime):
        c = config()
        key = c.get('DASHSCOPE_API_KEY') or c.get('LLM_API_KEY')
        if not key:
            raise ValueError('百炼密钥未配置。')
        url = c.get('QWEN_VISION_BASE_URL', 'https://ws-qomab609c8hwy37x.cn-beijing.maas.aliyuncs.com/compatible-mode/v1').rstrip('/')
        if not url.startswith('https://'):
            raise ValueError('百炼接口必须使用 HTTPS。')
        body = {'model': c.get('QWEN_VISION_MODEL', 'qwen3-vl-plus'), 'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': 'data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii')}},
            {'type': 'text', 'text': PROMPT}]}], 'enable_thinking': False, 'stream': False, 'temperature': 0, 'max_tokens': 1200, 'response_format': {'type': 'json_object'}}
        request = urllib.request.Request(url+'/chat/completions', data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            raise ValueError(f'百炼调用失败（HTTP {e.code}），请检查额度、密钥和模型权限。') from None
        except Exception:
            raise ValueError('百炼连接失败或超时，请稍后重试。') from None
        try:
            if result['choices'][0].get('finish_reason') != 'stop':
                raise ValueError('Qwen 回复不完整，请重试。')
            counts = parse_counts(result['choices'][0]['message']['content'])
            return {'bicycle': counts['bicycle'], 'motorcycle': counts['powered_two_wheeler'],
                    'uncertain_type': counts['uncertain_type'], 'two_wheeler': counts['total'],
                    'person': counts['person'], 'usage': result.get('usage', {}), 'detections': []}
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError('Qwen 返回格式无效，请重试。') from None

def analyze_media(path, kind, engine, confidence, interval_seconds, progress):
    import cv2, numpy as np
    if kind == 'image':
        raw = path.read_bytes()
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0]*frame.shape[1] > 40000000:
            raise ValueError('图片无法解码或超过4000万像素。')
        mime = {'.png':'image/png', '.webp':'image/webp'}.get(path.suffix.lower(), 'image/jpeg')
        counts = engine.count(raw, mime)
        progress(1, 1)
        yield 0.0, counts, frame
        return
    capture = cv2.VideoCapture(str(path))
    try:
        fps, count = capture.get(cv2.CAP_PROP_FPS), capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0 or not math.isfinite(count) or count <= 0:
            raise ValueError('视频无法解码。')
        if count/fps > 120:
            raise ValueError('视频最长120秒。')
        stride = max(1, round(fps*interval_seconds), math.ceil(count/12))
        total = min(12, math.ceil(count/stride))
        index = done = 0
        while done < 12:
            ok, frame = capture.read()
            if not ok: break
            if index % stride == 0:
                if frame.shape[0]*frame.shape[1] > 16000000:
                    raise ValueError('视频超过1600万像素/帧。')
                ok, encoded = cv2.imencode('.png', frame)
                if not ok: raise ValueError('视频帧编码失败。')
                counts = engine.count(encoded.tobytes(), 'image/png')
                done += 1
                progress(done, total)
                yield round(index/fps, 3), counts, frame
            index += 1
    finally:
        capture.release()
