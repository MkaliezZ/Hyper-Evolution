"use strict";
// Teacher additions stay inside existing pages. The final student projection stays last.
const c10=(operation,payload={},peer_id=academicPeer(),request_id=uid())=>api('/api/local/capabilities/invoke',{
    contract_version:'companion.capability.v10',operation,payload,peer_id,request_id});
let wfScopes=[],wfCurrentDraft=null,wfRoster=[];
const wfButton=(action,label,id='')=>`<button type="button" class="btn ghost small" data-action="wf-${action}" data-id="${h(id)}">${h(label)}</button>`;
const wfCheck=label=>`<label class="checkline"><input type="checkbox" name="confirmed" required>${h(label)}</label>`;
const wfScopeFields=()=>`<fieldset><legend>本次范围（可不选，按明确考点准备）</legend>${wfScopes.filter(s=>s.order<=academicRoute.scope_order).map(s=>`<label class="checkline"><input type="checkbox" name="scope_ids" value="${h(s.id)}">${h(s.textbook)} · ${h(s.unit)}</label>`).join('')||'<p class="small muted">当前尚未登记教材范围。</p>'}</fieldset>`;
function wfDownload(name,text,type='text/plain;charset=utf-8'){
    const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function wfPlainReport(rep){
    return `${rep.route_title}\n${rep.audience==='parent'?'家长版':'学习版'}学习报告\n当前目标：${rep.goal}\n\n任务 ${rep.counts.assigned} 项，已交 ${rep.counts.submitted} 项；本周提交 ${rep.counts.this_week_submitted} 项，待评 ${rep.counts.pending_reviews} 题。\n\n目标记录：\n${rep.coverage.map(c=>`${c.title} / ${c.outcome}：${wfState(c.state)}`).join('\n')||'尚未安排固定目标测验。'}\n\n下一步：${rep.next_action}\n建议节奏：每周 ${rep.weekly_rhythm.sessions} 次，先核对反馈，再练习，最后用新题复测。\n${rep.note}`;
}
function wfState(s){return ({unmeasured:'尚未测到',pending:'待核对',meets_this_target:'本次达到参考线',needs_more_evidence:'安排补练与新题验证',planned:'待准备',in_progress:'准备中',done:'已完成',paused:'已暂停'})[s]||s;}

const wfPreviousTeacherHome=workspaceTeacherHome;
workspaceTeacherHome=async function(){
    await wfPreviousTeacherHome();
    if(academicContext?.selection.subject!=='english')return;
    $('#workspace-content')?.insertAdjacentHTML('beforeend',`<section class="card wf-panel"><h2>预登记学生</h2><p>还没配对也可以先登记姓名和备注。配对后关联学生设备，继续使用同一份档案。</p>${wfButton('roster','打开预登记与配对关联')}</section>`);
};
const wfPreviousPane=academicPane;
academicPane=async function(){
    const existing=await wfPreviousPane();if(!workspaceTeacher())return existing;
    const route=academicRoute,peer=academicPeer();
    wfScopes=(await c7('scope.list',{route_id:route.id},peer)).data.records;
    if(academicTab==='drafts'){
        const drafts=(await c7('k12.draft.list',{route_id:route.id},peer)).data.records;
        return `<section class="card wf-panel"><span class="eyebrow">备题工作流</span><h2>先找已审题，缺的再补。</h2><p>选考点与题数，系统先查本机题库并排除已布置题。基础考点可免费准备原创候选；其他缺题可用自己的API补充。</p><form id="wf-prepare" class="local-form"><div class="inline-grid"><label class="field">本次考点<input name="focus" required value="${h(route.goal)}" list="wf-focus"><datalist id="wf-focus"><option>be动词主谓一致</option><option>细节理解</option></datalist></label><label class="field">需要题数<input name="count" type="number" value="5" min="1" max="80" required></label></div>${wfScopeFields()}<div class="actions"><button class="btn accent" name="method" value="basic" type="submit">查题库并准备基础候选</button><button class="btn ghost" name="method" value="model" type="submit">缺题时用我的API补充</button></div><p class="small muted">基础练习目前支持主谓一致、阅读细节；所有候选均需教师审题。一次API任务最多补10题，其余缺口会保留。</p></form><div id="wf-prepare-result" aria-live="polite"></div></section>${existing}<section class="card"><h2>继续一份草稿</h2>${drafts.map(d=>`<article class="local-task"><div><strong>${h(d.body.title)}</strong><p class="small muted">第${d.revision}版 · ${d.body.questions.length}题</p></div><div class="actions">${wfButton('resume','继续审题',d.id)}${wfButton('patch','只改一道题',d.id)}${wfButton('fill','继续补题',d.id)}${wfButton('blueprint','分区 / 分值 / 时长',d.id)}${wfButton('bank-export','存入教师题库',d.id)}${wfButton('bind-goal','关联固定复测目标',d.id)}</div></article>`).join('')||'<p>准备候选后，会在这里继续。</p>'}</section>`;
    }
    if(academicTab==='scopes')return `${existing}<section class="card wf-panel"><h2>可复用教材目录</h2><p>把有权使用的教材词表登记一次，核对后再应用到各学生的对应路线。</p><div class="actions">${wfButton('curriculum','登记 / 导入目录')}${wfButton('curriculum-list','选目录应用到当前学生')}${wfButton('lexical','词形、专名与中文词注检查')}${wfButton('forecast','安排后续单元备题')}</div></section>`;
    if(academicTab==='bank'){
        const bank=(await c10('bank.list',{},null)).data.records;
        return `${existing}<section class="card wf-panel"><h2>教师本机共享题库</h2><p>经教师明确选入的原创或获授权题目，可在教材范围匹配后给其他学生重新组题。原始作答、档案和教师私有备注不随题目入库。</p>${bank.filter(x=>!x.retired).map(x=>`<details><summary>${h(x.question.skill)} · ${h(x.question.prompt)}</summary><p>${h(x.question.material)}</p><p class="small muted">来源：${h(x.source)} · ${x.grade}年级</p>${wfButton('bank-retire','停用此题',x.id)}</details>`).join('')||'<p>先在“练习与审题”完成审校，再点“存入教师题库”。</p>'}</section>`;
    }
    if(academicTab==='report'){
        const [report,goals,prep]=await Promise.all([c10('report.read',{route_id:route.id}),c10('goal.list'),c10('prep.list',{route_id:route.id})]);
        return `${existing}<section class="card wf-panel"><h2>固定目标与连续复测</h2><p>先登记目标，再在布置前关联题号。后面的新题复测会沿用目标编号，保留每次目标版本、日期和帮助条件。</p>${wfButton('goal-new','＋ 登记固定目标')}${goals.data.records.map(g=>`<p><strong>${h(g.title)}</strong> · 第${g.revision}版 ${wfButton('goal-history','查看历次复测',g.id)}</p>`).join('')}<div class="actions">${wfButton('report-learner','查看学习版报告')}${wfButton('report-parent','查看家长版报告')}${wfButton('weekly','生成下一轮候选安排')}</div><p class="small muted">安排会进入现有“学习安排”，由老师修改并另行发布。</p></section><section class="card"><h2>备课队列</h2>${prep.data.records.map(p=>`<article class="local-task"><div><strong>${h(p.skill)}</strong><p>${h(p.due_date)} · 库存${p.available} / 计划${p.requested}，缺${p.missing} · ${h(wfState(p.state))}</p></div>${wfButton('prep-state','更新进度',p.id)}</article>`).join('')||'<p>在教材范围页安排后续单元备题，不会自动推进学生进度。</p>'}<p>建议每周 ${report.data.weekly_rhythm.sessions} 次：核对 → 训练 → 新题复测。</p></section>`;
    }
    if(academicTab==='classes'){
        const classes=(await c7('k12.class.list',{},null)).data.classes;
        return `${existing}<section class="card wf-panel"><h2>逐人映射教材范围后布置</h2><p>给每位学生选择其自己的路线和等价单元，系统逐人核验。已发送的任务保留，失败的学生可单独重试。</p>${classes.filter(c=>!c.archived).map(c=>`<p>${h(c.title)} ${wfButton('class-map','映射并布置',c.id)} ${wfButton('class-report','批次状态 / 重试',c.id)}</p>`).join('')}${wfButton('group-evidence','查看可比较的原题与作答证据')}</section>`;
    }
    return existing;
};

async function wfRosterDialog(){
    wfRoster=(await c10('roster.list',{},null)).data.records;
    academicDialog('预登记与设备关联',`<p>同名学生请在名字里加上班级或其他区别，别名也会检查重名。</p><div>${wfRoster.map(v=>`<p><strong>${h(v.name)}</strong> · ${v.paired_peer_id?'已关联设备':'尚未配对'} ${wfButton('roster-edit','修改 / 关联',v.id)}</p>`).join('')}</div>${wfRosterForm()}`);
}
function wfRosterForm(v=null){return `<form id="wf-roster" class="local-form" data-id="${h(v?.id||'')}" data-revision="${v?.revision||0}"><label class="field">学生姓名<input name="name" required maxlength="80" value="${h(v?.name||'')}"></label><label class="field">别名（每行一个）<textarea name="aliases">${h(v?.aliases.join('\n')||'')}</textarea></label><label class="field">教师备注<textarea name="note" maxlength="1000">${h(v?.note||'')}</textarea></label><label class="field">关联已配对的设备<select name="peer_id"><option value="">先登记，稍后关联</option>${status.peers.filter(p=>p.role==='student'&&p.state==='active').map(p=>`<option value="${h(p.id)}" ${p.id===v?.paired_peer_id?'selected':''}>${h(p.name)} · ${h(p.id.slice(-8))}</option>`).join('')}</select></label><button class="btn accent" type="submit">保存档案</button></form>`;}

async function wfDraft(id){return (await c10('workflow.resume',{id})).data;}
async function wfContinue(id){
    const data=await wfDraft(id);wfCurrentDraft=data.draft;
    await academicReview(id);
    const form=$('#academic-review-form');if(!form)return;
    form.insertAdjacentHTML('afterbegin',`<div class="local-banner">尚有 ${data.review_state.pending.length} 题待审。${data.review_state.pending.map(h).join('、')||'全部题目已保留审校记录，可确认整份审校。'}<p>每题可以单独保存，下次回来接着审。</p></div>`);
    form.querySelectorAll('fieldset').forEach((field,i)=>{
        const q=wfCurrentDraft.body.questions[i];if(!q)return;
        const saved=data.review_state.accepted[q.id];
        if(saved){
            field.insertAdjacentHTML('afterbegin','<p class="status-pill">已有有效的人工审校记录</p>');
            form.elements['basis_'+i].value=saved.basis;form.elements['ambiguity_'+i].value=saved.ambiguity_check;
            for(const choice of saved.choices){const key=i+'_'+choice.option;form.elements['defensible_'+key].checked=choice.defensible;
                for(const [name,value] of [['reason',choice.reasoning],['why',choice.why_not],['next',choice.next_step]])form.elements[name+'_'+key].value=value;}
        }
        field.insertAdjacentHTML('beforeend',`<button type="button" class="btn ghost" data-action="wf-review-item" data-index="${i}">保存本题审校</button>`);
    });
    form.insertAdjacentHTML('beforeend',wfButton('finalize-review','使用保留记录，确认整份审校',id));
}
function wfItemReview(form,q,i){return {question_id:q.id,basis:form.elements['basis_'+i].value,
    ambiguity_check:form.elements['ambiguity_'+i].value,choices:academicKinds.includes(q.type)?q.options.map((_,j)=>{
        const letter=String.fromCharCode(65+j);return {option:letter,defensible:form.elements[`defensible_${i}_${letter}`].checked,
            reasoning:form.elements[`reason_${i}_${letter}`].value,why_not:form.elements[`why_${i}_${letter}`].value,next_step:form.elements[`next_${i}_${letter}`].value};}):[]};}
async function wfPatchDialog(id){
    wfCurrentDraft=(await wfDraft(id)).draft;
    academicDialog('局部修改：其他题的有效审校会保留',`<label class="field">选择题目<select id="wf-patch-select">${wfCurrentDraft.body.questions.map(q=>`<option value="${h(q.id)}">${h(q.id)} · ${h(q.prompt.slice(0,70))}</option>`).join('')}</select></label><div id="wf-patch-fields"></div>`);wfPatchFields();
}
function wfPatchFields(){
    const q=wfCurrentDraft.body.questions.find(q=>q.id===$('#wf-patch-select').value);
    $('#wf-patch-fields').innerHTML=`<form id="wf-patch" class="local-form" data-qid="${h(q.id)}"><label class="field">考点<input name="skill" required value="${h(q.skill)}"></label><label class="field">题型<select name="type">${academicOptions(academicCatalog.types,q.type)}</select></label>${[['material','本题材料'],['prompt','题干'],['options','选项（每行一个）'],['key','答案（每行一个）'],['evidence','原文依据'],['explanation','讲解'],['traps','错项类型（例如 B:张冠李戴，每行一个）']].map(([key,label])=>`<label class="field">${label}<textarea name="${key}" ${key==='prompt'?'required':''}>${h(Array.isArray(q[key])?q[key].join('\n'):key==='traps'?Object.entries(q.traps).map(([k,v])=>k+':'+v).join('\n'):q[key]||'')}</textarea></label>`).join('')}<label class="field">本题分值<input type="number" name="points" min="0.1" max="100" step="0.1" value="${q.points}"></label><button class="btn accent" type="submit">另存新版本，只重审受影响题目</button></form>`;
}
async function wfBlueprint(id){
    wfCurrentDraft=(await wfDraft(id)).draft;const d=wfCurrentDraft;
    const old=(await c10('blueprint.read',{id})).data;const groups={};
    for(const q of d.body.questions)(groups[q.type]??=[]).push(q);
    const sections=old.current?old.record.sections:Object.entries(groups).map(([type,qs])=>({title:academicCatalog.types[type],types:[type],question_ids:qs.map(q=>q.id),count:qs.length,points:qs.reduce((a,q)=>a+q.points,0),minutes:Math.max(2,qs.length*2)}));
    academicDialog('整卷蓝图：题数、分值与练习时长',`<form id="wf-blueprint" class="local-form"><p>按本次教师自编练习设置分区。保存后会随作业签名发送，学生可使用本机练习计时器。</p><label class="field">用途<select name="template"><option value="k12-custom">K12 自定义整卷</option><option value="toefl-2026">托福2026专项标签</option><option value="ielts-academic-computer">雅思学术类机考专项标签</option></select></label>${sections.map((s,i)=>`<fieldset data-wf-section="${i}"><label class="field">分区名称<input name="title_${i}" value="${h(s.title)}" required></label><label class="field">题号（用逗号分开）<input name="ids_${i}" value="${h(s.question_ids.join(','))}" required></label><label class="field">建议分钟数<input type="number" name="minutes_${i}" value="${s.minutes}" min="1" max="240" required></label><p>${s.count}题 · ${s.points}分，保存时按实际题目重新核对。</p></fieldset>`).join('')}<p class="small muted">托福、雅思选项用于标明专项用途；完整自适应模考与官方分数换算另需专用引擎。</p><button class="btn accent" type="submit">保存当前草稿的蓝图</button></form>`);
    if(old.current)$('#wf-blueprint').elements.template.value=old.record.template;
}
async function wfCurriculum(){academicDialog('先登记目录，再预览核对',`<form id="wf-curriculum" class="local-form"><label class="field">教材名称<input name="title" required></label><label class="field">来源与可用范围<input name="source" required minlength="3" placeholder="例如：教师自编讲义，限本班使用"></label><div class="inline-grid"><label class="field">单元名称<input name="unit" value="Unit 1" required></label><label class="field">单元顺序<input name="order" value="1" type="number" min="1" max="1000" required></label></div>${[['words','词表'],['phrases','短语'],['grammar','语法与操作']].map(([k,l])=>`<label class="field">${l}（每行一项）<textarea name="${k}"></textarea></label>`).join('')}<label class="checkline"><input name="complete" type="checkbox">本单元范围已完整列出</label><details><summary>已有词表或目录？导入TXT / Markdown / JSON</summary><p class="small muted">字段：title、source、units；单元含 unit、order、words、phrases、grammar、complete。</p><input id="wf-curriculum-file" type="file" accept=".json,.txt,.md">${wfButton('curriculum-template','下载原创目录模板')}<textarea name="import_json" aria-label="导入目录JSON"></textarea><label class="field">带单元标题的原始词表<textarea name="extract_text" placeholder="Unit 1&#10;Words: child, run, be&#10;Phrases: look at&#10;Grammar: 主谓一致"></textarea></label></details><button class="btn accent" type="submit">预览目录</button></form>`);}
async function wfCurriculumList(){
    const data=(await c10('curriculum.list',{},null)).data.records;
    academicDialog('把目录应用到当前学生',`${data.map(c=>`<form class="local-form wf-book-apply" data-id="${h(c.id)}" data-revision="${c.revision}"><h3>${h(c.title)}</h3><p>${h(c.source)}</p>${c.units.map(u=>`<label class="checkline"><input name="orders" value="${u.order}" type="checkbox" ${u.order>academicRoute.scope_order?'disabled':''}>${h(u.unit)} · ${u.words.length}词${u.order>academicRoute.scope_order?'（超出当前进度，先调整路线）':''}</label>`).join('')}<button class="btn accent" type="submit">应用所选单元</button></form>`).join('')||'<p>先登记并核对教材目录。</p>'}`);
}
async function wfGoalDialog(){academicDialog('登记可重复检查的目标',`<form id="wf-goal" class="local-form"><label class="field">目标名称<input name="title" required value="${h(academicRoute.goal)}"></label><label class="field">具体目标项（每行一项）<textarea name="outcomes" required placeholder="例如：辨认主语并选对be动词"></textarea></label><label class="field">本次试行参考线<input type="number" name="threshold" min="0.1" max="1" step="0.05" value="0.8"></label><button class="btn accent" type="submit">保存固定目标</button></form>`);}
async function wfGoalBind(id){
    const d=(await wfDraft(id)).draft;wfCurrentDraft=d;const goals=(await c10('goal.list')).data.records;
    academicDialog('布置前关联固定目标',`<form id="wf-bind" class="local-form"><label class="field">选择目标<select name="goal" id="wf-goal-select">${goals.map(g=>`<option value="${h(g.id)}" data-revision="${g.revision}" data-outcomes="${h(JSON.stringify(g.outcomes))}">${h(g.title)} · 第${g.revision}版</option>`).join('')}</select></label><div id="wf-bind-fields"></div><label class="field">覆盖说明<textarea name="coverage_note" required minlength="4" placeholder="题号如何覆盖目标，哪些内容尚未测到？"></textarea></label>${wfCheck('确认这是布置前设定的测验目标；本次使用独立作答条件。')}<button class="btn accent" type="submit" ${goals.length?'':'disabled'}>确认本次题号覆盖</button></form>${goals.length?'':'<p>先在“问题与学习报告”登记一个固定目标。</p>'}`);wfBindFields();
}
function wfBindFields(){const option=$('#wf-goal-select')?.selectedOptions[0];if(!option)return;$('#wf-bind-fields').innerHTML=JSON.parse(option.dataset.outcomes).map((label,i)=>`<label class="field">${h(label)} · 对应题号<input name="outcome_${i}" required placeholder="${h(wfCurrentDraft.body.questions.map(q=>q.id).join(','))}"></label>`).join('');}

async function wfClassMap(id){
    const c=(await c7('k12.class.list',{},null)).data.classes.find(c=>c.id===id);
    const drafts=(await c7('k12.bank.list',{route_id:academicRoute.id})).data.records;
    const members=await Promise.all(c.peers.map(async peer=>{const routes=(await c7('route.list',{},peer)).data.routes.filter(r=>!r.archived);const scopes=(await Promise.all(routes.map(r=>c7('scope.list',{route_id:r.id},peer)))).flatMap(x=>x.data.records);return {peer,routes,scopes};}));
    academicDialog('逐人选择路线和等价教材范围',`<form id="wf-class-map" class="local-form" data-id="${h(c.id)}" data-revision="${c.revision}"><label class="field">源草稿（当前学生的已审版本）<select name="draft" required>${drafts.map(d=>`<option value="${h(d.id)}" data-revision="${d.revision}">${h(d.body.title)} · 第${d.revision}版</option>`).join('')}</select></label>${members.map((m,i)=>`<fieldset data-wf-member="${h(m.peer)}"><legend>${h(status.peers.find(p=>p.id===m.peer)?.name||m.peer)}</legend><label class="field">学生自己的路线<select name="route_${i}" required>${m.routes.map(r=>`<option value="${h(r.id)}">${h(r.title)}</option>`).join('')}</select></label>${m.scopes.map(s=>`<label class="checkline"><input type="checkbox" name="scope_${i}" value="${h(s.id)}" data-route="${h(s.route_id)}">${h(s.textbook)} · ${h(s.unit)}</label>`).join('')||'<p>尚未登记范围；源草稿也无范围时可继续。</p>'}</fieldset>`).join('')}${wfCheck('已核对每位学生的路线与等价范围，同意逐人布置。')}<button class="btn accent" type="submit" ${drafts.length?'':'disabled'}>逐人核验并布置</button></form>`);
}

const wfPreviousOpenTask=openTask;
openTask=async function(id){
    await wfPreviousOpenTask(id);const t=currentTask;if(!t?.pack?.academic)return;
    if(workspaceTeacher())$('#workspace-content').insertAdjacentHTML('beforeend',`<section class="card"><h3>本次任务需要替换或撤回？</h3><p>撤回后学生停止继续提交，原答和已有反馈保留。</p>${wfButton('withdraw','撤回 / 关联替换任务',id)}</section>`);
    const bp=t.pack.teaching_blueprint;if(!bp)return;
    const timingAllowed=!workspaceTeacher()&&t.state==='active'&&!(t.pack.academic.mode==='target'&&(t.attempts.length||t.local_submissions?.length));
    $('#workspace-content').insertAdjacentHTML('afterbegin',`<section class="card wf-panel"><h3>本次练习蓝图 · ${bp.minutes}分钟 / ${bp.total_points}分</h3>${bp.sections.map(s=>`<p>${h(s.title)}：${s.count}题 · ${s.points}分 · 建议${s.minutes}分钟</p>`).join('')}${timingAllowed?`${wfButton('timer','开始 / 继续练习计时',id)} <output id="wf-timer" aria-live="polite">本机练习计时，不自动交卷</output>`:''}</section>`);
};
let wfTimer=null;
function wfStartTimer(){
    clearInterval(wfTimer);const task=currentTask,key='growth-practice-timer:'+status.device_id+':'+task.id;
    let end=Number(localStorage.getItem(key));if(!end){end=Date.now()+task.pack.teaching_blueprint.minutes*60000;localStorage.setItem(key,String(end));}
    const tick=()=>{const out=$('#wf-timer');if(!out||currentTask.id!==task.id){clearInterval(wfTimer);return;}const left=Math.max(0,Math.ceil((end-Date.now())/1000));out.textContent=left?`剩余 ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`:'建议时间已到，请保存作答后主动提交。';if(!left)clearInterval(wfTimer);};tick();wfTimer=setInterval(tick,1000);
}

document.addEventListener('change',async e=>{try{
    if(e.target.id==='wf-patch-select')wfPatchFields();
    if(e.target.id==='wf-goal-select')wfBindFields();
    if(e.target.closest('#wf-class-map')&&e.target.name.startsWith('route_')){
        const member=e.target.closest('fieldset');member.querySelectorAll('input[data-route]').forEach(input=>{input.disabled=input.dataset.route!==e.target.value;if(input.disabled)input.checked=false;input.closest('label').hidden=input.disabled;});
    }
    if(e.target.id==='wf-curriculum-file'){const file=e.target.files[0],form=$('#wf-curriculum');form.elements.import_json.value='';form.elements.extract_text.value='';form.elements[file.name.toLowerCase().endsWith('.json')?'import_json':'extract_text'].value=await file.text();}
}catch(error){notify(error.message,true);}});

document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-action^="wf-"]');if(!button)return;
    const action=button.dataset.action.slice(3),id=button.dataset.id;button.disabled=true;
    try{
        if(action==='roster')await wfRosterDialog();
        else if(action==='roster-edit')academicDialog('修改预登记与设备关联',wfRosterForm(wfRoster.find(v=>v.id===id)));
        else if(action==='resume')await wfContinue(id);
        else if(action==='patch')await wfPatchDialog(id);
        else if(action==='blueprint')await wfBlueprint(id);
        else if(action==='fill'){
            const state=await wfDraft(id);wfCurrentDraft=state.draft;
            academicDialog('在当前草稿上继续补题',`<form id="wf-fill" class="local-form"><p>已有${wfCurrentDraft.body.questions.length}题，本次最多调用自己的API补10题；新题会合并到这份草稿。</p><label class="field">补到总题数<input type="number" name="count" min="${wfCurrentDraft.body.questions.length+1}" max="80" value="${Math.min(80,state.preparation?.requested>wfCurrentDraft.body.questions.length?state.preparation.requested:wfCurrentDraft.body.questions.length+3)}" required></label><button class="btn accent" type="submit">用我的API补充候选</button></form>`);
        }
        else if(action==='review-item'){
            const f=$('#academic-review-form'),i=Number(button.dataset.index),d=wfCurrentDraft;
            if(!f.elements.human_review_confirmed.checked)throw Error('请实际核对后勾选教师审校确认。');
            const result=(await c10('draft.review_items',{id:d.id,expected_revision:d.revision,questions:[wfItemReview(f,d.body.questions[i],i)],human_review_confirmed:true,audio_listened:f.elements.audio_listened?.checked||false})).data;
            notify(`本题已保存，尚有${result.review_state.pending.length}题待审。`);
        }else if(action==='finalize-review'){
            const f=$('#academic-review-form');if(!f.elements.human_review_confirmed.checked)throw Error('请核对后勾选教师确认。');
            await c10('draft.finalize_review',{id,expected_revision:wfCurrentDraft.revision,human_review_confirmed:true,audio_listened:f.elements.audio_listened?.checked||false,resolution_note:f.elements.resolution_note?.value||''});closeModal();await academicHome();notify('整份审校已确认，布置仍需另行操作。');
        }else if(action==='bank-export'){
            wfCurrentDraft=(await wfDraft(id)).draft;academicDialog('加入教师本机题库',`<form id="wf-export" class="local-form"><label class="field">来源与复用范围<input name="reuse_source" required minlength="3" value="${h(wfCurrentDraft.body.source)}"></label>${wfCheck('我有权复用这些题目，且已检查并清除学生个人信息。')}<button class="btn accent" type="submit">加入教师题库</button></form>`);
        }else if(action==='bank-retire'){await c10('bank.retire',{id,reason:'教师在本机共享题库明确停用。'},null);await academicHome();}
        else if(action==='curriculum')await wfCurriculum();
        else if(action==='curriculum-list')await wfCurriculumList();
        else if(action==='curriculum-template')wfDownload('原创教材目录示例.json',JSON.stringify({title:'原创课本',source:'教师原创示例，可修改使用',units:[{unit:'Unit 1',order:1,words:['be','child','run'],phrases:[],grammar:['主谓一致'],complete:false}]},null,2),'application/json');
        else if(action==='curriculum-commit'){
            if(!$('#wf-book-confirm').checked)throw Error('请先核对目录并勾选确认。');
            await c10('curriculum.commit',{id,expected_revision:Number(button.dataset.revision),content_hash:button.dataset.hash,human_review_confirmed:true},null);closeModal();await academicHome();notify('教材目录已保存，可应用到不同学生。');
        }else if(action==='lexical')academicDialog('核对词形、专名和中文词注',`<form id="wf-lexical" class="local-form">${wfScopeFields()}<label class="field">检查文本<textarea name="text" required></textarea></label><label class="field">明确豁免词（每行一个）<textarea name="exemptions"></textarea></label><label class="field">专名（每行一个）<textarea name="proper_names"></textarea></label><button class="btn accent" type="submit">按所选范围检查</button></form><div id="wf-lexical-result"></div>`);
        else if(action==='forecast')academicDialog('安排单元备题',`<form id="wf-forecast" class="local-form"><p>可提前备后续单元，不改变学生已学进度。</p>${wfScopes.map(s=>`<label class="checkline"><input type="checkbox" name="scope_ids" value="${h(s.id)}">${h(s.unit)}</label>`).join('')}<label class="field">考点（每行一个）<textarea name="skills" required></textarea></label><label class="field">每个单元每个考点题数<input name="count" type="number" min="1" max="80" value="5"></label><label class="field">备好日期<input type="date" name="due_date" required></label><button class="btn accent" type="submit">核对库存并加入备课队列</button></form>`);
        else if(action==='prep-state'){
            const p=(await c10('prep.list',{route_id:academicRoute.id})).data.records.find(p=>p.id===id);
            academicDialog('更新备课进度',`<form id="wf-prep-state" class="local-form" data-id="${h(p.id)}" data-revision="${p.revision}"><label class="field">进度<select name="state">${['planned','in_progress','done','paused'].map(s=>`<option value="${s}" ${p.state===s?'selected':''}>${h(wfState(s))}</option>`).join('')}</select></label><button class="btn accent" type="submit">保存进度</button></form>`);
        }else if(action==='goal-new')await wfGoalDialog();
        else if(action==='bind-goal')await wfGoalBind(id);
        else if(action==='goal-history'){
            const data=(await c10('goal.history',{id})).data;
            academicDialog(data.goal.title+' · 历次复测',`${data.history.map(v=>`<article><p>${h(v.created)} · 目标第${v.goal_ref.revision}版 · ${v.current_goal_version?'当前目标版本':'历史目标版本'}</p>${v.results.flatMap(r=>r.outcomes).map(o=>`<p>${h(o.target)}：${o.score}/${o.total} · ${h(wfState(o.state))}</p>`).join('')||'<p>尚未提交。</p>'}${wfButton('open-work','查看原始任务',v.task_id)}</article>`).join('')||'<p>先在布置前关联目标，并以“目标测验”发布新题。</p>'}`);
        }else if(action.startsWith('report-')){
            const audience=action.slice(7),rep=(await c10('report.read',{route_id:academicRoute.id,audience})).data;
            academicDialog(audience==='parent'?'家长版学习报告':'学习版报告',`<pre class="wf-readable">${h(wfPlainReport(rep))}</pre><button class="btn accent" type="button" id="wf-report-download">下载文字报告</button>`);
            $('#wf-report-download').onclick=()=>wfDownload(`${academicRoute.title}-${audience}报告.txt`,wfPlainReport(rep));
        }else if(action==='weekly')academicDialog('生成下一轮候选安排',`<form id="wf-weekly" class="local-form"><p>按已登记的每周学习次数安排核对、训练和复测；每周次数少时，本轮三步会跨周。</p><label class="field">从哪天开始<input type="date" name="start_date" required value="${new Date().toISOString().slice(0,10)}"></label><label class="field">每次分钟数<input type="number" name="minutes" value="20" min="5" max="120"></label><button class="btn accent" type="submit">生成并去学习安排查看</button></form>`);
        else if(action==='class-map')await wfClassMap(id);
        else if(action==='class-report'){
            const data=(await c10('class.report',{id},null)).data;
            academicDialog(data.class.title+' · 布置记录',`${data.rows.map(v=>`<p>${h(status.peers.find(p=>p.id===v.peer_id)?.name||'学生')} · ${h(({not_submitted:'已布置，尚未提交',pending_review:'主观题待评',submitted:'已提交',failed:'本次未布置'})[v.state]||v.state)} ${h(v.error||'')}</p>`).join('')||'<p>尚无映射布置记录。</p>'}${(data.batches||[]).filter(b=>b.entries.some(e=>!e.task_id)).map(b=>`<button type="button" class="btn ghost" data-action="wf-class-retry" data-id="${h(b.id)}" data-class="${h(id)}">重试未成功成员</button>`).join('')}`);
        }else if(action==='class-retry'){
            const data=(await c10('class.report',{id:button.dataset.class},null)).data,batch=data.batches.find(b=>b.id===id);
            const result=(await c10('class.assign',{id:batch.class_ref.id,expected_revision:batch.class_ref.revision,source_draft_id:batch.source_ref.id,source_revision:batch.source_ref.revision,mappings:batch.mappings,human_review_confirmed:true},null,batch.request_id)).data;
            notify(result.partial?'部分成员仍需核对范围，已成功任务不会重复发送。':'全部成员已布置。');closeModal();
        }else if(action==='group-evidence'){
            const data=(await c10('class.evidence',{route_id:academicRoute.id})).data;
            academicDialog('相同条件下的作答证据',data.groups.map(g=>`<section><h3>可比较记录 · ${g.evidence.length}人</h3>${g.evidence.map(v=>`<details><summary>${h(status.peers.find(p=>p.id===v.peer_id)?.name||'学生')} · ${h(v.submitted_at)}</summary>${v.questions.map(q=>`<p><strong>${h(q.id)} ${h(q.prompt)}</strong></p><p>${h(q.material||'')}</p><p>原答：${h(v.original_answer.answers?.[q.id]||'')}</p>`).join('')}<p>已记录原因：${h(v.problems.map(p=>p.state+' / '+(p.cause||'待查')).join('；')||'尚未核对原因')}</p>${wfButton('open-work','查看完整作品',v.task_id)}</details>`).join('')}</section>`).join('')||'<p>还没有相同题目、目标和教材范围、且评分与帮助条件齐全的可比较记录。</p>');
        }else if(action==='open-work'){closeModal();await openTask(id);}
        else if(action==='withdraw'){
            const tasks=workspaceRows.filter(t=>t.id!==id&&t.state==='active'&&t.pack.academic?.route_id===currentTask.pack.academic.route_id);
            academicDialog('撤回并保留原答',`<form id="wf-withdraw" class="local-form" data-id="${h(id)}"><label class="field">撤回原因<textarea name="reason" required minlength="3"></textarea></label><label class="field">关联替换作业（可选）<select name="replacement"><option value="">本次只撤回</option>${tasks.map(t=>`<option value="${h(t.id)}">${h(t.pack.title)}</option>`).join('')}</select></label>${wfCheck('确认撤回当前任务，保留学生原答和反馈。')}<button class="btn accent" type="submit">确认撤回</button></form>`);
        }else if(action==='timer')wfStartTimer();
    }catch(error){notify(error.message,true);}finally{button.disabled=false;}
});

document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.id?.startsWith('wf-')&&!form.classList.contains('wf-book-apply'))return;
    event.preventDefault();const fields=new FormData(form),v=Object.fromEntries(fields),peer=academicPeer(),key=form.dataset.request||(form.dataset.request=uid());
    const button=event.submitter;button.disabled=true;
    try{
        if(form.id==='wf-roster'){
            await c10('roster.save',{id:form.dataset.id||null,expected_revision:Number(form.dataset.revision),name:v.name,aliases:academicLines(v.aliases),note:v.note,peer_id:v.peer_id||null},null,key);await wfRosterDialog();notify('学生档案已保存。');
        }else if(form.id==='wf-prepare'){
            const payload={route_id:academicRoute.id,focus:v.focus,count:Number(v.count),scope_ids:fields.getAll('scope_ids')};
            if(button.value==='model'){
                const job=await api('/api/local/jobs',{mode:'k12_workflow',peer_id:peer,...payload});
                $('#wf-prepare-result').innerHTML='<p id="academic-job-state">正在按题库 → 基础候选 → 模型补缺的顺序准备…</p>';academicPoll(job.id);
            }else{
                const result=(await c10('workflow.prepare',payload,peer,key)).data;await academicHome();
                notify(result.missing?`已保存可用候选，还缺${result.missing}题；可用自己的API补充。`:'候选已准备，请继续审题。');
                if(result.draft)await wfContinue(result.draft.id);
            }
        }else if(form.id==='wf-fill'){
            const d=wfCurrentDraft,job=await api('/api/local/jobs',{mode:'k12_workflow',peer_id:peer,draft_id:d.id,route_id:d.route_id,focus:d.body.goal,count:Number(v.count)});
            closeModal();$('#workspace-content').insertAdjacentHTML('afterbegin','<p id="academic-job-state">正在补充当前草稿的缺题…</p>');academicPoll(job.id);
        }else if(form.id==='wf-patch'){
            const old=wfCurrentDraft.body.questions.find(q=>q.id===form.dataset.qid);
            const q={...old,...Object.fromEntries(['type','skill','material','prompt','evidence','explanation'].map(k=>[k,v[k]])),options:academicLines(v.options),key:academicLines(v.key),points:Number(v.points),traps:Object.fromEntries(academicLines(v.traps).map(line=>{const i=line.search(/[:：]/);if(i<0)throw Error('错项类型请用 B:张冠李戴 这样的格式。');return [line.slice(0,i).trim(),line.slice(i+1).trim()];}))};
            const result=(await c10('draft.patch',{id:wfCurrentDraft.id,expected_revision:wfCurrentDraft.revision,questions:[q]},peer,key)).data;
            closeModal();await academicHome();notify(`新版本已保存，还需审${result.review_state.pending.length}题。`);
        }else if(form.id==='wf-blueprint'){
            const sections=[...form.querySelectorAll('[data-wf-section]')].map((_,i)=>{const ids=v['ids_'+i].split(/[,，\s]+/).filter(Boolean),qs=wfCurrentDraft.body.questions.filter(q=>ids.includes(q.id));return {title:v['title_'+i],types:[...new Set(qs.map(q=>q.type))],question_ids:ids,count:ids.length,points:qs.reduce((a,q)=>a+q.points,0),minutes:Number(v['minutes_'+i])};});
            await c10('blueprint.save',{id:wfCurrentDraft.id,expected_revision:wfCurrentDraft.revision,template:v.template,sections},peer,key);closeModal();notify('蓝图已保存，布置后学生可查看并计时。');
        }else if(form.id==='wf-export'){
            await c10('bank.export',{id:wfCurrentDraft.id,expected_revision:wfCurrentDraft.revision,personal_content_checked:true,reuse_source:v.reuse_source},peer,key);closeModal();notify('已加入教师本机题库；其他学生组题时仍需核对范围与审题。');
        }else if(form.id==='wf-curriculum'){
            const payload=v.import_json?.trim()?JSON.parse(v.import_json):{title:v.title,source:v.source,units:[{unit:v.unit,order:Number(v.order),words:academicLines(v.words),phrases:academicLines(v.phrases),grammar:academicLines(v.grammar),complete:form.elements.complete.checked}]};
            const record=(await c10(v.extract_text?.trim()?'curriculum.extract':'curriculum.preview',v.extract_text?.trim()?{title:v.title,source:v.source,text:v.extract_text}:payload,null,key)).data.record;
            academicDialog('核对教材目录',`<h3>${h(record.title)}</h3><p>${h(record.source)}</p>${record.unparsed_lines?.length?`<aside class="academic-note">有${record.unparsed_lines.length}行待核对：${record.unparsed_lines.map(x=>`<p>第${x.line}行：${h(x.text)}</p>`).join('')}</aside>`:''}${record.units.map(u=>`<details open><summary>${h(u.unit)} · ${u.words.length}词</summary><p>词表：${h(u.words.join('、'))}</p><p>短语：${h(u.phrases.join('、'))}</p><p>语法与操作：${h(u.grammar.join('、'))}</p><p>${u.complete?'声明单元范围完整':'范围仍可能不完整'}</p></details>`).join('')}<label class="checkline"><input id="wf-book-confirm" type="checkbox">我已核对词表、单元顺序和来源。</label><button type="button" class="btn accent" data-action="wf-curriculum-commit" data-id="${h(record.id)}" data-revision="${record.revision}" data-hash="${h(record.content_hash)}">确认保存目录</button>`);
        }else if(form.classList.contains('wf-book-apply')){
            await c10('curriculum.apply',{route_id:academicRoute.id,catalog_id:form.dataset.id,catalog_revision:Number(form.dataset.revision),unit_orders:fields.getAll('orders').map(Number)},peer,key);closeModal();await academicHome();notify('所选单元已应用到当前学生路线。');
        }else if(form.id==='wf-lexical'){
            const check=(await c10('lexical.check',{route_id:academicRoute.id,scope_ids:fields.getAll('scope_ids'),text:v.text,exemptions:academicLines(v.exemptions),proper_names:academicLines(v.proper_names)},peer,key)).data.check;
            $('#wf-lexical-result').innerHTML=`<section class="card"><h3>待查词：${h(check.unmatched_words.join('、')||'本次未发现')}</h3><p>${check.reliable_scope_declared?'所选范围已声明完整并经教师核对':'词表范围不完整，先作为核对提示'}</p>${check.matches.filter(x=>x.match!=='exact').map(x=>`<p>${h(x.token)} → ${h(x.lemma||'')} · ${h(({irregular_inflection:'不规则词形',regular_inflection:'规则词形',explicit_exemption:'明确豁免',declared_proper_name:'已登记专名',chinese_annotation:'附中文词注'})[x.match])}</p>`).join('')}</section>`;
        }else if(form.id==='wf-forecast'){
            await c10('prep.forecast',{route_id:academicRoute.id,scope_ids:fields.getAll('scope_ids'),skills:academicLines(v.skills),count_per_skill:Number(v.count),due_date:v.due_date},peer,key);closeModal();academicTab='report';await academicHome();
        }else if(form.id==='wf-prep-state'){
            await c10('prep.state',{id:form.dataset.id,expected_revision:Number(form.dataset.revision),state:v.state},peer,key);closeModal();await academicHome();
        }else if(form.id==='wf-goal'){
            await c10('goal.save',{title:v.title,outcomes:academicLines(v.outcomes),threshold:Number(v.threshold)},peer,key);closeModal();await academicHome();
        }else if(form.id==='wf-bind'){
            const selected=form.elements.goal.selectedOptions[0];
            const outcomes=Object.fromEntries(JSON.parse(selected.dataset.outcomes).map((label,i)=>[label,v['outcome_'+i].split(/[,，\s]+/).filter(Boolean)]));
            await c10('goal.bind',{id:wfCurrentDraft.id,expected_revision:wfCurrentDraft.revision,goal_id:v.goal,goal_revision:Number(selected.dataset.revision),outcomes,coverage_note:v.coverage_note,human_review_confirmed:true},peer,key);closeModal();notify('施测前目标已关联，接下来用“目标测验”布置。');
        }else if(form.id==='wf-weekly'){
            await c10('report.weekly_plan',{route_id:academicRoute.id,start_date:v.start_date,session_minutes:Number(v.minutes)},peer,key);closeModal();await workspaceRender('paths');
        }else if(form.id==='wf-class-map'){
            const selected=form.elements.draft.selectedOptions[0];
            const mappings=[...form.querySelectorAll('[data-wf-member]')].map((f,i)=>({peer_id:f.dataset.wfMember,route_id:v['route_'+i],scope_ids:fields.getAll('scope_'+i)}));
            const result=(await c10('class.assign',{id:form.dataset.id,expected_revision:Number(form.dataset.revision),source_draft_id:v.draft,source_revision:Number(selected.dataset.revision),mappings,human_review_confirmed:true},null,key)).data;
            closeModal();await academicHome();notify(result.partial?'部分成员需核对范围，可在批次状态里重试。':'已为冻结名单中的全部学生布置。');
        }else if(form.id==='wf-withdraw'){
            await c10('publication.withdraw',{task_id:form.dataset.id,replacement_task_id:v.replacement||null,reason:v.reason,human_review_confirmed:true},peer,key);closeModal();await openTask(form.dataset.id);notify('已撤回，等待签名更新同步；原答保留。');
        }
    }catch(error){delete form.dataset.request;notify(error.message,true);}finally{button.disabled=false;}
});
