"""Reusable teaching judgments. No persistence, model or transport dependencies."""
import re
from base.app.companion.aesthetic.academic import TYPES

POLICY = {
    'id': 'learning.teaching_workflow@1.0.0', 'professional_validation': 'NOT_REVIEWED',
    'rules': [
        {'id':'T01','when':'复用题目','judge':'来源和用途明确，按当前学生范围重新核对；排除已布置题。'},
        {'id':'T02','when':'修改草稿','judge':'按题目内容、共用材料、规则、范围和音频依赖决定审校是否失效。'},
        {'id':'T03','when':'记录词表检查','judge':'区分原词、可靠词形、用户豁免、中文词注和待查词；范围不完整时保留不确定性。'},
        {'id':'T04','when':'安排训练','judge':'先处理坏题和待评，再验证困难，选择关键操作，最后用未见题复测。'},
        {'id':'T05','when':'班级复用','judge':'冻结名单并逐人映射路线和范围；失败逐人重试，已成功任务不重复发送。'},
        {'id':'T06','when':'教师确认','judge':'AI、基础备题和题库复用均为候选；实际审题、布置和教学安排分别确认。'},
    ],
}

IRREGULAR = {'am':'be','is':'be','are':'be','was':'be','were':'be','been':'be','being':'be',
 'went':'go','gone':'go','did':'do','done':'do','does':'do','had':'have','has':'have',
 'children':'child','men':'man','women':'woman','feet':'foot','teeth':'tooth',
 'better':'good','best':'good','bought':'buy','thought':'think','wrote':'write','written':'write'}

def lexical_check(text, scopes, exemptions=(), proper_names=()):
    words={w.casefold().strip() for s in scopes for w in s['words']}
    exempt={w.casefold() for w in exemptions};names={w.casefold() for w in proper_names}
    annotations=[]
    for m in re.finditer(r"([A-Za-z]+)\s*[（(]([^()（）]*[\u4e00-\u9fff][^()（）]*)[）)]",text):
        annotations.append({'word':m.group(1),'annotation':m.group(2)})
    annotated={x['word'].casefold() for x in annotations}
    matches=[];unknown=[]
    for token in sorted(set(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text)),key=str.casefold):
        w=token.casefold();base=None;kind=None
        if w in words:base=w;kind='exact'
        elif w in exempt:kind='explicit_exemption'
        elif w in names:kind='declared_proper_name'
        elif w in annotated:kind='chinese_annotation'
        elif IRREGULAR.get(w) in words:base=IRREGULAR[w];kind='irregular_inflection'
        else:
            candidates=[]
            if w.endswith("'s"):candidates.append(w[:-2])
            if w.endswith('ies'):candidates.append(w[:-3]+'y')
            if w.endswith('ied'):candidates.append(w[:-3]+'y')
            if w.endswith('s') and not w.endswith('ss'):candidates.append(w[:-1])
            if w.endswith('es'):candidates.append(w[:-2])
            for suffix in ['ing','ed']:
                if w.endswith(suffix) and len(w)>len(suffix)+2:
                    stem=w[:-len(suffix)];candidates.extend([stem,stem+'e'])
                    if len(stem)>2 and stem[-1]==stem[-2]:candidates.append(stem[:-1])
            found=sorted(set(candidates)&words)
            if len(found)==1:base=found[0];kind='regular_inflection'
        if kind:matches.append({'token':token,'lemma':base,'match':kind})
        else:unknown.append(token)
    reliable=bool(words) and bool(scopes) and all(s['complete'] and s['content_reviewed'] for s in scopes)
    return {'matches':matches,'unmatched_words':unknown,'annotations':annotations,
        'ok':not unknown if reliable else None,'reliable_scope_declared':reliable,
        'source_refs':[{'id':s['id'],'revision':s['revision'],'content_hash':s['content_hash'],'source':s['source']} for s in scopes],
        'method':'supplied_wordlist_with_conservative_inflections_v1',
        'note':'专名须显式登记；词形规则用于筛查，未命中词交由教师核对。中文词注单独标记。'}

def scope_signature(scope):
    return {k:scope.get(k) for k in ['textbook','unit','order','source','words','phrases','grammar','complete','content_reviewed']}

def validate_blueprint(body, sections):
    questions=body['questions'];used=[];result=[]
    for section in sections:
        ids=section['question_ids'];selected=[q for q in questions if q['id'] in ids]
        if len(selected)!=len(ids) or len(set(ids))!=len(ids):raise ValueError('蓝图题号须对应草稿且不重复')
        if any(q['type'] not in section['types'] for q in selected):raise ValueError('题型与蓝图分区不一致')
        if len(selected)!=section['count']:raise ValueError('分区题数与蓝图不一致')
        if abs(sum(q['points'] for q in selected)-section['points'])>1e-6:raise ValueError('分区分值与题目分值不一致')
        used.extend(ids);result.append(section)
    if set(used)!={q['id'] for q in questions} or len(used)!=len(questions):raise ValueError('整卷蓝图须恰好覆盖所有题目')
    return {'sections':result,'total_points':sum(x['points'] for x in result),'minutes':sum(x['minutes'] for x in result),
            'kind':'teacher_declared_practice_blueprint','official_score_conversion':False}

def fallback_questions(focus, count, grade):
    """Small original item families, varied contexts; unsupported skills stay pending."""
    result=[]
    be=focus in ['be动词主谓一致','主谓一致','be动词']
    detail=focus in ['细节理解','阅读细节']
    if not (be or detail):return result
    subjects=[('I','am'),('She','is'),('They','are'),('We','are'),('He','is'),('You','are')]
    places=['library','garden','museum','classroom','club','office','studio','hall']
    for i in range(min(count,24)):
        if be:
            subject,answer=subjects[i%6];place=places[(i//6)%8]
            choices=['am','is','are'];shift=i%3;choices=choices[shift:]+choices[:shift]
            action='reading' if grade>=7 else None
            sentence=f'{subject} {{verb}} '+(f'{action} in the {place}.' if action else f'in the {place}.')
            material='情境：描述正在进行的动作，先核对句子的主语。' if action else '情境：描述现在所处的位置。'
            q={'type':'grammar_mcq','material':material,'prompt':'Choose: '+sentence.format(verb='___'),
               'options':choices,'key':[chr(65+choices.index(answer))],'evidence':f'主语 {subject} 在本句中搭配 be 动词形式 {answer}。',
               'explanation':f'先辨认主语 {subject}，再选择 {answer}。',
               'traps':{chr(65+j):'语法形式错误' for j,x in enumerate(choices) if x!=answer}}
        else:
            day=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][i%6]
            place=places[(i//6)%8];other='Sunday' if day!='Sunday' else 'Monday'
            material=f'The {place} opens on {day}.'
            if grade>=7:material+=f' It closes on {other}.'
            if grade>=10:material+=f' Staff may enter earlier, but public access begins on {day}.'
            options=[day,other];options=options[::-1] if i%2 else options
            q={'type':'reading_mcq','material':material,'prompt':f'On which day does the {place} open?',
               'options':options,'key':[chr(65+options.index(day))],'evidence':f'The {place} opens on {day}.',
               'explanation':'定位 opens 对应的日期，再核对 closes 的区别。',
               'traps':{chr(65+j):'张冠李戴' for j,x in enumerate(options) if x!=day}}
        result.append({'id':f'q{i+1}','skill':focus,'points':1.0,**q})
    return result

def catalog():
    return {'policy':POLICY,'types':TYPES,'fallback_skills':['be动词主谓一致','细节理解'],
        'blueprint_templates':[
            {'id':'k12-custom','name':'K12 自定义整卷','types':list(TYPES),'mode':'teacher_declared'},
            {'id':'toefl-2026','name':'托福2026专项蓝图','task_families':[
                'Complete the Words','Read in Daily Life','Read an Academic Passage',
                'Listen and Choose a Response','Listen to a Conversation','Listen to an Announcement','Listen to an Academic Talk',
                'Build a Sentence','Write an Email','Write for an Academic Discussion','Listen and Repeat','Take an Interview'],
             'source':'https://www.ets.org/toefl/test-takers/ibt/about/content.html?version=after-jan-2026',
             'use':'专项备题标签；自适应整卷另需专用引擎'},
            {'id':'ielts-academic-computer','name':'雅思学术类机考专项蓝图','task_families':['Listening','Reading','Writing Task 1','Writing Task 2','Speaking'],
             'source':'https://ielts.org/take-a-test/test-types/ielts-academic-test','use':'专项备题标签；不换算官方等级'}]}
