"""Evidence-based reports, stable goals and explicit per-student class mapping."""
import copy
from datetime import date, timedelta
from base.app.companion.aesthetic.teaching_workflow import scope_signature
from base.app.companion.assets.references import digest
from base.app.companion.assets.teaching_workflow import ref
from base.app.companion.functional import academic, academic_store as store

def goal_history(runtime,goal,peer):
    from base.app.companion.functional.teaching_workflow import rows
    tasks=runtime.teacher_dashboard(peer)['tasks'];history=[]
    for binding in rows(runtime,'goal_binding',peer):
        if binding['goal_ref']['id']!=goal['id']:continue
        target=academic.read(runtime,'target',binding['target_ref']['id'],peer,binding['target_ref']['revision'])
        for pub in store.rows(runtime,'publication',peer):
            if pub['draft_hash']!=binding['draft_ref']['content_hash'] or pub['mode']!='target':continue
            if pub['target']!=target['target'] or any(x['task_id']==pub['task_id'] and x['goal_ref']==binding['goal_ref'] for x in history):continue
            task=next((t for t in tasks if t['id']==pub['task_id']),None)
            if not task:continue
            rep=academic.report(runtime,task['pack']['academic']['route_id'],peer)
            results=[x for x in rep['target_results'] if x['task_id']==task['id']]
            history.append({'task_id':task['id'],'created':task['created'],'goal_ref':binding['goal_ref'],
                'current_goal_version':binding['goal_ref']==ref(goal),'draft_ref':binding['draft_ref'],
                'task_state':task['state'],'results':results,'state':'not_submitted' if not results else 'recorded'})
    return {'goal':goal,'history':sorted(history,key=lambda x:(x['created'],x['task_id'])),
            'comparison':'只在目标版本一致、评分和帮助条件明确时比较本次结果。'}

def rich_report(runtime,route_id,peer,audience):
    from base.app.companion.functional.teaching_workflow import rows
    rep=academic.report(runtime,route_id,peer);rr=rep['route'];tasks=academic.route_tasks(runtime,rr,peer)
    goals=rows(runtime,'goal',peer);histories=[goal_history(runtime,g,peer) for g in goals]
    coverage=[]
    for h in histories:
        relevant=[x for x in h['history'] if x['task_id'] in {t['id'] for t in tasks}]
        for label in h['goal']['outcomes']:
            points=[{'task_id':x['task_id'],'goal_ref':x['goal_ref'],'created':x['created'],**o}
                for x in relevant for result in x['results'] for o in result['outcomes'] if o['target']==label]
            current_points=[x for x in points if x['goal_ref']==ref(h['goal'])]
            coverage.append({'goal_id':h['goal']['id'],'title':h['goal']['title'],'outcome':label,
                'checks':points,'state':'unmeasured' if not current_points else current_points[-1]['state']})
    week_start=date.today()-timedelta(days=date.today().weekday())
    recent=[t for t in tasks if any(a['created'][:10]>=week_start.isoformat() for a in t['attempts'])]
    counts={'assigned':len(tasks),'submitted':rep['submitted'],'this_week_submitted':len(recent),
            'pending_reviews':rep['pending_reviews'],'cause_checks_pending':rep['unconfirmed_problems']}
    summary={'route_title':rr['title'],'goal':rr['goal'],'counts':counts,'coverage':coverage,
        'next_action':rep['next']['action'],'weekly_rhythm':{'sessions':rr['weekly_sessions'],
            'sequence':['核对反馈与困难','针对困难练习','换未见题独立复测']},'audience':audience,
        'note':'作答与评分按本次记录呈现；每次复测保留日期、目标版本和帮助条件。'}
    if audience=='teacher':summary.update(evidence=rep,goal_histories=histories,
        prep_queue=[x for x in rows(runtime,'prep',peer) if x['route_id']==route_id and x['state']!='done'])
    return summary

def prepare_class(runtime,r,p):
    c=store.get(runtime,'class',p.id)
    if c['archived'] or c['revision']!=p.expected_revision:raise ValueError('班级版本变化或已归档')
    if len({m.peer_id for m in p.mappings})!=len(p.mappings) or {m.peer_id for m in p.mappings}!=set(c['peers']):raise ValueError('须为冻结名单中的每个学生填写一次路线和范围映射')
    source=store.get(runtime,'draft',p.source_draft_id,p.source_revision)
    current=academic.current_draft(runtime,source['id'],source['peer_id'])
    if current['content_hash']!=source['content_hash']:raise ValueError('源草稿已有新版本')
    review=next((x for x in store.rows(runtime,'draft_review',source['peer_id']) if x['draft_hash']==source['content_hash']),None)
    if not review:raise ValueError('源草稿须先完成整份人工审校')
    sr=academic.route(runtime,source['route_id'],source['peer_id'])
    specs=[scope_signature(s) for s in academic.refs(runtime,source['body']['scope_ids'],sr['id'],source['peer_id'])]
    from base.app.companion.functional.teaching_workflow import rows
    blueprint=next((v for v in rows(runtime,'blueprint',source['peer_id']) if v['draft_ref']==ref(source)),None)
    return {'class':c,'draft':source,'source_route':sr,'review':review,'scope_specs':specs,'blueprint':blueprint}

def assign_class(runtime,r,p,plan):
    from base.app.companion.functional.teaching_workflow import child,save,rows
    c=plan['class'];source=plan['draft'];sr=plan['source_route'];entries=[]
    # Each child operation has its own durable receipt; retry reuses successful members.
    previous=next((v for v in rows(runtime,'batch') if v.get('request_id')==r.request_id),None)
    done={x['peer_id']:x for x in previous['entries'] if x.get('task_id')} if previous else {}
    if previous and len(done)==len(c['peers']):return {'batch':previous,'partial':False}
    for m in p.mappings:
        if m.peer_id in done:entries.append(done[m.peer_id]);continue
        try:
            rr=academic.route(runtime,m.route_id,m.peer_id);ss=academic.refs(runtime,m.scope_ids,m.route_id,m.peer_id)
            if (rr['level'],rr['grade'])!=(sr['level'],sr['grade']):raise ValueError('学段年级不一致，需单独审题')
            if sorted(digest(scope_signature(s)) for s in ss)!=sorted(digest(s) for s in plan['scope_specs']):raise ValueError('范围内容不等价，请先核对对应教材单元再重试')
            body=copy.deepcopy(source['body']);body['scope_ids']=m.scope_ids
            d=child(runtime,r,'k12.draft.save',{'route_id':m.route_id,'body':body},peer=m.peer_id,tag='class-draft')['record']
            child(runtime,r,'k12.draft.review',{'id':d['id'],'expected_revision':d['revision'],'draft_hash':d['content_hash'],
                'questions':plan['review']['questions'],'human_review_confirmed':True,
                'audio_listened':plan['review']['audio_listened'],'resolution_note':'教师确认等价范围映射后复用已审内容。'},peer=m.peer_id,tag='class-review')
            if plan.get('blueprint'):
                bp=plan['blueprint']
                child(runtime,r,'blueprint.save',{'id':d['id'],'expected_revision':d['revision'],
                    'template':bp['template'],'sections':bp['sections']},peer=m.peer_id,tag='class-blueprint',version='v10')
            pub=child(runtime,r,'k12.draft.publish',{'id':d['id'],'expected_revision':d['revision'],
                'human_review_confirmed':True,'mode':'practice'},peer=m.peer_id,tag='class-publish')['record']
            entries.append({'peer_id':m.peer_id,'task_id':pub['task_id'],'draft_ref':ref(d),'route_ref':ref(rr),
                            'scope_refs':[ref(s) for s in ss],'state':'queued'})
        except (ValueError,PermissionError,KeyError) as error:
            entries.append({'peer_id':m.peer_id,'state':'failed','error':str(error)})
    content={'request_id':r.request_id,'class_ref':ref(c),'source_ref':ref(source),'members':c['peers'],'entries':entries,
             'mappings':[m.model_dump() for m in p.mappings]}
    value=save(runtime,r,plan,'batch',content,old=previous)
    return {'batch':value,'partial':any(not e.get('task_id') for e in entries)}

def class_evidence(runtime,route_id,peer):
    # Common question/target/content scope, never inferred from matching grade alone.
    def signatures(rr,who):
        rep=academic.report(runtime,rr['id'],who);tasks={t['id']:t for t in academic.route_tasks(runtime,rr,who)};result={}
        for item in rep['target_results']:
            if any(o['state']=='pending' for o in item['outcomes']):continue
            t=tasks[item['task_id']];meta=t['pack']['academic'];specs=[]
            for s in meta['scope_refs']:
                value=academic.read(runtime,'scope',s['id'],who,s['revision']);specs.append(scope_signature(value))
            signature=digest({'questions':sorted(meta['question_refs'].values()),'target':meta['target'],
                              'scope':sorted(digest(s) for s in specs)})
            a=next(a for a in t['attempts'] if a['id']==item['submission_id'])
            problems=[v for v in store.rows(runtime,'problem',who) if v['task_id']==t['id'] and v['submission_id']==a['id']]
            result[signature]={'peer_id':who,'route_id':rr['id'],'task_id':t['id'],'submission_id':a['id'],
                'submitted_at':a['created'],'questions':t['pack']['items'],'original_answer':a['answer'],
                'automatic':a.get('automatic'),'teacher_scores':[v for v in store.rows(runtime,'score',who) if v['submission_id']==a['id']],
                'problems':problems,'target_result':item}
        return result
    rr=academic.route(runtime,route_id,peer);own=signatures(rr,peer);groups={}
    for other in academic.visible_routes(runtime,None):
        if other['id']==rr['id'] or other['archived'] or (other['grade'],other['level'])!=(rr['grade'],rr['level']):continue
        comparable=signatures(other,other['peer_id'])
        for signature in set(own)&set(comparable):groups.setdefault(signature,[own[signature]]).append(comparable[signature])
    return {'groups':[{'signature':key,'evidence':values} for key,values in groups.items()],
            'automatic_grouping':False,'note':'候选同时提供原题、实际作答、已记录原因和施测日期，供教师比较后决定。'}

def execute(runtime,r,p,plan):
    from base.app.companion.functional.teaching_workflow import child,save,rows,get
    op=r.operation;peer=r.peer_id
    if op=='goal.list':return {'records':rows(runtime,'goal',peer)}
    if op=='goal.save':
        academic.check_peer(runtime,peer)
        if len(set(p.outcomes))!=len(p.outcomes) or any(not x.strip() or len(x)>160 for x in p.outcomes):raise ValueError('目标项须明确且不重复，单项最多160字')
        return {'record':save(runtime,r,plan,'goal',p.model_dump(exclude={'id','expected_revision'}),peer,old=plan.get('old'))}
    if op=='goal.bind':
        d=plan['draft'];g=get(runtime,'goal',p.goal_id,peer,p.goal_revision)
        if set(p.outcomes)!=set(g['outcomes']):raise ValueError('须完整映射该目标版本的所有目标项')
        if any(v['draft_hash']==d['content_hash'] for v in store.rows(runtime,'publication',peer)):raise ValueError('已布置任务不能补录施测前目标')
        target={'title':g['title'],'threshold':g['threshold'],'outcomes':p.outcomes,'coverage_note':p.coverage_note}
        record=child(runtime,r,'k12.target.confirm',{'id':d['id'],'expected_revision':d['revision'],
            'draft_hash':d['content_hash'],'target':target,'human_review_confirmed':True})['record']
        return {'record':save(runtime,r,plan,'goal_binding',{'goal_ref':ref(g),'draft_ref':ref(d),'target_ref':ref(record)},peer)}
    if op=='goal.history':
        academic.check_peer(runtime,peer);return goal_history(runtime,get(runtime,'goal',p.id,peer),peer)
    if op=='publication.withdraw':
        task=academic.authorized_task(runtime,p.task_id,peer)
        if p.replacement_task_id:
            other=academic.authorized_task(runtime,p.replacement_task_id,peer)
            if other['id']==task['id'] or other['state']!='active':raise ValueError('替换任务须是另一份已布置的活动任务')
            if other['pack'].get('academic',{}).get('route_id')!=task['pack'].get('academic',{}).get('route_id'):raise ValueError('替换任务须属于同一学生的同一路线')
        runtime.service.base.set_state(task['id'],'archived')
        runtime.queue_task_update(peer,task['id'],event_id='withdraw-'+digest(r.request_id))
        return {'record':save(runtime,r,plan,'withdrawal',{'task_id':task['id'],'replacement_task_id':p.replacement_task_id,
                'reason':p.reason,'state':'withdrawn','original_answers_retained':True},peer),'delivery':'queued'}
    if op=='report.read':return rich_report(runtime,p.route_id,peer,p.audience)
    if op=='report.weekly_plan':
        rep=rich_report(runtime,p.route_id,peer,'teacher');rr=academic.route(runtime,p.route_id,peer)
        start=date.fromisoformat(p.start_date);sessions=rr['weekly_sessions'];steps=[]
        actions=[rep['next_action'],'围绕已核对困难完成一组针对性练习，并保存原始作品。','用未见题独立复测同一目标；记录帮助条件，主观作品交老师评阅。']
        for i in range(max(3,sessions)):
            steps.append({'id':'step'+str(i+1),'action':actions[min(i,2)],'minutes':p.session_minutes,
                          'due_date':(start+timedelta(days=i*7//sessions)).isoformat()})
        content={'title':rr['title']+' · 下一轮学习安排','goal':rr['goal'],'steps':steps,
            'task_ids':[t['id'] for t in academic.route_tasks(runtime,rr,peer) if t['state']=='active'][:20],
            'reason':rep['next_action']+'；依据当前已交、待评和目标覆盖记录生成，老师可在学习安排中修改后分享。'}
        data=child(runtime,r,'path.create',content,version='v5')
        return {**data,'published':False,'next_entry':'schedule','evidence_hash':digest(rep)}
    if op=='class.assign':return assign_class(runtime,r,p,plan)
    if op=='class.report':
        c=store.get(runtime,'class',p.id);values=[]
        for b in rows(runtime,'batch'):
            if b['class_ref']['id']!=p.id:continue
            for e in b['entries']:
                row={**e,'batch_id':b['id']}
                if e.get('task_id'):
                    task=academic.authorized_task(runtime,e['task_id'],e['peer_id']);a=task['attempts'][-1] if task['attempts'] else None
                    row['state']='not_submitted' if not a else 'submitted'
                    row['objective']={k:(a.get('automatic') or {}).get(k) for k in ['score','total']} if a else None
                    if a:
                        scores={v['question_id'] for v in store.rows(runtime,'score',e['peer_id']) if v['submission_id']==a['id']}
                        if any(q.get('open_response') and q['id'] not in scores for q in task['pack']['items']):row['state']='pending_review'
                values.append(row)
        return {'class':c,'rows':values,'batches':[b for b in rows(runtime,'batch') if b['class_ref']['id']==p.id],
                'legacy':academic.class_report(runtime,p.id)}
    if op=='class.evidence':return class_evidence(runtime,p.route_id,peer)
    raise ValueError('未知教学工作流操作')
