/* Presentation only. Permissions and judgments remain in LocalRuntime. */
(function(root){
    'use strict';
    function taskState(task,role){
        const last=(task.attempts||[]).at(-1);
        const queued=(task.local_submissions||[]).some(s=>s.delivery!=='acknowledged');
        if(task.state==='archived')return {key:'archived',label:'已归档',action:'查看记录'};
        if(task.state==='paused')return {key:'paused',label:'已暂停',action:'查看任务'};
        if(role==='student'&&queued)return {key:'sending',label:'本机已保存 · 等待送达',action:'查看发送记录'};
        if(!last)return {key:'todo',label:role==='teacher'?'等待学生提交':'待完成',action:role==='teacher'?'查看任务':'继续完成'};
        if(last.evaluation?.judgement==='needs_revision')return {key:'revision',label:'需要修订',action:role==='teacher'?'查看修订要求':'查看反馈并修订'};
        if(last.evaluation?.judgement==='meets_criteria')return {key:'feedback',label:'本次作品已获教师确认',action:'查看反馈'};
        if(last.review_history?.length)return {key:'feedback',label:'已有教师反馈',action:'查看反馈'};
        if(role==='teacher')return {key:'review',label:'待教师评阅',action:'评阅最新作品'};
        if(task.origin==='teacher')return {key:'waiting',label:'已提交 · 待教师评阅',action:'查看本次提交'};
        return {key:'feedback',label:last.automatic?'已有自动核对 · 非教师判断':'已提交 · 可记录反思',action:'查看记录与反思'};
    }
    function matches(task,filter,query,role){
        const state=taskState(task,role).key;
        const group=filter==='feedback'?['feedback','revision']:filter==='todo'?(role==='teacher'?['todo']:['todo','revision']):filter==='waiting'?['waiting','sending']:filter==='review'?['review']:filter==='closed'?['paused','archived']:null;
        return (!group||group.includes(state))&&[task.pack?.title,task._studentName,task.teacher_name].join(' ').toLowerCase().includes((query||'').trim().toLowerCase());
    }
    // URL view state is independent from the persisted teaching route and permissions.
    function routeTarget(hash){return {route:String(hash||'').replace(/^#/,'').split('?')[0]};}
    const routeHash=route=>'#'+route;
    const activeRoute=(view,returnRoute)=>view==='task'?returnRoute:view==='agent-job'?'agent':view==='policy-lab'?'policy':view;
    const api={taskState,matches,routeTarget,routeHash,activeRoute};
    if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WorkspaceState=api;
})(typeof window==='undefined'?this:window);
