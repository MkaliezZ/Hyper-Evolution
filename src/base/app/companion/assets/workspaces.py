"""Pure workspace paths and immutable source representations."""
import re
from pathlib import Path
from base.app.companion.assets.references import digest

def subject_path(root,subject):
    if not re.fullmatch(r'english|mathematics|science|humanities|other|subject-[0-9a-f]{16}',subject):
        raise ValueError('学科目录标识无效')
    root=Path(root).resolve();target=root/'subjects'/subject
    if not target.resolve().is_relative_to(root) or target.is_symlink():raise ValueError('学科目录越界')
    return target

def text_path(folder,asset):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',asset['id']):raise ValueError('资料文件标识无效')
    return Path(folder)/'materials'/asset['id']/('v'+str(int(asset['revision']))+'.txt')

def check_text(asset,raw):
    if raw.decode('utf-8')!=asset['text'] or digest(asset['text'])!=asset['source_hash']:
        raise ValueError('资料文件与保存版本不一致，请恢复原文件或在页面中另存修订；不会忽略文件变化')
