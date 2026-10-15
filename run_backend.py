"""Run with system Python; avoids the Windows temporary venv launcher."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
for directory in (ROOT.parents[1] / 'work/venv/Lib/site-packages',
                  ROOT / '.venv/Lib/site-packages', ROOT / '.vision-deps'):
    if directory.is_dir():
        sys.path.insert(0, str(directory))
sys.path.insert(0, str(ROOT / 'backend'))

if __name__ == '__main__':
    try:
        import uvicorn
    except ImportError:
        raise SystemExit('Backend dependencies missing. Run: python -m pip install -r backend/requirements.txt')
    print('Campus backend: http://127.0.0.1:8000/docs', flush=True)
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
