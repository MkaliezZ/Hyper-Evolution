import json
import argparse
import tempfile
from pathlib import Path
from base.core import Store
from base.app.activities import prepare_activity
from base.app.assessment import evaluate_submission
parser = argparse.ArgumentParser(description='管线自检；--business 验证当前业务样例')
parser.add_argument('--business', action='store_true')
args = parser.parse_args()
if args.business:
    path = Path(__file__).resolve().parents[1] / 'src/base/app/acceptance.json'
    sample = json.loads(path.read_text(encoding='utf-8-sig'))
    activity = prepare_activity()
    if activity['mode'] != sample['mode']:
        raise ValueError('app/acceptance.json.mode 与业务不一致，请更新业务验收样例')
    evaluation = evaluate_submission(activity, sample['answer'])
    for field in ('status', 'correct'):
        if 'expected_' + field in sample and evaluation.get(field) != sample['expected_' + field]:
            raise ValueError('app/acceptance.json：业务样例的' + field + '不符合预期')
    if sample.get('expected_comment_contains', '') not in evaluation['comment']:
        raise ValueError('app/acceptance.json：业务反馈未包含预期内容')
with tempfile.TemporaryDirectory(prefix='base-check-') as folder:
    service = Store(folder)
    task = service.create('合成自检学习者')
    draft = prepare_activity()
    answer = str(draft['expected']) if draft['mode'] == 'numeric' else '先完成一个小任务，再记录反馈。'
    row = service.submit(task['token'], answer, 'self-check')
    service.feedback(row['id'], '目标明确，请增加观察指标。', '记录一次实际结果。')
    assert Store(folder).public_task(task['token'])['submissions'][0]['evaluation']['status'] == 'reviewed'
print(json.dumps({'ok': True, 'scope': 'business-example-and-pipeline' if args.business else 'pipeline-only', 'checks': ['创建活动', '提交', '人工反馈', '重启读取'], 'real_data_modified': False, 'teaching_quality_verified': False}, ensure_ascii=False))
