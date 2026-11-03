"use strict";
function selfStudyMode(){return status?.profile?.role==='student'&&status?.experience?.id==='self';}
function experienceMode(){return workspaceTeacher()?'teacher':selfStudyMode()?'self':'student';}
const experienceCall=(operation,payload={},request_id=uid())=>api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v11',request_id,operation,payload});
const experienceOldHeader=header;
header=function(){experienceOldHeader();if(!status?.profile?.role)return;const brand=$('.brand strong'),small=$('.brand small');
 if(brand)brand.textContent=workspaceTeacher()?'Enlighter':selfStudyMode()?'Self-Evolver':'Evolver';if(small)small.textContent='超维成长 · '+(workspaceTeacher()?'教师工作台':selfStudyMode()?'自学版':'跟随老师学习');
 document.title=(workspaceTeacher()?'Enlighter · 教师版':selfStudyMode()?'Self-Evolver · 自学版':'Evolver · 学生版')+'｜超维成长';
 const spans=document.querySelectorAll('.workspace-header-tools>span');if(spans.length)spans[spans.length-1].textContent=workspaceTeacher()?'教师版':selfStudyMode()?'自学版':'学生版';};
const experienceOldSetup=setup;
setup=function(){experienceOldSetup();const select=$('#role');if(select){select.innerHTML='<option value="student">Evolver · 学生版（跟随老师）</option><option value="self">Self-Evolver · 自学版（自主学习）</option><option value="teacher">Enlighter · 我是老师</option>';if(['teacher','student','self'].includes(status?.launch_edition))select.value=status.launch_edition;}};
const experienceOldAllowed=workspaceAllowed;
workspaceAllowed=function(route){
 if(!selfStudyMode())return experienceOldAllowed(route);
 return ['home','academic','materials','agent','retrieval','policy','tasks','practice','writing','feedback','reviews','memory','planning','paths','connections','settings','guide','features'].includes(route)&&studentPreviousAllowed(route);
};
workspaceNavigation=function(){
 const mode=experienceMode(),group=ExperienceState.group(mode,view,workspaceReturn),groups=ExperienceState[mode];
 const button=(route,label,active)=>`<button data-action="ws-route" data-route="${route}" class="${active?'active':''}" ${active?'aria-current="page"':''}>${label}</button>`;
 const utilOpen=group[0]==='settings';
 return `<aside class="workspace-sidebar"><button class="workspace-menu-toggle" data-action="ws-menu" aria-expanded="false" aria-controls="workspace-navigation">打开导航菜单</button><nav aria-label="本机导航" id="workspace-navigation"><p class="experience-caption">${({teacher:'ENLIGHTER / 教学工作台',self:'SELF-EVOLVER / 自学版',student:'EVOLVER / 学生版'})[mode]}</p><div class="workspace-nav-group">${button('academic','学科与路线',group[0]==='academic')}</div><div class="workspace-nav-group">${groups.filter(([route])=>workspaceAllowed(route)).map(([route,label])=>button(route,label,group[0]===route)).join('')}</div><details class="experience-utilities" ${utilOpen?'open':''}><summary>连接与设置</summary><div class="workspace-nav-group">${ExperienceState.utilities(mode).filter(([route])=>workspaceAllowed(route)).map(([route,label])=>button(route,label,ExperienceState.section(view,workspaceReturn,mode)===route)).join('')}</div></details></nav><div class="workspace-device"><strong>保存在这台电脑</strong><small>${mode==='student'?'按老师的任务学习，提交后查看反馈。':status.model?.configured?'使用自己的 '+h(status.model.model):'AI帮助需要先配置自己的API'}</small>${mode!=='teacher'?experienceSwitch():`<button data-action="ws-route" data-route="settings">模型配置与备份 →</button>`}</div></aside>`;
};
function experienceSwitch(){return `<div class="experience-mode" aria-label="选择学习模式"><button data-action="experience-select" data-mode="student" aria-pressed="${!selfStudyMode()}">Evolver 学生版</button><button data-action="experience-select" data-mode="self" aria-pressed="${selfStudyMode()}">Self-Evolver 自学版</button></div>`;}
const experienceOldShell=shell;
shell=function(html){
 if(status?.profile?.role){
  const mode=experienceMode(),group=ExperienceState.group(mode,view,workspaceReturn),route=ExperienceState.section(view,workspaceReturn,mode);
  const tabs=group[2].filter(([r])=>workspaceAllowed(r));
  if(tabs.length>1)html=`<nav class="experience-context" aria-label="${h(group[1])}子导航"><span>${h(group[1])}</span>${tabs.map(([r,label])=>`<button data-action="ws-route" data-route="${r}" ${r===route?'aria-current="page"':''}>${label}</button>`).join('')}</nav>`+html;
 }
 experienceOldShell(html);
};
const experienceGuidedHome=workspaceStudentHome;
workspaceStudentHome=async function(){if(!selfStudyMode())return experienceGuidedHome();
 await workspaceLoad();view='home';const tasks=ExperienceState.ownTasks(workspaceRows),todo=tasks.filter(t=>!t.attempts.length),done=tasks.filter(t=>t.attempts.length);
 shell(`${workspaceHeading('SELF-EVOLVER / 自学版',`${status.profile.name}，从一个小目标开始。`,'把资料读懂，做一份自己的作品，再用反馈决定下一步。')}
 <div class="experience-steps">${[['01','定一个目标','这次学会什么','planning'],['02','读资料与提问','读原文、看原图、问不懂的地方','materials'],['03','动手做练习','按目标和方法完成作品','tasks'],['04','对照反馈修订','核对、自评，或用自己的模型','feedback'],['05','复习再试一次','换个问题，看这次能否用出来','reviews']].map(([n,t,d,r])=>`<button class="experience-step" data-action="ws-route" data-route="${r}"><b>${n}</b><strong>${t}</strong><span>${d}</span></button>`).join('')}</div>
 <section class="card"><div class="section-head"><h2>继续这次学习</h2><button class="btn text small" data-action="ws-route" data-route="tasks">全部练习 →</button></div>${(todo.length?todo:done).slice().reverse().slice(0,3).map(workspaceTaskRow).join('')||workspaceEmpty('先加入一份自己的资料','保存文字或原图，点击“用这段资料学习”，写一个目标并预览安排。','<button class="btn accent" data-action="ws-route" data-route="materials">添加学习资料 →</button>')}</section>
 <div class="workspace-action-grid">${workspaceRouteCard('我想先试一遍','用一份自编示例，走完读资料、练习、反馈和复习。','guide')}${workspaceRouteCard('整理目标与安排','沿用成长规划和学习安排，把大目标拆成这周的小步。','planning')}${workspaceRouteCard('需要AI帮助？','配置自己的API。阅读提问、写作建议和作品反馈按需调用。','settings')}</div>`);
};
const experienceOldTasks=workspaceRenderTasks;
workspaceRenderTasks=function(){if(!selfStudyMode())return experienceOldTasks();const all=workspaceRows;try{workspaceRows=ExperienceState.ownTasks(all);studentPreviousTasks();}finally{workspaceRows=all;}};
const experienceOldTaskPage=workspaceTasks;
workspaceTasks=async function(route){await experienceOldTaskPage(route);if(selfStudyMode()){
 const heading=$('#workspace-content h1'),description=$('#workspace-content .local-top .muted');
 if(heading)heading.textContent=route==='feedback'?'对照作品，找到下一步。':'把自己的练习做完。';
 if(description)description.textContent=route==='feedback'?'打开已提交作品，可查看自动核对、AI建议和自己的反思，再回到原作修订。':'这里只列本学科自主学习任务；老师布置的任务请切换到“跟随老师”。';
 document.querySelectorAll('.workspace-filters [data-filter="waiting"],.workspace-filters [data-filter="revision"]').forEach(b=>b.remove());
}};
function experienceTaskDisplay(task){
 if(!selfStudyMode()||task.origin==='teacher')return task;
 return {...task,attempts:task.attempts.map(a=>a.evaluation?.status==='pending'&&!a.review_history?.length?{...a,evaluation:{...a.evaluation,
  comment:'这次作品已保存在本机，可以对照本次目标与标准回看。',next_step:'记录反思或查看AI建议，再修订作品；需要时安排复习。'}}:a)};
}
const experienceOldResults=results;
results=function(task){return experienceOldResults(experienceTaskDisplay(task));};
const experienceOldTaskRow=workspaceTaskRow;
workspaceTaskRow=function(task){return experienceOldTaskRow(experienceTaskDisplay(task));};
const experienceOldBoot=workspaceBoot;
workspaceBoot=async function(){return selfStudyMode()?studentPreviousBoot():experienceOldBoot();};
const experienceOldEnhance=continuityEnhance;
continuityEnhance=async function(){await experienceOldEnhance();if(!selfStudyMode()||view!=='task'||!currentTask||currentTask.origin==='teacher'||$('#self-feedback'))return;
 const next=$('.workspace-task-next>div>p');if(next&&currentTask.attempts.length)next.textContent='记录反思或查看AI建议，再修订作品；需要时安排复习。';
 const hint=$('#work-form .card>.small.muted');if(hint)hint.textContent='支持12MB以内的录音、PDF、图片或纯文本。先保留原作，再按本次标准回看；AI反馈只读取实际提供的内容。';
 const attempt=currentTask.attempts.at(-1);if(!attempt)return;
 const panel=document.createElement('section');panel.className='card experience-feedback';panel.id='self-feedback';
 panel.innerHTML=`<span class="eyebrow">REFLECT / 第 ${currentTask.attempts.length} 次提交</span><h2>看一眼结果，再决定怎么练。</h2><p>自动核对保留在作品记录。你可以先写反思，也可以让自己的模型对照本次目标、资料和实际文字准备建议。</p><div class="actions"><button class="btn accent" data-action="self-ai-review">用我的API准备作品反馈</button><button class="btn ghost" data-action="self-reflect">记录反思并安排复习</button><button class="btn text" data-action="ws-route" data-route="reviews">查看复习安排 →</button></div><p class="small muted">AI只评估实际读取的文字；录音与附件需另行查看。建议会标注来源，原作与每次修订都保留。</p><div id="self-ai-result" aria-live="polite"></div>`;
 $('.local-footer')?.before(panel);
};
guide=function(){const manual=UsageGuides.manuals[experienceMode()];view='guide';shell(`${workspaceHeading('GUIDE / 使用说明',manual.title,manual.lead)}${usageGuideBody(manual)}`);};
async function selfPoll(id,taskId){const job=await api('/api/local/jobs/'+id);if(job.status==='failed')throw Error(job.error);if(job.status!=='completed'){setTimeout(()=>selfPoll(id,taskId).catch(e=>notify(e.message,true)),1200);return;}
 if(view==='task'&&currentTask?.id===taskId){await openTask(taskId);notify('AI建议已保存，请在本次评价记录中查看。');}else notify('AI建议已保存，回到对应作品即可查看。');}
document.addEventListener('click',async event=>{const b=event.target.closest('[data-action]');if(!b)return;const a=b.dataset.action;if(!['experience-select','self-ai-review','self-reflect','self-example'].includes(a))return;
 try{b.disabled=true;
  if(a==='experience-select'){if(recorder?.state==='recording')throw Error('先结束录音并保存，再切换学习模式。');await saveDraft();await experienceCall('experience.select',{experience:b.dataset.mode});await refreshStatus();await workspaceNavigate('home');notify('已切换学习模式，原有记录与配对保留。');}
  else if(a==='self-ai-review'){const task=currentTask,attempt=task.attempts.at(-1);const job=await api('/api/local/jobs',{mode:'self_review',task_id:task.id,submission_id:attempt.id});$('#self-ai-result').textContent='正在对照这次作品准备建议…';selfPoll(job.id,task.id).catch(e=>{notify(e.message,true);b.disabled=false;});}
  else if(a==='self-reflect'){const task=currentTask;modal('把这次收获留给下次自己',`<form id="experience-reflect-form" data-task="${h(task.id)}" data-submission="${h(task.attempts.at(-1).id)}" class="local-form"><label class="field">这次做到了什么、还卡在哪里<textarea name="comment" maxlength="4000" required></textarea></label><label class="field">下次具体试什么<input class="input" name="next_step" maxlength="1500" required></label><label class="checkline"><input name="schedule_review" type="checkbox" checked>安排个人复习（已有安排则沿用）</label><button class="btn accent" type="submit">保存反思和下一步</button></form>`);}
  else if(a==='self-example'){const m=(await studyCall('material.save',{title:'自学示例 · 给观点加一个理由',source:'超维成长自编示例，非考试真题',text:'A campus garden can help students relax. A short walk among plants gives them a quiet break between classes. Students can also care for the garden together and meet new friends.'})).data.material;
   const t=(await experienceCall('self.start',{source:{material_id:m.id,revision:m.revision,source_hash:m.source_hash},goal:'用原文中的一个理由，解释校园花园对学生的帮助',method:'apply',scenario:'general',minutes:10})).data;
   workspaceReturn='tasks';await openTask(t.task_id);history.pushState({task:t.task_id},'','/#task');notify('示例任务已建好，写下自己的解释后提交。');}
 }catch(e){notify(e.message,true);if(b.isConnected)b.disabled=false;}finally{if(b.isConnected&&a!=='self-ai-review')b.disabled=false;}
});
document.addEventListener('submit',async event=>{const f=event.target;if(f.id!=='experience-reflect-form')return;event.preventDefault();const button=f.querySelector('button');button.disabled=true;try{const p=Object.fromEntries(new FormData(f));p.schedule_review=f.elements.schedule_review.checked;p.task_id=f.dataset.task;p.submission_id=f.dataset.submission;await experienceCall('self.reflect',p);closeModal();await openTask(p.task_id);notify('反思已保存，可继续修订或按安排复习。');}catch(e){notify(e.message,true);}finally{button.disabled=false;}});
