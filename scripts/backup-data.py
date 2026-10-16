"""Run after stopping uploads/backend. Back up local data, never credentials."""
import argparse
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from contextlib import closing

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--storage',type=Path,default=ROOT/'backend/storage')
parser.add_argument('--database',type=Path,default=ROOT/'backend/storage/traffic.sqlite3')
parser.add_argument('--output',type=Path,default=ROOT/'backups')
args=parser.parse_args()
if args.output.resolve().is_relative_to(args.storage.resolve()):raise SystemExit('Backup output must be outside the storage directory.')
if not args.storage.is_dir() or not args.database.is_file():raise SystemExit('Storage/database missing. For custom paths, pass --storage and --database.')
args.output.mkdir(parents=True,exist_ok=True)
stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S-%f')
target=args.output/f'CampusFlow-data-{stamp}.zip'
with tempfile.TemporaryDirectory(dir=args.output.resolve(),prefix='backup-temp-') as temporary:
    assert Path(temporary).resolve().is_relative_to(args.output.resolve())
    snapshot=Path(temporary)/'traffic.sqlite3'
    with closing(sqlite3.connect(f'{args.database.resolve().as_uri()}?mode=ro',uri=True)) as source:
        with closing(sqlite3.connect(snapshot)) as destination:source.backup(destination)
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(snapshot,'storage/traffic.sqlite3')
        for file in args.storage.rglob('*'):
            if file.is_file() and not file.is_symlink() and not file.name.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm')):
                archive.write(file,'storage/'+file.relative_to(args.storage).as_posix())
print('Backup saved:',target)
print('Contains local media and annotations. Keep private; do not upload to the public repository.')
