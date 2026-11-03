"use strict";
// Role-specific presentation of existing capabilities; no duplicated authorization.
let workspaceRows=[], workspacePeople=[], workspacePacks=[], workspaceReturn='tasks';
let workspaceFilter='all', workspaceQuery='', workspaceFeatureRows=[];
let workspaceEpoch=0;
const workspaceTeacher=()=>status?.profile?.role==='teacher';
const workspaceRoutes=['home','tasks','practice','feedback','planning','students','assign','review','materials','resources','agent','connections','settings','guide','features','policy','memory','reviews','retrieval','policy-lab','paths','writing','methods'];
function workspaceAllowed(route){
    if((workspaceTeacher()?['tasks','practice','feedback','reviews']:['students','assign','review','resources','methods']).includes(route))return false;
    const subject=academicContext?.selection.subject;
    if(subject==='legacy')return ['academic','home','tasks','students','review','materials','settings','guide','features','connections'].includes(route);
    return !(subject&&subject!=='english'&&['k12','practice','resources'].includes(route));
}
function workspaceNavigation(){
    const teacher=workspaceTeacher(), section=WorkspaceState.activeRoute(view,workspaceReturn);
    const groups=[['日常使用',teacher?[['home','教学首页'],['planning','投石问路 · 成长与目标'],['students','学生档案'],['assign','布置任务'],['review','作业与评阅']]:[['home','学习首页'],['tasks','我的任务'],['feedback','反馈与修订'],['planning','投石问路 · 成长与目标']]],['资料与学习',[['materials','我的资料库'],['retrieval','资料检索与对照'],['agent','学习助手'],['paths','学习安排'],['writing','写作与修订'],['memory','学习札记'],...(!teacher?[['reviews','我的复习']]:[]) ]],['教学方法',[['policy','学习设计与规则'],...(teacher?[['methods','方法资产与审阅']]:[])]],['连接与帮助',[['connections',teacher?'师生配对':'我的老师'],['settings','模型与本机设置'],['guide','使用指南'],['features','功能清单']]]];
    return `<aside class="workspace-sidebar"><button class="workspace-menu-toggle" data-action="ws-menu" aria-expanded="false" aria-controls="workspace-navigation">打开导航菜单</button><nav aria-label="本机导航" id="workspace-navigation">${groups.map(([title,items])=>[title,items.filter(([route])=>workspaceAllowed(route))]).filter(([,items])=>items.length).map(([title,items])=>`<div class="workspace-nav-group"><p>${title}</p>${items.map(([route,label])=>`<button data-action="ws-route" data-route="${route}" class="${section===route?'active':''}" ${section===route?'aria-current="page"':''}>${label}</button>`).join('')}</div>`).join('')}</nav><div class="workspace-device"><strong>保存在这台电脑</strong><small>${status.model?.configured?'已连接自己的模型':'模型 API 尚未配置'}</small><button data-action="ws-route" data-route="settings">${status.model?.configured?'管理模型与备份':'配置自己的 API →'}</button></div></aside>`;
}
function workspaceHeading(kicker,title,description,action=''){
    return `<div class="local-top"><div><span class="eyebrow">${kicker}</span><h1>${h(title)}</h1><p class="muted">${description}</p></div>${action}</div>`;
}
function workspaceCard(title,description,action,attributes='',tag=''){
    return `<button class="workspace-action-card" data-action="${action}" ${attributes}>${tag?`<span class="workspace-card-tag">${tag}</span>`:''}<strong>${title}</strong><span>${description}</span><b aria-hidden="true">→</b></button>`;
}
function workspaceRouteCard(title,description,route,tag=''){return workspaceCard(title,description,'ws-route',`data-route="${route}"`,tag);}
function workspaceEmpty(title,description,button=''){
    return `<div class="workspace-empty"><h3>${title}</h3><p class="muted">${description}</p>${button}</div>`;
}
function workspaceTaskRow(t){
    const s=WorkspaceState.taskState(t,status.profile.role);
    return `<article class="local-task workspace-task" data-task-id="${h(t.id)}"><div><div class="workspace-task-meta"><span class="status-pill ${s.key==='revision'||s.key==='review'?'attention':''}">${s.label}</span><span>${h(labels[t.purpose]||'学习任务')}</span>${workspaceTeacher()?`<span>${h(t._studentName||'')}</span>`:`<span>${t.origin==='teacher'?h(t.teacher_name||'老师布置'):'本机自主学习'}</span>`}</div><h3>${h(t.pack.title)}</h3><p class="small muted">${h(t.attempts?.at(-1)?.evaluation?.next_step||t.pack.companion_plan?.goal||t.pack.instructions||'打开任务查看具体要求')}</p></div><button class="btn ghost small" data-action="ws-task" data-id="${h(t.id)}" data-peer="${h(t._peer||'')}">${subjectReadOnly()?'查看历史记录':s.action} →</button></article>`;
}
async function workspaceLoad(){
    await refreshStatus();
    if(workspaceTeacher()){
        const peers=status.peers.filter(p=>p.role==='student'&&p.state==='active');
        const results=await Promise.all(peers.map(async p=>({peer:p,data:await api('/api/local/dashboard?peer_id='+encodeURIComponent(p.id))})));
        // Publish a complete projection only after every authorized read succeeds.
        workspacePeople=results;
        workspaceRows=results.flatMap(({peer,data})=>data.tasks.map(t=>({...t,_peer:peer.id,_studentName:data.person.name})));
        if(!peers.some(p=>p.id===selectedPeer))selectedPeer=peers[0]?.id||'';
        dashboard=results.find(x=>x.peer.id===selectedPeer)?.data||null;
    }else{
        dashboard=await api('/api/local/dashboard');
        workspaceRows=await Promise.all(dashboard.tasks.map(async t=>t.origin==='teacher'?{...t,...await api('/api/local/tasks/'+encodeURIComponent(t.id))}:t));
        workspacePeople=[];
    }
}
function workspaceSteps(){
    return `<section class="workspace-start"><div><strong>第一次使用？从这里走一遍。</strong><p class="small muted">${workspaceTeacher()?'连接学生 → 选择资料或题包 → 明确目标并布置 → 评阅作品 → 学生修订。':'选择本学科资料 → 完成本次任务 → 查看依据和反馈 → 修订或换材料再试。'}</p></div><button class="btn ghost small" data-action="ws-demo">体验原创资料示例</button><button class="btn text small" data-action="ws-route" data-route="guide">看使用教程 →</button></section>`;
}
async function workspaceStudentHome(){
    await workspaceLoad();view='home';
    const todo=workspaceRows.filter(t=>WorkspaceState.matches(t,'todo','','student'));
    const revisions=workspaceRows.filter(t=>WorkspaceState.taskState(t,'student').key==='revision');
    const waiting=workspaceRows.filter(t=>WorkspaceState.matches(t,'waiting','','student'));
    shell(`${workspaceHeading('TODAY / 学习首页',`${status.profile.name}，今天从哪里开始？`,'可以直接理解资料、做专项练习或完成老师的任务。选择适合这次目标的起点。')}
        <div class="workspace-metrics"><button data-action="ws-filter-route" data-route="tasks" data-filter="todo"><b>${todo.length}</b><span>待完成 / 待修订</span></button><button data-action="ws-filter-route" data-route="feedback" data-filter="revision"><b>${revisions.length}</b><span>需要修订</span></button><button data-action="ws-filter-route" data-route="tasks" data-filter="waiting"><b>${waiting.length}</b><span>待送达 / 待评阅</span></button></div>
        <section class="card workspace-priority"><div class="section-head"><h2>接着上次做</h2><button class="btn text small" data-action="ws-route" data-route="tasks">查看全部任务 →</button></div>${todo.length?todo.slice().reverse().slice(0,2).map(workspaceTaskRow).join(''):workspaceEmpty('当前没有待完成的任务','可从下面选一个小目标，不必先做整套诊断。')}</section>
        <section class="workspace-section"><h2>开始一次学习</h2><div class="workspace-action-grid">${workspaceRouteCard('读懂一段资料','课文、讲义、笔记：阅读、提问，再带着目标练习。','materials','通用伴学')}${subjectCurrent()==='english'?workspaceRouteCard('英语专项练习','诊断、补练、听力、写作、口语和新材料复测。','practice','英语 / 留学'):''}${workspaceRouteCard('看反馈，改作品','找到老师的具体建议，保留原稿继续修订。','feedback')}${workspaceRouteCard('向学习助手提问','让自己的模型结合已有学习证据，提出下一步建议。','agent','使用自己的 API')}${workspaceRouteCard('投石问路 · 成长与目标','把目标拆成要求、证据差距和可以开始的行动。','planning')}${workspaceRouteCard('连接我的老师','输入配对码，接收任务和签名反馈。','connections')}</div></section>${workspaceSteps()}`);
}
async function workspaceTeacherHome(){
    await workspaceLoad();view='home';
    const reviews=workspaceRows.filter(t=>WorkspaceState.taskState(t,'teacher').key==='review');
    const revisions=workspaceRows.filter(t=>WorkspaceState.taskState(t,'teacher').key==='revision');
    shell(`${workspaceHeading('TODAY / 教学首页','今天，先处理这几件事。','学生档案、任务和收到的作品保存在本机。先看待办，再开始备课。','<button class="btn accent" data-action="ws-route" data-route="assign">＋ 布置任务</button>')}
        <div class="workspace-metrics"><button data-action="ws-filter-route" data-route="review" data-filter="review"><b>${reviews.length}</b><span>最新作品待评阅</span></button><button data-action="ws-filter-route" data-route="review" data-filter="revision"><b>${revisions.length}</b><span>已反馈，待学生修订</span></button><button data-action="ws-route" data-route="students"><b>${workspacePeople.length}</b><span>已配对学生</span></button></div>
        <section class="card workspace-priority"><div class="section-head"><h2>待评阅作品</h2><button class="btn text small" data-action="ws-filter-route" data-route="review" data-filter="all">查看全部作业 →</button></div>${reviews.length?reviews.slice().reverse().slice(0,3).map(workspaceTaskRow).join(''):workspaceEmpty('当前没有待评阅的新作品','收到学生提交后会出现在这里。可以先准备下一次任务。')}</section>
        <section class="workspace-section"><h2>教学常用入口</h2><div class="workspace-action-grid">${workspaceRouteCard('布置一次学习','从本学科资料设计理解、专项或应用任务。','assign')}${workspaceRouteCard('查看学生档案','查看任务记录、近期错因线索和教师私有备注。','students')}${workspaceRouteCard('阅读与准备资料','保存讲义与选段，围绕原文提问，明确本次目标。','materials','通用伴学')}${subjectCurrent()==='english'?workspaceRouteCard('导入题库与试听','文字题先预览导入；音频题核对原文并完整试听。','resources'):''}${workspaceRouteCard('让助手准备建议','用自己的模型，依据所选学生的证据给建议或出草稿。','agent','使用自己的 API')}${workspaceRouteCard('邀请学生配对','发配对码，让师生各自使用自己的本机工作区。','connections')}</div></section>${workspaceSteps()}`);
}
async function workspaceTasks(route){
    await workspaceLoad();view=route;
    const teacher=workspaceTeacher(), feedback=route==='feedback';
    const title=teacher?'作业与评阅':feedback?'反馈与修订':'我的任务';
    shell(`${workspaceHeading(teacher?'TEACH / 作业':'LEARN / 任务',title,teacher?'汇总所有已配对学生的任务；待评阅按每个任务最新作品统计。':feedback?'区分教师反馈、自动核对和本人反思。查看下一步，再打开原任务修订。':'老师布置和本机自主任务放在一起；提交与送达、评阅状态分别显示。',`<button class="btn ghost" data-action="ws-refresh">刷新任务</button>`)}
        <section class="card"><div class="workspace-toolbar"><label class="workspace-search">${teacher?'搜索任务 / 学生':'搜索任务'}<input class="input" id="workspace-search" type="search" placeholder="输入任务名称${teacher?'或学生姓名':''}" value="${h(workspaceQuery)}"></label>${teacher?`<label>学生<select id="workspace-student-filter"><option value="">全部学生</option>${workspacePeople.map(({peer,data})=>`<option value="${h(peer.id)}">${h(data.person.name)}</option>`).join('')}</select></label>`:''}</div><div class="workspace-filters" role="group" aria-label="任务状态">${[['all','全部'],...(!feedback?[['todo',teacher?'未提交':'待完成'],['waiting','待送达 / 待评阅']]:[]),...(teacher?[['review','待我评阅']]:[]),['revision','需修订'],['feedback',teacher?'已有反馈':'反馈与记录'],['closed','暂停 / 归档']].filter(([id])=>!(teacher&&id==='waiting')).map(([id,label])=>`<button data-action="ws-filter" data-filter="${id}" aria-pressed="${workspaceFilter===id}" class="${workspaceFilter===id?'active':''}">${label}</button>`).join('')}</div><p id="workspace-result-count" class="small muted" aria-live="polite"></p><div id="workspace-task-list"></div></section>`);
    workspaceRenderTasks();
}
function workspaceRenderTasks(){
    const peer=$('#workspace-student-filter')?.value||'';
    const tasks=workspaceRows.filter(t=>(!peer||t._peer===peer)&&WorkspaceState.matches(t,workspaceFilter,workspaceQuery,status.profile.role));
    $('#workspace-result-count').textContent=`显示 ${tasks.length} 个任务，共 ${workspaceRows.length} 个。状态只表示本次任务进度，不代表长期掌握。`;
    $('#workspace-task-list').innerHTML=tasks.length?tasks.slice().reverse().map(workspaceTaskRow).join(''):workspaceEmpty('这里暂时没有对应的任务','可以切换状态、清空搜索，或开始一次新学习。',`<button class="btn ghost" data-action="ws-route" data-route="${workspaceTeacher()?'assign':'materials'}">${workspaceTeacher()?'去布置任务':'从资料开始'} →</button>`);
}
async function workspacePractice(){
    await workspaceLoad();view='practice';
    const descriptions={diagnostic:['阅读微诊断','用少量原创题观察当前作答，保留具体答案依据。'],practice:['按错因补练','依据最近诊断准备微练习；当前分支需先有诊断记录。'],listening:['听力练习','题目、录音、原文和答案配套使用；缺材料时说明需要补齐什么。'],writing:['写作与修订','先写自己的作品，提交后请老师反馈，再保留原稿修订。'],speaking:['口语作品','按题目录音或上传音频，请老师按实际声音评阅。'],retest:['换材料复测','用不同材料再试；当前英语分支需先完成诊断与补练。']};
    shell(`${workspaceHeading('PRACTICE / 英语专项',`${dashboard.person.exam==='ielts'?'雅思 Academic':'托福 2026'} · 选择这次要练什么`,'这里保留英语微练习。通用资料学习可以直接开始，不强制按诊断顺序走。')}
        <div class="workspace-action-grid">${Object.entries(descriptions).map(([purpose,[title,description]])=>workspaceCard(title,description,'ws-start',`data-purpose="${purpose}"`)).join('')}</div>
        <section class="card"><h2>需要按自己的情况出题？</h2><p>用你的模型结合已有作答和考试蓝图准备原创草稿。草稿需要核对，微练习不换算正式考试分数。</p><button class="btn accent" data-action="ws-agent-mode" data-mode="draft">设置个性化出题任务 →</button><button class="btn text" data-action="ws-route" data-route="materials">用自己的资料学习 →</button></section>
        <section class="workspace-start"><p>口语自动转写 / 发音评分、完整计时模考和全部题型尚未实现。听力不以 TTS 冒充已核验真人材料。</p><button class="btn text small" data-action="ws-route" data-route="features">查看功能范围 →</button></section>`);
}
async function workspaceStudents(){
    await workspaceLoad();view='students';
    const selected=workspacePeople.find(x=>x.peer.id===selectedPeer);
    shell(`${workspaceHeading('TEACH / 学生档案','把教学放回同一份学生记录。','只显示当前已配对学生；对方未提交的草稿和私人资料不会自动共享。','<button class="btn accent" data-action="invite">＋ 邀请学生配对</button>')}
        ${workspacePeople.length?`<div class="local-grid"><aside class="local-rail" aria-label="选择学生">${workspacePeople.map(({peer,data})=>`<button data-action="ws-select-student" data-peer="${h(peer.id)}" class="${peer.id===selectedPeer?'selected':''}" aria-pressed="${peer.id===selectedPeer}"><strong>${h(data.person.name)}</strong><small>${peerState(peer.id)} · ${data.tasks.length} 个任务</small></button>`).join('')}</aside><section class="card"><h2>${h(selected.data.person.name)}</h2><p class="muted">${subjectCurrent()==='english'?(selected.data.person.exam==='ielts'?'雅思 Academic':'托福 2026')+' · '+h(stages[selected.data.person.stage]):h(subjectLabel(subjectCurrent()))+'学习记录'}</p><div class="actions"><button class="btn accent" data-action="ws-route" data-route="assign">给这位学生布置任务</button><button class="btn ghost" data-action="ws-peer-tasks" data-peer="${h(selectedPeer)}">查看这位学生的作业</button></div><p class="small muted">近期错因线索：${h((selected.data.weak_skills||[]).join('、')||'暂无自动核对线索')}。仅来自已有题目，不作为完整能力诊断。</p><form id="notes-form" class="local-form"><label class="field">教师私有档案备注<textarea name="notes" maxlength="3000">${h(selected.data.person.notes||'')}</textarea><small>只保存在教师本机，不发送给学生或模型。</small></label><button class="btn ghost" type="submit">保存备注</button></form></section></div>`:workspaceEmpty('先连接第一位学生','老师生成配对码，学生在自己的电脑输入后就会出现。','<button class="btn accent" data-action="invite">生成学生配对码</button>')}`);
}
async function workspaceAssign(){
    await workspaceLoad();view='assign';
    if(!workspacePeople.length){shell(`${workspaceHeading('TEACH / 布置任务','先与学生建立连接。','资料可以先保存在教师本机；布置任务需要选择一位已配对学生。')}<section class="card"><button class="btn accent" data-action="invite">生成学生配对码</button><button class="btn ghost" data-action="ws-route" data-route="materials">先准备资料</button></section>`);return;}
    workspacePacks=subjectCurrent()==='english'?(await api('/api/local/resources')).packs:[];
    shell(`${workspaceHeading('TEACH / 布置任务','先明确目标，再选资料和方法。','只有选择的任务与资料片段发送给学生，教师资料库不会整库同步。')}
        <section class="card"><label class="field">这次布置给谁<select id="workspace-assign-peer">${workspacePeople.map(({peer,data})=>`<option value="${h(peer.id)}" ${peer.id===selectedPeer?'selected':''}>${h(data.person.name)}</option>`).join('')}</select></label></section>
        <div class="workspace-two-col"><section class="card"><span class="eyebrow">01 / 通用资料学习</span><h2>从资料设计任务</h2><p>打开一段课文、讲义或笔记，说明希望学生做到什么，再选择理解、针对困难练习或应用表达。</p><p class="small muted">发布时保存目标、选择理由、标准和原文版本。可以先理解资料，不必先诊断。</p><button class="btn accent" data-action="ws-route" data-route="materials">选资料并设计任务 →</button></section>
        ${subjectCurrent()==='english'?`<section class="card"><span class="eyebrow">02 / 英语题包</span><h2>从已有练习布置</h2><form id="assign-form" class="local-form"><label class="field">布置什么任务<select id="assign-purpose" name="purpose">${Object.entries(labels).filter(([k])=>k!=='reading').map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label><label class="field">选择题包<select id="resource-id" name="resource_id"></select></label><p class="small muted" id="workspace-assign-hint"></p><button class="btn accent" type="submit">布置给这位学生</button></form></section>`:''}</div>
        <section class="workspace-start"><p>还没有合适题包？模型草稿先审校，听力题先完整试听后放行。</p><button class="btn ghost small" data-action="ws-agent-mode" data-mode="draft">准备原创出题草稿</button><button class="btn text small" data-action="ws-route" data-route="resources">导入与审校题库 →</button></section>`);
    if(subjectCurrent()==='english')workspaceAssignOptions();else $('.workspace-start')?.remove();
}
function workspaceAssignOptions(){
    const data=workspacePeople.find(x=>x.peer.id===selectedPeer)?.data;dashboard=data;
    const purpose=$('#assign-purpose')?.value;if(!data||!purpose)return;
    const packs=workspacePacks.filter(p=>p.status==='ready'&&p.exam===data.person.exam&&(purpose==='listening'?Boolean(p.audio):!p.audio));
    $('#resource-id').innerHTML=`<option value="">${purpose==='listening'?'自动选择已审核听力':'使用现有规则准备'}</option>`+packs.map(p=>`<option value="${h(p.id)}">${h(p.title)}</option>`).join('');
    $('#workspace-assign-hint').textContent=purpose==='listening'&&!packs.length?'本机暂无符合这位学生考试路线的已审核录音。请先导入、核对原文并完整试听。':purpose==='practice'||purpose==='retest'?'当前英语补练 / 复测分支会检查学生已有的诊断与练习记录。':'只显示当前考试路线的已审核题包。';
}
async function workspaceConnections(){
    await refreshStatus();view='connections';const teacher=workspaceTeacher();
    const peers=status.peers.filter(p=>p.state==='active'&&p.role===(teacher?'student':'teacher'));
    shell(`${workspaceHeading('CONNECT / 本机配对',teacher?'老师与学生，各自在自己的电脑使用。':'连接老师，开始一起学习。','任务和作品按配对关系交换。已经接收的内容可离线查看；双方在线时继续送达。',`<button class="btn accent" data-action="${teacher?'invite':'join'}">${teacher?'生成学生配对码':'输入老师配对码'}</button>`)}<section class="card"><h2>${teacher?'已配对的学生':'我的老师'}</h2>${peers.length?peers.map(p=>`<div class="local-task"><div><h3>${h(p.name)}</h3><p class="small muted">${peerState(p.id)}</p></div><button class="btn text small" data-action="unpair" data-peer="${h(p.id)}">解除连接</button></div>`).join(''):workspaceEmpty('尚未连接',teacher?'点击上方按钮生成配对码，发给对应学生。':'输入老师本地版提供的 12 位配对码；没有老师也可以自主学习。')}<p class="small muted">待发送 ${status.pending_messages} 条。解除配对停止后续交换，对方已经保存的副本仍可能保留。</p></section><section class="card"><h2>也可以让自己的 Agent 使用</h2><p>外部 Agent 通过本机 MCP 操作同一份资料和学习记录，使用它自己的模型配置。</p><button class="btn ghost" data-action="mcp-config">查看本地 MCP 连接配置</button></section>`);
}
async function workspacePlanning(){
    await workspaceLoad();view='planning';const plan=dashboard.person.goal_plan;
    shell(`${workspaceHeading('PLAN / 目标与机会准备','把想做的事，变成有依据的下一步。','沿用投石问路的目标 → 要求 → 证据差距 → 活动 → 完成标准。官方要求和截止日期需要另行核实。','<button class="btn accent" data-action="goal">设置我的目标</button>')}
        <section class="card">${plan?.target?`<h2>${h(plan.target)}</h2>${(plan.gaps||[]).map(g=>`<article class="result-item"><h3>${h(g.requirement)}</h3><p>${h(g.evidence_status)}</p><p>完成标准：${h(g.completion_standard)}</p></article>`).join('')}`:workspaceEmpty('先选一个具体目标','例如准备一次导师交流、完成一份申请材料或参加研讨小组。先写目标，系统保存准备清单。')}<p class="small muted">这是准备清单，不预测录取概率，也不自动确认个人能力。</p></section>`);
}
async function workspaceFeatures(){
    view='features';
    if(!workspaceFeatureRows.length){const response=await fetch('/assets/feature-coverage.json');if(!response.ok)throw Error('功能清单暂时未能读取');workspaceFeatureRows=(await response.json()).items;}
    shell(`${workspaceHeading('SCOPE / 功能清单','已实现什么，还缺什么，一目了然。','规则运行条件、六类方法、原图、有界札记和个人复习已接入。专业审定、检索评测和 S3 扩展仍需补齐。')}
        <section class="card"><div class="workspace-toolbar"><label class="workspace-search">搜索功能<input id="workspace-feature-search" class="input" type="search" placeholder="例如：听力、评价、复习、记忆"></label><label>实现状态<select id="workspace-feature-filter"><option value="all">全部</option><option value="available">已可用</option><option value="partial">部分实现</option><option value="planned">尚未实现</option></select></label></div><div id="workspace-features"></div></section><p class="small muted">清单按本地源码范围记录；服务器、公开下载包和真实用户教学效果另行验收。可用入口只连接当前身份可以使用的功能。</p>`);
    workspaceRenderFeatures();
}
function workspaceRenderFeatures(){
    const query=$('#workspace-feature-search').value.trim().toLowerCase(),filter=$('#workspace-feature-filter').value;
    const items=workspaceFeatureRows.filter(i=>(filter==='all'||i.status===filter)&&[i.title,i.detail,i.id].join(' ').toLowerCase().includes(query));
    $('#workspace-features').innerHTML=items.map(i=>{const route=(workspaceTeacher()?i.teacher_route:i.student_route)||i.route;return `<article class="workspace-feature"><div><span class="status-pill ${i.status==='partial'?'attention':''}">${({available:'已可用',partial:'部分实现',planned:'尚未实现'})[i.status]}</span> <span class="small muted">${h(i.layer)} · ${h(i.id)}</span><h3>${h(i.title)}</h3><p class="small muted">${h(i.detail)}</p></div>${route&&workspaceAllowed(route)?`<button class="btn ghost small" data-action="ws-route" data-route="${h(route)}">打开入口 →</button>`:''}</article>`;}).join('')||workspaceEmpty('未找到对应功能','试试其他关键词或切换实现状态。');
}
function workspaceEnhance(){
    if(view!=='task'||!currentTask||!$('.stimulus'))return;
    const back=$('.workspace-content > button[data-action="home"]');if(back){back.dataset.action='ws-route';back.dataset.route=workspaceReturn;back.textContent='← 返回'+(workspaceTeacher()?'作业列表':workspaceReturn==='feedback'?'反馈与修订':'我的任务');}
    const task=currentTask,s=WorkspaceState.taskState(task,status.profile.role),last=task.attempts.at(-1);
    const tools=document.createElement('section');tools.className='workspace-task-next';tools.innerHTML=`<div><strong>${s.label}</strong><p class="small muted">${h(last?.evaluation?.next_step||task.pack.companion_plan?.goal||'查看要求，完成本次作品；历史提交会保留。')}</p></div><div class="actions">${last?workspaceTeacher()?`<button class="btn accent" data-action="study-assess" ${task.state==='archived'?'disabled':''}>评阅最新作品</button>`:'<button class="btn ghost" data-action="ws-jump-feedback">查看本次反馈</button>':''}${!workspaceTeacher()&&task.state==='active'?'<button class="btn accent" data-action="ws-jump-work">'+(last?'继续修订作品':'开始作答')+'</button>':''}</div>`;
    $('.stimulus').before(tools);
    document.querySelectorAll('[data-action="feedback"]').forEach(b=>{if(b.dataset.id===last?.id)b.remove();else b.classList.add('workspace-old-review');});
}
async function workspaceRender(route){
    if(!workspaceAllowed(route))throw Error('此入口不属于当前本机身份。');
    if(academicContext?.selection.subject==='legacy'&&route==='home'){
        view='home';return shell(`${workspaceHeading('ARCHIVE / 历史工作区','旧版记录完整保留，等待确认归属。','这里仅查看旧版资料与作业。已明确分类的资料已复制到对应学科；未知作业没有自动猜测归属。')}<div class="workspace-action-grid">${workspaceRouteCard('查看历史资料','确认归属后，迁入对应学科的独立文件夹。','materials')}${workspaceRouteCard('查看历史作业','原始提交、反馈和签名记录保留，不在其他学科混显。',workspaceTeacher()?'review':'tasks')}${workspaceRouteCard('切换学科工作区','进入一个学科，继续学习或布置新任务。','academic')}</div>`);
    }
    if(route==='policy')return continuityPolicy();
    if(route==='policy-lab')return policyLab();
    if(route==='retrieval')return retrievalHome();
    if(route==='paths')return evolutionPaths();
    if(route==='writing')return evolutionWriting();
    if(route==='methods')return methodLibrary();
    if(route==='memory')return continuityMemory();
    if(route==='reviews')return continuityReviews();
    if(route==='home')return home();
    if(['tasks','feedback','review'].includes(route))return workspaceTasks(route);
    if(route==='practice')return workspacePractice();
    if(route==='students')return workspaceStudents();
    if(route==='assign')return workspaceAssign();
    if(route==='connections')return workspaceConnections();
    if(route==='planning')return workspacePlanning();
    if(route==='materials')return studyHome();
    if(route==='resources')return resources();
    if(route==='agent'){await workspaceLoad();agentPage();return jobHistory();}
    if(route==='settings'){await refreshStatus();return settings();}
    if(route==='guide')return guide();
    if(route==='features')return workspaceFeatures();
}
async function workspaceNavigateNow(route,options={}){
    if(!workspaceRoutes.includes(route))return;
    if(!workspaceAllowed(route))throw Error('此入口不属于当前本机身份。');
    if(recorder?.state==='recording')throw Error('请先点击“停止录音并保存”，录音保存后再切换页面。');
    if(view==='task')await saveDraft();
    stopRecording();
    if(options.reset!==false){workspaceFilter=route==='feedback'?'feedback':'all';workspaceQuery='';}
    if(options.filter)workspaceFilter=options.filter;
    const epoch=++workspaceEpoch;
    await workspaceRender(route);
    if(epoch!==workspaceEpoch)return;
    const hash=WorkspaceState.routeHash(route,options);
    if(options.history!==false&&location.hash!==hash)history.pushState({route},'', '/'+hash);
    window.scrollTo({top:0,behavior:'instant'});workspaceFocusHeading();
}
// Preserve click order when multiple local reads finish at different times.
let workspaceNavigationTail=Promise.resolve();
function workspaceNavigate(route,options={}){
    const next=workspaceNavigationTail.then(()=>workspaceNavigateNow(route,options));
    workspaceNavigationTail=next.catch(()=>{});return next;
}
async function workspaceBoot(){
    const target=WorkspaceState.routeTarget(location.hash),route=target.route;
    if(route==='task'&&history.state?.task){
        await refreshStatus();selectedPeer=history.state.peer||'';workspaceReturn=workspaceTeacher()?'review':'tasks';await openTask(history.state.task);return;
    }
    await workspaceNavigate(workspaceRoutes.includes(route)&&workspaceAllowed(route)?route:'home',{history:false});
}
document.addEventListener('click',async event=>{
    const b=event.target.closest('[data-action]');if(!b)return;
    const action=b.dataset.action;
    const legacyNavigation=['home','materials','resources','agent','settings','guide'];
    if(!action.startsWith('ws-')&&!legacyNavigation.includes(action)&&action!=='open-task')return;
    event.preventDefault();event.stopImmediatePropagation();
    if(sending||studyBusy||(typeof academicBusy!=='undefined'&&academicBusy)||(typeof continuityBusy!=='undefined'&&continuityBusy)||(typeof retrievalBusy!=='undefined'&&retrievalBusy)){notify('正在保存这次操作，请稍候。');return;}
    try{
        if(action==='ws-skip')workspaceFocusHeading();
        else if(action==='ws-menu'){const open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',String(open));b.textContent=open?'收起导航菜单':'打开导航菜单';b.closest('aside').classList.toggle('is-open',open);}
        else if(action==='ws-route'||legacyNavigation.includes(action))await workspaceNavigate(b.dataset.route||action);
        else if(action==='ws-filter-route')await workspaceNavigate(b.dataset.route,{filter:b.dataset.filter});
        else if(action==='ws-filter'){workspaceFilter=b.dataset.filter;document.querySelectorAll('.workspace-filters button').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});workspaceRenderTasks();}
        else if(action==='ws-refresh')await workspaceNavigate(view,{reset:false,history:false});
        else if(action==='ws-task'||action==='open-task'){
            await saveDraft();workspaceReturn=['tasks','feedback','review'].includes(view)?view:workspaceTeacher()?'review':'tasks';
            if(b.dataset.peer)selectedPeer=b.dataset.peer;await openTask(b.dataset.id);history.pushState({task:b.dataset.id,peer:selectedPeer},'','/#task');window.scrollTo({top:0,behavior:'instant'});workspaceFocusHeading();
        }else if(action==='ws-select-student'){selectedPeer=b.dataset.peer;await workspaceStudents();}
        else if(action==='ws-peer-tasks'){await workspaceNavigate('review');$('#workspace-student-filter').value=b.dataset.peer;workspaceRenderTasks();}
        else if(action==='ws-demo'){
            await workspaceNavigate('materials');
            const result=await subjectSaveExample();await studyHome();
            await studyRead({material_id:result.data.material.id});
            notify('试试：选一段原文提问，或点“用这段资料学习”填写一个小目标。');
        }else if(action==='ws-agent-mode'){await workspaceNavigate('agent');$('#agent-mode').value=b.dataset.mode;$('#agent-prompt').placeholder='描述要解决的具体困难、希望的题型和本次完成标准。';$('#agent-prompt').focus();}
        else if(action==='ws-start'){
            try{const t=await api('/api/local/tasks',{purpose:b.dataset.purpose,request_key:uid()});workspaceReturn='tasks';await openTask(t.id);history.pushState({task:t.id},'','/#task');}
            catch(e){modal('开始这项练习还缺一步',`<p>${h(e.message)}</p><p class="small muted">通用资料学习可以直接开始，不受英语练习的前置条件限制。</p><div class="actions"><button class="btn accent" data-action="ws-recover-practice">返回英语练习</button><button class="btn ghost" data-action="ws-recover-materials">用自己的资料学习</button></div>`);}
        }else if(action==='ws-recover-practice'||action==='ws-recover-materials'){closeModal();await workspaceNavigate(action.endsWith('materials')?'materials':'practice');}
        else if(action==='ws-jump-work'){$('#work-form')?.scrollIntoView({behavior:'smooth',block:'start'});$('#work-text')?.focus({preventScroll:true});}
        else if(action==='ws-jump-feedback'){const section=Array.from(document.querySelectorAll('section')).find(s=>s.querySelector('h2')?.textContent==='已收到的反馈与提交历史');section?.scrollIntoView({behavior:'smooth',block:'start'});}
    }catch(e){notify(e.message,true);}
},true);
document.addEventListener('input',e=>{if(e.target.id==='workspace-search'){workspaceQuery=e.target.value;workspaceRenderTasks();}if(e.target.id==='workspace-feature-search')workspaceRenderFeatures();});
document.addEventListener('change',e=>{if(e.target.id==='workspace-student-filter')workspaceRenderTasks();if(e.target.id==='workspace-feature-filter')workspaceRenderFeatures();if(e.target.id==='workspace-assign-peer'){selectedPeer=e.target.value;workspaceAssignOptions();}if(e.target.id==='assign-purpose')workspaceAssignOptions();if(e.target.id==='workspace-agent-peer')selectedPeer=e.target.value;});
window.addEventListener('popstate',()=>{if(location.hash.startsWith('#start='))return;workspaceBoot().catch(e=>notify(e.message,true));});

// Keep keyboard focus inside dialogs, then restore it to their initiating control.
document.addEventListener('keydown',e=>{
    if(e.key!=='Tab'||!$('#modal-root').children.length)return;
    const controls=Array.from(document.querySelectorAll('.modal button,.modal input,.modal select,.modal textarea,.modal a,[role="dialog"] [tabindex]')).filter(el=>!el.disabled&&el.getClientRects().length);
    const first=controls[0],last=controls.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
});

function workspaceFocusHeading(){const heading=$('.workspace-content h1');if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}}
let workspaceRefreshing=false;
async function workspaceRefreshVisible(){
    if(workspaceRefreshing||!status?.profile?.role||document.hidden||$('#modal-root').children.length||sending||studyBusy||!['home','tasks','feedback','review'].includes(view))return;
    const original=view,epoch=workspaceEpoch,previous=JSON.stringify(workspaceRows),pending=status.pending_messages;
    workspaceRefreshing=true;
    try{
        await workspaceLoad();
        if(view!==original||epoch!==workspaceEpoch)return;
        if(JSON.stringify(workspaceRows)!==previous||pending!==status.pending_messages){
            if(original==='home'){const focused=document.activeElement;await home();if(focused?.dataset?.route){document.querySelector(`.workspace-sidebar [data-route="${CSS.escape(focused.dataset.route)}"]`)?.focus({preventScroll:true});}}
            else workspaceRenderTasks();
        }
    }catch(e){/* Manual refresh reports service errors; background refresh stays quiet. */}
    finally{workspaceRefreshing=false;}
}
