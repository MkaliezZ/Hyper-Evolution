"""Edit config/material/prompts first; change this function for a new workflow."""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).parent


def prepare_activity():
    try:
        config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8-sig'))
    except (ValueError, OSError) as error:
        raise ValueError(f'app/config.json 无法读取，请检查文件和JSON格式：{error}') from error
    if not isinstance(config, dict):
        raise ValueError('app/config.json：顶层必须是对象')
    try:
        raw = (ROOT / 'knowledge' / 'material.txt').read_bytes()
        config['material'] = raw.decode('utf-8-sig')
    except OSError as error:
        raise ValueError(f'app/knowledge/material.txt 无法读取：{error}') from error
    digest = hashlib.sha256(raw).hexdigest()
    for source in config.get('sources', []) if isinstance(config.get('sources', []), list) else []:
        if isinstance(source, dict) and source.get('file') == 'knowledge/material.txt':
            if source.get('sha256') != digest:
                source['verification_status'] = 'unverified'
                source.pop('verified_by', None)
                source.pop('verified_at', None)
            source['sha256'] = digest
            source['extraction_status'] = 'readable'
    from base.teaching import teaching_rules
    config['teaching_version'] = teaching_rules()['version']
    return config


def generation_context():
    from base.teaching import teaching_rules
    from base.app.profile import LearningProfile
    return {'activity': prepare_activity(), 'profile_schema': LearningProfile.model_json_schema(), 'prompt': (ROOT / 'prompts' / 'activity.txt').read_text(encoding='utf-8-sig'), 'teaching': teaching_rules()}
