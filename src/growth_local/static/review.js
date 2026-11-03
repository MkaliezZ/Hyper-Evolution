"use strict";
let teacherReview=null,reviewBusy=false;
const c6=(operation,payload={},peer_id=null,request_id=uid())=>api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v6',operation,payload,peer_id,request_id});
const oldStudyAssess=studyAssess;
studyAssess=function(){if(!workspaceTeacher())return oldStudyAssess();reviewOpen().catch(e=>notify(e.message,true));};
const reviewStatus=s=>({ungraded:'暂不能判断',partial:'有部分证据',supported:'已有支持证据',needs_revision:'需要修订'})[s]||s;
function reviewSource(s){return `${s.material?`<details open><summary>本次题目与材料</summary><pre class="review-original">${h(s.material)}</pre></details>`:''}${s.items?.length?`<details><summary>题目、学生作答与教师参考</summary>${s.items.map(i=>`<p><strong>${h(i.prompt)}</strong></p><p class="small">学生作答：${h(JSON.stringify(s.answers[i.id]??'未作答'))}</p><p class="small muted">教师参考：${h(JSON.stringify(i.key??[]))} ${h(i.evidence||'')}</p>`).join('')}</details>`:''}`;}
async function reviewEnhance(){
    if(view!=='task'||!currentTask?.attempts.length)return;
    if(!workspaceTeacher()){
        const aid=currentTask.companion_review_assistance?.find(r=>r.submission_id===currentTask.attempts.at(-1).id);
        if(aid){const n=document.createElement('p');n.className='local-banner';n.textContent='本次反馈由教师确认，参考了AI预审'+(aid.teacher_modified?'并经教师修改':'')+'；AI预审本身不是教师结论。';$('#study-task-panel')?.prepend(n);}
        return;
    }
    const button=document.querySelector('[data-action="study-assess"]');if(button)button.textContent='AI预审 / 人工评阅';
    const panel=document.createElement('section');panel.className='card';panel.id='teacher-review-status';panel.innerHTML='<h2>先准备预审，再由你决定。</h2><p>AI依据本次目标、评价标准和实际提交准备候选反馈。你可以逐项修改、保存本机草稿，确认后再发给学生。</p><button class="btn ghost" data-action="review-open">打开AI预审与教师评阅 →</button><p class="small muted" id="teacher-review-ready">正在读取本次预审状态…</p>';
    $('#study-task-panel')?.before(panel);const id=currentTask.id;
    try{const data=(await c6('review.list',{task_id:id},selectedPeer)).data;if(view==='task'&&currentTask?.id===id&&$('#teacher-review-ready'))$('#teacher-review-ready').textContent=data.prereviews.some(r=>r.current)?'已有对应当前作品的AI预审；尚需你核对并确认。':'当前没有可采用的AI预审，可手动发起；也可直接人工填写。';}catch(e){if($('#teacher-review-ready'))$('#teacher-review-ready').textContent=e.message;}
}
async function reviewOpen(){
    if(!currentTask?.attempts.length)throw Error('先收到一份实际作品，再进行评阅。');
    const task=currentTask,target={task_id:task.id,submission_id:task.attempts.at(-1).id},peer=selectedPeer;
    const [ctx,history,settings]=await Promise.all([c6('review.context',target,peer),c6('review.list',{task_id:task.id},peer),c6('review.settings')]);
    const draft=history.data.drafts.find(d=>d.current),ai=history.data.prereviews.find(p=>p.current);
    teacherReview={epoch:uid(),target,peer,context:ctx.data,draft:draft||null,ai:ai||null,adopted:draft?.prereview_id||null,pendingPublish:null};
    const source=ctx.data.source;
    modal('AI预审与教师评阅',`<div class="review-grid"><section><details open><summary>本次原作与要求</summary><p><strong>任务：</strong>${h(source.instructions)}</p><pre class="review-original">${h(source.work||'本次为客观作答或附件作品，请在任务页核对原件。')}</pre><ol>${source.criteria.map(x=>`<li>${h(x)}</li>`).join('')}</ol>${source.exact_checks?`<details><summary>程序客观核对（非AI评分）</summary><pre class="local-json">${h(JSON.stringify(source.exact_checks,null,2))}</pre></details>`:''}</details>
        <div class="review-ai"><h3>AI预审候选</h3><p class="small muted">使用教师自己的API；必要上下文发送至你配置的服务商。预审不改原答、不自动发给学生。</p><div class="actions"><button class="btn accent" data-action="review-generate" ${settings.data.model_configured?'':'disabled'}>生成 / 重新生成AI预审</button>${!settings.data.model_configured?'<button class="btn ghost" data-action="review-configure">先配置自己的API</button>':''}</div><label class="checkline"><input id="review-automatic" type="checkbox" ${settings.data.settings.automatic?'checked':''} ${settings.data.model_configured?'':'disabled'}>收到新的提交时自动准备预审（会消耗我的API额度）</label><p id="review-job-state" class="small" role="status"></p><div id="review-ai-report"></div></div></section>
        <section><h3>可修改的教师反馈</h3><p class="small muted">“采用候选”才会填入下方。AI完成时不会覆盖你正在编辑的内容。正式结论默认不判断达标。</p><form id="review-editor" class="local-form">${source.criteria.map((criterion,i)=>`<fieldset class="review-dimension"><legend>${h(criterion)}</legend><label class="field">我的观察<textarea name="dimension_${i}" maxlength="1500"></textarea></label><label class="field">原答或文字材料中的依据<input class="input" name="evidence_${i}" maxlength="1500"></label><label class="field">该项状态<select name="status_${i}">${['ungraded','partial','supported','needs_revision'].map(s=>`<option value="${s}">${reviewStatus(s)}</option>`).join('')}</select></label></fieldset>`).join('')}
        <label class="field">给学生的具体反馈<textarea name="comment" maxlength="4000" required></textarea></label><label class="field">下一步<input class="input" name="next_step" maxlength="2000" required></label><label class="field">本次正式结论<select name="outcome"><option value="ungraded">暂不判断达标</option><option value="partial">有部分证据，仍需补充</option><option value="needs_revision">需要修订</option><option value="meets_criteria">教师确认本次作品达标</option></select></label>
        ${ctx.data.coverage.needs_sound?'<label class="checkline"><input name="sound_review_confirmed" type="checkbox">我已亲自听取并核对本次录音的声音维度（AI没有分析声音）</label>':''}<label class="checkline"><input name="human_review_confirmed" type="checkbox">我已亲自查看作品及评价依据，确认以下反馈由我负责</label>
        <div class="actions"><button class="btn ghost" type="button" data-action="review-save">保存本机草稿</button><button class="btn accent" type="submit">确认教师反馈并发送</button></div><p id="review-save-state" class="small muted" role="status">本机草稿不会发送给学生。</p></form></section></div>`);
    document.querySelector('.modal').classList.add('review-modal');document.querySelector('.review-original').insertAdjacentHTML('beforebegin',reviewSource(source));
    if(ctx.data.coverage.limitations.length)document.querySelector('.review-ai').insertAdjacentHTML('beforebegin',`<ul class="small muted">${ctx.data.coverage.limitations.map(x=>`<li>${h(x)}</li>`).join('')}</ul>`);
    const old=history.data.prereviews.filter(p=>!p.current);if(old.length)document.querySelector('.review-ai').insertAdjacentHTML('afterend',`<details><summary>历史AI候选（${old.length}份，只读参考）</summary>${old.slice(0,10).map(p=>`<article><p class="small muted">${h(p.created)} · ${h(p.model_name)} · 对应旧依据，不可直接采用</p><p>${h(p.report.summary)}</p><p>${h(p.report.comment)}</p></article>`).join('')}</details>`);
    if(settings.data.settings.automatic)$('#review-automatic').disabled=false;
    reviewRenderAI();
    if(draft)reviewFill(draft.fields);
}
function reviewFill(fields){const f=$('#review-editor');if(!f)return;for(const k of ['comment','next_step','outcome'])f.elements[k].value=fields[k]||'ungraded';teacherReview.context.source.criteria.forEach((criterion,i)=>{const d=fields.dimensions.find(d=>d.criterion===criterion);f.elements['dimension_'+i].value=d?.observation||'';f.elements['evidence_'+i].value=d?.evidence||'';f.elements['status_'+i].value=d?.status||'ungraded';});f.elements.human_review_confirmed.checked=false;if(f.elements.sound_review_confirmed)f.elements.sound_review_confirmed.checked=false;}
function reviewRenderAI(){const p=teacherReview.ai,box=$('#review-ai-report');if(!box)return;if(!p){box.innerHTML='<p class="muted">还没有预审候选。可以先人工填写；生成失败不会影响原作。</p>';return;}const r=p.report;box.innerHTML=`<article><strong>候选摘要</strong><p>${h(r.summary)}</p>${r.dimensions.map(d=>`<div class="result-item"><strong>${h(d.criterion)} · ${h(reviewStatus(d.status))}</strong><p>${h(d.observation)}</p>${d.evidence?`<blockquote>${h(d.evidence)}</blockquote>`:''}</div>`).join('')}<h4>需要你核对 / 无法判断</h4><ul>${r.uncertainties.map(x=>`<li>${h(x)}</li>`).join('')}</ul><p class="small muted">模型：${h(p.model_name)} · 引用文字已核对，专业判断仍需审阅。</p><button class="btn ghost" data-action="review-adopt">采用为可编辑草稿</button></article>`;}
function reviewFields(){const f=$('#review-editor'),s=teacherReview.context.source;return {comment:f.elements.comment.value,next_step:f.elements.next_step.value,outcome:f.elements.outcome.value,
    dimensions:s.criteria.map((criterion,i)=>({criterion,observation:f.elements['dimension_'+i].value,evidence:f.elements['evidence_'+i].value,status:f.elements['status_'+i].value}))};}
async function reviewSave(){const s=teacherReview;if(!s||!$('#review-editor'))throw Error('请重新打开本次评阅');const fields=reviewFields();if(!fields.comment.trim()||!fields.next_step.trim())throw Error('请先填写具体反馈和下一步');
    const d=(await c6('review.draft.save',{...s.target,context_hash:s.context.context_hash,prereview_id:s.adopted,fields,draft_id:s.draft?.id||null,expected_revision:s.draft?.revision||0},s.peer)).data.draft;s.draft=d;$('#review-save-state').textContent='已保存本机草稿第 '+d.revision+' 版，尚未发送。';return d;}
async function reviewPoll(id,epoch){try{const s=teacherReview;if(!s||s.epoch!==epoch||!$('#review-editor'))return;const job=(await c6('review.job',{job_id:id},s.peer)).data.job;if(job.status==='completed'){
        const history=(await c6('review.list',{task_id:s.target.task_id},s.peer)).data;const ai=history.prereviews.find(p=>p.id===job.result.prereview_id&&p.current);if(!ai)throw Error('预审完成后作品已更新，请刷新本次评阅。');s.ai=ai;reviewRenderAI();$('#review-job-state').textContent='预审已准备好。需要你核对，采用后仍可逐项修改。';document.querySelector('[data-action="review-generate"]').disabled=false;
    }else if(job.status==='failed')throw Error(job.error||'预审未完成，可以重试或继续人工评阅。');else{$('#review-job-state').textContent=job.status==='queued'?'预审已排队，等待本机服务处理…':'AI正在核对当前任务与提交…';setTimeout(()=>reviewPoll(id,epoch),1400);}
    }catch(e){if(teacherReview?.epoch===epoch&&$('#review-job-state')){$('#review-job-state').textContent=e.message;document.querySelector('[data-action="review-generate"]').disabled=false;}notify(e.message,true);}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action^="review-"]');if(!b)return;e.preventDefault();e.stopImmediatePropagation();if(reviewBusy)return;reviewBusy=true;
    try{const a=b.dataset.action;if(teacherReview?.pendingPublish&&a!=='review-open')throw Error('这次发布结果尚待确认，请先重试确认或刷新查看反馈。');if(a==='review-open')await reviewOpen();else if(a==='review-configure'){closeModal();await workspaceNavigate('settings');}
        else if(a==='review-generate'){b.disabled=true;const s=teacherReview;const job=(await c6('review.start',s.target,s.peer)).data.job;reviewPoll(job.id,s.epoch);}
        else if(a==='review-adopt'){const p=teacherReview.ai;teacherReview.adopted=p.id;reviewFill({comment:p.report.comment,next_step:p.report.next_step,dimensions:p.report.dimensions,outcome:'ungraded'});$('#review-save-state').textContent='已填入AI候选，请逐项修改核对；尚未保存或发送。';}
        else if(a==='review-save')await reviewSave();
    }catch(error){notify(error.message,true);if(b.dataset.action==='review-generate')b.disabled=false;}finally{reviewBusy=false;}
},true);
document.addEventListener('change',async e=>{if(e.target.id!=='review-automatic')return;try{await c6('review.settings.save',{automatic:e.target.checked});notify(e.target.checked?'已开启：新提交使用教师自己的API准备预审，不自动发布。':'已关闭自动预审。');}catch(error){e.target.checked=!e.target.checked;notify(error.message,true);}});
document.addEventListener('submit',async e=>{if(e.target.id!=='review-editor')return;e.preventDefault();if(reviewBusy)return;reviewBusy=true;const s=teacherReview,f=e.target,b=f.querySelector('[type=submit]');b.disabled=true;
    try{if(!f.elements.human_review_confirmed.checked)throw Error('请先亲自核对作品和评价依据，再勾选教师确认。');
        if(!s.pendingPublish){const fields=reviewFields();if(fields.outcome==='meets_criteria'&&fields.dimensions.some(d=>d.status!=='supported'||!d.observation.trim()))throw Error('确认达标前，请逐项填写观察并核对已有支持证据。');if(fields.outcome==='meets_criteria'&&s.context.coverage.needs_sound&&!f.elements.sound_review_confirmed?.checked)throw Error('请亲自听取录音核对声音维度，或先不判断整体达标。');const d=await reviewSave();s.pendingPublish={request_id:uid(),draft_id:d.id,expected_revision:d.revision,draft_hash:d.content_hash,human_review_confirmed:true,sound_review_confirmed:f.elements.sound_review_confirmed?.checked===true};}
        const {request_id,...payload}=s.pendingPublish;await c6('review.publish',payload,s.peer,request_id);s.pendingPublish=null;closeModal();await openTask(s.target.task_id);notify('教师反馈已保存并加入发送队列；AI原稿与修改历史保留在教师本机。');
    }catch(error){notify(error.message,true);if(s.pendingPublish){b.textContent='重试完成这次确认';f.querySelectorAll('input,textarea,select').forEach(x=>x.disabled=true);$('#review-save-state').textContent='发布结果尚待确认。请重试同一次请求，或刷新查看已收到的反馈，避免另发重复评语。';}}
    finally{reviewBusy=false;b.disabled=false;}
});
