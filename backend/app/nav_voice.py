"""Voice input for AI navigation: cloud ASR first, campus name repair after.

Speech is only an input method. Audio never reaches the routing model: this module
returns plain text, so the existing chat protocol stays unchanged.
"""
import base64
import binascii
import json
import re
import unicodedata
import urllib.request
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .qwen_vision import config

router = APIRouter(prefix='/navigation', tags=['navigation'])

# Base64 inflates by ~4/3 and the model caps encoded input near 10 MB.
MAX_AUDIO_BYTES = 5 * 1024 * 1024
MIME_TYPES = {'audio/wav', 'audio/mpeg', 'audio/mp4', 'audio/flac', 'audio/ogg', 'audio/webm'}
VOCABULARY_HINT = 200

MIN_TERM = 3
MAX_TERM = 16
MAX_CATALOG_TERMS = 800
# Same convention as place_search.search_places: two thirds of the characters agree.
MATCH_RATIO = 0.66

# Confusions the acoustic model makes on this campus; high precision, extended as heard.
HOMOPHONES = {
    '名远': '明远', '明园': '明远', '民远': '明远', '铭远': '明远',
    '修院': '修远', '修元': '修远', '修园': '修远', '秀远': '修远',
    '宏远': '鸿远', '红远': '鸿远', '洪远': '鸿远', '鸿园': '鸿远',
    '滋蓝': '滋兰', '红翔': '鸿翔', '鸿祥': '鸿翔', '树惠': '树蕙',
}
DIGITS = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9', '零': '0', '〇': '0'}
STRIPPED = re.compile(r'[\s·、，。！？,.!?;；:："\'`~—\-]+')


class TranscribeRequest(BaseModel):
    audio: str = Field(min_length=16, max_length=8 * 1024 * 1024)
    mime: str = 'audio/wav'
    language: str = Field(default='zh', max_length=16)


def asr_settings():
    """ASR is configured independently from vision and from the routing model."""
    c = config()
    key = c.get('NAV_ASR_API_KEY')
    base = c.get('NAV_ASR_BASE_URL')
    model = c.get('NAV_ASR_MODEL') or 'qwen3-asr-flash'
    if not key or not base:
        raise ValueError('语音识别由负责同学接入，尚未配置；请直接打字，或使用浏览器自带语音输入')
    # Loopback stays plain HTTP so the module can be exercised without a certificate.
    if not base.startswith('https://') and not base.startswith(('http://127.0.0.1', 'http://localhost')):
        raise ValueError('语音接口必须使用HTTPS')
    return key, base.rstrip('/'), model


def decode_audio(body):
    mime = body.mime.split(';')[0].strip().lower()
    if mime not in MIME_TYPES:
        raise ValueError(f'不支持的音频格式：{body.mime}')
    try:
        raw = base64.b64decode(body.audio, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError('音频编码无效，请重新录制') from None
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise ValueError(f'音频超过{MAX_AUDIO_BYTES // 1024 // 1024}MB，请说短一些后重试')
    return raw, mime


def message_text(message):
    content = (message or {}).get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return ''


def call_asr(key, base, model, raw, mime, language, vocabulary):
    hint = '、'.join(vocabulary[:VOCABULARY_HINT])
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': '你是长安大学渭水校区导航语音转写。只输出简体中文口语原文，保留楼栋编号、方位词以及"去""到"等动词。不要回答问题，不要加标点以外的格式。校园常见地点：' + hint},
            {'role': 'user', 'content': [{'type': 'input_audio', 'input_audio': {'data': f'data:{mime};base64,{base64.b64encode(raw).decode()}'}}]},
        ],
        'stream': False,
        'asr_options': {'enable_itn': False, 'language': language},
    }
    request = urllib.request.Request(base + '/chat/completions', data=json.dumps(payload).encode('utf-8'),
                                     headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except Exception:
        raise ValueError('语音识别服务连接失败，请稍后重试或直接打字') from None
    choices = payload.get('choices') or []
    if not choices:
        raise ValueError('语音识别返回为空，请重试')
    text = message_text(choices[0].get('message')).strip()
    if not text:
        raise ValueError('没有听清，请靠近麦克风再说一次')
    return text, model


def loose(text):
    """Length-preserving cleanup, so a match can be mapped back onto the original.

    place_search.normalize strips 楼/区/教学 and rewrites numbers, which breaks the
    index mapping; it stays the search-side helper and is not reused here.
    """
    cleaned = STRIPPED.sub('', unicodedata.normalize('NFKC', text).lower())
    return ''.join(DIGITS.get(ch, ch) for ch in cleaned)


def catalog_terms(items):
    """Candidate names and aliases, longest first, bounded for cost."""
    seen = set()
    terms = []
    for item in items:
        for term in [str(item.get('name', ''))] + [str(a) for a in (item.get('aliases') or [])]:
            key = loose(term)
            if not MIN_TERM <= len(key) <= MAX_TERM or key in seen:
                continue
            seen.add(key)
            terms.append((key, term))
    terms.sort(key=lambda t: (-len(t[0]), t[0]))
    return terms[:MAX_CATALOG_TERMS]


def apply_homophones(text):
    changes = []
    for wrong, right in HOMOPHONES.items():
        if wrong in text:
            text = text.replace(wrong, right)
            changes.append({'from': wrong, 'to': right})
    return text, changes


def repair_places(text, items):
    """Fix misheard campus names, e.g. 修元楼 -> 修远楼.

    A name that never matches the catalog silently degrades into a clarification,
    so repair runs before parsing. Every change is returned and shown to the user,
    who can still edit the text before sending.
    """
    fixed, changes = apply_homophones(text)
    flat = loose(fixed)
    if len(flat) != len(fixed) or len(flat) < MIN_TERM:
        return fixed, changes
    for key, term in catalog_terms(items):
        if key in flat:
            continue
        size = len(key)
        first, last = key[0], key[-1]
        best = None
        for start in range(len(flat) - size + 1):
            if flat[start] != first and flat[start + size - 1] != last:
                continue
            ratio = SequenceMatcher(None, flat[start:start + size], key).ratio()
            if ratio >= MATCH_RATIO and (best is None or ratio > best[0]):
                best = (ratio, start)
        if best:
            start = best[1]
            changes.append({'from': fixed[start:start + size], 'to': term})
            return fixed[:start] + term + fixed[start + size:], changes
    return fixed, changes


@router.get('/asr')
def asr_status():
    """Lets the page choose cloud ASR or the browser's own recognizer up front."""
    try:
        _key, _base, model = asr_settings()
    except ValueError as e:
        return {'ready': False, 'message': str(e)}
    return {'ready': True, 'model': model, 'message': '云端语音识别已就绪'}


@router.post('/transcribe')
def transcribe(body: TranscribeRequest, request: Request):
    from .navigation import campus_places
    try:
        raw, mime = decode_audio(body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    try:
        key, base, model = asr_settings()
    except ValueError as e:
        raise HTTPException(503, str(e)) from None
    try:
        items = campus_places(request)
    except Exception:
        items = []
    vocabulary = sorted({str(p.get('name', '')) for p in items if p.get('name')})
    try:
        heard, model = call_asr(key, base, model, raw, mime, body.language, vocabulary)
    except ValueError as e:
        raise HTTPException(503, str(e)) from None
    fixed, corrections = repair_places(heard, items) if items else (heard, [])
    return {'text': fixed, 'raw': heard, 'corrections': corrections, 'engine': model,
            'bytes': len(raw), 'mime': mime}
