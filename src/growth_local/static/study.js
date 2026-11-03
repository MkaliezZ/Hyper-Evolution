"use strict";
let studyMaterial=null,studyMethods={},studyPreview=null,studyBusy=false;
async function studyCall(operation,payload={},peer_id=null,request_id=uid()){
    return api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v2',request_id,operation,payload,peer_id});
}
function studyRef(){return studyMaterial.task_id?{task_id:studyMaterial.task_id}:{material_id:studyMaterial.id,revision:studyMaterial.revision,source_hash:studyMaterial.source_hash};}
function studySelection(){const t=$('#study-source-text');return {...studyRef(),start:t.selectionStart===t.selectionEnd?0:Array.from(t.value.slice(0,t.selectionStart)).length,end:t.selectionStart===t.selectionEnd?Array.from(t.value).length:Array.from(t.value.slice(0,t.selectionEnd)).length};}
async function studyHome(){
    view='materials';studyMaterial=null;const data=(await studyCall('material.list')).data;
    studyMethods=(await studyCall('study.options')).data.methods;
    shell(`<div class="local-top"><div><span class="eyebrow">LEARN FROM YOUR MATERIALS</span><h1>从一段资料，开始理解与表达。</h1><p>保存资料 → 阅读与提问 → 带着目标练习 → 对照依据修订。</p></div><button class="btn accent" data-action="study-add">＋ 添加资料</button></div><section class="card"><h2>我的本机资料</h2><p class="small muted">资料不会自动共享。教师布置任务时，仅发送所选片段。可添加文字、TXT、Markdown，或用“添加原图”保存 PNG / JPEG 页面。PDF / OCR 还未接入。</p>${data.materials.length?data.materials.map(m=>`<div class="local-task"><div><h3>${h(m.title)}</h3><p class="small muted">第 ${m.revision} 版 · 来源：${h(m.source)}</p></div><button class="btn ghost" data-action="study-read" data-id="${h(m.id)}">打开资料 →</button></div>`).join(''):'<div class="empty"><p>还没有资料。添加一段课文、讲义或自己的笔记即可开始。</p><button class="btn ghost" data-action="study-example">体验原创示例</button></div>'}</section><div id="study-reader"></div>`);
}
function studyAdd(){modal('添加本机资料',`<form id="study-material-form" class="local-form"><label class="field">资料标题<input class="input" name="title" maxlength="160" required></label><label class="field">来源 / 使用说明<input class="input" name="source" maxlength="500" required placeholder="例如：自己编写的讲义；某教材第几页，个人学习使用"></label><label class="file-button">从 TXT / Markdown 填入<input id="study-text-upload" type="file" accept=".txt,.md" hidden></label><label class="field">资料正文<textarea id="study-material-input" name="text" maxlength="60000" required></textarea></label><p class="small muted">保存表示原文已接入，不代表内容已核验。请填写你知道的来源，不要猜测。</p><button class="btn accent" type="submit">保存到本机</button></form>`);}
async function studyRead(source){
    const data=(await studyCall('material.read',source,status.profile.role==='teacher'?selectedPeer||null:null)).data;
    if(!$('#study-reader')){view='materials';shell('<div id="study-reader"></div>');}
    studyMaterial=data;
    $('#study-reader').innerHTML=`<section class="card"><button class="btn text" data-action="subject-return">← 返回资料列表</button><div class="section-head"><div><h2>${h(data.title)}</h2><p class="small muted">来源：${h(data.source)} · 第 ${data.revision} 版${data.superseded?' · 已有更新版本，本次仍查看此版本':''}</p></div>${!data.task_id?'<button class="btn ghost" data-action="study-edit">修订资料</button>':''}</div><label class="field">原文（可选中一段）<textarea id="study-source-text" readonly style="min-height:260px">${h(data.text)}</textarea></label><p class="small muted">选中片段后解释或练习；未选中时使用全文。长资料建议一次选取较小片段。</p><div class="actions"><button class="btn accent" data-action="study-practice">用这段资料学习</button><button class="btn ghost" data-action="study-ask">问一问所选原文</button></div><div id="study-explanation"></div></section>`;
    $('#study-reader').scrollIntoView({behavior:'smooth',block:'start'});
}
async function studyPractice(){
    if(!Object.keys(studyMethods).length)studyMethods=(await studyCall('study.options')).data.methods;
    const peers=status.peers.filter(p=>p.role==='student'&&p.state==='active');
    if(status.profile.role==='teacher'&&!peers.length)throw Error('先与一位学生配对，再布置任务；你仍可阅读和提问。');
    const source=studySelection();
    modal(status.profile.role==='teacher'?'设计并布置学习任务':'为自己设计本次学习',`<form id="study-activity-form" class="local-form">${status.profile.role==='teacher'?`<label class="field">布置给谁<select name="peer_id">${peers.map(p=>`<option value="${h(p.id)}" ${p.id===selectedPeer?'selected':''}>${h(p.name)}</option>`).join('')}</select></label>`:''}<label class="field">这次希望做到什么<input class="input" name="goal" maxlength="1000" required placeholder="例如：能区分作者的观点和支持依据"></label><label class="field">从什么方式开始<select id="study-method" name="method">${Object.entries(studyMethods).map(([id,m])=>`<option value="${id}">${h(m.name)}</option>`).join('')}</select></label><p id="study-method-reason" class="small muted">${h(studyMethods.understand.rationale)}</p><details id="study-design-details"><summary>补充问题与完成标准（选填）</summary><label class="field" data-targeted hidden>希望集中解决的困难（针对训练必填）<input class="input" name="obstacle" maxlength="1000" placeholder="不确定时可留空，先理解资料"></label><label class="field"><span id="study-question-label">本次问题或成果要求（选填）</span><textarea name="question" maxlength="2000" placeholder="留空时按所选方法提供起始任务。"></textarea></label><label class="field" data-targeted hidden>本次要练的操作（针对训练必填）<input class="input" name="target_operation" maxlength="1000" placeholder="例如：区分观点与观察依据；其他任务请写自己的操作"></label><label class="field">具体完成标准（针对训练必填，每行一项）<textarea name="criteria" placeholder="其他方法可留空，采用起始观察标准。"></textarea></label></details><p class="small muted">系统保留方法理由、评价标准和来源版本；不是默认出五道题，也不把完成记为掌握。</p><button class="btn accent" type="submit">${status.profile.role==='teacher'?'保存并布置':'创建学习任务'}</button></form>`);
    $('#study-activity-form').dataset.source=JSON.stringify(source);
}
function studyAsk(){
    if(!status.model.configured){settings();notify('请先配置你自己的模型 API，再使用原文解释。',true);return;}
    const source=studySelection();
    modal('围绕所选原文提问',`<form id="study-question-form" class="local-form"><label class="field">想弄清什么<textarea name="prompt" maxlength="2000" required placeholder="例如：作者的结论有哪些限制？哪些是原文明说的，哪些只是推断？"></textarea></label><p class="small muted">仅发送本次所选文字和问题到你配置的模型服务商。回复会核对引用文字，理解与解释质量仍需审阅。</p><button class="btn accent" type="submit">用我的 API 提问</button></form>`);
    $('#study-question-form').dataset.source=JSON.stringify(source);
}
async function studyPoll(id){
    const job=await api('/api/local/jobs/'+id);
    if(job.status==='failed')throw Error(job.error);
    if(job.status!=='completed'){setTimeout(()=>studyPoll(id).catch(e=>notify(e.message,true)),1200);return;}
    const out=job.result.output;const box=$('#study-explanation');if(!box){notify('资料解释已保存到本机助手记录');return;}
    box.innerHTML=`<hr><h3>围绕原文的解释</h3><p class="agent-output">${h(out.message)}</p>${out.citations.map(c=>`<blockquote>${h(c.quote)}<p class="small muted">原文位置 ${c.source_ref.start}—${c.source_ref.end} · 第 ${c.source_ref.revision} 版</p></blockquote>`).join('')}<p>${out.next_steps.map(h).join('；')}</p><p class="small muted">${h(out.boundary)}</p>`;
}
const studyOriginalShell=shell;
shell=function(html){
    studyOriginalShell(html);
    if(view==='guide'&&$('.local-guide')){
        const help=document.createElement('section');help.className='card';help.innerHTML='<h2>用自己的资料开始：四步就能体验</h2><ol><li>进入「资料与练习」，添加文字，或点击「体验原创示例」。</li><li>打开资料，可选取片段提问；解释使用你设置的模型 API。无需模型也能创建学习任务。</li><li>填写本次目标，选择理解、针对困难练习或应用表达。针对训练需补充操作、具体问题与完成标准。</li><li>提交作品并如实说明帮助条件；记录反思，或请老师按标准反馈，再修订。</li></ol><p>老师可在「题库与试听」预览 CSV / JSON，核对错误和重复后确认待审导入；音频题继续走资源 ZIP 和完整试听。</p><button class="btn ghost" data-action="materials">打开资料与练习 →</button>';
        $('.local-guide').prepend(help);
    }
    if(view==='resources'&&$('.local-top')){
        const button=document.createElement('button');button.className='btn accent';button.dataset.action='study-bank';button.textContent='表格题库导入';$('.local-top').append(button);
    }
    if(view==='task'&&currentTask&&$('.stimulus')){
        const task=currentTask;const panel=document.createElement('section');panel.className='card';panel.id='study-task-panel';$('.local-footer').before(panel);
        const plan=task.pack.companion_plan;
        if(plan&&!task.pack.academic){
            const introduction=document.createElement('section');introduction.className='card';
            introduction.innerHTML=`<h2>本次学习为什么这样安排</h2><p><strong>目标：</strong>${h(plan.goal)}</p><p><strong>${h(plan.name)}：</strong>${h(plan.rationale)}</p><p><strong>需要观察：</strong>${plan.criteria.map(h).join('；')}</p><p class="small muted">${h(plan.normal_conditions)} ${h(plan.verification)}</p><button class="btn text" data-action="study-task-read">打开本次资料 →</button>`;
            $('.stimulus').before(introduction);panel.innerHTML='<h2>评价与观察记录</h2><div id="study-ledger"></div>';
            const form=$('#work-form');
            if(form){const conditions=document.createElement('section');conditions.className='card';conditions.innerHTML='<h3>这次是怎样完成的</h3><label class="field">正常参与 / 工具（选填）<input class="input" name="study_normal" maxlength="800" placeholder="例如：查阅原文、向老师澄清题意"></label><label class="field">额外帮助（选填）<input class="input" name="study_help" maxlength="800" placeholder="例如：没有额外帮助；得到提示；参考了AI改写。不填则记未说明"></label><p class="small muted">这是你的说明，不会自动被认定为独立完成。</p>';form.querySelector('.sticky-submit').before(conditions);}
        }else panel.innerHTML='<h2>评价与观察记录</h2><div id="study-ledger"></div>';
        studyLoadLedger(task).catch(e=>{if($('#study-ledger'))$('#study-ledger').textContent=e.message;});
    }
    if(typeof workspaceEnhance==='function')workspaceEnhance();
    if(typeof continuityEnhance==='function')continuityEnhance().catch(e=>notify(e.message,true));
    if(typeof retrievalEnhance==='function')retrievalEnhance();
    if(typeof evolutionEnhance==='function')evolutionEnhance();
    if(typeof reviewEnhance==='function')reviewEnhance().catch(e=>notify(e.message,true));
};
async function studyLoadLedger(task){
    const data=(await studyCall('assessment.list',{task_id:task.id},status.profile.role==='teacher'?selectedPeer:null)).data;
    if(currentTask?.id!==task.id||!$('#study-ledger'))return;
    const last=task.attempts.at(-1);
    $('#study-ledger').innerHTML=`<h3>保留原答与每次评价</h3>${last&&status.profile.role!=='teacher'?`<button class="btn ghost" data-action="study-assess" ${task.state==='archived'?'disabled':''}>${status.profile.role==='teacher'?'按本次标准记录评阅':'记录我的反思与下一步'}</button>`:last?'<p class="small muted">通过上方“评阅最新作品”记录正式评阅；历史记录继续保留。</p>':'<p class="muted">提交作品后，可以记录评价与修订依据。</p>'}${data.entries.map(r=>`<article class="result-item"><strong>${h(({teacher_review:'教师评阅',self_report:'本人反思',model_suggestion:'模型建议'})[r.source_type])}</strong><p>${h(r.comment)}</p>${r.dimensions.map(d=>`<p class="small">${h(d.criterion)}：${h(d.observation)}${d.evidence?' · 引用：'+h(d.evidence):''}</p>`).join('')}<p>下一步：${h(r.next_step)}</p><span class="small muted">${h(new Date(r.created).toLocaleString('zh-CN'))} · ${h(({ungraded:'暂不判断达标',partial:'有部分证据',needs_revision:'需要修订',meets_criteria:'本次作品达标'})[r.outcome]||'待复核')} · 原答及来源版本已关联</span></article>`).join('')}<p class="small muted">旧评阅仍在原提交历史中。本人反思保存在本机；教师正式评阅随签名任务同步。</p>`;
}
function studyAssess(){
    const task=currentTask,last=task.attempts.at(-1),criteria=task.pack.companion_plan?.criteria||[];
    modal(status.profile.role==='teacher'?'依据作品逐项评阅':'我的学习反思',`<form id="study-assessment-form" class="local-form"><p class="small muted">本次评阅第 ${task.attempts.length} 次提交。结论仅针对这次作品。</p><details open><summary>对照本次作品</summary><p class="agent-output small">${h(last.answer?.text||'本次为逐题作答或附件作品，请先在任务页核对。')}</p></details>${criteria.map((c,i)=>`<label class="field">${h(c)}<input class="input" name="dimension_${i}" maxlength="1500" placeholder="观察到了什么？证据不足可说明暂不能判断。"></label><label class="field">该项依据（选填原答或原文中的原句）<input class="input" name="evidence_${i}" maxlength="1500"></label><label class="field">该项观察状态<select name="status_${i}"><option value="ungraded">暂不能判断</option><option value="supported">已有支持证据</option><option value="partial">有部分证据</option><option value="needs_revision">需要修订</option></select></label>`).join('')}<label class="field">具体反馈 / 反思<textarea name="comment" maxlength="4000" required></textarea></label><label class="field">下一步<input class="input" name="next_step" maxlength="2000" required></label><label class="field">本次结论<select name="outcome"><option value="ungraded">暂不判断达标</option><option value="partial">有部分证据，仍需补充</option><option value="needs_revision">需要修订</option>${status.profile.role==='teacher'?'<option value="meets_criteria">教师确认本次作品达标</option>':''}</select></label>${status.profile.role==='teacher'?'<label class="checkline"><input type="checkbox" name="human_review_confirmed" required>我已亲自查看作品及本次评价依据</label>':''}<button class="btn accent" type="submit">保存本次记录</button></form>`);
    $('#study-assessment-form').dataset.task=task.id;$('#study-assessment-form').dataset.submission=last.id;
}
function studyBank(){studyPreview=null;modal('题库导入：先预览，再确认',`<p>支持 CSV 或 JSON 题包数组。仅接受现有托福 / 雅思题型，音频题继续使用原资源 ZIP 配套导入。</p><form id="study-bank-form" class="local-form"><label class="file-button">选择 CSV / JSON<input id="study-bank-upload" type="file" accept=".csv,.json" hidden></label><label class="field">格式<select name="format" id="study-bank-format"><option value="csv">CSV</option><option value="json">JSON 题包数组</option></select></label><label class="field">文件内容<textarea name="content" id="study-bank-input" maxlength="400000" required></textarea></label><p class="small muted">CSV 列：title, stimulus, exam, task_type, kind, prompt, options, answer, evidence, explanation, skill, source_title。选项用 | 分隔。<br>exam 用 ielts / toefl；支持的题型以原题库校验为准。所有导入内容仍待教师审校。</p><button class="btn ghost" type="button" data-action="study-bank-template">下载 CSV 示例</button><button class="btn accent" type="submit">解析并预览</button></form><div id="study-bank-preview"></div>`);}
document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-action]');if(!button)return;
    try{switch(button.dataset.action){
        case 'materials':await studyHome();break;
        case 'study-add':studyAdd();break;
        case 'study-example':await subjectSaveExample();await studyHome();break;
        case 'study-read':await studyRead({material_id:button.dataset.id});break;
        case 'study-edit':studyAdd();$('#study-material-form').dataset.id=studyMaterial.id;$('#study-material-form').dataset.revision=studyMaterial.revision;$('#study-material-form').elements.title.value=studyMaterial.title;$('#study-material-form').elements.source.value=studyMaterial.source;$('#study-material-input').value=studyMaterial.text;$('#study-material-form').elements.classification_revision.value=studyMaterial.classification?.revision||0;if(studyMaterial.classification?.subject)$('#study-material-form').elements.subject.value=studyMaterial.classification.subject;break;
        case 'study-practice':await studyPractice();break;
        case 'study-ask':studyAsk();break;
        case 'study-task-read':await studyRead({task_id:currentTask.id});break;
        case 'study-assess':studyAssess();break;
        case 'study-bank':studyBank();break;
        case 'study-bank-confirm':if(!studyPreview)throw Error('请先生成有效预览');button.disabled=true;const result=await studyCall('bank.commit',{preview_id:studyPreview.id,preview_hash:studyPreview.preview_hash});closeModal();await resources();notify(`已保存 ${result.data.imported.length} 包待审题；跳过 ${result.data.skipped_existing.length} 包已有题目。`);break;
        case 'study-bank-template':{const csv='title,stimulus,exam,task_type,kind,prompt,options,answer,evidence,explanation,skill,source_title\nDemo notice,The workshop starts at ten.,toefl,daily_life,mcq,When does it start?,At ten|At noon,A,starts at ten,原文说明十点开始,detail,原创演示\n';const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='题库导入示例.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);break;}
    }}catch(e){notify(e.message,true);button.disabled=false;}
});
document.addEventListener('change',async event=>{try{
    if(['study-text-upload','study-bank-upload'].includes(event.target.id)){
        const f=event.target.files[0];if(!f)return;if(f.size>400000)throw Error('文件请控制在400KB以内，较大资料请拆分。');const text=await f.text();
        if(event.target.id==='study-text-upload')$('#study-material-input').value=text;else{$('#study-bank-input').value=text;$('#study-bank-format').value=f.name.endsWith('.json')?'json':'csv';}
    }else if(event.target.id==='study-method'){
        $('#study-method-reason').textContent=studyMethods[event.target.value].rationale;
        const targeted=event.target.value==='targeted';$('#study-question-label').textContent=targeted?'本次问题或成果要求（必填）':'本次问题或成果要求（选填）';
        document.querySelectorAll('[data-targeted]').forEach(el=>el.hidden=!targeted);
        const details=$('#study-design-details');details.open=targeted;details.querySelector('summary').textContent=targeted?'针对训练：补齐困难、操作、问题与标准':'补充问题与完成标准（选填）';
        ['obstacle','target_operation','question','criteria'].forEach(name=>$('#study-activity-form').elements[name].required=targeted);
    }
}catch(e){notify(e.message,true);}});
document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.id.startsWith('study-'))return;event.preventDefault();if(studyBusy)return;studyBusy=true;const button=form.querySelector('button[type="submit"]');button.disabled=true;
    if(!form.dataset.request)form.dataset.request=uid();const request=form.dataset.request;
    try{
        const obj=Object.fromEntries(new FormData(form));
        if(form.id==='study-material-form'){
            if(form.dataset.id){obj.material_id=form.dataset.id;obj.expected_revision=Number(form.dataset.revision);}
            await studyCall('material.save',obj,null,request);await subjectAfterSave(obj.subject);closeModal();await studyHome();notify('资料已保存在本机。');
        }else if(form.id==='study-activity-form'){
            const peer=obj.peer_id||null;delete obj.peer_id;obj.criteria=(obj.criteria||'').split('\n').map(c=>c.trim()).filter(Boolean);const result=await studyCall('activity.create',{...JSON.parse(form.dataset.source),...obj},peer,request);closeModal();if(status.profile.role==='teacher')selectedPeer=peer;workspaceReturn=status.profile.role==='teacher'?'review':'tasks';await openTask(result.data.task_id);history.pushState({task:result.data.task_id,peer:selectedPeer},'','/#task');notify('已保存本次目标、方法与资料版本。');
        }else if(form.id==='study-question-form'){
            const job=await api('/api/local/jobs',{mode:'reading',source:JSON.parse(form.dataset.source),prompt:obj.prompt,peer_id:status.profile.role==='teacher'?selectedPeer:null});closeModal();$('#study-explanation').textContent='正在读取所选原文并解释…';await studyPoll(job.id);
        }else if(form.id==='study-assessment-form'){
            const criteria=currentTask.pack.companion_plan?.criteria||[];const dimensions=criteria.flatMap((criterion,i)=>obj['dimension_'+i]?.trim()?[{criterion,observation:obj['dimension_'+i],evidence:obj['evidence_'+i]||'',status:obj['status_'+i]||'ungraded'}]:[]);
            await studyCall('assessment.record',{task_id:form.dataset.task,submission_id:form.dataset.submission,source_type:status.profile.role==='teacher'?'teacher_review':'self_report',comment:obj.comment,next_step:obj.next_step,outcome:obj.outcome,dimensions,human_review_confirmed:form.elements.human_review_confirmed?.checked===true},status.profile.role==='teacher'?selectedPeer:null,request);closeModal();await openTask(currentTask.id);notify('本次记录已保存，原答与旧反馈继续保留。');
        }else if(form.id==='study-bank-form'){
            const data=(await studyCall('bank.preview',obj,null,request)).data;studyPreview=data;
            $('#study-bank-preview').innerHTML=`<hr><h3>导入预览</h3><p>${data.packs.length} 个有效题包；文件内重复 ${data.duplicates_in_file} 个；本机已有 ${data.already_present} 个。</p>${data.packs.map(p=>`<p>${h(p.title)} · ${h(p.exam)} · ${p.items} 题</p>`).join('')}${data.errors.map(e=>`<p class="muted">第 ${e.row} 行 / 包：${h(e.message)}</p>`).join('')}<p class="small muted">确认只会保存为待审，不会自动布置或放行。</p><button class="btn accent" data-action="study-bank-confirm" ${data.errors.length?'disabled':''}>确认保存待审题库</button>`;
        }
    }catch(e){delete form.dataset.request;notify(e.message,true);}finally{studyBusy=false;button.disabled=false;}
});
document.addEventListener('input',event=>{const form=event.target.closest('form[id^="study-"]');if(form)delete form.dataset.request;});
