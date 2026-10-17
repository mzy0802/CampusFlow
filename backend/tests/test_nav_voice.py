"""Voice input stays an input method: audio is transcribed to text, never routed."""
import base64
import json
import urllib.request

import pytest
from fastapi.testclient import TestClient

from app import nav_voice
from app.main import app

WAV = base64.b64encode(b'RIFF' + b'\x00' * 64).decode()
ASR_ENV = {'NAV_ASR_API_KEY': 'k', 'NAV_ASR_BASE_URL': 'https://asr.example.invalid', 'NAV_ASR_MODEL': 'qwen3-asr-flash'}


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_transcribe_rejects_unsupported_format():
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/midi'})
    assert response.status_code == 400
    assert '不支持' in response.json()['detail']


def test_transcribe_rejects_oversized_audio():
    client = TestClient(app)
    huge = base64.b64encode(b'\x00' * (nav_voice.MAX_AUDIO_BYTES + 1)).decode()
    response = client.post('/api/navigation/transcribe', json={'audio': huge, 'mime': 'audio/wav'})
    assert response.status_code == 400
    assert 'MB' in response.json()['detail']


def test_asr_status_reports_ready_and_unconfigured(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(nav_voice, 'config', lambda: ASR_ENV)
    assert client.get('/api/navigation/asr').json()['ready'] is True
    monkeypatch.setattr(nav_voice, 'config', lambda: {})
    body = client.get('/api/navigation/asr').json()
    assert body['ready'] is False
    assert '尚未配置' in body['message']


def test_transcribe_disabled_without_own_config(monkeypatch):
    monkeypatch.setattr(nav_voice, 'config', lambda: {})
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/wav'})
    assert response.status_code == 503
    assert '尚未配置' in response.json()['detail']


def test_transcribe_does_not_reuse_vision_credentials(monkeypatch):
    monkeypatch.setattr(nav_voice, 'config', lambda: {'DASHSCOPE_API_KEY': 'vision-only',
                                                      'QWEN_VISION_BASE_URL': 'https://example.invalid'})
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/wav'})
    assert response.status_code == 503
    assert '尚未配置' in response.json()['detail']


def test_transcribe_rejects_plain_http_endpoint(monkeypatch):
    monkeypatch.setattr(nav_voice, 'config', lambda: {**ASR_ENV, 'NAV_ASR_BASE_URL': 'http://asr.example.invalid'})
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/wav'})
    assert response.status_code == 503
    assert 'HTTPS' in response.json()['detail']


def test_asr_allows_loopback_without_tls(monkeypatch):
    """Local testing should not need a certificate, but any other host still must."""
    local = {'NAV_ASR_API_KEY': 'k', 'NAV_ASR_BASE_URL': 'http://127.0.0.1:8787/v1', 'NAV_ASR_MODEL': 'qwen3-asr-flash'}
    monkeypatch.setattr(nav_voice, 'config', lambda: local)
    assert nav_voice.asr_settings()[1] == 'http://127.0.0.1:8787/v1'
    monkeypatch.setattr(nav_voice, 'config', lambda: {**local, 'NAV_ASR_BASE_URL': 'http://asr.example.invalid'})
    with pytest.raises(ValueError, match='HTTPS'):
        nav_voice.asr_settings()


def test_repair_fixes_known_homophone():
    fixed, changes = nav_voice.repair_places('我要去修元楼一区', [{'id': 'a', 'name': '修远教学楼一区'}])
    assert '修远' in fixed
    assert {'from': '修元', 'to': '修远'} in changes


def test_repair_fixes_misheard_name_by_similarity():
    fixed, changes = nav_voice.repair_places('我要去逸福图书馆', [{'id': 'a', 'name': '逸夫图书馆'}])
    assert fixed == '我要去逸夫图书馆'
    assert changes[0]['to'] == '逸夫图书馆'


def test_repair_leaves_name_already_in_catalog():
    items = [{'id': 'a', 'name': '修远教学楼一区'}]
    fixed, changes = nav_voice.repair_places('我要去修远教学楼一区', items)
    assert fixed == '我要去修远教学楼一区'
    assert changes == []


def test_transcribe_returns_text_and_surfaces_correction(monkeypatch):
    from app import navigation
    captured = {}

    def fake(request, timeout=None):
        captured['url'] = request.full_url
        captured['body'] = json.loads(request.data.decode('utf-8'))
        return _Response({'choices': [{'message': {'content': '我要去修元楼一区'}}]})

    monkeypatch.setattr(urllib.request, 'urlopen', fake)
    monkeypatch.setattr(nav_voice, 'config', lambda: ASR_ENV)
    monkeypatch.setattr(navigation, 'campus_places', lambda request: [{'id': 'a', 'name': '修远教学楼一区'}])
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/wav'})
    assert response.status_code == 200
    data = response.json()
    assert data['engine'] == 'qwen3-asr-flash'
    assert '修远' in data['text']
    assert data['raw'] == '我要去修元楼一区'
    assert data['corrections']
    assert captured['url'].endswith('/chat/completions')
    assert captured['body']['model'] == 'qwen3-asr-flash'
    assert captured['body']['messages'][1]['content'][0]['type'] == 'input_audio'
    assert '修远教学楼一区' in captured['body']['messages'][0]['content']


def test_transcribe_reports_unreachable_service(monkeypatch):
    from app import navigation

    def broken(request, timeout=None):
        raise OSError('network down')

    monkeypatch.setattr(urllib.request, 'urlopen', broken)
    monkeypatch.setattr(nav_voice, 'config', lambda: ASR_ENV)
    monkeypatch.setattr(navigation, 'campus_places', lambda request: [])
    client = TestClient(app)
    response = client.post('/api/navigation/transcribe', json={'audio': WAV, 'mime': 'audio/wav'})
    assert response.status_code == 503
    assert '连接失败' in response.json()['detail']


def test_asr_failure_never_falls_back_to_guessing(monkeypatch):
    """No credentials and no browser speech means a clear error, not a fake route."""
    monkeypatch.setattr(nav_voice, 'config', lambda: {})
    with pytest.raises(ValueError, match='尚未配置'):
        nav_voice.asr_settings()
