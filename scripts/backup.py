"""Stop the service before running backup. Restore only into an empty folder."""
import argparse
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('action', choices=['backup', 'restore'])
p.add_argument('archive', type=Path)
p.add_argument('destination', type=Path, nargs='?')
a = p.parse_args()
if a.action == 'backup':
    if not any((ROOT/'data').rglob('base.sqlite3')):
        p.error('还没有数据库，请先启动并完成演示')
    with zipfile.ZipFile(a.archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for folder, prefix in [(ROOT/'data', 'data'), (ROOT/'src/base/app', 'app')]:
            for file in folder.rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and file.resolve() != a.archive.resolve():
                    z.write(file, str(Path(prefix)/file.relative_to(folder)))
else:
    if not a.destination:
        p.error('请指定全新恢复目录')
    target = a.destination.resolve()
    if target.exists() and any(target.iterdir()):
        p.error('恢复目录必须为空')
    with zipfile.ZipFile(a.archive) as z:
        for entry in z.infolist():
            path = (target/entry.filename).resolve()
            if not path.is_relative_to(target):
                p.error('备份包含非法路径')
        z.extractall(target)
print('完成。备份含私有数据与凭据，请妥善保存。')
