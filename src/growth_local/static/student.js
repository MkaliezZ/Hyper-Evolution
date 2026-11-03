"use strict";
// Guided students follow assigned work; explicit self mode reuses the original local learning capabilities.
function studentGuidedMode(){return !workspaceTeacher()&&!(typeof selfStudyMode==='function'&&selfStudyMode());}
const studentPreviousAllowed=workspaceAllowed;
workspaceAllowed=function(route){return !studentGuidedMode()?studentPreviousAllowed(route):StudentState.routes.includes(route)&&studentPreviousAllowed(route);};
const studentPreviousNavigation=workspaceNavigation;
workspaceNavigation=function(){
 if(!studentGuidedMode())return studentPreviousNavigation();
 const current=StudentState.section(view,workspaceReturn);
 const groups=[['学习领域',[['academic','切换学科']]],...StudentState.groups];
 return `<aside class="workspace-sidebar"><button class="workspace-menu-toggle" data-action="ws-menu" aria-expanded="false" aria-controls="workspace-navigation">打开导航菜单</button><nav aria-label="本机导航" id="workspace-navigation">${groups.map(([title,items])=>`<div class="workspace-nav-group"><p>${title}</p>${items.filter(([r])=>workspaceAllowed(r)).map(([route,label])=>`<button data-action="ws-route" data-route="${route}" class="${current===route?'active':''}" ${current===route?'aria-current="page"':''}>${label}</button>`).join('')}</div>`).join('')}</nav><div class="workspace-device"><strong>保存在这台电脑</strong><small>按老师的任务学习，提交后查看反馈。</small></div></aside>`;
};
const studentPreviousRender=workspaceRender;
workspaceRender=async function(route){
 if(studentGuidedMode()&&subjectReadOnly()&&route==='home'){
  view='home';return shell(`${workspaceHeading('ARCHIVE / 历史记录','查看以前收到的任务。','历史原答和反馈保留在本机。继续新任务时，先切换到对应学科。')}${workspaceRouteCard('查看历史任务','打开以前收到的作业和反馈。','tasks')}${workspaceRouteCard('切换学科','回到老师本次布置的任务。','academic')}`);
 }
 return studentPreviousRender(route);
};
workspaceStudentHome=async function(){
 await workspaceLoad();view='home';const rows=StudentState.tasks(workspaceRows);
 const todo=rows.filter(t=>WorkspaceState.matches(t,'todo','','student')),revisions=rows.filter(t=>WorkspaceState.taskState(t,'student').key==='revision'),waiting=rows.filter(t=>WorkspaceState.matches(t,'waiting','','student'));
 shell(`${workspaceHeading('TODAY / 学习首页',`${status.profile.name}，先完成这次学习。`,'老师布置的任务、反馈和下一步安排，都从这里继续。')}
 <div class="workspace-metrics"><button data-action="ws-filter-route" data-route="tasks" data-filter="todo"><b>${todo.length}</b><span>待完成 / 待修订</span></button><button data-action="ws-filter-route" data-route="feedback" data-filter="revision"><b>${revisions.length}</b><span>需要修订</span></button><button data-action="ws-filter-route" data-route="tasks" data-filter="waiting"><b>${waiting.length}</b><span>待送达 / 待评阅</span></button></div>
 <section class="card"><div class="section-head"><h2>现在要做的任务</h2><button class="btn text small" data-action="ws-route" data-route="tasks">查看全部任务 →</button></div>${todo.length?todo.slice().reverse().slice(0,3).map(workspaceTaskRow).join(''):workspaceEmpty('本学科暂时没有待完成任务','可以先看看老师的规划，或保持双方程序在线等待新任务。')}</section>
 <div class="workspace-action-grid">${workspaceRouteCard('老师的规划','了解当前目标、准备情况和老师建议的下一步。','planning')}${workspaceRouteCard('学习安排','按老师发布的步骤，找到对应任务继续。','paths')}${workspaceRouteCard('反馈与修订','打开原任务，对照老师建议修改再提交。','feedback')}</div>
 <section class="workspace-start"><p>第一次使用：连接老师 → 切换到对应学科 → 打开任务 → 完成并提交 → 查看反馈。</p><button class="btn ghost" data-action="ws-route" data-route="connections">连接我的老师</button><button class="btn text" data-action="ws-route" data-route="guide">查看使用说明</button></section>`);
};
const studentPreviousTasks=workspaceRenderTasks;
workspaceRenderTasks=function(){if(!studentGuidedMode())return studentPreviousTasks();const original=workspaceRows;try{workspaceRows=StudentState.tasks(original);studentPreviousTasks();const empty=$('#workspace-task-list .workspace-empty');if(empty)empty.innerHTML='<h3>这里暂时没有对应的任务</h3><p class="muted">可切换状态、清空搜索，或确认老师已发布任务、双方已连接且学科一致。</p>';}finally{workspaceRows=original;}};
const studentPreviousTaskPage=workspaceTasks;
workspaceTasks=async function(route){await studentPreviousTaskPage(route);if(studentGuidedMode())$('#workspace-content .local-top .muted').textContent=route==='feedback'?'查看老师的反馈，打开原任务修订；提交和送达状态分别显示。':'这里只显示老师布置的本学科任务，打开后查看要求并完成。';};
const studentPreviousPlanning=workspacePlanning;
workspacePlanning=async function(){
 if(!studentGuidedMode())return studentPreviousPlanning();
 await workspaceLoad();view='planning';const data=(await g9('context')).data,plans=StudentState.plans(data.plans,status.device_id);
 shell(`${workspaceHeading('PLAN / 老师的规划','知道目标，再完成眼前这一步。','这里查看老师明确分享给你的规划。需要调整时，先和老师讨论，由老师更新并重新分享。')}
 ${plans.map(p=>`<section class="card"><p class="small muted">${h(status.peers.find(x=>x.id===p.owner_device)?.name||'老师')}分享 · 第${p.revision}版</p><h2>${h(p.content.goal||'老师的成长建议')}</h2>${growthFacts(p.content)}${p.content.requirements.map(r=>`<div class="growth-action"><h3>${h(r.requirement)}</h3><p>已有准备：${h(r.current_evidence||'和老师一起补充')}<br>下一步：${h(r.next_action||'和老师讨论')}<br>完成标准：${h(r.completion_standard||'按本次任务要求')}</p></div>`).join('')}<button class="btn accent" data-action="ws-route" data-route="tasks">去完成老师布置的任务 →</button></section>`).join('')||'<section class="card"><h2>老师还没有分享本学科规划</h2><p>保持配对连接。老师在教师端完成投石问路并明确分享后，会显示在这里。</p></section>'}`);
};
const studentPreviousPaths=evolutionPaths;
evolutionPaths=async function(){
 if(!studentGuidedMode())return studentPreviousPaths();
 await e5Load();view='paths';const paths=StudentState.schedules((await c5('path.list')).data.paths,status.device_id),tasks=StudentState.tasks(workspaceRows);
 shell(`${workspaceHeading('ARRANGE / 学习安排','按老师的安排，一步一步完成。','查看老师已发布的安排。完成情况以对应任务的实际提交和反馈为准。')}${paths.map(p=>`<section class="card"><span class="eyebrow">老师发布 · 第${p.revision}版</span><h2>${h(p.title)}</h2><p>${h(p.goal)}</p><ol>${p.steps.map(s=>`<li>${h(s.action)} · 约${s.minutes}分钟${s.due_date?' · '+h(s.due_date):''}</li>`).join('')}</ol>${p.task_ids.map(id=>tasks.find(t=>t.id===id)).filter(Boolean).map(workspaceTaskRow).join('')}</section>`).join('')||'<section class="card"><h2>老师还没有发布本学科安排</h2><p>你可以先完成“我的任务”中的作业。</p><button class="btn accent" data-action="ws-route" data-route="tasks">查看我的任务 →</button></section>'}`);
};
const studentPreviousSubjects=academicSubjects;
academicSubjects=async function(){
 if(!studentGuidedMode())return studentPreviousSubjects();
 await academicLoad();view='academic';shell(`${workspaceHeading('SUBJECT / 切换学科','找到这次作业所在的学科。','进入学科后，只显示该学科的任务、反馈和老师规划。身份、配对和模型设置共用。')}<div class="workspace-action-grid">${Object.entries(academicCatalog.subjects).map(([id,item])=>workspaceCard(h(item.name),id===subjectCurrent()?'当前学科':'查看本学科老师布置的任务','academic-select',`data-subject="${h(id)}" data-track="${id==='english'?(academicContext.selection.subject==='english'?academicContext.selection.track:'k12'):'materials'}"`)).join('')}</div>`);
};
function studentTaskReader(){
 if(!studentGuidedMode())return;
 document.querySelectorAll('[data-action="study-practice"],[data-action="study-edit"],[data-action="c3-image-design"]').forEach(b=>b.remove());
 document.querySelectorAll('[data-action="subject-return"]').forEach(b=>{b.dataset.action='student-return-task';b.textContent='← 返回这次任务';});
 document.querySelectorAll('#study-reader p').forEach(p=>{if(p.textContent.includes('选中片段后解释或练习'))p.textContent='选中片段后可以提问；完成后返回本次任务继续作答。';});
}
const studentPreviousRead=studyRead;
studyRead=async function(source){await studentPreviousRead(source);studentTaskReader();};
const studentPreviousPage=c3OpenPage;
c3OpenPage=async function(source){await studentPreviousPage(source);studentTaskReader();};
const studentPreviousEnhance=continuityEnhance;
continuityEnhance=async function(){await studentPreviousEnhance();if(studentGuidedMode()){
 document.querySelectorAll('.continuity-task-tools,#study-task-panel,[data-action="c3-capture"]').forEach(e=>e.remove());
 document.querySelectorAll('#workspace-content details').forEach(e=>{if(e.querySelector('summary')?.textContent==='这次采用了哪些专业判断规则')e.remove();});
}};
const studentPreviousGuide=guide;
guide=function(){
 if(!studentGuidedMode()){studentPreviousGuide();$('#workspace-content')?.insertAdjacentHTML('afterbegin','<section class="card"><h2>教师分工与 AI 入口</h2><p>老师负责规划、备课、布置和评阅；学生主要完成任务、查看反馈和老师已发布的规划。</p><p>投石问路保存成长卡，再明确分享给学生；学生端称为“老师的规划”，按只读方式展示。学习助手提供备课、看学生情况、准备练习和预审作业四个入口。</p><p>模型还可在资料页解释原文或原图，在写作页准备局部建议，在K12路线备题和独立审题，在作品评阅页准备预审。内置模型使用老师自己配置的 API；保存成长卡、配对和查看记录无需模型。</p></section>');return;}
 view='guide';shell(`${workspaceHeading('GUIDE / 学生使用说明','先找到任务，其他按需要再用。','学生端围绕老师布置的学习展开。首次先连接老师、选对学科。')}
 <section class="card"><h2>完成一次学习</h2><ol><li>打开“我的老师”，输入老师给的配对码，双方保持程序运行。</li><li>从顶部“切换学科”进入作业对应学科，再打开“我的任务”。</li><li>阅读要求、资料与完成标准，完成作答或录音，点击“提交给老师”。</li><li>看发送状态，等待老师评阅；收到反馈后回到原任务修订并再次提交。</li></ol></section>
 <section class="card"><h2>老师的规划与学习安排</h2><p>“老师的规划”查看老师明确分享的成长目标与下一步。“学习安排”查看老师已发布的步骤和关联任务。学生端直接阅读即可，规划调整由老师更新。</p></section>
 <section class="card"><h2>AI 在哪里 能帮我做什么</h2><p>学生端保留完成任务时需要的帮助，没有独立备题或教学管理入口。</p><ul><li>文字任务中的“为这份任务保存首稿”进入写作与修订，打开作品后可点“用自己的模型准备建议”。先看差异，确认修改后，再明确提交给老师。</li><li>任务中的“打开本次原文 / 原图”可查看资料。允许使用帮助的任务，可从原文提问或围绕原图提问；原图需要支持图片的模型。</li><li>老师可能先用AI预审，再修改确认后发反馈。查看这些反馈使用老师一侧的结果，不消耗你的模型额度。</li></ul><p>如需自己调用模型，在“模型与本机设置”填写自己的 API 并测试。模型会读取本次需要的文字或原图；考试或独立测验请遵守老师的帮助要求。听力播放、作答、提交、看规划与反馈都无需配置模型。</p></section>
 <section class="card"><h2>MCP 和数据</h2><p>设置里可复制本地MCP配置，连接自己的Agent；先让它确认当前学科，只处理老师的任务。普通Agent推理由该Agent自身配置计费；明确启动工作台模型能力时，使用工作台所配API。作品和记录保存在本机，明确提交后老师收到副本。换机先在设置中创建加密恢复包。</p></section>`);
};
// Old bookmarks land on assigned work; new navigation never opens teaching tools for students.
const studentPreviousBoot=workspaceBoot;
workspaceBoot=async function(){if(studentGuidedMode()&&['k12','practice','agent','materials','retrieval','policy','policy-lab','methods','memory','reviews'].includes(WorkspaceState.routeTarget(location.hash).route)){await academicLoad();return workspaceNavigate('tasks',{history:true});}return studentPreviousBoot();};
document.addEventListener('click',event=>{
 if(!studentGuidedMode())return;const b=event.target.closest('[data-action]');if(!b)return;
 if(b.dataset.action==='student-return-task'){event.preventDefault();event.stopImmediatePropagation();if(currentTask)openTask(currentTask.id).catch(e=>notify(e.message,true));return;}
 if(b.dataset.action.startsWith('growth-')||['goal','academic-route-new','academic-scope-new','academic-generate','c3-capture','c3-schedule','ws-demo'].includes(b.dataset.action)){event.preventDefault();event.stopImmediatePropagation();notify('学生端按老师布置的任务学习；规划和练习由老师准备。');}
},true);
