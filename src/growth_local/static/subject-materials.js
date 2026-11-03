"use strict";
let subjectLibraryEpoch=0,subjectLibraryNotice=null;
const w8=(operation,payload={},request_id=uid())=>api('/api/local/capabilities/invoke',{contract_version:'companion.capability.v8',operation:'workspace.'+operation,payload,request_id});
const subjectCurrent=()=>academicContext?.selection.subject||'english';
const subjectLabel=id=>id==='legacy'?'历史工作区（待归属）':academicCatalog?.subjects[id]?.name||'待归属';
const subjectReadOnly=()=>subjectCurrent()==='legacy';
const subjectOptions=current=>Object.entries(academicCatalog.subjects).filter(([id])=>id!=='legacy').map(([id,item])=>`<option value="${h(id)}" ${id===current?'selected':''}>${h(item.name)}</option>`).join('');
function subjectSaveField(){return `<p class="small muted">保存位置：${h(subjectLabel(subjectCurrent()))}工作区。切换学科请先关闭此窗口，从“学科与路线”进入。</p><input name="subject" type="hidden" value="${h(subjectCurrent())}"><input name="classification_revision" type="hidden" value="0">`;}
const subjectPreviousStudyCall=studyCall;
studyCall=async function(operation,payload={},peer_id=null,request_id=uid()){
    if(operation==='material.save'&&payload.subject)return c7('academic.material.save',{...payload,classification_revision:Number(payload.classification_revision||0)},peer_id,request_id);
    const result=await subjectPreviousStudyCall(operation,payload,peer_id,request_id);
    if(operation==='material.read'&&!result.data.task_id){
        const c=(await c7('academic.asset.info',{asset_kind:'text',asset_id:result.data.id})).data.classification;
        result.data.classification={...c,subject:subjectReadOnly()?c.subject:subjectCurrent()};
    }
    return result;
};
const subjectPreviousAdd=studyAdd;
studyAdd=function(){if(subjectReadOnly())return notify('历史工作区只读，请先切换学科。',true);subjectPreviousAdd();$('#study-material-form').insertAdjacentHTML('afterbegin',subjectSaveField());};
const subjectPreviousAddPage=c3AddPage;
c3AddPage=function(){if(subjectReadOnly())return notify('历史工作区只读，请先切换学科。',true);subjectPreviousAddPage();$('#continuity-page-form').insertAdjacentHTML('afterbegin',subjectSaveField());};
const subjectPreviousRead=studyRead;
studyRead=async function(source){await subjectPreviousRead(source);if(subjectReadOnly())document.querySelectorAll('#study-reader [data-action="study-edit"],#study-reader [data-action="study-practice"],#study-reader [data-action="study-ask"]').forEach(b=>b.remove());};
function subjectImportButton(kind,asset){return `<button class="btn ghost small" data-action="subject-import" data-kind="${kind}" data-id="${h(asset.id)}" data-revision="${asset.revision}" data-hash="${h(asset.source_hash)}">迁入指定学科</button>`;}
studyHome=async function(){
    await academicLoad();const subject=subjectCurrent(),legacy=subjectReadOnly(),name=subjectLabel(subject);
    const epoch=++subjectLibraryEpoch;view='materials';studyMaterial=null;
    const [result,options]=await Promise.all([c7('academic.material.list',{subject:'all'}),studyCall('study.options')]);
    if(epoch!==subjectLibraryEpoch||view!=='materials')return;
    const data=result.data;studyMethods=options.data.methods;
    shell(`${workspaceHeading('LIBRARY / '+h(name),legacy?'历史资料（只读）':name+'资料库',legacy?'完整保留旧版资料和历史。确认资料归属后可迁入指定学科；原件继续保留。':'本页只显示'+h(name)+'工作区的资料。作业、反馈、札记与复习也在这个工作区内。',`<div class="subject-library-actions"><button class="btn ghost" data-action="ws-route" data-route="academic">切换学科</button>${legacy?'':'<button class="btn accent" data-action="study-add">＋ 添加资料</button>'}</div>`)}
        <div class="subject-filter-heading subject-library-controls"><strong>${legacy?'旧版原件保留':'独立学科工作区'} · 共 ${data.materials.length+data.pages.length} 份资料</strong><details class="subject-folder"><summary>查看本机保存位置</summary><code>${h(academicContext.workspace?.subjects.find(s=>s.id===subject)?.folder||academicContext.workspace?.legacy?.folder||'')}</code></details></div>
        ${subjectLibraryNotice?`<div class="subject-library-notice" role="status"><span>${h(subjectLibraryNotice.message)}</span><button class="btn text small" data-action="subject-enter" data-subject="${h(subjectLibraryNotice.subject)}">进入${h(subjectLabel(subjectLibraryNotice.subject))} →</button></div>`:''}
        <section class="card" id="subject-material-library"><div class="section-head"><h2>文字资料</h2><span class="small muted">${data.materials.length} 份</span></div><p class="small muted">支持文字、TXT、Markdown；按版本保存到本学科的 materials 文件夹。布置任务时只发送明确选择的内容。</p>
        ${data.materials.map(m=>`<article class="local-task"><div><h3>${h(m.title)}</h3><p class="small muted">第${m.revision}版 · ${h(m.source)}${legacy?' · 原有分类：'+h(subjectLabel(m.classification.subject)):''}</p></div><div class="actions"><button class="btn ghost" data-action="study-read" data-id="${h(m.id)}">打开资料 →</button>${legacy?subjectImportButton('text',m):''}</div></article>`).join('')||`<div class="empty"><p>这个工作区还没有文字资料。</p>${!legacy?`<button class="btn ghost" data-action="study-example">${subject.startsWith('subject-')?'体验通用资料示例':'体验'+h(name)+'原创示例'}</button>`:''}</div>`}</section>
        <section class="card" id="continuity-pages"><div class="section-head"><h2>原图资料</h2><span class="small muted">${data.pages.length} 份</span></div><p class="small muted">原始像素保存在本学科目录，支持 PNG / JPEG；PDF / OCR 暂未接入。</p>${data.pages.map(p=>`<article class="local-task"><div><h3>${h(p.title)}</h3><p class="small muted">第${p.revision}版 · ${p.width} × ${p.height} · ${h(p.source)}</p></div><div class="actions"><button class="btn ghost" data-action="c3-open-page" data-source="${h(JSON.stringify({page_id:p.id,revision:p.revision}))}">打开原图 →</button>${legacy?subjectImportButton('page',p):''}</div></article>`).join('')||'<p class="small muted">这个工作区还没有原图。</p>'}</section><div id="study-reader"></div>`);
};
c3Pages=async function(){};
function subjectExample(subject){
    const examples={
        english:['Campus garden · 英语原创示例','A campus garden can lower nearby temperatures, but its influence depends on location and design. Some nearby paths cooled while distant streets changed little. The authors recommend checking local conditions rather than assuming that every garden has the same effect.'],
        mathematics:['比例关系 · 数学原创示例','同一种笔记本每本6元。买2本需要12元，买5本需要30元。在单价不变且没有折扣的条件下，总价等于单价乘数量。比较“本数翻倍，总价也翻倍”和“总价始终等于本数加6”两种说法，用一个算例说明哪一种符合这里的条件。'],
        science:['单变量比较 · 科学原创示例','两组同种幼苗使用相同的土壤，获得相同的浇水量，但每天的光照时长不同。研究者记录两周后的高度。若要比较光照时长与生长的关系，还需要核对哪些起始条件？一次比较中观察到的差别，是否足以推广到所有植物？请区分观察、可能解释与仍需检查的条件。'],
        humanities:['记录与解释 · 人文原创示例','以下是虚构的城市交通材料：一份记录显示，新公交线路开通后，中心车站的乘车人数增加；另一份记录显示，同期周边街道正在施工。请区分材料直接说明的事实与“新增线路必然让所有居民出行更方便”这一解释，还缺哪些证据？'],
        other:['目标与证据 · 通用原创示例','一个小组希望用两周完成一份校园观察报告。现有材料包括一次访谈和三次现场记录。请先说明报告要回答的一个具体问题，再区分已经有的证据、仍缺的信息和现在可以开始的一步行动。不要把计划完成当作结论已经成立。']};
    const [title,text]=examples[subject]||examples.other;return {title,text,source:'团队原创演示素材，非教材或官方试题；内容适配需自行核对',subject,classification_revision:0};
}
async function subjectSaveExample(){await academicLoad();const subject=subjectCurrent();if(subjectReadOnly())throw Error('请先切换到学科工作区');return studyCall('material.save',subjectExample(subject),null,'subject-original-example-v1-'+subject);}
async function subjectAfterSave(subject){if(subject!==subjectCurrent())throw Error('学科工作区已切换，请刷新后核对资料');subjectLibraryNotice=null;history.replaceState({route:'materials'},'', '/#materials');}
document.addEventListener('click',async e=>{
    const b=e.target.closest('[data-action^="subject-"]');if(!b)return;e.preventDefault();b.disabled=true;
    try{if(b.dataset.action==='subject-return')await workspaceNavigate('materials');
        else if(b.dataset.action==='subject-enter'){await w8('select',{subject:b.dataset.subject});subjectLibraryNotice=null;await academicLoad();await workspaceNavigate('materials');}
        else if(b.dataset.action==='subject-import')modal('确认迁入哪一个学科',`<form id="subject-import-form" class="local-form" data-kind="${h(b.dataset.kind)}" data-id="${h(b.dataset.id)}" data-revision="${b.dataset.revision}" data-hash="${h(b.dataset.hash)}"><label class="field">目标学科<select name="subject" required><option value="" disabled selected>请选择实际所属学科</option>${subjectOptions('')}</select></label><p>复制已核对的原始版本到该学科的独立资料目录；旧版原件与历史作业保留。</p><label class="checkline"><input name="confirmed" type="checkbox" required>我已核对资料，确认迁入这个学科</label><button class="btn accent" type="submit">确认迁入</button></form>`);
    }catch(error){notify(error.message,true);}finally{if(b.isConnected)b.disabled=false;}
});
document.addEventListener('submit',async e=>{
    const f=e.target;if(f.id!=='subject-import-form')return;e.preventDefault();const b=f.querySelector('[type="submit"]');if(b.disabled)return;b.disabled=true;f.dataset.request||=uid();
    try{const subject=f.elements.subject.value;await w8('legacy.import',{subject,asset_kind:f.dataset.kind,asset_id:f.dataset.id,revision:Number(f.dataset.revision),source_hash:f.dataset.hash,human_confirmed:f.elements.confirmed.checked},f.dataset.request);
        subjectLibraryNotice={subject,message:'已迁入'+subjectLabel(subject)+'的独立资料目录，旧版原件继续保留。'};closeModal();await studyHome();
    }catch(error){notify(error.message,true);}finally{if(b.isConnected)b.disabled=false;}
});
document.addEventListener('input',e=>{const f=e.target.closest('#subject-import-form');if(f)delete f.dataset.request;});

const subjectPreviousAgentPage=agentPage;
agentPage=function(){subjectPreviousAgentPage();if(subjectCurrent()!=='english')$('#agent-mode option[value="draft"]')?.remove();};
const subjectPreviousShell=shell;
shell=function(html){subjectPreviousShell(html);if(subjectReadOnly()&&['task','students'].includes(view)){
    $('#workspace-content')?.insertAdjacentHTML('afterbegin','<p class="academic-note">历史工作区只读。原始提交和反馈完整保留；继续学习请切换到对应学科。</p>');
    document.querySelectorAll('#workspace-content form input,#workspace-content form textarea,#workspace-content form select,#workspace-content form button').forEach(el=>el.disabled=true);
    document.querySelectorAll('#workspace-content button[data-action="feedback"],#workspace-content button[data-action^="review-"],#workspace-content button[data-action="toggle-task"]').forEach(el=>el.disabled=true);
}};
