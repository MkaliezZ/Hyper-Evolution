"""Bounded CSV/JSON preview. Import is not semantic review or permission to distribute."""
import csv,io,json
from collections import defaultdict
from base.app.content import BLUEPRINTS
from base.app.companion.assets.references import digest

def preview(runtime,format,content):
    errors=[];packs=[]
    if format=='json':
        try:raw=json.loads(content)
        except ValueError:raise ValueError('JSON 格式无法解析') from None
        if not isinstance(raw,list):raise ValueError('JSON 顶层须是题包数组')
    else:
        try:rows=list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
        except csv.Error:raise ValueError('CSV 内容过长或格式无效，请拆分并检查引号') from None
        if len(rows)>300:raise ValueError('一次最多300行')
        if not rows:raise ValueError('文件没有题目行')
        groups=defaultdict(list)
        for index,row in enumerate(rows,2):
            if None in row or len(row)>30:
                errors.append({'row':index,'message':'列数或CSV分隔格式无效'});continue
            if any(str(v or '').lstrip().startswith(('=','+','@')) for v in row.values()):
                errors.append({'row':index,'message':'不接受公式或可执行单元格'});continue
            groups[tuple(row.get(k,'') for k in ['title','stimulus','exam','task_type','source_title'])].append((index,row))
        raw=[]
        for (title,stimulus,exam,task_type,source_title),group in groups.items():
            items=[]
            for index,row in group:
                items.append({'id':f'q{len(items)+1}','kind':row.get('kind',''), 'prompt':row.get('prompt',''),
                  'key':[x.strip() for x in row.get('answer','').split('|') if x.strip()],
                  'options':[x.strip() for x in row.get('options','').split('|') if x.strip()],
                  'evidence':row.get('evidence',''),'explanation':row.get('explanation',''),'skill':row.get('skill','')})
            raw.append({'title':title,'stimulus':stimulus,'exam':exam,'task_type':task_type,
                        'items':items,'source':{'kind':'user_provided','title':source_title},'_row':group[0][0]})
    if not raw and not errors:raise ValueError('文件没有可预览的题包')
    if len(raw)>300:raise ValueError('一次最多300个题包')
    for n,original in enumerate(raw,1):
        try:
            if not isinstance(original,dict):raise ValueError('题包须为对象')
            if original.get('audio') or original.get('media_path') or original.get('audio_sha256'):
                raise ValueError('音频题请使用原资源ZIP导入并核对配套；表格导入不接受音频路径')
            exam=original.get('exam','')
            if exam not in BLUEPRINTS:raise ValueError('考试须为 ielts 或 toefl')
            allowed=['title','stimulus','exam','task_type','instructions','items','source','stage']
            p={k:original[k] for k in allowed if k in original}
            p.setdefault('instructions','按原文作答。');p.setdefault('stage','application')
            source=p.get('source',{})
            p['source']={'kind':'user_provided','title':source.get('title',''),
                         'verification_status':'unverified','declaration':'uploader_statement'}
            p['blueprint']=original.get('blueprint',BLUEPRINTS[exam]['version'])
            p['purpose']='practice'
            fingerprint=digest(p);p['id']='bank-'+fingerprint[:24];p['family_id']='bank-family-'+digest([exam,p['stimulus'],p['source']['title']])[:24]
            p['status']='pending_review'
            runtime.service.validate_pack(p)
            if not p['source'].get('title','').strip():raise ValueError('请填写来源名称')
            packs.append(p)
        except (ValueError,TypeError,KeyError):
            errors.append({'row':original.get('_row',n) if isinstance(original,dict) else n,
                           'message':'题包不完整或不适配：请核对考试版本、题型、题干、答案、依据、解析与来源；音频须走ZIP配套导入。'})
    unique={p['id']:p for p in packs}
    existing={p['id'] for p in runtime.service.resources()}
    return {'packs':list(unique.values()),'errors':errors,'rows_parsed':len(raw),
            'duplicates_in_file':len(packs)-len(unique),'already_present':sum(k in existing for k in unique),
            'status':'blocked' if errors else 'ready_for_confirmation','content_quality':'pending_review'}
