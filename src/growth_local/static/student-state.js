(function(root){
 'use strict';
 const routes=['home','academic','tasks','feedback','planning','paths','connections','settings','guide','writing'];
 const groups=[['本次学习',[['home','学习首页'],['tasks','我的任务'],['feedback','反馈与修订']]],['目标与安排',[['planning','老师的规划'],['paths','学习安排']]],['连接与帮助',[['connections','我的老师'],['settings','模型与本机设置'],['guide','使用指南']]]];
 const tasks=rows=>rows.filter(t=>t.origin==='teacher');
 const plans=(rows,device)=>rows.filter(p=>p.author_role==='teacher'&&p.owner_device!==device&&p.signature_verified);
 const schedules=(rows,device)=>rows.filter(p=>p.owner_device!==device);
 const section=(view,back)=>['writing','materials','task','k12','practice','agent-job'].includes(view)?back==='feedback'?'feedback':'tasks':view;
 const api={routes,groups,tasks,plans,schedules,section};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StudentState=api;
})(typeof window==='undefined'?this:window);
