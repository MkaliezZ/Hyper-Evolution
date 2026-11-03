"""Portable declarative method assets. No private source links, code or executable hooks."""
import json,re
from base.app.companion.assets.references import digest

METHOD_FIELDS=['title','problem','intended_scope','use_basis','provenance_statement','deidentification_note',
    'procedure','acceptance','good_case','bad_case','evidence_limits']

def screened_content(content):
    """Conservative obvious-identifier checks supplement, never replace declared review."""
    text=json.dumps(content,ensure_ascii=False)
    patterns=[r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',r'(?<!\d)1[3-9]\d{9}(?!\d)',
        r'(?i)\b(?:sk-|api[_ -]?key\s*[:=]|bearer\s+)[A-Za-z0-9_-]{8,}',r'(?i)[A-Z]:[\\/]',r'\b\d{17}[0-9Xx]\b']
    if any(re.search(p,text) for p in patterns):raise ValueError('检测到疑似联系方式、密钥或本机路径；请先移除并重新审阅')
    return content

def portable_release(candidate,review,publisher,note,version):
    content=screened_content({k:candidate[k] for k in METHOD_FIELDS})
    value={'schema':'companion.method.asset.v1','asset_id':candidate['id'],'version':version,'content':content,
        'review':{k:review[k] for k in ['reviewer_name','expertise_statement','conclusion','reason']},
        'publication':{'publisher_name':publisher,'note':note},
        'boundary':'本机声明范围内的方法资产；身份、资质、用途依据及脱敏均为调用者声明，未由平台认证。不会自动激活运行规则。'}
    screened_content(value)
    return {**value,'sha256':digest(value)}
