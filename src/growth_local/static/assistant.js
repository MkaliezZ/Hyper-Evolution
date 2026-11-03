"use strict";
let assistantIntent='prepare',growthContext=null,growthEdit=null,growthBusy=false,growthTaskGoal=null;
const assistantPrompts={coach:[
 ['下一步练什么','请结合这位学生在当前学科已提交的作品、教师反馈和投石问路梳理，整理已有表现、还需了解的问题，以及最合适的下一步学习行动。请引用具体任务，不足之处列成可追问的问题。'],
 ['准备下次课','请根据近期作品和反馈，为我整理下次课的关注重点：先看什么、问什么、安排什么活动，以及课后看什么表现。'],
 ['反馈是否用上了','请比较能看到的原答、教师反馈与后续提交，整理学生已经回应的建议，以及我下次可以继续追问的地方。']],
 draft:[['练一个重点','请按这位学生的考试路线，围绕近期作品中的一个具体困难生成5题原创微练习，提供答案、原文依据和解析，供我先审校。'],
 ['换材料再试','请换一个情境和材料，围绕本次已经练过的目标生成5题原创复测草稿，避免重复原题和答案线索。']]};
const assistantPreviousPage=agentPage;
function assistantSteps(steps){return `<ol class="assistant-steps">${steps.map(x=>`<li>${h(x)}</li>`).join('')}</ol>`;}
function assistantPeerField(){return `<label class="field growth-pair">这次帮助哪位学生<select id="workspace-agent-peer"><option value="">请选择已配对学生</option>${status.peers.filter(p=>p.role==='student'&&p.state==='active').map(p=>`<option value="${h(p.id)}" ${p.id===selectedPeer?'selected':''}>${h(p.name)}</option>`).join('')}</select></label>`;}
agentPage=function(){
 if(!workspaceTeacher()){
  assistantPreviousPage();
  $('#agent-form')?.insertAdjacentHTML('beforebegin','<section class="assistant-intro assistant-plan-link"><div><strong>还没想好接下来学什么？</strong><p class="small muted">先用投石问路梳理现状、目标和下一步，再让助手帮你学习。</p></div><button class="btn ghost" data-action="ws-route" data-route="planning">打开投石问路</button></section>');return;
 }
 view='agent';const flow=AssistantState.flow(assistantIntent,subjectCurrent(),academicContext?.selection.track);
 const rows=workspaceRows.filter(t=>t._peer===selectedPeer),submitted=rows.filter(t=>t.attempts?.length&&t.subject_context?.track!=='k12'&&!t.pack.academic).length;
 const reason=flow.mode?AssistantState.ready(flow.mode,status.model.configured,selectedPeer,submitted):'';
 const examples=assistantPrompts[flow.mode]||[];
 const common=`<span class="eyebrow">TEACHING ASSISTANT / ${h(subjectLabel(subjectCurrent()))}</span><h1>今天，想让助手帮你做什么？</h1><p class="muted">先选一件事，下面会告诉你需要准备什么、接下来怎么做。</p>
 <section class="assistant-intro"><div><strong>先看清成长方向，再安排这次学习。</strong><p class="small muted">投石问路：现状 → 方向 → 目标要求 → 下一步行动。</p></div><button class="btn ghost" data-action="ws-route" data-route="planning">先做投石问路 →</button></section>
 <div class="assistant-intents" role="group" aria-label="老师想做的事">${AssistantState.intents.map(i=>`<button class="assistant-intent" data-action="assistant-intent" data-intent="${i.id}" aria-pressed="${assistantIntent===i.id}"><strong>${i.title}</strong><span>${i.detail}</span></button>`).join('')}</div>`;
 const form=flow.mode?`${assistantPeerField()}<p class="small muted">${flow.mode==='coach'?`本学科已有 ${submitted} 项已提交任务；助手读取近期作品、可见反馈与成长梳理。`:'读取所选学生的考试路线和近期学习记录，准备5题原创草稿。'}</p>
 <form id="agent-form" class="local-form"><input type="hidden" name="mode" value="${flow.mode}"><label class="field" for="agent-prompt">你想重点看看什么？</label><div class="assistant-examples" role="group" aria-label="可直接使用的提问示例">${examples.map(([name],i)=>`<button type="button" data-action="assistant-example" data-mode="${flow.mode}" data-example="${i}">${h(name)}</button>`).join('')}</div><textarea id="agent-prompt" name="prompt" maxlength="2000" required>${h(examples[0]?.[1]||'')}</textarea>
 ${reason?`<p class="assistant-state" role="status">${h(reason)} ${!status.model.configured?'<button type="button" class="btn text small" data-action="ws-route" data-route="settings">配置API →</button>':''}${!selectedPeer?'<button type="button" class="btn text small" data-action="ws-route" data-route="connections">去配对学生 →</button>':''}${flow.mode==='coach'&&selectedPeer&&!submitted?'<button type="button" class="btn text small" data-action="ws-route" data-route="assign">先布置一次任务 →</button>':''}</p>`:`<p class="small muted">本次使用你配置的 ${h(status.model.model)}，点击后开始模型调用。</p>`}<button class="btn accent" type="submit" ${reason?'disabled':''}>${h(flow.label)}</button></form>`:
 `${['k12','review'].includes(flow.route)?assistantPeerField():''}<button class="btn accent" data-action="assistant-go" data-route="${flow.route}">${h(flow.label)} →</button><p class="small muted">${assistantIntent==='review'?'先选一份学生已提交的作品，再在评阅页生成AI预审；修改确认后发送。':flow.route==='k12'?'按学习路线选择实际范围，备题、审题和布置在同一条教学流程里完成。':'打开资料后可以先提问梳理内容，再选择方法、目标和完成标准来设计任务。'}</p>`;
 shell(common+`<section class="card" aria-label="当前任务的使用步骤"><h2>${h(AssistantState.intents.find(x=>x.id===assistantIntent).title)}</h2>${assistantSteps(flow.steps)}${form}</section>
 <details class="card assistant-help"><summary>第一次用，照这个例子走一遍</summary><p>例如准备一节数学资料课：先在投石问路里记下“想用实际例子解释比例关系”这个目标；再选“根据资料备课”，打开本学科资料，点击“问一问所选原文”或“用这段资料学习”。学生交回作品后，用“预审学生作业”准备反馈，再看下一次需要练什么。</p><p>还没有作品时，可以先备课和设计任务。收到提交后，再用“看学生情况”分析近期表现。</p></details><div id="agent-result"></div>`);
};

const g9=(operation,payload={},request_id=uid())=>api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v9',operation:'planning.'+operation,peer_id:workspaceTeacher()?selectedPeer:null,payload,request_id});
const growthStages={exploring:'探索方向',preparing:'积累准备',acting:'行动实践',reviewing:'复盘调整'};
const growthBlank=()=>({current_situation:'',stage:'exploring',question:'',strengths:'',directions:'',goal:'',horizon:'',requirements:[]});
const growthOwn=p=>p.owner_device===status.device_id;
function growthFacts(content){return `<dl>${[['目前在做什么',content.current_situation],['目前阶段',growthStages[content.stage]],['最想弄清的问题',content.question],['已有准备与优势',content.strengths],['正在考虑的方向',content.directions],['下一目标',content.goal||'还在探索方向'],['时间安排',content.horizon]].filter(([,v])=>v).map(([k,v])=>`<div class="growth-fact"><dt>${h(k)}</dt><dd>${h(v)}</dd></div>`).join('')}</dl>`;}
function growthCard(plan){return `<article class="growth-plan"><p class="growth-origin">${growthOwn(plan)?'本机保存':plan.author_role==='teacher'?'老师分享的建议':'学生分享的梳理'} · 第${plan.revision}版${plan.signature_verified?' · 已核验配对签名':''}</p><h3>${h(plan.content.goal||'成长方向梳理')}</h3>${growthFacts(plan.content)}${plan.content.requirements.map((r,i)=>`<div class="growth-action"><h4>${i+1}. ${h(r.requirement)}</h4><p class="small">已有准备：${h(r.current_evidence||'待补充')}<br>主要差距：${h(r.gap||'待讨论')}<br>下一步：${h(r.next_action||'待选择')}<br>完成标准：${h(r.completion_standard||'待填写')}</p>${r.source_url?`<p class="small">来源链接：<a target="_blank" rel="noopener noreferrer" href="${h(r.source_url)}">打开填写的参考来源</a></p>`:''}</div>`).join('')}<div class="actions"><button class="btn ghost small" data-action="growth-edit" data-id="${plan.id}">${growthOwn(plan)?'继续修改':'以此为起点，另存我的版本'}</button>${growthOwn(plan)?`<button class="btn ghost small" data-action="growth-share" data-id="${plan.id}">${workspaceTeacher()?'分享建议给这位学生':'选择老师并分享'}</button>`:''}<button class="btn accent small" data-action="growth-learn" data-id="${plan.id}">把行动带入学习任务 →</button></div></article>`;}
function growthRequirement(i,r={}){return `<fieldset class="growth-requirement" data-growth-requirement><legend>目标要求 ${i+1}</legend><div class="growth-form-grid">${[['requirement','对方或目标要求什么','例如：能用证据说明一个观点'],['current_evidence','目前已有的准备或作品','写已经做过的事，或关联下方作品'],['gap','还差什么','例如：例子和观点的关系需要再说清楚'],['next_action','下一步做什么','写一个具体、做得完的动作'],['completion_standard','做到什么样就可以进入下一步','例如：用新材料写一段说明，并请老师反馈'],['source_url','要求来源链接（选填）','https://…']].map(([k,label,placeholder])=>`<label class="field">${label}<${k==='source_url'?'input':'textarea'} ${k==='source_url'?'class="input" type="url"':''} name="req_${i}_${k}" maxlength="${k==='source_url'?2000:k==='requirement'||k==='gap'?500:1000}" placeholder="${placeholder}" ${k==='source_url'?`value="${h(r[k]||'')}"`:''}>${k==='source_url'?'':h(r[k]||'')+'</textarea>'}</label>`).join('')}</div><button class="btn text small" type="button" data-action="growth-remove-row">移除这一项</button></fieldset>`;}
workspacePlanning=async function(){
 await workspaceLoad();view='planning';growthEdit=null;
 const head=`<span class="eyebrow">投石问路 / ${h(subjectLabel(subjectCurrent()))}</span><h1>先看清现在，再决定下一步。</h1><p class="muted">把当前状态、想去的方向、已有准备和具体行动放在同一张成长梳理卡里。</p>`;
 if(workspaceTeacher()&&!selectedPeer){shell(head+workspaceEmpty('先连接一位学生','配对后可以查看他分享的梳理，也能为他保存自己的方向建议。')+'<button class="btn accent" data-action="ws-route" data-route="connections">去师生配对</button>');return;}
 growthContext=(await g9('context')).data;
 shell(head+`${workspaceTeacher()?`<label class="field growth-pair">这次梳理哪位学生<select id="growth-peer">${status.peers.filter(p=>p.role==='student'&&p.state==='active').map(p=>`<option value="${h(p.id)}" ${p.id===selectedPeer?'selected':''}>${h(p.name)}</option>`).join('')}</select></label>`:''}
 <div class="growth-counts" aria-label="本学科近期学习记录"><span><b>${growthContext.state_counts.tasks}</b>近期任务</span><span><b>${growthContext.state_counts.submitted}</b>已提交作品的任务</span><span><b>${growthContext.state_counts.with_teacher_feedback}</b>已有教师反馈的任务</span></div><p class="small muted">以上来自本学科最多10项近期可见任务。成长阶段和方向在下方结合本人想法、具体作品一起梳理。</p>
 <div class="growth-step-nav" role="group" aria-label="投石问路四个环节">${['收资 · 看清现状','投石 · 探索方向','问路 · 拆成行动','展示 · 回看梳理'].map((label,i)=>`<button class="btn ghost" data-action="growth-step" data-step="${i}">${i+1}. ${label}</button>`).join('')}</div>
 <div id="growth-editor"></div><section class="card growth-step" id="growth-step-3"><div class="section-head"><h2>展示 · 成长梳理卡</h2><button class="btn ghost small" data-action="growth-new">新建另一份梳理</button></div><p class="small muted">自己的版本可继续修改；收到的版本保留原作者，分享由你单独确认。</p><div id="growth-plans">${growthContext.plans.map(growthCard).join('')||'<p class="muted">完成上面的梳理并保存，成长卡会显示在这里。</p>'}</div></section>
 <details class="card assistant-help"><summary>投石问路可以怎样用？</summary><p>收资先把目前在做的事、已有作品和最想弄清的问题写出来；投石比较想走的方向；问路把一个目标拆成要求、准备和行动；展示把这些整理成可以继续讨论的成长卡。</p><p>例如：想参加一次英文研讨，先看看已有阅读、邮件和表达作品，再写清需要准备的内容，挑一个最近能完成的动作。当前页面支持梳理与师生建议交换，机会搜索、资格和截止日期核查由后续专用能力接入。</p></details>`);
 const own=growthContext.plans.find(growthOwn);growthRenderEditor(own||null);growthShowStep(growthContext.plans.length?3:0);
};
function growthRenderEditor(plan,copy=false){
 growthEdit=copy?null:plan;const c=plan?plan.content:growthBlank(),refs=copy?[]:plan?.evidence_refs?.map(x=>x.task_id)||[];
 $('#growth-editor').innerHTML=`<form id="growth-form" class="local-form"><section class="card growth-step" id="growth-step-0"><h2>收资 · 先把现状说清楚</h2><p class="small muted">${workspaceTeacher()?'这是老师在本机填写的建议版本；学生分享的原版会单独保留。':'从自己最在意的问题开始。没想好方向，也可以先保存现状。'}</p>
 <label class="field">目前在做什么、处在什么节点？<textarea name="current_situation" maxlength="2000" required placeholder="例如：正在准备行前英语；阅读能理解大意，导师交流和表达还想多练。">${h(c.current_situation)}</textarea></label><div class="growth-form-grid"><label class="field">目前更接近哪个阶段？<select name="stage">${Object.entries(growthStages).map(([id,label])=>`<option value="${id}" ${c.stage===id?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">最近最想弄清的问题<input class="input" name="question" maxlength="1000" value="${h(c.question)}" placeholder="例如：我应该先加强哪种表达能力？"></label></div>
 <label class="field">已经有的准备、兴趣和优势<textarea name="strengths" maxlength="2000" placeholder="写已经做过的事、现有作品和愿意投入的方向。">${h(c.strengths)}</textarea></label><details><summary>关联已有作品，作为本次讨论的依据</summary><div class="growth-choices">${growthContext.tasks.map(t=>`<label><input type="checkbox" name="task_id" value="${h(t.id)}" ${refs.includes(t.id)?'checked':''} ${t.attempts?'':'disabled'}>${h(t.title)} · ${t.attempts?'已有提交':'尚未提交'}</label>`).join('')||'<p>目前还没有本学科作品，可以先写现状和目标。</p>'}</div></details></section>
 <section class="card growth-step" id="growth-step-1"><h2>投石 · 想往哪里走？</h2><label class="field">正在考虑的方向，以及为什么想试<textarea name="directions" maxlength="2000" placeholder="可以写两三个方向，再比较自己为什么感兴趣、已有准备和需要投入什么。">${h(c.directions)}</textarea></label><div class="growth-form-grid"><label class="field">选一个接下来想达到的目标<input class="input" name="goal" maxlength="1000" value="${h(c.goal)}" placeholder="例如：完成一次10分钟英文项目介绍；还在探索时可先留空。"></label><label class="field">希望什么时候、用多少时间推进？<input class="input" name="horizon" maxlength="160" value="${h(c.horizon)}" placeholder="例如：未来两周，每周两次。"></label></div></section>
 <section class="card growth-step" id="growth-step-2"><h2>问路 · 把目标拆成可做的下一步</h2><p class="small muted">已有准备、还差什么和计划去做的事分开写。每份最多6项，先填最重要的一项就可以。</p><div id="growth-requirements">${(c.requirements.length?c.requirements:[{}]).map((r,i)=>growthRequirement(i,r)).join('')}</div><button class="btn ghost" type="button" data-action="growth-add-row">＋ 再拆一项要求</button></section>
 <div class="actions"><button class="btn accent" type="submit">保存本机，生成成长梳理卡</button><span class="small muted">${growthEdit?'第'+growthEdit.revision+'版继续修改，历史版本保留':'先保存到本机，之后可再选择分享'}</span></div></form>`;
 $('#growth-form').noValidate=true;
 for(const i of [0,1])$('#growth-step-'+i).insertAdjacentHTML('beforeend',`<button type="button" class="btn ghost" data-action="growth-step" data-step="${i+1}">下一步：${i===0?'探索方向':'拆成行动'} →</button>`);
 growthShowStep(0);
}
function growthShowStep(n){
 if(![0,1,2,3].includes(n))return;
 for(let i=0;i<4;i++){const box=$('#growth-step-'+i);if(box)box.hidden=i!==n;}
 const save=$('#growth-form > .actions');if(save)save.hidden=n===3;
 document.querySelectorAll('.growth-step-nav [data-step]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.step)===n)));
 $('#growth-step-'+n)?.scrollIntoView({behavior:'smooth',block:'start'});
}
function growthPayload(form){
 const d=Object.fromEntries(new FormData(form)),requirements=[];
 form.querySelectorAll('[data-growth-requirement]').forEach(row=>{
  const values={};row.querySelectorAll('input,textarea').forEach(el=>values[el.name.split('_').slice(2).join('_')]=el.value.trim());
  if(Object.values(values).some(Boolean)){
   if(!values.requirement){growthShowStep(2);throw Error('请给这项行动补上“目标要求什么”。');}
   if(values.source_url&&!/^https?:\/\//.test(values.source_url)){growthShowStep(2);throw Error('来源链接请填写http或https地址。');}
   requirements.push(values);
  }
 });
 const content={};for(const key of ['current_situation','stage','question','strengths','directions','goal','horizon'])content[key]=d[key]||'';content.requirements=requirements;
 if(!content.current_situation.trim()){growthShowStep(0);throw Error('先用一句话写下目前在做什么，再保存这份梳理。');}
 return {id:growthEdit?.id||null,expected_revision:growthEdit?.revision||0,content,task_ids:new FormData(form).getAll('task_id')};
}
function growthFind(id){const p=growthContext?.plans.find(x=>x.id===id);if(!p)throw Error('请重新打开投石问路，读取最新记录。');return p;}
const growthPreviousPractice=studyPractice;
function growthPrefillTask(form,details){
 if(AssistantState.applyGoal(form,details,growthTaskGoal,subjectCurrent(),workspaceTeacher()?selectedPeer:null))
  form.insertAdjacentHTML('afterbegin','<p class="assistant-state">已带入投石问路的目标和行动，你可以调整方法、问题与完成标准。</p>');
}
studyPractice=function(){growthPreviousPractice();growthPrefillTask($('#study-activity-form'),$('#study-design-details'));};
const growthPreviousDesign=c3Design;
c3Design=async function(source){await growthPreviousDesign(source);growthPrefillTask($('#continuity-design-form'),$('#continuity-design-detail'));};
const growthPreviousLibrary=studyHome;
studyHome=async function(){await growthPreviousLibrary();if(growthTaskGoal&&growthTaskGoal.subject===subjectCurrent()&&growthTaskGoal.peer===(workspaceTeacher()?selectedPeer:null)&&view==='materials')$('#subject-material-library')?.insertAdjacentHTML('beforebegin',`<div class="assistant-intro"><p>本次目标：${h(growthTaskGoal.goal)}。请选择资料，打开后点击“用这段资料学习”。</p><button class="btn text small" data-action="growth-clear-task">取消本次衔接</button></div>`);};
jobHistory=async function(){
 const {jobs}=await api('/api/local/jobs');if(view!=='agent')return;
 const names={coach:'学生情况与下一步',draft:'留学英语原创草稿',reading:'资料解释',vision:'原图解释',writing:'写作建议',prereview:'作业AI预审',k12_workflow:'K12题库优先备题与续做',k12_generate:'K12备题',k12_review:'K12独立审题'};
 const routes={writing:'writing',prereview:'review',k12_workflow:'k12',k12_generate:'k12',k12_review:'k12'};
 $('#agent-result').innerHTML=`<section class="card"><h2>本机助手任务记录</h2>${jobs.map(j=>{const route=routes[j.mode],title=(names[j.mode]||'学习任务')+' · '+(({completed:'已完成',failed:'未完成',running:'处理中',queued:'排队中'})[j.status]||j.status);return `<p>${route?`<button class="btn text" data-action="ws-route" data-route="${route}" ${workspaceAllowed(route)?'':'disabled'}>${h(title)} · 到对应页面查看</button>`:`<button class="btn text" data-action="open-job" data-id="${h(j.id)}">${h(title)}</button>`}<span class="small muted"> ${h(j.created)}</span></p>`;}).join('')||'<p class="muted">先从上面选一件事。需要模型的任务完成后，可以在这里重新查看。</p>'}</section>`;
};
document.addEventListener('click',async event=>{
 const b=event.target.closest('[data-action]');if(!b)return;const a=b.dataset.action;if(!a.startsWith('assistant-')&&!a.startsWith('growth-'))return;
 event.preventDefault();if(growthBusy)return notify('正在保存，请稍候。');
 if(['growth-add-row','growth-remove-row'].includes(a)&&$('#growth-form'))delete $('#growth-form').dataset.request;
 try{
  if(a==='assistant-intent'){assistantIntent=b.dataset.intent;agentPage();await jobHistory();}
  else if(a==='assistant-example'){$('#agent-prompt').value=assistantPrompts[b.dataset.mode][Number(b.dataset.example)][1];$('#agent-prompt').focus();}
  else if(a==='assistant-go'){await workspaceNavigate(b.dataset.route,b.dataset.route==='review'?{filter:'review'}:{});if(b.dataset.route==='review'&&selectedPeer){$('#workspace-student-filter').value=selectedPeer;workspaceRenderTasks();}}
  else if(a==='growth-step')growthShowStep(Number(b.dataset.step));
  else if(a==='growth-new'){growthRenderEditor(null);$('#growth-step-0').scrollIntoView({behavior:'smooth'});}
  else if(a==='growth-edit'){const p=(await g9('read',{id:b.dataset.id})).data.plan;growthRenderEditor(p,!growthOwn(p));$('#growth-step-0').scrollIntoView({behavior:'smooth'});}
  else if(a==='growth-add-row'){const box=$('#growth-requirements'),n=box.children.length;if(n>=6)throw Error('这份梳理最多6项，先挑最重要的。');box.insertAdjacentHTML('beforeend',growthRequirement(n));}
  else if(a==='growth-remove-row'){b.closest('[data-growth-requirement]').remove();$('#growth-requirements').querySelectorAll('[data-growth-requirement]').forEach((row,i)=>{row.querySelector('legend').textContent='目标要求 '+(i+1);row.querySelectorAll('input,textarea').forEach(el=>el.name=el.name.replace(/^req_\d+_/,'req_'+i+'_'));});}
  else if(a==='growth-share'){
   const p=(await g9('read',{id:b.dataset.id})).data.plan,peers=status.peers.filter(x=>x.state==='active'&&x.role==='teacher');
   modal('检查后，再分享这份成长梳理',`${growthFacts(p.content)}<p class="small muted">同时分享本卡中的要求、行动、来源链接和已关联作品的版本引用；其他资料和私有备注不随卡发送。</p><form id="growth-share-form" data-id="${p.id}" data-revision="${p.revision}" data-hash="${p.content_hash}">${workspaceTeacher()?'<p>接收人：'+h(status.peers.find(x=>x.id===selectedPeer)?.name)+'</p>':`<label class="field">分享给哪位老师<select name="receiver_id" required><option value="">请选择</option>${peers.map(x=>`<option value="${x.id}">${h(x.name)}</option>`).join('')}</select></label>`}<label class="checkline"><input name="confirmed" type="checkbox" required>我已查看这份规划，选择分享给这位配对老师 / 学生</label><button class="btn accent" type="submit">确认分享这份版本</button></form>`);
   $('#growth-share-form').insertAdjacentHTML('beforebegin',p.content.requirements.map((r,i)=>`<div class="growth-action"><strong>${i+1}. ${h(r.requirement)}</strong><p class="small">已有准备：${h(r.current_evidence)}<br>主要差距：${h(r.gap)}<br>下一步：${h(r.next_action)}<br>完成标准：${h(r.completion_standard)}${r.source_url?'<br>参考来源：'+h(r.source_url):''}</p></div>`).join(''));
  }else if(a==='growth-learn'){
   const p=growthFind(b.dataset.id),r=p.content.requirements.find(x=>x.next_action)||{};
   if(!p.content.goal&&!r.next_action)throw Error('先写一个目标或下一步行动，再带入学习任务。');
   growthTaskGoal={subject:subjectCurrent(),peer:workspaceTeacher()?selectedPeer:null,goal:p.content.goal||r.next_action,action:r.next_action||'',criteria:r.completion_standard||''};await workspaceNavigate('materials');
  }else if(a==='growth-clear-task'){growthTaskGoal=null;await studyHome();}
 }catch(error){notify(error.message,true);}
});
document.addEventListener('change',async event=>{
 try{if(event.target.id==='workspace-agent-peer'&&view==='agent'&&workspaceTeacher()){selectedPeer=event.target.value;agentPage();await jobHistory();}
 else if(event.target.id==='growth-peer'){selectedPeer=event.target.value;await workspacePlanning();}}
 catch(error){notify(error.message,true);}
});
document.addEventListener('submit',async event=>{
 const f=event.target;if(!['growth-form','growth-share-form'].includes(f.id))return;
 event.preventDefault();event.stopImmediatePropagation();if(growthBusy)return;growthBusy=true;studyBusy=true;
 const b=f.querySelector('button[type=submit]');b.disabled=true;
 try{
  f.dataset.request||=uid();
  if(f.id==='growth-form'){
   const result=(await g9('save',growthPayload(f),f.dataset.request)).data;
   await workspacePlanning();notify('成长梳理已保存。需要分享时，再选接收人。');
   $('#growth-step-3').scrollIntoView({behavior:'smooth'});
   if(result.policy.missing.length)$('#growth-plans').insertAdjacentHTML('afterbegin',`<p class="assistant-state">下次可以接着补：${result.policy.missing.map(h).join('；')}。</p>`);
  }else{
   if(!f.elements.confirmed.checked)throw Error('请先查看本次分享内容并确认。');
   await g9('share',{id:f.dataset.id,expected_revision:Number(f.dataset.revision),content_hash:f.dataset.hash,receiver_id:f.elements.receiver_id?.value||null},f.dataset.request);
   closeModal();notify('已加入发送队列，双方在线时送达。');
  }
 }catch(error){notify(error.message,true);}finally{growthBusy=false;studyBusy=false;if(b.isConnected)b.disabled=false;}
},true);
document.addEventListener('input',event=>{const f=event.target.closest('#growth-form,#growth-share-form');if(f)delete f.dataset.request;});
document.addEventListener('click',event=>{
 if(event.target.closest('[data-action="goal"]')){
  event.preventDefault();event.stopImmediatePropagation();workspaceNavigate('planning').catch(error=>notify(error.message,true));
 }
},true);
