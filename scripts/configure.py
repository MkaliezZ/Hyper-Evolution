"""Optional config editor. Validates before writing; preserves a timestamped backup."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from base.app.activities import prepare_activity
from base.teaching import check_activity

parser = argparse.ArgumentParser(description='修改当前伴学配置；资料与评价代码仍由开发者编辑')
for field in ('name', 'goal', 'deliverable', 'criteria', 'next_step'):
    parser.add_argument('--' + field.replace('_', '-'))
args = parser.parse_args()
changes = {k: v for k,v in vars(args).items() if v is not None}
if not changes:
    parser.error('至少指定一项，例如 --name 我的阅读伴学 --goal 能用证据解释一个观点')
path = ROOT/'src/base/app/config.json'
draft = prepare_activity() | changes
result = check_activity(draft)
current = json.loads(path.read_text(encoding='utf-8-sig'))
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
backup = path.with_name('config.' + stamp + '.bak')
backup.write_bytes(path.read_bytes())
path.write_text(json.dumps(current | changes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'ok': True, 'backup': backup.name, 'warnings': result['warnings'], 'next': '重启服务并创建新活动；再执行check.ps1 -Business与verify.ps1。'}, ensure_ascii=False))
