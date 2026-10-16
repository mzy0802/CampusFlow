"""All tests use isolated storage; never touch local uploads or the live database."""
import pytest

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path,monkeypatch):
    monkeypatch.setenv('TRAFFIC_DB',str(tmp_path/'traffic.sqlite3'))
    monkeypatch.setenv('DETECTION_STORAGE',str(tmp_path/'vision'))
