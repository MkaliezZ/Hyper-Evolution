"""Stable content references and review dependencies; no runtime knowledge."""
import re
from base.app.companion.assets.references import digest

def ref(value):
    return {k:value[k] for k in ['id','revision','content_hash']}

def review_dependencies(draft):
    b=draft['body']
    shared={k:b.get(k) for k in ['instructions','goal','source','criteria','supports','audio_id']}
    shared.update(route_ref=draft['route_ref'],scope_refs=draft['scope_refs'],policy=draft.get('policy_ref'))
    return {q['id']:digest({'question':{**q,'points':float(q.get('points',1))},'shared':shared}) for q in b['questions']}

def export_item(question, source, scope_specs, level, grade):
    content={k:v for k,v in question.items() if k!='id'}
    content['points']=float(content.get('points',1))
    return {'question':question,'source':source,'scope_specs':scope_specs,'level':level,'grade':grade,
            'question_hash':digest(content),'origin':'teacher_explicitly_exported_reviewed_draft'}

def extract_curriculum(text):
    """Parse explicit plaintext headings, preserving uncertain lines for review."""
    units=[];warnings=[];section=None;current=None;line_refs=[]
    headings={'words':'words','vocabulary':'words','词表':'words','单词':'words','词汇':'words',
              'phrases':'phrases','短语':'phrases','grammar':'grammar','语法':'grammar'}
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip().lstrip('#').strip()
        if not line:continue
        unit=re.match(r'(?:Unit\s*(\d+)|第\s*(\d+)\s*单元)(.*)',line,re.I)
        if unit:
            current={'unit':line,'order':int(unit.group(1) or unit.group(2)),
                     'words':[],'phrases':[],'grammar':[],'complete':False}
            units.append(current);section=None;line_refs.append({'unit_order':current['order'],'line':number});continue
        category=re.match(r'^([^:：]+)[:：]\s*(.*)$',line)
        if category and category.group(1).casefold() in headings:
            section=headings[category.group(1).casefold()];line=category.group(2)
        if current and section:
            # Chinese glosses after a word are kept in the source, not treated as English lexemes.
            values=re.split(r'[;,；，、\t]+',line) if section!='grammar' else re.split(r'[;；]+',line)
            for value in values:
                value=value.strip().lstrip('-•').strip()
                if not value:continue
                if section=='words':
                    word=re.match(r"^([A-Za-z]+(?:'[A-Za-z]+)?)(?:\s|[（(]|$)",value)
                    if not word:warnings.append({'line':number,'text':value,'reason':'词条格式待核对'});continue
                    value=word.group(1)
                if value not in current[section]:current[section].append(value)
        elif line:warnings.append({'line':number,'text':line,'reason':'未匹配明确单元或词表/短语/语法标题'})
    if not units:raise ValueError('文本需含 Unit 1 / 第1单元，以及 Words / 词表等明确标题')
    if len({u['order'] for u in units})!=len(units):raise ValueError('单元顺序号重复，请核对原文')
    return {'units':units,'unparsed_lines':warnings,'line_refs':line_refs,'source_text_hash':digest(text),
            'source_text':text,'extraction_method':'explicit_text_headings_v1'}

def public_blueprint(value):
    public={'version':'teaching.blueprint.v1','blueprint_ref':ref(value),
        **{k:value[k] for k in ['template','sections','minutes','total_points','official_score_conversion']}}
    return {**public,'content_hash':digest(public)}

def verify_blueprint(pack):
    value=pack.get('teaching_blueprint')
    if value is None:return
    allowed={'version','blueprint_ref','template','sections','minutes','total_points','official_score_conversion','content_hash'}
    if set(value)!=allowed or value['version']!='teaching.blueprint.v1' or value['official_score_conversion'] is not False:raise ValueError('整卷蓝图扩展无效')
    if digest({k:v for k,v in value.items() if k!='content_hash'})!=value['content_hash']:raise ValueError('整卷蓝图内容指纹不一致')
    sections=value['sections']
    if not isinstance(sections,list) or not 1<=len(sections)<=20:raise ValueError('整卷分区无效')
    ids=[]
    for s in sections:
        if set(s)!={'title','types','question_ids','count','points','minutes'}:raise ValueError('整卷分区字段无效')
        if type(s['minutes']) is not int or not 1<=s['minutes']<=240 or s['count']!=len(s['question_ids']):raise ValueError('整卷时间或题数无效')
        ids+=s['question_ids']
    if len(ids)!=len(set(ids)) or set(ids)!={q['id'] for q in pack['items']}:raise ValueError('整卷蓝图须覆盖本次全部题号')
    if value['minutes']!=sum(s['minutes'] for s in sections):raise ValueError('整卷总时长无效')
