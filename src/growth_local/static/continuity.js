"use strict";
let continuityBusy=false,continuityCatalog=null,continuityPage=null,continuityDraft=null,continuityMemories=[],continuityCards=[];
const c3=(operation,payload={},peer_id=null,request_id=uid())=>api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v3',request_id,operation,payload,peer_id});
async function c3Catalog(){if(!continuityCatalog)continuityCatalog=(await c3('policy.catalog')).data;return continuityCatalog;}
function c3Peer(){return workspaceTeacher()?selectedPeer||null:null;}
function c3TaskSource(source){return {task_id:source.task_id,revision:source.revision,source_hash:source.source_hash,...(source.region?{region:source.region}:{})};}
function c3Source(){return {...continuityPage.source_ref,...(continuityPage.source_ref.task_id?{}:{page_id:continuityPage.id})};}
function c3ImageURL(source){return '/api/local/pages/image?'+new URLSearchParams({...source,...(workspaceTeacher()&&selectedPeer?{peer_id:selectedPeer}:{})}).toString();}
function c3Decisions(plan){return `<p><strong>${h(plan.name)}</strong> · ${h(plan.operation)}</p><p class="small muted">${h(plan.rationale)} ${h(plan.form_reason)}</p><ul>${plan.criteria.map(c=>`<li>${h(c)}</li>`).join('')}</ul><details><summary>查看采用的规则、理由和待补项</summary>${plan.decisions.map(d=>`<article class="result-item"><strong>${h(d.pack)} · ${h(({pass:'运行条件已检查',needs_review:'需要审阅',needs_input:'需要补充',blocked:'不能采用'})[d.status])}</strong><p>${h(d.decision)}</p><p class="small muted">${h(d.rationale)}</p><p class="small muted">规则：${h(d.instruction)}</p></article>`).join('')}<p class="small muted">冻结规则版本和来源。检查通过不等于专业审定或学习效果已经验证。</p></details>`;}
async function continuityPolicy(){
    const data=await c3Catalog();view='policy';
    shell(`${workspaceHeading('DESIGN / 学习设计','先判断怎样学，再调用工具。','目标、已有表现、材料、方法、帮助和评价依据共同决定一次学习的安排。规则可以检查执行条件，专业内容仍需审阅。')}
        <section class="card"><h2>让规则参与一份真实任务</h2><p>打开自己的文字或原图，点击“设计本次学习”，选择希望做到什么、采用什么方法。系统先预览选择理由和缺项，再保存活动。</p><button class="btn accent" data-action="ws-route" data-route="materials">选择资料开始 →</button> <button class="btn ghost" data-action="ws-route" data-route="policy-lab">案例、反例与验收 →</button></section>
        <div class="workspace-action-grid">${data.packs.map(p=>`<section class="card"><span class="eyebrow">${h(p.design_index)}</span><h3>${h(p.name)}</h3><p>${h(p.judgement_question)}</p><p class="small muted">${h(p.rules[0].decision)}</p><details><summary>规则与好坏例</summary>${p.rules.map(r=>`<p><strong>${h(r.rule_id)}</strong> ${h(r.decision)}</p>`).join('')}<p>适当做法：${h(p.examples.good)}</p><p>反例：${h(p.examples.bad)}</p><p class="small muted">版本 ${h(p.version)} · 已装入运行时；专业质量未审定</p></details></section>`).join('')}</div>`);
}
async function c3Design(source){
    const data=await c3Catalog();continuityDraft=null;
    const peers=status.peers.filter(p=>p.role==='student'&&p.state==='active');
    if(workspaceTeacher()&&!peers.length){notify('先连接学生，才能布置；资料和规则可以先查看。',true);return;}
    modal(workspaceTeacher()?'设计并布置本次学习':'设计本次学习',`<form id="continuity-design-form" class="local-form" data-source="${h(JSON.stringify(source))}">${workspaceTeacher()?`<label class="field">布置给谁<select name="peer_id">${peers.map(p=>`<option value="${h(p.id)}" ${p.id===selectedPeer?'selected':''}>${h(p.name)}</option>`).join('')}</select></label>`:''}
        <label class="field">这次希望做到什么<input class="input" name="goal" required maxlength="1000" placeholder="写一个可以观察的小目标"></label>
        <div class="inline-grid"><label class="field">学习情境<select name="scenario" id="continuity-scenario">${Object.entries(data.scenarios).map(([id,s])=>`<option value="${id}" ${id===(source.page_id||(source.task_id&&continuityPage?.source_ref.task_id===source.task_id)?'visual_reading':'general')?'selected':''}>${h(s.name)}</option>`).join('')}</select></label><label class="field">从什么方式开始<select name="method" id="continuity-method">${Object.entries(data.methods).map(([id,m])=>`<option value="${id}">${h(m.name)}</option>`).join('')}</select></label></div>
        <p class="small muted" id="continuity-method-reason">${h(data.methods.understand.rationale)}</p>
        <details id="continuity-design-detail"><summary>调整操作、问题、帮助和标准</summary>
        <label class="field" data-c3-targeted hidden>困难假设（候选，不是自动诊断）<input class="input" name="obstacle" maxlength="1000"></label>
        <label class="field" data-c3-targeted hidden>本次要练的关键操作<input class="input" name="target_operation" maxlength="1000"></label>
        <label class="field">具体问题或成果要求<textarea name="question" maxlength="2000" placeholder="理解、探究或应用可留空，先查看系统给出的候选安排"></textarea></label>
        <label class="field">完成标准（每行一项）<textarea name="criteria" placeholder="可采用情境的起始标准；针对训练须明确填写"></textarea></label>
        <label class="field">活动形式（可选）<input class="input" name="form" maxlength="100" placeholder="留空按情境建议，例如连线只是一种可选形式"></label><label class="field">为什么更换形式<input class="input" name="form_reason" maxlength="1000" placeholder="形式改变时，说明怎样让目标操作可观察"></label>
        <label class="field">正常参与方式与工具<input class="input" name="normal_conditions" maxlength="1000" placeholder="例如可查原文、可向伙伴澄清；并不要求独自完成"></label>
        <label class="field">本人需要承担什么<input class="input" name="learner_responsibility" maxlength="1000"></label></details>
        <label class="field">本次预计分钟数<input class="input" type="number" name="minutes" min="2" max="120" value="10"></label>
        <p class="small muted">先检查目标、材料和方法是否一致，再决定是否创建。规则给出的候选内容需要结合真实情况判断。</p><button class="btn accent" type="submit">预览本次安排 →</button></form><div id="continuity-design-preview"></div>`);
}
async function c3Pages(){
    if(view!=='materials'||!$('#study-reader'))return;
    const data=(await c3('page.list')).data;if(view!=='materials'||!$('#study-reader'))return;
    if(!data.pages.length)return;
    const box=document.createElement('section');box.className='card';box.id='continuity-pages';
    box.innerHTML=`<h2>我的原图资料</h2><p class="small muted">保留原始像素和版本。支持单页 PNG / JPEG；PDF / OCR 尚未接入。</p>${data.pages.map(p=>`<div class="local-task"><div><h3>${h(p.title)}</h3><p class="small muted">第 ${p.revision} 版 · ${p.width} × ${p.height} · ${h(p.source)}</p></div><button class="btn ghost" data-action="c3-open-page" data-source="${h(JSON.stringify({page_id:p.id,revision:p.revision}))}">打开原图 →</button></div>`).join('')}`;
    $('#continuity-pages')?.remove();$('#study-reader').before(box);
}
function c3AddPage(){modal('添加一张原始页面',`<form id="continuity-page-form" class="local-form"><label class="field">原图标题<input name="title" class="input" maxlength="160" required></label><label class="field">来源 / 使用说明<input name="source" class="input" maxlength="500" required></label><label class="field">选择 PNG / JPEG 原图<input id="continuity-page-file" type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" required></label><label class="field">附注（选填，不作为核验转写）<textarea name="caption" maxlength="3000"></textarea></label><p class="small muted">单图不超过 2MB、1200万像素。保存时不改动原始字节；需要模型解释时，会发送整张原图及关注区域到你选择的模型服务商。</p><button class="btn accent" type="submit">保存原图到本机</button></form>`);}
async function c3OpenPage(source){
    const data=(await c3('page.read',{...source,include_image:false},c3Peer())).data;continuityPage=data;
    if(!$('#study-reader')){view='materials';shell('<div id="study-reader"></div>');}
    $('#study-reader').innerHTML=`<section class="card"><button class="btn text" data-action="subject-return">← 返回资料列表</button><h2>${h(data.title)}</h2><p class="small muted">${h(data.source)} · 第 ${data.revision} 版 · 原图字节已校验</p><img class="continuity-original" src="${h(c3ImageURL(data.source_ref))}" alt="${h(data.title)}的原始页面"><p class="small muted">${h(data.caption||'无附注。')} 附注是用户提供的说明，不是OCR或专业核验结果。</p><details><summary>设置关注区域（可选，默认整页）</summary><p class="small muted">按显示图片的宽高比例填写左、上、右、下；0 是起点，1 是终点。发送模型时仍发送整张原图，并标注该关注范围。</p><div class="inline-grid">${['左','上','右','下'].map((x,i)=>`<label class="field">${x}<input class="input" type="number" min="0" max="1" step="0.05" data-c3-region="${i}" value="${i<2?0:1}"></label>`).join('')}</div></details><div class="actions"><button class="btn accent" data-action="c3-image-design">用原图设计学习</button><button class="btn ghost" data-action="c3-image-ask">围绕原图提问</button></div><div id="continuity-explanation"></div></section>`;
    $('#study-reader').scrollIntoView({behavior:'smooth',block:'start'});
}
function c3ImageSource(){const region=Array.from(document.querySelectorAll('[data-c3-region]')).map(el=>Number(el.value));return {...c3Source(),region:region.length===4?region:[0,0,1,1]};}
function c3Ask(){
    if(!status.model.configured||!status.model.vision_model){modal('先选择自己的原图模型',`<p>原图需要支持图片输入的模型，文字模型不能替代。你现在的主模型配置保留。</p><button class="btn accent" data-action="c3-go-model">设置原图模型</button>`);return;}
    modal('围绕原图提问',`<form id="continuity-vision-form" class="local-form" data-source="${h(JSON.stringify(c3ImageSource()))}"><label class="field">想弄清什么<textarea name="prompt" required maxlength="2000" placeholder="例如：图里支持了什么结论？哪些内容看不清或不能判断？"></textarea></label><p class="small muted">使用你的 ${h(status.model.vision_model)} 和自有 API。发送整张原图与关注范围；回复区分观察、推断与未知。</p><button class="btn accent" type="submit">用我的模型读取原图</button></form>`);
}
function c3VisualOutput(result){const out=result.output;return `<h3>围绕原图的解释</h3><p class="agent-output">${h(out.message)}</p>${out.observations.map(o=>`<blockquote>${h(o.description)}<p class="small muted">第 ${o.source_ref.revision} 版 · 图区 ${o.region.join(' / ')}</p></blockquote>`).join('')}<p>仍不能确定：${out.unknown.map(h).join('；')||'模型未列出；仍需审阅其解释。'}</p><p>下一步：${out.next_steps.map(h).join('；')}</p><p class="small muted">${h(out.boundary)}</p>`;}
async function c3Poll(id){const job=await api('/api/local/jobs/'+id);if(job.status==='failed')throw Error(job.error);if(job.status!=='completed'){setTimeout(()=>c3Poll(id).catch(e=>notify(e.message,true)),1200);return;}if($('#continuity-explanation'))$('#continuity-explanation').innerHTML=c3VisualOutput(job.result);else notify('原图解释已保存在学习助手任务记录中。');}
function c3PeerSelect(){return workspaceTeacher()?`<label class="field">查看哪位学生的教学札记<select id="continuity-peer">${status.peers.filter(p=>p.role==='student'&&p.state==='active').map(p=>`<option value="${h(p.id)}" ${p.id===selectedPeer?'selected':''}>${h(p.name)}</option>`).join('')}</select></label>`:'';}
function c3RememberRoute(route){history.pushState({route},'','/#'+route);window.scrollTo({top:0,behavior:'instant'});workspaceFocusHeading();}
async function continuityMemory(includeHidden=false){
    await workspaceLoad();view='memory';
    if(workspaceTeacher()&&!selectedPeer){shell(`${workspaceHeading('NOTES / 学习札记','先选择一位已配对学生。','教学札记按学生分别保存，不会混入其他人的资料。')}<button class="btn ghost" data-action="ws-route" data-route="students">查看学生档案 →</button>`);return;}
    const data=(await c3('memory.list',{include_hidden:includeHidden},c3Peer())).data;continuityMemories=data.entries;
    shell(`${workspaceHeading('NOTES / 学习札记','把经历留下来，也保留原始依据。','从任务中保存作品和反馈的有界摘录。札记可以修订、暂不使用；来源更新或解除配对后，不再自动作为当前模型依据。')}
        <section class="card">${c3PeerSelect()}<label class="checkline"><input type="checkbox" id="continuity-show-hidden" ${includeHidden?'checked':''}>显示暂不使用的札记</label>${data.entries.length?data.entries.map(m=>`<article class="result-item"><span class="status-pill">${m.hidden?'暂不使用':m.current?'依据当前有效':'依据有更新，待刷新'}</span><h3>${h(m.title)}</h3><p class="agent-output">${h(m.body)}</p><p class="small muted">第 ${m.revision} 版 · ${m.authorship==='bounded_source_extract'?'原始记录的有界摘录':'用户手动修订'} · ${m.allow_for_model&&!m.hidden&&m.current?'可供自己的模型参考':'不进入模型上下文'}</p><div class="actions"><button class="btn ghost small" data-action="ws-task" data-id="${h(m.source_refs[0].task_id)}" data-peer="${h(c3Peer()||'')}">回看作品依据 →</button><button class="btn ghost small" data-action="c3-edit-memory" data-id="${h(m.id)}">修订札记</button><button class="btn text small" data-action="c3-toggle-memory" data-id="${h(m.id)}">${m.hidden?'恢复使用':'暂不使用'}</button></div></article>`).join(''):workspaceEmpty('还没有学习札记','打开一份已经提交过的任务，点击“保存学习札记”。',`<button class="btn ghost" data-action="ws-route" data-route="${workspaceTeacher()?'review':'tasks'}">查看学习任务 →</button>`)}</section>`);
}
async function c3Capture(){
    modal('保存本次学习札记',`<form id="continuity-memory-form" class="local-form"><label class="field">札记标题<input class="input" name="title" maxlength="120" value="${h(currentTask.pack.title.slice(0,120))}" required></label><p>从本次已提交作品、可见反馈及帮助条件生成短摘录，保留来源引用。不会提取教师私注或其他人的资料。</p><p class="small muted">依据仍有效时可供自己的模型参考；不自动分享给师生或公共方法库，也不推断掌握。</p><button class="btn accent" type="submit">保存到本机札记</button></form>`);
}
async function continuityReviews(){
    const data=(await c3('review.list',{include_paused:true})).data;continuityCards=data.cards;view='reviews';
    shell(`${workspaceHeading('RECALL / 我的复习','安排下一次回忆，也允许调整。','先尝试回忆或再用，再核对原任务。间隔来自你选择的参数和本人声明，不是精确记忆曲线或教师达标判断。')}
        <section class="card">${data.cards.length?data.cards.map(c=>`<article class="result-item"><span class="status-pill">${c.paused?'已暂停':c.task_state!=='active'?'原任务已暂停 / 归档':c.due?'现在可复习':'已安排'}</span><h3>${h(c.title)}</h3><p>${h(c.prompt)}</p><p class="small muted">下次：${h(new Date(c.due_at).toLocaleString('zh-CN'))} · 可调间隔：${c.intervals.join(' / ')} 天${c.source_current?'':' · 原任务已有新记录，作答后会更新依据'}</p><div class="actions">${!c.paused&&c.task_state==='active'?`<button class="btn accent small" data-action="c3-recall" data-id="${h(c.id)}">开始回忆</button>`:''}<button class="btn ghost small" data-action="c3-adjust-review" data-id="${h(c.id)}">改期或暂停</button><button class="btn text small" data-action="ws-task" data-id="${h(c.task_id)}">打开原任务 →</button></div>${c.recent_events?.length?`<details><summary>最近复习与调整记录</summary>${c.recent_events.map(e=>`<p class="small">${h(new Date(e.created).toLocaleString('zh-CN'))} · ${h(e.detail.response||'调整安排')} ${h(({again:'想不起来',hard:'费力完成',good:'能够回忆'})[e.detail.rating]||'')}</p>`).join('')}</details>`:''}</article>`).join(''):workspaceEmpty('先从一份已完成的作品安排复习','打开学习任务，点击“安排个人复习”，再选适合自己的间隔。','<button class="btn ghost" data-action="ws-route" data-route="tasks">打开我的任务 →</button>')}</section>`);
}
function c3Schedule(){modal('安排个人复习',`<form id="continuity-schedule-form" class="local-form"><label class="field">复习时希望自己做到什么<textarea name="prompt" maxlength="1500" placeholder="例如：先不看旧答案，用新的例子说明概念的边界"></textarea></label><label class="field">间隔天数（用逗号分隔，可修改）<input class="input" name="intervals" value="1,3,7,14" required></label><p class="small muted">这是可调的起始安排，不是对你的记忆能力测量。复习回答只保存在自己的本机；需要老师评阅时，在原任务中提交。</p><button class="btn accent" type="submit">保存复习安排</button></form>`);}
async function c3Recall(id){
    const card=continuityCards.find(c=>c.id===id),task=await api('/api/local/tasks/'+card.task_id),a=task.attempts.find(a=>a.id===card.source_ref.submission_id);
    const saved=localStorage.getItem('growth-recall:'+card.id)||'';
    modal('先回忆，再核对',`<form id="continuity-recall-form" class="local-form" data-id="${h(card.id)}" data-revision="${card.revision}"><p>${h(card.prompt)}</p><label class="field">我的这次回忆 / 再用<textarea name="response" maxlength="4000" required>${h(saved)}</textarea></label><details><summary>需要时查看原答与当时反馈</summary><p class="agent-output">${h(a?.answer?.text||'逐题作答或附件作品，请回原任务查看。')}</p><p>${h(a?.evaluation?.comment||'暂无反馈')}</p></details><label class="field">这次回忆感觉怎样（本人声明）<select name="rating"><option value="again">想不起来，需要重新学习</option><option value="hard">费力完成，还需要核对</option><option value="good">能够回忆，仍需按任务标准核对</option></select></label><label class="field">额外帮助（如实填写）<input class="input" name="additional_help" maxlength="800" placeholder="例如：没有额外帮助；看过示范；得到提示。不填记未说明"></label><p class="small muted">文字草稿暂存此浏览器，记录后进入本机学习库。选择“能够回忆”不会自动被当作答案正确或掌握。</p><button class="btn accent" type="submit">记录本次并调整下一次</button></form>`);
}
function c3Adjust(id){const c=continuityCards.find(x=>x.id===id);modal('调整自己的复习安排',`<form id="continuity-adjust-form" data-id="${h(c.id)}" data-revision="${c.revision}" class="local-form"><label class="field">改为几天后（留空不改日期）<input class="input" type="number" min="0" max="90" name="days_from_now" placeholder="0 表示今天"></label><label class="checkline"><input type="checkbox" name="paused" ${c.paused?'checked':''}>暂停这张复习卡</label><button class="btn accent" type="submit">保存调整</button></form>`);}
async function continuityEnhance(){
    if(view==='guide'&&$('.local-guide')){
        const help=document.createElement('section');help.className='card';help.innerHTML=`<h2>从一次学习到下一次安排</h2><ol><li>在“我的资料库”添加文字，或用“添加原图”保存 PNG / JPEG。</li><li>打开资料，选择“用这段资料学习”或“用原图设计学习”。理解、探究、针对练习、应用、复习和复盘都可作为起点。</li><li>写一个可观察的小目标，预览选择理由和标准。针对练习还需说明困难假设与关键操作；缺必要声音或原图时不能发布。</li><li>完成并提交作品后，对照本次标准记录具体反馈。自动核对和模型解释不能代替教师正式判断。</li><li>在任务中保存“学习札记”，可回查作品、修订或暂不采用。来源变化后旧札记不再进入模型上下文。</li>${workspaceTeacher()?'<li>教学札记按所选学生分开保存在教师本机；学生的个人复习由学生自己安排。</li>':'<li>在任务中安排个人复习：先回忆再核对，如实记录额外帮助，按需要改期或暂停。查看“我的复习”即可继续，不会自动通知或代交作业。</li>'}</ol><p class="small muted">普通原图查看无需模型。原图提问需在设置中另填支持图片的模型名称，使用自己的 Key；图片会发给所选服务商。</p><button class="btn accent" data-action="ws-route" data-route="materials">从资料开始 →</button></section>`;$('.local-guide').querySelector('.card').before(help);
    }
    if(view==='materials'&&!subjectReadOnly()&&$('.local-top')){
        const b=document.createElement('button');b.className='btn ghost';b.textContent='＋ 添加原图';b.dataset.action='c3-add-page';($('.subject-library-actions')||$('.local-top')).append(b);c3Pages().catch(e=>notify(e.message,true));
    }
    if(view==='task'&&currentTask){
        const task=currentTask;
        if(task.pack.source_page){
            const image=document.createElement('section');image.className='card';image.innerHTML=`<h2>本次原始页面</h2><img class="continuity-original" src="${h(c3ImageURL({task_id:task.id}))}" alt="本次任务绑定的原图"><button class="btn ghost" data-action="c3-open-page" data-source="${h(JSON.stringify({task_id:task.id}))}">打开原图阅读 →</button>`;$('.stimulus')?.before(image);
            const b=$('[data-action="study-task-read"]');if(b){b.dataset.action='c3-open-page';b.dataset.source=JSON.stringify({task_id:task.id});b.textContent='打开本次原图 →';}
        }
        const plan=task.pack.companion_plan?.runtime_policy;
        if(plan){const details=document.createElement('details');details.className='card';details.innerHTML=`<summary>这次采用了哪些专业判断规则</summary>${c3Decisions(plan)}`;$('#study-task-panel')?.before(details);}
        if(task.attempts.length){const tools=document.createElement('div');tools.className='actions continuity-task-tools';tools.innerHTML='<button class="btn ghost small" data-action="c3-capture">保存学习札记</button>'+(!workspaceTeacher()?'<button class="btn ghost small" data-action="c3-schedule">安排个人复习</button>':'');$('.workspace-task-next')?.append(tools);}
    }
    if(view==='settings'&&continuityPage){const b=document.createElement('button');b.className='btn text';b.dataset.action='c3-return-page';b.textContent='← 返回刚才的原图';$('.local-settings')?.prepend(b);}
}
document.addEventListener('click',async event=>{
    const b=event.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;
    if(action==='study-practice'){event.preventDefault();event.stopImmediatePropagation();try{await c3Design(studySelection());}catch(e){notify(e.message,true);}return;}
    if(!action.startsWith('c3-'))return;event.preventDefault();event.stopImmediatePropagation();
    if(continuityBusy||sending||studyBusy)return;
    try{
        if(action==='c3-add-page')c3AddPage();
        else if(action==='c3-open-page')await c3OpenPage(JSON.parse(b.dataset.source));
        else if(action==='c3-image-design')await c3Design(c3ImageSource());
        else if(action==='c3-image-ask')c3Ask();
        else if(action==='c3-go-model'){closeModal();await workspaceNavigate('settings');}
        else if(action==='c3-return-page')await c3OpenPage(c3Source());
        else if(action==='c3-publish'){
            if(!continuityDraft)throw Error('请先预览本次安排');continuityBusy=true;b.disabled=true;
            const f=$('#continuity-design-form');if(!f.dataset.request)f.dataset.request=uid();
            const result=await c3('activity.create',continuityDraft.payload,continuityDraft.peer,f.dataset.request);
            closeModal();if(continuityDraft.peer)selectedPeer=continuityDraft.peer;workspaceReturn=workspaceTeacher()?'review':'tasks';await openTask(result.data.task_id);history.pushState({task:result.data.task_id,peer:selectedPeer},'','/#task');notify('已保存场景、规则决定、标准和来源版本。');
        }else if(action==='c3-capture')await c3Capture();
        else if(action==='c3-edit-memory'){
            const m=continuityMemories.find(x=>x.id===b.dataset.id);modal('修订学习札记',`<form id="continuity-correct-form" data-id="${h(m.id)}" data-revision="${m.revision}" class="local-form"><label class="field">修订后的札记<textarea name="body" maxlength="3000" required>${h(m.body)}</textarea></label><label class="checkline"><input type="checkbox" name="allow_for_model">允许这条手动修订用于我自己的模型建议</label><p class="small muted">保留旧版本和原始依据。修订不改变教师反馈或证明掌握。</p><button class="btn accent" type="submit">保存新版本</button></form>`);
        }else if(action==='c3-toggle-memory'){const m=continuityMemories.find(x=>x.id===b.dataset.id);await c3('memory.visibility',{memory_id:m.id,hidden:!m.hidden},c3Peer());await continuityMemory(true);}
        else if(action==='c3-schedule')c3Schedule();
        else if(action==='c3-recall')await c3Recall(b.dataset.id);
        else if(action==='c3-adjust-review')c3Adjust(b.dataset.id);
    }catch(e){notify(e.message,true);b.disabled=false;}finally{continuityBusy=false;}
},true);
document.addEventListener('submit',async event=>{
    const f=event.target;if(!f.id.startsWith('continuity-'))return;event.preventDefault();if(continuityBusy)return;continuityBusy=true;
    const b=f.querySelector('[type="submit"]');if(b)b.disabled=true;
    try{
        const obj=Object.fromEntries(new FormData(f));if(!f.dataset.request)f.dataset.request=uid();
        if(f.id==='continuity-page-form'){
            const file=$('#continuity-page-file').files[0];if(!file||file.size>2*1024*1024)throw Error('请选择2MB以内的 PNG / JPEG 原图');
            const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(const chunk of bytes)binary+=String.fromCharCode(chunk);
            delete obj.file;await c7('academic.page.save',{title:obj.title,source:obj.source,caption:obj.caption,data_base64:btoa(binary),subject:obj.subject,classification_revision:Number(obj.classification_revision||0)},null,f.dataset.request);await subjectAfterSave(obj.subject);closeModal();await studyHome();notify('原图已保存到本机，未改动原始字节。');
        }else if(f.id==='continuity-design-form'){
            const peer=obj.peer_id||null;delete obj.peer_id;obj.criteria=obj.criteria.split('\n').map(x=>x.trim()).filter(Boolean);obj.minutes=Number(obj.minutes);
            const payload={source:JSON.parse(f.dataset.source),...obj};const result=await c3('policy.plan',payload,peer);continuityDraft={payload,peer,plan:result.data.plan};
            $('#continuity-design-preview').innerHTML='<hr><h3>本次安排预览</h3>'+c3Decisions(result.data.plan)+`<button class="btn accent" data-action="c3-publish" ${['blocked','needs_input'].includes(result.data.plan.status)?'disabled':''}>${workspaceTeacher()?'确认并布置给学生':'确认创建本次学习'}</button>`;
        }else if(f.id==='continuity-vision-form'){
            const source=JSON.parse(f.dataset.source);const job=await api('/api/local/jobs',{mode:'vision',source,prompt:obj.prompt,peer_id:c3Peer()});closeModal();$('#continuity-explanation').textContent='正在将原图发送给你选择的视觉模型…';await c3Poll(job.id);
        }else if(f.id==='continuity-memory-form'){
            await c3('memory.capture',{task_ids:[currentTask.id],title:obj.title},c3Peer(),f.dataset.request);closeModal();await continuityMemory();c3RememberRoute('memory');notify('已保存有来源依据的学习札记。');
        }else if(f.id==='continuity-correct-form'){
            await c3('memory.correct',{memory_id:f.dataset.id,expected_revision:Number(f.dataset.revision),body:obj.body,allow_for_model:f.elements.allow_for_model.checked},c3Peer(),f.dataset.request);closeModal();await continuityMemory(true);
        }else if(f.id==='continuity-schedule-form'){
            await c3('review.create',{task_id:currentTask.id,prompt:obj.prompt,intervals:obj.intervals.split(/[,，]/).map(x=>Number(x.trim()))},null,f.dataset.request);closeModal();await continuityReviews();c3RememberRoute('reviews');notify('个人复习安排已保存。');
        }else if(f.id==='continuity-recall-form'){
            await c3('review.record',{card_id:f.dataset.id,expected_revision:Number(f.dataset.revision),response:obj.response,rating:obj.rating,additional_help:obj.additional_help||'未说明'},null,f.dataset.request);localStorage.removeItem('growth-recall:'+f.dataset.id);closeModal();await continuityReviews();notify('已记录本次回忆，未写入教师判断。');
        }else if(f.id==='continuity-adjust-form'){
            const payload={card_id:f.dataset.id,expected_revision:Number(f.dataset.revision),paused:f.elements.paused.checked};if(obj.days_from_now!=='')payload.days_from_now=Number(obj.days_from_now);
            await c3('review.adjust',payload,null,f.dataset.request);closeModal();await continuityReviews();
        }
    }catch(e){notify(e.message,true);}finally{continuityBusy=false;if(b)b.disabled=false;}
});
document.addEventListener('change',async e=>{
    try{
        if(e.target.id==='continuity-method'){
            const targeted=e.target.value==='targeted';$('#continuity-method-reason').textContent=continuityCatalog.methods[e.target.value].rationale;
            document.querySelectorAll('[data-c3-targeted]').forEach(el=>el.hidden=!targeted);$('#continuity-design-detail').open=targeted;
            ['obstacle','target_operation','question','criteria'].forEach(name=>$('#continuity-design-form').elements[name].required=targeted);
        }else if(e.target.id==='continuity-peer'){selectedPeer=e.target.value;await continuityMemory();}
        else if(e.target.id==='continuity-show-hidden')await continuityMemory(e.target.checked);
    }catch(error){notify(error.message,true);}
});
document.addEventListener('input',e=>{
    const f=e.target.closest('form[id^="continuity-"]');if(!f)return;delete f.dataset.request;
    if(f.id==='continuity-design-form'){continuityDraft=null;$('#continuity-design-preview').innerHTML='';}
    if(f.id==='continuity-recall-form')localStorage.setItem('growth-recall:'+f.dataset.id,f.elements.response.value);
});
